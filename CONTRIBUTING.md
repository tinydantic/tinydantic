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

=== "Instal with uv"

    We recommend using [uv](https://docs.astral.sh/uv/) to install and manage Python versions on your development system. We'll also use the [`uv tool`](https://docs.astral.sh/uv/concepts/tools/#the-uv-tool-interface) subcommand in the next step to install a helpful tool for managing python projects ([Hatch](#hatch)).[^1]

    First, follow the [Installing uv](https://docs.astral.sh/uv/getting-started/installation/) documentation and make sure that the `uv` command is available in your shell.

    ```sh
    uv --version
    ```

    Next, use uv to install Python 3.10 or later. We'll install the latest version of Python provided by uv (currently `3.12` at the time of writing).

    ```sh
    uv python install 3.12
    ```

    NOTE: While recommended, uv is not *required* for development (we're currently only using it to install `python` and `hatch`). As long as you have Python 3.10 or later installed, you should be able to follow the remainder of this guide.

=== "Install without uv"

    The simplest way to install Python is to [download an official installer](https://www.python.org/downloads/). Check out [this article](https://realpython.com/installing-python/#macos-how-to-install-python-using-the-official-installer) for an overview of some alternative installation options.

#### Hatch

This project currently uses [Hatch](https://hatch.pypa.io/) for project management.[^1] This includes tasks like running tests against multiple versions of Python, building the docs, creating new releases, etc.

=== "Instal with uv"

    If you installed Python via `uv` in the previous section, you can install `hatch` by running the following command. The `--python-preference=only-managed` and `--python=3.12` options instruct uv to install Hatch using the managed Python 3.12 instance we installed in the previous step.

    ```sh
    uv tool install --python-preference=only-managed --python=3.12 hatch
    ```

=== "Install without uv"

    Install `hatch` by following one of the installation methods described in the [Hatch installation guide](https://hatch.pypa.io/latest/install/). We recommend installing `hatch` [via pipx](https://hatch.pypa.io/latest/install/#pipx).

The important thing is that at this point, you should be able to run the `hatch` command.

```sh
hatch --version
```

### Pull Requests

#### Installation and setup

[Fork](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/working-with-forks/fork-a-repo) the `tinydantic` repository, clone it, and change directory to the project root.

```sh
git clone git@github.com:<your GitHub username>/tinydantic.git
cd tinydantic
```

Install the project in [development mode](https://setuptools.pypa.io/en/latest/userguide/development_mode.html) into the default Hatch [Environment](https://hatch.pypa.io/latest/config/environment/overview/), and start a shell in that environment.

```sh
hatch shell
```

Hatch environments provide isolated workspaces for testing, building documentation, etc. Unless an environment is [chosen explicitly](https://hatch.pypa.io/latest/environment/#selection), Hatch will use the `default` environment. Behind the scenes, Hatch creates and activates a Python virtual environment automatically, and installs the `tinydantic` package in “development mode” by performing an [editable installation](https://setuptools.pypa.io/en/latest/userguide/development_mode.html). It will also install all the dependencies required by that environment development into the virtual environment.

At this point, you should be able to start the `python` interpreter and import the `tinydantic` package.

```pycon
>>> import tinydantic

```

#### Install pre-commit hooks

`tinydantic` uses [pre-commit](https://pre-commit.com/) to automatically run a series of quality checks against your code locally before it is committed to the repository. (The `pre-commit` command should have been installed automatically when you ran the `hatch shell` command earlier.)

Install the pre-commit hook scripts.

```sh
pre-commit install
```

When you commit your changes (`git commit ...`), the git hook scripts will run automatically and check for issues in your code.

Normally, pre-commit only checks the files that were modified as part of the commit. A Hatch script is provided to run `pre-commit` manually on all the files if needed.

```sh
hatch run pre-commit:run
```

#### Make your changes

Create a new branch for your changes.

```sh
git checkout -b my-new-feature-branch
```

#### Run tests

While you are making changes in your new branch, you can run the test suite to make sure you didn't break anything. Optionally, `--cover` prints out a [Coverage](https://coverage.readthedocs.io/en/latest/index.html) report showing which parts of the code were executed by the tests.

```sh
hatch test --cover
```

> [!NOTE]
>
> Since no environment is specified, the test command will only run tests in the first defined environment that either already exists or is compatible (in this case, the default environment).
>
> See <https://hatch.pypa.io/latest/tutorials/testing/overview/#single-environment> for more details.

Before submitting a pull request, you can run the test suite against a matrix of all the Python versions supported by `tinydantic`. Hatch will automatically download any versions of Python needed to test each supported version in the matrix. This takes a little bit longer to run, but can catch issues that only show up with a specific version of Python.

```sh
hatch test --all --cover
```

After running the tests with the `--cover` option, you can also generate an interactive HTML coverage report.

```sh
coverage html
```

#### Run formatters and linters

Before committing your changes, you should format and lint your code. The following top-level command runs [`hatch fmt`](https://hatch.pypa.io/latest/cli/reference/#hatch-fmt) (which runs the [Ruff](https://docs.astral.sh/ruff/) formatter and linter), as well as a series of other checks.

```sh
hatch run check
```

#### Build Documentation

If you have made any changes to the documentation (including changes to function signatures, class definitions, or docstrings that will appear in the API documentation), make sure it builds successfully.

The following command will build and serve the documentation locally on your machine. While the server is running, it will watch for any changes to the documentation files, rebuild the site, and refresh your browser automatically.

```sh
hatch run doc:serve
```

Before committing your changes, it's good to build and run some validation checks on the built documentation.

```sh
hatch run doc:build-check
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
> cz commit
> ```

#### Create a PR on GitHub

When your changes are ready for review, push your branch to GitHub and [create a pull request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request). Link to any relevant issues and include a description of your changes.

Creating a pull request will kick off a series of automated checks that run as part of workflows in GitHub Actions. If any of the checks fail, fix the issues locally in your PR branch, create a new commit (or amend your existing commits), and push the changes to the remote PR branch. GitHub will automatically run the checks again when changes are pushed to the PR branch. Repeat this process until all checks have passed.

### Development Releases

Whenever a new commit is merged to the `main` branch on GitHub and all automated checks pass, a development release is automatically created and published to <https://test.pypi.org/project/tinydantic/>.

You can test the development release by installing the package using `pip`.

```sh
pip install -i https://test.pypi.org/simple/ tinydantic
```

You can print the current development version by running the following command in the repository.

```sh
hatch version
```

### Release Process

The release process is entirely automated using workflows in GitHub Actions. New releases are created and build artifacts are published automatically when a compliant [SemVer](https://semver.org/) release tag of the form `v<MAJOR>.<MINOR>.<PATCH>` is pushed to GitHub.

The following command takes a SemVer-compliant version as an argument, creates an annotated tag using the provided version number, and pushes the tag to GitHub.

```sh
hatch run release <MAJOR>.<MINOR>.<PATCH>
```

When the tag is pushed to GitHub, an GitHub Actions workflow automatically creates a release on GitHub, builds and publishes the Python package, and updates the documentation site.

### Editor Setup

TODO: Add VS Code setup instructions

[^1]: Hatch and uv both provide project management capabilities. Currently, we're using Hatch for project management because there are a couple features provided by Hatch that uv doesn't support (e.g. [environments](https://hatch.pypa.io/latest/environment/) and [scripts](https://hatch.pypa.io/latest/config/environment/overview/#scripts)). Eventually, this project may switch over to use uv exclusively and remove the dependency on Hatch.

<!-- development-guide-end -->
