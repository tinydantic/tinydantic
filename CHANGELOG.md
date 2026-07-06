# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[unreleased]: https://github.com/tinydantic/tinydantic/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/tinydantic/tinydantic/compare/v0.1.19...v0.2.0
