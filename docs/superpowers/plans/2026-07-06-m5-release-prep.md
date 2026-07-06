# Milestone 5: Release Prep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repository release-ready for v0.2.0 — changelog, M4-review cleanups, deploy-path de-risking, and a verified release runbook — WITHOUT merging to main or pushing the release tag (those two actions are reserved for Chris; a published PyPI version is irreversible).

**Architecture:** Milestone 5 of 5 from `docs/superpowers/specs/2026-07-05-tinydantic-v0.2-design.md` §11.5, amended by explicit instruction: everything staged, the PR opened (if tooling allows), merge + `cz bump` + tag push left as a documented morning action. Builds on `cdwilson/v0.2.0-m4-docs` (HEAD `661649a`, 992 tests, CI green).

**Known environment issue:** the `gh` CLI began failing with authorization timeouts around 02:30 (likely locked macOS keychain). Pure-git pushes may still work. Any step needing `gh` must degrade gracefully: attempt once; on auth failure, write the exact command into the runbook instead of retry-looping.

## Global Constraints

- Conventional commits + `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>` trailer; hook lore as previous milestones.
- NEVER: merge to main, push any tag, run `cz bump` for real (dry-run only), publish anything.
- Never file issues upstream.

---

### Task 1: M4-review cleanups + changelog

**Files:** `pyproject.toml` (comment fix), `README.md` (docs link), `CHANGELOG.md` (0.2.0 entry), stray `.tmp` deletion.

