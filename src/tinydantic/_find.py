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
    [QueryUsageError][tinydantic.QueryUsageError] because the wider
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

from operator import attrgetter
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    Literal,
    TypeVar,
    cast,
)

from tinydb.queries import QueryInstance

from tinydantic._errors import (
    DocumentNotFoundError,
    QueryFieldError,
    QueryTypeError,
    QueryUsageError,
    QueryValueError,
)
from tinydantic._query import _require_condition

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

    from tinydb.queries import QueryLike

    from tinydantic._model import TinydanticModel
    from tinydantic._query import DocIdQuery

ModelT = TypeVar("ModelT", bound="TinydanticModel")

_REPEAT_MSG = (
    "{name}() was already called on this query. Clauses do not "
    "accumulate; state each clause once{hint}."
)


def _validated_window(name: str, n: object) -> int:
    """Check that a skip/limit operand is a non-negative int.

    Bools are rejected like the id-condition operand rule.

    Raises:
        QueryTypeError: If ``n`` is not an int (bools included).
        QueryValueError: If ``n`` is an int below zero.
    """
    if isinstance(n, bool) or not isinstance(n, int):
        msg = (
            f"{name}() requires a non-negative int, got "
            f"{type(n).__name__}: {n!r}"
        )
        raise QueryTypeError(msg)
    if n < 0:
        msg = f"{name}() requires a non-negative int, got {n!r}"
        raise QueryValueError(msg)
    return n


