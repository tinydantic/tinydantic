# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the fluent find() query API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import pytest

from pydantic import Field

from tinydantic import (
    DocumentNotFoundError,
    FindQuery,
    FindQueryError,
    SelectorError,
    ShadowedFieldError,
    SortFieldError,
    TinydanticModel,
    TinydanticUserError,
    q,
)

if TYPE_CHECKING:
    from tinydb import TinyDB


class User(TinydanticModel):
    """Unbound user model; tests bind per-database subclasses."""

    name: str
    age: int


@pytest.fixture
def user_class(db: TinyDB) -> type[User]:
    """Return a User subclass bound to a fresh database."""

    class BoundUser(User, database=db, table_name="users"):
        """User bound to the test database."""

    return BoundUser


class TestErrorHierarchy:
    """FindQueryError and SortFieldError join the curated surface."""

    def test_find_query_error_is_user_error_and_value_error(
        self,
    ) -> None:
        """FindQueryError subclasses TinydanticUserError+ValueError."""
        assert issubclass(FindQueryError, TinydanticUserError)
        assert issubclass(FindQueryError, ValueError)

    def test_sort_field_error_is_find_query_error(self) -> None:
        """SortFieldError subclasses FindQueryError."""
        assert issubclass(SortFieldError, FindQueryError)


class TestFindConstruction:
    """find() builds a lazy, immutable FindQuery."""

    def test_find_returns_find_query(self, user_class: type[User]) -> None:
        """find() with and without cond returns a FindQuery."""
        assert isinstance(user_class.find(), FindQuery)
        assert isinstance(user_class.find(q("age") >= 18), FindQuery)

    def test_find_none_raises_selector_error(
        self, user_class: type[User]
    ) -> None:
        """A None condition value is refused at construction."""
        with pytest.raises(SelectorError, match="no argument"):
            user_class.find(None)  # type: ignore[call-overload]

    def test_find_performs_no_io(self, db: TinyDB) -> None:
        """Building a chain never touches the database."""

        class Untouched(User, database=db, table_name="untouched"):
            """Bound model whose table must stay untouched."""

        Untouched.find(q("age") >= 18)
        assert "untouched" not in db.tables()

    def test_repr_shows_clauses(self, user_class: type[User]) -> None:
        """repr() names the model and shows the clause set."""
        text = repr(user_class.find())
        assert "BoundUser" in text
        assert "cond=" in text
        assert "skip=" in text


class TestModifiers:
    """Modifier validation, immutability, and the once-rule."""

    def test_modifiers_return_new_chains(self, user_class: type[User]) -> None:
        """Each modifier leaves the receiver untouched."""
        base = user_class.find()
        sorted_chain = base.sort("name")
        assert sorted_chain is not base
        # The base can still accept its own sort: it was never
        # mutated by the first call.
        assert base.sort("age") is not sorted_chain

    def test_repeated_sort_raises(self, user_class: type[User]) -> None:
        """A second sort() raises; message teaches one-call form."""
        chain = user_class.find().sort("name")
        with pytest.raises(FindQueryError, match="once"):
            chain.sort("age")

    def test_repeated_skip_and_limit_raise(
        self, user_class: type[User]
    ) -> None:
        """skip()/limit() follow the same once-rule as sort()."""
        with pytest.raises(FindQueryError, match="once"):
            user_class.find().skip(1).skip(2)
        with pytest.raises(FindQueryError, match="once"):
            user_class.find().limit(1).limit(2)

    def test_unknown_sort_field_raises_eagerly(
        self, user_class: type[User]
    ) -> None:
        """A wrong field name fails at sort(), not at all()."""
        with pytest.raises(SortFieldError, match="shoe_size"):
            user_class.find().sort("shoe_size")

    def test_alias_is_not_a_sort_key(self, db: TinyDB) -> None:
        """Sort keys are attribute names, not storage aliases."""

        class Aliased(TinydanticModel, database=db, table_name="aliased"):
            """Model with an aliased field."""

            full_name: str = Field(alias="fullName")

        Aliased.find().sort("full_name")  # attribute name: fine
        with pytest.raises(SortFieldError, match="fullName"):
            Aliased.find().sort("fullName")

    def test_descending_prefix_parses(self, user_class: type[User]) -> None:
        """A - prefix is accepted; a bare - is refused."""
        user_class.find().sort("-age", "name")
        with pytest.raises(SortFieldError):
            user_class.find().sort("-")

    def test_mixed_sort_forms_raise(self, user_class: type[User]) -> None:
        """Field names cannot combine with key= or reverse=."""
        with pytest.raises(FindQueryError, match="key="):
            user_class.find().sort("name", key=lambda u: u.age)
        with pytest.raises(FindQueryError, match="key="):
            user_class.find().sort("name", reverse=True)

    def test_sort_without_arguments_raises_type_error(
        self, user_class: type[User]
    ) -> None:
        """sort() with nothing to sort by is a TypeError."""
        with pytest.raises(TypeError, match="sort"):
            user_class.find().sort()

    def test_skip_limit_operand_validation(
        self, user_class: type[User]
    ) -> None:
        """skip/limit require a non-negative non-bool int."""
        find = user_class.find()
        for bad in (-1, True, 1.5, "3", None):
            with pytest.raises(FindQueryError):
                find.skip(bad)  # type: ignore[arg-type]
            with pytest.raises(FindQueryError):
                find.limit(bad)  # type: ignore[arg-type]
        find.skip(0)  # legal no-op
        find.limit(0)  # legal empty window


