# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for document-id query expressions and translation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydb import where
from tinydb.queries import QueryInstance

from tests.model.models import UserBase
from tinydantic import DocumentIDConditionError, q
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


class TestModelIdExpression:
    """Class-level Model.id returns the typed id query."""

    def test_model_id_is_doc_id_query(
        self,
        user_class: type[UserBase],
    ) -> None:
        """Model.id returns a DocIdQuery."""
        assert isinstance(user_class.id, DocIdQuery)

    def test_unbound_model_builds_conditions(self) -> None:
        """Building an id condition needs no bound database."""
        cond = UserBase.id == 1
        assert isinstance(cond, DocIdCondition)

    def test_q_passes_id_query_through(
        self,
        user_class: type[UserBase],
    ) -> None:
        """q(Model.id) passes through (DocIdQuery is a Query)."""
        assert isinstance(q(user_class.id), DocIdQuery)

    def test_other_fields_still_plain_queries(
        self,
        user_class: type[UserBase],
    ) -> None:
        """Non-id fields keep returning plain TinyDB queries."""
        cond = user_class.name == "Alice"
        assert not isinstance(user_class.name, DocIdQuery)
        assert not has_id_condition(cond)


@pytest.fixture
def users(user_class: type[UserBase]) -> type[UserBase]:
    """Return the bound user class with three users (ids 1-3)."""
    user_class.insert_multiple(
        [
            user_class(name="Alice", age=30),
            user_class(name="Bob", age=25),
            user_class(name="Carol", age=35),
        ],
    )
    return user_class


class TestIdConditionReads:
    """Id conditions work through every read method."""

    def test_get_by_id_equality(self, users: type[UserBase]) -> None:
        """get(Model.id == n) fetches by document id."""
        user = users.get(users.id == 2)  # type: ignore[call-overload]
        assert user is not None
        assert user.id == 2
        assert user.name == "Bob"

    def test_get_missing_id_returns_none(
        self,
        users: type[UserBase],
    ) -> None:
        """A get with an unknown id returns None."""
        assert users.get(q(users.id) == 999) is None

    @pytest.mark.parametrize(
        ("build", "expected_ids"),
        [
            (lambda cls: q(cls.id) != 2, [1, 3]),
            (lambda cls: q(cls.id) < 2, [1]),
            (lambda cls: q(cls.id) <= 2, [1, 2]),
            (lambda cls: q(cls.id) > 2, [3]),
            (lambda cls: q(cls.id) >= 2, [2, 3]),
            (lambda cls: q(cls.id).one_of([1, 3]), [1, 3]),
        ],
    )
    def test_search_by_id_comparisons(
        self,
        users: type[UserBase],
        build: Callable[[type[UserBase]], QueryInstance],
        expected_ids: list[int],
    ) -> None:
        """Every operator matches the right documents."""
        found = users.search(build(users))
        assert {user.id for user in found} == set(expected_ids)

    def test_search_composed_with_field_condition(
        self,
        users: type[UserBase],
    ) -> None:
        """Id conditions compose with field conditions."""
        found = users.search((q(users.id) != 2) & (q(users.age) >= 30))
        assert {user.id for user in found} == {1, 3}

    def test_search_id_condition_right_of_field(
        self,
        users: type[UserBase],
    ) -> None:
        """Composition works with the id condition on the right."""
        found = users.search(
            (where("name") == "Alice") | (q(users.id) == 3),
        )
        assert {user.id for user in found} == {1, 3}

    def test_search_inverted(self, users: type[UserBase]) -> None:
        """A negated id condition matches the complement."""
        found = users.search(~(q(users.id) == 2))
        assert {user.id for user in found} == {1, 3}

    def test_get_by_cond_and_get_or_raise(
        self,
        users: type[UserBase],
    ) -> None:
        """The get() delegates inherit translation."""
        by_cond = users.get_by_cond(q(users.id) == 3)
        assert by_cond is not None
        assert by_cond.name == "Carol"
        assert users.get_or_raise(q(users.id) == 1).name == "Alice"

    def test_contains(self, users: type[UserBase]) -> None:
        """contains() translates pure and composed id conditions."""
        assert users.contains(q(users.id) == 1)
        assert not users.contains(q(users.id) == 999)
        assert users.contains((q(users.id) > 1) & (q(users.age) == 35))

    def test_count(self, users: type[UserBase]) -> None:
        """count() translates pure and composed id conditions."""
        assert users.count(q(users.id) == 1) == 1
        assert users.count(q(users.id) == 999) == 0
        assert users.count(q(users.id) >= 2) == 2

    def test_raw_table_search_raises(
        self,
        users: type[UserBase],
    ) -> None:
        """Bypassing tinydantic raises instead of matching nothing."""
        with pytest.raises(DocumentIDConditionError, match="doc_id"):
            users.get_table().search(q(users.id) == 1)

    def test_q_string_id_still_queries_body(
        self,
        users: type[UserBase],
    ) -> None:
        """q('id') stays a raw body-key query (escape hatch)."""
        assert users.search(q("id") == 1) == []
