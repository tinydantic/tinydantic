# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Shadowed model fields fail loudly at class definition."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydb.queries import Query

from tinydantic import ShadowedFieldError, TinydanticModel, field

if TYPE_CHECKING:
    from tinydb import TinyDB

# Deliberately shadowed fields are the point of this module;
# pydantic rightly warns about every one of them.
pytestmark = pytest.mark.filterwarnings(
    "ignore:Field name .* shadows an attribute:UserWarning",
)


class TestDetection:
    """Shadowed fields raise ShadowedFieldError at definition."""

    def test_tinydantic_method_collision(self, db: TinyDB):
        """A field named after a tinydantic classmethod errors."""
        with pytest.raises(
            ShadowedFieldError,
            match=r"'search' shadows TinydanticModel\.search",
        ):

            class Command(TinydanticModel, database=db):
                """Test model."""

                search: str  # type: ignore[assignment]

    def test_pydantic_method_collision(self, db: TinyDB):
        """A field named after a pydantic method errors."""
        with pytest.raises(
            ShadowedFieldError,
            match=r"'copy' shadows BaseModel\.copy",
        ):

            class Doc(TinydanticModel, database=db):
                """Test model."""

                copy: str  # type: ignore[assignment]

    def test_user_mixin_collision(self, db: TinyDB):
        """A field shadowing the user's own mixin method errors."""

        class Mixin:
            """User mixin with a method."""

            def full_name(self) -> str:
                """Return a display name."""
                return "x"

        with pytest.raises(
            ShadowedFieldError,
            match=r"'full_name' shadows Mixin\.full_name",
        ):

            class Person(Mixin, TinydanticModel, database=db):
                """Test model."""

                full_name: str  # type: ignore[assignment]

    def test_error_lists_every_offender(self, db: TinyDB):
        """All shadowed fields are named in one error."""
        with pytest.raises(
            ShadowedFieldError,
            match=r"(?s)'count'.*'search'",
        ):

            class Multi(TinydanticModel, database=db):
                """Test model."""

                search: str  # type: ignore[assignment]
                count: int  # type: ignore[assignment]

    def test_error_names_the_remedies(self, db: TinyDB):
        """The message points at rename and shadowed_fields+field()."""
        with pytest.raises(
            ShadowedFieldError,
            match=r"shadowed_fields.*field\(Command, ",
        ):

            class Command(TinydanticModel, database=db):
                """Test model."""

                search: str  # type: ignore[assignment]


class TestNotFlagged:
    """Legitimate definitions stay silent."""

    def test_clean_fields_and_defaults(self, db: TinyDB):
        """Ordinary fields (with defaults) never trip the check."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str
            year: int = 1999

        assert isinstance(User.name, Query)

    def test_id_is_not_flagged(self, db: TinyDB):
        """The built-in id field is exempt (DocIdQuery handles it)."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str


class TestOptOut:
    """shadowed_fields= permits listed names, q() queries them."""

    def test_opt_out_allows_and_q_queries(self, db: TinyDB):
        """A listed field stores, loads, and queries via q()."""

        class Command(
            TinydanticModel,
            database=db,
            shadowed_fields=("search",),
        ):
            """Test model."""

            name: str
            search: str  # type: ignore[assignment]

        Command(name="grep", search="fuzzy").insert()
        found = Command.get(field(Command, "search") == "fuzzy")
        assert found is not None
        assert found.search == "fuzzy"

    def test_opt_out_is_inherited(self, db: TinyDB):
        """Subclasses do not re-declare the parent's opt-out."""

        class Base(
            TinydanticModel,
            database=db,
            shadowed_fields=("search",),
        ):
            """Test base model."""

            search: str  # type: ignore[assignment]

        class Child(Base):
            """Inherits the shadowed search field and the opt-out."""

    def test_unlisted_field_still_errors_in_subclass(self, db: TinyDB):
        """The opt-out covers only the listed names."""

        class Base(
            TinydanticModel,
            database=db,
            shadowed_fields=("search",),
        ):
            """Test base model."""

            search: str  # type: ignore[assignment]

        with pytest.raises(ShadowedFieldError, match="'count'"):

            class Child(Base):
                """Adds an unlisted shadowed field."""

                count: int  # type: ignore[assignment]

    def test_unshadowed_listed_name_is_accepted(self, db: TinyDB):
        """Listing a name that is not shadowed is not an error."""

        class User(
            TinydanticModel,
            database=db,
            shadowed_fields=("nothing_here",),
        ):
            """Test model."""

            name: str
