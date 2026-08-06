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
>>> class User(TinydanticModel, database=db, table_name="users"):
...     name: str
...     age: int
...     email: str
...     address: Address
>>> users = User.insert_multiple(
...     [
...         User(
...             name="Alice",
...             age=30,
...             email="alice@example.com",
...             address=Address(city="Portland", country="US"),
...         ),
...         User(
...             name="Bob",
...             age=25,
...             email="bob@example.org",
...             address=Address(city="Berlin", country="DE"),
...         ),
...         User(
...             name="Carol",
...             age=35,
...             email="carol@example.com",
...             address=Address(city="Berlin", country="DE"),
...         ),
...     ]
... )
>>> [user.id for user in users]
[1, 2, 3]

```

## Field comparisons

Equality and the ordering operators build the query you would expect:

```pycon
>>> User.get(User.name == "Alice")
User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))
>>> User.search(User.name != "Alice")
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]
>>> User.search(User.age < 30)
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE'))]

```

The query object also exposes TinyDB's own methods. `.matches` tests the _whole_ value against a regular expression, `.search` looks for the pattern _anywhere_ in the value, and `.test` runs an arbitrary predicate:

```pycon
>>> User.search(User.email.matches(r".*@example\.com"))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]
>>> User.search(User.email.search("example.org"))
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE'))]
>>> User.search(User.age.test(lambda v: v >= 30))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

> [!WARNING]
>
> `.matches()` and `.search()` compile their pattern with Python's `re` module. Never compile untrusted input as a pattern — attacker-chosen regexes can trigger catastrophic backtracking (ReDoS). See [Security considerations](security.md#untrusted-input-in-queries).

## Logical composition

Combine conditions with `&` (and), `|` (or), and `~` (not). Parenthesize each operand — Python's bitwise operators bind more loosely than comparisons.

```pycon
>>> User.search((User.age >= 30) & (User.address.country == "US"))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]
>>> User.search((User.name == "Alice") | (User.name == "Bob"))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE'))]
>>> User.search(~(User.address.country == "DE"))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]

```

## Nested fields

Chain attribute access to query into a nested model. `User.address.city` builds a query against the `city` key inside the stored `address` object.

```pycon
>>> User.search(User.address.city == "Berlin")
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

## Escaping to a raw TinyDB query

The field syntax covers the common cases, but TinyDB's [Query][tinydb.queries.Query] has more: `one_of`, `any`, `all`, `fragment`, and friends. Build a raw query and pass it to any read method — `search()`, `get()`, `count()`, and so on all accept it.

```pycon
>>> from tinydb import Query
>>> query = Query()
>>> User.search(query.name.one_of(["Alice", "Carol"]))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

## Static type checking

At runtime `User.name` is a Query, so `User.name == 'Alice'` produces a query condition. A static type checker, however, sees the field's _annotation_ (`str`) and concludes that `User.name == 'Alice'` is a `bool` — then complains when you pass that "bool" to `search()`. The code runs correctly; only the type checker is confused.

The [q()][tinydantic.q] helper resolves this. It returns its argument unchanged but typed as a Query, so the comparison types as a query condition. This mirrors SQLModel's [col()](https://sqlmodel.tiangolo.com/tutorial/where/#type-annotations-and-errors) function, which exists for the same reason.

```pycon
>>> from tinydantic import q
>>> User.search(q(User.name) == "Alice")
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]

```

> [!TIP]
>
> `q()` changes nothing at runtime — `q(User.name) == 'Alice'` and `User.name == 'Alice'` build the identical query. Reach for it only to silence a type checker; every other example on this page uses the bare form.

`q()` also accepts a field name as a string, building a query on that document key. This form exists for the shadowed-field escape hatch below.

```pycon
>>> User.search(q("name") == "Alice")
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]

```

## Querying by id

The `id` field is not a body field: it maps to TinyDB's `doc_id`, the document's key in the table (see [Models](models.md)). Class-level `User.id` therefore builds a _document-id query_, which the model methods translate to TinyDB's native id operations — the same convenience Beanie and ODMantic provide for MongoDB's `_id`:

