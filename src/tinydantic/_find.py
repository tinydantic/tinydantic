# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Fluent query chains for tinydantic models.

``Model.find(cond)`` returns a [FindQuery][tinydantic.FindQuery]:
an immutable, lazy description of a query — a clause set of
condition, ordering, and window (skip/limit). Modifiers return new
chains; only terminals touch storage, and every terminal operates
on exactly the set ``.all()`` would return.

Design decisions (spelled out on the docs "Fluent queries" page):

-   The pipeline is fixed — match, sort, skip, limit — regardless
    of modifier call order, following the unanimous SQL/MongoDB/
    ODM convention.
-   Each clause is stated once; repeating a modifier raises
    [FindQueryError][tinydantic.FindQueryError] because the wider
    ecosystem disagrees on what repetition means (Beanie appends a
    tiebreaker, Python's stable-sort idiom and pandas make the
    last sort primary, Django and MongoEngine replace), so
    tinydantic refuses to guess.
-   Sorting runs on validated model instances, never raw stored
    bodies, so datetimes and custom types compare by value and
    every field exists.
-   Write terminals honor sort/skip/limit by resolving the chain
    to concrete document ids and delegating to the existing verbs
    — unlike Beanie, which silently ignores the modifiers and
    operates on every match.
"""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeVar,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from tinydb.queries import QueryLike

    from tinydantic._model import TinydanticModel

ModelT = TypeVar("ModelT", bound="TinydanticModel")


class FindQuery(Generic[ModelT]):
    """An immutable, lazy fluent query over a model's table.

    Built by [find][tinydantic.TinydanticModel.find]; not meant to
    be constructed directly. Modifiers (``sort``/``skip``/
    ``limit``) return new chains and validate eagerly; terminals
    (``all``/``first``/``first_or_raise``/``count``/``exists``/
    iteration/``delete``/``update``) execute a fresh read against
    the current binding — results are never cached on the chain.

    The pipeline is fixed: match, then sort, then skip, then
    limit, regardless of the order modifiers are called in. Every
    terminal — including the write terminals — operates on exactly
    the set ``.all()`` would return.
    """

    __slots__ = (
        "_cond",
        "_limit",
        "_model",
        "_skip",
        "_sort_fields",
        "_sort_key",
        "_sort_reverse",
    )

    # The clause set is one argument per clause by design; the
    # constructor is internal (built via find()/_replace only).
    def __init__(  # noqa: PLR0913
        self,
        model: type[ModelT],
        *,
        cond: QueryLike | None = None,
        sort_fields: tuple[tuple[str, bool], ...] | None = None,
        sort_key: Callable[[ModelT], Any] | None = None,
        sort_reverse: bool = False,
        skip: int | None = None,
        limit: int | None = None,
    ) -> None:
        """Store the clause set; performs no I/O or validation."""
        self._model = model
        self._cond = cond
        self._sort_fields = sort_fields
        self._sort_key = sort_key
        self._sort_reverse = sort_reverse
        self._skip = skip
        self._limit = limit

    def _replace(self, **changes: Any) -> FindQuery[ModelT]:
        """Return a copy of this chain with ``changes`` applied."""
        state: dict[str, Any] = {
            "cond": self._cond,
            "sort_fields": self._sort_fields,
            "sort_key": self._sort_key,
            "sort_reverse": self._sort_reverse,
            "skip": self._skip,
            "limit": self._limit,
        }
        state.update(changes)
        return FindQuery(self._model, **state)

    def __repr__(self) -> str:
        """Show the model and full clause set for debugging."""
        if self._sort_key is not None:
            sort: object = f"key={self._sort_key!r}"
        elif self._sort_fields is not None:
            sort = tuple(
                ("-" if descending else "") + name
                for name, descending in self._sort_fields
            )
        else:
            sort = None
        return (
            f"FindQuery({self._model.__name__}, "
            f"cond={self._cond!r}, sort={sort!r}, "
            f"skip={self._skip!r}, limit={self._limit!r})"
        )
