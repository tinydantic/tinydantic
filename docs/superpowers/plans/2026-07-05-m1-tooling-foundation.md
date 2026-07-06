# Milestone 1: Tooling Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate tinydantic from hatch to uv + uv_build + poethepoet, update all dependencies, and raise the Python floor to 3.11 — with the existing prototype code passing tests throughout.

**Architecture:** This is milestone 1 of 5 from the approved spec `docs/superpowers/specs/2026-07-05-tinydantic-v0.2-design.md` (read its §8 before starting). No library code changes in this milestone — only `pyproject.toml`, configs, CI workflows, and contributor docs. Version source of truth moves from git tags (hatch-vcs) to a static `version` in `pyproject.toml` (bumped by commitizen at release time).

**Tech Stack:** uv (project manager + lockfile), uv_build (PEP 517 backend), poethepoet (task runner), commitizen (`pep621` version provider), pytest, ruff, mypy, pre-commit, GitHub Actions.

## Global Constraints

- Python floor: `requires-python = ">=3.11"`; CI matrix CPython 3.11, 3.12, 3.13, 3.14.
- Windows, macOS, and Linux are all first-class: no Makefiles, no shell-isms in poe tasks, CI tests all three OSes.
- Dependency floors: `pydantic[email]>=2.11`, `tinydb>=4.8`. Drop `eval_type_backport` and `typing-extensions` from runtime deps.
- Conventional commits (a commit-msg hook enforces this). All commits end with the Claude co-author trailer.
- Pre-commit hooks run on every commit and may reformat files (prettier, taplo) or fail on unknown words (cspell) or unlicensed files (reuse). If a commit fails because hooks modified files: `git add -u` and retry. If cspell flags a legitimate new word: append it to `project-words.txt`, then `sort --ignore-case -u project-words.txt -o project-words.txt`, stage, retry.
- Never file issues on external repositories.
- The existing test suite must pass after every task. Static version stays `0.1.19` (the latest release) until milestone 5's `cz bump`.

---

### Task 1: Branch and baseline

**Files:**

- Delete: `src/tinydantic/_document_old.py.tmp` (untracked leftover)

**Interfaces:**

- Produces: branch `cdwilson/v0.2.0-m1-tooling` where all milestone-1 work happens; a recorded baseline proving tests pass before any changes.

- [ ] **Step 1: Create the branch**

```bash
git checkout cdwilson/initial-prototype-and-docs
git checkout -b cdwilson/v0.2.0-m1-tooling
rm -f src/tinydantic/_document_old.py.tmp
```

- [ ] **Step 2: Record the baseline — tests pass with the OLD (hatch-era) pyproject**

Run: `uv run --extra test pytest` Expected: PASS (all tests; suite includes doctests from README/docs per `[tool.pytest.ini_options]`). If this fails, STOP — the baseline is broken and the problem is not yours to fix silently; report it.

---

### Task 2: Rewrite pyproject.toml (uv_build, dependency-groups, static version)

**Files:**

- Modify: `pyproject.toml` (full rewrite, content below)
- Create: `uv.lock` (generated)

**Interfaces:**

- Produces: dependency groups `test`, `types`, `docs`, `lint`, `dev` (used by every later task and by CI); static `version = "0.1.19"`; `uv_build` backend. Task 3 adds `[tool.poe.tasks]` to this file.

- [ ] **Step 1: Replace pyproject.toml with the following content**

