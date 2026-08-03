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
    ``remove()``, ``get_or_raise()``, ``upsert()``) need exactly
    one way to pick documents. tinydantic raises this — a
    ``ValueError`` subclass, so existing handlers keep working —
    instead of letting TinyDB's ``RuntimeError`` (which nothing
    catches deliberately) or its hints about TinyDB internals
    leak through.
    """

    def __init__(self, message: str) -> None:
        """Initialize with a context-specific message."""
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
