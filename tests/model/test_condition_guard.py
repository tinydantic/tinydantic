# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the guard on values passed where a query belongs."""

from __future__ import annotations

import copy
import pickle

from typing import TYPE_CHECKING, Any

import pytest

from tinydb import Query, TinyDB, where
from tinydb.storages import MemoryStorage

from tinydantic import (
    QueryFieldError,
    QueryTypeError,
    SelectorError,
    TinydanticModel,
    q,
)

if TYPE_CHECKING:
    from collections.abc import Callable

_db = TinyDB(storage=MemoryStorage)


class User(TinydanticModel, database=_db, table_name="guard_users"):
    """Model under test, declared at module level like its sibling.

    Module scope keeps ``User.name`` resolving through the
    metaclass ``__getattr__`` for the type checkers.
    """

    name: str
    age: int


@pytest.fixture(autouse=True)
def _populated() -> Any:
    """Give each test one document, and clean up after it."""
    User.truncate()
    User.insert(User(name="Alice", age=30))
    yield
    User.truncate()


# Every value-shaped operand a user might pass by mistake. The
# empty table matters as much as the populated one: TinyDB calls a
# "condition" once per document, so on an empty table a string
# condition used to return [] rather than raising.
WRONG_KINDS: list[Any] = [
    "Alice",
    {"name": "Alice"},
    42,
    ["name", "Alice"],
    None,
    User.name,  # a builder: the comparison was forgotten
]


def _guarded_calls() -> dict[str, Callable[[Any], object]]:
    """Map each guarded method to a one-argument call."""
    return {
        "search": User.search,
        "get": User.get,
        "get_or_none": User.get_or_none,
        "contains": User.contains,
        "count": User.count,
        "remove": User.remove,
        "find": User.find,
        "update": lambda cond: User.update({"age": 1}, cond),
        "upsert": lambda cond: User.upsert(
            User(name="B", age=1),
            cond,
        ),
        "update_many": lambda cond: User.update_many(
            [({"age": 1}, cond)],
        ),
    }


class TestWrongKindsAreRefused:
    """A value where a query belongs raises, at the call."""

    @pytest.mark.parametrize("method", sorted(_guarded_calls()))
    @pytest.mark.parametrize("cond", WRONG_KINDS)
    def test_every_guarded_method_refuses(
        self,
        method: str,
        cond: Any,
    ) -> None:
        """Each method rejects each wrong operand kind."""
        with pytest.raises(QueryTypeError):
            _guarded_calls()[method](cond)

    @pytest.mark.parametrize("cond", WRONG_KINDS)
    def test_refused_on_an_empty_table_too(self, cond: Any) -> None:
        """The empty table is where the silent [] used to live."""
        User.truncate()
        with pytest.raises(QueryTypeError):
            User.search(cond)

    def test_the_error_is_a_type_error(self) -> None:
        """Python's convention for a wrong-kind argument."""
        with pytest.raises(TypeError):
            User.search("Alice")  # type: ignore[arg-type]


class TestMessagesNameTheFix:
    """Each operand kind gets the advice that fits it."""

    def test_dict_names_the_mongodb_translation(self) -> None:
        """The MongoDB habit is converted, not just rejected."""
        with pytest.raises(QueryTypeError, match="MongoDB"):
            User.search({"name": "Alice"})  # type: ignore[arg-type]

    def test_none_names_the_unset_variable(self) -> None:
        """None reads as a variable that was never set."""
        with pytest.raises(QueryTypeError, match="unexpectedly None"):
            User.search(None)  # type: ignore[arg-type]

    def test_builder_names_the_missing_comparison(self) -> None:
        """A forgotten == is the likeliest builder mistake."""
        with pytest.raises(QueryTypeError, match="query builder"):
            User.search(User.name)  # type: ignore[arg-type]

    def test_value_names_the_comparison_form(self) -> None:
        """A bare value is shown how to become a condition."""
        with pytest.raises(QueryTypeError, match=r"Model\.field"):
            User.search("Alice")  # type: ignore[arg-type]

    def test_the_method_is_named(self) -> None:
        """The message says which call was wrong."""
        with pytest.raises(QueryTypeError, match=r"count\(\)"):
            User.count("Alice")  # type: ignore[arg-type]


