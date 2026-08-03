# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""The curated error surface: no raw TinyDB exceptions leak."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pydantic import Field, ValidationError

from tinydantic import (
    DocumentAlreadyExistsError,
    DocumentNotFoundError,
    SelectorError,
    TinydanticModel,
    q,
)

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestSelectorError:
    """Selector misuse raises SelectorError, never RuntimeError."""

    def test_get_no_selector(self, db: TinyDB):
        """get() with nothing raises SelectorError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError):
            User.get()  # type: ignore[call-overload]

    def test_get_too_many_selectors_compat(self, db: TinyDB):
        """The upgraded guard can still be caught as ValueError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(ValueError, match="at most one"):
            User.get(  # type: ignore[call-overload]
                q(User.name) == "x",
                doc_id=1,
            )
        with pytest.raises(SelectorError):
            User.get(  # type: ignore[call-overload]
                q(User.name) == "x",
                doc_id=1,
            )

    def test_contains_no_selector(self, db: TinyDB):
        """contains() with nothing raises SelectorError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError):
            User.contains()

    def test_get_or_raise_no_selector(self, db: TinyDB):
        """get_or_raise() with nothing raises SelectorError."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError):
            User.get_or_raise()  # type: ignore[call-overload]

    def test_remove_no_selector_points_at_truncate(self, db: TinyDB):
        """remove() with nothing refuses and names truncate()."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        User(name="x").insert()
        with pytest.raises(SelectorError, match="truncate"):
            User.remove()
        assert User.count() == 1

    def test_upsert_no_cond_unset_id(self, db: TinyDB):
        """upsert() without cond or id explains both fixes."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(SelectorError, match="insert"):
            User.upsert(User(name="x"))

    def test_upsert_with_id_still_works(self, db: TinyDB):
        """The valid no-cond path (id set) is untouched."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="x").insert()
        user.name = "y"
        assert User.upsert(user) == [user.id]


class TestDocumentAlreadyExists:
    """Duplicate ids raise DocumentAlreadyExistsError."""

    def test_insert_duplicate_id(self, db: TinyDB):
        """insert() with an existing id names model, table, id."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="x").insert()
        with pytest.raises(
            DocumentAlreadyExistsError,
            match=rf"id {user.id} already exists.*'user'",
        ):
            User(id=user.id, name="dup").insert()

    def test_insert_duplicate_compat(self, db: TinyDB):
        """Old except-ValueError handlers keep working."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="x").insert()
        with pytest.raises(ValueError, match="already exists"):
            User(id=user.id, name="dup").insert()

    def test_insert_multiple_duplicate_id_atomic(self, db: TinyDB):
        """A duplicate anywhere aborts the batch, nothing written."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="x").insert()
        with pytest.raises(
            DocumentAlreadyExistsError,
            match=str(user.id),
        ):
            User.insert_multiple(
                [User(name="new"), User(id=user.id, name="dup")],
            )
        assert User.count() == 1

    def test_insert_multiple_batch_internal_duplicate(self, db: TinyDB):
        """Two identical ids inside one batch are refused too."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        with pytest.raises(DocumentAlreadyExistsError, match="7"):
            User.insert_multiple(
                [User(id=7, name="a"), User(id=7, name="b")],
            )
        assert User.count() == 0

    @pytest.mark.filterwarnings(
        "ignore::UserWarning",  # serializer warns pre-validation
    )
    def test_insert_validation_error_not_swallowed(self, db: TinyDB):
        """A corrupted instance still raises ValidationError."""

        class Tagged(TinydanticModel, database=db):
            """Test model with a list field."""

            tags: list[int] = Field(default_factory=list)

        tagged = Tagged(tags=[1])
        tagged.tags.append("junk")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            tagged.insert()


class TestMissingDocIDs:
    """Explicit doc_ids misses raise DocumentNotFoundError."""

    def test_update_missing_doc_id(self, db: TinyDB):
        """update(doc_ids=[missing]) names the missing id."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        User(name="x").insert()
        with pytest.raises(DocumentNotFoundError, match="999"):
            User.update({"name": "y"}, doc_ids=[999])
        loaded = User.get_by_id(1)
        assert loaded is not None
        assert loaded.name == "x"

    def test_update_partial_miss_writes_nothing(self, db: TinyDB):
        """One missing id aborts the batch; valid ids untouched."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        user = User(name="x").insert()
        assert user.id is not None
        with pytest.raises(DocumentNotFoundError, match="999"):
            User.update({"name": "y"}, doc_ids=[user.id, 999])
        loaded = User.get_by_id(user.id)
        assert loaded is not None
        assert loaded.name == "x"

    def test_update_missing_doc_id_unvalidated_model(self, db: TinyDB):
        """The validate_writes=False delegation path wraps too."""

        class Loose(TinydanticModel, database=db, validate_writes=False):
            """Test model with write validation off."""

            name: str

        Loose(name="x").insert()
        with pytest.raises(DocumentNotFoundError, match="999"):
            Loose.update({"name": "y"}, doc_ids=[999])

    def test_remove_missing_doc_id(self, db: TinyDB):
        """remove(doc_ids=[missing]) names the missing id."""

        class User(TinydanticModel, database=db):
            """Test model."""

            name: str

        User(name="x").insert()
        with pytest.raises(DocumentNotFoundError, match="999"):
            User.remove(doc_ids=[999])
        assert User.count() == 1
