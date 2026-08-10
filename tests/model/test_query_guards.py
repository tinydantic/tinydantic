# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the guards on boolean context, iteration, indexing."""

from __future__ import annotations

import functools
import operator

import pytest

from tinydb import TinyDB, where
from tinydb.queries import Query, QueryInstance
from tinydb.storages import MemoryStorage

from tinydantic import QueryTypeError, TinydanticModel, field, q


def _branch_on(cond: object) -> str:
    """Use a condition where a boolean belongs.

    The shape of the real mistake — an "if the user exists" guard —
    in a single statement, so ``pytest.raises`` can wrap it.
    """
    return "taken" if cond else "not taken"


_db = TinyDB(storage=MemoryStorage)


class User(TinydanticModel, database=_db):
    """Model under test.

    Declared at module level so mypy resolves ``User.name`` through
    the metaclass ``__getattr__`` (which types as ``Any``); a
    ``type[TinydanticModel]`` parameter would hide it.
    """

    name: str
    age: int
    tags: list[str] = []  # noqa: RUF012


@pytest.fixture(autouse=True)
def _populate() -> None:
    """Reset the table to two known documents per test."""
    User.truncate()
    User.insert_multiple(
        [
            User(name="Alice", age=30, tags=["admin"]),
            User(name="Bob", age=40, tags=["us"]),
        ],
    )


class TestBooleanContext:
    """Boolean context raises instead of being silently true."""

    def test_condition_is_not_a_boolean(self) -> None:
        """A bare condition refuses bool()."""
        with pytest.raises(QueryTypeError, match="no truth value"):
            bool(User.name == "Alice")

    def test_condition_that_would_not_match_also_raises(self) -> None:
        """The guard does not depend on stored data."""
        with pytest.raises(QueryTypeError):
            bool(User.name == "nobody")

    def test_if_statement_raises(self) -> None:
        """`if cond:` — the headline mistake — raises."""
        with pytest.raises(QueryTypeError, match="contains"):
            _branch_on(User.name == "Alice")

    def test_not_raises(self) -> None:
        """`not cond` raises rather than returning False."""
        with pytest.raises(QueryTypeError):
            _ = not (User.age > 30)

    def test_and_raises(self) -> None:
        """`and` raises rather than discarding the left operand."""
        with pytest.raises(QueryTypeError, match=r"& \| ~"):
            _ = (User.age > 30) and (User.name == "Alice")

    def test_or_raises(self) -> None:
        """`or` raises rather than discarding the right operand."""
        with pytest.raises(QueryTypeError):
            _ = (User.age > 30) or (User.name == "Alice")

    def test_builtin_all_raises(self) -> None:
        """all() over conditions raises rather than returning True."""
        conditions = [User.age > 30, User.name == "Alice"]
        with pytest.raises(QueryTypeError):
            all(conditions)

    def test_comprehension_filter_raises(self) -> None:
        """A class-level condition in a comprehension raises."""
        users = User.all()
        with pytest.raises(QueryTypeError):
            [u for u in users if User.age > 30]

    def test_composed_condition_raises(self) -> None:
        """`&` keeps the guard, so `if (a & b):` raises too."""
        composed = (User.age > 20) & (User.name == "Alice")
        with pytest.raises(QueryTypeError):
            bool(composed)

    def test_inverted_condition_raises(self) -> None:
        """`~` keeps the guard."""
        with pytest.raises(QueryTypeError):
            bool(~(User.name == "Alice"))

    def test_or_composed_condition_raises(self) -> None:
        """`|` keeps the guard."""
        composed = (User.age > 20) | (User.name == "Bob")
        with pytest.raises(QueryTypeError):
            bool(composed)

    def test_query_builder_is_not_a_boolean(self) -> None:
        """`bool(Model.field)` raises with builder-specific advice."""
        with pytest.raises(QueryTypeError, match="query builder"):
            bool(User.name)

    def test_id_condition_is_guarded(self) -> None:
        """DocIdCondition inherits the guard."""
        with pytest.raises(QueryTypeError):
            bool(User.id == 1)

    def test_field_helper_conditions_are_guarded(self) -> None:
        """Conditions from field() are guarded too."""
        with pytest.raises(QueryTypeError):
            bool(field(User, "name") == "Alice")

    def test_message_names_the_is_not_none_spelling(self) -> None:
        """The optional-condition idiom is given its fix."""
        with pytest.raises(
            QueryTypeError,
            match="cond is not None",
        ):
            bool(User.name == "Alice")


