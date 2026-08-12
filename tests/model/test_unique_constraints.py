# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for composite unique constraints (``UniqueConstraint``)."""

from __future__ import annotations

import datetime

from typing import Annotated, cast

import pytest

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from tinydantic import (
    ConstraintFieldError,
    TinydanticModel,
    Unique,
    UniqueConstraint,
    UniqueConstraintError,
    q,
)


class TestUniqueConstraintConstruction:
    """Constructor validation happens before any model context."""

    def test_fields_and_key_are_stored(self) -> None:
        """Fields land as a tuple; key is kept as passed."""
        constraint = UniqueConstraint("a", "b", key=str.casefold)
        assert constraint.fields == ("a", "b")
        assert constraint.key is str.casefold

    def test_key_defaults_to_none(self) -> None:
        """No key means exact-match comparison."""
        assert UniqueConstraint("a").key is None

    def test_zero_fields_raises(self) -> None:
        """A constraint over nothing is meaningless."""
        with pytest.raises(ValueError, match="at least one field"):
            UniqueConstraint()

    def test_duplicate_fields_raise(self) -> None:
        """Repeating a field is a typo, not a wider constraint."""
        with pytest.raises(ValueError, match="duplicate"):
            UniqueConstraint("a", "b", "a")

    def test_non_callable_key_raises(self) -> None:
        """``key=`` must be callable."""
        with pytest.raises(ValueError, match="callable"):
            UniqueConstraint("a", key="casefold")  # type: ignore[arg-type]

    def test_frozen(self) -> None:
        """Constraints are immutable."""
        constraint = UniqueConstraint("a")
        with pytest.raises(AttributeError):
            constraint.fields = ("b",)  # type: ignore[misc]

    def test_unique_marker_non_callable_key_raises(self) -> None:
        """``Unique(key=...)`` validates the same way."""
        with pytest.raises(ValueError, match="callable"):
            Unique(key="casefold")  # type: ignore[arg-type]

    def test_unique_marker_key_defaults_to_none(self) -> None:
        """The bare marker keeps exact-match semantics."""
        assert Unique().key is None


class TestErrorMessages:
    """UniqueConstraintError renders tuples honestly."""

    def test_singular_wording_preserved(self) -> None:
        """One key-less field keeps today's exact message shape."""
        err = UniqueConstraintError(
            model_name="User",
            table_name="user",
            fields=("email",),
            values=("a@x.io",),
            doc_id=3,
        )
        assert str(err) == (
            "Value 'a@x.io' for unique field 'email' already "
            "exists in table 'user' (model 'User') — held by "
            "document 3."
        )

    def test_composite_wording(self) -> None:
        """Composites pluralize and show both tuples."""
        err = UniqueConstraintError(
            model_name="Follow",
            table_name="follow",
            fields=("follower_id", "followee_id"),
            values=(3, 7),
            doc_id=4,
        )
        assert "Values (3, 7) for unique fields" in str(err)
        assert "('follower_id', 'followee_id')" in str(err)

    def test_comparison_key_shown_when_differing(self) -> None:
        """A normalizing key surfaces its computed key."""
        err = UniqueConstraintError(
            model_name="Article",
            table_name="article",
            fields=("author_id", "slug"),
            values=(7, "My-Slug"),
            comparison_key=(7, "my-slug"),
            doc_id=4,
        )
        assert "(comparison key (7, 'my-slug'))" in str(err)

    def test_no_clause_without_key(self) -> None:
        """Key-less (exact-match) errors carry no key clause."""
        err = UniqueConstraintError(
            model_name="A",
            table_name="a",
            fields=("x",),
            values=("v",),
            doc_id=1,
        )
        assert "comparison key" not in str(err)

    def test_batch_wording(self) -> None:
        """``doc_id=None`` names the batch, as today."""
        err = UniqueConstraintError(
            model_name="U",
            table_name="u",
            fields=("email",),
            values=("a@x.io",),
            doc_id=None,
        )
        assert "another document in the same batch" in str(err)


