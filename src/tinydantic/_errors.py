# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

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
