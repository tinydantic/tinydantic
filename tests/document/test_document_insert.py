# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.document.models import UserBase


class TestDocumentInsert:
    """TODO: needs docstring."""

    def test_insert_id_is_not_set(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(name="Alice", age=37)
        assert user.id is None
        user.insert()
        assert user.id == 1

    def test_insert_id_is_none(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(id=None, name="Alice", age=37)
        assert user.id is None
        user.insert()
        assert user.id == 1

    def test_insert_id_is_zero(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(id=0, name="Alice", age=37)
        assert user.id == 0
        user.insert()
        assert user.id == 0

    def test_insert_id_is_negative(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(id=-5, name="Alice", age=37)
        user.insert()
        assert user.id == -5

    def test_insert_id_increment(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user1 = user_class(name="Alice", age=37)
        user1.insert()
        user2 = user_class(name="Alice", age=37)
        user2.insert()
        assert user1.id == 1
        assert user2.id == 2

    def test_insert_id_increment_from_none(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user1 = user_class(id=None, name="Alice", age=37)
        user1.insert()
        user2 = user_class(name="Alice", age=37)
        user2.insert()
        assert user1.id == 1
        assert user2.id == 2

    def test_insert_id_increment_from_zero(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user1 = user_class(id=0, name="Alice", age=37)
        user1.insert()
        user2 = user_class(name="Alice", age=37)
        user2.insert()
        assert user1.id == 0
        assert user2.id == 1

    def test_insert_id_increment_from_negative(
        self,
        user_class: type[UserBase],
    ):
        """TODO: needs docstring."""
        user1 = user_class(id=-5, name="Alice", age=37)
        user1.insert()
        user2 = user_class(name="Alice", age=37)
        user2.insert()
        assert user1.id == -5
        assert user2.id == -4

    def test_insert_doc_without_optional_args(
        self,
        user_class: type[UserBase],
    ):
        """TODO: needs docstring."""
        user = user_class(name="Alice")
        user.insert()
        result = user_class.get(document_id=user.id)
        assert isinstance(result, user_class)
        assert result.name == "Alice"
        assert result.age is None

    def test_insert_doc_with_optional_args(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(name="Alice", age=37)
        user.insert()
        result = user_class.get(document_id=user.id)
        assert isinstance(result, user_class)
        assert result.name == "Alice"
        assert result.age == 37

    def test_insert_existing_document(self, user_class: type[UserBase]):
        """TODO: needs docstring."""
        user = user_class(name="Alice", age=37)
        user.insert()
        user_class.get(document_id=user.id)
        with pytest.raises(
            ValueError,
            match=r"Document with ID .* already exists",
        ):
            user.insert()


class TestDocumentInsertMany:
    """TODO: needs docstring."""

    def test_insert_many(
        self,
        user_class: type[UserBase],
        make_users: list[UserBase],
    ):
        """TODO: needs docstring."""
        user_class.insert_multiple(make_users)