- [ ] **Step 1:** `git checkout cdwilson/v0.2.0-m4-docs && git checkout -b cdwilson/v0.2.0-m5-release && uv run poe test` (992 expected). `rm -f src/tinydantic/_document_old.py.tmp`.
- [ ] **Step 2:** In `pyproject.toml`, find the comment on the `properdocs` line in the docs dependency group claiming properdocs "aliases mkdocs imports at runtime" — replace with the accurate statement: `# properdocs is the docs build engine (poe docs-build); the transitive mkdocs package remains installed (mkdocs-material dependency) and is what mike uses for versioned deploys.` (adjust wording to fit TOML comment style/line length).
- [ ] **Step 3:** In `README.md`, add a Documentation link near the top (after the badges/intro, matching README voice): a sentence pointing to <https://tinydantic.dev>. Also add `Documentation` to the Table of Contents only if you add a section heading — a one-liner in the intro needs no TOC change.
- [ ] **Step 4:** `CHANGELOG.md` — add a `## [0.2.0] - <today's date>` section under `[Unreleased]`, Keep-a-Changelog style with `### Changed` (breaking), `### Added`, `### Fixed` subsections. Content (from the M4 final review's raw material — rewrite as user-facing bullets, breaking items marked **BREAKING**):
  - BREAKING: `Document` → `TinydanticModel` with class-kwargs config (`database=`, `table_name=`) and `bind()`.
  - BREAKING: `id` now included in `model_dump()`; stored documents are JSON-mode serialized; `save()` on a new instance inserts.
  - BREAKING: `get()` selector params renamed `doc_id`/`doc_ids` (keyword-only), >1 selector raises `ValueError`, `get(doc_ids=...)` returns `list[Self]` skipping missing ids.
  - BREAKING: minimum Python 3.11 (was 3.8); PyPy support claim dropped.
  - BREAKING: `DocumentIDRequiredError` no longer subclasses `ValueError` (error hierarchy now rooted at `TinydanticError`).
  - Added: full Table API (`search`, `contains`, `update`, `update_multiple`, `upsert`, `remove`), `delete()`, `get_by_cond`/`get_by_id`/`get_by_ids`, `q()` helper, error classes exported at package root, `py.typed` marker.
  - Fixed: `save()` crash on unsaved instances; `replace()` leaking `KeyError` on missing documents; datetime/UUID/nested models now round-trip through storage.
  - Changed (tooling): hatch → uv + poethepoet + uv_build (static versioning via commitizen); docs engine → ProperDocs; docs site gains eight usage pages.
  - Update the link definitions at the bottom: `[unreleased]: .../compare/v0.2.0...HEAD` and `[0.2.0]: .../compare/v0.1.19...v0.2.0`.
- [ ] **Step 5:** Gate (`uv run poe test`, `poe spell-check`, `poe pre-commit`) then commit `docs: prepare v0.2.0 changelog and release cleanups` + trailer.

---

### Task 2: Release readiness verification + runbook + push

**Files:** Create `docs/superpowers/plans/2026-07-06-v0.2.0-release-runbook.md`.

- [ ] **Step 1: Deploy-path de-risk (M4 review Important):** build the site with the ENGINE MIKE USES: `uv run mkdocs build --config-file mkdocs.yaml --clean --strict` (real mkdocs, not properdocs). Must exit 0. Record versions (`uv run pip show mkdocs properdocs | grep -E "Name|Version"`).
- [ ] **Step 2: Version plumbing dry-run:** `uv run cz bump --dry-run` — expected output includes `tag to create: v0.2.0` and the bump `0.1.19 → 0.2.0` (a MINOR bump: `major_version_zero = true` maps breaking changes to minor). Record exact output. Verify `uv version --short` still prints `0.1.19` afterward (dry-run must not modify).
- [ ] **Step 3: Full local gate:** `uv run poe check && uv run poe test-cov && uv run poe docs-build-check && uv build && rm -rf dist`.
- [ ] **Step 4: Write the runbook** `docs/superpowers/plans/2026-07-06-v0.2.0-release-runbook.md` — the exact morning sequence for Chris:

```text
# v0.2.0 Release Runbook

Pre-verified on 2026-07-06 (see .superpowers/sdd/progress.md). Every
step below is copy-paste; nothing else is required.

## 1. Open + merge the PR

    gh pr create --base main --head cdwilson/v0.2.0-m5-release \
      --title "tinydantic v0.2.0: TinydanticModel, complete Table API, uv toolchain" \
      --fill-verbose

Review it, wait for PR CI (14 jobs), then merge. Use a MERGE COMMIT,
not squash: cz bump reads conventional commits, and squashing loses
the feat!/fix granularity (version math still lands on 0.2.0 if the
squash subject is a feat!, but the merge commit is cleaner).

## 2. Confirm the docs-dev deploy on main

    gh run watch $(gh run list --workflow docs-dev.yaml --limit 1 \
      --json databaseId -q '.[0].databaseId') --exit-status

(It runs mike with the real mkdocs engine — pre-verified locally.)

## 3. Cut the release from main

    git checkout main && git pull
    uv run cz bump    # writes version 0.2.0 + creates tag v0.2.0
    git push origin main --follow-tags

## 4. Watch the publish pipeline

The tag triggers: version-guard -> build -> publish-to-pypi (+
TestPyPI, GitHub Release with sigstore artifacts) and docs-release
(mike deploys the v0.2.0 docs alias).

    gh run watch $(gh run list --workflow publish-python-package.yaml \
      --limit 1 --json databaseId -q '.[0].databaseId') --exit-status

## 5. Post-release sanity

    pip install tinydantic==0.2.0   # in a scratch venv

Check https://tinydantic.dev shows the new usage pages.

## Notes

- The publish version-guard has never fired before (first tagged
  release on the new pipeline) — step 4's watch is where it proves
  out. If it fails, the tag/pyproject mismatch message says exactly
  what's wrong; nothing publishes on failure.
- gh CLI was hitting keychain auth timeouts overnight; if it still
  does, re-auth with `gh auth login` or use the GitHub UI for 1-2.
```

(Write the runbook file with this exact content, minus this parenthetical. The `text` fence above is only to keep repo formatters from reflowing the plan; the runbook file itself is plain markdown — prettier will format it on commit, which is fine there because the commands live in indented code blocks.)

- [ ] **Step 5:** Commit `docs: add v0.2.0 release runbook` + trailer. Push: `git push -u origin cdwilson/v0.2.0-m5-release`. Attempt CI dispatch ONCE via `gh workflow run ci.yaml --ref cdwilson/v0.2.0-m5-release`; on gh auth failure, note it — the PR CI in the runbook covers verification.
- [ ] **Step 6:** Attempt `gh pr create` ONCE (exact command from the runbook, `--draft`). On auth failure: skip — the runbook step 1 covers it.
