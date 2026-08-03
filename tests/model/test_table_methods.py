# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the classmethod table surface."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

import pytest

from pydantic import ValidationError, model_validator

from tinydantic import (
    TinydanticModel,
    UnknownUpdateFieldError,
    q,
)
from tinydantic.tinydb.operations import replace

if TYPE_CHECKING:
    from collections.abc import (
        Callable,
        Mapping,
        MutableMapping,
    )

    from tinydb import TinyDB

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
        """Insert path sets id on the passed instance."""
        document = user_class(name="Alice", age=37)
        ids = user_class.upsert(
            document,
            user_class.name == "Alice",  # type: ignore[arg-type]
        )
        assert len(ids) == 1
        assert document.id == ids[0]
        fetched = user_class.get_by_id(ids[0])
        assert fetched is not None
        assert fetched.age == 37

    def test_upsert_updates_when_matched(self, user_class: type[UserBase]):
        """Update path keeps the document id and links the instance."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        document = user_class(name="Alice", age=99)
        ids = user_class.upsert(
            document,
            user_class.name == "Alice",  # type: ignore[arg-type]
        )
        assert ids == [user.id]
        assert document.id == user.id
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None
        assert fetched.age == 99

    def test_upsert_multiple_matches_leaves_id_unset(
        self,
        user_class: type[UserBase],
    ):
        """Updating several documents is ambiguous — id stays unset."""
        user_class(name="Alice", age=1).insert()
        user_class(name="Alice", age=2).insert()
        document = user_class(name="Alice", age=99)
        ids = user_class.upsert(
            document,
            user_class.name == "Alice",  # type: ignore[arg-type]
        )
        assert len(ids) == 2
        assert document.id is None

    def test_upsert_without_cond_keeps_id(
        self,
        user_class: type[UserBase],
    ):
        """The no-cond form (upsert by preset id) keeps the id."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        user.age = 38
        ids = user_class.upsert(user)
        assert ids == [user.id]
        assert user.id == ids[0]


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


