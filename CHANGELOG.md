# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **BREAKING:** `patch` is now a reserved attribute name on tinydantic models — the first method added under the flat-namespace policy. A model with a field named `patch` raises `ShadowedFieldError` at class definition; opt out with `shadowed_fields=("patch",)` or rename the field.

- **BREAKING:** A model field whose name shadows an existing class attribute — a tinydantic method (`search`, `count`, ...), a pydantic method (`copy`, `json`, ...), or a method from your own base classes — now raises `ShadowedFieldError` at class definition instead of pydantic's easily-missed warning followed by silently broken `Model.field` query sugar. Opt in deliberately with the new `shadowed_fields=("name", ...)` class kwarg (inherited like the other config keys) and query such fields with `q("name")`.

- **BREAKING:** Selector misuse raises the new `SelectorError` (a `ValueError` subclass, so existing handlers keep working): zero-selector `get()`/`contains()`/`remove()` no longer leak TinyDB's `RuntimeError`, `upsert()` without a cond or a persisted `id` no longer leaks TinyDB's `ValueError` (whose "use a table.Document" hint means nothing in tinydantic), and the existing too-many-selector `ValueError` guards are upgraded to `SelectorError`. `remove()` with no selector points at `truncate()`.
- **BREAKING:** `insert()`/`insert_multiple()` with an already-taken `id` raise the new `DocumentAlreadyExistsError` (also a `ValueError` subclass) naming the model, table, and taken id(s) — including ids repeated within one batch — instead of TinyDB's raw `ValueError`.
- **BREAKING:** `update()`/`remove()` with an explicit `doc_ids` list containing a missing id raise `DocumentNotFoundError` (matching `replace()`/`delete()`) instead of a bare `KeyError`, and abort before anything is written.
- **BREAKING:** Attribute assignment is now validated (`validate_assignment` in the base `model_config`): assigning a value that fails validation raises `pydantic.ValidationError` immediately, and `model_validator(mode="after")` invariants re-run on every assignment. Subclasses can opt out with `model_config = ConfigDict(validate_assignment=False)`.
- **BREAKING:** Whole-model writes (`insert()`, `insert_multiple()`, `save()`, `replace()`, `upsert()`) validate their serialized payload before it reaches storage and raise `pydantic.ValidationError` for documents that would fail on their next read — closing the paths assignment validation cannot see (in-place container mutation, nested-model mutation, `object.__setattr__`). Opt out per model with the new `validate_writes=False` class kwarg.
- **BREAKING:** `update()` and `update_multiple()` validate each matched document's merged result (stored body plus new fields, or a transform callable's output) with the real document id visible to validators, before anything is written; a validation failure anywhere aborts the whole batch with nothing written. Transform callables can no longer write schema-invalid data by default; `validate_writes=False` restores the previous behavior. All mapping/transform updates now run through the atomic write cycle previously reserved for id-condition writes.
- **BREAKING:** Update mappings containing keys that are not model fields raise the new `UnknownUpdateFieldError` instead of writing them to storage unvalidated. Pass `extra_keys="allow"` to `update()`/`update_multiple()` to write them anyway (for databases shared with other tools or schema-evolution keys the model does not know yet).
- **BREAKING:** `YAMLStorage.write` now serializes with `yaml.safe_dump` (matching the `yaml.safe_load` used by reads) and raises `yaml.representer.RepresenterError` for values the safe dumper cannot represent — before the file is touched. Previously, full-Dumper `yaml.dump` wrote arbitrary Python objects as `!!python/object` tags that the storage's own read then refused to load, leaving the database file unreadable until hand-edited.
- `model_validator(mode="after")` hooks now observe the document's real `id` during reads (previously always `None`), and a stray legacy `id` key inside a stored document body is always masked by the actual `doc_id`.
- The code license is now MIT only (previously dual-licensed under Apache-2.0 OR MIT). The relicense is not retroactive: released versions up to and including 0.4.0 remain available under Apache-2.0 OR MIT. Documentation and images remain CC-BY-4.0.

### Added

- `patch()` — instance-level partial update: validates the given fields, writes only those fields to the stored document by id (atomic, merged-result-validated like `update()`), and syncs the instance after the write succeeds. Closes the lost-update trap of whole-document mutate-then-`save()` and the instance/storage drift of table-level `update(doc_ids=...)`.

- `shadowed_fields` configuration key and `ShadowedFieldError` — loud, definition-time detection of fields that would break the `Model.field` query shorthand, with an explicit per-class opt-out.

