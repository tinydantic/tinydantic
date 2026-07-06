# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Model classes shared by the model tests.

``UserBase`` deliberately has no database bound. Fixtures subclass it
with class keywords to bind each test's database, for example
``class User(UserBase, database=db, table_name="users")``.
"""

from __future__ import annotations

from tinydantic import TinydanticModel


class UserBase(TinydanticModel):
    """An unbound user model for tests."""

    name: str
    age: int | None = None
