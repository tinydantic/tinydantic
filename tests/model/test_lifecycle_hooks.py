# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""before_write/after_read lifecycle hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from uuid import uuid4

import pytest

from tinydantic import (
    DocumentIDUpdateError,
    RevisionUpdateError,
    TinydanticModel,
    UnknownUpdateFieldError,
    q,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from tinydb import TinyDB


class Hooked(TinydanticModel):
    """Test model recording hook invocations."""

    name: str
    stamped: int = 0

    writes: ClassVar[list[str]] = []
    seen: ClassVar[list[Mapping[str, Any]]] = []

    def before_write(
        self,
        fields: Mapping[str, Any],
    ) -> Mapping[str, Any] | None:
        """Record the write and stamp a field."""
        type(self).writes.append(self.name)
        type(self).seen.append(dict(fields))
        return {"stamped": self.stamped + 1}


@pytest.fixture
def hooked(db: TinyDB) -> type[Hooked]:
    """Hooked bound to the test database, recorders reset."""

    class Bound(Hooked, database=db):
        """Bound test model."""

    Bound.writes = []
    Bound.seen = []
    return Bound


class TestBeforeWriteContract:
    """before_write() contributes fields to the write."""

    def test_insert_fires_once_and_persists_returned_field(
        self,
        hooked: type[Hooked],
    ):
        """insert() calls the hook; its return value is stored."""
        doc = hooked(name="a").insert()
        assert hooked.writes == ["a"]
        assert doc.stamped == 1
        assert doc.id is not None
        loaded = hooked.get_by_id(doc.id)
        assert loaded is not None
        assert loaded.stamped == 1

    def test_whole_model_write_sees_every_field(
        self,
        hooked: type[Hooked],
    ):
        """Fields holds all model fields, never id."""
        hooked(name="a").insert()
        assert hooked.seen == [{"name": "a", "stamped": 0}]


class TestBeforeWriteOnPatch:
    """patch() fires the hook — the H4 regression."""

    def test_patch_fires_once(self, hooked: type[Hooked]):
        """patch() calls the hook."""
        doc = hooked(name="a").insert()
        hooked.writes.clear()
        doc.patch(name="b")
        assert hooked.writes == ["a"]

    def test_patch_sees_only_the_caller_fields(
        self,
        hooked: type[Hooked],
    ):
        """Fields holds the patched fields, not the whole model."""
        doc = hooked(name="a").insert()
        hooked.seen.clear()
        doc.patch(name="b")
        assert hooked.seen == [{"name": "b"}]

    def test_patch_persists_returned_field(self, hooked: type[Hooked]):
        """A field the hook returns is written by patch()."""
        doc = hooked(name="a").insert()
        assert doc.stamped == 1
        doc.patch(name="b")
        assert doc.stamped == 2
        assert doc.id is not None
        loaded = hooked.get_by_id(doc.id)
        assert loaded is not None
        assert loaded.stamped == 2
        assert loaded.name == "b"

    def test_empty_patch_does_not_fire(self, hooked: type[Hooked]):
        """An empty patch() writes nothing, so it hooks nothing."""
        doc = hooked(name="a").insert()
        hooked.writes.clear()
        doc.patch()
        assert hooked.writes == []
        assert doc.stamped == 1


class TestBeforeWriteCoverage:
    """Which write paths fire the hook, and which do not."""

    def test_save_of_new_instance_fires_exactly_once(
        self,
        hooked: type[Hooked],
    ):
        """save() delegating to insert() never double-fires."""
        hooked(name="a").save()
        assert hooked.writes == ["a"]

    def test_save_of_existing_fires(self, hooked: type[Hooked]):
        """save() on a persisted instance fires the hook."""
        doc = hooked(name="a").insert()
        doc.save()
        assert hooked.writes == ["a", "a"]
        assert doc.stamped == 2

    def test_replace_fires(self, hooked: type[Hooked]):
        """replace() fires the hook."""
        doc = hooked(name="a").insert()
        doc.replace()
        assert hooked.writes == ["a", "a"]
        assert doc.stamped == 2

    def test_upsert_fires(self, hooked: type[Hooked]):
        """upsert() fires the hook on the passed document."""
        hooked.upsert(hooked(name="a"), q(hooked.name) == "a")
        assert hooked.writes == ["a"]

    def test_insert_multiple_fires_per_document(
        self,
        hooked: type[Hooked],
    ):
        """insert_many() fires once per document."""
        docs = hooked.insert_many([hooked(name="a"), hooked(name="b")])
        assert hooked.writes == ["a", "b"]
        assert [doc.stamped for doc in docs] == [1, 1]

    def test_update_does_not_fire(self, hooked: type[Hooked]):
        """Table-level update() has no instance, so no hook."""
        doc = hooked(name="a").insert()
        hooked.writes.clear()
        assert doc.id is not None
        hooked.update_by_ids({"name": "b"}, [doc.id])
        assert hooked.writes == []

    def test_update_all_does_not_fire(self, hooked: type[Hooked]):
        """Table-level update_all() has no instance, so no hook."""
        hooked(name="a").insert()
        hooked.writes.clear()
        hooked.update_all({"name": "b"})
        assert hooked.writes == []


class TestBeforeWriteReturnValue:
    """Rules applied to what the hook hands back."""

    def test_returning_none_writes_normally(self, db: TinyDB):
        """A hook contributing nothing does not disturb the write."""

        class Quiet(TinydanticModel, database=db):
            """Test model whose hook contributes nothing."""

            name: str

            def before_write(
                self,
                fields: Mapping[str, Any],  # noqa: ARG002
            ) -> Mapping[str, Any] | None:
                """Contribute nothing."""
                return None

        doc = Quiet(name="a").insert()
        assert doc.id is not None
        loaded = Quiet.get_by_id(doc.id)
        assert loaded is not None
        assert loaded.name == "a"

    def test_returning_id_raises(self, db: TinyDB):
        """The hook may not set the document id."""

        class Forger(TinydanticModel, database=db):
            """Test model whose hook returns id."""

            name: str

            def before_write(
                self,
                fields: Mapping[str, Any],  # noqa: ARG002
            ) -> Mapping[str, Any] | None:
                """Try to set the document id."""
                return {"id": 99}

        with pytest.raises(DocumentIDUpdateError):
            Forger(name="a").insert()
        assert Forger.count() == 0

    def test_returning_revision_id_raises(self, db: TinyDB):
        """The hook may not set the revision token."""

        class Rotator(
            TinydanticModel,
            database=db,
            use_revision=True,
        ):
            """Test model whose hook returns revision_id."""

            name: str

            def before_write(
                self,
                fields: Mapping[str, Any],  # noqa: ARG002
            ) -> Mapping[str, Any] | None:
                """Try to set the revision token."""
                return {"revision_id": uuid4()}

        with pytest.raises(RevisionUpdateError):
            Rotator(name="a").insert()
        assert Rotator.count() == 0

    def test_returning_unknown_field_raises(self, db: TinyDB):
        """The hook may only contribute model fields."""

        class Stray(TinydanticModel, database=db):
            """Test model whose hook returns a stray key."""

            name: str

            def before_write(
                self,
                fields: Mapping[str, Any],  # noqa: ARG002
            ) -> Mapping[str, Any] | None:
                """Contribute a field the model does not have."""
                return {"nope": 1}

        with pytest.raises(UnknownUpdateFieldError):
            Stray(name="a").insert()
        assert Stray.count() == 0


class TestBeforeWriteAborts:
    """A raising hook leaves storage untouched."""

    def test_raising_hook_aborts_insert(self, db: TinyDB):
        """An exception in before_write() writes nothing."""

        class Guarded(TinydanticModel, database=db):
            """Test model whose hook refuses."""

            name: str

            def before_write(
                self,
                fields: Mapping[str, Any],  # noqa: ARG002
            ) -> Mapping[str, Any] | None:
                """Refuse every write."""
                msg = "nope"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="nope"):
            Guarded(name="a").insert()
        assert Guarded.count() == 0

    def test_raising_hook_aborts_patch(self, db: TinyDB):
        """A hook that refuses on patch() writes nothing."""

        class Fussy(TinydanticModel, database=db):
            """Test model whose hook refuses updates only."""

            name: str

            def before_write(
                self,
                fields: Mapping[str, Any],  # noqa: ARG002
            ) -> Mapping[str, Any] | None:
                """Refuse once the model is persisted."""
                if self.id is not None:
                    msg = "nope"
                    raise RuntimeError(msg)
                return None

        doc = Fussy(name="a").insert()
        with pytest.raises(RuntimeError, match="nope"):
            doc.patch(name="b")
        assert doc.name == "a"
        assert doc.id is not None
        stored = Fussy.get_by_id(doc.id)
        assert stored is not None
        assert stored.name == "a"


