# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for composite unique constraints (``UniqueConstraint``)."""

from __future__ import annotations

import pytest

from tinydantic import (
    Unique,
    UniqueConstraint,
    UniqueConstraintError,
)


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
