# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

import pytest

from tinydb import TinyDB

from tests.model.models import UserBase
from tinydantic.config import get_config_value
from tinydantic.errors import DatabaseNotBoundError


class TestModelDatabaseConfig:
    """TODO: needs docstring."""

    def test_database_is_not_set(self):
        """Unbound model operations raise DatabaseNotBoundError."""
        user = UserBase(name="Alice", age=37)
        with pytest.raises(DatabaseNotBoundError, match="UserBase"):
            user.insert()

    def test_database_is_set(self, user_class: type[UserBase]):
        """A bound model resolves its database."""
        assert isinstance(user_class.get_database(), TinyDB)


class TestModelTableNameConfig:
    """TODO: needs docstring."""

    def test_table_name_matches_test_param(
        self,
        request: pytest.FixtureRequest,
        user_class: type[UserBase],
    ):
        """The stored table_name matches what the fixture passed."""
        expected = request.node.callspec.params.get("user_class")
        assert get_config_value(user_class, "table_name") == expected
