# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for TinydanticModel configuration and id attributes."""

from __future__ import annotations

import pytest

from tinydb import TinyDB

from tests.model.models import UserBase
from tinydantic import DatabaseNotBoundError
from tinydantic._config import get_config_value


class TestModelDatabaseConfig:
    """Tests for model database binding."""

    def test_database_is_not_set(self):
        """Unbound model operations raise DatabaseNotBoundError."""
        user = UserBase(name="Alice", age=37)
        with pytest.raises(DatabaseNotBoundError, match="UserBase"):
            user.insert()

    def test_database_is_set(self, user_class: type[UserBase]):
        """A bound model resolves its database."""
        assert isinstance(user_class.get_database(), TinyDB)


class TestModelTableNameConfig:
    """Tests for model table_name configuration."""

    def test_table_name_matches_test_param(
        self,
        request: pytest.FixtureRequest,
        user_class: type[UserBase],
    ):
        """The stored table_name matches what the fixture passed."""
        expected = request.node.callspec.params.get("user_class")
        assert get_config_value(user_class, "table_name") == expected


class TestModelIDAttribute:
    """Tests for the model id attribute."""

    def test_id_is_not_set(self, user_class: type[UserBase]):
        """A model created without an id defaults id to None."""
        user = user_class(name="Alice", age=37)
        assert user.id is None

    def test_id_set_to_none(self, user_class: type[UserBase]):
        """A model created with id=None keeps id as None."""
        user = user_class(id=None, name="Alice", age=37)
        assert user.id is None

    def test_id_set_to_int(self, user_class: type[UserBase]):
        """An explicit id is preserved after insert."""
        user = user_class(id=5, name="Alice", age=37)
        user.insert()
        assert user.id == 5
