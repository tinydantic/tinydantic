# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tests.document.models import UserBase


class TestDocumentGet:
    """TODO: needs docstring."""

    def test_get_return_type(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(name="Alice", age=37)
        user.insert()
        result = user_class.get(document_id=user.id)
        assert isinstance(result, user_class)
