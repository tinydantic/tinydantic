# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the fluent find() query API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Annotated, cast

import pytest

from pydantic import Field, ValidationError
from tinydb import TinyDB
from tinydb.storages import MemoryStorage

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, MutableMapping

from tinydantic import (
    DocumentIDUpdateError,
    DocumentNotFoundError,
    FindQuery,
    QueryFieldError,
    QueryTypeError,
    QueryUsageError,
    QueryValueError,
    ShadowedFieldError,
    TinydanticModel,
    TinydanticUserError,
    Unique,
    UnknownUpdateFieldError,
    field,
    q,
)


class User(TinydanticModel):
    """Unbound user model; tests bind per-database subclasses."""

    name: str
    age: int


@pytest.fixture
def user_class(db: TinyDB) -> type[User]:
    """Return a User subclass bound to a fresh database."""

    class BoundUser(User, database=db, table_name="users"):
        """User bound to the test database."""

    return BoundUser


class TestErrorHierarchy:
    """Chain errors carry the builtin base Python would."""

    def test_every_chain_error_is_a_user_error(self) -> None:
        """All four can be caught as TinydanticUserError."""
        for error in (
            QueryFieldError,
            QueryTypeError,
            QueryUsageError,
            QueryValueError,
        ):
            assert issubclass(error, TinydanticUserError)

    def test_builtin_bases_follow_python_convention(self) -> None:
        """Wrong kind, bad value, and bad name map as Python does."""
        assert issubclass(QueryTypeError, TypeError)
        assert issubclass(QueryValueError, ValueError)
        assert issubclass(QueryFieldError, AttributeError)

    def test_usage_error_has_no_builtin_base(self) -> None:
        """A clause stated twice is neither a type nor a value bug."""
        assert not issubclass(QueryUsageError, TypeError)
        assert not issubclass(QueryUsageError, ValueError)


class TestFilter:
    """filter() narrows a chain, repeatably, with AND."""

    @pytest.fixture
    def populated(self, user_class: type[User]) -> type[User]:
        """Four users spanning both filter dimensions."""
        user_class.insert_multiple(
            [
                user_class(name="ada", age=36),
                user_class(name="bob", age=17),
                user_class(name="cy", age=41),
                user_class(name="dee", age=17),
            ],
        )
        return user_class

    def test_filter_ands_with_the_find_condition(
        self, populated: type[User]
    ) -> None:
        """Both conditions must match."""
        chain = populated.find(field(populated, "age") > 18).filter(
            field(populated, "name") == "ada",
        )
        assert [u.name for u in chain.all()] == ["ada"]

    def test_filter_supplies_the_condition_when_there_is_none(
        self, populated: type[User]
    ) -> None:
        """find() with no condition can still be narrowed."""
        chain = populated.find().filter(field(populated, "age") == 17)
        assert sorted(u.name for u in chain.all()) == ["bob", "dee"]

    def test_filter_repeats_unlike_the_other_modifiers(
        self, populated: type[User]
    ) -> None:
        """Successive filters mean AND, so repetition is allowed."""
        chain = (
            populated.find()
            .filter(field(populated, "age") > 18)
            .filter(field(populated, "age") < 40)
            .filter(field(populated, "name") == "ada")
        )
        assert [u.name for u in chain.all()] == ["ada"]

    def test_filter_returns_a_new_chain(self, populated: type[User]) -> None:
        """The base chain is never mutated."""
        base = populated.find(field(populated, "age") > 18)
        narrowed = base.filter(field(populated, "name") == "ada")
        assert narrowed is not base
        assert base.count() == 2

    def test_filter_composes_with_the_window(
        self, populated: type[User]
    ) -> None:
        """Order of modifier calls does not change the pipeline."""
        chain = (
            populated.find()
            .sort("name")
            .filter(field(populated, "age") == 17)
            .limit(1)
        )
        assert [u.name for u in chain.all()] == ["bob"]

    def test_filter_works_on_top_of_a_callable_condition(
        self, populated: type[User]
    ) -> None:
        """A lambda has no &, so the AND falls back to a closure."""
        chain = populated.find(lambda doc: doc["age"] == 17).filter(
            field(populated, "name") == "dee",
        )
        assert [u.name for u in chain.all()] == ["dee"]

    def test_filter_refuses_a_non_condition(
        self, populated: type[User]
    ) -> None:
        """The operand goes through the same guard find() uses."""
        chain = populated.find()
        with pytest.raises(QueryTypeError):
            chain.filter("ada")  # type: ignore[arg-type]
        with pytest.raises(QueryTypeError):
            chain.filter(None)  # type: ignore[arg-type]


