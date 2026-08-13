# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for document-id query expressions and translation."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pydantic import ValidationError
from tinydb import where
from tinydb.queries import QueryInstance
from tinydb.table import Table

from tests.model.models import UserBase
from tinydantic import (
    DocumentIDConditionError,
    DocumentIDUpdateError,
    DocumentNotFoundError,
    QueryFieldError,
    TinydanticError,
    field,
    q,
)
from tinydantic._query import (
    DocIdCondition,
    DocIdQuery,
    has_id_condition,
    id_from_condition,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


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
    user_class.insert_many(
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
        user = users.get(q(users.id) == 2)
        assert user.id == 2
        assert user.name == "Bob"

    def test_get_or_none_missing_id_returns_none(
        self,
        users: type[UserBase],
    ) -> None:
        """get_or_none() with an unknown id returns None."""
        assert users.get_or_none(q(users.id) == 999) is None

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

    def test_get_by_condition(
        self,
        users: type[UserBase],
    ) -> None:
        """get() with an id condition inherits translation."""
        by_cond = users.get(q(users.id) == 3)
        assert by_cond is not None
        assert by_cond.name == "Carol"
        assert users.get(q(users.id) == 1).name == "Alice"

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

    def test_contains_and_count_do_not_validate(
        self,
        users: type[UserBase],
    ) -> None:
        """contains()/count() never validate documents into models.

        A schema-invalid raw document must not break them; search()
        by contrast validates and raises.
        """
        users.get_table().insert({"name": 123, "age": "not an int"})
        assert users.contains(q(users.id) > 3)
        assert users.count(q(users.id) > 1) == 3
        with pytest.raises(ValidationError):
            users.search(q(users.id) > 3)

    def test_get_validates_only_the_first_match(
        self,
        users: type[UserBase],
    ) -> None:
        """get() stops at the first match, like TinyDB's get().

        A schema-invalid document that matches the condition later
        in table order must not affect the result — only the
        returned document is validated (search(), by contrast,
        validates every match).
        """
        users.get_table().insert({"name": 123, "age": "not an int"})
        found = users.get(q(users.id) >= 1)
        assert found is not None
        assert found.id == 1
        with pytest.raises(ValidationError):
            users.search(q(users.id) >= 1)

    def test_raw_table_search_raises(
        self,
        users: type[UserBase],
    ) -> None:
        """Bypassing tinydantic raises instead of matching nothing."""
        with pytest.raises(DocumentIDConditionError, match="doc_id"):
            users.get_table().search(q(users.id) == 1)

    def test_named_id_field_is_refused(
        self,
        users: type[UserBase],
    ) -> None:
        """field(Model, 'id') raises instead of matching nothing.

        'id' is in model_fields but maps to doc_id, so a body query
        on it would silently return [] forever.
        """
        with pytest.raises(QueryFieldError, match="doc_id"):
            field(users, "id")

    def test_raw_id_key_query_still_matches_nothing(
        self,
        users: type[UserBase],
    ) -> None:
        """The raw path is unvalidated, so it stays silently empty.

        Pins why field() refuses 'id': where('id') is legal TinyDB
        and returns nothing, since tinydantic never writes that key.
        """
        assert users.search(where("id") == 1) == []


class TestIdConditionWrites:
    """Id conditions work through the write methods."""

    def test_update_by_id_condition(self, users: type[UserBase]) -> None:
        """update() resolves id conditions to doc_ids."""
        updated = users.update({"age": 26}, q(users.id) == 2)
        assert updated == [2]
        doc = users.get_table().get(doc_id=2)
        assert isinstance(doc, dict)
        assert doc["age"] == 26

    def test_update_by_composed_condition(
        self,
        users: type[UserBase],
    ) -> None:
        """Composed id conditions update the right documents."""
        updated = users.update(
            {"age": 0},
            (q(users.id) != 2) & (q(users.age) >= 30),
        )
        assert sorted(updated) == [1, 3]

    def test_update_no_match_returns_empty(
        self,
        users: type[UserBase],
    ) -> None:
        """No matching ids: no write, empty result."""
        updated = users.update({"age": 99}, q(users.id) == 999)
        assert updated == []
        assert users.count() == 3

    def test_id_condition_filters_while_by_ids_asserts(
        self,
        users: type[UserBase],
    ) -> None:
        """update_by_ids() asserts, where an id condition filters."""
        assert users.update({"age": 1}, q(users.id).one_of([2, 999])) == [2]
        with pytest.raises(DocumentNotFoundError, match="id 999"):
            users.update_by_ids({"age": 5}, [3, 999])
        assert [user.age for user in users.all()] == [30, 1, 35]

    def test_remove_by_id_condition(self, users: type[UserBase]) -> None:
        """remove() resolves id conditions to doc_ids."""
        removed = users.remove(q(users.id).one_of([1, 3]))
        assert removed == [1, 3]
        assert {user.id for user in users.all()} == {2}

    def test_remove_no_match_returns_empty(
        self,
        users: type[UserBase],
    ) -> None:
        """No matching ids: nothing removed."""
        removed = users.remove(q(users.id) == 999)
        assert removed == []
        assert users.count() == 3

    def test_upsert_updates_matching_id(
        self,
        users: type[UserBase],
    ) -> None:
        """upsert() with a matching id condition updates."""
        document = users(name="Bobby", age=27)
        ids = users.upsert(document, q(users.id) == 2)
        assert ids == [2]
        assert document.id == 2
        doc = users.get_table().get(doc_id=2)
        assert isinstance(doc, dict)
        assert doc["name"] == "Bobby"
        assert users.count() == 3

    def test_upsert_inserts_when_no_match(
        self,
        users: type[UserBase],
    ) -> None:
        """upsert() with no matching id inserts a new document."""
        document = users(name="Dave", age=40)
        ids = users.upsert(document, q(users.id) == 999)
        assert ids == [4]
        assert document.id == 4
        assert users.count() == 4

    def test_update_multiple_by_id_condition(
        self,
        users: type[UserBase],
    ) -> None:
        """update_many() applies id-condition pairs in a batch."""
        ids = users.update_many(
            [
                ({"age": 1}, q(users.id) == 1),
                ({"age": 2}, q(users.id).one_of([2, 3])),
            ],
        )
        assert sorted(ids) == [1, 2, 3]
        doc = users.get_table().get(doc_id=3)
        assert isinstance(doc, dict)
        assert doc["age"] == 2

    def test_update_multiple_mixed_pairs(
        self,
        users: type[UserBase],
    ) -> None:
        """Field-condition and id-condition pairs mix in one batch."""
        ids = users.update_many(
            [
                ({"age": 50}, where("name") == "Alice"),
                ({"age": 60}, (q(users.id) > 1) & (q(users.age) == 35)),
            ],
        )
        assert sorted(ids) == [1, 3]

    def test_update_multiple_overlapping_pairs(
        self,
        users: type[UserBase],
    ) -> None:
        """Overlapping pairs keep upstream batch semantics.

        One id per matching pair, in order, and later pairs see
        earlier pairs' mutations.
        """
        ids = users.update_many(
            [
                ({"age": 1}, q(users.id) == 2),
                ({"name": "Bobby"}, q(users.id) == 2),
            ],
        )
        assert ids == [2, 2]
        doc = users.get_table().get(doc_id=2)
        assert isinstance(doc, dict)
        assert doc["age"] == 1
        assert doc["name"] == "Bobby"

    def test_update_multiple_no_match_returns_empty(
        self,
        users: type[UserBase],
    ) -> None:
        """No matching ids: empty result, nothing changed."""
        result = users.update_many(
            [({"age": 9}, q(users.id) == 999)],
        )
        assert result == []
        assert users.count() == 3

    def test_update_multiple_raise_aborts_whole_batch(
        self,
        users: type[UserBase],
    ) -> None:
        """An exception mid-batch aborts before anything persists."""

        def boom(_doc: Mapping) -> None:
            """Fail mid-batch to test the abort guarantee."""
            msg = "boom"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="boom"):
            users.update_many(
                [
                    ({"age": 99}, q(users.id) == 1),
                    (boom, q(users.id) == 2),
                ],
            )
        doc = users.get_table().get(doc_id=1)
        assert isinstance(doc, dict)
        assert doc["age"] == 30

    def test_missing_private_api_raises(
        self,
        users: type[UserBase],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A TinyDB without _update_table fails loudly."""
        monkeypatch.delattr(Table, "_update_table")
        with pytest.raises(TinydanticError, match="_update_table"):
            users.update({"age": 1}, q(users.id) == 1)

    def test_update_mapping_id_key_raises(
        self,
        users: type[UserBase],
    ) -> None:
        """update() refuses to set the id field."""
        with pytest.raises(DocumentIDUpdateError, match="doc_id"):
            users.update({"id": 99}, where("name") == "Alice")
        doc = users.get_table().get(doc_id=1)
        assert isinstance(doc, dict)
        assert "id" not in doc

    def test_update_multiple_mapping_id_key_raises(
        self,
        users: type[UserBase],
    ) -> None:
        """update_many() mappings get the same id guard."""
        with pytest.raises(DocumentIDUpdateError, match="doc_id"):
            users.update_many(
                [({"id": 99}, where("name") == "Alice")],
            )

    def test_id_update_hint_names_a_live_selector(
        self,
        users: type[UserBase],
    ) -> None:
        """The hint names update_by_ids(), and it works.

        It used to name the ``doc_ids=`` parameter, removed this
        cycle in favor of ``update_by_ids()`` — advice pointing at
        an API that no longer exists.
        """
        with pytest.raises(DocumentIDUpdateError) as excinfo:
            users.update({"id": 99}, where("name") == "Alice")
        message = str(excinfo.value)

        assert "update_by_ids()" in message
        assert "doc_ids=" not in message

        assert users.update_by_ids({"age": 41}, [1]) == [1]


class TestIdFromCondition:
    """Tests for extracting a document id from a condition."""

    def test_bare_equality_yields_the_id(
        self,
        users: type[UserBase],
    ) -> None:
        """A bare ``id == n`` condition yields ``n``."""
        assert id_from_condition(q(users.id) == 3) == 3

    def test_other_operators_yield_none(
        self,
        users: type[UserBase],
    ) -> None:
        """Only equality names a single document."""
        assert id_from_condition(q(users.id) != 3) is None
        assert id_from_condition(q(users.id) > 3) is None
        assert id_from_condition(q(users.id).one_of([1, 2])) is None

    def test_composed_condition_yields_none(
        self,
        users: type[UserBase],
    ) -> None:
        """A composition may match more than the named id."""
        cond = (q(users.id) == 3) & (where("name") == "Alice")
        assert id_from_condition(cond) is None

    def test_field_condition_yields_none(self) -> None:
        """A body-field condition names no document id."""
        assert id_from_condition(where("name") == "Alice") is None
