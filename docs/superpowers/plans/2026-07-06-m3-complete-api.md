# Milestone 3: Complete the API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the six stubbed CRUD methods, add `delete()` and the overloaded `get()` with `get_by_*` variants, fix `save()` and the id/serialization design bugs, and export the error classes — completing the spec §4 API surface.

**Architecture:** Milestone 3 of 5 from `docs/superpowers/specs/2026-07-05-tinydantic-v0.2-design.md` (§3.6, §3.7, §4 are binding — read them first). Builds on branch `cdwilson/v0.2.0-m2-core` (M2 result, HEAD `959b526`, 431 tests). All work in `src/tinydantic/_model.py` + tests. TinyDB parameter vocabulary (`cond`, `doc_id`, `doc_ids`) replaces the ported `condition`/`document_id`/`document_ids` names everywhere — a public API change that also touches existing test call sites.

**Tech Stack:** as M2. New methods get real (concise, Google-style) docstrings — they are new API, not ported TODO stubs.

## Global Constraints

- Conventional commits + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer; hooks may reformat (`git add -u`, retry); cspell → `project-words.txt` + `sort --ignore-case -u project-words.txt -o project-words.txt`.
- TDD every task: failing tests first (RED evidence), implement, GREEN, full suite, lint+types, commit.
- Spec behavior tightenings vs raw TinyDB: passing more than one selector among `cond`/`doc_id`/`doc_ids` raises `ValueError`; TinyDB's own "none provided" errors pass through unchanged.
- Where this plan says "verify against TinyDB source", read the installed `tinydb/table.py` in `.venv` — behavior fidelity to the installed version beats this plan's guesses; document what you found in your report.
- Never file issues on external repositories. If TinyDB behavior itself is awkward, record it in your report (friction-log material) — do not work around it silently.
- `uv run poe test` green at the end of every task.
- mypy note for test code: after `user = user_class(...).insert()`, `user.id` is typed `int | None`. The strict-typed variants (`get_by_id(doc_id: int)`, `get_by_ids(list[int])`) will need an `assert user.id is not None` narrowing line in tests before passing `user.id` — add those lines as needed rather than loosening the API types.

---

### Task 1: Branch and baseline

- [ ] **Step 1:**

```bash
git checkout cdwilson/v0.2.0-m2-core
git checkout -b cdwilson/v0.2.0-m3-api
uv run poe test
```

Expected: 431 passed. STOP if not.

---

### Task 2: The interlocked serialization change + save() fix + delete()

**Files:**

- Modify: `src/tinydantic/_model.py` (the `id` field, `to_tinydb_document`, `save`; add `delete`)
- Create: `tests/model/test_serialization.py`
- Modify: `tests/model/test_model_attributes.py` (if any test asserts id-excluded dumps — check first)

**Interfaces:**

- Produces: `to_tinydb_document()` emitting JSON-mode dumps without `id`; `save() -> Self` (insert when `id is None`, else upsert-by-id); `delete() -> None`.

These three edits are ONE interlocked change (M2 review finding): removing `exclude=True` from `id` without simultaneously excluding it in `to_tinydb_document` would leak `id` into stored documents.

- [ ] **Step 1: Write the failing tests** — `tests/model/test_serialization.py`:

