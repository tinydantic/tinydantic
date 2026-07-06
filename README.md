# tinydantic

<!-- overview-start -->

[![PyPI - Version](https://img.shields.io/pypi/v/tinydantic.svg)](https://pypi.org/project/tinydantic) [![PyPI - Python Version](https://img.shields.io/pypi/pyversions/tinydantic.svg)](https://pypi.org/project/tinydantic) [![Pydantic v2](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/pydantic/pydantic/main/docs/badge/v2.json)](https://pydantic.dev)

`tinydantic` is a simple Python object-document mapper (ODM) for the [TinyDB](https://tinydb.readthedocs.io/en/latest/) document database. It uses [Pydantic](https://docs.pydantic.dev/latest/)—the most widely used data validation library—for document model definition and validation.

<!-- prettier-ignore-start -->

> [!NOTE]
> `tinydantic` is under active development. Releases follow the [SemVer versioning spec](https://semver.org):
>
> > Major version zero (0.y.z) is for initial development. Anything MAY change at any time. The public API SHOULD NOT be considered stable.
>
> Minor releases may include breaking changes until v1.0 — check the [changelog](https://github.com/tinydantic/tinydantic/blob/main/CHANGELOG.md) when upgrading. Feedback is welcome!

<!-- prettier-ignore-end -->

<!-- overview-end -->

Full documentation — including a [quickstart](https://tinydantic.dev/latest/usage/quickstart/) that walks through a complete create-read-update-delete example — is available at [tinydantic.dev](https://tinydantic.dev).

## Table of Contents

- [Installation](#installation)
- [Introduction](#introduction)
- [License](#license)

## Introduction

<!-- introduction-start -->

`tinydantic` is a wrapper library around [TinyDB](https://tinydb.readthedocs.io/en/latest/) that enables using [Pydantic](https://docs.pydantic.dev/) models to manage documents stored in a TinyDB database. By specifying Python type annotations for each field in a document model, data validation is handled automatically by Pydantic when instantiating a model from the database.

<!-- introduction-end -->

## Installation

<!-- installation-start -->

`tinydantic` is [available on PyPI](https://pypi.org/project/tinydantic/) and can be installed with [pip](https://github.com/pypa/pip). Easy peasy lemon squeezy 🍋

```sh
pip install tinydantic
```

<!-- installation-end -->

## License

See the [LICENSE](https://github.com/tinydantic/tinydantic/blob/main/LICENSE.md) file for copyright & license information.
