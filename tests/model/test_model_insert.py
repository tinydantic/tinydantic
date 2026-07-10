# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for inserting TinydanticModel documents."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.model.models import UserBase


class TestModelInsert:
    """Tests for TinydanticModel.insert."""

    def test_insert_id_is_not_set(self, user_class: type[UserBase]):
        """Inserting a model without an id assigns the next id."""
        user = user_class(name="Alice", age=37)
        assert user.id is None
        user.insert()
        assert user.id == 1

    def test_insert_id_is_none(self, user_class: type[UserBase]):
        """Inserting a model with id=None assigns the next id."""
        user = user_class(id=None, name="Alice", age=37)
        assert user.id is None
        user.insert()
        assert user.id == 1

    def test_insert_id_is_zero(self, user_class: type[UserBase]):
        """Inserting a model with id=0 preserves the explicit id."""
        user = user_class(id=0, name="Alice", age=37)
        assert user.id == 0
        user.insert()
        assert user.id == 0

    def test_insert_id_is_negative(self, user_class: type[UserBase]):
        """A negative id is preserved on insert."""
        user = user_class(id=-5, name="Alice", age=37)
        user.insert()
        assert user.id == -5

    def test_insert_id_increment(self, user_class: type[UserBase]):
        """Consecutive inserts without ids increment the assigned id."""
        user1 = user_class(name="Alice", age=37)
        user1.insert()
        user2 = user_class(name="Alice", age=37)
        user2.insert()
        assert user1.id == 1
        assert user2.id == 2

    def test_insert_id_increment_from_none(self, user_class: type[UserBase]):
        """An id=None insert increments the next assigned id."""
        user1 = user_class(id=None, name="Alice", age=37)
        user1.insert()
        user2 = user_class(name="Alice", age=37)
        user2.insert()
        assert user1.id == 1
        assert user2.id == 2

    def test_insert_id_increment_from_zero(self, user_class: type[UserBase]):
        """An explicit id=0 insert increments the next assigned id."""
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
        """A negative id still increments the next assigned id."""
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
        """Optional fields omitted on insert round-trip as unset."""
        user = user_class(name="Alice")
        user.insert()
        assert user.id is not None
        result = user_class.get(doc_id=user.id)
        assert isinstance(result, user_class)
        assert result.name == "Alice"
        assert result.age is None

    def test_insert_doc_with_optional_args(self, user_class: type[UserBase]):
        """Optional fields set on insert round-trip as set."""
        user = user_class(name="Alice", age=37)
        user.insert()
        assert user.id is not None
        result = user_class.get(doc_id=user.id)
        assert isinstance(result, user_class)
        assert result.name == "Alice"
        assert result.age == 37

    def test_insert_existing_document(self, user_class: type[UserBase]):
        """Re-inserting an existing id raises a ValueError."""
        user = user_class(name="Alice", age=37)
        user.insert()
        assert user.id is not None
        user_class.get(doc_id=user.id)
        with pytest.raises(
            ValueError,
            match=r"Document with ID .* already exists",
        ):
            user.insert()


class TestModelInsertMany:
    """Tests for TinydanticModel.insert_multiple."""

    def test_insert_many(
        self,
        user_class: type[UserBase],
        make_users: list[UserBase],
    ):
        """insert_multiple stores every provided model."""
        user_class.insert_multiple(make_users)
        assert user_class.count() == len(make_users)

    def test_insert_many_sets_ids_in_place(
        self,
        user_class: type[UserBase],
        make_users: list[UserBase],
    ):
        """Each passed-in model gets its assigned id, like insert()."""
        assert all(user.id is None for user in make_users)
        user_class.insert_multiple(make_users)
        assert [user.id for user in make_users] == [1, 2]

    def test_insert_many_returns_the_models(
        self,
        user_class: type[UserBase],
        make_users: list[UserBase],
    ):
        """The same instances come back, ids set, in order."""
        result = user_class.insert_multiple(make_users)
        assert result == make_users
        assert all(a is b for a, b in zip(result, make_users, strict=True))
        assert [user.id for user in result] == [1, 2]

    def test_insert_many_round_trip(
        self,
        user_class: type[UserBase],
        make_users: list[UserBase],
    ):
        """Inserted models can be fetched back by their new ids."""
        for user in user_class.insert_multiple(make_users):
            assert user.id is not None
            fetched = user_class.get_by_id(user.id)
            assert fetched is not None
            assert fetched.name == user.name

    def test_insert_many_accepts_a_generator(
        self,
        user_class: type[UserBase],
    ):
        """Non-list iterables work and still come back as a list."""
        result = user_class.insert_multiple(
            user_class(name=name) for name in ("Alice", "Bob")
        )
        assert [user.name for user in result] == ["Alice", "Bob"]
        assert [user.id for user in result] == [1, 2]
