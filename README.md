# tinydantic

<!-- overview-start -->

[![PyPI - Version](https://img.shields.io/pypi/v/tinydantic.svg)](https://pypi.org/project/tinydantic) [![PyPI - Python Version](https://img.shields.io/pypi/pyversions/tinydantic.svg)](https://pypi.org/project/tinydantic)

`tinydantic` is a simple Python object-document mapper (ODM) for the [TinyDB](https://tinydb.readthedocs.io/en/latest/) document database. It uses [Pydantic](https://docs.pydantic.dev/latest/)—the most widely used data validation library—for document model definition and validation.

<!-- prettier-ignore-start -->

> [!WARNING]
> `tinydantic` is currently a work in progress 🏗️
>
> This project is still in the prototyping phase and should be considered experimental.
>
> Releases follow the [SemVer versioning spec](https://semver.org):
>
> > Major version zero (0.y.z) is for initial development. Anything MAY change at any time. The public API SHOULD NOT be considered stable.
>
> There's not much to see here yet, but feel free to grab your hard hat 👷 and have a look around. Feedback is welcome!

<!-- prettier-ignore-end -->

<!-- overview-end -->

## Table of Contents

- [Installation](#installation)
- [Introduction](#introduction)
- [License](#license)

## Introduction

<!-- introduction-start -->

`tinydantic` is a wrapper library around [TinyDB](https://tinydb.readthedocs.io/en/latest/) that enables using [Pydantic](https://docs.pydantic.dev/) models to manage documents stored in a TinyDB database. By specifying Python type annotations for each field in a document model, validation is handled automatically by Pydantic when instantiating a model from the database.

<!-- introduction-end -->

## Installation

<!-- installation-start -->

`tinydantic` is [available on PyPI](https://pypi.org/project/tinydantic/) and can be installed with [pip](https://github.com/pypa/pip).

```sh
pip install tinydantic
```

<!-- installation-end -->

## Basic Example

<!-- basic-example-start -->

Here's a basic example showing how to create, insert, and query for a document using `tinydantic`.

### Using `tinydantic` models

First, create a TinyDB database where the documents will be stored. In this example, we're using an in-memory database, but TinyDB supports other [storage types](https://tinydb.readthedocs.io/en/latest/usage.html#storage-types) which can store the database persistently as JSON, YAML, etc.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> db = TinyDB(storage=MemoryStorage)

```

Create a `User` document model, configuring it to store documents in the `users` table of the `db` database. Since `User` is a subclass of [Document][tinydantic.Document] (which itself is a subclass of [pydantic.BaseModel][]), `User` is also a Pydantic model! You have all the power of Pydantic models when creating a `tinydantic` document model.

```pycon
>>> from pydantic import EmailStr
>>> from tinydantic import Document
>>> class User(Document):
...     database = db
...     table_name = 'users'
...     name: str
...     email: EmailStr

```

Create a new `User` instance for a user named "Alice".

```pycon
>>> alice = User(name='Alice', email='alice@example.com')

```

Insert `alice` into the database.

```pycon
>>> alice.insert()
User(id=1, name='Alice', email='alice@example.com')

```

Query the database for users with the name "Alice". Notice that this returns a `User` instance that was automatically validated by Pydantic!

```pycon
>>> User.get(User.name == 'Alice')
User(id=1, name='Alice', email='alice@example.com')

```

### Comparison to TinyDB

Since `tinydantic` is built on top of TinyDB, you can still use the `tinydb` package to interact with the database directly.

For comparison, let's try to accomplish the same task as shown above using only TinyDB _without_ `tinydantic`. For this example, we'll continue using the same database (`db`) we created earlier.

```pycon
>>> users_table = db.table('users')
>>> users_table.insert({'name': 'Alice', 'email': 'alice@example.com'})
2
>>> from tinydb import where
>>> users_table.get(where('name') == 'Alice')
{'name': 'Alice', 'email': 'alice@example.com'}

```

Notice, that TinyDB does not impose any restrictions on the document we insert _into_ the database table. Additionally, there is no automatic parsing or validation of the data _returned_ from the database.

### Pydantic validation in action

_What happens if an invalid document is somehow returned from the database?_

Let's set up a contrived example to test the automatic Pydantic validation.

First, we'll manually insert a document that is missing the `email` field from the `User` model we created earlier.

```pycon
>>> users_table.insert({'name': 'Bob'})
3

```

Next, we'll query for users named "Bob" using the tinydantic model we created earlier.

```pycon
>>> User.get(User.name == 'Bob')
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for User
email
  Field required [type=missing, input_value={'name': 'Bob'}, input_type=Document]
```

As you can see, Pydantic produced a `ValidationError` because the document returned from the database is missing the `email` field required by the `User` model.

<!-- basic-example-end -->

## License

See the [LICENSE](https://github.com/tinydantic/tinydantic/blob/main/LICENSE.md) file for copyright & license information.
