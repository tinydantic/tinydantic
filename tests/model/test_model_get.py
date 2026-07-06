# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for retrieving TinydanticModel documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.model.models import UserBase


class TestModelGet:
    """Tests for TinydanticModel.get."""

    def test_get_return_type(self, user_class: type[UserBase]):
        """Return an instance of the model class."""
        user = user_class(name="Alice", age=37)
        user.insert()
        assert user.id is not None
        result = user_class.get(doc_id=user.id)
        assert isinstance(result, user_class)
