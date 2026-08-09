# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""The query expressions tinydantic hands out.

Two pairs of types live here, one specializing the other. Each pair
is a *query* (the builder reached from a model class) and the
*condition* its comparisons produce — mirroring TinyDB's own
[Query][tinydb.queries.Query] and
[QueryInstance][tinydb.queries.QueryInstance] split:

```text
GuardedQuery ── GuardedCondition
    └── DocIdQuery ── DocIdCondition
```

**Guarded queries** are what ``Model.field``, ``q()``, and
``field()`` return. They behave exactly like TinyDB's own types —
same tests, same hashvals, same equality, so they stay
interchangeable with raw TinyDB conditions — except that the three
protocols TinyDB leaves silently wrong raise
[QueryConditionError][tinydantic.QueryConditionError] instead:
boolean context (every condition is otherwise truthy, so
``if Model.field == x:`` is a check that always passes), iteration
(which powers ``in``, otherwise ``True`` for any operand), and
non-string path steps (which TinyDB reads as a callable to apply,
so ``Model.field[0]`` otherwise matches nothing).

**Doc-id queries** specialize that pair for ``Model.id``, which
maps to TinyDB's ``doc_id`` — the document's *key* in the table
mapping — not a field in the stored document body. TinyDB evaluates
conditions against the body only (``search``, ``get``, ``update``,
and ``remove`` all call the condition with the raw body mapping),
so no ordinary ``Query`` can express "document id equals 1"; such a
query would silently match nothing. Class-level ``Model.id`` access
returns a ``DocIdQuery`` whose comparisons build ``DocIdCondition``
instances. The model's query methods detect these (via
``has_id_condition``) and translate them to TinyDB's native
``doc_id``-based operations. If an id condition ever reaches
TinyDB's raw body-only evaluator, it raises
[DocumentIDConditionError][tinydantic.DocumentIDConditionError]
rather than silently matching nothing.
"""

from __future__ import annotations

import operator

from typing import TYPE_CHECKING, Any, Final

from tinydb.queries import Query, QueryInstance

from tinydantic._errors import (
    DocumentIDConditionError,
    QueryConditionError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

# Tag marking a DocIdCondition's hashval. Composed queries
# (``&``/``|``/``~``) embed their operands' hashvals in
# tuple/frozenset trees, so the tag keeps id conditions detectable
# inside compositions.
DOC_ID_SENTINEL: Final[str] = "__tinydantic_doc_id__"

_MISSING: Final = object()

_ESCAPED_MSG = (
    "An id condition reached TinyDB's raw query evaluator, which "
    "only ever sees the document body (never doc_id). Pass id "
    "conditions to tinydantic model methods, or select documents "
    "with doc_id=/doc_ids= instead."
)


def _validate_doc_id(value: object) -> int:
    """Check that an id comparison operand is a plain int.

    TinyDB document ids are ints. ``None`` (an id that was never
    assigned) and other types are rejected loudly instead of
    building a condition that could never match.

    Raises:
        TypeError: If ``value`` is not an int (bools are rejected
            too).
    """
    if isinstance(value, bool) or not isinstance(value, int):
        msg = (
            f"id conditions require an int document id, got "
            f"{value!r}. An id of None means the model was never "
            "inserted — insert() or save() it first."
        )
        raise TypeError(msg)
    return value


_BOOL_COND_MSG = (
    "A query condition has no truth value (it is a lazy "
    "description of a test, not a comparison). For an existence "
    "check use Model.contains(cond), Model.get(cond) is not None, "
    "or Model.find(cond).exists(). To combine conditions use & | ~ "
    "— and/or/not evaluate truthiness and silently discard half "
    "the query. To compare a value you already hold, reach through "
    "an instance (user.name == x), not the class (User.name == x). "
    "To test whether a condition variable was set, write "
    "'cond is not None'."
)

_BOOL_QUERY_MSG = (
    "A field query has no truth value (Model.field is a query "
    "builder, not a value). Compare it to build a condition "
    "(Model.field == value) and pass that to a query method. On an "
    "instance, instance.field is the value itself."
)

_ITER_MSG = (
    "A field query is not iterable (Model.field is a query "
    "builder, not a value), so 'x in Model.field' cannot work — it "
    "would be True for any x. For a substring use "
    "Model.field.search(pattern) or Model.field.test(predicate); "
    "for an element of a list field use Model.field.any([x])."
)


def _index_msg(item: object) -> str:
    """Build the message for a non-string query path step."""
    return (
        f"Query paths are document keys, so Model.field[...] takes "
        f"a string; got {item!r}. TinyDB reads a non-string step as "
        f"a function to call, so indexing a list field by position "
        f"builds a condition that matches nothing. Use "
        f"Model.field.any([value]) to test membership, or "
        f"Model.field.test(lambda v: v[0] == value) for a "
        f"positional check."
    )


def _guarded(cond: QueryInstance) -> QueryInstance:
    """Retag a plain ``QueryInstance`` as a guarded condition.

    TinyDB builds every condition through ``QueryInstance(...)``
    directly, so a ``Query`` subclass alone cannot change what
    comparisons return. Rebuilding the object instead would mean
    reading its ``_test`` and ``_hash`` — private attributes — or
    dropping the hash and with it TinyDB's query cache. Reassigning
    ``__class__`` avoids both: it uses no private names, keeps the
    identical test function and hashval (so guarded conditions
    still compare, hash, and cache exactly like raw TinyDB ones),
    and only ever applies to objects TinyDB just constructed.

    Conditions that are already a tinydantic subclass — a
    ``DocIdCondition``, or one retagged earlier — are returned
    untouched.
    """
    if type(cond) is QueryInstance:
        cond.__class__ = GuardedCondition
    return cond


class GuardedCondition(QueryInstance):
    """A query condition that refuses to answer as a boolean.

    Behaves exactly like TinyDB's
    [QueryInstance][tinydb.queries.QueryInstance] — same test, same
    hash, same equality, so it stays interchangeable with raw
    TinyDB conditions — except that boolean context raises instead
    of returning the default ``True``.

    Composition preserves the guard: ``&``, ``|``, and ``~`` return
    guarded conditions, so ``if (a & b):`` raises too.
    """

    def __bool__(self) -> bool:
        """Refuse boolean context — a condition is not a boolean.

        Raises:
            QueryConditionError: Always.
        """
        raise QueryConditionError(_BOOL_COND_MSG)

    def __and__(self, other: QueryInstance) -> QueryInstance:
        """Compose with ``and``, keeping the guard."""
        return _guarded(super().__and__(other))

    def __or__(self, other: QueryInstance) -> QueryInstance:
        """Compose with ``or``, keeping the guard."""
        return _guarded(super().__or__(other))

    def __invert__(self) -> QueryInstance:
        """Negate, keeping the guard."""
        return _guarded(super().__invert__())


class GuardedQuery(Query):
    """The query builder returned by class-level ``Model.field``.

    A [Query][tinydb.queries.Query] whose condition builders return
    ``GuardedCondition`` objects, and which refuses the three
    protocols TinyDB leaves silently wrong:
    boolean context, iteration (which powers ``in``), and
    non-string path steps.

    Attribute and string-key chaining preserve the subclass, so
    ``User.address.city`` and ``Model.field["key"]`` stay guarded.
    """

    def __bool__(self) -> bool:
        """Refuse boolean context — a query is not a boolean.

        Raises:
            QueryConditionError: Always.
        """
        raise QueryConditionError(_BOOL_QUERY_MSG)

    def __iter__(self) -> Any:
        """Refuse iteration — and with it ``in``.

        Without this, Python falls back to the legacy sequence
        protocol: it calls ``__getitem__(0)``, compares the
        resulting query to the left operand (which builds a
        condition, which is truthy), and reports ``True`` for any
        operand at all.

        Raises:
            QueryConditionError: Always.
        """
        raise QueryConditionError(_ITER_MSG)

    def __getitem__(self, item: str) -> Any:
        """Extend the query path by a document key.

        Raises:
            QueryConditionError: If ``item`` is not a string.
        """
        if not isinstance(item, str):
            raise QueryConditionError(_index_msg(item))
        return super().__getitem__(item)

    def __eq__(self, rhs: object) -> Any:  # type: ignore[override]
        """Build an ``== rhs`` condition."""
        return _guarded(super().__eq__(rhs))

    def __ne__(self, rhs: object) -> Any:  # type: ignore[override]
        """Build a ``!= rhs`` condition."""
        return _guarded(super().__ne__(rhs))

    def __lt__(self, rhs: Any) -> Any:
        """Build a ``< rhs`` condition."""
        return _guarded(super().__lt__(rhs))

    def __le__(self, rhs: Any) -> Any:
        """Build a ``<= rhs`` condition."""
        return _guarded(super().__le__(rhs))

    def __gt__(self, rhs: Any) -> Any:
        """Build a ``> rhs`` condition."""
        return _guarded(super().__gt__(rhs))

    def __ge__(self, rhs: Any) -> Any:
        """Build a ``>= rhs`` condition."""
        return _guarded(super().__ge__(rhs))

    # Defining __eq__ suppresses the inherited __hash__; restore it
    # so GuardedQuery instances stay hashable like any Query.
    __hash__ = Query.__hash__

    def exists(self) -> Any:
        """Build an "key is present" condition."""
        return _guarded(super().exists())

    def matches(self, regex: str, flags: int = 0) -> Any:
        """Build a whole-value regex condition."""
        return _guarded(super().matches(regex, flags))

    def search(self, regex: str, flags: int = 0) -> Any:
        """Build a substring regex condition."""
        return _guarded(super().search(regex, flags))

    def test(self, func: Callable[..., Any], *args: Any) -> Any:
        """Build a condition from an arbitrary predicate."""
        return _guarded(super().test(func, *args))

    def any(self, cond: Any) -> Any:
        """Build an "any element matches" condition."""
        return _guarded(super().any(cond))

    def all(self, cond: Any) -> Any:
        """Build an "every element matches" condition."""
        return _guarded(super().all(cond))

    def one_of(self, items: list[Any]) -> Any:
        """Build a "value is one of items" condition."""
        return _guarded(super().one_of(items))

    def fragment(self, document: Mapping[str, Any]) -> Any:
        """Build a "contains this sub-document" condition."""
        return _guarded(super().fragment(document))

    def noop(self) -> Any:
        """Build a condition matching every document."""
        return _guarded(super().noop())


class DocIdCondition(GuardedCondition):
    """A query condition on the document id (TinyDB's ``doc_id``).

    Built by comparing ``Model.id`` (a ``DocIdQuery``) to an int.
    The test function reads ``doc.doc_id``, which only exists on
    [Document][tinydb.table.Document] instances — tinydantic's
    model methods evaluate id conditions by iterating the table
    (which yields Documents). TinyDB's own evaluator passes the
    raw body mapping instead; reaching it raises
    [DocumentIDConditionError][tinydantic.DocumentIDConditionError]
    so an id condition can never silently match nothing.
    """

    def __init__(
        self,
        opname: str,
        op: Callable[[Any, Any], bool],
        value: int | tuple[int, ...],
    ) -> None:
        """Build a condition testing ``doc_id`` against ``value``.

        Args:
            opname: Operator name for the hash (e.g. ``"=="``).
            op: Binary predicate applied as ``op(doc_id, value)``.
            value: The validated operand (an int, or a tuple of
                ints for ``one_of``).
        """
        self.opname = opname
        self.value = value

        def test(doc: Any) -> bool:
            """Test ``doc.doc_id`` against the operand."""
            doc_id = getattr(doc, "doc_id", _MISSING)
            if doc_id is _MISSING:
                raise DocumentIDConditionError(_ESCAPED_MSG)
            return op(doc_id, value)

        super().__init__(test, (DOC_ID_SENTINEL, opname, value))


class DocIdQuery(GuardedQuery):
    """The query expression returned by class-level ``Model.id``.

    Comparing it to an int builds a ``DocIdCondition`` that the
    model's query methods translate to TinyDB ``doc_id``
    operations:

    ```python
    User.get(User.id == 1)
    User.search(User.id.one_of([1, 3]))
    ```

    Unlike body-field queries, ``id`` has no sub-fields, so
    attribute access raises ``AttributeError``.
    """

    def __eq__(  # type: ignore[override]
        self,
        value: object,
    ) -> DocIdCondition:
        """Build an ``id == value`` condition."""
        return DocIdCondition("==", operator.eq, _validate_doc_id(value))

    def __ne__(  # type: ignore[override]
        self,
        value: object,
    ) -> DocIdCondition:
        """Build an ``id != value`` condition."""
        return DocIdCondition("!=", operator.ne, _validate_doc_id(value))

    def __lt__(self, value: object) -> DocIdCondition:
        """Build an ``id < value`` condition."""
        return DocIdCondition("<", operator.lt, _validate_doc_id(value))

    def __le__(self, value: object) -> DocIdCondition:
        """Build an ``id <= value`` condition."""
        return DocIdCondition("<=", operator.le, _validate_doc_id(value))

    def __gt__(self, value: object) -> DocIdCondition:
        """Build an ``id > value`` condition."""
        return DocIdCondition(">", operator.gt, _validate_doc_id(value))

    def __ge__(self, value: object) -> DocIdCondition:
        """Build an ``id >= value`` condition."""
        return DocIdCondition(">=", operator.ge, _validate_doc_id(value))

    # Defining __eq__ suppresses the inherited __hash__; restore it
    # so DocIdQuery instances stay hashable like any Query.
    __hash__ = Query.__hash__

    def one_of(self, items: Iterable[object]) -> DocIdCondition:
        """Build an ``id in items`` condition.

        Args:
            items: An iterable of int document ids.

        Raises:
            TypeError: If any element is not an int.
        """
        ids = tuple(_validate_doc_id(item) for item in items)
        return DocIdCondition("one_of", lambda a, b: a in b, ids)

    def __getattr__(self, item: str) -> Any:
        """Refuse sub-field access — id has no sub-fields.

        Raises:
            AttributeError: Always; ``id`` maps to the document id
                and supports comparisons only.
        """
        msg = (
            f"Model.id has no sub-field {item!r}; it maps to "
            "TinyDB's doc_id and supports comparisons only"
        )
        raise AttributeError(msg)


def has_id_condition(cond: object) -> bool:
    """Check whether a condition contains an id condition.

    Detects a bare ``DocIdCondition`` or one embedded in a composed
    query by walking the query's hash tree for the
    ``DOC_ID_SENTINEL`` tag. Compositions that erase the hash (for
    example combining with a non-cacheable custom query) are
    undetectable here; they fail loudly at evaluation instead (see
    ``DocIdCondition``).
    """
    if isinstance(cond, DocIdCondition):
        return True
    # QueryInstance keeps its hash tree in the private ``_hash``
    # attribute; TinyDB offers no public accessor. This read-only
    # dependency is recorded in the private-API registry on the
    # Upstream Limitations docs page. getattr keeps it tolerant of
    # arbitrary QueryLike objects — and if a future TinyDB renames
    # the attribute, detection degrades loudly, not silently:
    # bare DocIdConditions are still caught by the isinstance
    # check above, and undetected compositions raise
    # DocumentIDConditionError when TinyDB evaluates them.
    return _tree_has_sentinel(getattr(cond, "_hash", None))


def _tree_has_sentinel(node: object) -> bool:
    """Check a hashval tree for the ``DOC_ID_SENTINEL`` tag."""
    if isinstance(node, tuple):
        if node and node[0] == DOC_ID_SENTINEL:
            return True
        return any(_tree_has_sentinel(item) for item in node)
    if isinstance(node, frozenset):
        return any(_tree_has_sentinel(item) for item in node)
    return False
