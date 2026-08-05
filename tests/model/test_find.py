# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the fluent find() query API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pydantic import Field

from tinydantic import (
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
