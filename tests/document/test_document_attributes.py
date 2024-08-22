# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

import pytest

from tinydb import TinyDB

from tests.document.models import UserBase


class TestDocumentDatabaseAttribute:
    """TODO: needs docstring."""

    def test_database_is_not_set(self):
        """TODO: needs docstring."""
        user = UserBase(name="Alice", age=37)
        with pytest.raises(
            AttributeError,
            match="database",
        ):
            user.insert()

    def test_database_is_set(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        assert isinstance(user_class.database, TinyDB)


class TestDocumentTableNameAttribute:
    """TODO: needs docstring."""

    def test_table_name_matches_test_param(
        self,
        request: pytest.FixtureRequest,
        user_class: type[UserBase],
    ):
        """TODO: needs docstring."""
        expected_table_name = request.node.callspec.params.get("user_class")
        assert user_class.table_name == expected_table_name


class TestDocumentIDAttribute:
    """TODO: needs docstring."""

    def test_id_is_not_set(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(name="Alice", age=37)
        assert user.id is None

    def test_id_set_to_none(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(id=None, name="Alice", age=37)
        assert user.id is None

    def test_id_set_to_int(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(id=5, name="Alice", age=37)
        user.insert()
        assert user.id == 5
