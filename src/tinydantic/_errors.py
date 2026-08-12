# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Errors specific to tinydantic."""

from __future__ import annotations


class TinydanticError(Exception):
    """Base class for `tinydantic` errors."""


class TinydanticUserError(TinydanticError):
    """Base class for errors caused by incorrect use of tinydantic."""


class DatabaseNotBoundError(TinydanticUserError):
    """No database is bound to the model class.

    Raised when a table operation is attempted on a model that has no
    ``database`` configured anywhere in its class hierarchy.
    """

    def __init__(self, model_name: str) -> None:
        """Initialize with the name of the unbound model class."""
        super().__init__(
            f"No database is bound to {model_name!r}. Pass "
            "database=<TinyDB instance> as a class keyword when "
            f"defining the model, or call {model_name}.bind("
            "database=...) before using it.",
        )


class AmbiguousConfigError(TinydanticUserError):
    """Conflicting tinydantic config inherited from unrelated bases.

    Raised at class-definition time when two base classes that are not
    part of one inheritance chain supply different values for the same
    tinydantic config key and the new class does not set that key
    itself. tinydantic refuses to guess which base should win — see
    the ``tinydantic._config`` module docstring for the design
    rationale.
    """

    def __init__(
        self,
        *,
        model_name: str,
        key: str,
        first: str,
        second: str,
    ) -> None:
        """Initialize with the conflicting classes and config key."""
        super().__init__(
            f"{model_name!r} inherits conflicting values for tinydantic "
            f"config key {key!r} from unrelated base classes {first!r} "
            f"and {second!r}. Set {key}= explicitly on {model_name!r} "
            "to resolve the ambiguity.",
        )


class DocumentNotFoundError(TinydanticError):
    """Requested document is not found.

    The message names the model, the table, and — when the lookup was
    by id — the missing document id, so the error is actionable
    without a debugger.
    """

    def __init__(
        self,
        *,
        model_name: str,
        table_name: str,
        doc_id: int | None = None,
    ) -> None:
        """Initialize with the model, table, and optional id context."""
        if doc_id is not None:
            selector = f"with id {doc_id}"
        else:
            selector = "matching the given query"
        super().__init__(
            f"No document {selector} in table {table_name!r} "
            f"(model {model_name!r})",
        )


class DocumentAlreadyExistsError(TinydanticError, ValueError):
    """A document with this id already exists in the table.

    Raised by ``insert()`` and ``insert_many()`` when a model
    arrives with an ``id`` that is already taken — by a stored
    document, or by another model in the same batch. A
    ``ValueError`` subclass, so handlers written for TinyDB's raw
    error keep working.
    """

    def __init__(
        self,
        *,
        model_name: str,
        table_name: str,
        doc_ids: list[int],
    ) -> None:
        """Initialize with the model, table, and taken id(s)."""
        ids = ", ".join(str(doc_id) for doc_id in doc_ids)
        noun = "id" if len(doc_ids) == 1 else "ids"
        super().__init__(
            f"Document with {noun} {ids} already exists in table "
            f"{table_name!r} (model {model_name!r}). Omit id to "
            "let TinyDB assign one, or use save()/upsert() to "
            "update the existing document.",
        )


