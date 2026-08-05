# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the fluent find() query API."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

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