class TestValidConditionsStillPass:
    """The guard is duck-typed, so QueryLike keeps working."""

    def test_a_lambda_is_a_condition(self) -> None:
        """TinyDB's QueryLike is a protocol, not a class."""
        found = User.search(lambda doc: doc["name"] == "Alice")
        assert [u.name for u in found] == ["Alice"]

    def test_a_lambda_works_through_find(self) -> None:
        """Chains accept the same operands the verbs do."""
        assert User.find(lambda doc: doc["age"] > 5).count() == 1

    def test_a_raw_where_condition_is_a_condition(self) -> None:
        """Conditions built outside tinydantic are untouched."""
        assert User.count(where("name") == "Alice") == 1

    def test_a_raw_query_condition_is_a_condition(self) -> None:
        """Including ones built from tinydb.Query directly."""
        assert User.count(Query()["name"] == "Alice") == 1

    def test_a_model_condition_is_a_condition(self) -> None:
        """The ordinary spelling is unaffected."""
        assert User.count(q(User.name) == "Alice") == 1

    def test_omitted_conditions_still_mean_omitted(self) -> None:
        """The sentinel keeps absence distinct from None."""
        assert User.count() == 1
        # remove() keeps the sentinel so absence can point at the
        # whole-table spelling instead of failing as a bare
        # TypeError.
        with pytest.raises(SelectorError, match="truncate"):
            User.remove()
        with pytest.raises(SelectorError, match="update_all"):
            User.update({"age": 1})

    def test_reads_require_a_condition_positionally(self) -> None:
        """Reads take one selector, so absence is a TypeError."""
        with pytest.raises(TypeError, match="cond"):
            User.get()  # type: ignore[call-arg]
        with pytest.raises(TypeError, match="cond"):
            User.contains()  # type: ignore[call-arg]


class TestFindRaisesEagerly:
    """find() validates at the call, not at the terminal."""

    def test_find_raises_before_a_terminal_runs(self) -> None:
        """The error names the line that made the mistake."""
        with pytest.raises(QueryTypeError):
            User.find("Alice")  # type: ignore[call-overload]

    def test_find_with_no_argument_is_the_whole_table(self) -> None:
        """The whole-table spelling is unaffected by the guard."""
        assert User.find().count() == 1


class TestUnknownFieldOnTheClass:
    """A typo'd field name reports like field() does."""

    def test_unknown_field_raises_query_field_error(self) -> None:
        """The bare AttributeError named nothing useful."""
        with pytest.raises(QueryFieldError, match="nickname"):
            _ = User.nickname  # type: ignore[attr-defined]

    def test_the_message_lists_the_queryable_fields(self) -> None:
        """Same advice field() gives for the same mistake."""
        with pytest.raises(QueryFieldError, match=r"\['age', 'name'\]"):
            _ = User.nickname  # type: ignore[attr-defined]

    def test_it_is_still_an_attribute_error(self) -> None:
        """Attribute lookup must fail the way Python expects."""
        with pytest.raises(AttributeError):
            _ = User.nickname  # type: ignore[attr-defined]

    def test_hasattr_reports_false(self) -> None:
        """hasattr() swallows AttributeError and nothing else."""
        assert not hasattr(User, "nickname")

    def test_known_fields_still_build_queries(self) -> None:
        """The guard does not shadow the query sugar."""
        assert User.count(q(User.name) == "Alice") == 1


class TestIntrospectionSurvives:
    """The AttributeError base is load-bearing, not decoration."""

    def test_copy_and_deepcopy(self) -> None:
        """Copy probes double-underscore names via __getattr__."""
        user = User(name="Alice", age=30)
        assert copy.copy(user).name == "Alice"
        assert copy.deepcopy(user).name == "Alice"

    def test_pickle_round_trip(self) -> None:
        """Pickle probes __reduce_ex__, __getstate__, and friends."""
        user = User(name="Alice", age=30)
        assert pickle.loads(pickle.dumps(user)).name == "Alice"

    def test_pydantic_introspection(self) -> None:
        """Dumping and schema generation walk the class."""
        user = User(name="Alice", age=30)
        assert user.model_dump()["name"] == "Alice"
        assert "name" in User.model_json_schema()["properties"]

    def test_private_names_defer_to_pydantic(self) -> None:
        """Underscored probes get Python's own error, not ours."""
        with pytest.raises(AttributeError):
            _ = User._not_a_field  # noqa: SLF001  # type: ignore[attr-defined]