class TestFindConstruction:
    """find() builds a lazy, immutable FindQuery."""

    def test_find_returns_find_query(self, user_class: type[User]) -> None:
        """find() with and without cond returns a FindQuery."""
        assert isinstance(user_class.find(), FindQuery)
        adults = user_class.find(field(user_class, "age") >= 18)
        assert isinstance(adults, FindQuery)

    def test_find_none_raises_query_type_error(
        self, user_class: type[User]
    ) -> None:
        """A None condition value is refused at construction.

        None is the wrong kind of object, not a missing
        argument — omitting the condition is the whole-table
        spelling, which the message names.
        """
        with pytest.raises(QueryTypeError, match="no argument"):
            user_class.find(None)  # type: ignore[call-overload]

    def test_find_performs_no_io(self, db: TinyDB) -> None:
        """Building a chain never touches the database."""

        class Untouched(User, database=db, table_name="untouched"):
            """Bound model whose table must stay untouched."""

        Untouched.find(field(Untouched, "age") >= 18)
        assert "untouched" not in db.tables()

    def test_repr_shows_clauses(self, user_class: type[User]) -> None:
        """repr() names the model and shows the clause set."""
        text = repr(user_class.find())
        assert "BoundUser" in text
        assert "cond=" in text
        assert "skip=" in text


class TestModifiers:
    """Modifier validation, immutability, and the once-rule."""

    def test_modifiers_return_new_chains(self, user_class: type[User]) -> None:
        """Each modifier leaves the receiver untouched."""
        base = user_class.find()
        sorted_chain = base.sort("name")
        assert sorted_chain is not base
        # The base can still accept its own sort: it was never
        # mutated by the first call.
        assert base.sort("age") is not sorted_chain

    def test_repeated_sort_raises(self, user_class: type[User]) -> None:
        """A second sort() raises; message teaches one-call form."""
        chain = user_class.find().sort("name")
        with pytest.raises(QueryUsageError, match="once"):
            chain.sort("age")

    def test_repeated_skip_and_limit_raise(
        self, user_class: type[User]
    ) -> None:
        """skip()/limit() follow the same once-rule as sort()."""
        with pytest.raises(QueryUsageError, match="once"):
            user_class.find().skip(1).skip(2)
        with pytest.raises(QueryUsageError, match="once"):
            user_class.find().limit(1).limit(2)

    def test_unknown_sort_field_raises_eagerly(
        self, user_class: type[User]
    ) -> None:
        """A wrong field name fails at sort(), not at all()."""
        with pytest.raises(QueryFieldError, match="shoe_size"):
            user_class.find().sort("shoe_size")

    def test_alias_is_not_a_sort_key(self, db: TinyDB) -> None:
        """Sort keys are attribute names, not storage aliases."""

        class Aliased(TinydanticModel, database=db, table_name="aliased"):
            """Model with an aliased field."""

            full_name: str = Field(alias="fullName")

        Aliased.find().sort("full_name")  # attribute name: fine
        with pytest.raises(QueryFieldError, match="fullName"):
            Aliased.find().sort("fullName")

    def test_descending_prefix_parses(self, user_class: type[User]) -> None:
        """A - prefix is accepted; a bare - is refused."""
        user_class.find().sort("-age", "name")
        with pytest.raises(QueryFieldError):
            user_class.find().sort("-")

    def test_mixed_sort_forms_raise(self, user_class: type[User]) -> None:
        """Field names cannot combine with key= or reverse=."""
        with pytest.raises(QueryValueError, match="key="):
            user_class.find().sort("name", key=lambda u: u.age)
        with pytest.raises(QueryValueError, match="key="):
            user_class.find().sort("name", reverse=True)

    def test_sort_without_arguments_raises(
        self, user_class: type[User]
    ) -> None:
        """sort() with nothing to sort by names no ordering.

        Like a missing selector, the arguments are individually
        fine and the combination supplies no value, so this is a
        QueryValueError rather than the bare TypeError it used
        to leak.
        """
        with pytest.raises(QueryValueError, match="sort"):
            user_class.find().sort()

    def test_skip_limit_operand_validation(
        self, user_class: type[User]
    ) -> None:
        """skip/limit require a non-negative non-bool int."""
        find = user_class.find()
        for wrong_type in (True, 1.5, "3", None):
            with pytest.raises(QueryTypeError):
                find.skip(wrong_type)  # type: ignore[arg-type]
            with pytest.raises(QueryTypeError):
                find.limit(wrong_type)  # type: ignore[arg-type]
        with pytest.raises(QueryValueError):
            find.skip(-1)
        with pytest.raises(QueryValueError):
            find.limit(-1)
        find.skip(0)  # legal no-op
        find.limit(0)  # legal empty window


