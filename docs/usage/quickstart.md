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
>>> from tinydantic import TinydanticModel
>>> class User(TinydanticModel, database=db, table_name="users"):
...     name: str
...     age: int

```

> [!TIP]
>
> Because `User` is a subclass of [TinydanticModel][tinydantic.TinydanticModel] (itself a subclass of [pydantic.BaseModel][]), it is a full Pydantic model. Everything you know about Pydantic — validators, computed fields, JSON schema, rich types — works here.

## Insert a document

Create an instance and call [insert()][tinydantic.TinydanticModel.insert]. Before insertion the model's `id` is `None`; afterwards it carries the document id TinyDB assigned.

```pycon
>>> alice = User(name="Alice", age=37)
>>> alice
User(id=None, name='Alice', age=37)
>>> alice.insert()
User(id=1, name='Alice', age=37)

```

## Read it back

Query the table by building a condition from a model field. [get()][tinydantic.TinydanticModel.get] returns a single validated model instance (or `None`).

```pycon
>>> User.get(User.name == "Alice")
User(id=1, name='Alice', age=37)

```

## If you use a type checker

That query runs correctly, but `mypy` or `pyright` will flag it. On the _class_, `User.name` returns a TinyDB query — that is what makes the comparison a query condition. A type checker cannot see that: it reads the field's annotation (`str`) and concludes `User.name == "Alice"` is a `bool`.

```text
error: Argument 1 to "get" has incompatible type "bool"; expected "QueryLike"
```

Wrap the field in [q()][tinydantic.q] to tell the checker what actually happens at runtime:

```pycon
>>> from tinydantic import q
>>> User.get(q(User.name) == "Alice")
User(id=1, name='Alice', age=37)

```

`q()` hands back the very object you passed it, so both spellings build the identical query — there is no runtime cost and no behavior change. If you do not run a type checker you never need it, which is why the rest of these docs use the shorter bare form.

> [!TIP]
>
> Reach for `q()` rather than silencing the error. `get()`, `get_or_raise()`, and `find()` are overloaded, and when no overload matches, `mypy` gives up on the whole call and types the result `Any` — so a `# type: ignore` hides the message and leaves you with an unchecked value where a `User` should be.

See [Queries → Static type checking](queries.md#static-type-checking) for what `q()` does and does not fix.

## Update it

Mutate the instance and call [save()][tinydantic.TinydanticModel.save]. Because the model already has an `id`, `save()` updates the stored document in place.

```pycon
>>> alice.age = 38
>>> alice.save()
User(id=1, name='Alice', age=38)
>>> User.get(User.name == "Alice")
User(id=1, name='Alice', age=38)

```

## Delete it

Call [delete()][tinydantic.TinydanticModel.delete] to remove the document. Querying for it afterwards returns `None`.

```pycon
>>> alice.delete()
>>> print(User.get(User.name == "Alice"))
None

```

## Using TinyDB directly

Because `tinydantic` is built on top of TinyDB, you can always drop down to TinyDB itself — the database and its tables are ordinary TinyDB objects. For comparison, here is the same kind of insert-and-query flow against the `users` table directly, without `tinydantic`:

```pycon
>>> users_table = db.table("users")
>>> users_table.insert({"name": "Bob", "age": 25})
2
>>> from tinydb import where
>>> users_table.get(where("name") == "Bob")
{'name': 'Bob', 'age': 25}

```

Notice that TinyDB does not restrict what you insert, and the raw document comes back as a plain dict — no parsing, no validation, no model.

## Pydantic validation in action

So what happens if an invalid document somehow ends up in the database? Let's insert one directly with TinyDB — bypassing the model — that is missing the `age` field the `User` model requires:

```pycon
>>> users_table.insert({"name": "Carol"})
3
>>> User.get(User.name == "Carol")
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for User
age
  Field required [type=missing, input_value={'name': 'Carol'}, input_type=Document]

```

Pydantic refuses to hand you a `User` that does not satisfy the model, so data problems surface at the boundary instead of propagating through your code.

## Where next

- [CRUD tour](crud.md) — the full set of create, read, update, and delete methods, with the sharp edges spelled out.
- [Queries](queries.md) — comparisons, logical composition, nested fields, and static type checking.