```python
# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Round-trip serialization, save(), and delete() tests (spec 3.6/3.7)."""

from __future__ import annotations

import datetime
import uuid

import pytest

from pydantic import BaseModel

from tests.model.models import UserBase
from tinydantic import TinydanticModel
from tinydantic.errors import DocumentIDRequiredError, DocumentNotFoundError


class Address(BaseModel):
    """Nested model for round-trip tests."""

    city: str
    zip_code: str


class RichBase(TinydanticModel):
    """Model exercising rich pydantic types (spec 3.7)."""

    name: str
    created_at: datetime.datetime
    token: uuid.UUID
    address: Address


@pytest.fixture
def rich_class(db) -> type[RichBase]:
    """RichBase bound to the parametrized test database."""

    class Rich(RichBase, database=db):
        """Bound test model."""

    return Rich


class TestIDSerialization:
    """The id field is visible in dumps but never stored (spec 3.6)."""

    def test_model_dump_includes_id(self, user_class: type[UserBase]):
        """model_dump() exposes id (FastAPI response models need it)."""
        user = user_class(name="Alice", age=37).insert()
        assert user.model_dump()["id"] == user.id

    def test_stored_document_has_no_id_field(self, user_class: type[UserBase]):
        """The id lives in TinyDB's doc_id, not inside the document."""
        user = user_class(name="Alice", age=37).insert()
        raw = user_class.get_table().get(doc_id=user.id)
        assert raw is not None
        assert "id" not in raw

    def test_to_tinydb_document_excludes_id(self, user_class: type[UserBase]):
        """to_tinydb_document never embeds the id key."""
        user = user_class(id=7, name="Alice", age=37)
        doc = user.to_tinydb_document(force_dict=True)
        assert "id" not in doc


class TestRoundTrip:
    """Rich pydantic types survive storage and come back typed."""

    def test_datetime_uuid_nested_round_trip(self, rich_class: type[RichBase]):
        """spec 3.7: JSON-mode dump out, validation back in."""
        original = rich_class(
            name="Alice",
            created_at=datetime.datetime(
                2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc
            ),
            token=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            address=Address(city="Oakland", zip_code="94601"),
        )
        original.insert()
        loaded = rich_class.get(doc_id=original.id)
        assert loaded is not None
        assert loaded.created_at == original.created_at
        assert loaded.token == original.token
        assert loaded.address == original.address

    def test_stored_values_are_json_primitives(self, rich_class: type[RichBase]):
        """What actually hits storage is JSON-safe (str, not datetime)."""
        original = rich_class(
            name="Alice",
            created_at=datetime.datetime(
                2026, 7, 6, 12, 0, tzinfo=datetime.timezone.utc
            ),
            token=uuid.uuid4(),
            address=Address(city="Oakland", zip_code="94601"),
        )
        original.insert()
        raw = rich_class.get_table().get(doc_id=original.id)
        assert isinstance(raw["created_at"], str)
        assert isinstance(raw["token"], str)
        assert isinstance(raw["address"], dict)


class TestSave:
    """save() = insert when new, upsert-by-id when persisted (spec 4)."""

    def test_save_new_instance_inserts(self, user_class: type[UserBase]):
        """The prototype crashed here (bare upsert with no cond)."""
        user = user_class(name="Alice", age=37)
        saved = user.save()
        assert saved is user
        assert user.id is not None
        fetched = user_class.get(doc_id=user.id)
        assert fetched is not None
        assert fetched.name == "Alice"

    def test_save_existing_instance_updates(self, user_class: type[UserBase]):
        """Saving again writes changes under the same id."""
        user = user_class(name="Alice", age=37).insert()
        user.age = 38
        user.save()
        fetched = user_class.get(doc_id=user.id)
        assert fetched is not None
        assert fetched.age == 38
        assert fetched.id == user.id


class TestDelete:
    """delete() removes by id with precise errors."""

    def test_delete_removes_document(self, user_class: type[UserBase]):
        """Deleted documents are gone."""
        user = user_class(name="Alice", age=37).insert()
        user.delete()
        assert user_class.get(doc_id=user.id) is None

    def test_delete_without_id_raises(self, user_class: type[UserBase]):
        """Unsaved instances cannot be deleted."""
        user = user_class(name="Alice", age=37)
        with pytest.raises(DocumentIDRequiredError):
            user.delete()

    def test_delete_missing_document_raises(self, user_class: type[UserBase]):
        """Deleting an already-removed document raises."""
        user = user_class(name="Alice", age=37).insert()
        user.delete()
        with pytest.raises(DocumentNotFoundError):
            user.delete()
```