@pytest.fixture
def seeded(user_class: type[User]) -> type[User]:
    """Insert a small diverse dataset and return the class.

    Ids are 1..5 in insertion order: bob/30, alice/25, carol/30,
    dave/25, erin/40.
    """
    for name, age in [
        ("bob", 30),
        ("alice", 25),
        ("carol", 30),
        ("dave", 25),
        ("erin", 40),
    ]:
        user_class(name=name, age=age).insert()
    return user_class


class TestReadTerminals:
    """Read terminals and the fixed pipeline."""

    def test_all_matches_search(self, seeded: type[User]) -> None:
        """find(cond).all() equals search(cond)."""
        cond = field(seeded, "age") >= 30
        assert seeded.find(cond).all() == seeded.search(cond)

    def test_find_no_args_is_whole_table(self, seeded: type[User]) -> None:
        """find() with no condition reads every document."""
        assert seeded.find().count() == 5

    def test_sort_ascending_and_descending(self, seeded: type[User]) -> None:
        """Single-key sorts order by field value."""
        names = [u.name for u in seeded.find().sort("name")]
        assert names == sorted(names)
        ages = [u.age for u in seeded.find().sort("-age")]
        assert ages == sorted(ages, reverse=True)

    def test_multi_key_mixed_directions(self, seeded: type[User]) -> None:
        """Left-to-right significance with per-key direction."""
        got = [(u.age, u.name) for u in seeded.find().sort("age", "-name")]
        assert got == [
            (25, "dave"),
            (25, "alice"),
            (30, "carol"),
            (30, "bob"),
            (40, "erin"),
        ]

    def test_ties_keep_doc_id_order(self, seeded: type[User]) -> None:
        """Equal keys come out in stored (doc id) order."""
        ids = [u.id for u in seeded.find().sort("age")]
        # ages: alice(2)=25, dave(4)=25, bob(1)=30, carol(3)=30,
        # erin(5)=40 — ties in doc-id order via sort stability.
        assert ids == [2, 4, 1, 3, 5]

    def test_key_callable_with_reverse(self, seeded: type[User]) -> None:
        """The key= escape hatch sorts by arbitrary callables."""
        names = [
            u.name
            for u in seeded.find().sort(
                key=lambda u: (u.age, u.name), reverse=True
            )
        ]
        assert names[0] == "erin"

    def test_pipeline_order_is_fixed(self, seeded: type[User]) -> None:
        """limit-then-sort spelling equals sort-then-limit."""
        a = seeded.find().sort("-age").limit(2).all()
        b = seeded.find().limit(2).sort("-age").all()
        assert a == b
        assert [u.name for u in a] == ["erin", "bob"]

    def test_window_slicing(self, seeded: type[User]) -> None:
        """skip/limit slice the sorted result."""
        window = seeded.find().sort("name").skip(1).limit(2)
        assert [u.name for u in window] == ["bob", "carol"]
        assert seeded.find().limit(0).all() == []

    def test_first_and_first_or_raise(self, seeded: type[User]) -> None:
        """first() is all()[0]-or-None; strict form raises."""
        oldest = seeded.find().sort("-age").first()
        assert oldest is not None
        assert oldest.name == "erin"
        empty = seeded.find(field(seeded, "age") > 200)
        assert empty.first() is None
        with pytest.raises(DocumentNotFoundError):
            empty.first_or_raise()
        # The window applies before first: an empty page raises.
        with pytest.raises(DocumentNotFoundError):
            seeded.find().skip(30).first_or_raise()

    def test_terminal_invariants(self, seeded: type[User]) -> None:
        """first/count/exists agree with all() on every chain."""
        chains = [
            seeded.find(),
            seeded.find(field(seeded, "age") >= 30),
            seeded.find(field(seeded, "age") > 200),
            seeded.find().sort("-name").skip(1),
            seeded.find(field(seeded, "age") == 25).sort("name").limit(1),
            seeded.find().skip(4).limit(3),
        ]
        for chain in chains:
            everything = chain.all()
            assert chain.count() == len(everything)
            assert chain.exists() == bool(everything)
            expected = everything[0] if everything else None
            assert chain.first() == expected
            assert list(chain) == everything

    def test_execution_is_fresh_not_cached(self, seeded: type[User]) -> None:
        """A reused chain sees writes made after it was built."""
        chain = seeded.find(field(seeded, "age") >= 30)
        assert chain.count() == 3
        seeded(name="frank", age=50).insert()
        assert chain.count() == 4

    def test_datetime_fields_sort_chronologically(self, db: TinyDB) -> None:
        """Sorting uses validated values, not stored strings."""

        class Event(TinydanticModel, database=db, table_name="events"):
            """Event with a real datetime field."""

            at: datetime

        early = datetime(2026, 1, 2, tzinfo=timezone.utc)
        late = datetime(2026, 11, 1, tzinfo=timezone.utc)
        mid = datetime(2026, 3, 5, tzinfo=timezone.utc)
        for at in (late, early, mid):
            Event(at=at).insert()
        got = [e.at for e in Event.find().sort("at")]
        assert got == [early, mid, late]

    def test_none_comparison_propagates_type_error(self, db: TinyDB) -> None:
        """Optional-field Nones raise Python's TypeError."""

        class Score(TinydanticModel, database=db, table_name="scores"):
            """Score with an optional value."""

            value: int | None = None

        Score(value=3).insert()
        Score(value=None).insert()
        with pytest.raises(TypeError):
            Score.find().sort("value").all()

    def test_id_condition_chains(self, seeded: type[User]) -> None:
        """Model.id conditions work through the chain."""
        second = seeded.find(q(seeded.id) == 2).first()
        assert second is not None
        assert second.name == "alice"
        ids = [
            u.id for u in seeded.find(q(seeded.id).one_of([1, 3])).sort("-id")
        ]
        assert ids == [3, 1]


