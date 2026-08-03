# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""The curated error surface: no raw TinyDB exceptions leak."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydantic import SelectorError, TinydanticModel, q

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestSelectorError:
    """Selector misuse raises SelectorError, never RuntimeError."""

    def test_get_no_selector(self, db: TinyDB):
        """get() with nothing raises SelectorError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError):
            User.get()  # type: ignore[call-overload]

    def test_get_too_many_selectors_compat(self, db: TinyDB):
        """The upgraded guard can still be caught as ValueError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(ValueError, match="at most one"):
            User.get(  # type: ignore[call-overload]
                q(User.name) == "x",
                doc_id=1,
            )
        with pytest.raises(SelectorError):
            User.get(  # type: ignore[call-overload]
                q(User.name) == "x",
                doc_id=1,
            )

    def test_contains_no_selector(self, db: TinyDB):
        """contains() with nothing raises SelectorError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError):
            User.contains()

    def test_get_or_raise_no_selector(self, db: TinyDB):
        """get_or_raise() with nothing raises SelectorError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError):
            User.get_or_raise()  # type: ignore[call-overload]

    def test_remove_no_selector_points_at_truncate(self, db: TinyDB):
        """remove() with nothing refuses and names truncate()."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        User(name="x").insert()
        with pytest.raises(SelectorError, match="truncate"):
            User.remove()
        assert User.count() == 1

    def test_upsert_no_cond_unset_id(self, db: TinyDB):
        """upsert() without cond or id explains both fixes."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError, match="insert"):
            User.upsert(User(name="x"))

    def test_upsert_with_id_still_works(self, db: TinyDB):
        """The valid no-cond path (id set) is untouched."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="x").insert()
        user.name = "y"
        assert User.upsert(user) == [user.id]
