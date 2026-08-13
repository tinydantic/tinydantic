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
>>> users = User.insert_many(
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

The query object also exposes TinyDB's own methods. `.matches` anchors a regular expression at the _start_ of the value, `.search` looks for the pattern _anywhere_ in the value, and `.test` runs an arbitrary predicate:

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
> `.matches()` is anchored at the start only — it runs `re.match`, not `re.fullmatch`, so the pattern above also matches `alice@example.com.evil`. End the pattern with `$` when you mean the whole value. (TinyDB's own docstring says "whole string has to match"; that is the wording, not the behavior — tracked in [#144](https://github.com/tinydantic/tinydantic/issues/144).)

```pycon
>>> mallory = User(
...     name="Mallory",
...     age=40,
...     email="mallory@example.com.evil",
...     address=Address(city="Berlin", country="DE"),
... )
>>> _ = mallory.insert()
>>> [u.name for u in User.search(User.email.matches(r".*@example\.com"))]
['Alice', 'Carol', 'Mallory']
>>> [u.name for u in User.search(User.email.matches(r".*@example\.com$"))]
['Alice', 'Carol']
>>> mallory.delete()

```

> [!WARNING]
>
> `.matches()` and `.search()` compile their pattern with Python's `re` module. Never compile untrusted input as a pattern — attacker-chosen regexes can trigger catastrophic backtracking (ReDoS). See [Security considerations](security.md#untrusted-input-in-queries).

## Logical composition

Combine conditions with `&` (and), `|` (or), and `~` (not). Parenthesize each operand — Python's bitwise operators bind more _tightly_ than comparisons, so without parentheses `User.age >= 30 & User.address.country == "US"` parses as a chained comparison over `30 & User.address.country`, which is not the query you wrote. The keywords `and`, `or`, and `not` are _not_ substitutes — they discard half the query, and raise rather than doing so silently; see [A condition is never a boolean](#a-condition-is-never-a-boolean).

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

## Computed fields

Pydantic's [`@computed_field`](https://docs.pydantic.dev/latest/concepts/fields/#the-computed_field-decorator) is serialized, so unlike an ordinary property it reaches storage as a real document key — and queries like any other field:

```pycon
>>> from pydantic import computed_field
>>> class Product(TinydanticModel, database=db, table_name="products"):
...     name: str
...     price_cents: int
...
...     @computed_field
...     @property
...     def price_band(self) -> str:
...         return "premium" if self.price_cents >= 5000 else "budget"
>>> _ = Product.insert_many(
...     [
...         Product(name="Desk", price_cents=24900),
...         Product(name="Mug", price_cents=1200),
...     ]
... )
>>> Product.search(Product.price_band == "budget")
[Product(id=2, name='Mug', price_cents=1200, price_band='budget')]

```

[field()][tinydantic.field] reaches the same key by name, and builds an identical condition:

```pycon
>>> from tinydantic import field
>>> (Product.price_band == "budget") == (field(Product, "price_band") == "budget")
True

```

An ordinary property is _not_ stored, so it is not queryable — and because it is a real class attribute, comparing it produces a silent `False` rather than an error:

```pycon
>>> class Item(TinydanticModel, database=db, table_name="items"):
...     name: str
...
...     @property
...     def slug(self) -> str:
...         return self.name.lower()
>>> Item.slug == "desk"  # a property, not a query
False

```

If you want to query on a derived value, that is the distinction that matters: add `@computed_field` and it becomes a stored, matchable key.

> [!WARNING]
>
> A computed field's stored value is a snapshot taken at write time. Reading a document re-derives the value from the other fields and ignores the stored one, so if you later change how the value is computed, existing documents keep the old value — and queries match the _stored_ value, not the freshly computed one. Changing the derivation is a schema migration; see [Schema evolution](schema-evolution.md).

Computed fields stay read-only. Assignment raises, exactly as it does on a plain pydantic model:

```pycon
>>> Product.get_by_id(2).price_band = "premium"
Traceback (most recent call last):
  ...
AttributeError: property 'price_band' of 'Product' object has no setter

```

The wording is CPython's own, not tinydantic's: the assignment is handed to the property, so the property raises. That also means the message varies by interpreter — Python 3.10 says `can't set attribute 'price_band'` instead. A computed field that _does_ define a setter still runs it.

## Escaping to a raw TinyDB query

`Model.field` already exposes TinyDB's whole condition vocabulary — `one_of`, `any`, `all`, `fragment`, `test`, and the rest — so the escape hatch is not about missing methods. It is for keys the model does not declare: `extra="allow"` documents, legacy keys left by an older schema, or a database shared with another tool. Build a raw query and pass it to any read method — `search()`, `get()`, `count()`, and so on all accept it. (For a field the model _does_ declare but whose name is shadowed by a method, the answer is [field()](#sharp-edge-fields-that-shadow-query-methods), not a raw query.)

```pycon
>>> from tinydb import Query
>>> query = Query()
>>> User.search(query.name.one_of(["Alice", "Carol"]))
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US')),
  User(id=3, name='Carol', age=35, email='carol@example.com', address=Address(city='Berlin', country='DE'))]

```

## Static type checking

At runtime `User.name` is a Query, so `User.name == 'Alice'` produces a query condition. A static type checker, however, sees the field's _annotation_ (`str`) and concludes that `User.name == 'Alice'` is a `bool` — then complains when you pass that "bool" to `search()`. The code runs correctly; only the type checker is confused.

The [q()][tinydantic.q] helper resolves this. It returns its argument unchanged but typed as a Query, so the comparison types as a query condition. This mirrors SQLModel's [col()](https://sqlmodel.tiangolo.com/tutorial/where/#type-annotations-and-errors) function, which exists for the same reason — and which SQLModel likewise introduces in one section while its examples stay bare.

```pycon
>>> from tinydantic import field, q
>>> User.search(q(User.name) == "Alice")
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]

```

> [!TIP]
>
> `q()` changes nothing at runtime — it hands back the object you passed it, so `q(User.name) == 'Alice'` and `User.name == 'Alice'` build conditions that compare and hash equal. Not even TinyDB's query cache can tell them apart. Examples throughout these docs use the bare form because it reads more directly; in a project you type-check, `q()` is the form that passes.

`q()` is a _cast_, not a constructor. It does not take a field name, because a string is indistinguishable from an instance attribute that happens to hold one — accepting either would make `q(user.name)` quietly build a query on the _value_:

```pycon
>>> alice = User.get(q(User.name) == "Alice")
>>> q(alice.name)
Traceback (most recent call last):
  ...
TypeError: q() expected a TinyDB Query from class-level field access like Model.field, got 'str'. A string is a value, not a field: for a field whose name is shadowed by a method, use field(Model, 'name'); for a raw document key, use tinydb.where('key').

```

To query a field by name, use [field()][tinydantic.field] — see [Sharp edge: fields that shadow query methods](#sharp-edge-fields-that-shadow-query-methods) below.

### Prefer `q()` to suppressing the error

A suppressed error is not equivalent to a fixed one. On a method with a single signature — `search()`, `get()`, `contains()` — `mypy` reports the bad argument and still knows the return type. On the overloaded [find()][tinydantic.TinydanticModel.find] it does not: when no overload matches, `mypy` falls back to `Any` for the whole call.

```text
a = User.search(User.name == "Alice")   # error: incompatible type "bool"
reveal_type(a)                          # list[User]        — return type survives

b = User.get(User.name == "Alice")      # error: incompatible type "bool"
reveal_type(b)                          # User              — return type survives

d = User.find(User.name == "Alice")     # error: no overload variant matches
reveal_type(d)                          # Any               — return type lost

e = User.find(q(User.name) == "Alice")  # no error
reveal_type(e)                          # FindQuery[User]
```

Silence the `find()` error with `# type: ignore` and every method you chain onto `d` goes unchecked. `pyright` is better behaved here — it reports the argument and keeps `FindQuery[User]` — but under either checker the `q()` form is the one that leaves you with the types you came for.

### What `q()` does not fix

`q()` corrects the direction where the checker rejects working code. The mismatch runs the other way too: expressions the checker accepts because it believes the annotation, which then fail at runtime because the class attribute is really a Query.

```pycon
>>> User.name.upper()
Traceback (most recent call last):
  ...
TypeError: QueryInstance.__call__() missing 1 required positional argument: 'value'
>>> len(User.name)
Traceback (most recent call last):
  ...
TypeError: object of type 'Query' has no len()
>>> User.age + 1
Traceback (most recent call last):
  ...
TypeError: unsupported operand type(s) for +: 'Query' and 'int'

```

A type checker passes all three. No wrapper can close that direction — it would take a change to how fields are annotated — so treat `Model.field` as a query builder and nothing else. Reach for the value on an _instance_ (`user.name.upper()`), which is a genuine `str`. The reasoning behind leaving this gap open is recorded in [Static typing design](../contributing/static_typing.md).

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
>>> User.get(User.id == draft.id)  # doctest: -IGNORE_EXCEPTION_DETAIL
Traceback (most recent call last):
  ...
TypeError: id conditions require an int document id, got None. An id of None
means the model was never inserted — insert() or save() it first.

```

`q(User.id)` is the typed form of the document-id query. Asking for `id` _by name_ is refused, because a body query on `id` would match nothing forever — tinydantic never writes that key:

```pycon
>>> User.search(q(User.id) == 1)
[User(id=1, name='Alice', age=30, email='alice@example.com', address=Address(city='Portland', country='US'))]
>>> field(User, "id")
Traceback (most recent call last):
  ...
tinydantic._errors.QueryFieldError: 'id' is not a queryable field of 'User': it maps to TinyDB's doc_id and is never written to the document body. Use User.id for document-id queries (q(User.id) == 1).

```

Because TinyDB's own query evaluator only ever sees the document body, an id condition that bypasses the model methods fails loudly rather than silently matching nothing:

```pycon
>>> db.table("users").search(User.id == 1)  # doctest: -IGNORE_EXCEPTION_DETAIL
Traceback (most recent call last):
  ...
tinydantic._errors.DocumentIDConditionError: An id condition reached TinyDB's
raw query evaluator, which only ever sees the document body (never doc_id).
Pass id conditions to tinydantic model methods, or select documents by id with
get_by_ids(), update_by_ids(), or remove_by_ids() instead.

```

> [!WARNING]
>
> Ordered comparisons match against a document's _current_ id, and ids are reused: [truncate()][tinydantic.TinydanticModel.truncate] resets the counter so new documents start again at 1, and [save()][tinydantic.TinydanticModel.save] can re-insert a document under its old id. A stored bookmark like "poll for `User.id > 50`" silently misses everything inserted after a reset — use a real timestamp or sequence field for insertion-order logic.

The reset trap, concretely — a checkpoint recorded before a truncate silently misses everything inserted after it:

```pycon
>>> class Draft(TinydanticModel, database=db, table_name="drafts"):
...     text: str
>>> drafts = Draft.insert_many([Draft(text="a"), Draft(text="b"), Draft(text="c")])
>>> [draft.id for draft in drafts]
[1, 2, 3]
>>> checkpoint = 3
>>> Draft.truncate()
>>> Draft(text="newest, after the reset").insert()
Draft(id=1, text='newest, after the reset')
>>> Draft.search(Draft.id > checkpoint)
[]

```

## A condition is never a boolean

`User.name == "Alice"` does not compare anything. It builds a description of a test — an object TinyDB runs later, once per document. In raw TinyDB such an object is truthy, and truthy _always_: the field, the operator, the value, and the contents of the table make no difference, so `if User.name == requested:` is a check that always passes. tinydantic raises [QueryTypeError][tinydantic.QueryTypeError] instead:

```pycon
>>> bool(User.name == "Alice")  # doctest: -IGNORE_EXCEPTION_DETAIL
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: A query condition has no truth value
(it is a lazy description of a test, not a comparison). For an existence check
use Model.contains(cond), Model.get_or_none(cond) is not None, or
Model.find(cond).exists(). To combine conditions use & | ~ — and/or/not
evaluate truthiness and silently discard half the query. To compare a value
you already hold, reach through an instance (user.name == x), not the class
(User.name == x). To test whether a condition variable was set, write
'cond is not None'.

```

That covers every construct which asks an object for its truth value — `if`, `not`, `and`, `or`, `any()`, `all()`, a comprehension's `if` clause. The sections below name each mistake and the query that says what was meant.

### Asking whether a document exists

A condition reads like a check, so it gets written as one. It is not a check: at this point nothing has touched the table.

```pycon
>>> if User.name == "nobody by this name":
...     print("unreachable")
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: A query condition has no truth value ...

```

Hand the condition to a method instead. Which method depends on what you want back:

```pycon
>>> User.contains(User.name == "nobody by this name")
False
>>> User.get_or_none(User.name == "nobody by this name") is not None
False
>>> User.find(User.name == "nobody by this name").exists()
False

```

[contains()][tinydantic.TinydanticModel.contains] when a bool is the whole answer, [get_or_none()][tinydantic.TinydanticModel.get_or_none] when you want the document too, and [exists()][tinydantic.FindQuery.exists] when you already hold a chain. Not `get()`: it raises on a miss, which is the case an existence check is asking about.

### Combining conditions

`&`, `|`, and `~` compose queries. `and`, `or`, and `not` do not — they evaluate truthiness and hand back one operand unchanged, so half the query would disappear. All three raise:

```pycon
>>> (User.age >= 30) and (User.address.country == "DE")
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: A query condition has no truth value ...
>>> not (User.age >= 30)
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: A query condition has no truth value ...

```

Composition keeps the guard, so a composed condition cannot leak into boolean context either:

```pycon
>>> combined = (User.age >= 30) & (User.address.country == "DE")
>>> [user.name for user in User.search(combined)]
['Carol']
>>> bool(combined)
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: A query condition has no truth value ...

```

Building a condition from a list needs the same care. `any()` and `all()` reduce with `or`/`and`, so they raise as well; reduce with the query operators instead:

```pycon
>>> import functools, operator
>>> conditions = [User.age >= 30, User.address.country == "DE"]
>>> matched = User.search(functools.reduce(operator.and_, conditions))
>>> [user.name for user in matched]
['Carol']

```

### Membership and indexing

`in` is not a query operator. In raw TinyDB it reports `True` for any operand at all — Python falls back to iterating the query object, which yields more query objects endlessly, and the first comparison it makes is truthy. Iteration is refused, so `in` raises:

```pycon
>>> "Ali" in User.name
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: A field query is not iterable ...

```

For a substring, use `.search()` (a regular expression, matched anywhere in the value) or `.test()` with a predicate:

```pycon
>>> [user.name for user in User.search(User.name.search("Ali"))]
['Alice']
>>> [user.name for user in User.search(User.name.test(lambda v: "Ali" in v))]
['Alice']

```

For a list field, `.any()` is the query that means "contains this element":

```pycon
>>> class Post(TinydanticModel, database=db, table_name="posts"):
...     title: str
...     tags: list[str] = []
>>> posts = Post.insert_many(
...     [
...         Post(title="Intro", tags=["python", "tinydb"]),
...         Post(title="Notes", tags=["docs"]),
...     ]
... )
>>> [post.title for post in Post.search(Post.tags.any(["python"]))]
['Intro']

```

Indexing a list field by position is refused too. A query path is a sequence of document _keys_, and TinyDB reads a non-string step as a function to call — so a positional index used to build a condition that quietly matched nothing:

```pycon
>>> Post.tags[0] == "python"
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: Query paths are document keys ...

```

```pycon
>>> matched = Post.search(Post.tags.test(lambda v: bool(v) and v[0] == "python"))
>>> [post.title for post in matched]
['Intro']

```

String keys are the supported form and are untouched — that is how [where()](https://tinydb.readthedocs.io/en/latest/usage.html#queries) reaches keys with spaces or dots.

### `Model.field` versus `instance.field`

Every case above comes from one root: **`User.name` is a query, `user.name` is a value.** The same expression means opposite things depending on what is left of the dot.

```pycon
>>> alice.name == "Alice"
True
>>> User.name == "Alice"  # doctest: +ELLIPSIS
QueryImpl('==', ('name',), 'Alice')

```

The distinction bites hardest when filtering documents you have already loaded — a class-level condition in a comprehension used to filter nothing:

```pycon
>>> [user.name for user in User.all() if User.age > 30]
Traceback (most recent call last):
  ...
tinydantic._errors.QueryTypeError: A query condition has no truth value ...
>>> [user.name for user in User.all() if user.age > 30]
['Carol']

```

Conditions belong in the query methods, which run them against storage. Once you hold instances, compare their attributes.

> [!NOTE]
>
> The guards live on the query objects tinydantic hands out — `Model.field`, [q()][tinydantic.q], [field()][tinydantic.field], `Model.id`, and anything composed from them. A raw `tinydb.Query()` built yourself is an ordinary TinyDB object and keeps TinyDB's behavior, so `bool(Query().name == "Alice")` is still silently `True`.

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
>>> commands = Command.insert_many(
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

That `False` is silently wrong: no error, no match, forever. It is also where [q()][tinydantic.q] earns its keep for a reason that has nothing to do with type checkers — handed a method instead of a Query, it raises rather than shrugging:

```pycon
>>> q(Command.search)  # doctest: -IGNORE_EXCEPTION_DETAIL
Traceback (most recent call last):
  ...
TypeError: q() expected a TinyDB Query from class-level field access like Model.field,
got 'method'. That resolves to a method, not a field, so the comparison is a plain
False matching nothing. Reach the field by name: field(Command, 'search').

```

The advice names the exact call to make: `q()` recovers both the attribute's name and the class it was reached through, so it can point at the field rather than describe it.

Reach the opted-in field by name with [field()][tinydantic.field], which builds a query on that document key:

```pycon
>>> Command.search(field(Command, "search") == "fuzzy")
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
> Pydantic also warns about shadowed fields at class definition (`Field name "search" ... shadows an attribute`). For a deliberate opt-in, silence it with `warnings.filterwarnings("ignore", message=r'Field name "search"')` — or treat the warning as a reminder that `field(Command, "search")` is the only query path for that field.

## Fluent queries

Every condition on this page — `Model.field` sugar, [q()][tinydantic.q], [field()][tinydantic.field], raw TinyDB queries, `Model.id` conditions — plugs directly into [find()][tinydantic.TinydanticModel.find], which adds sorting, pagination, and lazy, reusable query chains on top. See [Fluent queries](find.md).