class UniqueConstraintError(TinydanticError):
    """A write would duplicate a unique value (tuple).

    Raised by create-style and instance-level writes when a field
    marked [Unique][tinydantic.Unique] — or the field tuple of a
    [UniqueConstraint][tinydantic.UniqueConstraint] — already
    holds the same value elsewhere: in the table, or earlier in
    the same ``insert_many()`` batch. When the match was
    produced by a comparison-``key`` callable, the message shows
    the computed key alongside the raw values, so a normalized
    match never looks like a phantom collision.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        model_name: str,
        table_name: str,
        fields: tuple[str, ...],
        values: tuple[object, ...],
        comparison_key: object | None = None,
        doc_id: int | None,
    ) -> None:
        """Initialize with the clash location and values."""
        where = (
            f"document {doc_id}"
            if doc_id is not None
            else "another document in the same batch"
        )
        if len(fields) == 1:
            subject = (
                f"Value {values[0]!r} for unique field "
                f"{fields[0]!r} already exists"
            )
        else:
            subject = (
                f"Values {values!r} for unique fields {fields!r} already exist"
            )
        key_clause = (
            f" (comparison key {comparison_key!r})"
            if comparison_key is not None
            else ""
        )
        super().__init__(
            f"{subject}{key_clause} in table {table_name!r} "
            f"(model {model_name!r}) — held by {where}.",
        )


class DocumentIDConditionError(TinydanticUserError):
    """An id condition was used where ``doc_id`` is unavailable.

    ``Model.id`` conditions are translated to document-id
    operations by the tinydantic model methods. TinyDB itself
    evaluates query conditions against the document body, which
    never contains the document id, so an id condition that
    reaches TinyDB's raw evaluator raises this error instead of
    silently matching nothing.
    """

    def __init__(self, message: str) -> None:
        """Initialize with a context-specific message."""
        super().__init__(message)


class DocumentIDUpdateError(TinydanticUserError):
    """An update mapping tried to set the ``id`` field.

    ``id`` maps to TinyDB's ``doc_id`` — the document's key in the
    table, not a field in the stored body — and an update cannot
    change it. Allowing the key through would write a stray ``id``
    field into the body that ``insert()`` and ``save()`` would
    never produce.
    """

    def __init__(self, *, model_name: str) -> None:
        """Initialize with the model whose update set ``id``."""
        super().__init__(
            f"update() cannot set 'id' on {model_name!r} — id "
            "maps to TinyDB's doc_id, which updates cannot "
            "change. Use doc_ids=[...] or a query condition to "
            "select documents instead.",
        )


class UnknownUpdateFieldError(TinydanticUserError):
    """An update mapping contains keys that are not model fields.

    Unknown keys are rejected by default: they bypass validation
    entirely (pydantic ignores extra keys), so allowing them
    through would persist unvalidated — even non-JSON-safe —
    values. Pass ``extra_keys="allow"`` to write them anyway, for
    example when the database file is shared with other tools or
    carries schema-evolution keys this model does not know yet.
    """

    def __init__(self, *, model_name: str, keys: list[str]) -> None:
        """Initialize with the model and the offending keys."""
        joined = ", ".join(repr(key) for key in sorted(keys))
        super().__init__(
            f"update() mapping for {model_name!r} contains keys "
            f"that are not model fields: {joined}. Unknown keys "
            "are written without any validation, so they are "
            'rejected by default; pass extra_keys="allow" to '
            "write them anyway.",
        )


class SelectorError(TinydanticUserError, ValueError):
    """A method got no selector, or conflicting selectors.

    Selector-taking methods (``get()``, ``contains()``,
    ``update()``, ``remove()``, ``get_or_raise()``, ``upsert()``)
    need exactly one way to pick documents. This covers *how many*
    were given — none, or several — not what they are: a selector
    of the wrong kind is a
    [QueryTypeError][tinydantic.QueryTypeError].

    It stays separate from
    [QueryValueError][tinydantic.QueryValueError], despite sharing
    a base, because a selector is not always a query:
    ``get(doc_id=1, doc_ids=[1])`` names no query at all.

    ``ValueError`` is the base for the same reason
    ``subprocess.run(capture_output=True, stdout=...)`` raises one
    — the arguments are individually well-typed and wrong in
    combination. tinydantic raises it instead of letting TinyDB's
    ``RuntimeError`` (which nothing catches deliberately) or its
    hints about TinyDB internals leak through.
    """

    def __init__(self, message: str) -> None:
        """Initialize with a context-specific message."""
        super().__init__(message)


class QueryTypeError(TinydanticUserError, TypeError):
    """A query and a value were confused for one another.

    One mistake with two directions, and tinydantic raises the
    same type for both because a caller recovers from them the
    same way:

    -   A query object used as a value. ``Model.field`` is a query
        builder and ``Model.field == value`` describes a test —
        neither is a boolean, neither is iterable, and a query
        path is a sequence of document keys. Python's default
        answers are silently wrong (every object is truthy; a
        ``Query`` iterates forever through ``__getitem__``; a
        non-string path step is read as a callable and matches
        nothing).
    -   A value used as a query. ``search("Alice")`` and
        ``search({"name": "Alice"})`` reach TinyDB as conditions
        it cannot evaluate, failing with ``'str' object is not
        callable`` or ``unhashable type: 'dict'`` — or, on an
        empty table, not failing at all and returning ``[]``.

    A modifier operand of the wrong type (``limit("10")``) lands
    here too: same rule, same base.

    ``TypeError`` is the base because Python raises ``TypeError``
    for every analogous mistake — a non-iterable in ``list()``, a
    bad index type, an argument of the wrong type. An earlier
    design used ``ValueError`` on the numpy/pandas
    ambiguous-truth precedent, but that precedent only ever
    covered ``bool()``; it was carried to iteration, indexing, and
    argument types, where it does not apply. Nothing depended on
    the old base: raw TinyDB raises nothing at all for the
    query-as-value cases, and the value-as-query cases leaked a
    bare ``TypeError`` anyway.

    Despite the name this is not about static typing — it is the
    runtime kind of an object. Type-checker friction is what
    [q()][tinydantic.q] is for.
    """


class QueryValueError(TinydanticUserError, ValueError):
    """A query operand has the right type and an unusable value.

    Raised eagerly, at the call that supplied the value: a
    negative ``skip()``/``limit()`` window, or a ``sort()`` given
    both field names and ``key=`` when it can honor only one.

    The line against
    [QueryTypeError][tinydantic.QueryTypeError] is Python's own:
    ``limit("10")`` is the wrong kind of object, ``limit(-1)`` is
    the right kind carrying a value no window can have.
    """


class QueryUsageError(TinydanticUserError):
    """A query was built in an unsupported sequence.

    Type and value are both fine; the call sequence is not.
    Raised when a chain restates a clause it already has —
    ``find().sort("a").sort("b")`` — because the ecosystem
    disagrees about what repetition means (Beanie appends a
    tiebreaker, Python's stable-sort idiom and pandas make the
    last sort primary, Django and MongoEngine replace), so
    tinydantic refuses to guess.

    Alone among the query errors it subclasses no builtin. It is
    neither a type nor a value problem, and mapping it onto
    ``ValueError`` or ``RuntimeError`` would be arbitrary; the
    thing to catch is
    [TinydanticUserError][tinydantic.TinydanticUserError].

    ``filter()`` is deliberately exempt: successive filters mean
    AND everywhere in the ecosystem, so there is nothing to guess.
    """


class QueryFieldError(TinydanticUserError, AttributeError):
    """A name is not a queryable or sortable field of the model.

    Raised eagerly — at the [field()][tinydantic.field] call, the
    ``.sort()`` call, or the ``Model.name`` attribute access —
    rather than returning a query that matches nothing forever.
    Covers names the model does not declare (including storage
    aliases, which are never storage keys), ``id`` (mapped to
    ``doc_id``, never written to the document body), and dotted
    paths (``where()`` does not traverse them — chain attributes
    instead).

    Keys the model genuinely does not declare — ``extra="allow"``
    documents, legacy keys — are reachable with TinyDB's
    ``where()``, which the message names.

    ``AttributeError`` is load-bearing, not decoration: the
    metaclass raises this from ``__getattr__``, and ``hasattr()``,
    ``copy``, ``pickle``, and pydantic's own introspection all
    depend on attribute lookup failing with an ``AttributeError``.
    """


class ShadowedFieldError(TinydanticUserError):
    """A model field shadows an existing class attribute.

    A real class attribute wins over the metaclass ``__getattr__``
    that turns ``Model.field`` into a query, so a shadowed field's
    query sugar silently evaluates to ``False`` and matches
    nothing (or fails cryptically, depending on table contents).
    tinydantic refuses the class definition instead. Rename the
    field, or list it in the ``shadowed_fields=`` class kwarg and
    query it with ``field(Model, "name")``.
    """

    def __init__(
        self,
        *,
        model_name: str,
        shadowed: dict[str, str],
    ) -> None:
        """Initialize with the model and the shadowed fields."""
        pairs = ", ".join(
            f"{name!r} shadows {owner}"
            for name, owner in sorted(shadowed.items())
        )
        names = ", ".join(repr(name) for name in sorted(shadowed))
        super().__init__(
            f"Field(s) on {model_name!r} shadow existing "
            f"attributes: {pairs}. Model.field query sugar would "
            "silently break for them. Rename the field(s), or "
            f"declare shadowed_fields=({names},) on the class "
            f"and query them with field({model_name}, <field name>).",
        )


class ConstraintFieldError(TinydanticUserError):
    """A unique constraint names a field it cannot enforce.

    Raised at class definition or ``bind()`` time when a
    [UniqueConstraint][tinydantic.UniqueConstraint] names a field
    that is not a model field (it would be ``None`` in every
    stored body and silently never enforce) or names ``id``
    (document ids are never stored in the document body, so an
    ``id`` constraint would silently never match — and ids are
    unique already). Loud rejection instead of silent
    non-enforcement.
    """

    def __init__(
        self,
        *,
        model_name: str,
        constraint_fields: tuple[str, ...],
        field: str,
        reason: str,
    ) -> None:
        """Initialize with the constraint and the offending field."""
        names = ", ".join(repr(name) for name in constraint_fields)
        subject = (
            f"UniqueConstraint({names}) on model {model_name!r} "
            f"names {field!r}"
        )
        if reason == "id":
            message = (
                f"{subject}: document ids are never stored in "
                "the document body, so an id constraint would "
                "silently never match — ids are unique already."
            )
        else:
            message = f"{subject}, which is not a model field."
        super().__init__(message)


class DocumentIDRequiredError(TinydanticError):
    """Required document ID is missing.

    Raised by instance operations that address a stored document by
    its id (``replace()``, ``delete()``) when the instance was never
    inserted, so its ``id`` is still ``None``.
    """

    def __init__(self, *, model_name: str, operation: str) -> None:
        """Initialize with the model name and attempted operation."""
        super().__init__(
            f"Cannot {operation}() a {model_name!r} instance whose id "
            "is None — insert() or save() it first",
        )


class StaleDocumentError(TinydanticError):
    """A revision check failed: the document changed since it was read.

    Raised by ``save()``, ``replace()``, and ``delete()`` on models
    with ``use_revision=True`` when the stored document's
    ``revision_id`` no longer matches the token this instance holds —
    another writer modified (or deleted) the document after this
    instance read it. Nothing is written.

    Recover by reloading the document, re-deciding with fresh state,
    and retrying — or pass ``ignore_revision=True`` for deliberate
    last-write-wins. In HTTP terms this error maps to a
    ``412 Precondition Failed``.

    Attributes:
        doc_id: The contested document id.
        deleted: ``True`` when the document was deleted since it
            was read (so there is nothing to merge with — decide
            whether re-creating it is appropriate and do so
            explicitly with ``insert()``); ``False`` when it was
            modified.
    """

    def __init__(
        self,
        *,
        model_name: str,
        table_name: str,
        doc_id: int,
        deleted: bool,
    ) -> None:
        """Initialize with the model, table, id, and conflict kind."""
        self.doc_id = doc_id
        self.deleted = deleted
        happened = "deleted" if deleted else "modified"
        super().__init__(
            f"{model_name!r} document {doc_id} in table "
            f"{table_name!r} was {happened} since this instance "
            "read it. Reload and retry, or pass "
            "ignore_revision=True for deliberate last-write-wins.",
        )


class RevisionFieldError(TinydanticUserError):
    """A ``use_revision=True`` model declares its own ``revision_id``.

    ``use_revision=True`` injects a ``revision_id`` field managed by
    tinydantic's write paths, so a user-declared field of the same
    name would corrupt the revision protocol. Rename the field, or
    drop ``use_revision``.
    """

    def __init__(self, *, model_name: str) -> None:
        """Initialize with the model name."""
        super().__init__(
            f"{model_name!r} sets use_revision=True but declares its "
            "own 'revision_id' field. revision_id is managed by "
            "tinydantic on revisioned models — rename the field, or "
            "drop use_revision.",
        )


class RevisionUpdateError(TinydanticUserError):
    """An update mapping tried to write ``revision_id`` directly.

    On models with ``use_revision=True``, ``revision_id`` is rotated
    by tinydantic on every write; writing it directly would corrupt
    the revision protocol (a forged token could mask concurrent
    writes). Drop the key — every write path already rotates it.
    """

    def __init__(self, *, model_name: str) -> None:
        """Initialize with the model name."""
        super().__init__(
            f"Cannot write 'revision_id' directly on {model_name!r} — "
            "use_revision=True models rotate it automatically on "
            "every write. Drop the key from the update.",
        )


class DatabaseLockedError(TinydanticError):
    """Another process already holds this database's lock.

    Raised by ``ProcessLockMiddleware`` when the sidecar lock file
    is already exclusively locked — a second process (or a second
    TinyDB instance in this process) has the database open. TinyDB
    is single-process software: concurrent access corrupts data.
    Close the other handle, or point this process at its own
    database file.
    """

    def __init__(self, *, path: str) -> None:
        """Initialize with the database path."""
        self.path = path
        super().__init__(
            f"The database {path!r} is already open in another "
            "process (its lock file is held). TinyDB has no "
            "multi-process safety — close the other process, or "
            "use a separate database file.",
        )
