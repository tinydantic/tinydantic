# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.document.models import UserBase

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
    """TODO: needs docstring."""

    class User(UserBase):
        """TODO: needs docstring."""

        database = db
        table_name = request.param

    return User


@pytest.fixture
def make_users(user_class: type[UserBase]) -> list[UserBase]:
    """TODO: needs docstring."""
    return [
        user_class(name="John", age=37),
        user_class(name="John Smith", age=24),
    ]
