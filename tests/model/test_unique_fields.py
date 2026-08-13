# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Unique-field enforcement via the Annotated Unique marker."""

from __future__ import annotations

import datetime

from typing import TYPE_CHECKING, Annotated

import pytest

from tinydantic import (
    TinydanticModel,
    Unique,
    UniqueConstraintError,
    field,
    q,
)

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestInsertPaths:
    """Create-style writes refuse duplicate unique values."""

    def test_duplicate_insert_raises(self, db: TinyDB):
        """A second insert with the same value names the clash."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique()]

        User(email="a@x.io").insert()
        with pytest.raises(
            UniqueConstraintError,
            match=r"'a@x\.io'.*'email'.*'user'",
        ):
            User(email="a@x.io").insert()
        assert User.count() == 1

    def test_distinct_values_pass(self, db: TinyDB):
        """Different values insert freely."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique()]

        User(email="a@x.io").insert()
        User(email="b@x.io").insert()
        assert User.count() == 2

    def test_multiple_nones_allowed(self, db: TinyDB):
        """None is exempt, like SQL NULL under UNIQUE."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str | None, Unique()] = None

        User().insert()
        User().insert()
        assert User.count() == 2

    def test_bare_class_marker_works(self, db: TinyDB):
        """Annotated[str, Unique] (no call) also enforces."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique]

        User(email="a@x.io").insert()
        with pytest.raises(UniqueConstraintError):
            User(email="a@x.io").insert()

    def test_insert_multiple_intra_batch_aborts(self, db: TinyDB):
        """A duplicate inside one batch writes nothing."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique()]

        with pytest.raises(UniqueConstraintError):
            User.insert_many(
                [User(email="a@x.io"), User(email="a@x.io")],
            )
        assert User.count() == 0

    def test_rich_values_compare_serialized(self, db: TinyDB):
        """Datetimes clash by their stored representation."""

        class Event(TinydanticModel, database=db):
            """Test model."""

            at: Annotated[datetime.datetime, Unique()]

        when = datetime.datetime(
            2027, 1, 1, 12, 0, tzinfo=datetime.timezone.utc
        )
        Event(at=when).insert()
        with pytest.raises(UniqueConstraintError):
            Event(at=when).insert()


class TestInstanceWrites:
    """save/replace/patch exclude the instance's own document."""

    def test_save_own_value_passes(self, db: TinyDB):
        """Re-saving an unchanged unique value is not a clash."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique()]

        user = User(email="a@x.io").insert()
        user.save()
        user.replace()
        assert User.count() == 1

    def test_save_conflicting_value_raises(self, db: TinyDB):
        """Stealing another document's value via save() fails."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique()]

        User(email="a@x.io").insert()
        other = User(email="b@x.io").insert()
        other.email = "a@x.io"
        with pytest.raises(UniqueConstraintError):
            other.save()

    def test_patch_conflicting_value_raises(self, db: TinyDB):
        """patch() enforces uniqueness, nothing written."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique()]

        User(email="a@x.io").insert()
        other = User(email="b@x.io").insert()
        with pytest.raises(UniqueConstraintError):
            other.patch(email="a@x.io")
        assert other.email == "b@x.io"
        assert other.id is not None
        loaded = User.get_by_id(other.id)
        assert loaded is not None
        assert loaded.email == "b@x.io"

    def test_patch_own_value_passes(self, db: TinyDB):
        """Patching a unique field to its current value is fine."""

        class User(TinydanticModel, database=db):
            """Test model."""

            email: Annotated[str, Unique()]

        user = User(email="a@x.io").insert()
        user.patch(email="a@x.io")
        assert user.email == "a@x.io"


class TestUpsert:
    """upsert() handles matched-set semantics."""

    def test_single_match_update_passes(self, db: TinyDB):
        """Updating the one matching document is fine."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str
            email: Annotated[str, Unique()]

        User(name="al", email="a@x.io").insert()
        User.upsert(
            User(name="al", email="a2@x.io"),
            q(User.name) == "al",
        )
        found = User.get(field(User, "email") == "a2@x.io")
        assert found is not None

    def test_insert_branch_checked(self, db: TinyDB):
        """The no-match insert branch enforces uniqueness."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str
            email: Annotated[str, Unique()]

        User(name="al", email="a@x.io").insert()
        with pytest.raises(UniqueConstraintError):
            User.upsert(
                User(name="new", email="a@x.io"),
                q(User.name) == "new",
            )

    def test_multi_match_with_unique_payload_raises(self, db: TinyDB):
        """N matched documents cannot share one unique value."""

        class User(TinydanticModel, database=db):
            """Test model."""

            role: str
            email: Annotated[str, Unique()]

        User(role="admin", email="a@x.io").insert()
        User(role="admin", email="b@x.io").insert()
        with pytest.raises(UniqueConstraintError):
            User.upsert(
                User(role="admin", email="c@x.io"),
                q(User.role) == "admin",
            )


class TestDocumentedBypass:
    """The update verbs deliberately skip the check."""

    def test_update_by_ids_bypasses_uniqueness(self, db: TinyDB):
        """update_by_ids() is a documented loose path.

        update()'s own bypass is pinned in
        ``test_unique_constraints.py``.
        """

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str
            email: Annotated[str, Unique()]

        User(name="al", email="a@x.io").insert()
        bob = User(name="bo", email="b@x.io").insert()
        assert bob.id is not None
        User.update_by_ids({"email": "a@x.io"}, [bob.id])
        raw = User.get_table().get(doc_id=bob.id)
        assert isinstance(raw, dict)
        assert raw["email"] == "a@x.io"
