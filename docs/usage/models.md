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
...     LOW = "low"
...     HIGH = "high"
>>> class Tag(BaseModel):
...     label: str
...     weight: int
>>> class Task(TinydanticModel, database=db, table_name="tasks"):
...     title: str
...     created: datetime.datetime
...     ref: uuid.UUID
...     priority: Priority
...     tags: list[Tag] = []

```

Insert an instance built from real Python objects:

```pycon
>>> Task(
...     title="Ship docs",
...     created=datetime.datetime(2026, 7, 5, 9, 30),
...     ref=uuid.UUID("12345678-1234-5678-1234-567812345678"),
...     priority=Priority.HIGH,
...     tags=[Tag(label="urgent", weight=5)],
... ).insert()
Task(id=1, title='Ship docs', created=datetime.datetime(2026, 7, 5, 9, 30), ref=UUID('12345678-1234-5678-1234-567812345678'), priority=<Priority.HIGH: 'high'>, tags=[Tag(label='urgent', weight=5)])

```

Fetch it back and the fields are the same typed values, not strings — Pydantic validates the stored primitives back into `datetime`, `UUID`, `Priority`, and `Tag` objects:

```pycon
>>> task = Task.get(Task.title == "Ship docs")
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
>>> class Account(TinydanticModel, database=db, table_name="accounts"):
...     email: str
...
...     @field_validator("email")
...     @classmethod
...     def _check_email(cls, value: str) -> str:
...         if "@" not in value:
...             raise ValueError("email must contain @")
...         return value

```

Constructing with a bad value raises before anything reaches storage:

```pycon
>>> Account(email="not-an-email")
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for Account
email
  Value error, email must contain @ ...

```

The same guard fires on the way _out_. Suppose a malformed document already exists in the table — written before the validator existed, or by another tool — with an `email` that has no `@`:

```pycon
>>> db.table("accounts").insert({"email": "broken"})
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
>
> Writes hold the same line: attribute assignment is validated (`validate_assignment` is on for every tinydantic model; subclasses can opt out in their own `model_config`), every whole-model write re-validates its serialized payload before it reaches storage, and `update()` validates each matched document's merged result — so an update that would corrupt a field refuses to run, and a document that would fail its next read is never written. The write-side checks can be switched off per model with the `validate_writes=False` class kwarg (see [Configuration](configuration.md)) when bulk-write performance matters more than the guarantee.

```pycon
>>> db.table("accounts").truncate()

```

## Defaults and `default_factory`

Ordinary Pydantic defaults and [default factories][pydantic.fields.Field] work as usual. Fields you omit are filled in at construction time and then stored:

```pycon
>>> from pydantic import Field
>>> class Session(TinydanticModel, database=db, table_name="sessions"):
...     user: str
...     token: uuid.UUID = Field(
...         default_factory=lambda: uuid.UUID(
...             "00000000-0000-0000-0000-000000000001"
...         ),
...     )
...     active: bool = True
>>> Session(user="alice").insert()
Session(id=1, user='alice', token=UUID('00000000-0000-0000-0000-000000000001'), active=True)

```

The defaults are persisted, so a later read returns the filled-in values:

```pycon
>>> Session.get(Session.user == "alice")
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

## Lifecycle hooks

Two overridable no-op methods mark the storage boundary. [before_save()][tinydantic.TinydanticModel.before_save] runs once at the start of every whole-model write (`insert()`, each document of `insert_multiple()`, `save()`, `replace()`, `upsert()`) — before serialization, so anything it sets is validated and persisted with the write. The classic use is audit timestamps:

```pycon
>>> import datetime
>>> class Note(TinydanticModel, database=db, table_name="notes"):
...     text: str
...     created_at: datetime.datetime | None = None
...     updated_at: datetime.datetime | None = None
...
...     def before_save(self) -> None:
...         """Stamp audit timestamps."""
...         now = datetime.datetime.now(tz=datetime.timezone.utc)
...         if self.id is None:
...             self.created_at = now
...         self.updated_at = now
>>> note = Note(text="draft").insert()
>>> note.created_at == note.updated_at
True
>>> note.text = "final"
>>> _ = note.save()
>>> note.updated_at >= note.created_at
True

```

[after_load()][tinydantic.TinydanticModel.after_load] runs after a stored document is validated into an instance — on every materializing read, with the real `id` set. Changes made there affect only the in-memory instance; reads never write. A sketch:

```python
class Session(TinydanticModel, database=db):
    token: str

    def after_load(self) -> None:
        """Track which sessions this process touched."""
        SEEN_SESSION_IDS.add(self.id)
```

Three rules worth remembering: field-level writes (`update()`, `patch()`) fire **neither** hook — they never write the whole model, so fields set in `before_save()` would be silently dropped; a raising hook **aborts the write** with nothing written; and hooks are ordinary methods, so mixins can cooperate via `super().before_save()`. Prefer hooks over `model_validator` for side effects: validators also fire on construction, on every read, and on every assignment — a timestamp bumped there is stamped by reads too.

## Unique fields

Mark a field with the [Unique][tinydantic.Unique] annotation and tinydantic refuses writes that would duplicate its value in the table:

```pycon
>>> from typing import Annotated
>>> from tinydantic import Unique, UniqueConstraintError
>>> class Member(TinydanticModel, database=db, table_name="members"):
...     email: Annotated[str, Unique()]
>>> Member(email="ada@example.com").insert()
Member(id=1, email='ada@example.com')
>>> Member(email="ada@example.com").insert()
Traceback (most recent call last):
  ...
tinydantic._errors.UniqueConstraintError: Value 'ada@example.com' for unique field 'email' ...

```

The contract, in full:

- Enforced on create-style and instance-level writes: `insert()`, `insert_multiple()` (including duplicates inside one batch), `save()`, `replace()`, `upsert()`, and `patch()`. A write that would clash raises [UniqueConstraintError][tinydantic.UniqueConstraintError] before anything reaches storage; rewriting a document's own value is never a clash.
- `None` values are exempt — several documents may all leave a unique field unset, mirroring SQL's `NULL` under `UNIQUE`.
- The table-level bulk path (`update()`/`update_all()`/`update_multiple()`) deliberately does **not** enforce uniqueness — it is the documented loose escape, like `extra_keys="allow"`.
- The check is check-then-write within one process. That is sound under tinydantic's documented single-process, serialized-writes scope, but it is not a database constraint: another process writing the same file concurrently can still create duplicates.

## Where next

- [Queries](queries.md) — build query conditions from model fields, including nested ones.
- [Storage](storage.md) — choose a backend and persist your documents to disk.
- [Configuration](configuration.md) — bind models to a database and table, and how config resolves across a class hierarchy.