@pytest.fixture
def seeded(user_class: type[User]) -> type[User]:
    """Insert a small diverse dataset and return the class.

    Ids are 1..5 in insertion order: bob/30, alice/25, carol/30,
    dave/25, erin/40.
    """
    for name, age in [
        ("bob", 30),
        ("alice", 25),
        ("carol", 30),
        ("dave", 25),
        ("erin", 40),
    ]:
        user_class(name=name, age=age).insert()
    return user_class


class TestReadTerminals:
    """Read terminals and the fixed pipeline."""

    def test_all_matches_search(self, seeded: type[User]) -> None:
        """find(cond).all() equals search(cond)."""
        cond = q("age") >= 30
        assert seeded.find(cond).all() == seeded.search(cond)

    def test_find_no_args_is_whole_table(self, seeded: type[User]) -> None:
        """find() with no condition reads every document."""
        assert seeded.find().count() == 5

    def test_sort_ascending_and_descending(self, seeded: type[User]) -> None:
        """Single-key sorts order by field value."""
        names = [u.name for u in seeded.find().sort("name")]
        assert names == sorted(names)
        ages = [u.age for u in seeded.find().sort("-age")]
        assert ages == sorted(ages, reverse=True)

    def test_multi_key_mixed_directions(self, seeded: type[User]) -> None:
        """Left-to-right significance with per-key direction."""
        got = [(u.age, u.name) for u in seeded.find().sort("age", "-name")]
        assert got == [
            (25, "dave"),
            (25, "alice"),
            (30, "carol"),
            (30, "bob"),
            (40, "erin"),
        ]

    def test_ties_keep_doc_id_order(self, seeded: type[User]) -> None:
        """Equal keys come out in stored (doc id) order."""
        ids = [u.id for u in seeded.find().sort("age")]
        # ages: alice(2)=25, dave(4)=25, bob(1)=30, carol(3)=30,
        # erin(5)=40 — ties in doc-id order via sort stability.
        assert ids == [2, 4, 1, 3, 5]

    def test_key_callable_with_reverse(self, seeded: type[User]) -> None:
        """The key= escape hatch sorts by arbitrary callables."""
        names = [
            u.name
            for u in seeded.find().sort(
                key=lambda u: (u.age, u.name), reverse=True
            )
        ]
        assert names[0] == "erin"

    def test_pipeline_order_is_fixed(self, seeded: type[User]) -> None:
        """limit-then-sort spelling equals sort-then-limit."""
        a = seeded.find().sort("-age").limit(2).all()
        b = seeded.find().limit(2).sort("-age").all()
        assert a == b
        assert [u.name for u in a] == ["erin", "bob"]

    def test_window_slicing(self, seeded: type[User]) -> None:
        """skip/limit slice the sorted result."""
        window = seeded.find().sort("name").skip(1).limit(2)
        assert [u.name for u in window] == ["bob", "carol"]
        assert seeded.find().limit(0).all() == []

    def test_first_and_first_or_raise(self, seeded: type[User]) -> None:
        """first() is all()[0]-or-None; strict form raises."""
        oldest = seeded.find().sort("-age").first()
        assert oldest is not None
        assert oldest.name == "erin"
        empty = seeded.find(q("age") > 200)
        assert empty.first() is None
        with pytest.raises(DocumentNotFoundError):
            empty.first_or_raise()
        # The window applies before first: an empty page raises.
        with pytest.raises(DocumentNotFoundError):
            seeded.find().skip(30).first_or_raise()

    def test_terminal_invariants(self, seeded: type[User]) -> None:
        """first/count/exists agree with all() on every chain."""
        chains = [
            seeded.find(),
            seeded.find(q("age") >= 30),
            seeded.find(q("age") > 200),
            seeded.find().sort("-name").skip(1),
            seeded.find(q("age") == 25).sort("name").limit(1),
            seeded.find().skip(4).limit(3),
        ]
        for chain in chains:
            everything = chain.all()
            assert chain.count() == len(everything)
            assert chain.exists() == bool(everything)
            expected = everything[0] if everything else None
            assert chain.first() == expected
            assert list(chain) == everything

    def test_execution_is_fresh_not_cached(self, seeded: type[User]) -> None:
        """A reused chain sees writes made after it was built."""
        chain = seeded.find(q("age") >= 30)
        assert chain.count() == 3
        seeded(name="frank", age=50).insert()
        assert chain.count() == 4

    def test_datetime_fields_sort_chronologically(self, db: TinyDB) -> None:
        """Sorting uses validated values, not stored strings."""

        class Event(TinydanticModel, database=db, table_name="events"):
            """Event with a real datetime field."""

            at: datetime

        early = datetime(2026, 1, 2, tzinfo=timezone.utc)
        late = datetime(2026, 11, 1, tzinfo=timezone.utc)
        mid = datetime(2026, 3, 5, tzinfo=timezone.utc)
        for at in (late, early, mid):
            Event(at=at).insert()
        got = [e.at for e in Event.find().sort("at")]
        assert got == [early, mid, late]

    def test_none_comparison_propagates_type_error(self, db: TinyDB) -> None:
        """Optional-field Nones raise Python's TypeError."""

        class Score(TinydanticModel, database=db, table_name="scores"):
            """Score with an optional value."""

            value: int | None = None

        Score(value=3).insert()
        Score(value=None).insert()
        with pytest.raises(TypeError):
            Score.find().sort("value").all()

    def test_id_condition_chains(self, seeded: type[User]) -> None:
        """Model.id conditions work through the chain."""
        second = seeded.find(seeded.id == 2).first()
        assert second is not None
        assert second.name == "alice"
        ids = [u.id for u in seeded.find(seeded.id.one_of([1, 3])).sort("-id")]
        assert ids == [3, 1]


class TestBooleanContext:
    """A chain refuses truthiness instead of lying."""

    def test_bool_raises_find_query_error(
        self, user_class: type[User]
    ) -> None:
        """If User.find(...) is refused with the fix named."""
        with pytest.raises(FindQueryError, match="exists"):
            bool(user_class.find())

    def test_len_is_unsupported(self, user_class: type[User]) -> None:
        """len() fails naturally; count() is the spelling."""
        with pytest.raises(TypeError):
            len(user_class.find())  # type: ignore[arg-type]


class TestFindReservedWord:
    """find is a reserved word on the model namespace."""

    @pytest.mark.filterwarnings(
        "ignore:Field name .* shadows an attribute:UserWarning",
    )
    def test_field_named_find_raises_shadowed_field_error(
        self,
    ) -> None:
        """A model field named find is refused at definition."""
        with pytest.raises(ShadowedFieldError, match="find"):

            class Bad(TinydanticModel):
                """Model illegally naming a field find."""

                find: str  # type: ignore[assignment]