class CountingStorage(MemoryStorage):
    """MemoryStorage that counts write() calls."""

    def __init__(self) -> None:
        """Start with a zero write count."""
        super().__init__()
        self.write_count = 0

    def write(self, data: dict) -> None:
        """Record the write, then delegate."""
        self.write_count += 1
        super().write(data)


class TestDelete:
    """delete() removes exactly the .all() set."""

    def test_delete_without_modifiers(self, seeded: type[User]) -> None:
        """Condition-only delete removes every match."""
        removed = seeded.find(field(seeded, "age") == 25).delete()
        assert sorted(removed) == [2, 4]
        assert seeded.count() == 3

    def test_delete_honors_sort_skip_limit(self, seeded: type[User]) -> None:
        """Keep-newest-N pruning: modifiers select victims."""
        removed = seeded.find().sort("-id").skip(2).delete()
        assert removed == [3, 2, 1]  # sorted order preserved
        assert {u.id for u in seeded.all()} == {4, 5}

    def test_delete_matches_all_set(self, seeded: type[User]) -> None:
        """delete() removes exactly what all() showed."""
        chain = seeded.find(field(seeded, "age") >= 30).sort("age").limit(2)
        expected = [u.id for u in chain.all()]
        removed = chain.delete()
        assert removed == expected

    def test_whole_table_delete_is_explicit_and_legal(
        self, seeded: type[User]
    ) -> None:
        """find().delete() deletes everything, deliberately."""
        removed = seeded.find().delete()
        assert len(removed) == 5
        assert seeded.count() == 0

    def test_empty_window_delete_writes_nothing(self) -> None:
        """Zero matches: no-op, [] returned, zero writes."""
        storage = CountingStorage()
        counting_db = TinyDB(storage=lambda: storage)

        class Item(TinydanticModel, database=counting_db, table_name="items"):
            """Minimal model over the counting storage."""

            name: str

        Item(name="only").insert()
        writes_before = storage.write_count
        result = Item.find(field(Item, "name") == "missing").limit(3).delete()
        assert result == []
        assert storage.write_count == writes_before


