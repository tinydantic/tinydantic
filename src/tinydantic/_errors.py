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

    Raised by ``insert()`` and ``insert_multiple()`` when a model
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
    """A write would duplicate a unique field's value.

    Raised by create-style and instance-level writes when a field
    marked [Unique][tinydantic.Unique] already holds the same
    value elsewhere — in the table, or earlier in the same
    ``insert_multiple()`` batch.
    """

    def __init__(
        self,
        *,
        model_name: str,
        table_name: str,
        field: str,
        value: object,
        doc_id: int | None,
    ) -> None:
        """Initialize with the clash location and value."""
        where = (
            f"document {doc_id}"
            if doc_id is not None
            else "another document in the same batch"
        )
        super().__init__(
            f"Value {value!r} for unique field {field!r} already "
            f"exists in table {table_name!r} (model "
            f"{model_name!r}) — held by {where}.",
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
    need exactly one way to pick documents. tinydantic raises this — a
    ``ValueError`` subclass, so existing handlers keep working —
    instead of letting TinyDB's ``RuntimeError`` (which nothing
    catches deliberately) or its hints about TinyDB internals
    leak through.
    """

    def __init__(self, message: str) -> None:
        """Initialize with a context-specific message."""
        super().__init__(message)


class ShadowedFieldError(TinydanticUserError):
    """A model field shadows an existing class attribute.

    A real class attribute wins over the metaclass ``__getattr__``
    that turns ``Model.field`` into a query, so a shadowed field's
    query sugar silently evaluates to ``False`` and matches
    nothing (or fails cryptically, depending on table contents).
    tinydantic refuses the class definition instead. Rename the
    field, or list it in the ``shadowed_fields=`` class kwarg and
    query it with ``q("name")``.
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
            "and query them with q(<field name>).",
        )


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
