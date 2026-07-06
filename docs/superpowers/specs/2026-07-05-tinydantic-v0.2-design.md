# tinydantic v0.2.0 Design Spec

**Date:** 2026-07-05 **Status:** Approved by Chris Wilson (pending final spec review) **Authors:** Chris Wilson + Claude (design conversation, 2026-07-05)

This document is the durable record of the v0.2.0 design so any future session (any model) can pick up the work without the original conversation. Read this together with the implementation plan in `docs/superpowers/plans/` (created after this spec is approved).

## 1. Project goal

`tinydantic` is a Python object-document mapper (ODM) for [TinyDB](https://tinydb.readthedocs.io/) built on [Pydantic](https://docs.pydantic.dev/) v2. Target audience: developers who already know **pydantic, SQLModel, FastAPI, and TinyDB** — the API must feel natural to them.

v0.2.0 is a breaking release (allowed under SemVer 0.y.z; latest release is 0.1.19) that:

1. Completes the ODM so `TinydanticModel` cleanly covers TinyDB's `Table` API.
2. Replaces the `Document` base class with `TinydanticModel` configured via class kwargs (SQLModel-style).
3. Modernizes tooling: hatch → uv + poethepoet, MkDocs → ProperDocs, Python ≥3.11, all dependencies updated to latest.
4. Ships a doctested set of usage examples.

### Non-goals for 0.2.0 (documented "future ideas")

- Async support (TinyDB is sync; aiotinydb exists but is out of scope)
- Document references/relationships
- Unique constraints / indexes
- Custom document ID types (TinyDB `Table.document_id_class`)
- Multi-database binding for one model
- Zensical docs migration (ProperDocs is the interim step)

## 2. Branch strategy

- Base all work on `cdwilson/initial-prototype-and-docs` (tests pass there). Create new feature branch(es) off it; final PR to `main`.
- `cdwilson/refactor` (commit `2b2e150`) is a half-finished version of this same redesign: source renamed to `TinydanticModel` with config in `model_config`, but tests never updated (they still set `database = db` class attributes) and it imports `typing.override` (3.12+) while claiming 3.8 support. **Mine it for ideas, then delete it.** This spec supersedes it.
- Delete the stray `src/tinydantic/_document_old.py.tmp`.

## 3. Core API

### 3.1 The base class

```python
from tinydb import TinyDB
from tinydantic import TinydanticModel

db = TinyDB("app.json")

class User(TinydanticModel, database=db, table_name="users"):
    name: str
    email: str

alice = User(name="Alice", email="alice@example.com")
alice.insert()                        # sets alice.id
User.get(User.name == "Alice")        # -> User instance (validated)
```

**Name:** `TinydanticModel` (not `Document`). Rationale: TinyDB has a real public `tinydb.table.Document` class returned by `Table.get()`; exporting our own `Document` collides in imports, docs prose, and tracebacks. Precedent: SQLModel's package-named base class. In tinydantic vocabulary, "document" always means the stored TinyDB record; "model" means the user's Pydantic class.

### 3.2 Configuration: class kwargs, tinydantic-owned storage

**User-facing API:** class keyword arguments (`database=`, `table_name=`), exactly like SQLModel's `class Hero(SQLModel, table=True)`.

**Mechanism (approach B from the design discussion):**

- `TinydanticConfig` is a **plain `TypedDict`** (NOT extending `pydantic.ConfigDict`) with keys `database: TinyDB` and `table_name: str | None`.
- Config kwargs are received via **`__init_subclass__`** (with the ambiguity check in `__pydantic_init_subclass__`, which runs after pydantic finishes building the class) — public, documented pydantic extension points. Verified against pydantic source (`ConfigWrapper.for_model`): pydantic pops only recognized `ConfigDict` keys from class kwargs; the rest flow to `__init_subclass__`. **No metaclass involvement in config.**
- Each class stores only the keys explicitly set on it, in its own `__tinydantic_config__` class attribute. Lookup walks `cls.__mro__` for the first class whose config contains the key — standard Python attribute semantics.
- **Ambiguity error:** at class definition time, if two bases would supply _conflicting_ values for the same tinydantic key and the new class doesn't set that key explicitly, raise a definition-time error naming the bases and the fix ("set `database=` explicitly on `C`").

**Why not store in `model_config`** (what the refactor branch and SQLModel/pydantic-settings do): pydantic merges `model_config` across multiple bases in "last wins" order — the _opposite_ of Python's MRO (pydantic#9992). Pydantic's maintainers agree it's concerning; fix PRs (#9995, #9996) were rejected as breaking; a v3 change is speculative. Storing our keys there would (a) inherit those semantics, (b) risk future key collisions with `ConfigDict`, (c) couple us to behavior pydantic may flip. With approach B + the ambiguity error, there is no scenario where "our order vs pydantic's order" silently matters: single-inheritance chains resolve identically under both orderings, and multi-base conflicts are loud errors.

**Documentation requirement (explicit request from Chris):** this design — MRO-based lookup, the ambiguity error, and why tinydantic config deliberately does not live in `model_config` — must be prominently documented BOTH in the code (docstrings on `TinydanticConfig`, `__init_subclass__`, and the lookup helper, citing pydantic#9992) AND in the docs site (a dedicated "Configuration" page section explaining inheritance behavior with examples).

- Keep `protected_namespaces=("tinydantic_",)` in `model_config` (a legitimate pydantic key) to reserve the `tinydantic_` prefix for future methods (per Samuel Colvin's guidance in pydantic#10315).

### 3.3 Late binding

`Model.bind(database=..., table_name=...)` classmethod updates the class's `__tinydantic_config__` after definition — for tests and app factories where no `TinyDB` exists at import time. Any table operation on an unbound model raises `DatabaseNotBoundError` with a message pointing at both binding options. Subclass-in-fixture (the existing test pattern) remains supported and documented.

### 3.4 Table naming

Default table name: `pydantic.alias_generators.to_snake(cls.__name__)` (`AdminUser` → `admin_user`), overridable via `table_name=`.

### 3.5 Query sugar and the metaclass

- `User.name` at class level returns `tinydb.queries.where("name")` via metaclass `__getattr__`, so `User.name == "Alice"` is a TinyDB query. Nested access chains naturally (`User.address.city == "X"`), since TinyDB `Query` supports attribute chaining.
- The metaclass now does ONLY this (config moved to `__init_subclass__`). Obtain the base metaclass without private imports at runtime:

  ```python
  if TYPE_CHECKING:
      from pydantic._internal._model_construction import ModelMetaclass
  else:
      ModelMetaclass = type(BaseModel)  # no private import at runtime
  ```

- Guard (from prototype): only return queries once `__pydantic_complete__` is true and `attr in cls.model_fields`.
- **`q()` helper** (5-line `col()` equivalent; name `q` chosen over SQL-flavored `col` — subject to final veto in spec review): type checkers see `User.name == "Alice"` as `bool`, not `QueryLike` (same wart as SQLModel; metaclasses don't run statically). `q(User.name)` is a runtime identity function (with an `isinstance(field, Query)` check) typed `(Any) -> Query`, so `User.search(q(User.name) == "Alice")` typechecks. Docs get a "Static type checking" section showing both forms.
- **Documented footgun:** user fields named like classmethods (`search`, `update`, `count`, …) shadow them silently. Pydantic's shadow warning covers most cases; raw `tinydb.Query()` always works as the escape hatch. Docs callout, not a redesign.

### 3.6 The `id` field

- `id: int | None = None` — **without** `Field(exclude=True)`. The prototype's `exclude=True` silently dropped `id` from ALL serialization, so FastAPI responses lost it. Now `model_dump()` / FastAPI responses include `id`.
- `id` is excluded only when writing to storage: `model_dump(mode="json", exclude={"id"})`.

### 3.7 Serialization round-trip

`to_tinydb_document()` uses **`model_dump(mode="json")`** (prototype used Python-mode `model_dump()`, which crashes JSON storage on `datetime`, `UUID`, enums, …). Reads go through `model_validate`, which converts JSON values back to rich types. This makes "any JSON- serializable Pydantic model round-trips through storage" a tested guarantee.

## 4. CRUD surface (complete TinyDB Table mirror)

Instance methods:

| Method | Behavior |
| --- | --- |
| `insert()` | Insert; sets `self.id`; returns `self` |
| `save()` | **Fixed semantics:** `insert()` if `id is None`, else upsert by id. (Prototype passed a bare dict to `Table.upsert()` with no cond — confirmed `ValueError` against TinyDB source.) |
| `replace()` | Update-by-id with full replacement; `DocumentIDRequiredError` if unbound id; `DocumentNotFoundError` if gone |
| `delete()` | **New.** Remove by `self.id`; `DocumentIDRequiredError` if id unset; `DocumentNotFoundError` if not in table |

Class methods: `insert_multiple(docs)`, `all()`, `search(cond)`, `contains(cond=... | doc_id=...)`, `update(fields | transform, cond=..., doc_ids=...)`, `update_multiple(updates)`, `upsert(doc, cond=...)`, `remove(cond=..., doc_ids=...)`, `truncate()`, `count(cond)`, `clear_cache()` — mirroring `tinydb.table.Table` signatures and returning validated model instances where documents come back, doc-id lists where TinyDB returns doc ids.

**Deliberate deviation — `get()` split for sane return types** (TinyDB's overloaded `get()` returns `Document | list[Document] | None`):

- `get(cond) -> Self | None`
- `get_by_id(doc_id) -> Self | None`
- `get_by_ids(doc_ids) -> list[Self | None]`

Docs note the mapping to TinyDB's single `get()`. Exact `get_by_ids` missing-id behavior mirrors TinyDB 4.8.x (verify against source during implementation).

## 5. Errors

Keep the refactor branch's hierarchy, renaming for the new vocabulary:

- `TinydanticError` (base)
  - `TinydanticUserError`
    - `DatabaseNotBoundError` (replaces `TinydanticDatabaseMissingError`)
    - `AmbiguousConfigError` (the §3.2 config ambiguity error)
  - `DocumentNotFoundError`
  - `DocumentIDRequiredError`

## 6. Package layout

```text
src/tinydantic/
  __init__.py      # public: TinydanticModel, TinydanticConfig, q, errors, __version__
  _model.py        # TinydanticModel + thin query metaclass + q()
  config.py        # TinydanticConfig + MRO lookup + ambiguity check
  errors.py
  tinydb/          # TinyDB extensions — future extraction candidate
    storages.py    # YAMLStorage
    middlewares.py # ReadOnlyMiddleware
    operations.py  # replace()
```

`tinydantic.tinydb` must stay dependency-clean (no imports from tinydantic core; core → `operations.replace` is the only allowed edge) so it can later be extracted into a standalone package. Docs give it a separate "TinyDB extensions" section noting possible future extraction.

## 7. TinyDB friction log

TinyDB is in maintenance mode. When TinyDB bugs/design issues make tinydantic harder (first known case: `Table.update()` annotates `fields` as `Callable[[Mapping], None]` though it accepts a `Mapping`, forcing an ugly cast):

1. Record the issue + full drafted collateral (title, body, minimal repro) under `docs/upstream/` in this repo.
2. **NEVER file upstream issues/PRs without Chris's explicit approval** (standing rule).
3. If friction becomes blocking, the sanctioned fallback is switching the dependency to the fork <https://github.com/tinydantic/tinydb/>; keep this a one-line pyproject change.

## 8. Tooling & infrastructure

### 8.1 Cross-platform requirement

**Windows, macOS, and Linux are all first-class.** Poe tasks must be shell-neutral, no Makefiles, CI test matrix runs on all three OSes.

### 8.2 hatch → uv + poethepoet

- uv manages the project; commit `uv.lock`.
- Dev/test/docs/types dependencies move from `[project.optional-dependencies]` to `[dependency-groups]` (PEP 735).
- **Build backend stays `hatchling` + `hatch-vcs`** (VCS-driven versioning; uv's own backend doesn't provide it). uv is orthogonal to the backend.
- Hatch envs/scripts → **poethepoet** tasks in `pyproject.toml` (`uv run poe check`, `test`, `docs`, …). Chosen over just/taskipy/make: most-downloaded pyproject-native runner (~5M/mo), 1:1 translation from hatch scripts, keeps tasks in TOML where taplo/schema tooling applies, cross-platform.
- CI workflows switch to `astral-sh/setup-uv` + `uv sync`; keep the existing four-workflow structure (ci / docs-dev / docs-release / publish-python-package) and the existing tag-driven release process.

### 8.3 Python & dependencies

- `requires-python = ">=3.11"`. CI matrix: CPython 3.11–3.14 × {ubuntu, windows, macos}. Native `typing.Self`; do NOT use `typing.override` (3.12+) — not needed by the new code. Drop the `typing_extensions` and `eval_type_backport` runtime deps.
- Drop PyPy classifiers (not CI-tested).
- All dependencies to latest: pydantic 2.13.x (floor `>=2.11`), tinydb 4.8.x (floor `>=4.8`), ruff, mypy, pre-commit hooks, all mkdocs plugins.
- Update classifiers: `Development Status :: 3 - Alpha`, Python 3.11–3.14.

### 8.4 Docs: MkDocs → ProperDocs

- ProperDocs (v1.6.x) is an actively-maintained drop-in fork of abandoned **MkDocs core**; mkdocs-material (maintenance mode, 9.7.x) stays as the theme, existing plugin set kept and updated. Follow the ProperDocs migration guide (github.com/orgs/ProperDocs/discussions/33).
- Zensical migration is a future project once docs are worth rewriting.

### 8.5 CLAUDE.md

Add a root `CLAUDE.md`: short project overview, pointer to this spec and the implementation plan, branch strategy, conventions (conventional commits, REUSE headers, doctested docs, cross-platform rule, the never-auto-file-upstream rule).

## 9. Examples set (docs deliverable)

Six doctested pages (pytest already runs `--doctest-glob '*.md'` over `docs/`), so every example is CI-verified:

1. **Quickstart** — README basic example on the new API.
2. **CRUD tour** — every method incl. `delete()`, `save()`, `upsert()`.
3. **Queries** — field queries, logical ops, nested fields, `q()` for type checkers, escaping to raw `tinydb.Query`.
4. **Real Pydantic models** — datetime/UUID/enum/nested models, validators, defaults; round-trip through JSON storage.
5. **Storage options** — JSON file, in-memory, YAMLStorage, caching middleware.
6. **Testing your models** — in-memory fixtures, `bind()` vs subclass-in-fixture patterns.

README's basic example is updated to the new API (it's included into docs and doctested).

## 10. Testing & quality

- TDD (superpowers workflow). Port existing test suites to the new API first — they are the spec for the port — then per-method tests for newly implemented operations.
- New test areas: round-trip serialization (datetime/UUID/nested), unbound-model errors, config inheritance incl. the ambiguity error, `save()` on fresh instances, `id` present in `model_dump()`, metaclass-pin test (fails loudly if a pydantic upgrade breaks `type(BaseModel)` assumptions).
- Fill every `TODO: needs docstring` (interrogate enforces 100%).
- Keep: coverage, ruff, mypy, pre-commit, REUSE, cspell, doctests.

## 11. Order of work

1. **Tooling foundation** (new branch): uv migration + poe + dependency updates + Python ≥3.11 + CI matrix — with existing prototype code still passing tests throughout.
2. **Port the core**: `TinydanticModel`, `TinydanticConfig` + `__init_subclass__` config + ambiguity error + `bind()` + thin metaclass + `q()`; tests updated; old naming and refactor branch deleted.
3. **Complete the API**: six stubbed methods + `delete()` + `get` split + `save()` fix + JSON-mode serialization + id-serialization fix. TDD.
4. **Docs & examples**: ProperDocs swap, six example pages, API reference docstrings, configuration-inheritance docs (§3.2), CLAUDE.md.
5. **Release prep**: changelog, classifiers, tag `v0.2.0`, existing pipeline publishes to PyPI + deploys docs.

## 12. Decision log (for future sessions)

| Decision | Choice | Why |
| --- | --- | --- |
| Base class name | `TinydanticModel` | tinydb.table.Document collision; SQLModel precedent |
| Config API | Class kwargs | SQLModel-style; matches refactor branch intent |
| Config storage | Own `__tinydantic_config__`, MRO lookup + ambiguity error | pydantic#9992 last-wins merge; collision risk; own semantics |
| Config kwargs plumbing | `__init_subclass__` (public hook) | Verified in pydantic source; kills metaclass config code |
| Metaclass base | `type(BaseModel)` at runtime | No private import; TYPE_CHECKING-only static hint |
| `get()` | Split: `get`/`get_by_id`/`get_by_ids` | Sane return types |
| Storage serialization | `model_dump(mode="json", exclude={"id"})` | datetime/UUID round-trip; id visible to FastAPI |
| Type-checker helper | `q()` | SQLModel `col()` analog; "col" is SQL vocabulary |
| Python floor | 3.11 | 3.10 near EOL; native `Self`; no typing_extensions |
| Task runner | poethepoet | pyproject-native, most popular, cross-platform |
| Docs engine | ProperDocs + mkdocs-material | MkDocs abandoned; Zensical not plugin-ready |
| Build backend | hatchling + hatch-vcs (kept) | uv backend lacks VCS versioning |
| Version | 0.2.0 (breaking; 0.1.19 already released) | SemVer 0.y.z |
| PyPy | Dropped from classifiers | Not CI-tested |
| Upstream issues | Draft collateral only; file only with explicit approval | Chris's standing rule |
