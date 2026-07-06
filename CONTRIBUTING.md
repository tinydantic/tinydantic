# Contributing

Thanks for your interest in contributing to `tinydantic`!

If you want to see how this project compares to [recommended community standards](https://opensource.guide/), you can check out the `tinydantic` [Community Standards](https://github.com/tinydantic/tinydantic/community) page.

<!-- toc-start -->

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [I have a question](#i-have-a-question)
- [I found a bug](#i-found-a-bug)
- [I want to contribute](#i-want-to-contribute)
  - [Development Guide](#development-guide)

<!-- toc-end -->

## Code of Conduct

This project and everyone participating in it is governed by the [tinydantic Code of Conduct](./CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code. Please report unacceptable behavior [directly on GitHub](https://docs.github.com/en/communities/maintaining-your-safety-on-github/reporting-abuse-or-spam) so that the issue can be [managed and resolved on the platform](https://docs.github.com/en/communities/moderating-comments-and-conversations/managing-reported-content-in-your-organizations-repository). Please also feel free to reach out directly at <christopher.david.wilson@gmail.com>.

## I have a question

If you have a question about how to _use_ `tinydantic`, first check out the [documentation](https://tinydantic.dev).

If you still need help, feel free to [start a discussion](https://github.com/tinydantic/tinydantic/discussions/new/choose)!

## I found a bug

We use GitHub issues to track bugs and other issues. If you run into an issue with the project, start by searching for existing [Issues](https://github.com/tinydantic/tinydantic/issues) and [Discussions](https://github.com/tinydantic/tinydantic/discussions) to see if the bug has already been reported by someone else.

If the issue has not already been reported, open a [new issue](https://github.com/tinydantic/tinydantic/issues/new).

> [!IMPORTANT]
>
> If you think you have identified a security issue with a tinydantic project, **do not open a public issue!**
>
> See the [Security Policy](https://github.com/tinydantic/tinydantic/security) for instructions on how to responsibly report your findings.

## I want to contribute

You can contribute to `tinydantic` by submitting a [pull request](https://docs.github.com/en/github/collaborating-with-issues-and-pull-requests/about-pull-requests) to:

1. Fix a bug
2. Add a new feature
3. Improve the documentation

> [!IMPORTANT]
>
> When contributing to this project, you must agree that you have authored 100% of the content, that you have the necessary rights to the content, and that the content you contribute may be provided under the project license.

If you are new to the project, check out <https://github.com/tinydantic/tinydantic/contribute> for a list of good first issues.

> [!TIP]
>
> Before submitting a larger pull request (e.g. new features or breaking changes), consider creating an [issue](https://github.com/tinydantic/tinydantic/issues/new) to outline your proposed changes.

The next section describes how to set up a development environment and create a pull request to submit your changes for review.

<!-- development-guide-start -->

## Development Guide

### Prerequisites

#### Python

This project is written in [Python](https://www.python.org/) and requires a Python interpreter to be installed for development.

=== "Install with uv"

    We recommend using [uv](https://docs.astral.sh/uv/) to install and manage Python versions on your development system. uv is also used for the rest of the project's development workflow (see the [uv](#uv) section below).

    First, follow the [Installing uv](https://docs.astral.sh/uv/getting-started/installation/) documentation and make sure that the `uv` command is available in your shell.

    ```sh
    uv --version
    ```

    Next, use uv to install Python 3.11 or later. We'll install the latest version of Python provided by uv (currently `3.13` at the time of writing).

    ```sh
    uv python install 3.13
    ```

    NOTE: As long as you have Python 3.11 or later installed, you should be able to follow the remainder of this guide.

=== "Install without uv"

    The simplest way to install Python is to [download an official installer](https://www.python.org/downloads/). Check out [this article](https://realpython.com/installing-python/#macos-how-to-install-python-using-the-official-installer) for an overview of some alternative installation options.

#### uv

This project uses [uv](https://docs.astral.sh/uv/) for project management. This includes managing the project's dependencies, running project tasks (via [poe](https://poethepoet.natn.io/)), running tests against multiple versions of Python, building the docs, creating new releases, etc.

If you installed Python with uv in the previous section, you already have uv installed. Otherwise, follow the [Installing uv](https://docs.astral.sh/uv/getting-started/installation/) documentation now.

The important thing is that at this point, you should be able to run the `uv` command.

```sh
uv --version
```

### Pull Requests

#### Installation and setup

[Fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) the `tinydantic` repository, clone it, and change directory to the project root.

```sh
git clone git@github.com:<your GitHub username>/tinydantic.git
cd tinydantic
```

Install the project along with all of its development dependencies.

```sh
uv sync --all-groups
```

Behind the scenes, uv creates a Python virtual environment in a `.venv` directory at the project root, installs the `tinydantic` package in [development mode](https://setuptools.pypa.io/en/latest/userguide/development_mode.html) by performing an [editable installation](https://setuptools.pypa.io/en/latest/userguide/development_mode.html), and installs all of the project's dependencies. The `--all-groups` flag ensures that every [dependency group](https://docs.astral.sh/uv/concepts/projects/dependencies/#dependency-groups) is installed (including the `dev` group, which pulls in everything needed for testing, linting, type-checking, and building the docs).

You can run any command inside this environment by prefixing it with [`uv run`](https://docs.astral.sh/uv/reference/cli/#uv-run). For example, you should be able to start the `python` interpreter and import the `tinydantic` package.

```sh
uv run python
```

```pycon
>>> import tinydantic

```

#### Install pre-commit hooks

`tinydantic` uses [pre-commit](https://pre-commit.com/) to automatically run a series of quality checks against your code locally before it is committed to the repository. (The `pre-commit` command was installed into the virtual environment when you ran `uv sync --all-groups` above.)

Install the pre-commit hook scripts into your local git repository.

```sh
uv run pre-commit install
```

When you commit your changes (`git commit ...`), the git hook scripts will run automatically and check for issues in your code.

Normally, pre-commit only checks the files that were modified as part of the commit. A poe task is provided to run `pre-commit` manually on all the files if needed.

```sh
uv run poe pre-commit
```

#### Make your changes

Create a new branch for your changes.

```sh
git checkout -b my-new-feature-branch
```

#### Run tests

While you are making changes in your new branch, you can run the test suite to make sure you didn't break anything.

```sh
uv run poe test
```

You can also run the test suite together with a [Coverage](https://coverage.readthedocs.io/en/latest/index.html) report showing which parts of the code were executed by the tests.

```sh
uv run poe test-cov
```

> [!NOTE]
>
> The `test` and `test-cov` tasks run against the single Python version installed in your `.venv`. The full test matrix — every supported Python version (3.11–3.14) across Linux, macOS, and Windows — runs automatically in CI when you open a pull request, which can catch issues that only show up with a specific version of Python or a specific operating system.

After running `uv run poe test-cov`, you can also generate an interactive HTML coverage report.

```sh
uv run coverage html
```

#### Run formatters and linters

Before committing your changes, you should format your code and run the project's checks. First, format your code and apply autofixes with the [Ruff](https://docs.astral.sh/ruff/) formatter and linter.

```sh
uv run poe fmt
```

Then run the full suite of checks (linting, license/SBOM checks, spell-checking, and type-checking).

```sh
uv run poe check
```

#### Build Documentation

If you have made any changes to the documentation (including changes to function signatures, class definitions, or docstrings that will appear in the API documentation), make sure it builds successfully.

The following command will build and serve the documentation locally on your machine. While the server is running, it will watch for any changes to the documentation files, rebuild the site, and refresh your browser automatically.

```sh
uv run poe docs-serve
```

Before committing your changes, it's good to build and run some validation checks on the built documentation.

```sh
uv run poe docs-build-check
```

#### Commit your changes

When you are done making changes, commit them to your new branch.

`tinydantic` follows the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification to enforce some consistency across commit messages.

```sh
git commit -m "<type>[optional scope]: <description>"
```

This [cheat sheet](https://kapeli.com/cheat_sheets/Conventional_Commits.docset/Contents/Resources/Documents/index) lists the allowed options for the `<type>` field.

Here's an example of a commit message that follows the spec.

```plaintext
fix: correct minor typos in code

See the issue for details on the typos fixed.

Closes issue #12
```

> [!TIP]
>
> The development dependencies automatically install the [Commitizen](https://commitizen-tools.github.io/commitizen/) CLI tool (`cz`) which walks you through creating a conventional commit message via a questionnaire-style interface.
>
> Instead of `git commit ...`, use the `cz` command to commit your changes.
>
> ```sh
> # Make your changes...
> uv run cz commit
> ```

#### Create a PR on GitHub

When your changes are ready for review, push your branch to GitHub and [create a pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request). Link to any relevant issues and include a description of your changes.

Creating a pull request will kick off a series of automated checks that run as part of workflows in GitHub Actions. If any of the checks fail, fix the issues locally in your PR branch, create a new commit (or amend your existing commits), and push the changes to the remote PR branch. GitHub will automatically run the checks again when changes are pushed to the PR branch. Repeat this process until all checks have passed.

### Development Releases

Between releases, the `version` field under `[project]` in `pyproject.toml` holds the latest released version — merges to `main` do not publish anything. Publishing to TestPyPI is currently disabled: with a static version there is no unique development version to upload per merge (the previous behavior relied on the hatch-vcs build plugin deriving one from git). If the uv build backend gains VCS-derived versioning, per-merge TestPyPI publishing may return.

Historical development releases can still be browsed at <https://test.pypi.org/project/tinydantic/>, and can be installed with `pip`.

```sh
pip install -i https://test.pypi.org/simple/ tinydantic
```

You can print the version currently declared in `pyproject.toml` by running the following command in the repository.

```sh
uv version
```

### Release Process

The release process is automated using workflows in GitHub Actions. New releases are created and build artifacts are published automatically when a compliant [SemVer](https://semver.org/) release tag of the form `v<MAJOR>.<MINOR>.<PATCH>` is pushed to GitHub.

Because the `main` branch is protected (no direct pushes), the version bump travels in a pull request like any other change, and the release tag is pushed afterward — git tags are not governed by branch protection.

**Step 1 — changelog.** Update `CHANGELOG.md` with a section for the new release. The changelog is curated by hand; `cz bump` does not generate it.

**Step 2 — bump the version.** On a release branch, let [Commitizen](https://commitizen-tools.github.io/commitizen/) determine the next [SemVer](https://semver.org/)-compliant version from the commit history and write it to `pyproject.toml` without committing or tagging, then refresh the lockfile to match:

```sh
uv run cz bump --files-only
uv lock
```

**Step 3 — merge.** Commit the result (for example `bump: version 0.1.19 → 0.2.0`), push, open a pull request, and merge it once CI passes.

**Step 4 — tag.** Tag the merged commit on `main` and push the tag:

```sh
git fetch origin
git tag -a v<MAJOR>.<MINOR>.<PATCH> -m "Release version <MAJOR>.<MINOR>.<PATCH>" origin/main
git push origin v<MAJOR>.<MINOR>.<PATCH>
```

When the tag is pushed to GitHub, a GitHub Actions workflow verifies that the tag matches the version in `pyproject.toml`, builds and publishes the Python package, creates a release on GitHub, and updates the documentation site.

> [!NOTE] Do not create the GitHub release manually in the web UI — the publish workflow creates it from the tag and will fail if one already exists.

### Editor Setup

TODO: Add VS Code setup instructions

<!-- development-guide-end -->
