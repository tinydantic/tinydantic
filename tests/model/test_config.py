# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for the tinydantic configuration machinery.

These tests use plain (non-pydantic) classes: the config helpers only
rely on ``__mro__`` and per-class ``__dict__`` entries, so they can be
tested without constructing real models.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from tinydantic.config import check_config_ambiguity, get_config_value
from tinydantic.errors import AmbiguousConfigError


class Root:
    """Root class providing a database marker and table name."""

    __tinydantic_config__: ClassVar[dict[str, str]] = {
        "database": "db-root",
        "table_name": "root",
    }


class Child(Root):
    """Child that sets nothing itself."""

    __tinydantic_config__: ClassVar[dict[str, str]] = {}


class Override(Root):
    """Child that overrides only the table name."""

    __tinydantic_config__: ClassVar[dict[str, str]] = {
        "table_name": "override",
    }


class OtherRoot:
    """Unrelated root with a conflicting database marker."""

    __tinydantic_config__: ClassVar[dict[str, str]] = {"database": "db-other"}


class SameValueRoot:
    """Unrelated root whose database value matches Root's."""

    __tinydantic_config__: ClassVar[dict[str, str]] = {"database": "db-root"}


class TestGetConfigValue:
    """Tests for per-key MRO config resolution."""

    def test_own_value(self):
        """A key set on the class itself is returned."""
        assert get_config_value(Root, "table_name") == "root"

    def test_inherited_value(self):
        """A key not set on the class resolves from the closest base."""
        assert get_config_value(Child, "database") == "db-root"
        assert get_config_value(Child, "table_name") == "root"

    def test_override_wins_per_key(self):
        """Overriding one key does not disturb inheritance of others."""
        assert get_config_value(Override, "table_name") == "override"
        assert get_config_value(Override, "database") == "db-root"

    def test_missing_key_returns_default(self):
        """An unset key returns the provided default."""
        assert get_config_value(Root, "missing") is None
        assert get_config_value(Root, "missing", default=42) == 42

    def test_class_without_config_attr(self):
        """Classes with no config anywhere resolve to the default."""

        class Bare:
            """No tinydantic config at all."""

        assert get_config_value(Bare, "database") is None


class TestCheckConfigAmbiguity:
    """Tests for the multi-base conflict check."""

    def test_single_chain_is_not_ambiguous(self):
        """Single-inheritance overrides are ordinary, not conflicts."""
        check_config_ambiguity(Override)

    def test_unrelated_conflicting_bases_raise(self):
        """Two unrelated bases with different values is an error."""

        class Diamond(Root, OtherRoot):
            """Inherits conflicting database values."""

            __tinydantic_config__: ClassVar[dict[str, str]] = {}

        with pytest.raises(AmbiguousConfigError, match="database"):
            check_config_ambiguity(Diamond)

    def test_explicit_own_value_resolves_conflict(self):
        """Setting the key on the class itself silences the check."""

        class Resolved(Root, OtherRoot):
            """Sets database explicitly, so no ambiguity remains."""

            __tinydantic_config__: ClassVar[dict[str, str]] = {
                "database": "db-mine",
            }

        check_config_ambiguity(Resolved)

    def test_equal_values_are_not_ambiguous(self):
        """Two bases agreeing on the value is not a conflict."""

        class Agreeing(Root, SameValueRoot):
            """Both bases say db-root."""

            __tinydantic_config__: ClassVar[dict[str, str]] = {}

        check_config_ambiguity(Agreeing)