class TestDeclarationValidation:
    """Bad constraints fail loudly at definition or bind time."""

    def test_unknown_field_raises_at_class_definition(
        self,
        db: TinyDB,
    ) -> None:
        """A constraint naming a non-field is rejected."""
        with pytest.raises(ConstraintFieldError, match="typo"):

            class Bad(
                TinydanticModel,
                database=db,
                constraints=(UniqueConstraint("typo"),),
            ):
                """Test model with a misspelled constraint."""

                real: int

    def test_id_field_raises_at_class_definition(
        self,
        db: TinyDB,
    ) -> None:
        """``id`` is never in the body — silent-non-match trap."""
        with pytest.raises(ConstraintFieldError, match="'id'"):

            class Bad(
                TinydanticModel,
                database=db,
                constraints=(UniqueConstraint("id", "a"),),
            ):
                """Test model constraining the id field."""

                a: int

    def test_bind_validates_constraints(self, db: TinyDB) -> None:
        """Late binding gets the same loud validation."""

        class Late(TinydanticModel):
            """Test model bound after definition."""

            a: int

        with pytest.raises(ConstraintFieldError, match="typo"):
            Late.bind(
                database=db,
                constraints=(UniqueConstraint("typo"),),
            )

    def test_nearest_wins_inheritance(self, db: TinyDB) -> None:
        """A subclass's ``constraints=`` replaces its parent's."""

        class Parent(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model declaring a pair constraint."""

            a: int
            b: int

        class Child(Parent, table_name="child", constraints=()):
            """Subclass suppressing the inherited constraint."""

        Child(a=1, b=2).insert()
        Child(a=1, b=2).insert()  # no constraint — allowed
        Parent(a=1, b=2).insert()
        with pytest.raises(UniqueConstraintError):
            Parent(a=1, b=2).insert()

    def test_unbind_restores_parent(self, db: TinyDB) -> None:
        """``unbind('constraints')`` resurfaces inherited config."""

        class Base(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a"),),
        ):
            """Test model declaring a single-field constraint."""

            a: int

        class Sub(Base, table_name="sub"):
            """Subclass inheriting the constraint."""

        Sub.bind(constraints=())
        Sub(a=1).insert()
        Sub(a=1).insert()  # constraint suppressed
        Sub.unbind("constraints")
        with pytest.raises(UniqueConstraintError):
            Sub(a=1).insert()


class TestCompositeEnforcement:
    """Pair uniqueness on the instance-level write paths."""

    def test_duplicate_pair_insert_raises(self, db: TinyDB) -> None:
        """The same (a, b) pair twice is rejected."""

        class Follow(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int

        Follow(a=3, b=7).insert()
        with pytest.raises(UniqueConstraintError) as exc:
            Follow(a=3, b=7).insert()
        assert "Values (3, 7)" in str(exc.value)
        assert Follow.count() == 1

    def test_distinct_pairs_pass(self, db: TinyDB) -> None:
        """Sharing one member of the pair is not a clash."""

        class Follow(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int

        Follow(a=3, b=7).insert()
        Follow(a=3, b=8).insert()
        Follow(a=4, b=7).insert()
        assert Follow.count() == 3

    def test_any_none_member_exempts(self, db: TinyDB) -> None:
        """``(1, None)`` twice is allowed; ``key=`` never runs."""
        calls: list[tuple[object, ...]] = []

        def spy(*values: object) -> tuple[object, ...]:
            """Record every invocation and return the tuple."""
            calls.append(values)
            return values

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b", key=spy),),
        ):
            """Test model with an optional constraint member."""

            a: int
            b: int | None = None

        M(a=1).insert()
        M(a=1).insert()
        assert M.count() == 2
        assert calls == []

    def test_casefold_key_rejects_case_variant(
        self,
        db: TinyDB,
    ) -> None:
        """('Chris', 7) then ('chris', 7) collides via the key."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(
                UniqueConstraint(
                    "name",
                    "org",
                    key=lambda n, o: (n.casefold(), o),
                ),
            ),
        ):
            """Test model with a case-insensitive pair."""

            name: str
            org: int

        M(name="Chris", org=7).insert()
        with pytest.raises(UniqueConstraintError) as exc:
            M(name="chris", org=7).insert()
        assert "comparison key ('chris', 7)" in str(exc.value)
        M(name="Chris", org=8).insert()

    def test_key_receives_serialized_values(
        self,
        db: TinyDB,
    ) -> None:
        """Datetimes arrive as ISO strings; ``[:10]`` is the date."""

        class Entry(
            TinydanticModel,
            database=db,
            constraints=(
                UniqueConstraint(
                    "user_id",
                    "at",
                    key=lambda uid, ts: (uid, ts[:10]),
                ),
            ),
        ):
            """Test model unique per user per calendar day."""

            user_id: int
            at: datetime.datetime

        Entry(
            user_id=1,
            at=datetime.datetime(2026, 8, 5, 9, 0),  # noqa: DTZ001
        ).insert()
        with pytest.raises(UniqueConstraintError):
            Entry(
                user_id=1,
                at=datetime.datetime(2026, 8, 5, 17, 30),  # noqa: DTZ001
            ).insert()
        Entry(
            user_id=1,
            at=datetime.datetime(2026, 8, 6, 9, 0),  # noqa: DTZ001
        ).insert()

    def test_exact_and_normalized_coexist(self, db: TinyDB) -> None:
        """Same field set, different keys: both enforce."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(
                UniqueConstraint("v"),
                UniqueConstraint("v", key=str.casefold),
            ),
        ):
            """Test model with exact plus normalized constraints."""

            v: str

        M(v="A").insert()
        with pytest.raises(UniqueConstraintError):
            M(v="a").insert()  # caught by the casefold constraint

    def test_field_order_dedupes(self, db: TinyDB) -> None:
        """('a','b') and ('b','a') key-less collapse to one.

        Behavioral proxy: both orders enforce identically and
        swapped values still count as a distinct pair.
        """

        class M(
            TinydanticModel,
            database=db,
            constraints=(
                UniqueConstraint("a", "b"),
                UniqueConstraint("b", "a"),
            ),
        ):
            """Test model with the same pair declared twice."""

            a: int
            b: int

        M(a=1, b=2).insert()
        with pytest.raises(UniqueConstraintError):
            M(a=1, b=2).insert()
        M(a=2, b=1).insert()

    def test_marker_key_enforces(self, db: TinyDB) -> None:
        """``Unique(key=str.casefold)`` on a single field."""

        class U(TinydanticModel, database=db):
            """Test model with a normalized single-field marker."""

            email: Annotated[str, Unique(key=str.casefold)]

        U(email="A@X.io").insert()
        with pytest.raises(UniqueConstraintError) as exc:
            U(email="a@x.IO").insert()
        assert "comparison key" in str(exc.value)

    def test_save_own_pair_ok_conflict_raises(
        self,
        db: TinyDB,
    ) -> None:
        """Re-writing a document's own pair is never a clash."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int
            note: str = ""

        first = M(a=1, b=2).insert()
        first.note = "still mine"
        first.save()

        second = M(a=1, b=3).insert()
        second.a, second.b = 1, 2
        with pytest.raises(UniqueConstraintError):
            second.save()
        with pytest.raises(UniqueConstraintError):
            second.replace()

    def test_update_bypass_pinned(self, db: TinyDB) -> None:
        """The table-level bulk path stays the documented bypass."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int
            tag: str = ""

        M(a=1, b=2).insert()
        target = M(a=9, b=9, tag="move").insert()
        assert target.id is not None
        M.update({"a": 1, "b": 2}, q(M.tag) == "move")
        moved = M.get_by_id(target.id)
        assert moved is not None
        assert (moved.a, moved.b) == (1, 2)

    def test_key_exception_propagates(self, db: TinyDB) -> None:
        """A raising key is a user bug — no wrapping."""

        class Boom(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", key=lambda _: 1 / 0),),
        ):
            """Test model whose key always raises."""

            a: int

        with pytest.raises(ZeroDivisionError):
            Boom(a=1).insert()


class TestBatchAndUpsert:
    """Constraint enforcement on the batch and upsert paths."""

    def test_insert_multiple_intra_batch_duplicate_aborts(
        self,
        db: TinyDB,
    ) -> None:
        """A duplicate computed key inside a batch writes nothing."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(
                UniqueConstraint(
                    "a",
                    "b",
                    key=lambda a, b: (a, b.casefold()),
                ),
            ),
        ):
            """Test model with a normalized pair constraint."""

            a: int
            b: str

        with pytest.raises(UniqueConstraintError) as exc:
            M.insert_many(
                [M(a=1, b="X"), M(a=2, b="y"), M(a=1, b="x")],
            )
        assert "same batch" in str(exc.value)
        assert "comparison key (1, 'x')" in str(exc.value)
        assert M.count() == 0

    def test_insert_multiple_against_stored_documents(
        self,
        db: TinyDB,
    ) -> None:
        """Batch inserts also clash with already-stored pairs."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int

        M(a=1, b=2).insert()
        with pytest.raises(UniqueConstraintError):
            M.insert_many([M(a=3, b=4), M(a=1, b=2)])
        assert M.count() == 1

    def test_upsert_multi_match_with_full_constraint_raises(
        self,
        db: TinyDB,
    ) -> None:
        """N matched docs cannot share one constrained tuple."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int
            tag: str

        M(a=1, b=1, tag="x").insert()
        M(a=2, b=2, tag="x").insert()
        with pytest.raises(UniqueConstraintError):
            M.upsert(M(a=9, b=9, tag="x"), q(M.tag) == "x")

    def test_upsert_single_match_novel_pair_ok(
        self,
        db: TinyDB,
    ) -> None:
        """One match plus a free pair updates cleanly."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int
            tag: str

        M(a=1, b=1, tag="x").insert()
        M.upsert(M(a=9, b=9, tag="x"), q(M.tag) == "x")
        got = M.get(q(M.tag) == "x")
        assert got is not None
        assert (got.a, got.b) == (9, 9)

    def test_upsert_stealing_a_stored_pair_raises(
        self,
        db: TinyDB,
    ) -> None:
        """An upsert cannot steal a different document's pair."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int
            tag: str

        M(a=1, b=1, tag="x").insert()
        M(a=2, b=2, tag="y").insert()
        with pytest.raises(UniqueConstraintError):
            M.upsert(M(a=1, b=1, tag="y"), q(M.tag) == "y")


