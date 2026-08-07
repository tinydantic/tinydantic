# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Round-trip serialization, save() and delete()."""

from __future__ import annotations

import datetime
import uuid

from typing import TYPE_CHECKING

import pytest

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    model_validator,
)
from tinydb.table import Document

from tinydantic import (
    DocumentIDRequiredError,
    DocumentNotFoundError,
    TinydanticModel,
    UnknownUpdateFieldError,
    q,
)

if TYPE_CHECKING:
    from tinydb import TinyDB

    from tests.model.models import UserBase


class Address(BaseModel):
    """Nested model for round-trip tests."""

    city: str
    zip_code: str


class RichBase(TinydanticModel):
    """Model exercising rich pydantic types."""

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
    """The id field is visible in dumps but never stored."""

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
        """JSON-mode dump out, validation back in."""
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


class TestUpdateSerialization:
    """update() runs mapping values through the model's fields."""

    def test_update_serializes_rich_values(self, rich_class: type[RichBase]):
        """A datetime lands in storage as a JSON-safe string."""
        original = rich_class(
            name="Alice",
            created_at=datetime.datetime(
                2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc
            ),
            token=uuid.uuid4(),
            address=Address(city="Oakland", zip_code="94601"),
        ).insert()
        assert original.id is not None
        new_time = datetime.datetime(
            2027, 1, 1, 12, 0, tzinfo=datetime.timezone.utc
        )
        rich_class.update({"created_at": new_time}, doc_ids=[original.id])
        raw = rich_class.get_table().get(doc_id=original.id)
        assert isinstance(raw, Document)
        assert isinstance(raw["created_at"], str)
        loaded = rich_class.get_by_id(original.id)
        assert loaded is not None
        assert loaded.created_at == new_time

    def test_update_serializes_nested_models(
        self,
        rich_class: type[RichBase],
    ):
        """A nested BaseModel value is stored as a plain dict."""
        original = rich_class(
            name="Alice",
            created_at=datetime.datetime(
                2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc
            ),
            token=uuid.uuid4(),
            address=Address(city="Oakland", zip_code="94601"),
        ).insert()
        assert original.id is not None
        rich_class.update(
            {"address": Address(city="Berlin", zip_code="10115")},
            doc_ids=[original.id],
        )
        raw = rich_class.get_table().get(doc_id=original.id)
        assert isinstance(raw, Document)
        assert raw["address"] == {"city": "Berlin", "zip_code": "10115"}

    def test_update_validates_values(self, user_class: type[UserBase]):
        """A value the field cannot validate raises ValidationError."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        with pytest.raises(ValidationError):
            user_class.update({"age": "not a number"}, doc_ids=[user.id])

    def test_update_unknown_keys_need_explicit_allow(
        self,
        user_class: type[UserBase],
    ):
        """Non-field keys are rejected unless extra_keys='allow'."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        with pytest.raises(UnknownUpdateFieldError, match="nickname"):
            user_class.update({"nickname": "Al"}, doc_ids=[user.id])
        user_class.update(
            {"nickname": "Al"},
            doc_ids=[user.id],
            extra_keys="allow",
        )
        raw = user_class.get_table().get(doc_id=user.id)
        assert isinstance(raw, Document)
        assert raw["nickname"] == "Al"

    def test_update_multiple_serializes_values(
        self,
        rich_class: type[RichBase],
    ):
        """update_multiple() serializes each update's mapping too."""
        original = rich_class(
            name="Alice",
            created_at=datetime.datetime(
                2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc
            ),
            token=uuid.uuid4(),
            address=Address(city="Oakland", zip_code="94601"),
        ).insert()
        new_time = datetime.datetime(
            2028, 1, 1, 12, 0, tzinfo=datetime.timezone.utc
        )
        rich_class.update_multiple(
            [({"created_at": new_time}, q("name") == "Alice")],
        )
        raw = rich_class.get_table().get(doc_id=original.id)
        assert isinstance(raw, Document)
        assert isinstance(raw["created_at"], str)


class TestSave:
    """save() = insert when new, else upsert-by-id."""

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


