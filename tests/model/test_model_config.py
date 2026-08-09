# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for TinydanticModel configuration via class keywords."""

from __future__ import annotations

import pytest

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

import tinydantic as td

from tinydantic import (
    AmbiguousConfigError,
    DatabaseNotBoundError,
    TinydanticModel,
)
from tinydantic._config import get_config_value


@pytest.fixture
def memory_db() -> TinyDB:
    """Return an isolated in-memory TinyDB instance."""
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
        """Tinydantic keys never enter model_config."""

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

        assert "tinydantic_" in User.model_config.get(
            "protected_namespaces", ()
        )

    def test_pydantic_default_namespaces_are_kept(self):
        """Reserving tinydantic_ does not drop pydantic's defaults.

        ``protected_namespaces`` replaces the inherited value rather
        than extending it, so tinydantic restates pydantic's default
        alongside its own prefix (see the Upstream Limitations page).
        Read the default from pydantic itself, so this fails loudly
        if a future release changes it.
        """
        from pydantic._internal._config import (  # noqa: PLC0415
            config_defaults,
        )

        default = config_defaults.get("protected_namespaces", ())
        reserved = TinydanticModel.model_config.get("protected_namespaces", ())
        assert set(default) <= set(reserved)

    def test_future_pydantic_method_name_warns(self, memory_db: TinyDB):
        """A model_dump_* field warns as it would on a BaseModel."""
        with pytest.warns(UserWarning, match="model_dump"):

            class Report(TinydanticModel, database=memory_db):
                """Test model naming a method pydantic may add."""

                model_dump_toml: str


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
    """Definition-time ambiguity detection."""

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
    """Error classes are importable from the package root."""
    assert issubclass(td.DatabaseNotBoundError, td.TinydanticError)
    assert issubclass(td.AmbiguousConfigError, td.TinydanticUserError)
    assert issubclass(td.DocumentNotFoundError, td.TinydanticError)
    assert issubclass(td.DocumentIDRequiredError, td.TinydanticError)


class TestValidateWrites:
    """The validate_writes configuration key."""

    def test_defaults_to_true(self, memory_db: TinyDB):
        """validate_writes resolves True when never set."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        assert get_config_value(User, "validate_writes", default=True) is True

    def test_class_kwarg_false(self, memory_db: TinyDB):
        """validate_writes=False is captured from class kwargs."""

        class User(
            TinydanticModel,
            database=memory_db,
            validate_writes=False,
        ):
            """Test model."""

            name: str

        assert get_config_value(User, "validate_writes", default=True) is False

    def test_inherited_via_mro(self, memory_db: TinyDB):
        """Subclasses inherit validate_writes via the MRO walk."""

        class Base(
            TinydanticModel,
            database=memory_db,
            validate_writes=False,
        ):
            """Test base model."""

            name: str

        class Child(Base):
            """Test child model."""

        assert (
            get_config_value(Child, "validate_writes", default=True) is False
        )

    def test_subclass_can_reenable(self, memory_db: TinyDB):
        """A subclass can turn validation back on."""

        class Base(
            TinydanticModel,
            database=memory_db,
            validate_writes=False,
        ):
            """Test base model."""

            name: str

        class Child(Base, validate_writes=True):
            """Test child model."""

        assert get_config_value(Child, "validate_writes", default=True) is True


class TestUnbind:
    """Late unbinding via Model.unbind()."""

    def test_unbind_database_detaches(self, memory_db: TinyDB):
        """unbind('database') detaches; get_database() raises."""

        class Late(TinydanticModel):
            """Test model bound and unbound."""

            name: str

        Late.bind(database=memory_db)
        assert Late.get_database() is memory_db
        Late.unbind("database")
        with pytest.raises(DatabaseNotBoundError):
            Late.get_database()

    def test_unbind_table_name_restores_derived(self, memory_db: TinyDB):
        """unbind('table_name') falls back to the snake_case name."""

        class AdminUser(
            TinydanticModel,
            database=memory_db,
            table_name="custom",
        ):
            """Test model with a custom table name."""

            name: str

        assert AdminUser.get_table().name == "custom"
        AdminUser.unbind("table_name")
        assert AdminUser.get_table().name == "admin_user"

    def test_unbind_all_keys(self, memory_db: TinyDB):
        """unbind() with no arguments clears every own key."""

        class Late(TinydanticModel):
            """Test model fully reset."""

            name: str

        Late.bind(database=memory_db, table_name="late_docs")
        Late.unbind()
        with pytest.raises(DatabaseNotBoundError):
            Late.get_database()
        assert get_config_value(Late, "table_name") is None

    def test_inherited_config_resurfaces(self, memory_db: TinyDB):
        """Unbinding an override re-exposes the inherited value."""

        class Base(TinydanticModel, database=memory_db):
            """Bound base model."""

            name: str

        other_db = TinyDB(storage=MemoryStorage)

        class Child(Base):
            """Subclass overriding then unbinding the database."""

        Child.bind(database=other_db)
        assert Child.get_database() is other_db
        Child.unbind("database")
        assert Child.get_database() is memory_db

    def test_unbind_subclass_leaves_parent_bound(self, memory_db: TinyDB):
        """unbind() on a subclass never affects the parent."""

        class Parent(TinydanticModel, database=memory_db):
            """Bound parent."""

            name: str

        class Sub(Parent):
            """Subclass that unbinds everything."""

        Sub.unbind()
        assert Parent.get_database() is memory_db

    def test_unknown_key_raises(self, memory_db: TinyDB):
        """An unknown key name raises ValueError naming valid keys."""

        class Late(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        with pytest.raises(
            ValueError,
            match=r"'not_a_config_key'.*'database'",
        ):
            Late.unbind("not_a_config_key")

    def test_unbind_never_set_key_is_noop(self, memory_db: TinyDB):
        """Unbinding a key the class never set changes nothing."""

        class Late(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        Late.unbind("table_name")
        assert Late.get_database() is memory_db


class TestBindFullCoverage:
    """bind() covers every config key."""

    def test_bind_validate_writes(self, memory_db: TinyDB):
        """bind(validate_writes=False) is stored and resolved."""

        class Late(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        Late.bind(validate_writes=False)
        assert get_config_value(Late, "validate_writes", default=True) is False

    def test_bind_shadowed_fields(self, memory_db: TinyDB):
        """bind(shadowed_fields=...) is stored and resolved."""

        class Late(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        Late.bind(shadowed_fields=("search",))
        assert get_config_value(Late, "shadowed_fields") == ("search",)
