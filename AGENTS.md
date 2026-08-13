# AGENTS.md

tinydantic — a Pydantic v2 ODM for TinyDB. `TinydanticModel` subclasses are pydantic models bound to a TinyDB table via class kwargs (`database=`, `table_name=`) — see `src/tinydantic/_model.py`. Design rationale lives in module/method docstrings (start with `src/tinydantic/_config.py`) and the usage docs under `docs/usage/`. TinyDB extensions (storages, middlewares, operations) live in `src/tinydantic/tinydb/`.

## Setup

- `uv sync --all-groups` — installs the venv and every dependency group.
- `npm ci` — installs cspell, markdownlint, and prettier into `node_modules`, where `npx` finds them; spell-check (and therefore `poe check`) fails without it. Prettier is pinned exactly (`--save-exact`) to the version its [pre-commit hook](https://github.com/rbubley/mirrors-prettier) uses — if that hook's `rev` moves, move `package.json` with it, or `npx prettier` and the hook will disagree about formatting.
- `uv run pre-commit install` — installs the pre-commit and commit-msg hooks.

## Conventions

- Conventional commits (commit-msg hook enforces).
- uv + poethepoet: `uv run poe test | lint | types | check | docs-build`. Also `fmt` (ruff autofix + format) and `pre-commit` (all hooks, all files). `check` is lint + sbom-check + spell-check + types — it does **not** run tests, so `poe test` is a separate call before claiming a change is green.
- Windows/macOS/Linux are all first-class; no shell-isms in poe tasks.
- Python 3.10 is the floor (`requires-python`; mypy and ruff target py310) — no syntax newer than 3.10.
- Ruff runs with `select = ALL`: 79-char code lines, Google-style docstrings wrapped at 72 chars (W505 `max-doc-length`), relative imports banned.
- Tests include doctests in README, CONTRIBUTING, and docs — a lying example fails CI.
- Tests run shuffled (pytest-randomly, on by default) — don't write order-dependent tests. CI adds `--numprocesses auto` (pytest-xdist) and `--reruns 2`; local `poe test` is serial and single-version, so a test that depends on process-local state or on a newer Python can pass locally and fail in CI.
- **Run `poe test-matrix` before pushing a PR.** It runs the suite under every supported Python (3.10–3.14) and combines coverage, which is what CI does across 15 job combinations — catching a version-specific break locally is far cheaper than a red PR. `poe test` alone only proves the interpreter you happen to be on.
- Markdown: prettier enforces `proseWrap: never` (don't hard-wrap prose); markdownlint requires an H1 on line 1.
- REUSE licensing: new code files need SPDX headers; `**.md` and listed files are covered by `REUSE.toml` aggregates.
- cspell gates commits: new legit words go in `project-words.txt`, which must stay globally case-insensitive sorted. `poe update-project-words` helps, but it _appends_ a sorted batch to the end rather than merging — re-sort the whole file afterwards, and read what it added. Only words that appear in checked-in files belong there — cspell skips `untracked/`, so never add a word for scratch or agent collateral.
- interrogate demands 100% docstring coverage.
- `untracked/` (repo root) is git-ignored scratch space for drafts, notes, and review collateral; linters and formatters are configured to skip it. Never put anything there that the repo should keep.
- Agent-workflow collateral (superpowers specs and plans, review reports, scratch analysis) is NEVER committed — it lives in `untracked/` only. Superpowers specs go in `untracked/superpowers/specs/`, plans in `untracked/superpowers/plans/`. Committing them drags their vocabulary into `project-words.txt`, which is meant to cover the shipped repo. If a decision in a spec matters to the project, restate it where the project keeps decisions: a module or method docstring, `docs/contributing/`, or the changelog.
- Prefer the public API of every upstream dependency (TinyDB, pydantic). Internal/private APIs (underscore-prefixed, or in a private module) may be used ONLY when the needed behavior is impossible through the public API, and only when explicitly called out and approved during planning/review.
- **Upstream friction always produces two artifacts, not one.** Whenever friction is found, worked around, or resolved — and whenever a private API is used — do _both_ of these in the same change:
  1. **File a tracking issue** in this repo with the `upstream` label (see [Upstream dependencies](#upstream-dependencies)). This is required, not optional, and it is required even when the decision is to live with the workaround indefinitely. Whether anything is ever filed with the upstream project is a separate, later, maintainer-only call — but the friction is tracked here from the moment it is found.
  2. **Record it on `docs/contributing/upstream_limitations.md`** — the limitation, why it matters to an ODM, the workaround we carry, the change that would remove it, and a **link to the tracking issue**. Private-API uses additionally get a row in that project's registry on the same page.

  The page is the durable explanation; the issue is the unit of work. Neither substitutes for the other, and a registry row or limitation section without a linked issue is incomplete.

- Forking or vendoring TinyDB was considered and rejected (2026-07-13) — don't propose it as a fallback.
- Do not store tinydantic config in pydantic's `model_config` (pydantic#9992) — see the `src/tinydantic/_config.py` module docstring.

## Issues and reviews

- [GitHub issues](https://github.com/tinydantic/tinydantic/issues) are the tracker. Review findings, deferred work, and known defects belong there — not in a checked-in or `untracked/` markdown report, which goes stale the moment the code moves and cannot be assigned, linked, or closed.
- Before filing anything, search open **and** closed issues (`gh issue list --state all --search "<terms>"`). A finding already reported — by a human or an agent — gets a comment on that issue, never a duplicate.
- When a review turns up something not already tracked, open an issue for it. Re-verify the finding against the current tree first, and record the evidence in the body: what you ran, at which commit, on what date. A finding that no longer reproduces is not filed.
- Every issue carries a type label (`bug`, `enhancement`, `documentation`) plus a topic label where one fits (`performance`, `api-design`, `polish`). Priority, size, and status live on the [project board](https://github.com/orgs/tinydantic/projects/1), not in labels. Milestones name the release the work is intended for.
- A PR that addresses an issue must link it with a closing keyword (`Closes #123`, `Fixes #123`) in the PR body, so merging the PR closes the issue.
- **Any issue an agent helped write or investigate carries the `ai-assisted` label and an `Assisted-by:` trailer**, following the [kernel's convention](https://docs.kernel.org/process/coding-assistants.html). Last line of the body, own paragraph:

  ```text
  Assisted-by: AGENT_NAME:MODEL_VERSION [TOOL1] [TOOL2]
  ```

  `AGENT_NAME` is the agent or harness (`Claude`, `Codex`), `MODEL_VERSION` the model that did the work. The bracketed tools are optional and space-separated — the brackets mark optionality, they are not typed. List only named analysis tools that produced evidence in the body (`pytest`, `mypy`, `ruff`, `pyright`); an ad-hoc repro script is not a tool, so most issues carry none. Drop any bracketed context-window or deployment suffix from the model id, since literal brackets would read as the tool syntax — `Claude:claude-opus-5`, not `Claude:claude-opus-5[1m]`.

- The same `Assisted-by:` trailer goes on **commits** an agent wrote — last line of the message body, same format. Agents **MUST NOT** add a `Signed-off-by` trailer anywhere: only a human can certify the DCO. `Assisted-by:` records help; it never signs for anyone.
- Say what you could _not_ do. An agent-filed issue states plainly whether the reproduction was actually run, whether a fix was built or tested, and what remains unverified. An unverified report that reads as verified costs a maintainer more than no report.
- Connect issues with GitHub's relationships rather than restating context: `gh issue edit <n> --add-blocking <m>`, `--add-blocked-by`, and `--parent` / `--add-sub-issue` for a genuine parent-child breakdown.

### Upstream dependencies

- **NEVER write to any repository outside `tinydantic/tinydantic`.** No issues, no comments or replies, no edits, no closing or reopening, no reactions, no reviews, no pull requests — not on `msiemens/tinydb`, `pydantic/pydantic`, `mkdocstrings/python`, nor anywhere else. The _only_ exception is an explicit instruction from a tinydantic maintainer to take that specific action at that moment. Approval is never durable and never implied: permission to file an issue is not permission to answer the maintainer's reply, and permission once is not permission again. If you believe an upstream action is warranted, prepare it and ask.
- **Reading upstream is unrestricted** and encouraged — fetch issue threads, PRs, release notes, and source whenever it helps. The prohibition is on writing, not on looking.
- An `upstream`-labelled issue in this repo is a **drafting workspace**: where an agent and a maintainer iterate on the text of an upstream report until it is good enough to send. It is also the one place that context lives, so tinydantic issues held up by the upstream fix point at it with a relationship instead of each repeating the problem.
- The draft carries what filing needs: target repo, affected version, reproduction, expected behavior, and the ready-to-post title and body — plus the patch or draft reply where one applies. Fence the ready-to-post text under a clear "do not post without approval" heading, so no reader mistakes a draft for something already sent.
- **Once it is filed upstream, decide case by case whether the tracking issue still has work to do.** If the draft is spent, close it and re-point the dependent tinydantic issues at the upstream URL directly — one less place to keep current. Keep it open only when something here is still being iterated on: a follow-up reply in progress, a workaround to land, or several tinydantic issues whose shared context lives in it. While it stays open, mirror upstream state into it (filed, answered, merged, closed) — one-directional, and our issue is never written back to upstream.
- **Do not manufacture work for upstream maintainers.** A tinydantic maintainer drives every upstream interaction; an agent's job ends at a draft worth sending. Prefer one well-prepared report over a series of partial ones, and don't propose an upstream issue where a comment on an existing thread would do. This restraint is about what reaches _upstream_ — it is never a reason to skip the tracking issue here, which is required for all friction including friction we have chosen to work around.
- `docs/contributing/upstream_limitations.md` remains the registry of friction tinydantic works _around_ — the reason, the workaround, and the upstream change that would remove it. The tracking issue is where a _filing_ is drafted; link the two while both exist.

## Docs

- Built by properdocs in strict mode — a broken internal link fails `poe docs-build`. Use `poe docs-serve` for live preview; mike handles versioned deploys.
- External links are a separate gate: `poe docs-check` runs linkchecker over the built `site/`, and `poe docs-build-check` chains the build and the check.
- The API reference is generated at build time by `scripts/gen_api_docs.py` (mkdocs-gen-files) — `docs/reference/` is intentionally sparse on disk; don't hand-write pages there.

## CI

- Branch pushes do NOT trigger CI (only pushes to main, tags, and PRs do): `gh workflow run ci.yaml --ref <branch>`.
- Releases (full steps: CONTRIBUTING.md "Release Process"): hand-update `CHANGELOG.md`; on a release branch run `uv run cz bump --files-only` then `uv lock` (writes `[project].version` — no commit, no tag); merge via PR (`main` is protected); then tag `v<version>` on the merged main commit and push the tag.
- The release workflow's version-guard asserts tag == pyproject version, gates PyPI publishing on the package and docs builds, and creates the GitHub release itself — never create one manually in the web UI.