```toml
# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

#:schema https://json.schemastore.org/pyproject.json

[build-system]
build-backend = "uv_build"
requires = [
  "uv_build>=0.11,<0.12",
]

[project]
authors = [
  { name = "Chris Wilson", email = "christopher.david.wilson@gmail.com" },
]
# https://pypi.org/classifiers/
classifiers = [
  "Development Status :: 3 - Alpha",
  "Framework :: Pydantic :: 2",
  "Intended Audience :: Developers",
  "Operating System :: OS Independent",
  "Programming Language :: Python :: 3",
  "Programming Language :: Python :: 3.11",
  "Programming Language :: Python :: 3.12",
  "Programming Language :: Python :: 3.13",
  "Programming Language :: Python :: 3.14",
  "Programming Language :: Python :: Implementation :: CPython",
  "Programming Language :: Python",
  "Topic :: Database",
  "Topic :: Software Development :: Libraries",
  "Typing :: Typed",
]
dependencies = [
  "PyYAML>=6.0",
  "pydantic[email]>=2.11",
  "tinydb>=4.8",
]
description = "A Pydantic-powered ODM (object-document mapper) for TinyDB"
keywords = [
  "odm",
  "pydantic",
  "tinydb",
]
license = "Apache-2.0 OR MIT"
license-files = [
  "LICENSES/*",
]
name = "tinydantic"
readme = "README.md"
requires-python = ">=3.11"
version = "0.1.19"

[project.urls]
Changelog = "https://github.com/tinydantic/tinydantic/blob/main/CHANGELOG.md"
Documentation = "https://tinydantic.dev"
Issues = "https://github.com/tinydantic/tinydantic/issues"
Source = "https://github.com/tinydantic/tinydantic"

[dependency-groups]
dev = [
  { include-group = "docs" },
  { include-group = "lint" },
  { include-group = "test" },
  { include-group = "types" },
  "check-jsonschema",
  "commitizen",
  "editorconfig-checker",
  "interrogate",
  "jsonschema[format]",
  "poethepoet",
  "pre-commit",
  "pre-commit-ci-config",
  "pyclean",
  "reuse>=5.0.0",
]
docs = [
  # black is used by separate_signature option in mkdocstrings-python
  "black",
  "poethepoet",
  "griffe",
  "linkchecker",
  "markdown-callouts",
  "markdown-gfm-admonition",
  "mdx_truly_sane_lists",
  "mike",
  "mkdocs-awesome-pages-plugin",
  "mkdocs-gen-files",
  "mkdocs-github-admonitions-plugin",
  "mkdocs-include-markdown-plugin",
  "mkdocs-material",
  "mkdocstrings",
  "mkdocstrings-python",
]
lint = [
  "poethepoet",
  "ruff>=0.14",
]
test = [
  "packaging",
  "poethepoet",
  "pytest>=8",
  "pytest-cov",
  "pytest-randomly",
  "pytest-rerunfailures",
  "pytest-xdist",
]
types = [
  "mypy>=1.14",
  "packaging",
  "types-PyYAML",
]

[tool.coverage.run]
branch = true
parallel = true
source_pkgs = [
  "tests",
  "tinydantic",
]

[tool.coverage.paths]
tests = [
  "*/tinydantic/tests",
  "tests",
]
tinydantic = [
  "*/tinydantic/src/tinydantic",
  "src/tinydantic",
]

[tool.coverage.report]
exclude_lines = [
  "if TYPE_CHECKING:",
  "if __name__ == .__main__.:",
  "no cov",
]

[tool.commitizen]
major_version_zero = true
name = "cz_conventional_commits"
tag_format = "v$version"
version_provider = "pep621"
version_scheme = "semver2"

[tool.interrogate]
fail-under = 100
ignore-private = true
ignore-regex = [
  "DocumentMeta",
]
ignore-semiprivate = true
omit-covered-files = true
style = "google"
verbose = 2

[tool.pytest.ini_options]
addopts = "--doctest-modules --doctest-glob '*.md'"
doctest_optionflags = "NORMALIZE_WHITESPACE IGNORE_EXCEPTION_DETAIL"
minversion = "6.0"
testpaths = [
  "CONTRIBUTING.md",
  "README.md",
  "docs",
  "src",
  "tests",
]
```

Notes on deliberate changes vs the old file (do not "fix" these):

- `license` is now a PEP 639 SPDX expression with `license-files` globs (this resolves the old TODO comment; the two `License :: OSI Approved ::` classifiers are removed because PEP 639 forbids combining them with the `license` expression field).
- All `[tool.hatch.*]` sections are gone. `dynamic = ["version"]` is gone. `semver` and `coverage` deps are gone (commitizen and pytest-cov replace them).
- `[project.optional-dependencies]` is gone — dev tooling moved to PEP 735 `[dependency-groups]`, which are not published metadata.

- [ ] **Step 2: Generate the lockfile and sync**

Run: `uv lock && uv sync --all-groups` Expected: lockfile created; resolution succeeds with pydantic ≥2.13 and tinydb ≥4.8.2. If resolution fails on a docs plugin (these are old), relax that one plugin's floor rather than pinning pydantic/tinydb lower, and note it in the commit message.

- [ ] **Step 3: Verify tests pass under the new metadata**

