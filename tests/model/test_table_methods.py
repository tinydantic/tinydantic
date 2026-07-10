# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for the classmethod table surface."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydantic.tinydb.operations import replace

if TYPE_CHECKING:
    from tests.model.models import UserBase


class TestSearch:
    """search() returns validated models."""

    def test_search_returns_models(self, user_class: type[UserBase]):
        """All matches come back as model instances with ids."""
        user_class(name="John", age=37).insert()
        user_class(name="John Smith", age=24).insert()
        user_class(name="Alice", age=30).insert()
        results = user_class.search(user_class.name.matches("John.*"))  # type: ignore[attr-defined]
        assert len(results) == 2
        assert all(isinstance(u, user_class) for u in results)
        assert all(u.id is not None for u in results)

    def test_search_no_match_is_empty(self, user_class: type[UserBase]):
        """No matches means an empty list."""
        assert user_class.search(user_class.name == "Nobody") == []  # type: ignore[arg-type]


class TestContains:
    """contains() mirrors TinyDB with the selector tightening."""

    def test_contains_by_cond(self, user_class: type[UserBase]):
        """Condition form."""
        user_class(name="Alice", age=37).insert()
        assert user_class.contains(user_class.name == "Alice")  # type: ignore[arg-type]
        assert not user_class.contains(user_class.name == "Bob")  # type: ignore[arg-type]

    def test_contains_by_doc_id(self, user_class: type[UserBase]):
        """doc_id form."""
        user = user_class(name="Alice", age=37).insert()
        assert user_class.contains(doc_id=user.id)
        assert not user_class.contains(doc_id=999)

    def test_contains_both_selectors_raises(self, user_class: type[UserBase]):
        """Tighter than TinyDB: both selectors is a ValueError."""
        user = user_class(name="Alice", age=37).insert()
        with pytest.raises(ValueError, match="one of"):
            user_class.contains(user_class.name == "Alice", doc_id=user.id)  # type: ignore[arg-type]


class TestUpdate:
    """update()/update_multiple() write through to the table."""

    def test_update_fields_by_cond(self, user_class: type[UserBase]):
        """Mapping-of-fields form."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        updated = user_class.update({"age": 38}, user_class.name == "Alice")  # type: ignore[arg-type]
        assert updated == [user.id]
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None
        assert fetched.age == 38

    def test_update_by_doc_ids(self, user_class: type[UserBase]):
        """doc_ids form."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        user_class.update({"age": 40}, doc_ids=[user.id])
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None
        assert fetched.age == 40

    def test_update_multiple(self, user_class: type[UserBase]):
        """Batched per-condition updates."""
        u1 = user_class(name="Alice", age=37).insert()
        u2 = user_class(name="Bob", age=24).insert()
        assert u1.id is not None
        assert u2.id is not None
        updated = user_class.update_multiple(
            [
                ({"age": 1}, user_class.name == "Alice"),  # type: ignore[list-item]
                ({"age": 2}, user_class.name == "Bob"),  # type: ignore[list-item]
            ]
        )
        assert sorted(updated) == sorted([u1.id, u2.id])
        alice = user_class.get_by_id(u1.id)
        bob = user_class.get_by_id(u2.id)
        assert alice is not None
        assert alice.age == 1
        assert bob is not None
        assert bob.age == 2


class TestUpsert:
    """Classmethod upsert() mirrors Table.upsert."""

    def test_upsert_inserts_when_no_match(self, user_class: type[UserBase]):
        """Insert path."""
        ids = user_class.upsert(
            user_class(name="Alice", age=37),
            user_class.name == "Alice",  # type: ignore[arg-type]
        )
        assert len(ids) == 1
        fetched = user_class.get_by_id(ids[0])
        assert fetched is not None
        assert fetched.age == 37

    def test_upsert_updates_when_matched(self, user_class: type[UserBase]):
        """Update path keeps the same document id."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        ids = user_class.upsert(
            user_class(name="Alice", age=99),
            user_class.name == "Alice",  # type: ignore[arg-type]
        )
        assert ids == [user.id]
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None
        assert fetched.age == 99


class TestRemove:
    """remove() mirrors TinyDB."""

    def test_remove_by_cond(self, user_class: type[UserBase]):
        """Condition form."""
        user = user_class(name="Alice", age=37).insert()
        user_class(name="Bob", age=24).insert()
        removed = user_class.remove(user_class.name == "Alice")  # type: ignore[arg-type]
        assert removed == [user.id]
        assert user_class.count(user_class.name == "Bob") == 1  # type: ignore[arg-type]

    def test_remove_by_doc_ids(self, user_class: type[UserBase]):
        """doc_ids form."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        removed = user_class.remove(doc_ids=[user.id])
        assert removed == [user.id]
        assert user_class.get_by_id(user.id) is None


class TestCount:
    """count() with and without a condition."""

    def test_count_by_cond(self, user_class: type[UserBase]):
        """Condition form counts only the matches."""
        user_class(name="Alice", age=37).insert()
        user_class(name="Bob", age=24).insert()
        assert user_class.count(user_class.name == "Alice") == 1  # type: ignore[arg-type]

    def test_count_without_cond_counts_all(self, user_class: type[UserBase]):
        """Bare count() returns the total number of documents."""
        assert user_class.count() == 0
        user_class(name="Alice", age=37).insert()
        user_class(name="Bob", age=24).insert()
        assert user_class.count() == 2


class TestOperationsEscapeHatch:
    """tinydantic's replace() operation works through update()."""

    def test_update_with_transform(self, user_class: type[UserBase]):
        """Callable-transform form (TinyDB operations protocol)."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        user_class.update(
            replace({"name": "Alicia", "age": 38}),  # type: ignore[arg-type]
            doc_ids=[user.id],
        )
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None
        assert fetched.name == "Alicia"
        assert fetched.age == 38
