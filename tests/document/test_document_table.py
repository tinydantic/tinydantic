# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tinydb.table import Table

if TYPE_CHECKING:
    import pytest

    from tests.document.models import UserBase


class TestDocumentGetTable:
    """TODO: needs docstring."""

    def test_table_return_type(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        table = user_class.get_table()
        assert isinstance(table, Table)

    def test_table_name_matches_fixture_param(
        self,
        request: pytest.FixtureRequest,
        user_class: type[UserBase],
    ):
        """TODO: needs docstring."""
        table = user_class.get_table()
        expected_table_name = request.node.callspec.params.get("user_class")
        if not expected_table_name:
            expected_table_name = user_class.__name__.lower()
        assert table.name == expected_table_name