class TestPatch:
    """patch() sees the whole pair, not just the patched member."""

    def test_patch_completing_conflicting_pair_raises(
        self,
        db: TinyDB,
    ) -> None:
        """Patching one member cannot sneak into a taken pair."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int

        M(a=1, b=7).insert()
        patched = M(a=2, b=7).insert()
        assert patched.id is not None
        with pytest.raises(UniqueConstraintError):
            patched.patch(a=1)  # stored b=7 completes taken (1, 7)
        stored = M.get_by_id(patched.id)
        assert stored is not None
        assert stored.a == 2  # nothing written

    def test_patch_to_novel_pair_passes(self, db: TinyDB) -> None:
        """Completing a free pair updates storage and self."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int

        M(a=1, b=7).insert()
        patched = M(a=2, b=7).insert()
        assert patched.id is not None
        patched.patch(a=3)
        stored = M.get_by_id(patched.id)
        assert stored is not None
        assert (stored.a, stored.b) == (3, 7)
        assert patched.a == 3

    def test_patch_own_pair_is_never_a_clash(
        self,
        db: TinyDB,
    ) -> None:
        """Re-writing a member with its stored value is fine."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a pair constraint."""

            a: int
            b: int

        doc = M(a=1, b=7).insert()
        doc.patch(a=1)

    def test_patch_non_member_field_skips_composite(
        self,
        db: TinyDB,
    ) -> None:
        """The touched-fields filter skips unrelated patches."""
        calls: list[tuple[object, ...]] = []

        def spy(*values: object) -> tuple[object, ...]:
            """Record every invocation and return the tuple."""
            calls.append(values)
            return values

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b", key=spy),),
        ):
            """Test model with a spied pair constraint."""

            a: int
            b: int
            note: str = ""

        doc = M(a=1, b=2).insert()
        calls.clear()
        doc.patch(note="hi")
        assert calls == []


