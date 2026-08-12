# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Optimistic concurrency: the use_revision revision_id protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID, uuid4

import pytest

from tinydantic import (
    DocumentNotFoundError,
    RevisionFieldError,
    RevisionUpdateError,
    StaleDocumentError,
    TinydanticModel,
    q,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from tinydb import TinyDB
    from tinydb.table import Document


class TestRevisionField:
    """Field injection, minting, and serialization round-trips."""

    def test_unsaved_instance_has_no_token(self, db: TinyDB):
        """revision_id defaults to None before the first write."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        assert Book(title="Dune").revision_id is None

    def test_insert_mints_uuid_token(self, db: TinyDB):
        """insert() assigns a UUID token, stored as its string."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert isinstance(book.revision_id, UUID)
        assert book.id is not None
        stored = cast("Document", Book.get_table().get(doc_id=book.id))
        assert stored["revision_id"] == str(book.revision_id)

    def test_token_round_trips_through_storage(self, db: TinyDB):
        """A reloaded instance holds the same UUID that was written."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.revision_id == book.revision_id

    def test_insert_multiple_mints_distinct_tokens(self, db: TinyDB):
        """Each batch-inserted document gets its own token."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        books = Book.insert_many(
            [Book(title="A"), Book(title="B")],
        )
        tokens = {book.revision_id for book in books}
        assert None not in tokens
        assert len(tokens) == len(books)

    def test_subclass_inherits_use_revision(self, db: TinyDB):
        """use_revision resolves through the MRO like other config."""

        class RevisionBase(TinydanticModel, use_revision=True):
            """Revisioned base without a database binding."""

        class Book(RevisionBase, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert isinstance(book.revision_id, UUID)

    def test_subclass_can_disable_revision_logic(self, db: TinyDB):
        """use_revision=False stops rotation; the field remains."""

        class RevisionBase(TinydanticModel, use_revision=True):
            """Revisioned base without a database binding."""

        class Book(RevisionBase, database=db, use_revision=False):
            """Test model that opts back out."""

            title: str

        book = Book(title="Dune").insert()
        assert book.revision_id is None

    def test_plain_model_has_no_field_or_key(self, db: TinyDB):
        """Models without use_revision are completely untouched."""

        class Book(TinydanticModel, database=db):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        stored = Book.get_table().get(doc_id=book.id)
        assert stored is not None
        assert "revision_id" not in stored
        with pytest.raises(AttributeError):
            _ = book.revision_id

    def test_plain_model_may_own_the_name(self, db: TinyDB):
        """Without use_revision, revision_id is an ordinary field."""

        class Release(TinydanticModel, database=db):
            """Test model with its own revision_id field."""

            # The base class declares revision_id statically (so
            # revisioned models type-check); owning the name on a
            # non-revisioned model needs this override.
            revision_id: str  # type: ignore[assignment]

        release = Release(revision_id="v3").insert()
        assert release.id is not None
        loaded = Release.get_by_id(release.id)
        assert loaded is not None
        assert loaded.revision_id == "v3"

    def test_declaring_the_field_on_revisioned_model_raises(
        self,
        db: TinyDB,
    ):
        """use_revision=True plus a user revision_id field refuses."""
        with pytest.raises(RevisionFieldError, match="revision_id"):

            class Book(TinydanticModel, database=db, use_revision=True):
                """Test model that declares the managed field."""

                revision_id: str  # type: ignore[assignment]


class TestTokenStaysOutOfTheCallerSurface:
    """The token is bookkeeping, not part of the document."""

    def test_absent_from_model_dump(self, db: TinyDB):
        """It would otherwise ride into every FastAPI response."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.model_dump() == {"id": book.id, "title": "Dune"}

    def test_absent_from_the_json_schema(self, db: TinyDB):
        """exclude=True alone does not do this; SkipJsonSchema does."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        assert set(Book.model_json_schema()["properties"]) == {
            "id",
            "title",
        }

    def test_still_reachable_on_the_instance(self, db: TinyDB):
        """The ETag flow reads it directly off the model."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert isinstance(book.revision_id, UUID)
        assert "revision_id" in repr(book)

    def test_still_written_to_storage(self, db: TinyDB):
        """The one excluded field storage genuinely needs."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        book.title = "Dune (1965)"
        book = book.save()
        assert book.id is not None
        stored = cast("Document", Book.get_table().get(doc_id=book.id))
        assert stored["revision_id"] == str(book.revision_id)

    def test_conflict_detection_survives_the_exclusion(self, db: TinyDB):
        """The round trip the exclusion could have broken."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int

        book = Book(title="Dune", stock=5).insert()
        assert book.id is not None
        stale = cast("Book", Book.get_by_id(book.id))
        book.stock = 4
        book = book.save()
        stale.stock = 3
        with pytest.raises(StaleDocumentError):
            stale.save()

    def test_models_without_the_opt_in_are_untouched(self, db: TinyDB):
        """No token, no exclusion, no schema change."""

        class Note(TinydanticModel, database=db):
            """Test model."""

            text: str

        note = Note(text="hi").insert()
        assert note.model_dump() == {"id": note.id, "text": "hi"}
        assert "revision_id" not in Note.model_json_schema()["properties"]


class TestSaveCheck:
    """save() compares the held token and rotates on success."""

    def test_save_rotates_the_token(self, db: TinyDB):
        """Every successful save mints a fresh token."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        first = book.revision_id
        book.title = "Dune (1965)"
        book.save()
        assert book.revision_id != first

    def test_stale_save_raises(self, db: TinyDB):
        """A save from a stale instance conflicts, writing nothing."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune", stock=5).insert()
        assert book.id is not None
        stale = Book.get_by_id(book.id)
        assert stale is not None
        book.stock = 4
        book.save()
        stale.stock = 3
        with pytest.raises(StaleDocumentError) as excinfo:
            stale.save()
        assert excinfo.value.deleted is False
        assert excinfo.value.doc_id == book.id
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.stock == 4

    def test_ignore_revision_forces_the_write(self, db: TinyDB):
        """ignore_revision=True is deliberate last-write-wins."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune", stock=5).insert()
        assert book.id is not None
        stale = Book.get_by_id(book.id)
        assert stale is not None
        book.stock = 4
        book.save()
        stale.stock = 3
        stale.save(ignore_revision=True)
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.stock == 3
        # The forced write still rotated: book is now stale.
        book.stock = 2
        with pytest.raises(StaleDocumentError):
            book.save()

    def test_save_after_delete_raises_deleted(self, db: TinyDB):
        """A held token with a missing document never resurrects."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        snapshot = Book.get_by_id(book.id)
        assert snapshot is not None
        book.delete()
        with pytest.raises(StaleDocumentError) as excinfo:
            snapshot.save()
        assert excinfo.value.deleted is True
        with pytest.raises(DocumentNotFoundError):
            Book.get_by_id(book.id)

    def test_never_read_instance_with_free_id_inserts(self, db: TinyDB):
        """Held None plus missing document inserts, import-style."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(id=7, title="Dune")
        book.save()
        assert book.id == 7
        assert isinstance(book.revision_id, UUID)

    def test_never_read_instance_cannot_blind_overwrite(self, db: TinyDB):
        """Held None + a tokened stored document = conflict."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        stored = Book(title="Dune").insert()
        blind = Book(id=stored.id, title="Imposter")
        with pytest.raises(StaleDocumentError):
            blind.save()

    def test_legacy_document_is_adopted(self, db: TinyDB):
        """Docs written before use_revision save without conflict."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        doc_id = Book.get_table().insert({"title": "Old"})
        legacy = Book.get_by_id(doc_id)
        assert legacy is not None
        assert legacy.revision_id is None
        legacy.title = "Adopted"
        legacy.save()
        assert isinstance(legacy.revision_id, UUID)
        stored = cast("Document", Book.get_table().get(doc_id=doc_id))
        assert stored is not None
        assert stored["revision_id"] == str(legacy.revision_id)