Run: `uv run pytest` Expected: PASS — same result as the Task 1 baseline.

- [ ] **Step 4: Verify the build backend and version plumbing**

```bash
uv build
uv version --short
```

Expected: `dist/tinydantic-0.1.19.tar.gz` and `dist/tinydantic-0.1.19-py3-none-any.whl` are produced without hatchling; `uv version --short` prints `0.1.19`. Then delete the artifacts: `rm -rf dist`.

- [ ] **Step 5: Verify commitizen reads the pep621 version**

Run: `uv run cz version --project` Expected: `0.1.19`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: migrate to uv_build backend with PEP 735 dependency groups

Replaces hatch/hatchling/hatch-vcs. Version source of truth moves from
git tags to [project].version, bumped by commitizen (pep621 provider).
Python floor raised to 3.11; pydantic>=2.11, tinydb>=4.8.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: poethepoet tasks replacing hatch scripts

**Files:**

- Modify: `pyproject.toml` (append `[tool.poe.tasks]` sections below the `[tool.commitizen]` section)

**Interfaces:**

- Produces: poe tasks `fmt`, `lint`, `test`, `test-cov`, `types`, `spell-check`, `sbom`, `sbom-check`, `check`, `clean`, `docs-build`, `docs-build-check`, `docs-serve`, `docs-check`, `docs-ci-publish`, `pre-commit`. CI (Task 5) and CONTRIBUTING (Task 6) invoke these exact names via `uv run poe <task>`.

- [ ] **Step 1: Append the poe configuration to pyproject.toml**

```toml
[tool.poe.tasks]
clean = "pyclean . --debris --verbose"
fmt = ["_ruff-fix", "_ruff-format"]
lint = ["_ruff-check", "_ruff-format-check"]
pre-commit = "pre-commit run --all-files --verbose"
sbom = "reuse spdx -o reuse.spdx"
sbom-check = "reuse lint"
spell-check = "npx cspell --gitignore --dot ."
test = "pytest"
test-cov = "pytest --cov --cov-branch"
types = "mypy --install-types --non-interactive src/tinydantic tests"
update-project-words = { shell = "npx cspell --gitignore --dot --words-only --unique . | sort --ignore-case >> project-words.txt" }

_ruff-check = "ruff check ."
_ruff-fix = "ruff check --fix ."
_ruff-format = "ruff format ."
_ruff-format-check = "ruff format --check ."

check = ["lint", "types", "sbom-check", "spell-check"]

[tool.poe.tasks.docs-build]
cmd = "mkdocs build --config-file mkdocs.yaml --clean --strict"
env = { PYTHONUNBUFFERED = "1", SOURCE_DATE_EPOCH = "1580601600" }

[tool.poe.tasks.docs-build-check]
sequence = [
  { ref = "docs-build --no-directory-urls" },
  { ref = "docs-check" },
]

[tool.poe.tasks.docs-check]
cmd = "linkchecker --config .linkcheckerrc site"

[tool.poe.tasks.docs-ci-publish]
cmd = "mike deploy --config-file mkdocs.yaml --update-aliases --push"
env = { PYTHONUNBUFFERED = "1", SOURCE_DATE_EPOCH = "1580601600" }

[tool.poe.tasks.docs-serve]
cmd = "mkdocs serve --config-file mkdocs.yaml --dev-addr localhost:8000"
env = { PYTHONUNBUFFERED = "1" }
```

Note: `update-project-words` uses `shell =` (it needs a pipe); it is a maintainer convenience, not used in CI, so the POSIX-shell requirement is acceptable there. Every other task is `cmd`/`sequence` and shell-free per the cross-platform constraint.

- [ ] **Step 2: Verify the critical tasks run**

```bash
uv run poe test
uv run poe lint
uv run poe sbom-check
uv run poe docs-build
```

Expected: `test` PASSES; `lint` may FAIL (Task 4 fixes lint/typing config fallout — a lint failure here is acceptable, note it and continue); `sbom-check` passes ("Congratulations! Your project is compliant..."); `docs-build` builds `site/` without errors (mkdocs is still the engine in this milestone; ProperDocs comes in milestone 4).

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "build: add poethepoet tasks replacing hatch scripts

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Point linters/type-checker at Python 3.11

**Files:**

- Modify: `ruff.toml` (add `target-version` near the top, after `line-length`)
- Modify: `pyproject.toml` (add `[tool.mypy]` section)