class TestBatchScanCost:
    """``insert_many`` checks the batch against one table scan."""

    @staticmethod
    def _reads_for_batch(batch_size: int) -> int:
        """Count storage reads for one constrained batch insert."""

        class CountingStorage(MemoryStorage):
            """A MemoryStorage that counts ``read()`` calls."""

            def __init__(self) -> None:
                """Start with a zeroed counter."""
                super().__init__()
                self.reads = 0

            def read(self) -> dict | None:
                """Count the call, then read as usual."""
                self.reads += 1
                return super().read()

        with TinyDB(storage=CountingStorage) as db:

            class M(TinydanticModel, database=db):
                """Test model with one unique field."""

                email: Annotated[str, Unique()]

            M.insert_many([M(email=f"seed{i}") for i in range(20)])
            batch = [M(email=f"new{i}") for i in range(batch_size)]
            storage = cast("CountingStorage", db.storage)
            storage.reads = 0
            M.insert_many(batch)
            return storage.reads

    def test_reads_do_not_grow_with_batch_size(self) -> None:
        """A batch of 40 costs the same reads as a batch of 2.

        The check used to run per document, so a batch of N cost N
        full storage reads — the O(N x M) behavior this pins shut.
        """
        assert self._reads_for_batch(40) == self._reads_for_batch(2)