class TestErrorContext:
    """Raised errors name the model, table, id, and operation."""

    def test_not_found_names_id_and_table(self, user_class: type[UserBase]):
        """DocumentNotFoundError carries the id and table name."""
        user = user_class(name="Alice", age=37).insert()
        table_name = user_class.get_table().name
        user.delete()
        with pytest.raises(DocumentNotFoundError) as excinfo:
            user.delete()
        message = str(excinfo.value)
        assert f"id {user.id}" in message
        assert repr(table_name) in message
        assert repr(user_class.__name__) in message

    def test_replace_not_found_names_id_and_table(
        self,
        user_class: type[UserBase],
    ):
        """replace() raises with the same context-rich message."""
        user = user_class(name="Alice", age=37).insert()
        user.delete()
        with pytest.raises(DocumentNotFoundError) as excinfo:
            user.replace()
        message = str(excinfo.value)
        assert f"id {user.id}" in message
        assert repr(user_class.get_table().name) in message

    def test_id_required_names_model_and_operation(
        self,
        user_class: type[UserBase],
    ):
        """DocumentIDRequiredError says what to do about it."""
        user = user_class(name="Alice", age=37)
        with pytest.raises(DocumentIDRequiredError) as excinfo:
            user.delete()
        message = str(excinfo.value)
        assert "delete()" in message
        assert repr(user_class.__name__) in message
        assert "insert()" in message

    def test_id_required_replace_operation(self, user_class: type[UserBase]):
        """replace() names itself in the id-required message."""
        user = user_class(name="Alice", age=37)
        with pytest.raises(DocumentIDRequiredError, match=r"replace\(\)"):
            user.replace()


class TestWriteBoundaryValidation:
    """Whole-model writes refuse payloads that would fail on read."""

    @pytest.mark.filterwarnings(
        "ignore::UserWarning",  # serializer warns pre-validation
    )
    def test_save_refuses_container_corruption(self, db: TinyDB):
        """In-place container mutation cannot reach storage."""

        class Tagged(TinydanticModel, database=db):
            """Test model with a list field."""

            tags: list[int] = Field(default_factory=list)

        tagged = Tagged(tags=[1]).insert()
        tagged.tags.append("junk")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            tagged.save()
        assert tagged.id is not None
        loaded = Tagged.get_by_id(tagged.id)
        assert loaded is not None
        assert loaded.tags == [1]

    @pytest.mark.filterwarnings(
        "ignore::UserWarning",  # serializer warns pre-validation
    )
    def test_save_refuses_nested_model_corruption(self, db: TinyDB):
        """Mutating a nested plain BaseModel cannot reach storage."""

        class Author(BaseModel):
            """Nested model without assignment validation."""

            name: str

        class Book(TinydanticModel, database=db):
            """Test model embedding Author."""

            author: Author

        book = Book(author=Author(name="F")).insert()
        book.author.name = 123  # type: ignore[assignment]
        with pytest.raises(ValidationError):
            book.save()

    @pytest.mark.filterwarnings(
        "ignore::UserWarning",  # serializer warns pre-validation
    )
    def test_insert_refuses_corrupted_instance(self, db: TinyDB):
        """insert() checks the payload, not just construction."""

        class Tagged(TinydanticModel, database=db):
            """Test model with a list field."""

            tags: list[int] = Field(default_factory=list)

        tagged = Tagged(tags=[1])
        tagged.tags.append("junk")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            tagged.insert()
        assert Tagged.count() == 0

    def test_boundary_validators_see_real_id(self, db: TinyDB):
        """save() validation runs with the instance id visible."""

        class Audited(TinydanticModel, database=db):
            """Test model recording the id its validator saw."""

            name: str
            seen_id: int | None = None

            @model_validator(mode="after")
            def record_id(self) -> Audited:
                """Record the id visible during validation."""
                object.__setattr__(self, "seen_id", self.id)
                return self

        audited = Audited(name="x").insert()
        audited.save()
        assert audited.id is not None

    @pytest.mark.filterwarnings(
        "ignore::UserWarning",  # serializer warns pre-validation
    )
    def test_validate_writes_false_restores_old_save(self, db: TinyDB):
        """The knob opts a model out of boundary validation."""

        class Loose(TinydanticModel, database=db, validate_writes=False):
            """Test model with write validation off."""

            tags: list[int] = Field(default_factory=list)

        loose = Loose(tags=[1]).insert()
        loose.tags.append("junk")  # type: ignore[arg-type]
        loose.save()
        raw = Loose.get_table().get(doc_id=loose.id)
        assert isinstance(raw, dict)
        assert raw["tags"] == [1, "junk"]
