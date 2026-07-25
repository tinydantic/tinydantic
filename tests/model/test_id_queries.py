# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for document-id query expressions and translation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydb import where
from tinydb.queries import QueryInstance

from tinydantic import DocumentIDConditionError
from tinydantic._query import (
    DocIdCondition,
    DocIdQuery,
    has_id_condition,
)

if TYPE_CHECKING:
    from collections.abc import Callable


class TestDocIdQuery:
    """Unit tests for the DocIdQuery expression object."""

    @pytest.mark.parametrize(
        ("opname", "build"),
        [
            ("==", lambda id_query: id_query == 1),
            ("!=", lambda id_query: id_query != 1),
            ("<", lambda id_query: id_query < 1),
            ("<=", lambda id_query: id_query <= 1),
            (">", lambda id_query: id_query > 1),
            (">=", lambda id_query: id_query >= 1),
            ("one_of", lambda id_query: id_query.one_of([1, 3])),
        ],
    )
    def test_comparisons_build_conditions(
        self,
        opname: str,
        build: Callable[[DocIdQuery], DocIdCondition],
    ) -> None:
        """Each operator builds a DocIdCondition with its opname."""
        cond = build(DocIdQuery())
        assert isinstance(cond, DocIdCondition)
        assert cond.opname == opname

    @pytest.mark.parametrize("bad", [None, "1", True, 1.5, [1]])
    def test_non_int_operands_raise(self, bad: object) -> None:
        """Non-int operands raise TypeError, loudly."""
        with pytest.raises(TypeError, match="int document id"):
            _ = DocIdQuery() == bad

    def test_one_of_validates_elements(self) -> None:
        """Each one_of element is validated."""
        with pytest.raises(TypeError, match="int document id"):
            DocIdQuery().one_of([1, "2"])

    def test_attribute_access_raises(self) -> None:
        """The id expression has no sub-fields."""
        with pytest.raises(AttributeError, match="no sub-field"):
            _ = DocIdQuery().city

    def test_equal_conditions_hash_equal(self) -> None:
        """Same condition twice: equal and same hash (cacheable)."""
        first = DocIdQuery() == 1
        second = DocIdQuery() == 1
        assert first == second
        assert hash(first) == hash(second)
        assert first.is_cacheable()

    def test_raw_evaluation_raises(self) -> None:
        """Evaluating against a body mapping (no doc_id) raises."""
        cond = DocIdQuery() == 1
        with pytest.raises(DocumentIDConditionError, match="doc_id"):
            cond({"name": "Alice"})


class TestHasIdCondition:
    """Unit tests for id-condition detection."""

    def test_bare_condition(self) -> None:
        """A bare DocIdCondition is detected."""
        assert has_id_condition(DocIdQuery() == 1)

    def test_composed_and_or_not(self) -> None:
        """Detection survives &, |, ~ composition on either side."""
        id_cond = DocIdQuery() == 1
        field_cond = where("name") == "Alice"
        assert has_id_condition(id_cond & field_cond)
        assert has_id_condition(field_cond & id_cond)
        assert has_id_condition(field_cond | id_cond)
        assert has_id_condition(~id_cond)
        assert has_id_condition(field_cond & (~id_cond | field_cond))

    def test_plain_queries_not_detected(self) -> None:
        """Ordinary field queries are not id conditions."""
        assert not has_id_condition(where("id") == 1)
        assert not has_id_condition(where("name") == "Alice")

    def test_non_cacheable_composition_undetectable(self) -> None:
        """Hash-erased compositions fall through (raise at eval).

        ``.test(lambda)`` queries are cacheable (their hashval
        includes the function object) — only a hand-built
        ``QueryInstance(test, None)`` erases the hash tree, making
        the id condition undetectable. It still fails loudly when
        evaluated.
        """
        opaque = QueryInstance(lambda _: True, None)
        cond = (DocIdQuery() == 1) & opaque
        assert not has_id_condition(cond)
        with pytest.raises(DocumentIDConditionError, match="doc_id"):
            cond({"name": "Alice"})