**Interfaces:**

- Produces: `uv run poe lint` and `uv run poe types` both green — the gate every later milestone relies on.

- [ ] **Step 1: Add target-version to ruff.toml**

Immediately after the `line-length = 79` line, add:

```toml
target-version = "py311"
```

- [ ] **Step 2: Add mypy config to pyproject.toml** (after `[tool.interrogate]`)

```toml
[tool.mypy]
python_version = "3.11"
```

- [ ] **Step 3: Run lint with autofix, then verify**

```bash
uv run poe fmt
uv run poe lint
```

Expected: `fmt` may apply pyupgrade-style fixes to `src/` and `tests/` (e.g. `Iterable`/`Mapping` imports moving to `collections.abc`). `lint` then PASSES. If a rule fires that cannot be autofixed and is not a genuine defect, do NOT add file-level ignores; fix the code minimally. The prototype code is known-clean under ruff `select = ["ALL"]` with the existing ignore list.

- [ ] **Step 4: Run the type check**

Run: `uv run poe types` Expected: PASS ("Success: no issues found"). Known acceptable outcome: with pydantic ≥2.11, the private-API import in `src/tinydantic/_document.py` (`pydantic._internal._model_construction`) may produce a new error; if so, append `# type: ignore[attr-defined]` to that import line only — milestone 2 deletes this file.

- [ ] **Step 5: Verify tests still pass, then commit**

Run: `uv run poe test` Expected: PASS

```bash
git add -u
git commit -m "chore: target Python 3.11 in ruff and mypy

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Update GitHub Actions workflows

**Files:**

- Modify: `.github/workflows/ci.yaml` (replace the `test` job)
- Modify: `.github/workflows/docs-dev.yaml` and `.github/workflows/docs-release.yaml` (replace hatch steps)
- Modify: `.github/workflows/publish-python-package.yaml` (add version-guard job)

**Interfaces:**

- Consumes: poe task names from Task 3; dependency groups from Task 2.
- Produces: CI green on the matrix {3.11–3.14} × {ubuntu, windows, macos}.

- [ ] **Step 1: In `ci.yaml`, replace the entire `test:` job with:**

```yaml
test:
  name: >-
    Python ${{ matrix.python-version }} on ${{ startsWith(matrix.os, 'macos-') && 'macOS' || startsWith(matrix.os, 'windows-') && 'Windows' || 'Linux' }}
  runs-on: ${{ matrix.os }}
  strategy:
    fail-fast: false
    matrix:
      os:
        - ubuntu-latest
        - windows-latest
        - macos-latest
      python-version:
        - "3.11"
        - "3.12"
        - "3.13"
        - "3.14"
  steps:
    - uses: actions/checkout@v4
    - name: Install uv
      uses: astral-sh/setup-uv@v6
      with:
        enable-cache: true
        python-version: ${{ matrix.python-version }}
    - name: Run static analysis
      run: uv run --group lint poe lint
    - name: Run tests
      run: >-
        uv run --group test poe test --cov --cov-branch -p no:cacheprovider --numprocesses auto --reruns 2 --reruns-delay 1
```

Also REMOVE the now-unneeded `fetch-depth: 0` lines from this workflow (they existed for hatch-vcs version derivation). The `online-checks` and `required-checks-pass` jobs stay unchanged. (`poe` resolves inside `uv run --group lint` / `--group test` because Task 2's pyproject includes `poethepoet` in those groups.)

- [ ] **Step 2: In `docs-dev.yaml`, replace the Python/hatch setup and build steps.**

Delete the `Set up Python` (3.8 pin), `Install UV` (curl), `Install Hatch`, `Display full version`, `Build documentation`, and `Commit documentation` steps; in their place:

```yaml
- name: Install uv
  uses: astral-sh/setup-uv@v6
  with:
    enable-cache: true
    python-version: "3.12"
- name: Build documentation
  run: uv run --group docs poe docs-build-check
- name: Commit documentation
  run: uv run --group docs poe docs-ci-publish dev
