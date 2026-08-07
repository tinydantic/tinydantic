# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""The TinydanticModel base class and query helpers."""

from __future__ import annotations

import sys

from importlib import metadata
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    cast,
    overload,
)
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.alias_generators import to_snake
from tinydb.queries import Query, where
from tinydb.table import Document, Table

from tinydantic._config import (
    _CONFIG_KEYS,
    CONFIG_ATTR,
    TinydanticConfig,
    check_config_ambiguity,
    get_config_value,
)
from tinydantic._errors import (
    ConstraintFieldError,
    DatabaseNotBoundError,
    DocumentAlreadyExistsError,
    DocumentIDRequiredError,
    DocumentIDUpdateError,
    DocumentNotFoundError,
    RevisionFieldError,
    RevisionUpdateError,
    SelectorError,
    ShadowedFieldError,
    StaleDocumentError,
    TinydanticError,
    UniqueConstraintError,
    UnknownUpdateFieldError,
)
from tinydantic._fields import Unique, UniqueConstraint
from tinydantic._find import FindQuery
from tinydantic._query import (
    DocIdCondition,
    DocIdQuery,
    has_id_condition,
)
from tinydantic.tinydb.operations import replace

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
        Iterable,
        Mapping,
    )
    from collections.abc import (
        Set as AbstractSet,
    )

    # pydantic's ModelMetaclass lives in a private module. We
    # type-check against the real class but resolve it at runtime as
    # type(BaseModel), so tinydantic never imports pydantic internals
    # at runtime and survives pydantic moving the module.
    from pydantic._internal._model_construction import ModelMetaclass
    from tinydb import TinyDB
    from tinydb.queries import QueryLike

    # Self is typing_extensions-only on Python 3.10 (typing.Self is
    # 3.11+). This import is TYPE_CHECKING-only, so typing_extensions
    # is not a runtime dependency.
    from typing_extensions import Self
else:
    ModelMetaclass = type(BaseModel)

# Name of the per-class attribute caching per-field TypeAdapters
# (built lazily by _field_adapter for update() serialization).
_FIELD_ADAPTERS_ATTR = "__tinydantic_field_adapters__"

# Sentinel distinguishing "find() called with no condition" (the
# explicit whole-table spelling) from an accidental None value.
_FIND_NOT_GIVEN = object()

# Name of the per-class attribute caching unique field names
# (computed once in __pydantic_init_subclass__).
_UNIQUE_MARKERS_ATTR = "__tinydantic_unique_markers__"

if sys.version_info >= (3, 14):
    from annotationlib import Format, call_annotate_function

# Class-namespace keys that may hold a PEP 649 deferred-annotations
# function on Python 3.14+. CPython's compiler emits
# ``__annotate_func__`` (``type.__new__`` renames it to the class's
# ``__annotate__`` afterwards); the PEP-spelled ``__annotate__`` is
# kept as a fallback in case that implementation detail changes.
_ANNOTATE_KEYS = ("__annotate_func__", "__annotate__")


def _deferred_annotate_key(namespace: dict[str, Any]) -> str | None:
    """Return the deferred-annotations key present, if any."""
    for key in _ANNOTATE_KEYS:
        if key in namespace:
            return key
    return None


def _declared_annotations(namespace: dict[str, Any]) -> dict[str, Any]:
    """Return a class body's own annotations, eager or deferred.

    Class bodies produce an eager ``__annotations__`` dict on
    Python 3.13 and earlier — and on any version in modules using
    ``from __future__ import annotations`` — but under PEP 649
    (3.14+ default semantics) they instead emit a deferred
    annotate function. Both shapes are read here; the deferred
    form is materialized with ``Format.FORWARDREF`` so
    unresolvable names cannot raise during class creation.
    """
    if "__annotations__" in namespace:
        return dict(namespace["__annotations__"])
    if sys.version_info >= (3, 14):
        key = _deferred_annotate_key(namespace)
        if key is not None:
            return dict(
                call_annotate_function(namespace[key], Format.FORWARDREF),
            )
    return {}


def _inject_revision_annotation(namespace: dict[str, Any]) -> None:
    """Add the ``revision_id`` annotation to a class-body namespace.

    On eager-annotation class bodies this extends the
    ``__annotations__`` dict. Under PEP 649 deferred annotations
    (3.14+) it wraps the compiler-emitted annotate function
    in place instead — assigning an eager ``__annotations__`` dict
    there would *shadow* the deferred annotations and silently
    erase the user's own field annotations (pydantic would then
    reject their defaulted, "non-annotated" attributes).
    """
    key = (
        _deferred_annotate_key(namespace)
        if sys.version_info >= (3, 14)
        else None
    )
    if sys.version_info >= (3, 14) and key is not None:
        prior = namespace[key]

        def annotate(format_value: int, /) -> dict[str, Any]:
            """Merge ``revision_id`` into the deferred annotations."""
            fmt = Format(format_value)
            merged = dict(call_annotate_function(prior, fmt))
            merged["revision_id"] = (
                "UUID | None" if fmt is Format.STRING else UUID | None
            )
            return merged

        namespace[key] = annotate
        return
    annotations = dict(namespace.get("__annotations__", {}))
    annotations["revision_id"] = UUID | None
    namespace["__annotations__"] = annotations


class _NothingMatchedError(Exception):
    """Internal control-flow marker for id-condition writes.

    Raised inside the updater handed to ``Table._update_table``
    when no document matched, aborting the cycle before its
    storage write — a no-match write then costs one read and zero
    writes, matching the public no-match paths.
    """


def q(field: Any) -> Query:
    """Build a typed TinyDB Query from a field or a field name.

    At runtime, class-level field access like ``User.name`` already
    returns a [Query][tinydb.queries.Query] (courtesy of the model
    metaclass), but static type checkers see the field annotation
    instead, so
    ``User.name == "Alice"`` types as ``bool``. Wrapping the field in
    ``q()`` gives the type checker the runtime truth:

    ```python
    User.search(q(User.name) == "Alice")
    ```

    A string builds a query on that document key
    (``tinydb.queries.where``). This is the escape hatch for fields
    whose names collide with model methods (``search``, ``get``,
    ``count``, ...) and are therefore unreachable through the
    ``Model.field`` shorthand:

    ```python
    Command.search(q("search") == "fuzzy")
    ```

    Note that ``q(Model.id)`` and ``q("id")`` differ: ``Model.id``
    builds a document-id query (translated to TinyDB ``doc_id``
    operations), while the string form queries a literal ``id``
    key in the document body — which tinydantic never writes.

    Args:
        field: A class-level field expression (e.g. ``User.name``)
            or a field name string (e.g. ``"name"``).

    Returns:
        The field expression unchanged, or a Query on the named
        field — either way, typed as a Query.

    Raises:
        TypeError: If ``field`` is neither a TinyDB Query nor a
            string — for example when called with an instance
            attribute instead of class-level field access.
    """
    if isinstance(field, str):
        return where(field)
    if not isinstance(field, Query):
        msg = (
            f"q() expected a TinyDB Query (class-level field access "
            f"like Model.field) or a field name string, got "
            f"{type(field).__name__!r}"
        )
        raise TypeError(msg)
    return field


