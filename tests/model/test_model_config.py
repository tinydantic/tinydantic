# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for TinydanticModel configuration via class keywords."""

from __future__ import annotations

import pytest

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

import tinydantic as td

from tinydantic import TinydanticModel
from tinydantic.errors import AmbiguousConfigError, DatabaseNotBoundError


@pytest.fixture
def memory_db() -> TinyDB:
    """An isolated in-memory TinyDB instance."""
    return TinyDB(storage=MemoryStorage)


class TestClassKwargsConfig:
    """Configuration via class keyword arguments."""

    def test_database_and_table_name(self, memory_db: TinyDB):
        """Both kwargs are stored and used."""

        class User(TinydanticModel, database=memory_db, table_name="users"):
            """Test model."""

            name: str

        assert User.get_database() is memory_db
        assert User.get_table().name == "users"

    def test_derived_table_name_is_snake_case(self, memory_db: TinyDB):
        """Without table_name, the snake_case class name is used."""

        class AdminUser(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        assert AdminUser.get_table().name == "admin_user"

    def test_config_is_inherited(self, memory_db: TinyDB):
        """Subclasses inherit config from their parents per key."""

        class Base(TinydanticModel, database=memory_db, table_name="base"):
            """Test model."""

            name: str

        class Child(Base, table_name="children"):
            """Overrides only the table name."""

        assert Child.get_database() is memory_db
        assert Child.get_table().name == "children"
        assert Base.get_table().name == "base"

    def test_config_does_not_pollute_model_config(self, memory_db: TinyDB):
        """Spec 3.2: tinydantic keys never enter model_config."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        assert "database" not in User.model_config
        assert "table_name" not in User.model_config

    def test_tinydantic_namespace_is_protected(self, memory_db: TinyDB):
        """model_config reserves the tinydantic_ prefix."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        assert "tinydantic_" in User.model_config["protected_namespaces"]


class TestUnboundModel:
    """Behavior of models with no database anywhere."""

    def test_get_database_raises(self):
        """get_database raises a helpful error when unbound."""

        class Loose(TinydanticModel):
            """Test model with no database."""

            name: str

        with pytest.raises(DatabaseNotBoundError, match="Loose"):
            Loose.get_database()

    def test_insert_raises(self):
        """Table operations raise when unbound."""

        class Loose(TinydanticModel):
            """Test model with no database."""

            name: str

        with pytest.raises(DatabaseNotBoundError):
            Loose(name="Alice").insert()


class TestBind:
    """Late binding via Model.bind()."""

    def test_bind_database(self, memory_db: TinyDB):
        """bind() attaches a database after class definition."""

        class Late(TinydanticModel):
            """Test model bound after definition."""

            name: str

        Late.bind(database=memory_db)
        assert Late.get_database() is memory_db
        inserted = Late(name="Alice").insert()
        assert inserted.id == 1

    def test_bind_does_not_affect_parent(self, memory_db: TinyDB):
        """bind() on a subclass leaves the parent unbound."""

        class Parent(TinydanticModel):
            """Unbound parent."""

            name: str

        class Sub(Parent):
            """Subclass bound late."""

        Sub.bind(database=memory_db, table_name="subs")
        assert Sub.get_table().name == "subs"
        with pytest.raises(DatabaseNotBoundError):
            Parent.get_database()


class TestAmbiguity:
    """Definition-time ambiguity detection (spec 3.2)."""

    def test_conflicting_unrelated_bases_raise(self, memory_db: TinyDB):
        """A diamond over two differently-bound bases is an error."""
        other_db = TinyDB(storage=MemoryStorage)

        class A(TinydanticModel, database=memory_db):
            """First bound base."""

            name: str

        class B(TinydanticModel, database=other_db):
            """Second bound base, different database."""

            email: str

        with pytest.raises(AmbiguousConfigError, match="database"):

            class C(A, B):
                """Ambiguously bound diamond."""

    def test_explicit_kwarg_resolves_conflict(self, memory_db: TinyDB):
        """Setting database explicitly on the diamond is fine."""
        other_db = TinyDB(storage=MemoryStorage)

        class A(TinydanticModel, database=memory_db):
            """First bound base."""

            name: str

        class B(TinydanticModel, database=other_db):
            """Second bound base."""

            email: str

        class C(A, B, database=memory_db):
            """Explicitly resolved diamond."""

        assert C.get_database() is memory_db


def test_top_level_error_exports():
    """Error classes are importable from the package root (spec 6)."""
    assert issubclass(td.DatabaseNotBoundError, td.TinydanticError)
    assert issubclass(td.AmbiguousConfigError, td.TinydanticUserError)
    assert issubclass(td.DocumentNotFoundError, td.TinydanticError)
    assert issubclass(td.DocumentIDRequiredError, td.TinydanticError)