```pycon
>>> User.get(User.id == 2)
User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE'))
>>> User.search(User.id.one_of([1, 3]))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

The full comparison set works (`==`, `!=`, `<`, `<=`, `>`, `>=`, `one_of`), and id conditions compose with field conditions:

```pycon
>>> User.search((User.id >= 2) & (User.address.country == "DE"))
[User(id=2, name='Bob', age=25, email='bob@example.org', address=Address(city='Berlin', country='DE')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

An id condition only accepts an int. Anything else raises immediately — including `None`, which is what `id` is on a model that was never inserted:

```pycon
>>> draft = User(
...     name="Dana",
...     age=41,
...     email="dana@example.com",
...     address=Address(city="Oslo", country="NO"),
... )
>>> User.get(User.id == draft.id)
Traceback (most recent call last):
  ...
TypeError: id conditions require an int document id, got None

```

`Model.id` and `q("id")` are different things: `q(User.id)` is the typed form of the document-id query, while the string form `q("id")` queries a literal `id` key in the document body — a key tinydantic never writes:

```pycon
>>> User.search(q(User.id) == 1)
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]
>>> User.search(q("id") == 1)
[]

```

Because TinyDB's own query evaluator only ever sees the document body, an id condition that bypasses the model methods fails loudly rather than silently matching nothing:

```pycon
>>> db.table("users").search(User.id == 1)
Traceback (most recent call last):
  ...
tinydantic._errors.DocumentIDConditionError: An id condition reached TinyDB's raw query evaluator

```

> [!WARNING]
>
> Ordered comparisons match against a document's _current_ id, and ids are reused: [truncate()][tinydantic.TinydanticModel.truncate] resets the counter so new documents start again at 1, and [save()][tinydantic.TinydanticModel.save] can re-insert a document under its old id. A stored bookmark like "poll for `User.id > 50`" silently misses everything inserted after a reset — use a real timestamp or sequence field for insertion-order logic.

The reset trap, concretely — a checkpoint recorded before a truncate silently misses everything inserted after it:

```pycon
>>> class Draft(TinydanticModel, database=db, table_name="drafts"):
...     text: str
>>> drafts = Draft.insert_multiple(
...     [Draft(text="a"), Draft(text="b"), Draft(text="c")]
... )
>>> [draft.id for draft in drafts]
[1, 2, 3]
>>> checkpoint = 3
>>> Draft.truncate()
>>> Draft(text="newest, after the reset").insert()
Draft(id=1, text='newest, after the reset')
>>> Draft.search(Draft.id > checkpoint)
[]

```

## Sharp edge: fields that shadow query methods

A field cannot silently share its name with a method. Because `search`, `get`, `count`, and the other model methods are real attributes on the model class, a field with the same name would be shadowed — attribute access would find the method, not a field query, so `Model.field` sugar would break. tinydantic refuses the class definition instead of letting that happen:

```pycon
>>> class Command(TinydanticModel, database=db, table_name="commands"):
...     name: str
...     search: str
Traceback (most recent call last):
  ...
tinydantic._errors.ShadowedFieldError: Field(s) on 'Command' shadow existing attributes ...

```

If you need the field anyway — say the table is shared with another tool that writes a `search` key — opt in explicitly with the `shadowed_fields=` class kwarg. The field then works everywhere (storage, instance access, validation) except the `Model.field` shorthand, which keeps resolving to the method:

```pycon
>>> class Command(
...     TinydanticModel,
...     database=db,
...     table_name="commands",
...     shadowed_fields=("search",),
... ):
...     name: str
...     search: str
>>> commands = Command.insert_multiple(
...     [
...         Command(name="find", search="fuzzy"),
...         Command(name="grep", search="regex"),
...     ]
... )
>>> [command.id for command in commands]
[1, 2]
>>> Command.search == "fuzzy"  # still the method, not a query
False

```

Reach the opted-in field by passing its name to [q()][tinydantic.q], which builds a query on that document key:

```pycon
>>> Command.search(q("search") == "fuzzy")
[Command(id=1, name='find', search='fuzzy')]

```

A raw [Query][tinydb.queries.Query] (or [where()](https://tinydb.readthedocs.io/en/latest/usage.html#queries)) works the same way:

```pycon
>>> from tinydb import Query, where
>>> Command.search(Query()["search"] == "fuzzy")
[Command(id=1, name='find', search='fuzzy')]
>>> Command.search(where("search") == "regex")
[Command(id=2, name='grep', search='regex')]

```

> [!NOTE]
>
> Pydantic also warns about shadowed fields at class definition (`Field name "search" ... shadows an attribute`). For a deliberate opt-in, silence it with `warnings.filterwarnings("ignore", message=r'Field name "search"')` — or treat the warning as a reminder that `q("search")` is the only query path for that field.

## Fluent queries

Every condition on this page — `Model.field` sugar, [q()][tinydantic.q], raw TinyDB queries, `Model.id` conditions — plugs directly into [find()][tinydantic.TinydanticModel.find], which adds sorting, pagination, and lazy, reusable query chains on top. See [Fluent queries](find.md).