class TestReplaceAndDelete:
    """replace() and delete() check the held token."""

    def test_replace_checks_and_rotates(self, db: TinyDB):
        """replace() conflicts when stale, rotates when fresh."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        first = book.revision_id
        stale = Book.get_by_id(book.id)
        assert stale is not None
        book.title = "Dune (1965)"
        book.replace()
        assert book.revision_id != first
        stale.title = "Stale"
        with pytest.raises(StaleDocumentError):
            stale.replace()
        stale.replace(ignore_revision=True)
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.title == "Stale"

    def test_replace_missing_with_held_token_is_stale(self, db: TinyDB):
        """replace() after a concurrent delete reports deleted=True."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        snapshot = Book.get_by_id(book.id)
        assert snapshot is not None
        book.delete()
        with pytest.raises(StaleDocumentError) as excinfo:
            snapshot.replace()
        assert excinfo.value.deleted is True

    def test_replace_missing_never_read_is_not_found(self, db: TinyDB):
        """replace() keeps its not-found contract for unread ids."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        ghost = Book(id=999, title="Ghost")
        with pytest.raises(DocumentNotFoundError):
            ghost.replace()

    def test_stale_delete_raises_and_removes_nothing(self, db: TinyDB):
        """A stale delete() is refused; the document survives."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune").insert()
        assert book.id is not None
        stale = Book.get_by_id(book.id)
        assert stale is not None
        book.stock = 1
        book.save()
        with pytest.raises(StaleDocumentError):
            stale.delete()
        assert Book.get_by_id(book.id) is not None
        stale.delete(ignore_revision=True)
        with pytest.raises(DocumentNotFoundError):
            Book.get_by_id(book.id)

    def test_fresh_delete_succeeds(self, db: TinyDB):
        """A delete() holding the current token goes through."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        book.delete()
        with pytest.raises(DocumentNotFoundError):
            Book.get_by_id(book.id)


class TestPatchRotates:
    """patch() rotates without checking and absorbs the token."""

    def test_stale_patch_of_unrelated_field_merges(self, db: TinyDB):
        """patch() never conflicts; disjoint fields both survive."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune", stock=5).insert()
        assert book.id is not None
        copy_a = Book.get_by_id(book.id)
        copy_b = Book.get_by_id(book.id)
        assert copy_a is not None
        assert copy_b is not None
        copy_a.patch(stock=4)
        copy_b.patch(title="Dune (1965)")
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert loaded.stock == 4
        assert loaded.title == "Dune (1965)"

    def test_patch_absorbs_the_fresh_token(self, db: TinyDB):
        """After patch(), a save() on the instance is not stale."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune").insert()
        assert book.id is not None
        copy = Book.get_by_id(book.id)
        assert copy is not None
        copy.patch(stock=9)
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert copy.revision_id == loaded.revision_id
        copy.stock = 10
        copy.save()

    def test_patch_invalidates_other_holders(self, db: TinyDB):
        """patch() rotation makes other held tokens stale."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune").insert()
        assert book.id is not None
        other = Book.get_by_id(book.id)
        assert other is not None
        book.patch(stock=1)
        other.stock = 2
        with pytest.raises(StaleDocumentError):
            other.save()

    def test_patch_rejects_explicit_token(self, db: TinyDB):
        """Writing revision_id through patch() is refused."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        with pytest.raises(RevisionUpdateError):
            book.patch(revision_id=uuid4())


class TestTableVerbsRotate:
    """Class-level writers rotate every touched document's token."""

    def test_update_rotates(self, db: TinyDB):
        """update() invalidates held tokens for matched documents."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune").insert()
        assert book.id is not None
        Book.update_by_ids({"stock": 1}, [book.id])
        book.stock = 2
        with pytest.raises(StaleDocumentError):
            book.save()

    def test_update_rejects_explicit_token(self, db: TinyDB):
        """Writing revision_id through update() is refused."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        with pytest.raises(RevisionUpdateError):
            Book.update_by_ids({"revision_id": str(uuid4())}, [book.id])

    def test_update_transform_cannot_forge_a_token(self, db: TinyDB):
        """Rotation runs after transform callables."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune").insert()
        assert book.id is not None
        forged = str(uuid4())

        def forge(body: Mapping) -> None:
            """Try to write a chosen token through a transform."""
            cast("dict[str, Any]", body)["revision_id"] = forged

        Book.update_by_ids(forge, [book.id])
        reloaded = Book.get_by_id(book.id)
        assert reloaded is not None
        assert str(reloaded.revision_id) != forged

    def test_unvalidated_update_still_rotates(self, db: TinyDB):
        """validate_writes=False fast paths rotate too."""

        class Book(
            TinydanticModel,
            database=db,
            use_revision=True,
            validate_writes=False,
        ):
            """Test model on the unvalidated fast path."""

            title: str
            stock: int = 0

        book = Book(title="Dune").insert()
        Book.update_all({"stock": 1})
        book.stock = 2
        with pytest.raises(StaleDocumentError):
            book.save()

    def test_update_multiple_rotates(self, db: TinyDB):
        """update_many() rotates each matched document."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book_a = Book(title="A").insert()
        book_b = Book(title="B").insert()
        Book.update_many(
            [
                ({"stock": 1}, q(Book.title) == "A"),
                ({"stock": 2}, q(Book.title) == "B"),
            ],
        )
        for held in (book_a, book_b):
            held.stock = 9
            with pytest.raises(StaleDocumentError):
                held.save()

    def test_upsert_rotates_and_syncs(self, db: TinyDB):
        """upsert() rotates storage and the passed instance."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str
            stock: int = 0

        book = Book(title="Dune").insert()
        assert book.id is not None
        watcher = Book.get_by_id(book.id)
        assert watcher is not None
        book.stock = 2
        Book.upsert(book)
        loaded = Book.get_by_id(book.id)
        assert loaded is not None
        assert book.revision_id == loaded.revision_id
        watcher.stock = 0
        with pytest.raises(StaleDocumentError):
            watcher.save()

    def test_upsert_insert_branch_mints(self, db: TinyDB):
        """An upsert that inserts assigns the new document a token."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model."""

            title: str

        book = Book(title="Dune")
        ids = Book.upsert(book, q(Book.title) == "Dune")
        assert book.id == ids[0]
        assert isinstance(book.revision_id, UUID)