```

(`fetch-depth: 0` STAYS in the docs workflows — mike needs full history for the gh-pages branch.) In `docs-release.yaml`, apply the same replacement: delete its `Set up Python` (3.8 pin), `Install UV`, `Install Hatch`, and `Display full version` steps; add the same `astral-sh/setup-uv@v6` step (python-version "3.12"); change `Build documentation` to `run: uv run --group docs poe docs-build-check`; and change `Commit documentation` to `run: uv run --group docs poe docs-ci-publish "$DOC_VERSION" latest` (its `Get doc version` step and everything else stays).

- [ ] **Step 3: In `publish-python-package.yaml`, add a version-guard job before `build`:**

```yaml
version-guard:
  name: Verify tag matches pyproject version
  if: startsWith(github.ref, 'refs/tags/')
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Install uv
      uses: astral-sh/setup-uv@v6
    - name: Check tag == v$(uv version --short)
      run: |
        PYPROJECT_VERSION="v$(uv version --short)"
        if [ "$PYPROJECT_VERSION" != "${GITHUB_REF_NAME}" ]; then
          echo "Tag ${GITHUB_REF_NAME} != pyproject version ${PYPROJECT_VERSION}" >&2
          exit 1
        fi
```

Make `build` depend on it only for tag pushes by adding to the `build` job: nothing (build has no `needs` today and TestPyPI publishes from main without tags) — instead add `version-guard` to the `needs:` list of `publish-to-pypi` only. Also remove `fetch-depth: 0` from the `build` job's checkout (hatch-vcs is gone).

- [ ] **Step 4: Validate the workflow files**

Run: `uvx check-jsonschema --builtin-schema vendor.github-workflows .github/workflows/*.yaml` Expected: `ok -- validation done` for all four files.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows pyproject.toml uv.lock
git commit -m "ci: run workflows with uv and poe on Python 3.11-3.14

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

(If pyproject changed in Step 1/2, run `uv lock` first so the lockfile stays in sync.)

---

### Task 6: Update contributor docs

**Files:**

- Modify: `CONTRIBUTING.md`

**Interfaces:**

- Consumes: poe task names from Task 3.

- [ ] **Step 1: Rewrite the hatch-centric sections of CONTRIBUTING.md**

Read the file first. Then:

- The "Hatch" section (installing hatch, `hatch --version`, `hatch shell`): replace with a "uv" section — installing uv per <https://docs.astral.sh/uv/getting-started/installation/>, then `uv sync --all-groups` to create `.venv` with all dev dependencies.
- Replace command references throughout, preserving the surrounding prose structure:
  - `hatch run pre-commit:run` → `uv run poe pre-commit`
  - `hatch test --cover` → `uv run poe test-cov`
  - `hatch test --all --cover` → `uv run poe test-cov` with a note that the full version matrix runs in CI
  - `hatch run check` → `uv run poe check`
  - `hatch run doc:serve` → `uv run poe docs-serve`
  - `hatch run doc:build-check` → `uv run poe docs-build-check`
- Remove footnotes that explain hatch concepts (environments, `hatch shell` behavior). Keep the pre-commit and conventional-commit guidance intact.

CAUTION: `CONTRIBUTING.md` is in pytest's `testpaths` and is doctested — any ` ```pycon ` blocks you touch must remain valid doctests. The command examples are in plain ` ```sh ` blocks, which pytest ignores.

- [ ] **Step 2: Verify doctests and spelling still pass**

```bash
uv run poe test
uv run poe spell-check
```

Expected: both PASS (add any new legitimate words like `poethepoet` to `project-words.txt` per the global constraint).

- [ ] **Step 3: Commit**

```bash
git add CONTRIBUTING.md project-words.txt
git commit -m "docs: update contributing guide for uv and poe workflow

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Full verification gate

**Files:** none (verification only)

- [ ] **Step 1: Run everything locally**

```bash
uv run poe check
uv run poe test-cov
uv run poe pre-commit
uv build && rm -rf dist
```

Expected: all PASS. `poe check` = lint + types + sbom-check + spell-check.

- [ ] **Step 2: Push and watch CI**

```bash
git push -u origin cdwilson/v0.2.0-m1-tooling
gh run watch --exit-status
```

Expected: all jobs green, including the 12-cell test matrix. If a matrix cell fails on an OS/version combination, that is a real milestone deliverable failure — debug it (superpowers:systematic-debugging), do not shrink the matrix.

- [ ] **Step 3: Report**

Milestone 1 done. Do NOT merge; milestone 2 (core port) builds on this branch. The milestone-2 plan is authored at this boundary against the repo's actual state.
