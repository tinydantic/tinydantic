# Queries

Accessing a field on a model _class_ returns a [TinyDB Query][tinydb.queries.Query], so you build queries straight from your model definition: `User.name == 'Alice'` is a query condition, not a comparison. This page covers field comparisons, logical composition, nested fields, the raw-query escape hatch, and how to keep static type checkers happy.

The examples share an in-memory database of three users. Run them in order.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from pydantic import BaseModel
>>> from tinydantic import TinydanticModel
>>> db = TinyDB(storage=MemoryStorage)
>>> class Address(BaseModel):
...     city: str
...     country: str
>>> class User(TinydanticModel, database=db, table_name='users'):
...     name: str
...     age: int
...     email: str
...     address: Address
>>> users = User.insert_multiple([
...     User(name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
...     User(name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE')),
...     User(name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE')),
... ])
>>> [user.id for user in users]
[1, 2, 3]

```

## Field comparisons

Equality and the ordering operators build the query you would expect:

```pycon
>>> User.get(User.name == 'Alice')
User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))
>>> User.search(User.name != 'Alice')
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]
>>> User.search(User.age < 30)
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE'))]

```

The query object also exposes TinyDB's own methods. `.matches` tests the _whole_ value against a regular expression, `.search` looks for the pattern _anywhere_ in the value, and `.test` runs an arbitrary predicate:

```pycon
>>> User.search(User.email.matches(r'.*@example\.com'))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]
>>> User.search(User.email.search('example.org'))
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE'))]
>>> User.search(User.age.test(lambda v: v >= 30))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

## Logical composition

Combine conditions with `&` (and), `|` (or), and `~` (not). Parenthesize each operand — Python's bitwise operators bind more loosely than comparisons.

```pycon
>>> User.search((User.age >= 30) & (User.address.country == 'US'))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]
>>> User.search((User.name == 'Alice') | (User.name == 'Bob'))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE'))]
>>> User.search(~(User.address.country == 'DE'))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]

```

## Nested fields

Chain attribute access to query into a nested model. `User.address.city` builds a query against the `city` key inside the stored `address` object.

```pycon
>>> User.search(User.address.city == 'Berlin')
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

## Escaping to a raw TinyDB query

The field syntax covers the common cases, but TinyDB's [Query][tinydb.queries.Query] has more: `one_of`, `any`, `all`, `fragment`, and friends. Build a raw query and pass it to any read method — `search()`, `get()`, `count()`, and so on all accept it.

```pycon
>>> from tinydb import Query
>>> query = Query()
>>> User.search(query.name.one_of(['Alice', 'Carol']))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

## Static type checking

At runtime `User.name` is a Query, so `User.name == 'Alice'` produces a query condition. A static type checker, however, sees the field's _annotation_ (`str`) and concludes that `User.name == 'Alice'` is a `bool` — then complains when you pass that "bool" to `search()`. The code runs correctly; only the type checker is confused.

The [q()][tinydantic.q] helper resolves this. It returns its argument unchanged but typed as a Query, so the comparison types as a query condition. This mirrors SQLModel's [col()](https://sqlmodel.tiangolo.com/tutorial/where/#type-annotations-and-errors) function, which exists for the same reason.

```pycon
>>> from tinydantic import q
>>> User.search(q(User.name) == 'Alice')
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]

```

> [!TIP]
>
> `q()` changes nothing at runtime — `q(User.name) == 'Alice'` and `User.name == 'Alice'` build the identical query. Reach for it only to silence a type checker; every other example on this page uses the bare form.

## Sharp edge: fields that shadow query methods

A read method or query method shares its name with a field at your peril. Because `search`, `get`, `count`, `matches`, `test`, and the like are real attributes on the model class (or on the Query object), a field with the same name is shadowed — attribute access finds the method, not a field query.

Consider a model with a field literally named `search`:

```pycon
>>> class Command(TinydanticModel, database=db, table_name='commands'):
...     name: str
...     search: str
>>> commands = Command.insert_multiple([
...     Command(name='find', search='fuzzy'),
...     Command(name='grep', search='regex'),
... ])
>>> [command.id for command in commands]
[1, 2]

```

`Command.search` is the [search()][tinydantic.TinydanticModel.search] classmethod, not a field query. Comparing it to a string does not build a query — it just evaluates to `False`, which would silently match nothing:

```pycon
>>> Command.search == 'fuzzy'
False

```

> [!WARNING]
>
> **A field whose name collides with a method is not reachable through the `Model.field` shorthand.** The expression compiles and runs, but it produces a plain `bool` instead of a query — a bug that fails silently. Use the raw-query escape hatch to reach the field by name.

Reach the shadowed field with a raw [Query][tinydb.queries.Query] (or [where()](https://tinydb.readthedocs.io/en/latest/usage.html#queries)) that names the key as a string:

```pycon
>>> from tinydb import Query, where
>>> Command.search(Query()['search'] == 'fuzzy')
[Command(id=1, name='find', search='fuzzy')]
>>> Command.search(where('search') == 'regex')
[Command(id=2, name='grep', search='regex')]

```