NOTE: these tests call `get(doc_id=...)` — the Task 3 signature. Until Task 3 lands, adapt the calls in THIS task to the current signature (`get(document_id=...)`) and leave a `# TODO(M3-task3): rename to doc_id=` comment; Task 3's rename sweep removes them. (Alternative orderings create the same coupling in reverse.)

- [ ] **Step 2: RED** — `uv run pytest tests/model/test_serialization.py -v` → fails (`delete` missing, save crashes, id present in stored docs).

- [ ] **Step 3: Implement in `_model.py`:**

The `id` field loses `exclude=True`:

```python
    id: int | None = Field(
        default=None,
        description="Document ID",
    )
```

`to_tinydb_document` — replace the `model_dump()` call (docstring is now real):

```python
    def to_tinydb_document(
        self,
        *,
        force_dict: bool = False,
    ) -> dict[str, Any] | Document:
        """Convert this model to a TinyDB-storable document.

        Uses JSON-mode serialization so rich pydantic types (datetime,
        UUID, enums, nested models, ...) become JSON-safe primitives
        that round-trip through any TinyDB storage (spec 3.7). The
        ``id`` field is never embedded in the document — it maps to
        TinyDB's ``doc_id``.

        Args:
            force_dict: Return a plain dict even when ``id`` is set
                (otherwise a [Document][tinydb.table.Document] carrying
                ``doc_id`` is returned).
        """
        doc = self.model_dump(mode="json", exclude={"id"})

        if (force_dict is False) and (self.id is not None):
            doc = Document(doc, self.id)

        return doc
```

`save()` — fixed semantics, returns `Self`:

```python
    def save(self) -> Self:
        """Insert this model if it is new, otherwise update it by id.

        Returns:
            This instance (with ``id`` set if it was newly inserted).
        """
        if self.id is None:
            return self.insert()
        self.id = self.get_table().upsert(self.to_tinydb_document())[0]
        return self
```

`delete()` — new, placed after `replace()`:

```python
    def delete(self) -> None:
        """Remove this model's document from its table.

        Raises:
            DocumentIDRequiredError: If ``id`` is not set (the model
                was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
        """
        if self.id is None:
            raise DocumentIDRequiredError
        try:
            removed = self.get_table().remove(doc_ids=[self.id])
        except KeyError:
            raise DocumentNotFoundError from None
        if not removed:
            raise DocumentNotFoundError
```

