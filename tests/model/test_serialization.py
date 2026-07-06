# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Round-trip serialization, save() and delete() (spec 3.6/3.7)."""

from __future__ import annotations

import datetime
import uuid

from typing import TYPE_CHECKING

import pytest

from pydantic import BaseModel
from tinydb.table import Document

from tinydantic import (
    DocumentIDRequiredError,
    DocumentNotFoundError,
    TinydanticModel,
)

if TYPE_CHECKING:
    from tinydb import TinyDB

    from tests.model.models import UserBase


class Address(BaseModel):
    """Nested model for round-trip tests."""

    city: str
    zip_code: str


class RichBase(TinydanticModel):
    """Model exercising rich pydantic types (spec 3.7)."""

    name: str
    created_at: datetime.datetime
    token: uuid.UUID
    address: Address


@pytest.fixture
def rich_class(db: TinyDB) -> type[RichBase]:
    """RichBase bound to the parametrized test database."""

    class Rich(RichBase, database=db):
        """Bound test model."""

    return Rich


class TestIDSerialization:
    """The id field is visible in dumps but never stored (spec 3.6)."""

    def test_model_dump_includes_id(self, user_class: type[UserBase]):
        """model_dump() exposes id (FastAPI response models need it)."""
        user = user_class(name="Alice", age=37).insert()
        assert user.model_dump()["id"] == user.id

    def test_stored_document_has_no_id_field(self, user_class: type[UserBase]):
        """The id lives in TinyDB's doc_id, not inside the document."""
        user = user_class(name="Alice", age=37).insert()
        raw = user_class.get_table().get(doc_id=user.id)
        assert raw is not None
        assert "id" not in raw

    def test_to_tinydb_document_excludes_id(self, user_class: type[UserBase]):
        """to_tinydb_document never embeds the id key."""
        user = user_class(id=7, name="Alice", age=37)
        doc = user.to_tinydb_document(force_dict=True)
        assert "id" not in doc


class TestRoundTrip:
    """Rich pydantic types survive storage and come back typed."""

    def test_datetime_uuid_nested_round_trip(self, rich_class: type[RichBase]):
        """Spec 3.7: JSON-mode dump out, validation back in."""
        original = rich_class(
            name="Alice",
            created_at=datetime.datetime(
                2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc
            ),
            token=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            address=Address(city="Oakland", zip_code="94601"),
        )
        original.insert()
        assert original.id is not None
        loaded = rich_class.get(doc_id=original.id)
        assert isinstance(loaded, rich_class)
        assert loaded.created_at == original.created_at
        assert loaded.token == original.token
        assert loaded.address == original.address

    def test_stored_values_are_json_safe(self, rich_class: type[RichBase]):
        """What hits storage is JSON-safe (str, not datetime)."""
        original = rich_class(
            name="Alice",
            created_at=datetime.datetime(
                2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc
            ),
            token=uuid.uuid4(),
            address=Address(city="Oakland", zip_code="94601"),
        )
        original.insert()
        raw = rich_class.get_table().get(doc_id=original.id)
        assert isinstance(raw, Document)
        assert isinstance(raw["created_at"], str)
        assert isinstance(raw["token"], str)
        assert isinstance(raw["address"], dict)


class TestSave:
    """save() = insert when new, else upsert-by-id (spec 4)."""

    def test_save_new_instance_inserts(self, user_class: type[UserBase]):
        """The prototype crashed here (bare upsert with no cond)."""
        user = user_class(name="Alice", age=37)
        saved = user.save()
        assert saved is user
        assert user.id is not None
        fetched = user_class.get(doc_id=user.id)
        assert isinstance(fetched, user_class)
        assert fetched.name == "Alice"

    def test_save_existing_instance_updates(self, user_class: type[UserBase]):
        """Saving again writes changes under the same id."""
        user = user_class(name="Alice", age=37).insert()
        user.age = 38
        user.save()
        assert user.id is not None
        fetched = user_class.get(doc_id=user.id)
        assert isinstance(fetched, user_class)
        assert fetched.age == 38
        assert fetched.id == user.id


class TestDelete:
    """delete() removes by id with precise errors."""

    def test_delete_removes_document(self, user_class: type[UserBase]):
        """Deleted documents are gone."""
        user = user_class(name="Alice", age=37).insert()
        user.delete()
        assert user.id is not None
        assert user_class.get(doc_id=user.id) is None

    def test_delete_without_id_raises(self, user_class: type[UserBase]):
        """Unsaved instances cannot be deleted."""
        user = user_class(name="Alice", age=37)
        with pytest.raises(DocumentIDRequiredError):
            user.delete()

    def test_delete_missing_document_raises(self, user_class: type[UserBase]):
        """Deleting an already-removed document raises."""
        user = user_class(name="Alice", age=37).insert()
        user.delete()
        with pytest.raises(DocumentNotFoundError):
            user.delete()


class TestReplace:
    """replace() overwrites by id with precise errors."""

    def test_replace_missing_document_raises(self, user_class: type[UserBase]):
        """Replacing a vanished document raises the not-found error."""
        user = user_class(name="Alice", age=37).insert()
        user.delete()
        user.name = "Alicia"
        with pytest.raises(DocumentNotFoundError):
            user.replace()