class TestBatchClashReporting:
    """Which clash a batch reports, and how it names the holder."""

    def test_stored_clash_wins_over_intra_batch_clash(
        self,
        db: TinyDB,
    ) -> None:
        """A body clashing with both names the stored document."""

        class M(TinydanticModel, database=db):
            """Test model with one unique field."""

            email: Annotated[str, Unique()]

        stored = M(email="dup").insert()
        with pytest.raises(UniqueConstraintError) as exc:
            M.insert_many([M(email="dup"), M(email="dup")])
        assert f"document {stored.id}" in str(exc.value)
        assert "same batch" not in str(exc.value)
        assert M.count() == 1

    def test_lowest_stored_id_is_reported(self, db: TinyDB) -> None:
        """Pre-existing duplicates report the first stored holder."""

        class M(TinydanticModel, database=db):
            """Test model with one unique field."""

            email: Annotated[str, Unique()]

        # Seeded through the raw table, which does not enforce.
        M.get_table().insert_multiple([{"email": "dup"}, {"email": "dup"}])
        with pytest.raises(UniqueConstraintError) as exc:
            M.insert_many([M(email="dup")])
        assert "document 1" in str(exc.value)

    def test_every_constraint_enforces_across_a_batch(
        self,
        db: TinyDB,
    ) -> None:
        """A second constraint still catches its own duplicate."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a"), UniqueConstraint("b")),
        ):
            """Test model with two single-field constraints."""

            a: int
            b: int

        M(a=1, b=1).insert()
        with pytest.raises(UniqueConstraintError) as exc:
            M.insert_many([M(a=2, b=2), M(a=3, b=1)])
        assert "'b'" in str(exc.value)
        assert M.count() == 1

    def test_none_members_never_clash_within_a_batch(
        self,
        db: TinyDB,
    ) -> None:
        """Exempt bodies do not collapse onto one another."""

        class M(
            TinydanticModel,
            database=db,
            constraints=(UniqueConstraint("a", "b"),),
        ):
            """Test model with a nullable pair constraint."""

            a: int | None = None
            b: int | None = None

        M.insert_many([M(a=1), M(a=1), M(b=2), M()])
        assert M.count() == 4

    def test_preset_id_still_checks_stored_documents(
        self,
        db: TinyDB,
    ) -> None:
        """Presetting an unused id does not skip the scan."""

        class M(TinydanticModel, database=db):
            """Test model with one unique field."""

            email: Annotated[str, Unique()]

        M(email="taken").insert()
        with pytest.raises(UniqueConstraintError):
            M.insert_many([M(id=99, email="taken")])
        assert M.count() == 1