Verify against TinyDB source (installed `tinydb/table.py`): whether `remove(doc_ids=[missing])` raises `KeyError` or returns an empty list — keep both guards (they're cheap) but confirm the test passes for the real behavior.

- [ ] **Step 4: GREEN + full suite** — `uv run pytest tests/model/test_serialization.py -v` passes; `uv run poe test` passes (if an existing test asserted the OLD id-excluded dump behavior, update it to the new spec behavior and note it); `uv run poe lint && uv run poe types` clean.

- [ ] **Step 5: Commit** — `feat!: make id visible in dumps and store JSON-mode documents` with body noting BREAKING CHANGE (stored documents now JSON-mode; `save()` on new instances inserts) and the trailer.

---

### Task 3: get() — TinyDB-mirror overloads + get_by_* variants

**Files:**

- Modify: `src/tinydantic/_model.py` (`get` replacement + three new variants; `from typing import overload` import)
- Create: `tests/model/test_get.py`
- Modify: `tests/model/test_model_get.py`, `tests/model/test_model_insert.py`, `tests/model/test_serialization.py` (call-site rename `document_id=` → `doc_id=`, remove Task 2's TODO comments)

**Interfaces:**

- Produces: `get(cond=None, *, doc_id=None, doc_ids=None)` with `@overload` precision; `get_by_cond(cond) -> Self | None`; `get_by_id(doc_id) -> Self | None`; `get_by_ids(doc_ids) -> list[Self | None]` (adjust to actual TinyDB behavior — see Step 3).

- [ ] **Step 1: Write the failing tests** — `tests/model/test_get.py`:

```python
# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for get() and its typed variants (spec 4)."""

from __future__ import annotations

import pytest

from tests.model.models import UserBase


class TestGet:
    """The overloaded TinyDB-mirror get()."""

    def test_get_by_cond_positional(self, user_class: type[UserBase]):
        """get(cond) mirrors TinyDB's most common form."""
        user_class(name="Alice", age=37).insert()
        result = user_class.get(user_class.name == "Alice")  # type: ignore[arg-type]
        assert result is not None
        assert result.name == "Alice"

    def test_get_by_doc_id_keyword(self, user_class: type[UserBase]):
        """get(doc_id=...) fetches by document id."""
        user = user_class(name="Alice", age=37).insert()
        result = user_class.get(doc_id=user.id)
        assert result is not None
        assert result.name == "Alice"

    def test_get_missing_returns_none(self, user_class: type[UserBase]):
        """No match means None, mirroring TinyDB."""
        assert user_class.get(doc_id=999) is None

    def test_get_multiple_selectors_raises(self, user_class: type[UserBase]):
        """Spec tightening: more than one selector is a ValueError."""
        user = user_class(name="Alice", age=37).insert()
        with pytest.raises(ValueError, match="one of"):
            user_class.get(
                user_class.name == "Alice",  # type: ignore[arg-type]
                doc_id=user.id,
            )

    def test_get_by_doc_ids(self, user_class: type[UserBase]):
        """get(doc_ids=[...]) returns a list."""
        u1 = user_class(name="Alice", age=37).insert()
        u2 = user_class(name="Bob", age=24).insert()
        results = user_class.get(doc_ids=[u1.id, u2.id])
        assert isinstance(results, list)
        assert [r.name for r in results if r is not None] == ["Alice", "Bob"]


class TestGetVariants:
    """The explicit typed variants delegate to get()."""

    def test_get_by_cond(self, user_class: type[UserBase]):
        """get_by_cond returns a single validated model or None."""
        user_class(name="Alice", age=37).insert()
        result = user_class.get_by_cond(user_class.name == "Alice")  # type: ignore[arg-type]
        assert result is not None
        assert result.age == 37
        assert user_class.get_by_cond(user_class.name == "Nobody") is None  # type: ignore[arg-type]

    def test_get_by_id(self, user_class: type[UserBase]):
        """get_by_id returns a single validated model or None."""
        user = user_class(name="Alice", age=37).insert()
        result = user_class.get_by_id(user.id)
        assert result is not None
        assert result.name == "Alice"
        assert user_class.get_by_id(999) is None

    def test_get_by_ids(self, user_class: type[UserBase]):
        """get_by_ids returns validated models for the given ids."""
        u1 = user_class(name="Alice", age=37).insert()
        u2 = user_class(name="Bob", age=24).insert()
        results = user_class.get_by_ids([u1.id, u2.id])
        assert [r.name for r in results if r is not None] == ["Alice", "Bob"]
```

- [ ] **Step 2: RED** — new tests fail (`doc_id` unexpected keyword; variants missing).

- [ ] **Step 3: Implement.** FIRST verify against the installed TinyDB source what `Table.get(doc_ids=[...])` does with missing ids (skips them? returns None entries? raises KeyError?) and what it does when no selector is given (expect `RuntimeError`). Match the return annotation and the missing-ids test expectation to the REAL behavior, and record it in your report. Then replace `get` and add the variants:

```python
    @overload
    @classmethod
    def get(cls, cond: QueryLike) -> Self | None: ...

    @overload
    @classmethod
    def get(cls, *, doc_id: int) -> Self | None: ...

    @overload
    @classmethod
    def get(cls, *, doc_ids: list[int]) -> list[Self | None]: ...

    @classmethod
    def get(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_id: int | None = None,
        doc_ids: list[int] | None = None,
    ) -> Self | list[Self | None] | None:
        """Get one document (or several by id) as validated models.

        Mirrors [tinydb.table.Table.get][], with one tightening: at
        most one of ``cond``, ``doc_id``, ``doc_ids`` may be provided
        (TinyDB silently applies a precedence order; tinydantic raises
        ``ValueError``). The typed variants
        [get_by_cond][tinydantic.TinydanticModel.get_by_cond],
        [get_by_id][tinydantic.TinydanticModel.get_by_id], and
        [get_by_ids][tinydantic.TinydanticModel.get_by_ids] offer
        precise return types per call shape.

        Raises:
            ValueError: If more than one selector is provided.
        """
        provided = [
            s for s in (cond, doc_id, doc_ids) if s is not None
        ]
        if len(provided) > 1:
            msg = "Provide at most one of cond, doc_id, or doc_ids"
            raise ValueError(msg)

        result = cls.get_table().get(
            cond=cond,
            doc_id=doc_id,
            doc_ids=doc_ids,
        )

        if result is None:
            return None

        if isinstance(result, Document):
            return cls.from_tinydb_document(result)

        if isinstance(result, list):
            return [
                cls.from_tinydb_document(doc) if doc is not None else None
                for doc in result
            ]

        raise TypeError

    @classmethod
    def get_by_cond(cls, cond: QueryLike) -> Self | None:
        """Get the first document matching ``cond``, or ``None``."""
        return cls.get(cond)

    @classmethod
    def get_by_id(cls, doc_id: int) -> Self | None:
        """Get the document with the given id, or ``None``."""
        return cls.get(doc_id=doc_id)

    @classmethod
    def get_by_ids(cls, doc_ids: list[int]) -> list[Self | None]:
        """Get documents for the given ids (see get() for semantics)."""
        return cls.get(doc_ids=doc_ids)
```

Add `overload` to the `typing` imports. Then sweep the rename: `grep -rn "document_id" tests src` and update every call site (`document_id=` → `doc_id=`, `document_ids=` → `doc_ids=`), removing Task 2's TODO comments.

- [ ] **Step 4: GREEN + full suite + lint + types.** Note: `uv run poe types` is the real gate for the overloads — mypy must accept all three call shapes and the variants' delegations.

- [ ] **Step 5: Commit** — `feat!: overload get() with TinyDB-style selectors and typed variants` + trailer.

---

### Task 4: The remaining classmethod surface

**Files:**

- Modify: `src/tinydantic/_model.py` (implement `search`, `contains`, `update`, `update_multiple`, `upsert`, `remove`; rename `count`'s param to `cond`)
- Create: `tests/model/test_table_methods.py`

**Interfaces:**

- Produces (spec §4): `search(cond) -> list[Self]`, `contains(cond=None, *, doc_id=None) -> bool`, `update(fields, cond=None, *, doc_ids=None) -> list[int]`, `update_multiple(updates) -> list[int]`, `upsert(document, cond=None) -> list[int]`, `remove(cond=None, *, doc_ids=None) -> list[int]`, `count(cond) -> int`.

- [ ] **Step 1: Write the failing tests** — `tests/model/test_table_methods.py`:

```python
# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for the classmethod table surface (spec 4)."""

from __future__ import annotations

import pytest

from tests.model.models import UserBase
from tinydantic.tinydb.operations import replace


class TestSearch:
    """search() returns validated models."""

    def test_search_returns_models(self, user_class: type[UserBase]):
        """All matches come back as model instances with ids."""
        user_class(name="John", age=37).insert()
        user_class(name="John Smith", age=24).insert()
        user_class(name="Alice", age=30).insert()
        results = user_class.search(user_class.name.matches("John.*"))  # type: ignore[union-attr]
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
        """Spec tightening: both selectors is a ValueError."""
        user = user_class(name="Alice", age=37).insert()
        with pytest.raises(ValueError, match="one of"):
            user_class.contains(user_class.name == "Alice", doc_id=user.id)  # type: ignore[arg-type]


class TestUpdate:
    """update()/update_multiple() write through to the table."""

    def test_update_fields_by_cond(self, user_class: type[UserBase]):
        """Mapping-of-fields form."""
        user = user_class(name="Alice", age=37).insert()
        updated = user_class.update({"age": 38}, user_class.name == "Alice")  # type: ignore[arg-type]
        assert updated == [user.id]
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None and fetched.age == 38

    def test_update_by_doc_ids(self, user_class: type[UserBase]):
        """doc_ids form."""
        user = user_class(name="Alice", age=37).insert()
        user_class.update({"age": 40}, doc_ids=[user.id])
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None and fetched.age == 40

    def test_update_multiple(self, user_class: type[UserBase]):
        """Batched per-condition updates."""
        u1 = user_class(name="Alice", age=37).insert()
        u2 = user_class(name="Bob", age=24).insert()
        updated = user_class.update_multiple(
            [
                ({"age": 1}, user_class.name == "Alice"),  # type: ignore[list-item]
                ({"age": 2}, user_class.name == "Bob"),  # type: ignore[list-item]
            ]
        )
        assert sorted(updated) == sorted([u1.id, u2.id])
        alice = user_class.get_by_id(u1.id)
        bob = user_class.get_by_id(u2.id)
        assert alice is not None and alice.age == 1
        assert bob is not None and bob.age == 2


class TestUpsert:
    """Classmethod upsert() mirrors Table.upsert."""

    def test_upsert_inserts_when_no_match(self, user_class: type[UserBase]):
        """Insert path."""
        ids = user_class.upsert(
            user_class(name="Alice", age=37),
            user_class.name == "Alice",  # type: ignore[arg-type]
        )
        assert len(ids) == 1
        fetched = user_class.get_by_id(ids[0])
        assert fetched is not None and fetched.age == 37

    def test_upsert_updates_when_matched(self, user_class: type[UserBase]):
        """Update path keeps the same document id."""
        user = user_class(name="Alice", age=37).insert()
        ids = user_class.upsert(
            user_class(name="Alice", age=99),
            user_class.name == "Alice",  # type: ignore[arg-type]
        )
        assert ids == [user.id]
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None and fetched.age == 99


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
        removed = user_class.remove(doc_ids=[user.id])
        assert removed == [user.id]
        assert user_class.get_by_id(user.id) is None


class TestOperationsEscapeHatch:
    """tinydantic's replace() operation works through update()."""

    def test_update_with_transform(self, user_class: type[UserBase]):
        """Callable-transform form (TinyDB operations protocol)."""
        user = user_class(name="Alice", age=37).insert()
        user_class.update(
            replace({"name": "Alicia", "age": 38}),
            doc_ids=[user.id],
        )
        fetched = user_class.get_by_id(user.id)
        assert fetched is not None
        assert fetched.name == "Alicia"
        assert fetched.age == 38
```

- [ ] **Step 2: RED** — all fail with `NotImplementedError` (or signature errors).

- [ ] **Step 3: Implement.** Replace the six stubs (keep the `Table.update` cast band-aid comment where the cast is used; `count`'s parameter renames `condition` → `cond`):

```python
    @classmethod
    def search(cls, cond: QueryLike) -> list[Self]:
        """Get all documents matching ``cond`` as validated models."""
        return [
            cls.from_tinydb_document(doc)
            for doc in cls.get_table().search(cond)
        ]

    @classmethod
    def contains(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_id: int | None = None,
    ) -> bool:
        """Check whether a matching document exists.

        Raises:
            ValueError: If both ``cond`` and ``doc_id`` are provided.
        """
        if cond is not None and doc_id is not None:
            msg = "Provide at most one of cond or doc_id"
            raise ValueError(msg)
        return cls.get_table().contains(cond=cond, doc_id=doc_id)

    @classmethod
    def update(
        cls,
        fields: Mapping | Callable[[Mapping], None],
        cond: QueryLike | None = None,
        *,
        doc_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """Update matching documents with new fields or a transform.

        Returns:
            The ids of all updated documents.
        """
        return cls.get_table().update(
            # See replace() for why this cast is needed.
            # TODO @cdwilson: remove this cast once the annotation is
            # fixed in TinyDB.
            cast("Callable[[Mapping], None]", fields),
            cond=cond,
            doc_ids=doc_ids,
        )

    @classmethod
    def update_multiple(
        cls,
        updates: Iterable[
            tuple[
                Mapping | Callable[[Mapping], None],
                QueryLike,
            ]
        ],
    ) -> list[int]:
        """Apply several (fields_or_transform, cond) updates at once.

        Returns:
            The ids of all updated documents.
        """
        return cls.get_table().update_multiple(
            # See replace() for why this cast is needed.
            cast(
                "Iterable[tuple[Callable[[Mapping], None], QueryLike]]",
                updates,
            ),
        )

    @classmethod
    def upsert(
        cls,
        document: Self,
        cond: QueryLike | None = None,
    ) -> list[int]:
        """Update documents matching ``cond``, or insert ``document``.

        Returns:
            The ids of the updated (or inserted) documents.
        """
        return cls.get_table().upsert(
            document.to_tinydb_document(force_dict=cond is not None),
            cond,
        )

    @classmethod
    def remove(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """Remove matching documents.

        Returns:
            The ids of all removed documents.
        """
        return cls.get_table().remove(cond=cond, doc_ids=doc_ids)
```

Verify against the installed TinyDB source: (a) `Table.update`'s actual keyword names (`cond`, `doc_ids`); (b) `upsert` semantics when passed a `Document` with `doc_id` AND a cond (the `force_dict=cond is not None` guard makes cond-based upserts use the cond, and id-carrying upserts use the doc_id — confirm this against `Table.upsert`'s doc_id-extraction logic and adjust if the interplay differs; record findings).

- [ ] **Step 4: GREEN + full suite + lint + types.**

- [ ] **Step 5: Commit** — `feat: implement search, contains, update, upsert, and remove` + trailer.

---

### Task 5: Error exports, gate, push, CI

**Files:**

- Modify: `src/tinydantic/__init__.py`

- [ ] **Step 1: Export the error classes** (M2 review carry-forward; users need them to catch `delete()`/`replace()` failures):

Add to the imports and `__all__` in `src/tinydantic/__init__.py`:

```python
from tinydantic.errors import (
    AmbiguousConfigError,
    DatabaseNotBoundError,
    DocumentIDRequiredError,
    DocumentNotFoundError,
    TinydanticError,
    TinydanticUserError,
)
```

with all six names added to `__all__` (keep it sorted).

- [ ] **Step 2: Add an import smoke test.** Append to `tests/model/test_model_config.py` (module level, after the existing classes):

```python
def test_top_level_error_exports():
    """Error classes are importable from the package root (spec 6)."""
    import tinydantic

    assert issubclass(tinydantic.DatabaseNotBoundError, tinydantic.TinydanticError)
    assert issubclass(tinydantic.AmbiguousConfigError, tinydantic.TinydanticUserError)
    assert issubclass(tinydantic.DocumentNotFoundError, tinydantic.TinydanticError)
    assert issubclass(tinydantic.DocumentIDRequiredError, tinydantic.TinydanticError)
```

(Module-level function in that file, after the classes.)

- [ ] **Step 3: Full gate**

```bash
uv run poe check
uv run poe test-cov
uv run poe docs-build
uv run poe pre-commit
uv build && rm -rf dist
```

All PASS. Commit `feat: export error classes from the package root` + trailer.

- [ ] **Step 4: Push + CI**

```bash
git push -u origin cdwilson/v0.2.0-m3-api
gh workflow run ci.yaml --ref cdwilson/v0.2.0-m3-api
gh run list --workflow ci.yaml --branch cdwilson/v0.2.0-m3-api --limit 1
gh run watch <run-id> --exit-status
```

Expected: 14/14 green. Do NOT merge; M4 builds on this branch.
