# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for models with pydantic field aliases.

Storage keys are always python field names; aliases exist only at
the user's external boundary. tinydantic validates with
``by_name=True`` at its internal boundaries so aliased models
round-trip without requiring ``validate_by_name`` on the model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import ConfigDict, Field
from pydantic.alias_generators import to_camel

from tinydantic import TinydanticModel

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestAliasedModelRoundTrip:
    """Aliased models store python field names and read them back."""

    def test_insert_and_read_back(self, db: TinyDB):
        """The wire alias never blocks the storage round-trip."""

        class Person(TinydanticModel, database=db, table_name="people"):
            """Aliased test model."""

            first_name: str = Field(alias="firstName")

        person = Person(firstName="Ada").insert()
        loaded = Person.get_by_id(person.id)  # type: ignore[arg-type]
        assert loaded is not None
        assert loaded.first_name == "Ada"

    def test_storage_keys_are_field_names(self, db: TinyDB):
        """The stored body is keyed by python names, not aliases."""

        class Person(TinydanticModel, database=db, table_name="people"):
            """Aliased test model."""

            first_name: str = Field(alias="firstName")

        person = Person(firstName="Ada").insert()
        assert person.id is not None
        stored = db.table("people").get(doc_id=person.id)
        assert stored == {"first_name": "Ada"}

    def test_query_sugar_matches_storage(self, db: TinyDB):
        """Model.field queries hit the stored python-name keys."""

        class Person(TinydanticModel, database=db, table_name="people"):
            """Aliased test model."""

            first_name: str = Field(alias="firstName")

        Person(firstName="Ada").insert()
        found = Person.search(Person.first_name == "Ada")  # type: ignore[arg-type]
        assert len(found) == 1
        assert found[0].first_name == "Ada"

    def test_update_validates_merged_aliased_body(self, db: TinyDB):
        """Merged-result validation accepts python-name bodies."""

        class Person(TinydanticModel, database=db, table_name="people"):
            """Aliased test model."""

            first_name: str = Field(alias="firstName")
            city: str = "Portland"

        person = Person(firstName="Ada").insert()
        Person.update(
            {"city": "London"},
            Person.first_name == "Ada",  # type: ignore[arg-type]
        )
        loaded = Person.get_by_id(person.id)  # type: ignore[arg-type]
        assert loaded is not None
        assert loaded.city == "London"

    def test_patch_aliased_model(self, db: TinyDB):
        """patch() round-trips through the aliased model."""

        class Person(TinydanticModel, database=db, table_name="people"):
            """Aliased test model."""

            first_name: str = Field(alias="firstName")

        person = Person(firstName="Ada").insert()
        person.patch(first_name="Grace")
        loaded = Person.get_by_id(person.id)  # type: ignore[arg-type]
        assert loaded is not None
        assert loaded.first_name == "Grace"

    def test_validate_writes_false_reads_back(self, db: TinyDB):
        """The opt-out path can read what it wrote (regression)."""

        class Person(
            TinydanticModel,
            database=db,
            table_name="people",
            validate_writes=False,
        ):
            """Aliased test model without write validation."""

            first_name: str = Field(alias="firstName")

        person = Person(firstName="Ada").insert()
        loaded = Person.get_by_id(person.id)  # type: ignore[arg-type]
        assert loaded is not None
        assert loaded.first_name == "Ada"

    def test_alias_generator_model_round_trips(self, db: TinyDB):
        """A camelCase alias_generator model (FastAPI style) works."""

        class Person(TinydanticModel, database=db, table_name="people"):
            """Model with a model-wide alias generator."""

            model_config = ConfigDict(alias_generator=to_camel)

            first_name: str
            home_city: str

        person = Person(firstName="Ada", homeCity="London").insert()
        assert person.id is not None
        stored = db.table("people").get(doc_id=person.id)
        assert stored == {"first_name": "Ada", "home_city": "London"}
        loaded = Person.get_by_id(person.id)  # type: ignore[arg-type]
        assert loaded is not None
        assert loaded.home_city == "London"

    def test_wire_format_still_uses_aliases(self, db: TinyDB):
        """The user's external boundary is untouched by storage."""

        class Person(TinydanticModel, database=db, table_name="people"):
            """Aliased test model."""

            first_name: str = Field(alias="firstName")

        person = Person(firstName="Ada").insert()
        dumped = person.model_dump(by_alias=True)
        assert dumped == {"id": person.id, "firstName": "Ada"}