- `SelectorError` and `DocumentAlreadyExistsError` — completing the curated exception surface: no raw TinyDB or bare built-in exception leaks through tinydantic's public API.
- `validate_writes` configuration key (class kwarg, inherited like `database=`/`table_name=`): controls write-boundary re-validation; defaults to `True`.
- `UnknownUpdateFieldError` — raised for unknown keys in update mappings; a `TinydanticUserError` naming the offending keys and the escape hatch.

## [0.4.0] - 2026-07-10

### Changed

- **BREAKING:** `insert_multiple()` now mirrors `insert()`: each passed-in model's `id` is set in place to the id TinyDB assigned, and the same instances are returned in insertion order (`list[Self]`, previously `list[int]`). Read ids from the returned models' `id` attributes.
- **BREAKING:** `update()` and `update_multiple()` now give mapping values the same treatment `insert()` and `save()` give whole models: values that name model fields are validated against the field's type (invalid values raise `pydantic.ValidationError`) and serialized to JSON-safe primitives before reaching storage, so rich values such as `datetime` round-trip instead of corrupting JSON storage. Keys that are not model fields, and transform callables, pass through unchanged.
- **BREAKING:** `DocumentNotFoundError` and `DocumentIDRequiredError` now take keyword arguments when constructed directly, and their messages name the model, table, document id, and operation (for example `No document with id 42 in table 'books' (model 'Book')`).

### Added

- `get_or_raise()` — the strict counterpart to `get()`: fetches a single document by condition or `doc_id` and raises `DocumentNotFoundError` instead of returning `None` when no document matches.
- `count()` can now be called with no arguments to count all documents in the table.
- `q()` now accepts a field name as a string (`q("search") == "fuzzy"`), the escape hatch for querying fields whose names collide with model methods such as `search` or `get`.

## [0.3.1] - 2026-07-09

### Added

- `PYTHON_OBJECTS_INV`, `PYDANTIC_OBJECTS_INV`, and `TINYDB_OBJECTS_INV` environment variables that point the documentation build at local copies of the corresponding Sphinx object inventories, as a workaround for bot challenges (such as Read the Docs' Cloudflare challenge) rejecting mkdocstrings' inventory downloads.

## [0.3.0] - 2026-07-09

### Added

- Support for Python 3.10.

## [0.2.0] - 2026-07-06

### Changed

- **BREAKING:** The base class is now `TinydanticModel` (previously `Document`). Configure it with class keyword arguments—`database=` and `table_name=`—and rebind a model to a different database at runtime with `bind()`.
- **BREAKING:** A document's `id` is now included in `model_dump()`, and stored documents are serialized in JSON mode. Calling `save()` on an instance that has never been persisted now inserts it.
- **BREAKING:** `get()` selector arguments have been renamed to `doc_id` and `doc_ids` and are now keyword-only. Passing more than one selector raises `ValueError`, and `get(doc_ids=...)` returns a `list[Self]`, silently skipping any ids that are not found.
- **BREAKING:** The minimum supported Python version is now 3.11 (previously 3.8). PyPy is no longer claimed as a supported runtime.
- **BREAKING:** `DocumentIDRequiredError` no longer subclasses `ValueError`. All library exceptions now derive from a common `TinydanticError` base.
- Tooling: the project build backend moved from hatch to uv with `poethepoet` task running and `uv_build` (versioning is now static, managed by commitizen); the documentation engine is now ProperDocs, and the docs site gained eight new usage pages.

### Added

- A full Table API surface: `search`, `contains`, `update`, `update_multiple`, `upsert`, and `remove`.
- A `delete()` method for removing documents.
- Convenience lookups: `get_by_cond`, `get_by_id`, and `get_by_ids`.
- A `q()` query helper.
- Error classes are now exported from the package root.
- A `py.typed` marker so downstream type checkers pick up tinydantic's type hints.

### Fixed

- `save()` no longer crashes when called on an instance that has not yet been persisted.
- `replace()` no longer leaks a `KeyError` when the target document does not exist.
- `datetime`, `UUID`, and nested model fields now round-trip correctly through storage.

[unreleased]: https://github.com/tinydantic/tinydantic/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/tinydantic/tinydantic/compare/v0.3.1...v0.4.0
[0.3.1]: https://github.com/tinydantic/tinydantic/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/tinydantic/tinydantic/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/tinydantic/tinydantic/compare/v0.1.19...v0.2.0
