# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for class-level field queries and the q() helper."""

from __future__ import annotations

import pytest

from pydantic import (
    BaseModel,
    ConfigDict,
    ValidationError,
    computed_field,
)
from pydantic.alias_generators import to_camel
from tinydb import TinyDB, where
from tinydb.queries import Query, QueryInstance
from tinydb.storages import MemoryStorage

from tinydantic import QueryFieldError, TinydanticModel, field, q


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


class TestComputedFieldQueries:
    """Class-level access to computed fields builds queries."""

    def test_comparison_is_a_query_instance(self, memory_db: TinyDB):
        """Model.computed == value produces a QueryInstance."""

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        condition = User.shout == "ALICE"
        assert isinstance(condition, QueryInstance)

    def test_query_round_trip(self, memory_db: TinyDB):
        """A computed-field query finds an inserted document."""

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        User(name="alice").insert()
        results = User.search(User.shout == "ALICE")  # type: ignore[arg-type]
        assert [user.name for user in results] == ["alice"]

    def test_matches_the_field_helper_query(self, memory_db: TinyDB):
        """Every spelling builds the same query on the same key.

        Comparing the queries themselves would prove nothing —
        ``Query.__eq__`` builds a condition, and every condition is
        truthy. The built conditions are what compare and hash.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        built = User.shout == "ALICE"
        via_field = field(User, "shout") == "ALICE"
        raw = where("shout") == "ALICE"
        assert built == via_field
        assert built == raw
        assert hash(built) == hash(raw)

    def test_instance_access_returns_the_value(self, memory_db: TinyDB):
        """user.computed still computes, untouched by the query."""

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        value = User(name="alice").shout
        assert isinstance(value, str)
        assert value == "ALICE"

    def test_computed_field_is_still_serialized(self, memory_db: TinyDB):
        """Wrapping the property leaves storage output intact."""

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        user = User(name="alice")
        assert user.model_dump()["shout"] == "ALICE"
        user.insert()
        assert memory_db.table("user").all()[0]["shout"] == "ALICE"

    def test_computed_field_is_still_read_only(self, memory_db: TinyDB):
        """Assignment raises the property's own AttributeError.

        A bare ``__get__`` wrapper is a *non-data* descriptor, which
        sends assignment down pydantic's fallback path and reports
        "object has no attribute 'shout'" — untrue and unhelpful.
        Delegating ``__set__`` keeps the property's own message.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        user = User(name="alice")
        with pytest.raises(AttributeError, match="can't set attribute"):
            user.shout = "HACKED"  # type: ignore[misc]

    def test_computed_field_setter_still_runs(self, memory_db: TinyDB):
        """A settable computed field keeps its setter.

        The assignment route delegates to the property rather than
        refusing outright, so pydantic's support for computed fields
        that *do* have a setter survives.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with a settable computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

            @shout.setter
            def shout(self, value: str) -> None:
                """Set the name from an upper-case value."""
                self.name = value.lower()

        user = User(name="alice")
        user.shout = "BOB"
        assert user.name == "bob"

    def test_frozen_model_reports_the_frozen_error(self, memory_db: TinyDB):
        """Frozen models are left to pydantic's own guard.

        "Instance is frozen" is the right answer for every attribute
        of a frozen model, computed or not, so the assignment route
        is deliberately not installed there.
        """

        class User(TinydanticModel, database=memory_db):
            """Frozen test model with a computed field."""

            model_config = ConfigDict(frozen=True)

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        user = User(name="alice")
        with pytest.raises(ValidationError, match="frozen"):
            user.shout = "HACKED"  # type: ignore[misc]

    def test_inherited_computed_field_is_queryable(self, memory_db: TinyDB):
        """A subclass reports the same key as its base."""

        class Base(TinydanticModel, database=memory_db):
            """Base model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        class Child(Base, table_name="child"):
            """Subclass inheriting the computed field."""

            rank: int = 0

        assert q(Child.shout) == where("shout")
        value = Child(name="bob").shout
        assert isinstance(value, str)
        assert value == "BOB"

    def test_inherited_computed_field_is_read_only(self, memory_db: TinyDB):
        """A subclass routes assignment to the inherited property.

        The subclass declares no property of its own, so its
        descriptor has to be resolved from the base class — a
        subclass that looked only at its own namespace would fall
        through to pydantic and report the field as unknown.
        """

        class Base(TinydanticModel, database=memory_db):
            """Base model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        class Child(Base, table_name="child"):
            """Subclass inheriting the computed field."""

            rank: int = 0

        with pytest.raises(AttributeError, match="can't set attribute"):
            Child(name="bob").shout = "HACKED"  # type: ignore[misc]

    def test_property_docstring_survives_wrapping(self, memory_db: TinyDB):
        """The descriptor carries the property's docstring.

        Class access no longer returns the property, so dynamic
        introspection (help(), runtime doc tooling) reads the
        descriptor instead — it has to carry the documentation.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        descriptor = User.__dict__["shout"]
        assert descriptor.__doc__ == "Return the name in upper case."

    def test_plain_property_is_not_queryable(self, memory_db: TinyDB):
        """An ordinary property is not stored, so it stays a property.

        Only ``@computed_field`` properties are serialized and
        therefore reachable in storage; wrapping the rest would
        promise queries that can never match.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with an ordinary property."""

            name: str

            @property
            def title(self) -> str:
                """Return the name in title case."""
                return self.name.title()

        assert isinstance(User.__dict__["title"], property)
        assert User(name="alice").title == "Alice"


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

    def test_q_rejects_a_field_name_string(self):
        """q() is a cast, not a constructor: strings are refused.

        A string cannot be told apart from an instance attribute
        that happens to hold one, so accepting either makes the
        other silently wrong. field() is the named-field form.
        """
        with pytest.raises(TypeError, match="field\\(Model, 'name'\\)"):
            q("name")

    def test_q_rejects_an_instance_attribute(self, memory_db: TinyDB):
        """q(user.name) raises instead of querying the value.

        The regression this split exists for: a str-valued instance
        attribute used to reach the string branch and silently build
        a query on a document key named after the *value*.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        user = User(name="Alice")
        with pytest.raises(TypeError, match="'str'"):
            q(user.name)

    def test_q_is_a_runtime_no_op(self, memory_db: TinyDB):
        """Wrapping a field changes nothing about the query.

        The docs promise that skipping q() costs nothing, so the two
        spellings must stay indistinguishable — down to the hash,
        which is what TinyDB's query cache keys on.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        expr = User.name
        assert q(expr) is expr

        bare = User.name == "Alice"
        wrapped = q(User.name) == "Alice"
        assert bare == wrapped
        assert hash(bare) == hash(wrapped)

    # The shadowed field is the point of this test; pydantic rightly
    # warns about it.
    @pytest.mark.filterwarnings(
        'ignore:Field name "search":UserWarning',
    )
    def test_q_rejects_a_shadowed_method(self, memory_db: TinyDB):
        """q() refuses the one silently-wrong query expression."""

        class Command(
            TinydanticModel,
            database=memory_db,
            shadowed_fields=("search",),
        ):
            """Test model with a field shadowed by search()."""

            name: str
            search: str  # type: ignore[assignment]

        # Class access finds the method, so the comparison is a plain
        # False rather than a condition — q() turns that into a raise.
        assert (Command.search == "fuzzy") is False
        with pytest.raises(TypeError) as excinfo:
            q(Command.search)
        # The method knows both its own name and its owning class, so
        # the advice can be the exact call the user needs to make.
        assert "field(Command, 'search')" in str(excinfo.value)
        assert "on an instance" not in str(excinfo.value)

    def test_q_advises_computed_field_for_a_plain_property(
        self,
        memory_db: TinyDB,
    ):
        """A plain property is told how to become queryable.

        Computed fields resolve to a Query and never reach the hint,
        so a property arriving there is necessarily the kind that is
        never stored: no document key exists for it to match.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with an ordinary property."""

            name: str

            @property
            def slug(self) -> str:
                """Return the name in lower case."""
                return self.name.lower()

        with pytest.raises(TypeError) as excinfo:
            q(User.slug)
        message = str(excinfo.value)
        assert "computed_field" in message
        assert "'slug'" in message
        assert "on an instance" not in message

    def test_q_rejects_non_queries(self):
        """q() raises TypeError for non-Query values."""
        with pytest.raises(TypeError, match="Query"):
            q(42)

    def test_wrapping_the_comparison_names_the_fix(
        self,
        memory_db: TinyDB,
    ):
        """q(Model.field == v) points at q(Model.field) == v.

        A checker flags the whole comparison, so wrapping all of it
        is the likely misreading — and a built condition is a
        QueryInstance, which is not a Query.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        with pytest.raises(TypeError) as excinfo:
            q(User.name == "Alice")
        message = str(excinfo.value)
        assert "q(Model.field) == value" in message
        assert "string" not in message

    def test_string_advice_is_only_for_strings(self):
        """Non-string values do not get field()/where() advice."""
        with pytest.raises(TypeError) as excinfo:
            q(42)
        assert "string" not in str(excinfo.value)


class TestFieldHelper:
    """The field() named-field query constructor."""

    def test_field_builds_a_query_on_the_named_key(
        self,
        memory_db: TinyDB,
    ):
        """field(Model, 'name') queries that document key."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        User(name="Alice").insert()
        query = field(User, "name")
        assert isinstance(query, Query)
        assert [user.name for user in User.search(query == "Alice")] == [
            "Alice",
        ]

    def test_field_matches_a_raw_where_query(self, memory_db: TinyDB):
        """field() conditions stay interchangeable with TinyDB's.

        The model is a build-time lookup table only — it never
        enters the returned object, so the condition must compare
        and hash equal to the raw spelling.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        built = field(User, "name") == "Alice"
        raw = where("name") == "Alice"
        assert built == raw
        assert hash(built) == hash(raw)

    # The shadowed field is the point of this test; pydantic rightly
    # warns about it.
    @pytest.mark.filterwarnings(
        'ignore:Field name "search":UserWarning',
    )
    def test_field_reaches_a_shadowed_field(self, memory_db: TinyDB):
        """Fields colliding with methods stay queryable."""

        class Command(
            TinydanticModel,
            database=memory_db,
            shadowed_fields=("search",),
        ):
            """Test model with a field shadowed by search()."""

            name: str
            search: str  # type: ignore[assignment]

        Command(name="find", search="fuzzy").insert()
        Command(name="grep", search="regex").insert()
        # search() is shadowed by the field, so a checker sees a str
        # here — the very reason field() is the only query path.
        cond = field(Command, "search") == "fuzzy"
        results = Command.search(cond)  # type: ignore[operator]
        assert [command.name for command in results] == ["find"]

    def test_field_accepts_a_computed_field(self, memory_db: TinyDB):
        """Computed fields are stored, so they are queryable.

        They live in model_computed_fields, not model_fields, so a
        naive membership test would wrongly refuse them.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with a computed field."""

            name: str

            @computed_field  # type: ignore[prop-decorator]
            @property
            def shout(self) -> str:
                """Return the name in upper case."""
                return self.name.upper()

        User(name="alice").insert()
        results = User.search(field(User, "shout") == "ALICE")
        assert [user.name for user in results] == ["alice"]

    def test_field_accepts_revision_id(self, memory_db: TinyDB):
        """revision_id is a real body field on revisioned models."""

        class Doc(TinydanticModel, database=memory_db, use_revision=True):
            """Revisioned test model."""

            name: str

        doc = Doc(name="a")
        doc.insert()
        results = Doc.search(field(Doc, "revision_id") == str(doc.revision_id))
        assert [found.name for found in results] == ["a"]

    def test_field_rejects_an_unknown_name(self, memory_db: TinyDB):
        """An unknown name raises and names the raw escape."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        with pytest.raises(QueryFieldError) as excinfo:
            field(User, "nickname")
        message = str(excinfo.value)
        assert "'nickname' is not a queryable field of 'User'" in message
        assert "where('nickname')" in message

    def test_unknown_name_listing_excludes_id(self, memory_db: TinyDB):
        """The listing shows accepted names, so id is absent.

        Listing a name the very same call refuses would contradict
        the error it appears in.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        with pytest.raises(QueryFieldError) as excinfo:
            field(User, "nickname")
        assert "['name']" in str(excinfo.value)

    def test_field_rejects_id(self, memory_db: TinyDB):
        """Id maps to doc_id and is never in the document body."""

        class User(TinydanticModel, database=memory_db):
            """Test model."""

            name: str

        with pytest.raises(QueryFieldError, match=r"User\.id"):
            field(User, "id")

    def test_field_rejects_a_dotted_path(self, memory_db: TinyDB):
        """A dotted name points at attribute chaining.

        where('address.city') queries a literal dotted key and
        matches nothing, so refuse it and teach the real spelling.
        """

        class User(TinydanticModel, database=memory_db):
            """Test model with a nested model field."""

            name: str
            address: Address

        with pytest.raises(QueryFieldError) as excinfo:
            field(User, "address.city")
        assert "field(User, 'address').city" in str(excinfo.value)

    def test_field_rejects_a_storage_alias(self, memory_db: TinyDB):
        """Storage keys are Python field names, never aliases."""

        class Profile(TinydanticModel, database=memory_db):
            """Test model with an aliased field."""

            model_config = ConfigDict(alias_generator=to_camel)

            display_name: str

        with pytest.raises(QueryFieldError, match="not storage aliases"):
            field(Profile, "displayName")

    def test_field_rejects_an_extra_key(self, memory_db: TinyDB):
        """extra='allow' keys are not model fields, so where() wins.

        They live in per-instance __pydantic_extra__, so no
        class-level check can enumerate them.
        """

        class Doc(TinydanticModel, database=memory_db):
            """Test model accepting undeclared keys."""

            model_config = ConfigDict(extra="allow")

            name: str

        Doc(name="a", legacy=42).insert()
        with pytest.raises(QueryFieldError, match="where\\('legacy'\\)"):
            field(Doc, "legacy")
        # The documented raw path still reaches it.
        assert [d.name for d in Doc.search(where("legacy") == 42)] == ["a"]
