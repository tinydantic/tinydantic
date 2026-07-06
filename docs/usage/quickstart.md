# Quickstart

This page takes you from an empty database to a full create-read-update-delete cycle in a handful of lines.

## Create a database

Every `tinydantic` model stores its documents in a [TinyDB](https://tinydb.readthedocs.io/en/latest/) database. Here we use an in-memory database so the example is self-contained, but TinyDB supports persistent [storage types](https://tinydb.readthedocs.io/en/latest/usage.html#storage-types) too.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> db = TinyDB(storage=MemoryStorage)

```

## Define a model

A document model is a subclass of [TinydanticModel][tinydantic.TinydanticModel]. Pass the `database` and `table_name` as class keyword arguments, then declare fields with ordinary type annotations.

```pycon
>>> from pydantic import EmailStr
>>> from tinydantic import TinydanticModel
>>> class User(TinydanticModel, database=db, table_name='users'):
...     name: str
...     email: EmailStr

```

> [!TIP]
>
> Because `User` is a subclass of [TinydanticModel][tinydantic.TinydanticModel] (itself a subclass of [pydantic.BaseModel][]), it is a full Pydantic model. Everything you know about Pydantic — validators, computed fields, JSON schema — works here.

## Insert a document

Create an instance and call [insert()][tinydantic.TinydanticModel.insert]. Before insertion the model's `id` is `None`; afterwards it carries the document id TinyDB assigned.

```pycon
>>> alice = User(name='Alice', email='alice@example.com')
>>> alice
User(id=None, name='Alice', email='alice@example.com')
>>> alice.insert()
User(id=1, name='Alice', email='alice@example.com')

```

## Read it back

Query the table by building a condition from a model field. [get()][tinydantic.TinydanticModel.get] returns a single validated model instance (or `None`).

```pycon
>>> User.get(User.name == 'Alice')
User(id=1, name='Alice', email='alice@example.com')

```

## Update it

Mutate the instance and call [save()][tinydantic.TinydanticModel.save]. Because the model already has an `id`, `save()` updates the stored document in place.

```pycon
>>> alice.email = 'alice@work.example.com'
>>> alice.save()
User(id=1, name='Alice', email='alice@work.example.com')
>>> User.get(User.name == 'Alice')
User(id=1, name='Alice', email='alice@work.example.com')

```

## Delete it

Call [delete()][tinydantic.TinydanticModel.delete] to remove the document. Querying for it afterwards returns `None`.

```pycon
>>> alice.delete()
>>> print(User.get(User.name == 'Alice'))
None

```

## Using TinyDB directly

Because `tinydantic` is built on top of TinyDB, you can always drop down to TinyDB itself — the database and its tables are ordinary TinyDB objects. For comparison, here is the same kind of insert-and-query flow against the `users` table directly, without `tinydantic`:

```pycon
>>> users_table = db.table('users')
>>> users_table.insert({'name': 'Bob', 'email': 'bob@example.com'})
2
>>> from tinydb import where
>>> users_table.get(where('name') == 'Bob')
{'name': 'Bob', 'email': 'bob@example.com'}

```

Notice that TinyDB does not restrict what you insert, and the raw document comes back as a plain dict — no parsing, no validation, no model.

## Pydantic validation in action

So what happens if an invalid document somehow ends up in the database? Let's insert one directly with TinyDB — bypassing the model — that is missing the `email` field the `User` model requires:

```pycon
>>> users_table.insert({'name': 'Carol'})
3
>>> User.get(User.name == 'Carol')
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for User
email
  Field required [type=missing, input_value={'name': 'Carol'}, input_type=Document]

```

Pydantic refuses to hand you a `User` that does not satisfy the model, so data problems surface at the boundary instead of propagating through your code.

## Where next

- [CRUD tour](crud.md) — the full set of create, read, update, and delete methods, with the sharp edges spelled out.
- [Queries](queries.md) — comparisons, logical composition, nested fields, and static type checking.
