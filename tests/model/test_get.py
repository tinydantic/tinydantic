# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for get() and its typed variants (spec 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.model.models import UserBase


class TestGet:
    """The overloaded TinyDB-mirror get()."""

    def test_get_by_cond_positional(self, user_class: type[UserBase]):
        """get(cond) mirrors TinyDB's most common form."""
        user_class(name="Alice", age=37).insert()
        result = user_class.get(user_class.name == "Alice")  # type: ignore[call-overload]
        assert result is not None
        assert result.name == "Alice"

    def test_get_by_doc_id_keyword(self, user_class: type[UserBase]):
        """get(doc_id=...) fetches by document id."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        result = user_class.get(doc_id=user.id)
        assert result is not None
        assert result.name == "Alice"

    def test_get_missing_returns_none(self, user_class: type[UserBase]):
        """No match means None, mirroring TinyDB."""
        assert user_class.get(doc_id=999) is None

    def test_get_multiple_selectors_raises(self, user_class: type[UserBase]):
        """Spec tightening: more than one selector is a ValueError."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        with pytest.raises(ValueError, match="one of"):
            user_class.get(  # type: ignore[call-overload]
                user_class.name == "Alice",
                doc_id=user.id,
            )

    def test_get_by_doc_ids(self, user_class: type[UserBase]):
        """get(doc_ids=[...]) returns a list."""
        u1 = user_class(name="Alice", age=37).insert()
        u2 = user_class(name="Bob", age=24).insert()
        assert u1.id is not None
        assert u2.id is not None
        results = user_class.get(doc_ids=[u1.id, u2.id])
        assert isinstance(results, list)
        assert [r.name for r in results if r is not None] == ["Alice", "Bob"]


class TestGetVariants:
    """The explicit typed variants delegate to get()."""

    def test_get_by_cond(self, user_class: type[UserBase]):
        """get_by_cond returns a single validated model or None."""
        user_class(name="Alice", age=37).insert()
        result = user_class.get_by_cond(user_class.name == "Alice")  # type: ignore[arg-type]
        assert result is not None
        assert result.age == 37
        assert user_class.get_by_cond(user_class.name == "Nobody") is None  # type: ignore[arg-type]

    def test_get_by_id(self, user_class: type[UserBase]):
        """get_by_id returns a single validated model or None."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        result = user_class.get_by_id(user.id)
        assert result is not None
        assert result.name == "Alice"
        assert user_class.get_by_id(999) is None

    def test_get_by_ids(self, user_class: type[UserBase]):
        """get_by_ids returns validated models for the given ids."""
        u1 = user_class(name="Alice", age=37).insert()
        u2 = user_class(name="Bob", age=24).insert()
        assert u1.id is not None
        assert u2.id is not None
        results = user_class.get_by_ids([u1.id, u2.id])
        assert [r.name for r in results if r is not None] == ["Alice", "Bob"]
