# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Document-id query expressions.

``Model.id`` maps to TinyDB's ``doc_id`` — the document's *key* in
the table mapping — not a field in the stored document body. TinyDB
evaluates query conditions against the body only (``search``,
``get``, ``update``, and ``remove`` all call the condition with the
raw body mapping), so no ordinary [Query][tinydb.queries.Query] can
express "document id equals 1"; such a query would silently match
nothing.

This module provides the marker types tinydantic uses instead.
Class-level ``Model.id`` access returns a ``DocIdQuery`` whose
comparisons build ``DocIdCondition`` instances. The model's query
methods detect these (via ``has_id_condition``) and translate them
to TinyDB's native ``doc_id``-based operations. If an id condition
ever reaches TinyDB's raw body-only evaluator, it raises
[DocumentIDConditionError][tinydantic.DocumentIDConditionError]
rather than silently matching nothing.
"""

from __future__ import annotations

import operator

from typing import TYPE_CHECKING, Any, Final

from tinydb.queries import Query, QueryInstance

from tinydantic._errors import DocumentIDConditionError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

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


class DocIdCondition(QueryInstance):
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


class DocIdQuery(Query):
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
    # TinyDB Limitations docs page. getattr keeps it tolerant of
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
