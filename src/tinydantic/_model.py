# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""The TinydanticModel base class and query helpers."""

from __future__ import annotations

from importlib import metadata
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    cast,
    overload,
)

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter
from pydantic.alias_generators import to_snake
from tinydb.queries import Query, where
from tinydb.table import Document, Table

from tinydantic._config import (
    CONFIG_ATTR,
    TinydanticConfig,
    check_config_ambiguity,
    get_config_value,
)
from tinydantic._errors import (
    DatabaseNotBoundError,
    DocumentAlreadyExistsError,
    DocumentIDRequiredError,
    DocumentIDUpdateError,
    DocumentNotFoundError,
    SelectorError,
    ShadowedFieldError,
    TinydanticError,
    UnknownUpdateFieldError,
)
from tinydantic._query import (
    DocIdCondition,
    DocIdQuery,
    has_id_condition,
)
from tinydantic.tinydb.operations import replace

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

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
    """

    def __getattr__(cls, attr: str) -> Any:  # noqa: N805
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

    # --- configuration ---

    def __init_subclass__(
        cls,
        *,
        database: TinyDB | None = None,
        table_name: str | None = None,
        validate_writes: bool | None = None,
        shadowed_fields: tuple[str, ...] | None = None,
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
        if validate_writes is not None:
            config["validate_writes"] = validate_writes
        if shadowed_fields is not None:
            config["shadowed_fields"] = shadowed_fields
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

    @classmethod
    def bind(
        cls,
        *,
        database: TinyDB | None = None,
        table_name: str | None = None,
    ) -> None:
        """Bind or rebind tinydantic config after class definition.

        The late-binding escape hatch for tests and application
        factories where no TinyDB instance exists at import time:

        ```python
        class User(TinydanticModel):
            name: str


        User.bind(database=TinyDB("db.json"))
        ```

        Only the keys passed are updated; other keys keep their
        current (possibly inherited) values. Binding a subclass never
        affects its parents.
        """
        config = cast(
            "TinydanticConfig",
            dict(cls.__dict__.get(CONFIG_ATTR, {})),
        )
        if database is not None:
            config["database"] = database
        if table_name is not None:
            config["table_name"] = table_name
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

        Args:
            document: A TinyDB document (or plain mapping) to validate.

        Returns:
            A validated model instance, with ``id`` set from ``doc_id``
            when ``document`` carries one.
        """
        if isinstance(document, Document):
            return cls.model_validate(
                {**document, "id": document.doc_id},
            )
        return cls.model_validate(document)

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
        # Serialize before the try: pydantic.ValidationError is a
        # ValueError and must never be mistaken for a duplicate id.
        serialized = [doc.to_tinydb_document() for doc in docs]
        table = cls.get_table()
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
        read performs — so a failing merge aborts the whole cycle
        before its storage write.

        Raises:
            pydantic.ValidationError: If the merged body fails
                model validation.
        """
        body = dict(data[target_id])
        if callable(fields):
            fields(body)
        else:
            body.update(fields)
        if validate:
            cls.model_validate({**body, "id": target_id})
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

        raise TypeError

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

        Conditions on ``Model.id`` are supported (bare or composed
        with field conditions), evaluated against
        [Document][tinydb.table.Document] wrappers so they can
        read ``doc_id``. When ``doc_ids`` is passed explicitly,
        TinyDB's precedence applies and ``cond`` is not evaluated.

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
                cast("Callable[[Mapping], None]", fields),
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
            elif _cond is not None:
                targets = [
                    target_id
                    for target_id in list(data)
                    if _cond(
                        table.document_class(
                            data[target_id],
                            target_id,
                        ),
                    )
                ]
            else:
                targets = list(data)
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
        document means nothing is written.

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
                prepared,
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
        if cond is not None and has_id_condition(cond):
            document_dict = document.to_tinydb_document(force_dict=True)
            table = cls.get_table()
            _cond = cond

            def apply_upsert(data: dict[int, Any]) -> list[int]:
                """Merge the document body into matching documents."""
                matched: list[int] = []
                for target_id in list(data):
                    doc = table.document_class(
                        data[target_id],
                        target_id,
                    )
                    if _cond(doc):
                        matched.append(target_id)
                        # Copy-on-write: see update().
                        body = dict(data[target_id])
                        body.update(document_dict)
                        data[target_id] = body
                return matched

            ids = cls._run_write_cycle(apply_upsert)
            if not ids:
                ids = [table.insert(document_dict)]
        else:
            ids = cls.get_table().upsert(
                document.to_tinydb_document(force_dict=cond is not None),
                cond,
            )
        if len(ids) == 1:
            document.id = ids[0]
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
        ``doc_id``.

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
            type(self).model_validate({**doc, "id": self.id})

        if (force_dict is False) and (self.id is not None):
            doc = Document(doc, self.id)

        return doc

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
        # Serialize before the try: pydantic.ValidationError is a
        # ValueError and must never be mistaken for a duplicate id.
        doc = self.to_tinydb_document()
        try:
            self.id = self.get_table().insert(doc)
        except ValueError as exc:
            raise DocumentAlreadyExistsError(
                model_name=type(self).__name__,
                table_name=self.get_table().name,
                doc_ids=[cast("int", self.id)],
            ) from exc

        return self

    def replace(self) -> None:
        """Overwrite this model's stored document in place.

        Requires ``id`` to be set. Unlike
        [update][tinydantic.TinydanticModel.update], which merges
        fields, ``replace`` swaps the entire stored document for this
        model's current serialized state, so fields absent from the
        model are removed. Unlike
        [save][tinydantic.TinydanticModel.save], which re-inserts a
        missing document, ``replace`` requires the document to already
        exist.

        Raises:
            DocumentIDRequiredError: If ``id`` is not set (the model
                was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
        """
        if self.id is None:
            raise DocumentIDRequiredError(
                model_name=type(self).__name__,
                operation="replace",
            )

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
                    replace(self.to_tinydb_document(force_dict=True)),
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

    def delete(self) -> None:
        """Remove this model's document from its table.

        Raises:
            DocumentIDRequiredError: If ``id`` is not set (the model
                was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
        """
        if self.id is None:
            raise DocumentIDRequiredError(
                model_name=type(self).__name__,
                operation="delete",
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

        Returns:
            This instance, with the patched fields set to their
            validated values.

        Raises:
            DocumentIDRequiredError: If ``id`` is ``None`` (the
                model was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
            DocumentIDUpdateError: If ``fields`` contains ``id``.
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
        cls.update(fields, doc_ids=[self.id])
        # Sync only after the write succeeded. Direct __dict__
        # assignment, NOT setattr: with validate_assignment on,
        # per-field assignment can trip a cross-field invariant on
        # a transient state (start moved before end) even though
        # the final state — already checked by the merged-result
        # validation above — is valid.
        self.__dict__.update(validated)
        self.__pydantic_fields_set__.update(validated)
        return self

    def save(self) -> Self:
        """Insert this model if it is new, otherwise update it by id.

        If ``id`` is set but the document no longer exists in the
        table, it is re-inserted under the same id (TinyDB upsert
        semantics) — unlike ``replace()``/``delete()``, which raise
        [DocumentNotFoundError][tinydantic.DocumentNotFoundError].

        Returns:
            This instance (with ``id`` set if it was newly inserted).
        """
        if self.id is None:
            return self.insert()
        self.id = self.get_table().upsert(self.to_tinydb_document())[0]
        return self