class TestUnhookedModelsSkipTheMachinery:
    """Models without an override pay nothing for the hook."""

    def test_write_fields_is_not_built(self, db: TinyDB):
        """A model with no override never builds the mapping."""

        class Plain(TinydanticModel, database=db):
            """Test model that does not override the hook."""

            name: str

            def _write_fields(self) -> dict[str, Any]:
                """Explode if the machinery runs at all."""
                msg = "should not be called"
                raise AssertionError(msg)

        doc = Plain(name="a").insert()
        assert doc.id is not None


class TestAfterRead:
    """after_read() fires on reads, with the real id."""

    def test_get_and_search_and_all_fire(self, db: TinyDB):
        """Every materializing read calls the hook once per doc."""
        loads: list[int | None] = []

        class Watched(TinydanticModel, database=db):
            """Test model recording load-time ids."""

            name: str

            def after_read(self) -> None:
                """Record the id visible at load time."""
                loads.append(self.id)

        doc = Watched(name="a").insert()
        loads.clear()
        assert doc.id is not None
        Watched.get_by_id(doc.id)
        Watched.search(q(Watched.name) == "a")
        Watched.all()
        assert loads == [doc.id, doc.id, doc.id]

    def test_not_called_on_construction_or_insert(self, db: TinyDB):
        """Constructing and inserting never call after_read()."""
        loads: list[int | None] = []

        class Quiet(TinydanticModel, database=db):
            """Test model recording load-time ids."""

            name: str

            def after_read(self) -> None:
                """Record the id visible at load time."""
                loads.append(self.id)

        Quiet(name="a").insert()
        assert loads == []

    def test_mutations_are_not_persisted(self, db: TinyDB):
        """after_read() changes affect the instance only."""

        class Shouter(TinydanticModel, database=db):
            """Test model rewriting a field at load."""

            name: str

            def after_read(self) -> None:
                """Uppercase the name on the loaded instance."""
                self.name = self.name.upper()

        doc = Shouter(name="a").insert()
        assert doc.id is not None
        loaded = Shouter.get_by_id(doc.id)
        assert loaded is not None
        assert loaded.name == "A"
        raw = Shouter.get_table().get(doc_id=doc.id)
        assert isinstance(raw, dict)
        assert raw["name"] == "a"


class TestSuperChaining:
    """Overrides can cooperate via super()."""

    def test_subclass_chains_to_parent_hook(self, db: TinyDB):
        """A subclass hook calling super() runs both."""
        calls: list[str] = []

        class Base(TinydanticModel, database=db):
            """Base with a hook."""

            name: str

            def before_write(
                self,
                fields: Mapping[str, Any],  # noqa: ARG002
            ) -> Mapping[str, Any] | None:
                """Record the base call."""
                calls.append("base")
                return None

        class Child(Base, table_name="children"):
            """Child chaining to the base hook."""

            def before_write(
                self,
                fields: Mapping[str, Any],
            ) -> Mapping[str, Any] | None:
                """Record the child call, then chain."""
                calls.append("child")
                return super().before_write(fields)

        Child(name="a").insert()
        assert calls == ["child", "base"]
