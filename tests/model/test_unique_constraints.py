# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for composite unique constraints (``UniqueConstraint``)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydantic import (
    ConstraintFieldError,
    TinydanticModel,
    Unique,
    UniqueConstraint,
    UniqueConstraintError,
)

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestUniqueConstraintConstruction:
    """Constructor validation happens before any model context."""

    def test_fields_and_key_are_stored(self) -> None:
        """Fields land as a tuple; key is kept as passed."""
        constraint = UniqueConstraint("a", "b", key=str.casefold)
        assert constraint.fields == ("a", "b")
        assert constraint.key is str.casefold

    def test_key_defaults_to_none(self) -> None:
        """No key means exact-match comparison."""
        assert UniqueConstraint("a").key is None

    def test_zero_fields_raises(self) -> None:
        """A constraint over nothing is meaningless."""
        with pytest.raises(ValueError, match="at least one field"):
            UniqueConstraint()

    def test_duplicate_fields_raise(self) -> None:
        """Repeating a field is a typo, not a wider constraint."""
        with pytest.raises(ValueError, match="duplicate"):
            UniqueConstraint("a", "b", "a")

    def test_non_callable_key_raises(self) -> None:
        """``key=`` must be callable."""
        with pytest.raises(ValueError, match="callable"):
            UniqueConstraint("a", key="casefold")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        """Constraints are immutable."""
        constraint = UniqueConstraint("a")
        with pytest.raises(AttributeError):
            constraint.fields = ("b",)  # type: ignore[misc]

    def test_unique_marker_non_callable_key_raises(self) -> None:
        """``Unique(key=...)`` validates the same way."""
        with pytest.raises(ValueError, match="callable"):
            Unique(key="casefold")  # type: ignore[arg-type]

    def test_unique_marker_key_defaults_to_none(self) -> None:
        """The bare marker keeps exact-match semantics."""
        assert Unique().key is None


class TestErrorMessages:
    """UniqueConstraintError renders tuples honestly."""

    def test_singular_wording_preserved(self) -> None:
        """One key-less field keeps today's exact message shape."""
        err = UniqueConstraintError(
            model_name="User",
            table_name="user",
            fields=("email",),
            values=("a@x.io",),
            doc_id=3,
        )
        assert str(err) == (
            "Value 'a@x.io' for unique field 'email' already "
            "exists in table 'user' (model 'User') — held by "
            "document 3."
        )

    def test_composite_wording(self) -> None:
        """Composites pluralize and show both tuples."""
        err = UniqueConstraintError(
            model_name="Follow",
            table_name="follow",
            fields=("follower_id", "followee_id"),
            values=(3, 7),
            doc_id=4,
        )
        assert "Values (3, 7) for unique fields" in str(err)
        assert "('follower_id', 'followee_id')" in str(err)

    def test_comparison_key_shown_when_differing(self) -> None:
        """A normalizing key surfaces its computed key."""
        err = UniqueConstraintError(
            model_name="Article",
            table_name="article",
            fields=("author_id", "slug"),
            values=(7, "My-Slug"),
            comparison_key=(7, "my-slug"),
            doc_id=4,
        )
        assert "(comparison key (7, 'my-slug'))" in str(err)

    def test_comparison_key_hidden_when_equal(self) -> None:
        """An identity key adds no noise."""
        err = UniqueConstraintError(
            model_name="A",
            table_name="a",
            fields=("x",),
            values=("v",),
            comparison_key=("v",),
            doc_id=1,
        )
        assert "comparison key" not in str(err)

    def test_batch_wording(self) -> None:
        """``doc_id=None`` names the batch, as today."""
        err = UniqueConstraintError(
            model_name="U",
            table_name="u",
            fields=("email",),
            values=("a@x.io",),
            doc_id=None,
        )
        assert "another document in the same batch" in str(err)


class TestDeclarationValidation:
    """Bad constraints fail loudly at definition or bind time."""

    def test_unknown_field_raises_at_class_definition(
        self,
        db: TinyDB,
    ) -> None:
        """A constraint naming a non-field is rejected."""
        with pytest.raises(ConstraintFieldError, match="typo"):

            class Bad(
                TinydanticModel,
                database=db,
                constraints=(UniqueConstraint("typo"),),
            ):
                """Test model with a misspelled constraint."""

                real: int

    def test_id_field_raises_at_class_definition(
        self,
        db: TinyDB,
    ) -> None:
        """``id`` is never in the body — silent-non-match trap."""
        with pytest.raises(ConstraintFieldError, match="'id'"):

            class Bad(
                TinydanticModel,
                database=db,
                constraints=(UniqueConstraint("id", "a"),),
            ):
                """Test model constraining the id field."""

                a: int

    def test_bind_validates_constraints(self, db: TinyDB) -> None:
        """Late binding gets the same loud validation."""

        class Late(TinydanticModel):
            """Test model bound after definition."""

            a: int

        with pytest.raises(ConstraintFieldError, match="typo"):
            Late.bind(
                database=db,
                constraints=(UniqueConstraint("typo"),),
            )

    @pytest.mark.xfail(
        reason="enforcement lands with the registry task",
        strict=True,
    )
    def test_nearest_wins_inheritance(self, db: TinyDB) -> None:
        """A subclass's ``constraints=`` replaces its parent's."""

        class Parent(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model declaring a pair constraint."""

            a: int
            b: int

        class Child(Parent, table_name="child", constraints=()):
            """Subclass suppressing the inherited constraint."""

        Child(a=1, b=2).insert()
        Child(a=1, b=2).insert()  # no constraint — allowed
        Parent(a=1, b=2).insert()
        with pytest.raises(UniqueConstraintError):
            Parent(a=1, b=2).insert()

    @pytest.mark.xfail(
        reason="enforcement lands with the registry task",
        strict=True,
    )
    def test_unbind_restores_parent(self, db: TinyDB) -> None:
        """``unbind('constraints')`` resurfaces inherited config."""

        class Base(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a"),),
        ):
            """Test model declaring a single-field constraint."""

            a: int

        class Sub(Base, table_name="sub"):
            """Subclass inheriting the constraint."""

        Sub.bind(constraints=())
        Sub(a=1).insert()
        Sub(a=1).insert()  # constraint suppressed
        Sub.unbind("constraints")
        with pytest.raises(UniqueConstraintError):
            Sub(a=1).insert()
