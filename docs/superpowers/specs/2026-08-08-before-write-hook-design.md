# before_write / after_read lifecycle hooks

Design for review finding H4 (`reviews/2026-08-06_CLAUDE_REVIEW.md`): `before_save()` never fires on `patch()`, and the documentation recommends both.

## Problem

models.md teaches audit timestamps via `before_save()`. fastapi.md recommends `patch()` for partial updates. Follow both and `updated_at` silently stops moving, because field-level writes fire no hook.

The exclusion is correct in principle — `patch()` writes only the fields it was given, so a field set by mutating `self` inside a hook would be dropped on the way to storage. The defect is that the hook has no way to contribute a field to the write, so the two documented features cancel each other with no error and no output.

Two secondary problems surface alongside it:

- `before_save` is named after `save()`, one of the six write paths it fires on. The name understates its reach and invites exactly the wrong mental model.
- The rule is documented, but buried. models.md states it twenty lines below the timestamp recipe, as one clause in a "three rules worth remembering" paragraph, without the concrete consequence. fastapi.md, where the second half of the trap is taught, says nothing.

## Ecosystem context

The survey that shaped the coverage decision:

| Library | Whole-instance write | Partial instance write | Table/bulk write |
| --- | --- | --- | --- |
| Django | `pre_save` signal, `Field.pre_save` (`auto_now`) | `save(update_fields=[...])` fires `pre_save`; `auto_now` bumps only if the field is listed | `QuerySet.update()` fires nothing — documented |
| SQLAlchemy | `before_update` mapper event on flush | same (flush) | bulk `update()` skips mapper events; `Column.onupdate` survives only by compiling into the SQL |
| Beanie | `@before_event(Insert, Replace, Save)` | `@before_event(Update)` — `doc.set({...})` fires it | `find(...).update()` fires nothing |
| ODMantic | no lifecycle hooks | — | — |

Two patterns hold across all of them. Bulk writes never fire instance hooks — universal and deliberate. Partial _instance_ writes do. `patch()` is a partial instance write: it has `self`, an id, and one document. tinydantic is the outlier, and that outlier is H4.

## Design

### Renames

Both hooks are unreleased (`CHANGELOG.md` `[Unreleased]`; the released version is `0.4.0`), so these are renames before first release, not deprecations. No aliases, no shims. Reserved-name count stays at 27/28 — the existing unreleased CHANGELOG entries are edited in place rather than appended to.

- `after_load()` → `after_read()`. Pure rename; one call site, no semantic change.
- `before_save()` → `before_write()`. Rename plus a new signature and one new call site.

`write`/`read` mirrors TinyDB's own `Storage.read()`/`Storage.write()`, the layer directly beneath tinydantic, and matches the vocabulary the docs and config already use (`validate_writes`, "whole-model write", "field-level write", "the write boundary").

### The `before_write()` contract

```python
def before_write(
    self,
    fields: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Contribute fields to any instance-level write of self."""
```

**`fields`** — the model-field mapping about to be written, as validated Python values. Never contains `id` or `revision_id`. On `patch()` it is the caller's fields; on whole-model writes it is every model field.

**Return value** — a mapping of fields to add or override, or `None` for no contribution. Returned values are validated through `cls._field_adapter(key).validate_python`, applied to `self`, and written to storage.

**Fires on** `insert()`, `insert_multiple()` (once per document), `save()`, `replace()`, `upsert()`, and `patch()`.

**Does not fire on** `update()` or `update_all()`. They are classmethods that write by condition with no model instance, matching every ORM surveyed.

**Errors** — returning `id` raises `DocumentIDUpdateError`; returning `revision_id` on a `use_revision=True` model raises `RevisionUpdateError`. These are the rules `patch()` already enforces on caller input, applied to hook output. Raising from the hook aborts the write with nothing written. Overrides chain with `super().before_write(fields)`.

The canonical recipe becomes one hook that works on every instance write path:

```python
def before_write(self, fields):
    now = datetime.now(tz=datetime.timezone.utc)
    if self.id is None:
        return {"created_at": now, "updated_at": now}
    return {"updated_at": now}
```

### Mutating `self` is not supported

Assigning to `self` inside `before_write()` still happens to work on whole-model writes, because serialization reads `self` afterward. It is silently dropped by `patch()`, which writes only named fields.

This is documented as a hard rule — _always return the fields you want written; never mutate `self`_ — and is not enforced at runtime. A `__dict__` snapshot around the hook call would catch attribute rebinding but not in-place container mutation (`self.tags.append(...)` mutates the object both the snapshot and the instance point at, so a shallow comparison sees no change). A check that fires for some cases teaches users the library catches this class of mistake, which makes the uncaught cases worse than no check at all. Deep-copying every field on every write to close the gap is not worth the cost on a path the review already flags as the most expensive verb (M6). So: no check, an explicit warning instead.

### Cost

Building the full-field mapping on every whole-model write is wasted work for a default no-op hook. `__init_subclass__` records whether the subclass overrides the hook (`cls.before_write is not TinydanticModel.before_write`); models that do not override it skip both the mapping construction and the call. Unhooked models pay nothing.

## Call sites

Current, in `src/tinydantic/_model.py`:

| Line | Method                   | Change                          |
| ---- | ------------------------ | ------------------------------- |
| 918  | `from_tinydb_document()` | `after_load()` → `after_read()` |
| 946  | `insert_multiple()`      | new signature, per document     |
| 2131 | `upsert()`               | new signature                   |
| 2468 | `insert()`               | new signature                   |
| 2529 | `replace()`              | new signature                   |
| 2794 | `save()`                 | new signature                   |
| 2632 | `patch()`                | **new call site**               |

In `patch()` the hook runs after the caller's fields are validated into `validated` and before `serialized_patch` is built, so contributed fields flow through the existing unique-constraint merge, the `cls.update(...)` write, and the `self.__dict__` sync unchanged.

## Documentation

- **models.md** — rewrite the Lifecycle hooks section around one hook. State the consequence concretely where the recipe lives, not twenty lines below it: `update()` and `update_all()` write by condition with no instance, so they fire no hook and will not bump `updated_at`. Add the never-mutate-`self` warning.
- **crud.md** — one line in the `patch()` section noting the hook fires.
- **fastapi.md** — the `patch()` recommendation gets the counterpart note.
- **`patch()` docstring** — currently silent on hooks; document that `before_write()` fires and that returned fields join the write.
- **CHANGELOG.md** — edit the existing `[Unreleased]` entries in place.

## Testing

`tests/model/test_lifecycle_hooks.py`, renamed through and extended:

- Hook fires on all six instance write paths, once each; once per document for `insert_multiple()`.
- Hook fires on neither `update()` nor `update_all()`.
- Returned fields land in storage **and** on `self`, on both `save()` and `patch()`.
- Returning `id` raises `DocumentIDUpdateError`; returning `revision_id` raises `RevisionUpdateError`.
- Returning `None` writes normally.
- A raising hook writes nothing — on `patch()` as well as `insert()`.
- `super().before_write(fields)` chaining runs both.
- `fields` contents: caller's fields on `patch()`, all model fields on whole-model writes; never `id` or `revision_id`.
- `after_read()` fires on every materializing read with the real `id`; not on construction or insert; its mutations are not persisted.
- An unhooked model never builds the mapping (override-detection flag).
- models.md doctests, including one showing the return form behaving identically on `save()` and `patch()`.
