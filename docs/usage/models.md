# Models

A `tinydantic` document model is a full Pydantic model, so everything Pydantic offers — rich field types, validators, defaults, serialization — works unchanged. This page shows real-world models round-tripping through storage: `datetime`, `UUID`, enums, and nested models going in as Python objects and coming back out as the same typed values, plus validators, defaults, and a look at what actually lands in storage.

The examples share an in-memory database. Run them in order.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> db = TinyDB(storage=MemoryStorage)

```

## Rich field types round-trip

Declare fields with any JSON-serializable Pydantic type. Here a `Task` mixes a `datetime`, a `UUID`, an `Enum`, and a list of nested [pydantic.BaseModel][] instances.

```pycon
>>> import datetime
>>> import enum
>>> import uuid
>>> from pydantic import BaseModel
>>> from tinydantic import TinydanticModel
>>> class Priority(enum.Enum):
...     LOW = 'low'
...     HIGH = 'high'
>>> class Tag(BaseModel):
...     label: str
...     weight: int
>>> class Task(TinydanticModel, database=db, table_name='tasks'):
...     title: str
...     created: datetime.datetime
...     ref: uuid.UUID
...     priority: Priority
...     tags: list[Tag] = []

```

Insert an instance built from real Python objects:

```pycon
>>> Task(
...     title='Ship docs',
...     created=datetime.datetime(2026, 7, 5, 9, 30),
...     ref=uuid.UUID('12345678-1234-5678-1234-567812345678'),
...     priority=Priority.HIGH,
...     tags=[Tag(label='urgent', weight=5)],
... ).insert()
Task(id=1, title='Ship docs', created=datetime.datetime(2026, 7, 5, 9, 30), ref=UUID('12345678-1234-5678-1234-567812345678'), priority=<Priority.HIGH: 'high'>, tags=[Tag(label='urgent', weight=5)])

```

Fetch it back and the fields are the same typed values, not strings — Pydantic validates the stored primitives back into `datetime`, `UUID`, `Priority`, and `Tag` objects:

```pycon
>>> task = Task.get(Task.title == 'Ship docs')
>>> task.created
datetime.datetime(2026, 7, 5, 9, 30)
>>> task.ref
UUID('12345678-1234-5678-1234-567812345678')
>>> task.priority
<Priority.HIGH: 'high'>
>>> task.tags[0]
Tag(label='urgent', weight=5)

```

## Validators reject bad data — including on load

A [field_validator][pydantic.field_validator] runs both when you construct a model and when you read one from storage, so it guards the boundary in both directions. Consider an `Account` whose `email` must contain an `@`:

```pycon
>>> from pydantic import field_validator
>>> class Account(TinydanticModel, database=db, table_name='accounts'):
...     email: str
...
...     @field_validator('email')
...     @classmethod
...     def _check_email(cls, value: str) -> str:
...         if '@' not in value:
...             raise ValueError('email must contain @')
...         return value

```

Constructing with a bad value raises before anything reaches storage:

```pycon
>>> Account(email='not-an-email')
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for Account
email
  Value error, email must contain @ ...

```

The same guard fires on the way _out_. Suppose a malformed document already exists in the table — written before the validator existed, or by another tool — with an `email` that has no `@`:

```pycon
>>> db.table('accounts').insert({'email': 'broken'})
1
>>> Account.all()
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for Account
email
  Value error, email must contain @ ...

```

> [!TIP]
>
> Validation on load means a `tinydantic` read is a schema check, not just a fetch. Bad data surfaces as a loud [pydantic.ValidationError][pydantic_core.ValidationError] the moment you read it, rather than silently flowing into your application as an untyped dict.

```pycon
>>> db.table('accounts').truncate()

```

## Defaults and `default_factory`

Ordinary Pydantic defaults and [default factories][pydantic.fields.Field] work as usual. Fields you omit are filled in at construction time and then stored:

```pycon
>>> from pydantic import Field
>>> class Session(TinydanticModel, database=db, table_name='sessions'):
...     user: str
...     token: uuid.UUID = Field(
...         default_factory=lambda: uuid.UUID('00000000-0000-0000-0000-000000000001'),
...     )
...     active: bool = True
>>> Session(user='alice').insert()
Session(id=1, user='alice', token=UUID('00000000-0000-0000-0000-000000000001'), active=True)

```

The defaults are persisted, so a later read returns the filled-in values:

```pycon
>>> Session.get(Session.user == 'alice')
Session(id=1, user='alice', token=UUID('00000000-0000-0000-0000-000000000001'), active=True)

```

## What's actually stored

`tinydantic` serializes documents with `model_dump(mode="json", exclude={"id"})` before handing them to TinyDB. "JSON mode" means every rich type is reduced to a JSON-safe primitive — a `datetime` becomes an ISO 8601 string, a `UUID` becomes its string form, an `Enum` becomes its value, and nested models become plain dicts. Reach past `tinydantic` to the raw TinyDB table with [get_table()][tinydantic.TinydanticModel.get_table] to see it:

```pycon
>>> Task.get_table().get(doc_id=1)
{'title': 'Ship docs', 'created': '2026-07-05T09:30:00', 'ref': '12345678-1234-5678-1234-567812345678', 'priority': 'high', 'tags': [{'label': 'urgent', 'weight': 5}]}

```

This is the design that makes round-tripping work with _any_ TinyDB storage backend, including plain JSON files: nothing but JSON primitives ever reaches the storage layer, and [model_validate][pydantic.BaseModel.model_validate] reconstructs the rich types on the way back. The `id` field is deliberately absent from the stored body — it maps to TinyDB's own `doc_id` (see the [CRUD tour](crud.md) and [Configuration](configuration.md)).

> [!NOTE]
>
> Because storage only ever sees JSON primitives, any model that is JSON-serializable round-trips through `tinydantic` faithfully. A type Pydantic cannot serialize to JSON will raise when you try to insert it — surface it as a JSON-safe representation (or a custom serializer) instead.

## Where next

- [Queries](queries.md) — build query conditions from model fields, including nested ones.
- [Storage](storage.md) — choose a backend and persist your documents to disk.
- [Configuration](configuration.md) — bind models to a database and table, and how config resolves across a class hierarchy.
