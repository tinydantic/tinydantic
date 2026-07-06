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
- NEVER file issues on external repositories without Chris's explicit approval — draft collateral in `docs/upstream/` instead. If TinyDB friction blocks work, the sanctioned fallback is the <https://github.com/tinydantic/tinydb> fork.
- Do not store tinydantic config in pydantic's `model_config` (pydantic#9992) — see `src/tinydantic/config.py` module docstring.

## CI

- Branch pushes do NOT trigger CI: `gh workflow run ci.yaml --ref <branch>`.
- Releases: `uv run cz bump` writes `[project].version` + tags; the publish workflow's version-guard asserts tag == pyproject version.