class TestUpdateExtraKeys:
    """update() mappings reject unknown keys by default."""

    def test_update_rejects_unknown_keys(self, db: TinyDB):
        """Unknown mapping keys raise UnknownUpdateFieldError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="Al").insert()
        with pytest.raises(UnknownUpdateFieldError, match="gadget"):
            User.update({"gadget": 1}, q(User.name) == "Al")
        raw = User.get_table().get(doc_id=user.id)
        assert isinstance(raw, dict)
        assert "gadget" not in raw

    def test_update_extra_keys_allow(self, db: TinyDB):
        """extra_keys='allow' passes unknown keys through."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="Al").insert()
        User.update(
            {"gadget": 1},
            q(User.name) == "Al",
            extra_keys="allow",
        )
        raw = User.get_table().get(doc_id=user.id)
        assert isinstance(raw, dict)
        assert raw["gadget"] == 1

    def test_update_multiple_rejects_unknown_keys(self, db: TinyDB):
        """update_multiple() applies the same default."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        User(name="Al").insert()
        with pytest.raises(UnknownUpdateFieldError, match="gadget"):
            User.update_multiple(
                [({"gadget": 1}, q(User.name) == "Al")],
            )

    def test_update_multiple_extra_keys_allow(self, db: TinyDB):
        """update_multiple() honors extra_keys='allow'."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="Al").insert()
        User.update_multiple(
            [({"gadget": 1}, q(User.name) == "Al")],
            extra_keys="allow",
        )
        raw = User.get_table().get(doc_id=user.id)
        assert isinstance(raw, dict)
        assert raw["gadget"] == 1

    def test_error_names_all_unknown_keys(self, db: TinyDB):
        """The error message lists every offending key."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        User(name="Al").insert()
        with pytest.raises(
            UnknownUpdateFieldError,
            match="'gadget', 'widget'",
        ):
            User.update(
                {"widget": 1, "gadget": 2, "name": "Bo"},
                q(User.name) == "Al",
            )


class TestUpdateMergedValidation:
    """update() validates each matched document's merged result."""

    def test_mapping_enforces_cross_field_invariants(self, db: TinyDB):
        """A merged result violating an after-validator is refused."""

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

        event = Event(start=10, end=20).insert()
        with pytest.raises(ValidationError):
            Event.update({"end": 5}, q(Event.start) == 10)
        assert event.id is not None
        loaded = Event.get_by_id(event.id)
        assert loaded is not None
        assert loaded.end == 20

    def test_transform_output_is_validated(self, db: TinyDB):
        """Transform callables can no longer write junk by default."""

        class User(TinydanticModel, database=db):
            """Test model."""

            age: int

        user = User(age=30).insert()

        def poison(body: MutableMapping) -> None:
            """Write an invalid age."""
            body["age"] = "junk"

        with pytest.raises(ValidationError):
            User.update(
                # TinyDB annotates transforms with Mapping though it
                # passes a mutable dict; same cast as replace().
                cast("Callable[[Mapping], None]", poison),
                q(User.age) == 30,
            )
        assert user.id is not None
        loaded = User.get_by_id(user.id)
        assert loaded is not None
        assert loaded.age == 30

    def test_validation_failure_aborts_whole_batch(self, db: TinyDB):
        """One bad merged result means nothing is written."""

        class Item(TinydanticModel, database=db):
            """Test model."""

            name: str
            qty: int

        Item(name="a", qty=1).insert()
        Item(name="b", qty=2).insert()

        def poison_b(body: MutableMapping) -> None:
            """Corrupt only document b."""
            body["qty"] = "junk" if body["name"] == "b" else 99

        with pytest.raises(ValidationError):
            Item.update(
                # TinyDB annotates transforms with Mapping though it
                # passes a mutable dict; same cast as replace().
                cast("Callable[[Mapping], None]", poison_b),
            )
        assert sorted(item.qty for item in Item.all()) == [1, 2]

    def test_update_preserves_stored_extra_keys(self, db: TinyDB):
        """Merged validation ignores and preserves stored extras."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="Al").insert()
        assert user.id is not None
        User.update({"legacy": "kept"}, doc_ids=[user.id], extra_keys="allow")
        User.update({"name": "Bob"}, doc_ids=[user.id])
        raw = User.get_table().get(doc_id=user.id)
        assert isinstance(raw, dict)
        assert raw["name"] == "Bob"
        assert raw["legacy"] == "kept"

    def test_merged_validators_see_real_id(self, db: TinyDB):
        """Merged validation runs with the target doc_id visible."""

        class Audited(TinydanticModel, database=db):
            """Test model recording the id its validator saw."""

            name: str
            seen_id: int | None = None

            @model_validator(mode="after")
            def record_id(self) -> Audited:
                """Record the id visible during validation."""
                self.__dict__["seen_id"] = self.id
                return self

        recorder: list[int | None] = []

        class Spy(Audited, database=db, table_name="spy"):
            """Test model reporting ids seen during validation."""

            @model_validator(mode="after")
            def report(self) -> Spy:
                """Report the id visible during validation."""
                recorder.append(self.id)
                return self

        spy = Spy(name="x").insert()
        recorder.clear()
        Spy.update({"name": "y"}, doc_ids=[spy.id] if spy.id else None)
        assert spy.id in recorder

    def test_update_multiple_enforces_invariants(self, db: TinyDB):
        """update_multiple() validates merged results per pair."""

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

        event = Event(start=10, end=20).insert()
        with pytest.raises(ValidationError):
            Event.update_multiple([({"end": 5}, q(Event.start) == 10)])
        assert event.id is not None
        loaded = Event.get_by_id(event.id)
        assert loaded is not None
        assert loaded.end == 20

    def test_validate_writes_false_restores_old_update(self, db: TinyDB):
        """The knob restores per-field-only update validation."""

        class Event(TinydanticModel, database=db, validate_writes=False):
            """Test model with write validation off."""

            start: int
            end: int

            @model_validator(mode="after")
            def ordered(self) -> Event:
                """Require end >= start."""
                if self.end < self.start:
                    msg = "end must be >= start"
                    raise ValueError(msg)
                return self

        event = Event(start=10, end=20).insert()
        Event.update({"end": 5}, q(Event.start) == 10)
        raw = Event.get_table().get(doc_id=event.id)
        assert isinstance(raw, dict)
        assert raw["end"] == 5
