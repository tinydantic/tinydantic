# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Fixtures for model tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.model.models import UserBase

if TYPE_CHECKING:
    from tinydb import TinyDB


@pytest.fixture(
    params=[
        None,
        "",
        "users",
    ],
    ids=[
        "table_name_none",
        "table_name_empty",
        "table_name_users",
    ],
)
def user_class(request: pytest.FixtureRequest, db: TinyDB) -> type[UserBase]:
    """Return a user model class bound to the test database.

    Parametrized over table_name values: None (not provided), ""
    (explicitly falsy — falls back to the derived name), and "users".
    """

    class User(UserBase, database=db, table_name=request.param):
        """Bound test model."""

    return User


@pytest.fixture
def make_users(user_class: type[UserBase]) -> list[UserBase]:
    """Return a couple of unsaved user instances."""
    return [
        user_class(name="John", age=37),
        user_class(name="John Smith", age=24),
    ]
