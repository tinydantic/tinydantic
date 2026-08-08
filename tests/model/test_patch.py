# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Instance-level partial update via patch()."""

from __future__ import annotations

import datetime

from typing import TYPE_CHECKING

import pytest

from pydantic import ValidationError, model_validator

from tinydantic import (
    DocumentIDRequiredError,
    DocumentIDUpdateError,
    DocumentNotFoundError,
    TinydanticModel,
    UnknownUpdateFieldError,
    field,
)

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestPatchWrites:
    """patch() writes only the named fields and syncs self."""

    def test_preserves_concurrent_unrelated_change(self, db: TinyDB):
        """A stale copy patching one field keeps another's change."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str
            year: int
            in_stock: bool = True

        book = Book(title="Dune", year=1965).insert()
        assert book.id is not None
        copy_a = Book.get_by_id(book.id)
        copy_b = Book.get_by_id(book.id)
        assert copy_a is not None
        assert copy_b is not None
        copy_a.patch(year=1966)
        copy_b.patch(in_stock=False)  # stale year on copy_b
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.year == 1966
        assert loaded.in_stock is False

    def test_instance_matches_storage(self, db: TinyDB):
        """After patch(), instance and storage agree."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str
            in_stock: bool = True

        book = Book(title="Dune").insert()
        book.patch(in_stock=False)
        assert book.in_stock is False
        assert book.id is not None
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.in_stock is False

    def test_returns_self(self, db: TinyDB):
        """patch() returns the same instance for chaining."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.patch(title="Dune!") is book

    def test_coerces_values(self, db: TinyDB):
        """Coercible inputs land validated on self and in storage."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            year: int

        book = Book(year=1965).insert()
        book.patch(year="1966")  # type: ignore[arg-type]
        assert book.year == 1966
        assert book.id is not None
        raw = Book.get_table().get(doc_id=book.id)
        assert isinstance(raw, dict)
        assert raw["year"] == 1966

    def test_rich_value_python_on_self_serialized_in_storage(
        self,
        db: TinyDB,
    ):
        """A datetime stays a datetime on self, ISO in storage."""

        class Event(TinydanticModel, database=db):
            """Test model."""

            name: str
            when: datetime.datetime | None = None

        event = Event(name="launch").insert()
        when = datetime.datetime(
            2027, 1, 1, 12, 0, tzinfo=datetime.timezone.utc
        )
        event.patch(when=when)
        assert event.when == when
        assert event.id is not None
        raw = Event.get_table().get(doc_id=event.id)
        assert isinstance(raw, dict)
        assert isinstance(raw["when"], str)

    def test_multi_field_across_transient_invariant(self, db: TinyDB):
        """A valid final state is not tripped up mid-sync."""

        class Span(TinydanticModel, database=db):
            """Test model with a cross-field invariant."""

            start: int
            end: int

            @model_validator(mode="after")
            def ordered(self) -> Span:
                """Require end >= start."""
                if self.end < self.start:
                    msg = "end must be >= start"
                    raise ValueError(msg)
                return self

        span = Span(start=10, end=20).insert()
        # start=30 alone would violate end >= start; the final
        # state (30, 40) is valid and must go through.
        span.patch(start=30, end=40)
        assert (span.start, span.end) == (30, 40)
        assert span.id is not None
        loaded = Span.get_by_id(span.id)
        assert loaded is not None
        assert (loaded.start, loaded.end) == (30, 40)

    @pytest.mark.filterwarnings(
        "ignore:Field name .* shadows an attribute:UserWarning",
    )
    def test_shadowed_field_patches_via_kwargs(self, db: TinyDB):
        """Kwargs reach opted-in shadowed fields."""

        class Command(
            TinydanticModel,
            database=db,
            shadowed_fields=("search",),
        ):
            """Test model with an opted-in shadowed field."""

            name: str
            search: str  # type: ignore[assignment]

        command = Command(name="grep", search="fuzzy").insert()
        command.patch(search="regex")
        found = Command.get(field(Command, "search") == "regex")
        assert found is not None
        assert found.id == command.id


class TestPatchErrors:
    """patch() error paths reuse the curated exceptions."""

    def test_never_inserted(self, db: TinyDB):
        """patch() before insert raises DocumentIDRequiredError."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        with pytest.raises(DocumentIDRequiredError, match="patch"):
            Book(title="Dune").patch(title="Dune!")

    def test_vanished_document(self, db: TinyDB):
        """patch() on a deleted document raises, self untouched."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        book.delete()
        with pytest.raises(DocumentNotFoundError):
            book.patch(title="Dune!")
        assert book.title == "Dune"

    def test_id_key_rejected(self, db: TinyDB):
        """patch(id=...) raises DocumentIDUpdateError."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        with pytest.raises(DocumentIDUpdateError):
            book.patch(id=99)

    def test_unknown_field_rejected_nothing_written(self, db: TinyDB):
        """Unknown kwargs raise; storage stays clean."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        with pytest.raises(UnknownUpdateFieldError, match="shelf"):
            book.patch(shelf="A3")
        assert book.id is not None
        raw = Book.get_table().get(doc_id=book.id)
        assert isinstance(raw, dict)
        assert "shelf" not in raw

    def test_failed_validation_touches_nothing(self, db: TinyDB):
        """A bad value leaves storage and self unchanged."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            year: int

        book = Book(year=1965).insert()
        with pytest.raises(ValidationError):
            book.patch(year="not a year")  # type: ignore[arg-type]
        assert book.year == 1965
        assert book.id is not None
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.year == 1965

    def test_invariant_violation_touches_nothing(self, db: TinyDB):
        """A merged-result violation aborts before writing."""

        class Span(TinydanticModel, database=db):
            """Test model with a cross-field invariant."""

            start: int
            end: int

            @model_validator(mode="after")
            def ordered(self) -> Span:
                """Require end >= start."""
                if self.end < self.start:
                    msg = "end must be >= start"
                    raise ValueError(msg)
                return self

        span = Span(start=10, end=20).insert()
        with pytest.raises(ValidationError):
            span.patch(end=5)
        assert span.end == 20
        assert span.id is not None
        loaded = Span.get_by_id(span.id)
        assert loaded is not None
        assert loaded.end == 20

    def test_validate_writes_false_skips_invariants(self, db: TinyDB):
        """The knob restores per-field-only validation."""

        class Span(TinydanticModel, database=db, validate_writes=False):
            """Test model with write validation off."""

            start: int
            end: int

            @model_validator(mode="after")
            def ordered(self) -> Span:
                """Require end >= start."""
                if self.end < self.start:
                    msg = "end must be >= start"
                    raise ValueError(msg)
                return self

        span = Span(start=10, end=20).insert()
        span.patch(end=5)
        assert span.id is not None
        raw = Span.get_table().get(doc_id=span.id)
        assert isinstance(raw, dict)
        assert raw["end"] == 5


class TestEmptyPatch:
    """patch() with no fields checks existence, writes nothing."""

    def test_noop_on_live_document(self, db: TinyDB):
        """An empty patch of a live document returns self."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.patch() is book

    def test_raises_on_vanished_document(self, db: TinyDB):
        """An empty patch of a vanished document still raises."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        book.delete()
        with pytest.raises(DocumentNotFoundError):
            book.patch()
