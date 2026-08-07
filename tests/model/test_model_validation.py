# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for validating TinyDB documents into models."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest
import tinydb.table

from pydantic import ConfigDict, ValidationError, model_validator

from tinydantic import TinydanticModel

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
        Mapping,
        MutableMapping,
    )

    from tinydb import TinyDB

    from tests.model.models import UserBase


class TestModelValidation:
    """Tests for TinydanticModel.from_tinydb_document."""

    def test_validate_document_from_dict(self, user_class: type[UserBase]):
        """A plain dict validates into a model with id left unset."""
        tinydb_document = {
            "name": "Alice",
            "age": 37,
        }
        user = user_class.from_tinydb_document(tinydb_document)
        assert user.name == "Alice"
        assert user.age == 37

    def test_validate_document_from_tinydb_document(
        self,
        user_class: type[UserBase],
    ):
        """A TinyDB Document validates with its doc_id mapped to id."""
        tinydb_document = tinydb.table.Document(
            value={
                "name": "Alice",
                "age": 37,
            },
            doc_id=0,
        )
        user = user_class.from_tinydb_document(tinydb_document)
        assert user.name == "Alice"
        assert user.age == 37
        assert user.id == 0


class TestValidationSeesRealID:
    """Read validation observes the document's real id."""

    def test_after_validator_sees_real_id_on_read(self, db: TinyDB):
        """model_validator(mode='after') observes doc_id on reads."""

        class Audited(TinydanticModel, database=db):
            """Test model recording the id its validator saw."""

            name: str
            seen_id: int | None = None

            @model_validator(mode="after")
            def record_id(self) -> Audited:
                """Record the id visible during validation."""
                object.__setattr__(self, "seen_id", self.id)
                return self

        doc_id = Audited(name="x").insert().id
        assert doc_id is not None
        loaded = Audited.get_by_id(doc_id)
        assert loaded is not None
        assert loaded.seen_id == doc_id

    def test_stray_body_id_is_masked_by_doc_id(self, db: TinyDB):
        """A legacy body 'id' key never overrides the real doc_id."""

        class Legacy(TinydanticModel, database=db):
            """Test model reading a body with a stray id key."""

            name: str

        doc_id = Legacy(name="x").insert().id
        assert doc_id is not None

        def plant_stray_id(body: MutableMapping) -> None:
            """Write a stray id key into the stored body."""
            body["id"] = 999

        Legacy.get_table().update(
            # TinyDB annotates the transform with Mapping though it
            # passes a mutable dict; same cast band-aid as replace().
            cast("Callable[[Mapping], None]", plant_stray_id),
            doc_ids=[doc_id],
        )
        loaded = Legacy.get_by_id(doc_id)
        assert loaded is not None
        assert loaded.id == doc_id

    def test_plain_mapping_keeps_id_none(self, db: TinyDB):
        """A plain mapping still validates with id left unset."""

        class Plain(TinydanticModel, database=db):
            """Test model validated from a plain mapping."""

            name: str

        assert Plain.from_tinydb_document({"name": "x"}).id is None


class TestAssignmentValidation:
    """Attribute assignment validates by default."""

    def test_assignment_validates(self, db: TinyDB):
        """Assigning an invalid value raises immediately."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            year: int

        book = Book(year=1965)
        with pytest.raises(ValidationError):
            book.year = "not a year"  # type: ignore[assignment]
        assert book.year == 1965

    def test_assignment_coerces(self, db: TinyDB):
        """Coercible assigned values are validated and converted."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            year: int

        book = Book(year=1965)
        book.year = "1966"  # type: ignore[assignment]
        assert book.year == 1966

    def test_assignment_runs_after_validators(self, db: TinyDB):
        """Cross-field invariants re-run on assignment."""

        class Event(TinydanticModel, database=db):
            """Test model with a cross-field invariant."""

            start: int
            end: int

            @model_validator(mode="after")
            def ordered(self) -> Event:
                """Require end >= start."""
                if self.end < self.start:
                    msg = "end must be >= start"
                    raise ValueError(msg)
                return self

        event = Event(start=1, end=2)
        with pytest.raises(ValidationError):
            event.end = 0

    def test_subclass_can_opt_out(self, db: TinyDB):
        """validate_assignment=False restores loose assignment."""

        class Loose(TinydanticModel, database=db):
            """Test model opting out of assignment validation."""

            model_config = ConfigDict(validate_assignment=False)

            year: int

        loose = Loose(year=1)
        loose.year = "junk"  # type: ignore[assignment]
        assert loose.year == "junk"
