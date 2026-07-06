# Milestone 4: Docs & Examples Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Swap MkDocs core for ProperDocs, fill every remaining TODO docstring, ship the seven doctested example pages plus the Configuration page, and add CLAUDE.md.

**Architecture:** Milestone 4 of 5 from `docs/superpowers/specs/2026-07-05-tinydantic-v0.2-design.md` (§3.2 documentation requirement, §8.4, §8.5, §9). Builds on `cdwilson/v0.2.0-m3-api` (HEAD `e3d14cc`, 966 tests). Every example page is doctested (`--doctest-glob '*.md'` over `docs/`), so a page that lies fails CI. New usage pages live under `docs/usage/`; the nav is awesome-pages-driven (`docs/.pages` + per-directory `.pages` files).

**Doctest mechanics (read before writing any page):** pycon blocks (` ```pycon `) with `>>>` lines are executed by pytest. `doctest_optionflags = NORMALIZE_WHITESPACE IGNORE_EXCEPTION_DETAIL` is configured. Each page's doctest namespace is independent but SHARED WITHIN the page (top-to-bottom). Use `TinyDB(storage=MemoryStorage)` for all examples unless the page is specifically about file storage (then use `tempfile`). Repr output must match exactly (e.g. `User(id=1, name='Alice')` — field order follows model definition, `id` first since it's inherited... verify by running; write reprs from actual output, never from memory).

## Global Constraints

- Conventional commits + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer; hooks reformat (`git add -u`, retry); cspell → `project-words.txt` + `sort --ignore-case -u project-words.txt -o project-words.txt`. New markdown files are REUSE-covered by the existing `**.md` annotation — no headers needed.
- Gate per task: `uv run poe test` (doctests included) AND `uv run poe docs-build` (strict) green.
- **Query style decision (M3 review):** examples teach the bare runtime form (`User.name == "Alice"`). Exactly ONE section — "Static type checking" on the Queries page — teaches `q()`. Be consistent everywhere else.
- Documented sharp edges that MUST appear (M3 review findings): `update()`/`update_multiple()` pass fields to storage raw (no pydantic serialization); `get(doc_ids=...)`/`get_by_ids` skip missing ids and order by storage iteration (no positional correspondence); `save()` re-inserts a vanished document while `replace()`/`delete()` raise.
- Never file issues upstream. ProperDocs friction gets logged in reports.
- Prose style: match the existing docs voice (friendly, direct, light emoji use like the README). Address the reader as "you".

---

### Task 1: Branch + ProperDocs swap + new doc dependencies

**Files:** `pyproject.toml` (docs group; test group), `uv.lock`, possibly `mkdocs.yaml`.

- [ ] **Step 1:** `git checkout cdwilson/v0.2.0-m3-api && git checkout -b cdwilson/v0.2.0-m4-docs && uv run poe test` (966 expected).
- [ ] **Step 2:** Read the ProperDocs migration guide FIRST: fetch <https://github.com/orgs/ProperDocs/discussions/33> (use `gh api` or curl). Follow it: in the `docs` dependency group, replace the implicit mkdocs core with `properdocs` (mkdocs-material pulls in `mkdocs` — check whether the guide says to exclude/override it; uv supports `override-dependencies` under `[tool.uv]` if needed). Add `fastapi` and `httpx` to BOTH the `test` and `docs` groups (spec §9.7 — the FastAPI page's doctests need them). `uv lock && uv sync --all-groups`.
- [ ] **Step 3:** Verify the engine: `uv run poe docs-build` must produce `site/` strictly-clean using ProperDocs (`uv run pip show properdocs mkdocs` — report what's actually installed and which package provides the `mkdocs` command/module now). All 10 plugins must still work. `uv run poe docs-serve` is NOT part of the gate (no interactive check).
- [ ] **Step 4:** CONTINGENCY: if ProperDocs cannot run this plugin set (a plugin hard-pins mkdocs internals ProperDocs changed), STOP — report BLOCKED with the exact plugin + error. Do not silently stay on mkdocs.
- [ ] **Step 5:** Full suite + commit `build(docs): switch docs engine from mkdocs to properdocs` (+ trailer), noting in the body what provides the mkdocs module now.

---

### Task 2: Fill every remaining TODO docstring

**Files:** `src/tinydantic/_model.py` (8 methods: `from_tinydb_document`, `insert_multiple`, `all`, `truncate`, `count`, `clear_cache`, `insert`, `replace`), `src/tinydantic/tinydb/*.py` (check for TODO stubs), `tests/**` TODO stubs (module/class/test docstrings in `tests/model/test_model_get.py`, `test_model_insert.py`, `test_model_attributes.py`, `test_model_table.py`, `test_model_validation.py`, `tests/conftest.py`, others `grep -rn "TODO: needs docstring"` finds).

- [ ] **Step 1:** `grep -rn "TODO: needs docstring" src tests scripts` — that's your worklist. Zero hits must remain afterward.
- [ ] **Step 2:** Write real Google-style docstrings. For the 8 `_model.py` methods: match the quality/voice of the M3-written ones (`save`, `delete`, `update`...); mkdocstrings crossref syntax (`[Table.insert][tinydb.table.Table.insert]` etc.) where a TinyDB concept is referenced; `insert()` documents the duplicate-id `ValueError` from TinyDB; `replace()` documents `DocumentIDRequiredError`/`DocumentNotFoundError`; `from_tinydb_document` explains the doc_id → id mapping; `all()` notes it returns validated models. Test docstrings: one line describing the behavior under test.
- [ ] **Step 3:** `uv run poe test && uv run poe lint && uv run poe docs-build` green (docs-build validates every new crossref). Commit `docs: replace all TODO docstring stubs with real documentation` + trailer.

---

### Task 3: Usage pages — Quickstart, CRUD tour, Queries

**Files:** Create `docs/usage/.pages`, `docs/usage/index.md`, `docs/usage/quickstart.md`, `docs/usage/crud.md`, `docs/usage/queries.md`; modify `docs/.pages` (add `usage` after `get_started`).

- [ ] **Step 1:** `docs/usage/.pages`:

```yaml
title: Usage
nav:
  - Usage: index.md
  - quickstart.md
  - crud.md
  - queries.md
  - models.md
  - storage.md
  - configuration.md
  - testing.md
  - fastapi.md
```

(models/storage/configuration/testing/fastapi land in Tasks 4–5; awesome-pages tolerates listing them early ONLY if they exist — so create all nine files in THIS task, with Tasks 4–5 pages as one-line placeholder headings that Task 4/5 replace. Strict nav checks pass because the files exist.)

`docs/usage/index.md`: a short hub page — one paragraph and a bulleted description linking each page.

- [ ] **Step 2: quickstart.md.** The README basic example expanded: create db (memory), define `User(TinydanticModel, database=db, table_name="users")` with `name: str` + `email: EmailStr`, insert, `get(User.name == "Alice")`, mutate + `save()`, `delete()`. All pycon, all doctested. End with "where next" links.
- [ ] **Step 3: crud.md.** Sections per operation group, every method appears at least once in a pycon block: Create (`insert`, `insert_multiple`, classmethod `upsert`), Read (`all`, `get` incl. `doc_id=`/`doc_ids=` forms, `get_by_cond`/`get_by_id`/`get_by_ids`, `search`, `contains`, `count`), Update (`save`, `replace`, `update`, `update_multiple`), Delete (`delete`, `remove`, `truncate`). MUST include admonition callouts for the three sharp edges (global constraints): raw `update()` values, `doc_ids` skip-and-reorder semantics (show it: request `[2, 1, 999]`, get storage-order results without 999), `save()` vs `replace()`/`delete()` on vanished documents (show both behaviors).
- [ ] **Step 4: queries.md.** Field queries (`==`, `!=`, `<`, `.matches`, `.search`, `.test`), logical composition (`&`, `|`, `~`), nested fields (`User.address.city == ...` with a nested model), escaping to raw `tinydb.Query()` for anything exotic, THE "Static type checking" section (why type checkers see `bool`, `q(User.name) == "Alice"` fixes it — SQLModel `col()` comparison, one pycon block using `q`), and a callout on the field/method shadowing footgun (a field named `search` shadows the classmethod; escape hatch: `tinydb.Query()`).
- [ ] **Step 5:** `uv run poe test` (all new doctests pass) + `uv run poe docs-build` green. Commit `docs: add quickstart, CRUD tour, and queries usage pages` + trailer.

---

### Task 4: Usage pages — Real models, Storage, Configuration

**Files:** Replace placeholder `docs/usage/models.md`, `docs/usage/storage.md`, `docs/usage/configuration.md`.

- [ ] **Step 1: models.md** ("Real Pydantic models"). datetime/UUID/enum/nested-model fields round-tripping (pycon: insert, fetch, assert types via repr), validators (`field_validator` example that rejects bad data on load — the README Carol scenario generalized), defaults/default_factory, and a section showing what's stored (raw `get_table().get(...)` exposing JSON primitives) explaining spec §3.7 mode="json" semantics.
- [ ] **Step 2: storage.md.** In-memory (tests/scratch), JSON file (`tempfile` doctest), tinydantic's YAMLStorage (`from tinydantic.tinydb.storages import YAMLStorage`), CachingMiddleware composition, and a note that `tinydantic.tinydb` extras may become a standalone package (spec §6). Show `db.close()` / context-manager usage for file storages.
- [ ] **Step 3: configuration.md** — the spec §3.2 REQUIRED page. Cover: class kwargs (`database=`, `table_name=`), table-name derivation (`AdminUser` → `admin_user`), config inheritance through subclassing (pycon: base bound, child inherits, child overrides `table_name` only), `bind()` late binding, `DatabaseNotBoundError`, the ambiguity error (pycon: two differently-bound bases, diamond raises `AmbiguousConfigError`, explicit kwarg resolves), AND the design-note section: why config does not live in `model_config` (pydantic#9992 last-wins vs MRO, link the issue), matching the code docstrings.
- [ ] **Step 4:** Gate + commit `docs: add models, storage, and configuration usage pages` + trailer.

---

### Task 5: Usage pages — Testing + FastAPI

**Files:** Replace placeholder `docs/usage/testing.md`, `docs/usage/fastapi.md`.

- [ ] **Step 1: testing.md.** In-memory fixtures (the subclass-in-fixture pattern from this repo's own conftest, shown as a pytest example in a plain python block — pytest fixtures can't run as doctests; mark the block ` ```python ` so it's illustrative), `bind()` for app factories, `truncate()` between tests, and a doctested pycon block showing bind-based swapping.
- [ ] **Step 2: fastapi.md** (spec §9.7). A small CRUD API: define model, `POST /users` (inserts, returns model — `id` in the response per §3.6), `GET /users/{id}` (404 via `get_by_id` returning None), `GET /users` (`all()`). Exercise via `fastapi.testclient.TestClient` in doctested pycon blocks (TestClient is synchronous — doctest-friendly; verify status codes and JSON bodies). Then the async guidance section (spec: plain-`def` endpoints run in FastAPI's threadpool — the correct default; `asyncio.to_thread` for `async def`; TinyDB has no concurrency safety — single-process, and writes should come from one place). Mention the aiotinydb analysis conclusion in one sentence (link spec non-goals? no — just state sync-first guidance).
- [ ] **Step 3:** Gate + commit `docs: add testing and FastAPI usage pages` + trailer.

---

### Task 6: CLAUDE.md + get_started refresh + final gate

**Files:** Create `CLAUDE.md`; modify `docs/get_started/basic_example.md` (verify it still renders the README include correctly), `docs/get_started/index.md` (link to Usage).

- [ ] **Step 1: CLAUDE.md** at repo root:

```markdown
# CLAUDE.md

tinydantic — a Pydantic v2 ODM for TinyDB. `TinydanticModel` subclasses are pydantic models bound to a TinyDB table via class kwargs (`database=`, `table_name=`) — see `src/tinydantic/_model.py`.

## Authoritative documents

- Design spec (v0.2.0, decision log included): `docs/superpowers/specs/2026-07-05-tinydantic-v0.2-design.md`
- Implementation plans + execution ledger: `docs/superpowers/plans/`, `.superpowers/sdd/progress.md`

## Conventions

- Conventional commits (commit-msg hook enforces); commits end with the Claude co-author trailer when authored by Claude.
- uv + poethepoet: `uv run poe test | lint | types | check | docs-build`. Tests include doctests in README/docs — a lying example fails CI.
- Windows/macOS/Linux are all first-class; no shell-isms in poe tasks.
- REUSE licensing: new code files need SPDX headers; `**.md` and listed files are covered by `REUSE.toml` aggregates.
- cspell gates commits: new legit words go in `project-words.txt` (case-insensitive sorted).
- interrogate demands 100% docstring coverage.
- NEVER file issues on external repositories without Chris's explicit approval — draft collateral in `docs/upstream/` instead. If TinyDB friction blocks work, the sanctioned fallback is the https://github.com/tinydantic/tinydb fork.
- Do not store tinydantic config in pydantic's `model_config` (pydantic#9992) — see `src/tinydantic/config.py` module docstring.

## CI

- Branch pushes do NOT trigger CI: `gh workflow run ci.yaml --ref <branch>`.
- Releases: `uv run cz bump` writes `[project].version` + tags; the publish workflow's version-guard asserts tag == pyproject version.
```

- [ ] **Step 2:** `docs/get_started/index.md`: add a pointer to the Usage section. Confirm `basic_example.md` still doctests green (it includes the README).
- [ ] **Step 3: Full gate:** `uv run poe check && uv run poe test-cov && uv run poe docs-build-check && uv run poe pre-commit && uv build && rm -rf dist`. NOTE `docs-build-check` (not just build) — it runs linkchecker over the built site; broken intra-site links from the new pages fail here.
- [ ] **Step 4:** Commit `docs: add CLAUDE.md and link usage docs from get started` + trailer. Push + dispatch CI (`gh workflow run ci.yaml --ref cdwilson/v0.2.0-m4-docs`), watch to green (14 jobs). Do NOT merge.