def _and_conditions(left: QueryLike, right: QueryLike) -> QueryLike:
    """Combine two conditions so both must match.

    TinyDB's ``&`` is defined on ``QueryInstance``, not on the
    ``QueryLike`` protocol, so a chain filtered on top of a plain
    callable (a documented spelling) cannot use it. Two
    ``QueryInstance`` operands still compose with ``&`` — keeping
    the stable hashval TinyDB's query cache needs — and anything
    else falls back to a closure, which is hashable by identity
    and so merely uncacheable rather than broken.
    """
    if isinstance(left, QueryInstance) and isinstance(right, QueryInstance):
        return left & right

    def both(value: Mapping[Any, Any]) -> bool:
        """Match only documents both conditions accept."""
        return bool(left(value)) and bool(right(value))

    return both


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

    def filter(self, cond: QueryLike) -> FindQuery[ModelT]:
        """Narrow the chain with another condition (repeatable).

        The new condition is ANDed with whatever the chain
        already carries, so a base query can be refined per
        request without rebuilding it:

        ```python
        base = Article.find(q(Article.published) == True)
        recent = base.filter(q(Article.created) > cutoff)
        mine = recent.filter(q(Article.author_id) == user_id)
        ```

        Unlike ``sort``/``skip``/``limit``, ``filter()`` may be
        called any number of times. Those three refuse a second
        call because the ecosystem disagrees about what
        repetition means; successive filters mean AND in Django,
        SQLAlchemy, Beanie, and Mongoose alike, so there is
        nothing to guess.

        On a chain built by ``find()`` with no condition, the
        first ``filter()`` supplies the condition.

        Args:
            cond: The condition to AND into the chain.

        Returns:
            A new chain matching both conditions.

        Raises:
            QueryTypeError: If ``cond`` is ``None`` or anything
                else TinyDB cannot evaluate as a condition.
        """
        _require_condition(cond, method="filter")
        if self._cond is None:
            return self._replace(cond=cond)
        return self._replace(cond=_and_conditions(self._cond, cond))

    def sort(
        self,
        *fields: str,
        key: Callable[[ModelT], Any] | None = None,
        reverse: bool = False,
    ) -> FindQuery[ModelT]:
        """Set the ordering clause (once per chain).

        Two mutually exclusive forms:

        -   Field names: ``.sort("dept", "-salary")`` — Python
            attribute names, ``-`` prefix for descending, left-
            to-right from most to least significant.
        -   Escape hatch: ``.sort(key=..., reverse=...)`` — any
            callable over a model instance (nested paths, None
            handling).

        A second ``sort()`` raises instead of accumulating or
        replacing: the ecosystem disagrees on what it should
        mean (Beanie appends a tiebreaker; Python's stable-sort
        idiom and pandas make the last sort primary; Django and
        MongoEngine replace), so tinydantic refuses to guess.

        Args:
            fields: Field names, optionally ``-``-prefixed.
            key: Sort-key callable; excludes ``fields``.
            reverse: Descending order; only legal with ``key=``.

        Returns:
            A new chain with the ordering set.

        Raises:
            QueryUsageError: If sort was already set.
            QueryValueError: If the forms are mixed, if
                ``reverse=`` is used without ``key=``, or if
                called with neither fields nor ``key=``.
            QueryFieldError: If a name is not a model field.
        """
        if self._sort_fields is not None or self._sort_key is not None:
            msg = _REPEAT_MSG.format(
                name="sort",
                hint=(", combining keys in one call: .sort('name', '-age')"),
            )
            raise QueryUsageError(msg)
        if key is not None:
            if fields:
                msg = "sort() takes field names or key=, not both"
                raise QueryValueError(msg)
            return self._replace(
                sort_key=key,
                sort_reverse=bool(reverse),
            )
        if reverse:
            msg = (
                "reverse= is only valid with key=; with field "
                "names, mark descending per field with a '-' "
                "prefix: .sort('-age')"
            )
            raise QueryValueError(msg)
        if not fields:
            msg = "sort() requires field names or key="
            raise QueryValueError(msg)
        parsed: list[tuple[str, bool]] = []
        for spec in fields:
            descending = spec.startswith("-")
            name = spec.removeprefix("-")
            if not name or name not in self._model.model_fields:
                msg = (
                    f"{spec!r} is not a sortable field of "
                    f"{self._model.__name__!r}. Sort keys are "
                    "Python field names (not storage aliases); "
                    "known fields: "
                    f"{sorted(self._model.model_fields)}"
                )
                raise QueryFieldError(msg)
            parsed.append((name, descending))
        return self._replace(sort_fields=tuple(parsed))

    def skip(self, n: int) -> FindQuery[ModelT]:
        """Set the number of documents to skip (once per chain).

        Applied after sorting, before ``limit``. ``skip(0)`` is
        a legal no-op.

        Args:
            n: A non-negative int.

        Returns:
            A new chain with the skip set.

        Raises:
            QueryUsageError: If skip was already set.
            QueryTypeError: If ``n`` is not an int (bools
                rejected).
            QueryValueError: If ``n`` is negative.
        """
        if self._skip is not None:
            msg = _REPEAT_MSG.format(name="skip", hint="")
            raise QueryUsageError(msg)
        return self._replace(skip=_validated_window("skip", n))

    def limit(self, n: int) -> FindQuery[ModelT]:
        """Set the maximum result-window size (once per chain).

        Applied last in the fixed pipeline. ``limit(0)`` is
        legal and describes an empty window (it can arise from
        arithmetic).

        Args:
            n: A non-negative int.

        Returns:
            A new chain with the limit set.

        Raises:
            QueryUsageError: If limit was already set.
            QueryTypeError: If ``n`` is not an int (bools
                rejected).
            QueryValueError: If ``n`` is negative.
        """
        if self._limit is not None:
            msg = _REPEAT_MSG.format(name="limit", hint="")
            raise QueryUsageError(msg)
        return self._replace(limit=_validated_window("limit", n))

    def _execute(self) -> list[ModelT]:
        """Run the pipeline: match, sort, then slice the window.

        Matching delegates to the model's read verbs (inheriting
        id-condition translation and the pure-id-equality fast
        path); sorting runs on the validated model instances via
        successive stable sorts, least-significant key first.
        """
        if self._cond is None:
            results = self._model.all()
        else:
            results = self._model.search(self._cond)
        if self._sort_key is not None:
            results.sort(key=self._sort_key, reverse=self._sort_reverse)
        elif self._sort_fields is not None:
            for name, descending in reversed(self._sort_fields):
                results.sort(key=attrgetter(name), reverse=descending)
        start = self._skip or 0
        stop = None if self._limit is None else start + self._limit
        return cast("list[ModelT]", results[start:stop])

    def all(self) -> list[ModelT]:
        """Get the described documents as validated models."""
        return self._execute()

    def first(self) -> ModelT | None:
        """Get the first document of the window, or ``None``.

        Equivalent to ``chain.all()[0]`` when the window is
        non-empty — the window (skip/limit) applies first.
        """
        results = self._execute()
        return results[0] if results else None

    def first_or_raise(self) -> ModelT:
        """Get the first document of the window, or raise.

        The strict counterpart to
        [first][tinydantic.FindQuery.first], raising the same
        error [get][tinydantic.TinydanticModel.get] does. The
        default is lenient here, unlike ``get``: ``first()``
        samples a window that may legitimately be empty, where
        ``get()`` asserts one specific document.

        Raises:
            DocumentNotFoundError: If the window is empty.
        """
        result = self.first()
        if result is None:
            raise DocumentNotFoundError(
                model_name=self._model.__name__,
                table_name=self._model.get_table().name,
                doc_id=None,
            )
        return result

    def count(self) -> int:
        """Count the documents in the window, not the raw match."""
        return len(self._execute())

    def exists(self) -> bool:
        """Check whether the window contains any document."""
        return bool(self._execute())

    def __iter__(self) -> Iterator[ModelT]:
        """Iterate the materialized result of the pipeline."""
        return iter(self._execute())

    def _has_modifiers(self) -> bool:
        """Check whether any sort/skip/limit clause is set."""
        return (
            self._sort_fields is not None
            or self._sort_key is not None
            or self._skip is not None
            or self._limit is not None
        )

    def _id_filter(self, ids: list[int]) -> QueryLike:
        """Build a filtering condition over resolved document ids.

        Resolved ids were never named by the caller, so the chain
        has nothing to assert: the write paths route through this
        condition rather than the ``_by_ids`` verbs, so a document
        vanishing between resolution and write yields a smaller
        result instead of an error. It is also one full table read
        cheaper than the id-assertion path.
        """
        return cast("DocIdQuery", self._model.id).one_of(ids)

    @staticmethod
    def _in_window_order(written: list[int], window: list[int]) -> list[int]:
        """Restore the window's order over a condition's result.

        Condition writes report ids in table order, but a chain
        promises the order its own read pipeline produced — the
        whole point of honouring ``sort``/``skip``/``limit``.
        """
        touched = set(written)
        return [doc_id for doc_id in window if doc_id in touched]

    def _resolved_ids(self) -> list[int]:
        """Resolve the chain to concrete document ids.

        Runs the read pipeline and collects ids — the same set
        (and order) ``.all()`` returns. Ids are always present on
        read results, so the cast is safe.
        """
        return [cast("int", model.id) for model in self._execute()]

    def delete(self) -> list[int]:
        """Remove exactly the documents ``.all()`` would return.

        With only a condition set, delegates the condition to
        [remove][tinydantic.TinydanticModel.remove] directly. With
        modifiers (or no condition), resolves the sorted window to
        concrete ids first and removes those — unlike Beanie,
        which silently ignores sort/skip/limit on delete. Under
        the documented single-process, single-threaded contract
        the two paths are observably identical.

        An empty window is a no-op returning ``[]`` with zero
        storage writes. Deleting the whole table via ``find()``
        with no condition is legal (the spelling is explicit);
        [truncate][tinydantic.TinydanticModel.truncate] remains
        the idiomatic one-pass spelling.

        Returns:
            The removed document ids, in the window's order.
        """
        if self._cond is not None and not self._has_modifiers():
            return self._model.remove(self._cond)
        ids = self._resolved_ids()
        if not ids:
            return []
        return self._in_window_order(
            self._model.remove(self._id_filter(ids)),
            ids,
        )

    def update(
        self,
        fields: Mapping | Callable[[Mapping], None],
        *,
        extra_keys: Literal["reject", "allow"] = "reject",
    ) -> list[int]:
        """Update exactly the documents ``.all()`` would return.

        Mirrors [update][tinydantic.TinydanticModel.update] —
        same ``fields`` mapping-or-transform contract, same
        ``extra_keys`` policy, same errors, same merged-result
        validation and atomic abort, and the same deliberate
        non-enforcement of [Unique][tinydantic.Unique] markers —
        with the chain supplying the selection. With only a
        condition set the condition is delegated directly; with
        modifiers (or no condition) the sorted window is
        resolved to concrete ids first — unlike Beanie, which
        silently ignores sort/skip/limit on update. An empty
        window is a no-op returning ``[]``.

        Args:
            fields: A mapping of new field values, or a
                transform callable applied to each matched
                document body.
            extra_keys: ``"reject"`` (default) refuses mapping
                keys that are not model fields; ``"allow"``
                writes them through unchanged.

        Returns:
            The updated document ids, in the window's order.

        Raises:
            DocumentIDUpdateError: If a mapping contains
                ``id``.
            UnknownUpdateFieldError: If a mapping has non-field
                keys and ``extra_keys`` is ``"reject"``.
            pydantic.ValidationError: If a value or a merged
                document fails validation; nothing is written.
        """
        if self._cond is not None and not self._has_modifiers():
            return self._model.update(
                fields, self._cond, extra_keys=extra_keys
            )
        ids = self._resolved_ids()
        if not ids:
            # Still surface malformed payloads loudly: update()
            # validates mapping keys before selection, so an
            # empty window must not hide a DocumentIDUpdateError
            # or UnknownUpdateFieldError the same call would
            # raise on a non-empty one.
            if not callable(fields):
                self._model._serialize_update_fields(  # noqa: SLF001
                    fields,
                    extra_keys=extra_keys,
                )
            return []
        return self._in_window_order(
            self._model.update(
                fields,
                self._id_filter(ids),
                extra_keys=extra_keys,
            ),
            ids,
        )

    def __bool__(self) -> bool:
        """Refuse boolean context — a chain has no truth value.

        Without this every ``if Model.find(cond):`` would be
        silently, permanently true. It raises the same error a
        bare condition does one layer down — a chain and a
        condition are both query objects, and using either as a
        value is one mistake.

        Raises:
            QueryTypeError: Always; call ``.exists()`` or
                ``.count()``.
        """
        msg = (
            "A FindQuery has no truth value (it is a lazy query "
            "description). Use .exists() or .count()."
        )
        raise QueryTypeError(msg)

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
