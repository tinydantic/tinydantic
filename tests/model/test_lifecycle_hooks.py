# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""before_save/after_load lifecycle hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

import pytest

from tinydantic import TinydanticModel, q

if TYPE_CHECKING:
    from tinydb import TinyDB


class Hooked(TinydanticModel):
    """Test model counting hook invocations."""

    name: str
    stamped: int = 0

    saves: ClassVar[list[str]] = []
    loads: ClassVar[list[int | None]] = []

    def before_save(self) -> None:
        """Count the write and stamp a field."""
        type(self).saves.append(self.name)
        self.stamped += 1

    def after_load(self) -> None:
        """Record the id visible at load time."""
        type(self).loads.append(self.id)


@pytest.fixture
def hooked(db: TinyDB) -> type[Hooked]:
    """Hooked bound to the test database, counters reset."""

    class Bound(Hooked, database=db):
        """Bound test model."""

    Bound.saves = []
    Bound.loads = []
    return Bound


class TestBeforeSave:
    """before_save() fires once per whole-model write."""

    def test_insert_fires_once_and_persists_mutation(
        self,
        hooked: type[Hooked],
    ):
        """insert() calls the hook; its mutation is stored."""
        doc = hooked(name="a").insert()
        assert hooked.saves == ["a"]
        assert doc.stamped == 1
        assert doc.id is not None
        loaded = hooked.get_by_id(doc.id)
        assert loaded is not None
        assert loaded.stamped == 1

    def test_save_of_new_instance_fires_exactly_once(
        self,
        hooked: type[Hooked],
    ):
        """save() delegating to insert() never double-fires."""
        hooked(name="a").save()
        assert hooked.saves == ["a"]

    def test_save_of_existing_fires_once(self, hooked: type[Hooked]):
        """save() on a persisted instance fires the hook."""
        doc = hooked(name="a").insert()
        doc.save()
        assert hooked.saves == ["a", "a"]
        assert doc.stamped == 2

    def test_replace_fires(self, hooked: type[Hooked]):
        """replace() fires the hook."""
        doc = hooked(name="a").insert()
        doc.replace()
        assert hooked.saves == ["a", "a"]

    def test_upsert_fires(self, hooked: type[Hooked]):
        """upsert() fires the hook on the passed document."""
        hooked.upsert(hooked(name="a"), q(hooked.name) == "a")
        assert hooked.saves == ["a"]

    def test_insert_multiple_fires_per_document(
        self,
        hooked: type[Hooked],
    ):
        """insert_multiple() fires once per document."""
        hooked.insert_multiple([hooked(name="a"), hooked(name="b")])
        assert hooked.saves == ["a", "b"]

    def test_update_and_patch_do_not_fire(self, hooked: type[Hooked]):
        """Field-level writes never call before_save()."""
        doc = hooked(name="a").insert()
        hooked.saves.clear()
        assert doc.id is not None
        hooked.update({"name": "b"}, doc_ids=[doc.id])
        doc.patch(name="c")
        assert hooked.saves == []

    def test_raising_hook_aborts_write(self, db: TinyDB):
        """An exception in before_save() writes nothing."""

        class Guarded(TinydanticModel, database=db):
            """Test model whose hook refuses."""

            name: str

            def before_save(self) -> None:
                """Refuse every write."""
                msg = "nope"
                raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="nope"):
            Guarded(name="a").insert()
        assert Guarded.count() == 0


class TestAfterLoad:
    """after_load() fires on reads, with the real id."""

    def test_get_and_search_and_all_fire(self, hooked: type[Hooked]):
        """Every materializing read calls the hook once per doc."""
        doc = hooked(name="a").insert()
        hooked.loads.clear()
        assert doc.id is not None
        hooked.get_by_id(doc.id)
        hooked.search(q(hooked.name) == "a")
        hooked.all()
        assert hooked.loads == [doc.id, doc.id, doc.id]

    def test_not_called_on_construction_or_insert(
        self,
        hooked: type[Hooked],
    ):
        """Constructing and inserting never call after_load()."""
        hooked(name="a").insert()
        assert hooked.loads == []

    def test_mutations_are_not_persisted(self, db: TinyDB):
        """after_load() changes affect the instance only."""

        class Shouter(TinydanticModel, database=db):
            """Test model rewriting a field at load."""

            name: str

            def after_load(self) -> None:
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

            def before_save(self) -> None:
                """Record the base call."""
                calls.append("base")

        class Child(Base, table_name="children"):
            """Child chaining to the base hook."""

            def before_save(self) -> None:
                """Record the child call, then chain."""
                calls.append("child")
                super().before_save()

        Child(name="a").insert()
        assert calls == ["child", "base"]