class TestIteration:
    """Iteration — and therefore `in` — raises."""

    def test_in_raises(self) -> None:
        """`x in Model.field` raises rather than returning True."""
        with pytest.raises(QueryTypeError, match="not iterable"):
            _ = "A" in User.name

    def test_in_on_list_field_raises(self) -> None:
        """List-field membership raises and names .any()."""
        with pytest.raises(QueryTypeError, match=r"\.any\("):
            _ = "admin" in User.tags

    def test_iteration_raises(self) -> None:
        """Explicit iteration raises rather than never ending."""
        with pytest.raises(QueryTypeError):
            list(User.name)


class TestPathIndexing:
    """Non-string path steps raise instead of matching nothing."""

    def test_integer_index_raises(self) -> None:
        """Positional indexing of a list field raises."""
        with pytest.raises(QueryTypeError, match="matches nothing"):
            _ = User.tags[0]

    def test_message_shows_the_offending_step(self) -> None:
        """The message quotes the step that was rejected."""
        with pytest.raises(QueryTypeError, match="got 0"):
            _ = User.tags[0]

    def test_string_key_still_works(self) -> None:
        """String keys are the supported form and are untouched."""
        assert isinstance(q(User.name)["nested"], Query)


class TestQueriesStillWork:
    """The guards change nothing about querying."""

    def test_search_by_condition(self) -> None:
        """A guarded condition still selects documents."""
        found = User.search(q(User.name) == "Alice")
        assert [u.name for u in found] == ["Alice"]

    def test_composition_still_works(self) -> None:
        """`&`, `|`, `~` still build working queries."""
        both = (q(User.age) > 20) & (q(User.name) == "Alice")
        assert [u.name for u in User.search(both)] == ["Alice"]
        either = (q(User.age) > 35) | (q(User.name) == "Alice")
        assert [u.name for u in User.search(either)] == [
            "Alice",
            "Bob",
        ]
        assert [u.name for u in User.search(~(q(User.age) > 35))] == ["Alice"]

    def test_reduce_over_conditions(self) -> None:
        """The documented replacement for all() works."""
        conditions = [q(User.age) > 20, q(User.name) == "Alice"]
        combined = functools.reduce(operator.and_, conditions)
        assert [u.name for u in User.search(combined)] == ["Alice"]

    def test_builder_methods_still_work(self) -> None:
        """TinyDB's own builders survive the overrides."""
        assert [u.name for u in User.search(q(User.name).search("Ali"))] == [
            "Alice"
        ]
        assert [u.name for u in User.search(q(User.name).matches("A.*"))] == [
            "Alice"
        ]
        assert [
            u.name
            for u in User.search(
                q(User.name).test(lambda v: "Ali" in v),
            )
        ] == ["Alice"]
        assert [
            u.name
            for u in User.search(
                q(User.name).one_of(["Alice", "Bob"]),
            )
        ] == ["Alice", "Bob"]
        assert [u.name for u in User.search(q(User.tags).any(["admin"]))] == [
            "Alice"
        ]
        assert [u.name for u in User.search(q(User.name).exists())] == [
            "Alice",
            "Bob",
        ]

    def test_nested_attribute_chaining_stays_guarded(self) -> None:
        """Chained access keeps the subclass, so guards persist."""
        with pytest.raises(QueryTypeError):
            bool(q(User.name).nested == "x")

    def test_id_queries_still_work(self) -> None:
        """Document-id conditions are unaffected."""
        found = User.get(q(User.id) == 1)
        assert found is not None
        assert found.name == "Alice"


class TestRawTinyDBCompatibility:
    """Guarded conditions stay interchangeable with TinyDB's."""

    def test_is_a_query_instance(self) -> None:
        """Isinstance checks against TinyDB's types still pass."""
        assert isinstance(User.name == "Alice", QueryInstance)
        assert isinstance(User.name, Query)

    def test_equal_to_the_raw_tinydb_condition(self) -> None:
        """Equality with an identical raw condition is preserved."""
        assert (User.name == "Alice") == (where("name") == "Alice")

    def test_hashes_like_the_raw_tinydb_condition(self) -> None:
        """The hashval is untouched, so the query cache still hits."""
        guarded = User.name == "Alice"
        assert hash(guarded) == hash(where("name") == "Alice")

    def test_stays_cacheable(self) -> None:
        """Retagging preserves TinyDB's cacheability flag."""
        assert (q(User.name) == "Alice").is_cacheable()
        composed = (q(User.age) > 20) & (q(User.name) == "Alice")
        assert composed.is_cacheable()

    def test_composes_with_a_raw_tinydb_condition(self) -> None:
        """Mixing guarded and raw conditions still queries."""
        mixed = (q(User.age) > 20) & (where("name") == "Alice")
        assert [u.name for u in User.search(mixed)] == ["Alice"]

    def test_q_returns_the_guarded_query_unchanged(self) -> None:
        """q() is still a cast — same object in, same object out."""
        expr = User.name
        assert q(expr) is expr
