# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for class-level field queries and the q() helper."""

from __future__ import annotations

import pytest

from pydantic import BaseModel
from tinydb import TinyDB
from tinydb.queries import Query, QueryInstance
from tinydb.storages import MemoryStorage

from tinydantic import TinydanticModel, q


class Address(BaseModel):
    """Nested pydantic model for nested-query tests."""

    city: str


@pytest.fixture
def memory_db() -> TinyDB:
    """Return an isolated in-memory TinyDB instance."""
    return TinyDB(storage=MemoryStorage)


class TestFieldQueries:
    """Class-level attribute access produces TinyDB queries."""

    def test_field_comparison_is_a_query_instance(self, memory_db: TinyDB):
        """Model.field == value produces a TinyDB QueryInstance."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        condition = User.name == "Alice"
        assert isinstance(condition, QueryInstance)

    def test_query_round_trip(self, memory_db: TinyDB):
        """A field query finds an inserted document."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        User(name="Alice").insert()
        # A raw field comparison is a Query at runtime but types as
        # bool (this is why q() exists); get() also returns a union.
        result = User.get(User.name == "Alice")  # type: ignore[call-overload]
        assert result is not None
        assert result.name == "Alice"  # type: ignore[union-attr]

    def test_nested_field_query(self, memory_db: TinyDB):
        """Attribute chaining reaches into nested documents."""

        class User(TinydanticModel, database=memory_db):
            """Test model with a nested model field."""

            name: str
            address: Address

        User(name="Alice", address=Address(city="Oakland")).insert()
        # A raw field comparison is a Query at runtime but types as
        # bool (this is why q() exists); get() also returns a union.
        result = User.get(User.address.city == "Oakland")  # type: ignore[call-overload]
        assert result is not None
        assert result.name == "Alice"  # type: ignore[union-attr]

    def test_non_field_attribute_raises(self, memory_db: TinyDB):
        """Unknown class attributes still raise AttributeError."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        with pytest.raises(AttributeError):
            _ = User.not_a_field


class TestQHelper:
    """The q() static-typing helper."""

    def test_q_returns_the_query(self, memory_db: TinyDB):
        """q() is an identity function for real queries."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        query = q(User.name)
        assert isinstance(query, Query)
        assert isinstance(q(User.name) == "Alice", QueryInstance)

    def test_q_accepts_a_field_name_string(self):
        """q('name') builds a query on that key, like where()."""
        query = q("name")
        assert isinstance(query, Query)
        assert isinstance(query == "Alice", QueryInstance)

    # The shadowed field is the point of this test; pydantic rightly
    # warns about it.
    @pytest.mark.filterwarnings(
        'ignore:Field name "search":UserWarning',
    )
    def test_q_string_reaches_a_shadowed_field(self, memory_db: TinyDB):
        """Fields that collide with methods stay queryable via q()."""

        class Command(TinydanticModel, database=memory_db):
            """Test model with a field shadowed by search()."""

            name: str
            search: str  # type: ignore[assignment]

        Command(name="find", search="fuzzy").insert()
        Command(name="grep", search="regex").insert()
        results = Command.search(q("search") == "fuzzy")  # type: ignore[operator]
        assert [command.name for command in results] == ["find"]

    def test_q_rejects_non_queries(self):
        """q() raises TypeError for non-Query, non-string values."""
        with pytest.raises(TypeError, match="Query"):
            q(42)
