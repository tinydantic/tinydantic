# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for composite unique constraints (``UniqueConstraint``)."""

from __future__ import annotations

import pytest

from tinydantic import Unique, UniqueConstraint


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