class TinydanticModelMetaclass(ModelMetaclass):
    """Metaclass providing class-level field queries.

    Accessing a model *field* on the model *class* (not an instance)
    returns ``tinydb.queries.where(field_name)``, so expressions like
    ``User.name == "Alice"`` build TinyDB queries directly from the
    model definition.

    The ``id`` field is special-cased: it maps to TinyDB's
    ``doc_id``, which never appears in the stored document body, so
    ``Model.id`` returns a ``DocIdQuery`` (translated by the model's
    query methods to document-id operations) instead of a
    ``where("id")`` body query that would silently match nothing.

    Classes created with ``use_revision=True`` additionally get a
    ``revision_id: UUID | None`` field injected before pydantic
    collects fields — the optimistic-concurrency token rotated by
    every write path. Injection must happen here (not in
    ``__init_subclass__``): pydantic builds the field set from the
    class namespace, so the field has to exist in the namespace
    before class creation, which is also why ``use_revision``
    cannot be late-bound with ``bind()``.
    """

    def __new__(
        mcs,
        cls_name: str,
        bases: tuple[type[Any], ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> type:
        """Create the class, injecting ``revision_id`` if opted in.

        Raises:
            RevisionFieldError: If the class resolves
                ``use_revision=True`` (its own kwarg or inherited)
                but declares its own ``revision_id`` field.
        """
        explicit = kwargs.get("use_revision")
        inherited = any(
            get_config_value(base, "use_revision", default=False)
            for base in bases
        )
        resolved = inherited if explicit is None else explicit
        declared = "revision_id" in _declared_annotations(namespace)
        if resolved and declared:
            raise RevisionFieldError(model_name=cls_name)
        already_a_field = any(
            "revision_id" in getattr(base, "model_fields", {})
            for base in bases
        )
        if explicit and not already_a_field:
            _inject_revision_annotation(namespace)
            namespace["revision_id"] = Field(
                default=None,
                description="Optimistic-concurrency token",
            )
        return super().__new__(mcs, cls_name, bases, namespace, **kwargs)

    def __getattr__(cls, attr: str) -> Any:
        """Return a field Query, falling back to normal lookup.

        Pydantic calls ``__getattr__`` for each field while the model
        class is still being built; returning a Query then would break
        model construction (``RuntimeError: Empty query was
        evaluated``). The ``__pydantic_complete__`` guard defers query
        behavior until the model is fully built.
        """
        if cls.__pydantic_complete__ and attr in cls.model_fields:
            if attr == "id":
                # id maps to TinyDB's doc_id, which never appears
                # in the document body — a plain where("id") query
                # would silently match nothing.
                return DocIdQuery()
            return where(attr)
        return super().__getattr__(attr)  # type: ignore[misc]


class TinydanticModel(BaseModel, metaclass=TinydanticModelMetaclass):
    """Base class for tinydantic models.

    Subclass to define a document model, passing tinydantic
    configuration as class keyword arguments:

    ```python
    from tinydb import TinyDB
    from tinydantic import TinydanticModel

    db = TinyDB("db.json")


    class User(TinydanticModel, database=db, table_name="users"):
        name: str
    ```

    Configuration is stored per class in ``__tinydantic_config__`` and
    resolved by walking the MRO — deliberately NOT in pydantic's
    ``model_config``; see the ``tinydantic._config`` module docstring
    for the design rationale (pydantic#9992).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        # Reserve the tinydantic_ prefix so future tinydantic methods
        # cannot collide with user-defined fields (the use case Samuel
        # Colvin described in pydantic#10315).
        protected_namespaces=("tinydantic_",),
        # Assignment must not silently corrupt an instance that will
        # later be persisted; subclasses may opt out via their own
        # model_config.
        validate_assignment=True,
    )

    __tinydantic_config__: ClassVar[TinydanticConfig] = {}

    # --- model fields ---

    id: int | None = Field(
        default=None,
        description="Document ID",
    )

    if TYPE_CHECKING:
        # Static-only declaration of the field the metaclass
        # injects on use_revision=True models, so user code like
        # ``book.revision_id`` (ETag flows) type-checks. The block
        # never runs, so pydantic sees no field here and models
        # without use_revision raise AttributeError at runtime.
        revision_id: UUID | None = None

    # --- lifecycle hooks ---

    def before_save(self) -> None:
        """Run before any whole-model write of ``self``.

        Fires once at the start of ``insert()``, ``save()``,
        ``replace()``, ``upsert()``, and for each document of
        ``insert_multiple()`` — before serialization, so changes
        made here (audit timestamps are the classic case) are
        validated and persisted with the write. Raising aborts the
        write. Field-level writes (``update()``, ``patch()``) do
        not call it: they never write the whole model, so fields
        set here would be silently dropped. The default does
        nothing; overrides can chain with ``super().before_save()``.
        """

    def after_load(self) -> None:
        """Run after a document is validated into a model.

        Fires at the end of
        [from_tinydb_document][tinydantic.TinydanticModel.from_tinydb_document]
        — i.e. after every read that materializes an instance —
        with the real ``id`` set. Not called on ordinary
        construction, and changes made here affect only the
        in-memory instance (reads persist nothing). The default
        does nothing; overrides can chain with
        ``super().after_load()``.
        """

    # --- configuration ---

    def __init_subclass__(  # noqa: PLR0913
        cls,
        *,
        database: TinyDB | None = None,
        table_name: str | None = None,
        use_revision: bool | None = None,
        validate_writes: bool | None = None,
        shadowed_fields: tuple[str, ...] | None = None,
        constraints: tuple[UniqueConstraint, ...] | None = None,
        **kwargs: Any,
    ) -> None:
        """Capture tinydantic class keywords.

        Pydantic pops its own known config keys from class keyword
        arguments and forwards the rest here (a public extension
        point), so no metaclass involvement is needed for
        configuration. Only explicitly provided values are stored on
        this class — ``None`` means "not provided", and resolution
        falls through to base classes via
        ``get_config_value`` in ``tinydantic._config``.
        """
        super().__init_subclass__(**kwargs)
        config: TinydanticConfig = {}
        if database is not None:
            config["database"] = database
        if table_name is not None:
            config["table_name"] = table_name
        if use_revision is not None:
            config["use_revision"] = use_revision
        if validate_writes is not None:
            config["validate_writes"] = validate_writes
        if shadowed_fields is not None:
            config["shadowed_fields"] = shadowed_fields
        if constraints is not None:
            # Validation waits for __pydantic_init_subclass__ —
            # model_fields does not exist yet at this point.
            config["constraints"] = constraints
        setattr(cls, CONFIG_ATTR, config)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Validate config after pydantic finishes building the class.

        Raises:
            AmbiguousConfigError: If unrelated base classes supply
                conflicting tinydantic config (see
                ``check_config_ambiguity`` in ``tinydantic._config``).
            ShadowedFieldError: If a model field shadows an
                existing class attribute (the ``Model.field``
                query sugar would silently break) and is not
                listed in the ``shadowed_fields=`` class kwarg.
        """
        super().__pydantic_init_subclass__(**kwargs)
        check_config_ambiguity(cls)
        allowed = get_config_value(cls, "shadowed_fields", default=())
        shadowed: dict[str, str] = {}
        for name in cls.model_fields:
            if name == "id" or name in allowed:
                # id is tinydantic's own (Model.id builds a
                # DocIdQuery); allowed names are the documented
                # opt-out.
                continue
            for klass in cls.__mro__:
                if name in vars(klass):
                    # A real class attribute wins over the
                    # metaclass __getattr__ that builds queries,
                    # so this field's sugar is broken.
                    shadowed[name] = f"{klass.__name__}.{name}"
                    break
        if shadowed:
            raise ShadowedFieldError(
                model_name=cls.__name__,
                shadowed=shadowed,
            )
        cls._validate_constraints(
            get_config_value(cls, "constraints", default=()) or (),
        )
        markers: list[UniqueConstraint] = []
        for name, info in cls.model_fields.items():
            for meta in info.metadata:
                # The bare class is accepted alongside instances:
                # treating Annotated[str, Unique] as inert would be
                # a silent failure.
                if meta is Unique:
                    markers.append(UniqueConstraint(name))
                    break
                if isinstance(meta, Unique):
                    markers.append(
                        UniqueConstraint(name, key=meta.key),
                    )
                    break
        setattr(cls, _UNIQUE_MARKERS_ATTR, tuple(markers))

    @classmethod
    def _validate_constraints(
        cls,
        constraints: tuple[UniqueConstraint, ...],
    ) -> None:
        """Reject constraints naming ``id`` or non-model fields.

        Both failure modes would otherwise be *silent*: ``id`` is
        never stored in the document body (it maps to TinyDB's
        ``doc_id``), so an id constraint would never match; an
        unknown field reads as ``None`` in every body, so its
        constraint would never enforce.

        Raises:
            ConstraintFieldError: On the first offending field.
        """
        for constraint in constraints:
            for name in constraint.fields:
                if name == "id":
                    raise ConstraintFieldError(
                        model_name=cls.__name__,
                        constraint_fields=constraint.fields,
                        field=name,
                        reason="id",
                    )
                if name not in cls.model_fields:
                    raise ConstraintFieldError(
                        model_name=cls.__name__,
                        constraint_fields=constraint.fields,
                        field=name,
                        reason="unknown",
                    )

    @classmethod
    def bind(
        cls,
        *,
        database: TinyDB | None = None,
        table_name: str | None = None,
        validate_writes: bool | None = None,
        shadowed_fields: tuple[str, ...] | None = None,
        constraints: tuple[UniqueConstraint, ...] | None = None,
    ) -> None:
        """Bind or rebind tinydantic config after class definition.

        The late-binding escape hatch for tests and application
        factories where no TinyDB instance exists at import time:

        ```python
        class User(TinydanticModel):
            name: str


        User.bind(database=TinyDB("db.json"))
        ```

        Every [TinydanticConfig][tinydantic.TinydanticConfig] key
        can be bound late. Only the keys passed are updated; other
        keys keep their current (possibly inherited) values.
        Binding a subclass never affects its parents. The inverse
        is [unbind][tinydantic.TinydanticModel.unbind].
        """
        config = cast(
            "TinydanticConfig",
            dict(cls.__dict__.get(CONFIG_ATTR, {})),
        )
        if database is not None:
            config["database"] = database
        if table_name is not None:
            config["table_name"] = table_name
        if validate_writes is not None:
            config["validate_writes"] = validate_writes
        if shadowed_fields is not None:
            config["shadowed_fields"] = shadowed_fields
        if constraints is not None:
            cls._validate_constraints(constraints)
            config["constraints"] = constraints
        setattr(cls, CONFIG_ATTR, config)

    @classmethod
    def unbind(cls, *keys: str) -> None:
        """Remove late-bound tinydantic config from this class.

        The inverse of [bind][tinydantic.TinydanticModel.bind],
        for test fixtures that attach a database in setup and must
        detach it in teardown. With no arguments, every config key
        this class set is removed; with key names, only those.
        Only this class's own settings are removed — values
        inherited from base classes resurface, mirroring bind()'s
        rule that binding a subclass never affects its parents.
        Unbinding a key this class never set is a no-op.

        Args:
            keys: Config key names to remove (see
                [TinydanticConfig][tinydantic.TinydanticConfig]).
                Empty means all of them.

        Raises:
            ValueError: If a key name is not a tinydantic config
                key.
        """
        unknown = [key for key in keys if key not in _CONFIG_KEYS]
        if unknown:
            names = ", ".join(repr(key) for key in sorted(unknown))
            valid = ", ".join(repr(key) for key in _CONFIG_KEYS)
            msg = (
                f"unbind() got unknown config key(s) {names}; "
                f"valid keys are {valid}"
            )
            raise ValueError(msg)
        config = cast(
            "TinydanticConfig",
            dict(cls.__dict__.get(CONFIG_ATTR, {})),
        )
        for key in keys or _CONFIG_KEYS:
            config.pop(key, None)  # type: ignore[misc]
        setattr(cls, CONFIG_ATTR, config)

    @classmethod
    def get_database(cls) -> TinyDB:
        """Get the TinyDB database this model is bound to.

        Returns:
            The bound TinyDB database.

        Raises:
            DatabaseNotBoundError: If no database is configured
                anywhere in the class hierarchy.
        """
        database: TinyDB | None = get_config_value(cls, "database")
        if database is None:
            raise DatabaseNotBoundError(cls.__name__)
        return database

    @classmethod
    def get_table(cls) -> Table:
        """Get the TinyDB table for this model.

        Uses the configured ``table_name`` when set, otherwise the
        snake_case form of the class name (``AdminUser`` →
        ``admin_user``).
        """
        table_name: str | None = get_config_value(cls, "table_name")
        if not table_name:
            return cls.get_database().table(name=to_snake(cls.__name__))
        return cls.get_database().table(name=table_name)

    @classmethod
    def from_tinydb_document(cls, document: Mapping) -> Self:
        """Validate a TinyDB document into a model instance.

        Maps TinyDB's ``doc_id`` onto the model's ``id`` field: when
        ``document`` is a [Document][tinydb.table.Document] (as
        returned by TinyDB reads), its
        [doc_id][tinydb.table.Document.doc_id] joins the validation
        payload as ``id``, so ``model_validator(mode="after")``
        hooks observe the real id, and a stray ``id`` key in a
        stored body is always masked by the document's actual
        ``doc_id``. A plain mapping carries no ``doc_id``, so ``id``
        keeps its default of ``None``. This is the inverse of
        [to_tinydb_document][tinydantic.TinydanticModel.to_tinydb_document],
        which maps ``id`` back to ``doc_id`` and never stores it in the
        document body.

        Validation runs with ``by_name=True``: stored bodies are
        keyed by python field names, never aliases (see
        [to_tinydb_document][tinydantic.TinydanticModel.to_tinydb_document]),
        so aliased models read back without needing
        ``validate_by_name`` in their own config. Alias keys in a
        plain mapping are still accepted — ``by_name`` widens the
        accepted keys, never narrows them.

        Args:
            document: A TinyDB document (or plain mapping) to validate.

        Returns:
            A validated model instance, with ``id`` set from ``doc_id``
            when ``document`` carries one.
        """
        if isinstance(document, Document):
            instance = cls.model_validate(
                {**document, "id": document.doc_id},
                by_name=True,
            )
        else:
            instance = cls.model_validate(document, by_name=True)
        instance.after_load()
        return instance

    @classmethod
    def insert_multiple(cls, documents: Iterable[Self]) -> list[Self]:
        """Insert several models at once.

        Serializes each model with
        [to_tinydb_document][tinydantic.TinydanticModel.to_tinydb_document]
        and hands them to [tinydb.table.Table.insert_multiple][].
        Exactly like [insert][tinydantic.TinydanticModel.insert], each
        model's ``id`` is set in place to the document id TinyDB
        assigned, and the same instances are returned in insertion
        order.

        Args:
            documents: The models to insert.

        Returns:
            The inserted models, with ``id`` set, in insertion order.

        Raises:
            DocumentAlreadyExistsError: If any model's ``id`` is
                already stored, or repeated within the batch;
                nothing is inserted.
        """
        docs = list(documents)
        for doc in docs:
            doc.before_save()
            if cls._uses_revision():
                doc._set_revision_token(uuid4())  # noqa: SLF001
        # Serialize before the try: pydantic.ValidationError is a
        # ValueError and must never be mistaken for a duplicate id.
        serialized = [doc.to_tinydb_document() for doc in docs]
        table = cls.get_table()
        constraints = cls._unique_constraints()
        if constraints:
            preset_ids = {doc.id for doc in docs if doc.id is not None}
            seen: dict[int, set[object]] = {
                index: set() for index in range(len(constraints))
            }
            for body in serialized:
                cls._check_unique(body, exclude_doc_ids=preset_ids)
                for index, constraint in enumerate(constraints):
                    participation = cls._participating(constraint, body)
                    if participation is None:
                        continue
                    values, comparison = participation
                    if comparison in seen[index]:
                        raise UniqueConstraintError(
                            model_name=cls.__name__,
                            table_name=table.name,
                            fields=constraint.fields,
                            values=values,
                            comparison_key=(
                                comparison
                                if constraint.key is not None
                                else None
                            ),
                            doc_id=None,
                        )
                    seen[index].add(comparison)
        try:
            doc_ids = table.insert_multiple(serialized)
        except ValueError as exc:
            # The aborted batch wrote nothing, so the table still
            # reflects the pre-call state; scan the provided ids
            # for ones already stored or repeated in the batch.
            provided = [doc.id for doc in docs if doc.id is not None]
            taken = sorted(
                {
                    doc_id
                    for index, doc_id in enumerate(provided)
                    if table.contains(doc_id=doc_id)
                    or doc_id in provided[:index]
                },
            )
            raise DocumentAlreadyExistsError(
                model_name=cls.__name__,
                table_name=table.name,
                doc_ids=taken or provided,
            ) from exc
        for doc, doc_id in zip(docs, doc_ids, strict=True):
            doc.id = doc_id
        return docs

    @classmethod
    def all(cls) -> list[Self]:
        """Get every document in the table as validated models.

        Iterates the whole table and validates each document via
        [from_tinydb_document][tinydantic.TinydanticModel.from_tinydb_document],
        so every returned instance has its ``id`` populated from the
        stored ``doc_id``.

        Returns:
            All documents in the table as validated models.
        """
        return [cls.from_tinydb_document(doc) for doc in iter(cls.get_table())]

    @overload
    @classmethod
    def find(cls) -> FindQuery[Self]: ...

    @overload
    @classmethod
    def find(cls, cond: QueryLike) -> FindQuery[Self]: ...

    @classmethod
    def find(cls, cond: Any = _FIND_NOT_GIVEN) -> FindQuery[Self]:
        """Build a lazy fluent query over this model's table.

        Returns an immutable [FindQuery][tinydantic.FindQuery]
        describing a query; nothing touches storage until a
        terminal runs. Called with no argument it describes the
        whole table — that spelling is deliberate and explicit, so
        a ``None`` that *arrives* as a value (a condition variable
        that was never set) is refused loudly instead of silently
        widening the query to every document.

        ```python
        adults = User.find(q("age") >= 18)
        page = adults.sort("name").skip(20).limit(10).all()
        ```

        Args:
            cond: The query condition, or omitted for the whole
                table.

        Returns:
            A lazy query description; no I/O happens here.

        Raises:
            SelectorError: If ``cond`` is ``None`` — call
                ``find()`` with no argument to query the whole
                table.
        """
        if cond is None:
            msg = (
                "find() got None instead of a query condition — a "
                "condition variable is unexpectedly None. To query "
                "the whole table, call find() with no argument."
            )
            raise SelectorError(msg)
        if cond is _FIND_NOT_GIVEN:
            return FindQuery(cls)
        return FindQuery(cls, cond=cast("QueryLike", cond))

    @classmethod
    def _match_id_condition_ids(cls, cond: QueryLike) -> list[int]:
        """Resolve an id-bearing condition to matching doc_ids.

        TinyDB evaluates conditions against document bodies, which
        never contain the id, so id-bearing conditions are instead
        evaluated against table iteration — the one TinyDB API that
        yields [Document][tinydb.table.Document] instances carrying
        ``doc_id``. Used by the read paths; the write paths run
        their own single-cycle evaluation (see
        ``_run_write_cycle``).
        """
        return [doc.doc_id for doc in iter(cls.get_table()) if cond(doc)]

    @classmethod
    def _check_doc_ids_exist(cls, doc_ids: list[int]) -> None:
        """Raise for explicit doc_ids that are not in the table.

        TinyDB raises a bare ``KeyError`` for a missing id in
        ``update(doc_ids=...)``/``remove(doc_ids=...)``; checking
        membership up front (one table read via iteration) turns
        that into the same
        [DocumentNotFoundError][tinydantic.DocumentNotFoundError]
        that ``replace()`` and ``delete()`` raise, before anything
        is written.

        Raises:
            DocumentNotFoundError: For the first id not present in
                the table.
        """
        stored = {doc.doc_id for doc in iter(cls.get_table())}
        for doc_id in doc_ids:
            if doc_id not in stored:
                raise DocumentNotFoundError(
                    model_name=cls.__name__,
                    table_name=cls.get_table().name,
                    doc_id=doc_id,
                )

    @classmethod
    def _unique_constraints(cls) -> tuple[UniqueConstraint, ...]:
        """Resolve this model's effective unique constraints.

        Merges per-field [Unique][tinydantic.Unique] markers
        (collected at class definition) with the ``constraints``
        config key (resolved here, so late ``bind()`` works).
        Exact duplicates — same field *set* and same ``key``
        callable (or both key-less) — collapse to one; the same
        field set with different keys yields distinct constraints
        that all enforce.
        """
        markers: tuple[UniqueConstraint, ...] = getattr(
            cls,
            _UNIQUE_MARKERS_ATTR,
            (),
        )
        declared: tuple[UniqueConstraint, ...] = (
            get_config_value(cls, "constraints", default=()) or ()
        )
        merged: list[UniqueConstraint] = []
        seen: set[tuple[frozenset[str], int | None]] = set()
        for constraint in (*markers, *declared):
            identity = (
                frozenset(constraint.fields),
                None if constraint.key is None else id(constraint.key),
            )
            if identity in seen:
                continue
            seen.add(identity)
            merged.append(constraint)
        return tuple(merged)

    @classmethod
    def _participating(
        cls,
        constraint: UniqueConstraint,
        body: Mapping,
    ) -> tuple[tuple[object, ...], object] | None:
        """Return ``(values, comparison key)`` or ``None`` if exempt.

        A constraint participates only when **all** of its fields
        are non-``None`` in ``body`` (SQL composite
        ``UNIQUE``/``NULL`` semantics), so a ``key`` callable is
        never invoked with ``None``. Key-less constraints compare
        the raw serialized value tuple.
        """
        values = tuple(body.get(name) for name in constraint.fields)
        if any(value is None for value in values):
            return None
        comparison = (
            constraint.key(*values) if constraint.key is not None else values
        )
        return values, comparison

    @classmethod
    def _check_unique(
        cls,
        body: Mapping,
        *,
        exclude_doc_ids: AbstractSet[int] = frozenset(),
        touched_fields: AbstractSet[str] | None = None,
    ) -> None:
        """Scan the table for unique-constraint clashes with ``body``.

        Compares serialized values (what storage holds), through
        each constraint's ``key`` callable when one is set. A
        constraint participates only when all of its fields are
        non-``None`` in ``body``, mirroring SQL ``NULL`` under
        composite ``UNIQUE``. Check-then-write with no
        cross-process coordination — sound within tinydantic's
        documented single-process, serialized-writes scope.

        Args:
            body: The serialized document to test.
            exclude_doc_ids: Stored ids that are being (re)written
                and must not count as clashes.
            touched_fields: When given, only constraints naming at
                least one of these fields are checked — the
                partial-write filter used by ``patch()``.

        Raises:
            UniqueConstraintError: If any participating
                constraint's comparison key is already held by a
                document whose id is not in ``exclude_doc_ids``.
        """
        active: list[tuple[UniqueConstraint, tuple[object, ...], object]] = []
        for constraint in cls._unique_constraints():
            if touched_fields is not None and touched_fields.isdisjoint(
                constraint.fields,
            ):
                continue
            participation = cls._participating(constraint, body)
            if participation is None:
                continue
            values, comparison = participation
            active.append((constraint, values, comparison))
        if not active:
            return
        table = cls.get_table()
        for stored in iter(table):
            if stored.doc_id in exclude_doc_ids:
                continue
            for constraint, values, comparison in active:
                stored_participation = cls._participating(
                    constraint,
                    stored,
                )
                if stored_participation is None:
                    continue
                if stored_participation[1] == comparison:
                    raise UniqueConstraintError(
                        model_name=cls.__name__,
                        table_name=table.name,
                        fields=constraint.fields,
                        values=values,
                        comparison_key=(
                            comparison if constraint.key is not None else None
                        ),
                        doc_id=stored.doc_id,
                    )

    @classmethod
    def _check_upsert_unique(
        cls,
        document: Self,
        cond: QueryLike | None,
    ) -> None:
        """Enforce unique fields for an upsert's matched set.

        Resolves the documents ``cond`` matches first: a payload
        touching a unique field with more than one match raises
        (N documents cannot share one unique value); otherwise the
        payload is checked against everything except the matched
        documents. With no cond (update-by-id), the document's own
        id is the matched set.

        Raises:
            UniqueConstraintError: On any would-be duplicate.
        """
        constraints = cls._unique_constraints()
        if not constraints:
            return
        payload = document.to_tinydb_document(force_dict=True)
        if cond is None:
            matched = [cast("int", document.id)]
        elif has_id_condition(cond):
            matched = cls._match_id_condition_ids(cond)
        else:
            matched = [doc.doc_id for doc in cls.get_table().search(cond)]
        touched = [
            (constraint, participation)
            for constraint in constraints
            if (participation := cls._participating(constraint, payload))
            is not None
        ]
        if touched and len(matched) > 1:
            # N matched documents cannot share one unique value
            # (tuple): the payload would fan the same comparison
            # key out to every match.
            constraint, (values, comparison) = touched[0]
            raise UniqueConstraintError(
                model_name=cls.__name__,
                table_name=cls.get_table().name,
                fields=constraint.fields,
                values=values,
                comparison_key=(
                    comparison if constraint.key is not None else None
                ),
                doc_id=matched[0],
            )
        cls._check_unique(payload, exclude_doc_ids=set(matched))

    @classmethod
    def _apply_and_validate(
        cls,
        data: dict[int, Any],
        target_id: int,
        fields: Mapping | Callable[[Mapping], None],
        *,
        validate: bool,
    ) -> None:
        """Merge ``fields`` into one document body, then validate.

        Mutates a copy and assigns it back (copy-on-write), so an
        aborted cycle never leaks partial changes into storages
        that share body dicts by reference (MemoryStorage). When
        ``validate`` is true the merged body is validated with the
        real document id in the payload — the same check the next
        read performs (``by_name=True``: stored keys are python
        field names, not aliases) — so a failing merge aborts the
        whole cycle before its storage write.

        Raises:
            pydantic.ValidationError: If the merged body fails
                model validation.
        """
        body = dict(data[target_id])
        if callable(fields):
            fields(body)
        else:
            body.update(fields)
        if cls._uses_revision():
            # Rotate after the merge so a transform callable can
            # never forge a token; one fresh token per document.
            body["revision_id"] = str(uuid4())
        if validate:
            cls.model_validate({**body, "id": target_id}, by_name=True)
        data[target_id] = body

    @classmethod
    def _run_write_cycle(
        cls,
        updater: Callable[[dict[int, Any]], list[int]],
    ) -> list[int]:
        """Run one atomic read-modify-write cycle.

        ``updater`` receives the mutable ``{doc_id: body}`` table
        dict, mutates matching bodies in place, and returns the
        matched ids. The whole batch is one read-modify-write
        cycle: an exception anywhere (including a merged-result
        validation failure) aborts before the storage write, and
        when nothing matches the cycle is aborted the same way, so
        a no-match call costs one read and zero writes.

        This is the project's only *call* into a TinyDB internal
        API (``Table._update_table``) — approved 2026-07-13 for
        id-condition writes, extended 2026-08-02 to all validated
        ``update()``/``update_multiple()`` writes. TinyDB's public
        API offers no ``doc_ids`` batch path, never exposes
        ``doc_id`` to conditions, and cannot validate-then-write
        atomically (a public two-pass alternative has a
        read-modify-write race between passes). Every sanctioned
        private-API dependency (including the read-only
        ``QueryInstance._hash`` walk in ``has_id_condition``) is
        recorded in the registry on the TinyDB Limitations page,
        with the upstream changes that would remove it.

        Raises:
            TinydanticError: If the installed TinyDB does not
                provide ``Table._update_table``.
        """
        table = cls.get_table()
        if not hasattr(table, "_update_table"):
            msg = (
                "tinydantic needs TinyDB's internal "
                "Table._update_table for validated and "
                "id-condition writes, but "
                f"tinydb {metadata.version('tinydb')} does not "
                "provide it. Pin an older tinydb or upgrade "
                "tinydantic (see the TinyDB Limitations page in "
                "the tinydantic docs)."
            )
            raise TinydanticError(msg)
        matched: list[int] = []

        def run(data: dict[int, Any]) -> None:
            """Collect matches, aborting the cycle when none."""
            matched.extend(updater(data))
            if not matched:
                raise _NothingMatchedError

        try:
            # Private-API use approved per the AGENTS.md policy;
            # documented on docs/contributing/tinydb_limitations.md.
            table._update_table(run)  # noqa: SLF001
        except _NothingMatchedError:
            return []
        return matched

    @classmethod
    def search(cls, cond: QueryLike) -> list[Self]:
        """Get all documents matching ``cond`` as validated models.

        Conditions on ``Model.id`` (bare or composed with field
        conditions) are translated to document-id operations —
        TinyDB's own evaluator only ever sees the document body,
        which does not contain the id.
        """
        if isinstance(cond, DocIdCondition) and cond.opname == "==":
            # Pure id equality: a direct key lookup beats a scan.
            doc = cls.get_table().get(doc_id=cast("int", cond.value))
            if doc is None:
                return []
            return [cls.from_tinydb_document(cast("Document", doc))]
        if has_id_condition(cond):
            return [
                cls.from_tinydb_document(doc)
                for doc in iter(cls.get_table())
                if cond(doc)
            ]
        return [
            cls.from_tinydb_document(doc)
            for doc in cls.get_table().search(cond)
        ]

    @overload
    @classmethod
    def get(cls, cond: QueryLike) -> Self | None: ...

    @overload
    @classmethod
    def get(cls, *, doc_id: int) -> Self | None: ...

    @overload
    @classmethod
    def get(cls, *, doc_ids: list[int]) -> list[Self]: ...

    @classmethod
    def get(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_id: int | None = None,
        doc_ids: list[int] | None = None,
    ) -> Self | list[Self] | None:
        """Get one document (or several by id) as validated models.

        Mirrors [tinydb.table.Table.get][], with one tightening: at
        most one of ``cond``, ``doc_id``, ``doc_ids`` may be provided
        (TinyDB silently applies a precedence order; tinydantic raises
        ``ValueError``). The typed variants
        [get_by_cond][tinydantic.TinydanticModel.get_by_cond],
        [get_by_id][tinydantic.TinydanticModel.get_by_id], and
        [get_by_ids][tinydantic.TinydanticModel.get_by_ids] offer
        precise return types per call shape.

        When ``doc_ids`` is given, TinyDB returns only the documents
        that exist (missing ids are silently skipped), so the result is
        a ``list`` that may be shorter than the ids requested and is
        ordered by storage iteration, not by the ids passed in.

        Raises:
            SelectorError: If no selector, or more than one, is
                provided.
        """
        provided = [s for s in (cond, doc_id, doc_ids) if s is not None]
        if len(provided) > 1:
            msg = "Provide at most one of cond, doc_id, or doc_ids"
            raise SelectorError(msg)
        if not provided:
            msg = (
                "get() needs a selector: pass a query condition, "
                "doc_id=, or doc_ids="
            )
            raise SelectorError(msg)

        if cond is not None and has_id_condition(cond):
            if isinstance(cond, DocIdCondition) and cond.opname == "==":
                # Pure id equality: search() does a direct key
                # lookup and validates at most one document.
                results = cls.search(cond)
                return results[0] if results else None
            # Other id conditions: stop at the first match in
            # table order, validating only the returned document —
            # the same semantics TinyDB's get(cond) and the
            # field-condition path give.
            for doc in iter(cls.get_table()):
                if cond(doc):
                    return cls.from_tinydb_document(doc)
            return None

        result = cls.get_table().get(
            cond=cond,
            doc_id=doc_id,
            doc_ids=doc_ids,
        )

        if result is None:
            return None

        if isinstance(result, Document):
            return cls.from_tinydb_document(result)

        if isinstance(result, list):
            return [cls.from_tinydb_document(doc) for doc in result]

        # Unreachable per TinyDB's Table.get() contract (None, a
        # Document, or a list) — but a contract violation should
        # diagnose itself rather than raise bare.
        msg = (
            "unexpected return type from TinyDB Table.get(): "
            f"{type(result).__name__!r}"
        )
        raise TypeError(msg)

    @classmethod
    def get_by_cond(cls, cond: QueryLike) -> Self | None:
        """Get the first document matching ``cond``, or ``None``."""
        return cls.get(cond)

    @classmethod
    def get_by_id(cls, doc_id: int) -> Self | None:
        """Get the document with the given id, or ``None``."""
        return cls.get(doc_id=doc_id)

    @classmethod
    def get_by_ids(cls, doc_ids: list[int]) -> list[Self]:
        """Get documents for the given ids (see get() for semantics)."""
        return cls.get(doc_ids=doc_ids)

    @overload
    @classmethod
    def get_or_raise(cls, cond: QueryLike) -> Self: ...

    @overload
    @classmethod
    def get_or_raise(cls, *, doc_id: int) -> Self: ...

    @classmethod
    def get_or_raise(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_id: int | None = None,
    ) -> Self:
        """Get one document, raising instead of returning ``None``.

        The strict counterpart to
        [get][tinydantic.TinydanticModel.get] for call sites where a
        missing document is an error rather than an expected outcome
        (request handlers, lookups by known id, ...). Accepts exactly
        one selector: a query condition or a ``doc_id``. There is no
        ``doc_ids`` form — TinyDB silently skips missing ids in bulk
        gets, so "raise if missing" has no single obvious meaning
        there.

        Args:
            cond: The query condition to match.
            doc_id: The document id to fetch.

        Returns:
            The validated model instance.

        Raises:
            DocumentNotFoundError: If no matching document exists.
            SelectorError: If no selector or both selectors are
                provided.
        """
        if cond is not None and doc_id is None:
            result = cls.get(cond)
        elif doc_id is not None and cond is None:
            result = cls.get(doc_id=doc_id)
        else:
            msg = "Provide exactly one of cond or doc_id"
            raise SelectorError(msg)
        if result is None:
            raise DocumentNotFoundError(
                model_name=cls.__name__,
                table_name=cls.get_table().name,
                doc_id=doc_id,
            )
        return result

    @classmethod
    def contains(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_id: int | None = None,
    ) -> bool:
        """Check whether a matching document exists.

        Conditions on ``Model.id`` are translated to document-id
        operations; like plain-condition calls, no document is
        validated into a model.

        Raises:
            SelectorError: If no selector, or both selectors, are
                provided.
        """
        if cond is not None and doc_id is not None:
            msg = "Provide at most one of cond or doc_id"
            raise SelectorError(msg)
        if cond is None and doc_id is None:
            msg = (
                "contains() needs a selector: pass a query "
                "condition or doc_id="
            )
            raise SelectorError(msg)
        if cond is not None and has_id_condition(cond):
            if isinstance(cond, DocIdCondition) and cond.opname == "==":
                return cls.get_table().contains(
                    doc_id=cast("int", cond.value),
                )
            return any(cond(doc) for doc in iter(cls.get_table()))
        return cls.get_table().contains(cond=cond, doc_id=doc_id)

    @classmethod
    def _field_adapter(cls, field_name: str) -> TypeAdapter[Any]:
        """Get (or build and cache) a TypeAdapter for a model field.

        The adapter is built from the field's full annotation
        (including ``Field(...)`` metadata, via
        [rebuild_annotation][pydantic.fields.FieldInfo.rebuild_annotation])
        and cached on this class, so repeated ``update()`` calls pay
        the construction cost once per field.
        """
        adapters: dict[str, TypeAdapter[Any]] | None = cls.__dict__.get(
            _FIELD_ADAPTERS_ATTR,
        )
        if adapters is None:
            adapters = {}
            setattr(cls, _FIELD_ADAPTERS_ATTR, adapters)
        adapter = adapters.get(field_name)
        if adapter is None:
            field_info = cls.model_fields[field_name]
            adapter = TypeAdapter(field_info.rebuild_annotation())
            adapters[field_name] = adapter
        return adapter

    @classmethod
    def _serialize_update_fields(
        cls,
        fields: Mapping,
        *,
        extra_keys: Literal["reject", "allow"] = "reject",
    ) -> dict[str, Any]:
        """Validate and JSON-serialize known field values in a mapping.

        Each key that names a model field has its value validated
        against that field's type and serialized in JSON mode — the
        same treatment ``insert()``/``save()`` give whole models — so
        rich values (datetime, UUID, nested models, ...) land in
        storage as JSON-safe primitives. Keys that are not model
        fields are rejected by default — they would bypass
        validation entirely — and pass through unchanged only with
        ``extra_keys="allow"``.

        Raises:
            DocumentIDUpdateError: If the mapping contains an ``id``
                key — ``id`` maps to TinyDB's ``doc_id``, which an
                update cannot change.
            RevisionUpdateError: If the mapping contains a
                ``revision_id`` key on a ``use_revision=True``
                model — the token is rotated automatically and
                direct writes would corrupt the protocol.
            UnknownUpdateFieldError: If the mapping contains keys
                that are not model fields and ``extra_keys`` is
                ``"reject"`` (the default).
            pydantic.ValidationError: If a value fails validation
                against its field's type.
        """
        serialized: dict[str, Any] = {}
        unknown: list[str] = []
        for key, value in fields.items():
            if key == "id":
                raise DocumentIDUpdateError(model_name=cls.__name__)
            if key == "revision_id" and cls._uses_revision():
                raise RevisionUpdateError(model_name=cls.__name__)
            if key in cls.model_fields:
                adapter = cls._field_adapter(key)
                serialized[key] = adapter.dump_python(
                    adapter.validate_python(value),
                    mode="json",
                )
            else:
                unknown.append(key)
                serialized[key] = value
        if unknown and extra_keys == "reject":
            raise UnknownUpdateFieldError(
                model_name=cls.__name__,
                keys=unknown,
            )
        return serialized

    @classmethod
    def update(
        cls,
        fields: Mapping | Callable[[Mapping], None],
        cond: QueryLike | None = None,
        *,
        doc_ids: Iterable[int] | None = None,
        extra_keys: Literal["reject", "allow"] = "reject",
    ) -> list[int]:
        """Update matching documents with new fields or a transform.

        A ``fields`` mapping gets the same treatment ``insert()`` and
        ``save()`` give whole models: each value that belongs to a
        model field is validated against that field's type and
        serialized to a JSON-safe primitive before it reaches storage
        (keys that are not model fields pass through unchanged). A
        transform callable is handed to TinyDB as-is — what it writes
        is up to you.

        Unless the model opts out via ``validate_writes=False``,
        each matched document's merged result — stored body plus
        the new fields, or the transform's output — is validated
        before anything is written, so an update can never persist
        a body its next read would reject. Cross-field
        ``model_validator(mode="after")`` invariants run against
        the merge with the real document id visible; stored keys
        the model does not know are ignored by validation and
        preserved in the written body. The whole batch is one
        atomic read-modify-write cycle (see ``_run_write_cycle``):
        a validation failure on any matched document means nothing
        is written.

        Exactly one selector is required: a query condition or
        explicit ``doc_ids``. TinyDB's own ``update()`` treats a
        bare call as "update every document" and silently prefers
        ``doc_ids`` when both are given; tinydantic raises
        [SelectorError][tinydantic.SelectorError] in both cases —
        updating the whole table must be spelled
        [update_all][tinydantic.TinydanticModel.update_all],
        mirroring the
        [remove][tinydantic.TinydanticModel.remove]/
        [truncate][tinydantic.TinydanticModel.truncate] split.

        Conditions on ``Model.id`` are supported (bare or composed
        with field conditions), evaluated against
        [Document][tinydb.table.Document] wrappers so they can
        read ``doc_id``.

        As the deliberate table-level loose path, ``update()``
        does NOT enforce [Unique][tinydantic.Unique] field
        markers; every other write verb does.

        Args:
            fields: A mapping of new field values, or a transform
                callable applied to each matched document body.
            cond: The query condition selecting documents.
            doc_ids: Explicit document ids to update instead of a
                condition.
            extra_keys: ``"reject"`` (default) raises for mapping
                keys that are not model fields — they would be
                written without any validation. ``"allow"`` writes
                them through unchanged (for databases shared with
                other tools or schema-evolution keys this model
                does not know yet).

        Returns:
            The ids of all updated documents.

        Raises:
            SelectorError: If neither ``cond`` nor ``doc_ids`` is
                provided (use
                [update_all][tinydantic.TinydanticModel.update_all]
                to update every document), or both are.
            DocumentIDUpdateError: If a mapping contains an ``id``
                key.
            DocumentNotFoundError: If an explicit ``doc_ids`` id
                does not exist; nothing is written.
            UnknownUpdateFieldError: If a mapping contains keys
                that are not model fields and ``extra_keys`` is
                ``"reject"`` (the default).
            pydantic.ValidationError: If a mapping value fails
                validation against its field's type, or a matched
                document's merged result fails model validation.
        """
        if cond is not None and doc_ids is not None:
            msg = "Provide at most one of cond or doc_ids"
            raise SelectorError(msg)
        if cond is None and doc_ids is None:
            msg = (
                "update() needs a selector: pass a query condition "
                "or doc_ids=. To update every document, use "
                "update_all()."
            )
            raise SelectorError(msg)
        if not callable(fields):
            fields = cls._serialize_update_fields(
                fields,
                extra_keys=extra_keys,
            )
        if doc_ids is not None:
            doc_ids = list(doc_ids)
            cls._check_doc_ids_exist(doc_ids)
        validate = get_config_value(cls, "validate_writes", default=True)
        id_cond = (
            cond is not None and doc_ids is None and has_id_condition(cond)
        )
        if not validate and not id_cond:
            return cls.get_table().update(
                # See replace() for why this cast is needed.
                # TODO @cdwilson: remove this cast once the
                # annotation is fixed in TinyDB.
                cast("Callable[[Mapping], None]", cls._rotated(fields)),
                cond=cond,
                doc_ids=doc_ids,
            )
        table = cls.get_table()
        _cond, _fields, _doc_ids = cond, fields, doc_ids

        def apply_update(data: dict[int, Any]) -> list[int]:
            """Apply the fields to each selected document."""
            if _doc_ids is not None:
                # TinyDB's public update(doc_ids=...) raises
                # KeyError for a missing id; data[target_id] in
                # _apply_and_validate preserves that contract,
                # aborting before the storage write.
                targets = list(_doc_ids)
            else:
                # The selector checks above guarantee cond is set
                # when doc_ids is not.
                matches = cast("QueryLike", _cond)
                targets = [
                    target_id
                    for target_id in list(data)
                    if matches(
                        table.document_class(
                            data[target_id],
                            target_id,
                        ),
                    )
                ]
            for target_id in targets:
                cls._apply_and_validate(
                    data,
                    target_id,
                    _fields,
                    validate=validate,
                )
            return targets

        return cls._run_write_cycle(apply_update)

    @classmethod
    def update_all(
        cls,
        fields: Mapping | Callable[[Mapping], None],
        *,
        extra_keys: Literal["reject", "allow"] = "reject",
    ) -> list[int]:
        """Update every document in the table.

        The explicit whole-table counterpart to
        [update][tinydantic.TinydanticModel.update], which requires
        a selector — the same split
        [remove][tinydantic.TinydanticModel.remove] and
        [truncate][tinydantic.TinydanticModel.truncate] make for
        deletion. A distinct verb keeps mass writes greppable and
        impossible to reach by accidentally dropping a condition.

        Fields mappings and transform callables get exactly the
        treatment [update][tinydantic.TinydanticModel.update] gives
        them, including merged-result validation (unless the model
        opts out via ``validate_writes=False``) as one atomic
        cycle: a validation failure on any document means nothing
        is written. Like ``update()``, this loose path does NOT
        enforce [Unique][tinydantic.Unique] field markers.

        Args:
            fields: A mapping of new field values, or a transform
                callable applied to each document body.
            extra_keys: ``"reject"`` (default) raises for mapping
                keys that are not model fields; ``"allow"`` writes
                them through unchanged — see
                [update][tinydantic.TinydanticModel.update].

        Returns:
            The ids of all documents in the table.

        Raises:
            DocumentIDUpdateError: If a mapping contains an ``id``
                key.
            UnknownUpdateFieldError: If a mapping contains keys
                that are not model fields and ``extra_keys`` is
                ``"reject"`` (the default).
            pydantic.ValidationError: If a mapping value fails
                validation against its field's type, or any
                document's merged result fails model validation.
        """
        if not callable(fields):
            fields = cls._serialize_update_fields(
                fields,
                extra_keys=extra_keys,
            )
        validate = get_config_value(cls, "validate_writes", default=True)
        if not validate:
            return cls.get_table().update(
                # See replace() for why this cast is needed.
                # TODO @cdwilson: remove this cast once the
                # annotation is fixed in TinyDB.
                cast("Callable[[Mapping], None]", cls._rotated(fields)),
            )
        _fields = fields

        def apply_update_all(data: dict[int, Any]) -> list[int]:
            """Apply the fields to every document."""
            for target_id in list(data):
                cls._apply_and_validate(
                    data,
                    target_id,
                    _fields,
                    validate=validate,
                )
            return list(data)

        return cls._run_write_cycle(apply_update_all)

    @classmethod
    def update_multiple(
        cls,
        updates: Iterable[
            tuple[
                Mapping | Callable[[Mapping], None],
                QueryLike,
            ]
        ],
        *,
        extra_keys: Literal["reject", "allow"] = "reject",
    ) -> list[int]:
        """Apply several (fields_or_transform, cond) updates at once.

        Each update's fields mapping is validated and serialized
        exactly as in [update][tinydantic.TinydanticModel.update];
        transform callables pass through as-is.

        Unless the model opts out via ``validate_writes=False``,
        each matched document's merged result is validated exactly
        as in [update][tinydantic.TinydanticModel.update], and the
        whole batch is one atomic read-modify-write cycle (see
        ``_run_write_cycle``): a validation failure on any matched
        document means nothing is written. Like ``update()``, this
        loose path does NOT enforce
        [Unique][tinydantic.Unique] field markers.

        Pairs may use conditions on ``Model.id`` (bare or composed
        with field conditions) and mix freely with plain
        field-condition pairs, every condition evaluated against
        [Document][tinydb.table.Document] wrappers so id
        conditions can read ``doc_id`` — TinyDB's own batch
        semantics are preserved: documents are visited in table
        order, pairs apply in order per document (later pairs see
        earlier pairs' changes), and a document appears in the
        result once per pair that matched it.

        Args:
            updates: ``(fields_or_transform, cond)`` pairs.
            extra_keys: ``"reject"`` (default) raises for mapping
                keys that are not model fields; ``"allow"`` writes
                them through unchanged — see
                [update][tinydantic.TinydanticModel.update].

        Returns:
            The ids of all updated documents.

        Raises:
            DocumentIDUpdateError: If a mapping contains an ``id``
                key.
            UnknownUpdateFieldError: If a mapping contains keys
                that are not model fields and ``extra_keys`` is
                ``"reject"`` (the default).
            pydantic.ValidationError: If a mapping value fails
                validation against its field's type, or a matched
                document's merged result fails model validation.
        """
        prepared = [
            (
                fields
                if callable(fields)
                else cls._serialize_update_fields(
                    fields,
                    extra_keys=extra_keys,
                ),
                cond,
            )
            for fields, cond in updates
        ]
        validate = get_config_value(cls, "validate_writes", default=True)
        if validate or any(has_id_condition(cond) for _, cond in prepared):
            table = cls.get_table()

            def apply_pairs(data: dict[int, Any]) -> list[int]:
                """Apply each matching (fields, cond) pair in order."""
                matched: list[int] = []
                for target_id in list(data):
                    for fields, cond in prepared:
                        doc = table.document_class(
                            data[target_id],
                            target_id,
                        )
                        if cond(doc):
                            matched.append(target_id)
                            cls._apply_and_validate(
                                data,
                                target_id,
                                fields,
                                validate=validate,
                            )
                return matched

            return cls._run_write_cycle(apply_pairs)
        return cls.get_table().update_multiple(
            # See replace() for why this cast is needed.
            cast(
                "Iterable[tuple[Callable[[Mapping], None], QueryLike]]",
                [(cls._rotated(fields), cond) for fields, cond in prepared],
            ),
        )

    @classmethod
    def upsert(
        cls,
        document: Self,
        cond: QueryLike | None = None,
    ) -> list[int]:
        """Update documents matching ``cond``, or insert ``document``.

        Conditions on ``Model.id`` are translated to document-id
        operations. As with TinyDB's own upsert, when nothing
        matches, the insert does not adopt the condition's id value —
        the document is inserted with a fresh id.

        When exactly one document is affected — an insert, or an
        update that matched a single document — ``document.id`` is
        set to that document's id in place, mirroring
        [insert][tinydantic.TinydanticModel.insert] and
        [save][tinydantic.TinydanticModel.save]. When several
        documents match, linking ``document`` to any one of them
        would be arbitrary, so its ``id`` is left untouched.

        Returns:
            The ids of the updated (or inserted) documents.

        Raises:
            SelectorError: If ``cond`` is omitted and
                ``document.id`` is ``None`` — without either there
                is nothing to select the document to update by.
        """
        if cond is None and document.id is None:
            msg = (
                "upsert() without a cond updates by id, but this "
                "document's id is None — insert() or save() it "
                "first, or pass a query condition"
            )
            raise SelectorError(msg)
        document.before_save()
        cls._check_upsert_unique(document, cond)
        # upsert() cannot check revisions (its contract is
        # "regardless of current state") but must still rotate, so
        # held tokens elsewhere correctly go stale. One token for
        # the batch: equality is the only comparison tokens face.
        token = uuid4() if cls._uses_revision() else None
        if cond is not None and has_id_condition(cond):
            document_dict = document.to_tinydb_document(force_dict=True)
            if token is not None:
                document_dict["revision_id"] = str(token)
            ids = cls._upsert_id_condition(document_dict, cond)
        else:
            serialized = document.to_tinydb_document(
                force_dict=cond is not None,
            )
            if token is not None:
                serialized["revision_id"] = str(token)
            ids = cls.get_table().upsert(serialized, cond)
        if len(ids) == 1:
            document.id = ids[0]
            if token is not None:
                document._set_revision_token(token)
        return ids

    @classmethod
    def _upsert_id_condition(
        cls,
        document_dict: dict[str, Any],
        cond: QueryLike,
    ) -> list[int]:
        """Run upsert()'s id-condition branch atomically.

        Merges ``document_dict`` into every document matching
        ``cond`` in one read-modify-write cycle, inserting it as a
        new document when nothing matched (TinyDB upsert
        semantics — the insert does not adopt the condition's id).
        """
        table = cls.get_table()

        def apply_upsert(data: dict[int, Any]) -> list[int]:
            """Merge the document body into matching documents."""
            matched: list[int] = []
            for target_id in list(data):
                doc = table.document_class(
                    data[target_id],
                    target_id,
                )
                if cond(doc):
                    matched.append(target_id)
                    # Copy-on-write: see update().
                    body = dict(data[target_id])
                    body.update(document_dict)
                    data[target_id] = body
            return matched

        ids = cls._run_write_cycle(apply_upsert)
        if not ids:
            ids = [table.insert(document_dict)]
        return ids

    @classmethod
    def remove(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """Remove matching documents.

        Conditions on ``Model.id`` are executed in one atomic
        read-modify-write cycle (see
        ``_run_write_cycle``), with the condition
        evaluated against [Document][tinydb.table.Document]
        wrappers so it can read ``doc_id``. When ``doc_ids`` is
        passed explicitly, TinyDB's precedence applies and
        ``cond`` is not evaluated.

        Returns:
            The ids of all removed documents.

        Raises:
            SelectorError: If neither ``cond`` nor ``doc_ids`` is
                provided — removing every document must be spelled
                [truncate][tinydantic.TinydanticModel.truncate].
            DocumentNotFoundError: If an explicit ``doc_ids`` id
                does not exist; nothing is removed.
        """
        if cond is None and doc_ids is None:
            msg = (
                "remove() needs a selector: pass a query condition "
                "or doc_ids=. To remove every document, use "
                "truncate()."
            )
            raise SelectorError(msg)
        if doc_ids is not None:
            doc_ids = list(doc_ids)
            cls._check_doc_ids_exist(doc_ids)
        if cond is not None and doc_ids is None and has_id_condition(cond):
            table = cls.get_table()
            _cond = cond

            def apply_remove(data: dict[int, Any]) -> list[int]:
                """Pop documents matching the id condition."""
                matched: list[int] = []
                for target_id in list(data):
                    doc = table.document_class(
                        data[target_id],
                        target_id,
                    )
                    if _cond(doc):
                        matched.append(target_id)
                        data.pop(target_id)
                return matched

            return cls._run_write_cycle(apply_remove)
        return cls.get_table().remove(cond=cond, doc_ids=doc_ids)

    @classmethod
    def truncate(cls) -> None:
        """Remove every document from the table.

        Delegates to [tinydb.table.Table.truncate][], leaving the table
        empty and resetting its document id counter.
        """
        cls.get_table().truncate()

    @classmethod
    def count(cls, cond: QueryLike | None = None) -> int:
        """Count the documents matching ``cond``, or all documents.

        With a condition, delegates to [tinydb.table.Table.count][].
        Without one, returns the total number of documents in the
        table (``len(table)``) — TinyDB itself spells this
        ``len(db.table(...))``; tinydantic folds it into ``count()``
        so "how many documents are there?" needs no query object.

        Args:
            cond: The query condition to match. When omitted, every
                document in the table is counted.

        Returns:
            The number of matching (or total) documents.
        """
        if cond is None:
            return len(cls.get_table())
        if has_id_condition(cond):
            # Conditions on Model.id are translated to document-id
            # operations; nothing is validated into a model.
            if isinstance(cond, DocIdCondition) and cond.opname == "==":
                return int(
                    cls.get_table().contains(
                        doc_id=cast("int", cond.value),
                    ),
                )
            return len(cls._match_id_condition_ids(cond))
        return cls.get_table().count(cond)

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the table's query cache.

        Delegates to [tinydb.table.Table.clear_cache][]. TinyDB caches
        query results per table; call this to discard those cached
        results (for example after mutating storage out of band).
        """
        cls.get_table().clear_cache()

    # --- instance methods ---

    def to_tinydb_document(
        self,
        *,
        force_dict: bool = False,
    ) -> dict[str, Any] | Document:
        """Convert this model to a TinyDB-storable document.

        Uses JSON-mode serialization so rich pydantic types (datetime,
        UUID, enums, nested models, ...) become JSON-safe primitives
        that round-trip through any TinyDB storage. The ``id`` field is
        never embedded in the document — it maps to TinyDB's
        ``doc_id``. Keys are python field names, never aliases —
        the invariant that keeps ``Model.field`` queries aligned
        with stored keys — so the write check below (and every
        other internal validation) runs with ``by_name=True``.

        Unless the model opts out via ``validate_writes=False``, the
        serialized payload is validated before it is returned — the
        same check the document faces on its next read — so a write
        can never persist a body that a later read would reject.
        This catches what assignment validation cannot see:
        in-place container mutation, mutation of nested models, and
        ``object.__setattr__``. Validators observe the real ``id``
        (or ``None`` before the first insert, as at construction).

        Args:
            force_dict: Return a plain dict even when ``id`` is set
                (otherwise a [Document][tinydb.table.Document] carrying
                ``doc_id`` is returned).

        Raises:
            pydantic.ValidationError: If the serialized payload
                fails validation — the document is refused before
                it can reach storage.
        """
        doc = self.model_dump(mode="json", exclude={"id"})

        if get_config_value(type(self), "validate_writes", default=True):
            type(self).model_validate({**doc, "id": self.id}, by_name=True)

        if (force_dict is False) and (self.id is not None):
            doc = Document(doc, self.id)

        return doc

    @classmethod
    def _uses_revision(cls) -> bool:
        """Resolve whether this model opted into revision tracking."""
        return bool(get_config_value(cls, "use_revision", default=False))

    @classmethod
    def _rotated(
        cls,
        fields: Mapping | Callable[[Mapping], None],
    ) -> Mapping | Callable[[Mapping], None]:
        """Wrap ``fields`` to also rotate ``revision_id``.

        Used by the unvalidated fast paths, which hand ``fields``
        straight to TinyDB — the validated paths rotate inside
        ``_apply_and_validate`` instead. Returns ``fields``
        unchanged for models without ``use_revision``.
        """
        if not cls._uses_revision():
            return fields

        def rotate(body: Mapping) -> None:
            """Apply ``fields``, then mint a fresh revision token."""
            mutable = cast("dict[str, Any]", body)
            if callable(fields):
                fields(mutable)
            else:
                mutable.update(fields)
            mutable["revision_id"] = str(uuid4())

        return rotate

    def _set_revision_token(self, token: UUID) -> None:
        """Sync a freshly written token onto this instance.

        Direct ``__dict__`` assignment, NOT setattr: with
        ``validate_assignment`` on, assignment re-runs model
        validators, and the written state was already validated —
        the same reasoning as ``patch()``'s instance sync.
        """
        # The cast is for pyright, which resolves BaseModel's
        # `__slots__` entry for `__dict__` to a read-only
        # MappingProxyType; at runtime it is an ordinary dict.
        cast("dict[str, Any]", self.__dict__)["revision_id"] = token
        self.__pydantic_fields_set__.add("revision_id")

    def _check_revision(
        self,
        *,
        operation: str,
        on_missing: Literal["insert", "not_found"],
    ) -> None:
        """Compare this instance's held token against storage.

        ``on_missing`` selects the missing-document contract:
        ``save()`` may insert a never-read instance (``"insert"``),
        while ``replace()``/``delete()`` require the document to
        exist (``"not_found"``). A *held* token with a missing
        document is always a stale write — the document was
        deleted since this instance read it.

        Tokens compare as strings: the stored value is the
        JSON-serialized form, and a legacy document written before
        ``use_revision`` was enabled has no token at all, which
        matches a held ``None`` (first revisioned write adopts it).

        Raises:
            StaleDocumentError: If the stored token differs from
                the held one (``deleted=False``), or the document
                vanished after this instance read it
                (``deleted=True``).
            DocumentNotFoundError: If the document is missing, was
                never read by this instance, and ``on_missing`` is
                ``"not_found"``.
        """
        cls = type(self)
        doc_id = cast("int", self.id)
        stored = self.get_table().get(doc_id=doc_id)
        held = None if self.revision_id is None else str(self.revision_id)
        if stored is None:
            if held is None:
                if on_missing == "insert":
                    return
                raise DocumentNotFoundError(
                    model_name=cls.__name__,
                    table_name=self.get_table().name,
                    doc_id=doc_id,
                )
            raise StaleDocumentError(
                model_name=cls.__name__,
                table_name=self.get_table().name,
                doc_id=doc_id,
                deleted=True,
            )
        stored_doc = cast("Document", stored)
        if stored_doc.get("revision_id") != held:
            raise StaleDocumentError(
                model_name=cls.__name__,
                table_name=self.get_table().name,
                doc_id=doc_id,
                deleted=False,
            )
        # operation is part of the guard's contract for callers
        # and error messages may grow to use it; keep the
        # parameter honest even while unused in messages.
        del operation

    def insert(self) -> Self:
        """Insert this model as a new document.

        Serializes the model with
        [to_tinydb_document][tinydantic.TinydanticModel.to_tinydb_document]
        and inserts it via [tinydb.table.Table.insert][]. When ``id`` is
        unset it is assigned the id TinyDB generates; when ``id`` is
        already set that value is used as the document id.

        Returns:
            This instance, with ``id`` set to the new document id.

        Raises:
            DocumentAlreadyExistsError: If ``id`` is set to an id
                that already exists in the table.
        """
        self.before_save()
        cls = type(self)
        if cls._uses_revision():
            self._set_revision_token(uuid4())
        # Serialize before the try: pydantic.ValidationError is a
        # ValueError and must never be mistaken for a duplicate id.
        doc = self.to_tinydb_document()
        cls._check_unique(
            doc,
            exclude_doc_ids=(frozenset() if self.id is None else {self.id}),
        )
        try:
            self.id = self.get_table().insert(doc)
        except ValueError as exc:
            raise DocumentAlreadyExistsError(
                model_name=type(self).__name__,
                table_name=self.get_table().name,
                doc_ids=[cast("int", self.id)],
            ) from exc

        return self

    def replace(self, *, ignore_revision: bool = False) -> None:
        """Overwrite this model's stored document in place.

        Requires ``id`` to be set. Unlike
        [update][tinydantic.TinydanticModel.update], which merges
        fields, ``replace`` swaps the entire stored document for this
        model's current serialized state, so fields absent from the
        model are removed. Unlike
        [save][tinydantic.TinydanticModel.save], which re-inserts a
        missing document, ``replace`` requires the document to already
        exist.

        On models with ``use_revision=True``, the stored document's
        ``revision_id`` must still match the token this instance
        read (see [save][tinydantic.TinydanticModel.save] for the
        full protocol); a successful replace rotates the token in
        storage and on this instance.

        Args:
            ignore_revision: Skip the revision check — deliberate
                last-write-wins (the token still rotates). Inert
                on models without ``use_revision``.

        Raises:
            DocumentIDRequiredError: If ``id`` is not set (the model
                was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
            StaleDocumentError: If ``use_revision=True`` and the
                document was modified since this instance read it
                (``deleted=True`` when it was deleted and this
                instance had read it); nothing is written.
        """
        if self.id is None:
            raise DocumentIDRequiredError(
                model_name=type(self).__name__,
                operation="replace",
            )

        self.before_save()
        replacement = self.to_tinydb_document(force_dict=True)
        cls = type(self)
        cls._check_unique(
            replacement,
            exclude_doc_ids={self.id},
        )
        token: UUID | None = None
        if cls._uses_revision():
            if not ignore_revision:
                self._check_revision(
                    operation="replace",
                    on_missing="not_found",
                )
            token = uuid4()
            replacement["revision_id"] = str(token)
        try:
            updated_doc_ids = self.get_table().update(
                # In TinyDB, the Table.update/update_multiple methods
                # currently annotate the fields parameter with the type
                # Callable[[Mapping], None].
                #
                # However, the doc parameter that is passed to this
                # transform function is actually a python dict (which
                # is a type of MutableMapping).
                #
                # This cast is simply a band-aid to keep the type
                # checker happy.
                #
                # TODO @cdwilson: remove this cast once the annotation
                # is fixed in TinyDB.
                cast(
                    "Callable[[Mapping], None]",
                    replace(replacement),
                ),
                doc_ids=[self.id],
            )
        except KeyError:
            raise DocumentNotFoundError(
                model_name=type(self).__name__,
                table_name=self.get_table().name,
                doc_id=self.id,
            ) from None

        if not updated_doc_ids:
            raise DocumentNotFoundError(
                model_name=type(self).__name__,
                table_name=self.get_table().name,
                doc_id=self.id,
            )
        if token is not None:
            self._set_revision_token(token)

    def delete(self, *, ignore_revision: bool = False) -> None:
        """Remove this model's document from its table.

        On models with ``use_revision=True``, the stored document's
        ``revision_id`` must still match the token this instance
        read — a stale delete is the most destructive stale write
        there is (the HTTP analog is ``DELETE`` + ``If-Match``
        answering ``412``). Nothing is removed on a mismatch.

        Args:
            ignore_revision: Skip the revision check — deliberate
                delete-regardless. Inert on models without
                ``use_revision``.

        Raises:
            DocumentIDRequiredError: If ``id`` is not set (the model
                was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
            StaleDocumentError: If ``use_revision=True`` and the
                document was modified since this instance read it
                (``deleted=True`` when it was already deleted by
                another writer); nothing is removed.
        """
        cls = type(self)
        if self.id is None:
            raise DocumentIDRequiredError(
                model_name=cls.__name__,
                operation="delete",
            )
        if cls._uses_revision() and not ignore_revision:
            self._check_revision(
                operation="delete",
                on_missing="not_found",
            )
        try:
            removed = self.get_table().remove(doc_ids=[self.id])
        except KeyError:
            raise DocumentNotFoundError(
                model_name=type(self).__name__,
                table_name=self.get_table().name,
                doc_id=self.id,
            ) from None
        if not removed:
            raise DocumentNotFoundError(
                model_name=type(self).__name__,
                table_name=self.get_table().name,
                doc_id=self.id,
            )

    def patch(self, /, **fields: Any) -> Self:
        """Update only the given fields, in storage and on self.

        The instance-level partial update: validates the new
        values, merges exactly these fields into the stored
        document by id (other stored fields are untouched — unlike
        [save][tinydantic.TinydanticModel.save], which writes the
        whole document from this instance), and then updates this
        instance to match. The write is atomic and validated like
        [update][tinydantic.TinydanticModel.update]; if anything
        raises, storage and this instance are both left untouched.

        Unknown keys are always rejected — there is deliberately
        no ``extra_keys`` escape here; use the table-level
        [update][tinydantic.TinydanticModel.update] to write
        non-model keys. With no fields at all, nothing is written
        but the document's existence is still checked, so the
        error contract does not depend on the payload.

        Like ``update()``, values land in storage as serialized
        inputs: a ``model_validator`` that rewrites values applies
        on the next read.

        On models with ``use_revision=True``, ``patch()`` rotates
        the token but does NOT check it — it is the deliberate
        field-merge tool, and a check would make it conflict on
        concurrent changes to *unrelated* fields. Patch values you
        *decided*; values *derived* from a read (counters computed
        from stock, and the like) belong in the load-mutate-
        [save][tinydantic.TinydanticModel.save] loop, where the
        check lives. The fresh token is absorbed by this instance.

        Returns:
            This instance, with the patched fields set to their
            validated values.

        Raises:
            DocumentIDRequiredError: If ``id`` is ``None`` (the
                model was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
            DocumentIDUpdateError: If ``fields`` contains ``id``.
            RevisionUpdateError: If ``fields`` contains
                ``revision_id`` on a ``use_revision=True`` model —
                the token rotates automatically.
            UnknownUpdateFieldError: If a key is not a model
                field.
            pydantic.ValidationError: If a value fails validation
                or the merged document violates a model invariant;
                nothing is written.
        """
        cls = type(self)
        if self.id is None:
            raise DocumentIDRequiredError(
                model_name=cls.__name__,
                operation="patch",
            )
        if not fields:
            cls._check_doc_ids_exist([self.id])
            return self
        unknown: list[str] = []
        validated: dict[str, Any] = {}
        for key, value in fields.items():
            if key == "id":
                raise DocumentIDUpdateError(model_name=cls.__name__)
            if key == "revision_id" and cls._uses_revision():
                raise RevisionUpdateError(model_name=cls.__name__)
            if key not in cls.model_fields:
                unknown.append(key)
                continue
            validated[key] = cls._field_adapter(key).validate_python(
                value,
            )
        if unknown:
            raise UnknownUpdateFieldError(
                model_name=cls.__name__,
                keys=unknown,
            )
        serialized_patch = {
            key: cls._field_adapter(key).dump_python(
                value,
                mode="json",
            )
            for key, value in validated.items()
        }
        # Composite constraints need the post-write pair, not just
        # the patched member: merge over the stored body. A vanished
        # document skips the check — cls.update() below raises
        # DocumentNotFoundError for it.
        stored_body = self.get_table().get(doc_id=self.id)
        body: dict[str, Any] = (
            {**stored_body, **serialized_patch}
            # TinyDB Documents are dict subclasses; anything else
            # (None for a vanished document) falls back to the
            # patch alone.
            if isinstance(stored_body, dict)
            else serialized_patch
        )
        cls._check_unique(
            body,
            exclude_doc_ids={self.id},
            touched_fields=set(serialized_patch),
        )
        cls.update(fields, doc_ids=[self.id])
        # Sync only after the write succeeded. Direct __dict__
        # assignment, NOT setattr: with validate_assignment on,
        # per-field assignment can trip a cross-field invariant on
        # a transient state (start moved before end) even though
        # the final state — already checked by the merged-result
        # validation above — is valid.
        # The cast is for pyright; see _set_revision().
        cast("dict[str, Any]", self.__dict__).update(validated)
        self.__pydantic_fields_set__.update(validated)
        if cls._uses_revision():
            # patch() rotates without checking (it is the
            # field-merge tool — see the Concurrency docs), so the
            # fresh token comes from the write above; absorb it so
            # a later save() on this instance does not spuriously
            # conflict.
            stored = cast(
                "Document",
                self.get_table().get(doc_id=self.id),
            )
            self._set_revision_token(UUID(stored["revision_id"]))
        return self

    def save(self, *, ignore_revision: bool = False) -> Self:
        """Insert this model if it is new, otherwise update it by id.

        If ``id`` is set but the document no longer exists in the
        table, it is re-inserted under the same id (TinyDB upsert
        semantics) — unlike ``replace()``/``delete()``, which raise
        [DocumentNotFoundError][tinydantic.DocumentNotFoundError].

        On models with ``use_revision=True``, the stored document's
        ``revision_id`` must still match the token this instance
        read, or nothing is written and
        [StaleDocumentError][tinydantic.StaleDocumentError] is
        raised — including when the document was deleted in the
        meantime (``deleted=True``; a revisioned ``save()`` never
        silently resurrects a concurrently deleted document). A
        successful save rotates the token in storage and on this
        instance. An instance that never read its document (a held
        token of ``None``) conflicts with any stored token, but
        matches a legacy document written before ``use_revision``
        was enabled — the first revisioned write adopts it.

        Args:
            ignore_revision: Skip the revision check — deliberate
                last-write-wins (the token still rotates). Inert
                on models without ``use_revision``.

        Returns:
            This instance (with ``id`` set if it was newly inserted).

        Raises:
            StaleDocumentError: If ``use_revision=True`` and the
                document was modified or deleted since this
                instance read it; nothing is written.
        """
        if self.id is None:
            return self.insert()
        self.before_save()
        doc = self.to_tinydb_document()
        cls = type(self)
        cls._check_unique(doc, exclude_doc_ids={self.id})
        if cls._uses_revision():
            if not ignore_revision:
                self._check_revision(
                    operation="save",
                    on_missing="insert",
                )
            token = uuid4()
            doc["revision_id"] = str(token)
            self.id = self.get_table().upsert(doc)[0]
            self._set_revision_token(token)
            return self
        self.id = self.get_table().upsert(doc)[0]
        return self
