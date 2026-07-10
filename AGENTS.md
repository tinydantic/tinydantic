# AGENTS.md

tinydantic — a Pydantic v2 ODM for TinyDB. `TinydanticModel` subclasses are pydantic models bound to a TinyDB table via class kwargs (`database=`, `table_name=`) — see `src/tinydantic/_model.py`. Design rationale lives in module/method docstrings (start with `src/tinydantic/_config.py`) and the usage docs under `docs/usage/`. TinyDB extensions (storages, middlewares, operations) live in `src/tinydantic/tinydb/`.

## Setup

- `uv sync --all-groups` — installs the venv and every dependency group.
- `npm ci` — cspell/prettier/markdownlint run via `npx` from local `node_modules`; spell-check (and therefore `poe check`) fails without it.
- `uv run pre-commit install` — installs the pre-commit and commit-msg hooks.

## Conventions

- Conventional commits (commit-msg hook enforces).
- uv + poethepoet: `uv run poe test | lint | types | check | docs-build`. Also `fmt` (ruff autofix + format) and `pre-commit` (all hooks, all files).
- Windows/macOS/Linux are all first-class; no shell-isms in poe tasks.
- Python 3.10 is the floor (`requires-python`; mypy and ruff target py310) — no syntax newer than 3.10.
- Ruff runs with `select = ALL`: 79-char code lines, Google-style docstrings wrapped at 72 chars (W505 `max-doc-length`), relative imports banned.
- Tests include doctests in README, CONTRIBUTING, and docs — a lying example fails CI.
- Tests run shuffled (pytest-randomly) and parallel (pytest-xdist) — don't write order-dependent tests.
- Markdown: prettier enforces `proseWrap: never` (don't hard-wrap prose); markdownlint requires an H1 on line 1.
- REUSE licensing: new code files need SPDX headers; `**.md` and listed files are covered by `REUSE.toml` aggregates.
- cspell gates commits: new legit words go in `project-words.txt` (case-insensitive sorted).
- interrogate demands 100% docstring coverage.
- NEVER file issues on external repositories without explicit approval — draft collateral in `docs/upstream/` instead. If TinyDB friction blocks work, the sanctioned fallback is the <https://github.com/tinydantic/tinydb> fork.
- Do not store tinydantic config in pydantic's `model_config` (pydantic#9992) — see the `src/tinydantic/_config.py` module docstring.

## Docs

- Built by properdocs in strict mode — a broken link fails `poe docs-build`. Use `poe docs-serve` for live preview; mike handles versioned deploys.
- The API reference is generated at build time by `scripts/gen_api_docs.py` (mkdocs-gen-files) — `docs/reference/` is intentionally sparse on disk; don't hand-write pages there.

## CI

- Branch pushes do NOT trigger CI (only pushes to main, tags, and PRs do): `gh workflow run ci.yaml --ref <branch>`.
- Releases (full steps: CONTRIBUTING.md "Release Process"): hand-update `CHANGELOG.md`; on a release branch run `uv run cz bump --files-only` then `uv lock` (writes `[project].version` — no commit, no tag); merge via PR (`main` is protected); then tag `v<version>` on the merged main commit and push the tag.
- The release workflow's version-guard asserts tag == pyproject version, gates PyPI publishing on the package and docs builds, and creates the GitHub release itself — never create one manually in the web UI.
