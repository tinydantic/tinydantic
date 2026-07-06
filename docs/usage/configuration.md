# Configuration

Configuration is how a model learns _where_ its documents live: which [TinyDB][tinydb.database.TinyDB] database, and which table within it. `tinydantic` takes both as class keyword arguments — the same shape as SQLModel's `class Hero(SQLModel, table=True)`. This page covers the two config keys, how the table name is derived, how config flows through subclassing, late binding with `bind()`, the errors you can hit, and — in a closing design note — why this config deliberately lives outside Pydantic's `model_config`.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import TinydanticModel
>>> db = TinyDB(storage=MemoryStorage)

```

## Class keyword arguments

A model is configured with two keyword arguments on the class statement: `database=` (a TinyDB instance) and `table_name=` (a string).

```pycon
>>> class User(TinydanticModel, database=db, table_name='users'):
...     name: str
>>> User(name='Alice').insert()
User(id=1, name='Alice')

```

## Table-name derivation

`table_name=` is optional. When you omit it, the table name is derived from the class name converted to `snake_case` via [pydantic.alias_generators.to_snake][] — so `AdminUser` stores its documents in a table named `admin_user`:

```pycon
>>> class AdminUser(TinydanticModel, database=db):
...     name: str
>>> AdminUser(name='root').insert()
AdminUser(id=1, name='root')
>>> AdminUser.get_table().name
'admin_user'

```

## Configuration inheritance

Config keys are resolved by walking the class's [MRO](https://docs.python.org/3/glossary.html#term-method-resolution-order): each key is looked up on the class itself first, then its bases, and the first class that sets it wins. A subclass therefore inherits its parent's config and can override any single key while leaving the rest intact.

Here `Base` is bound to `db` with an explicit table name. `Child` sets only `table_name` — it inherits `database` from `Base`:

```pycon
>>> class Base(TinydanticModel, database=db, table_name='base_table'):
...     a: int
>>> class Child(Base, table_name='child_table'):
...     b: int
>>> Child.get_database() is db
True
>>> Child.get_table().name
'child_table'

```

Each class stores only the keys explicitly set on it, so overriding a key on a child never mutates the parent:

```pycon
>>> Base.get_table().name
'base_table'

```

## Late binding with `bind()`

Sometimes no `TinyDB` instance exists when the class is defined — a common case in tests and application factories, where the database is created at startup. Define the model with no `database=`, then attach one later with [bind()][tinydantic.TinydanticModel.bind]:

```pycon
>>> class Product(TinydanticModel, table_name='products'):
...     sku: str
>>> Product.bind(database=db)
>>> Product(sku='ABC-123').insert()
Product(id=1, sku='ABC-123')

```

`bind()` updates only the keys you pass, leaving the others (including inherited ones) untouched, and binding a subclass never affects its parents.

## `DatabaseNotBoundError`

Any table operation on a model that has no database anywhere in its class hierarchy raises [DatabaseNotBoundError][tinydantic.errors.DatabaseNotBoundError]. The message points at both ways to fix it:

```pycon
>>> class Orphan(TinydanticModel):
...     value: int
>>> Orphan.all()
Traceback (most recent call last):
  ...
tinydantic.errors.DatabaseNotBoundError: No database is bound to 'Orphan'. Pass database=<TinyDB instance> as a class keyword when defining the model, or call Orphan.bind(database=...) before using it.

```

## `AmbiguousConfigError`

MRO lookup gives a single, unambiguous answer when config comes down _one_ inheritance chain. The one case where it could not is a diamond: a class inheriting from two _unrelated_ bases that each set the same key to different values. Rather than silently pick one, `tinydantic` raises [AmbiguousConfigError][tinydantic.errors.AmbiguousConfigError] at class-definition time.

```pycon
>>> other_db = TinyDB(storage=MemoryStorage)
>>> class FromMain(TinydanticModel, database=db):
...     pass
>>> class FromOther(TinydanticModel, database=other_db):
...     pass
>>> class Combined(FromMain, FromOther):
...     value: int
Traceback (most recent call last):
  ...
tinydantic.errors.AmbiguousConfigError: 'Combined' inherits conflicting values for tinydantic config key 'database' from unrelated base classes 'FromMain' and 'FromOther'. Set database= explicitly on 'Combined' to resolve the ambiguity.

```

Setting the key explicitly on the new class resolves the conflict — the class's own value wins, and no lookup ambiguity remains:

```pycon
>>> class Combined(FromMain, FromOther, database=db):
...     value: int
>>> Combined.get_database() is db
True

```

## Design notes: why config is not in `model_config`

`tinydantic` stores its config in a per-class `__tinydantic_config__` attribute and resolves it by walking the MRO — deliberately _not_ in Pydantic's [model_config][pydantic.BaseModel.model_config]. The reason is a mismatch in ordering semantics.

Pydantic merges `model_config` across multiple base classes in "last wins" order — the _opposite_ of Python's MRO ([pydantic#9992](https://github.com/pydantic/pydantic/issues/9992)). Community fixes were rejected as breaking changes, and the behavior may yet change in Pydantic v3. Storing `tinydantic`'s keys there would inherit those surprising semantics, risk future key collisions with Pydantic's own [ConfigDict][pydantic.ConfigDict], and couple binding resolution to behavior Pydantic itself may flip.

Using a separate attribute with plain MRO lookup sidesteps all three problems. There is no scenario where "our order versus Pydantic's order" silently matters: a single inheritance chain resolves identically under both orderings, and the only case where they _could_ disagree — two unrelated bases with conflicting values — is turned into a loud `AmbiguousConfigError` rather than a quiet guess. This matches the rationale in the [tinydantic.config][] module docstring.

> [!NOTE]
>
> `tinydantic` keeps one legitimate key in `model_config`: `protected_namespaces=("tinydantic_",)`, which reserves the `tinydantic_` prefix so future methods cannot collide with your field names. That is a genuine Pydantic setting, so it belongs there.

## Where next

- [Storage](storage.md) — the TinyDB backends you can bind a model to.
- [CRUD tour](crud.md) — the read and write methods that use this configuration.