class TestUpdate:
    """update() mirrors the verb through the chain."""

    def test_update_without_modifiers(self, seeded: type[User]) -> None:
        """Condition-only update touches every match."""
        touched = seeded.find(field(seeded, "age") == 25).update({"age": 26})
        assert sorted(touched) == [2, 4]
        assert seeded.count(field(seeded, "age") == 26) == 2

    def test_update_honors_modifiers(self, seeded: type[User]) -> None:
        """Only the sorted window is updated."""
        window = seeded.find(field(seeded, "age") > 0).sort("age").limit(2)
        window.update({"age": 99})
        assert seeded.count(field(seeded, "age") == 99) == 2
        # The two youngest (alice, dave) were selected.
        assert {u.name for u in seeded.search(field(seeded, "age") == 99)} == {
            "alice",
            "dave",
        }

    def test_update_accepts_transform(self, seeded: type[User]) -> None:
        """Transform callables pass through like update()."""

        def bump(doc: MutableMapping) -> None:
            """Increment the stored age in place."""
            doc["age"] += 1

        # TinyDB annotates transforms with Mapping though it
        # passes a mutable dict; match update()'s precedent.
        seeded.find(field(seeded, "name") == "erin").update(
            cast("Callable[[Mapping], None]", bump)
        )
        erin = seeded.get(field(seeded, "name") == "erin")
        assert erin is not None
        assert erin.age == 41

    def test_extra_keys_passthrough(self, seeded: type[User]) -> None:
        """extra_keys forwards; default rejects unknowns."""
        chain = seeded.find(field(seeded, "name") == "bob").limit(1)
        with pytest.raises(UnknownUpdateFieldError):
            chain.update({"nickname": "bobby"})
        chain.update({"nickname": "bobby"}, extra_keys="allow")
        stored = seeded.get_table().get(doc_id=1)
        assert stored == {"name": "bob", "age": 30, "nickname": "bobby"}

    def test_id_key_rejected_through_chain(self, seeded: type[User]) -> None:
        """The id-key guard fires through both delegation paths."""
        with pytest.raises(DocumentIDUpdateError):
            seeded.find(field(seeded, "age") == 25).update({"id": 9})
        with pytest.raises(DocumentIDUpdateError):
            seeded.find().limit(1).update({"id": 9})

    def test_merged_validation_aborts_atomically(
        self, seeded: type[User]
    ) -> None:
        """A validation failure writes nothing (parity)."""
        with pytest.raises(ValidationError):
            seeded.find().sort("id").update({"age": "nope"})
        assert [u.age for u in seeded.find().sort("id")] == [
            30,
            25,
            30,
            25,
            40,
        ]

    def test_empty_window_update_is_noop(self, seeded: type[User]) -> None:
        """Zero matches return [] without touching the verbs."""
        empty = seeded.find(field(seeded, "age") > 200).limit(2)
        result = empty.update({"age": 1})
        assert result == []

    def test_empty_window_still_rejects_bad_payload(
        self, seeded: type[User]
    ) -> None:
        """Payload guards do not depend on the data state."""
        empty = seeded.find(field(seeded, "age") > 200).limit(1)
        with pytest.raises(DocumentIDUpdateError):
            empty.update({"id": 9})
        with pytest.raises(UnknownUpdateFieldError):
            empty.update({"bogus": 1})

    def test_unique_markers_not_enforced_parity(self, db: TinyDB) -> None:
        """The chain is the same loose path as update()."""

        class Handle(TinydanticModel, database=db, table_name="handles"):
            """Model with a unique field."""

            slug: Annotated[str, Unique]

        Handle(slug="a").insert()
        Handle(slug="b").insert()
        # update() deliberately skips Unique enforcement; the
        # chain must not be stricter or looser.
        one = Handle.find(field(Handle, "slug") == "b").limit(1)
        one.update({"slug": "a"})
        assert Handle.count(field(Handle, "slug") == "a") == 2

    def test_revision_rotates_through_chain(self, db: TinyDB) -> None:
        """use_revision models get fresh tokens via the chain."""

        class Doc(
            TinydanticModel,
            database=db,
            table_name="docs",
            use_revision=True,
        ):
            """Revisioned model."""

            body: str

        doc = Doc(body="v1").insert()
        before = doc.revision_id
        Doc.find(field(Doc, "body") == "v1").sort("id").update({"body": "v2"})
        stored = Doc.get_or_raise(doc_id=cast("int", doc.id))
        assert stored.revision_id != before


class TestBooleanContext:
    """A chain refuses truthiness instead of lying."""

    def test_bool_raises_find_query_error(
        self, user_class: type[User]
    ) -> None:
        """If User.find(...) is refused with the fix named."""
        with pytest.raises(QueryTypeError, match="exists"):
            bool(user_class.find())

    def test_len_is_unsupported(self, user_class: type[User]) -> None:
        """len() fails naturally; count() is the spelling."""
        with pytest.raises(TypeError):
            len(user_class.find())  # type: ignore[arg-type]


class TestFindReservedWord:
    """find is a reserved word on the model namespace."""

    @pytest.mark.filterwarnings(
        "ignore:Field name .* shadows an attribute:UserWarning",
    )
    def test_field_named_find_raises_shadowed_field_error(
        self,
    ) -> None:
        """A model field named find is refused at definition."""
        with pytest.raises(ShadowedFieldError, match="find"):

            class Bad(TinydanticModel):
                """Model illegally naming a field find."""

                find: str  # type: ignore[assignment]
