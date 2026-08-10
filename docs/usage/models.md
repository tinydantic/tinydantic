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

### Cross-field validators and mutate-then-save

`validate_assignment` re-runs your `model_validator(mode="after")` on **every** attribute assignment. For a model with an invariant spanning two fields, that makes the ordinary mutate-then-save flow impossible to complete one field at a time — the _intermediate_ state is invalid even when the destination is fine:

```pycon
>>> from pydantic import model_validator
>>> class Booking(TinydanticModel, database=db, table_name="bookings"):
...     start: int
...     end: int
...
...     @model_validator(mode="after")
...     def _ends_after_start(self):
...         if self.start >= self.end:
...             msg = "start must be before end"
...             raise ValueError(msg)
...         return self
>>> booking = Booking(start=1, end=5).insert()
>>> booking.start = 10  # 10..5 is invalid, though 10..20 would not be
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for Booking
  ...

```

Move both fields in one step instead. [patch()][tinydantic.TinydanticModel.patch] applies the whole mapping and validates the result once:

```pycon
>>> booking = booking.patch(start=10, end=20)
>>> (booking.start, booking.end)
(10, 20)

```

[model_copy(update=...)][pydantic.BaseModel.model_copy] followed by `save()` works the same way, and a model that genuinely wants unchecked assignment can opt out with `model_config = ConfigDict(validate_assignment=False)` — at the cost of the guarantee described above. Whole-model writes still validate, so an instance corrupted by assignment is refused at the storage boundary rather than persisted.

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

## Field aliases

Pydantic [aliases](https://docs.pydantic.dev/latest/concepts/alias/) give a field a different external name — the classic case is a camelCase wire format for a snake_case model, often model-wide via an `alias_generator`. Aliased models work with tinydantic out of the box, under one policy: **storage keys are always Python field names; aliases exist only at your external boundary.**

```pycon
>>> from pydantic import ConfigDict
>>> from pydantic.alias_generators import to_camel
>>> class Profile(TinydanticModel, database=db, table_name="profiles"):
...     model_config = ConfigDict(alias_generator=to_camel)
...     first_name: str
...     home_city: str
>>> profile = Profile(firstName="Ada", homeCity="London").insert()
>>> Profile.get_table().get(doc_id=profile.id)
{'first_name': 'Ada', 'home_city': 'London'}

```

Field-name keys are what keep the [query sugar](queries.md) coherent — `Profile.first_name` builds a query on the `"first_name"` key, which is exactly what storage holds:

```pycon
>>> Profile.search(Profile.first_name == "Ada")
[Profile(id=1, first_name='Ada', home_city='London')]

```

Meanwhile your wire format is untouched — serialize with `by_alias=True` as usual:

```pycon
>>> profile.model_dump(by_alias=True)
{'id': 1, 'firstName': 'Ada', 'homeCity': 'London'}

```

Under the hood, tinydantic validates with `by_name=True` at its own storage boundaries (reads, write checks, and merged update results), so stored field-name keys always validate — no `validate_by_name` needed in your model config. Aliases still apply everywhere _you_ talk to the model: construction and `model_validate` follow your model's own alias rules, exactly as in plain pydantic.

The same policy governs querying by name: [field()][tinydantic.field] takes Python field names and refuses aliases, rather than translating them.

```pycon
>>> from tinydantic import field
>>> field(Profile, "firstName")
Traceback (most recent call last):
  ...
tinydantic._errors.QueryFieldError: 'firstName' is not a queryable field of 'Profile'. Names are Python field names (not storage aliases); queryable fields: ['first_name', 'home_city']. For keys your model does not declare (extra='allow' documents, legacy keys), use tinydb.where('firstName').

```

## Lifecycle hooks

Two overridable no-op methods mark the storage boundary. [before_write()][tinydantic.TinydanticModel.before_write] runs once at the start of every instance-level write — `insert()`, each document of `insert_multiple()`, `save()`, `replace()`, `upsert()`, and `patch()`. It receives `fields`, the model-field mapping about to be written, and **returns** the fields it wants to add or override. The classic use is audit timestamps:

```pycon
>>> import datetime
>>> class Note(TinydanticModel, database=db, table_name="notes"):
...     text: str
...     created_at: datetime.datetime | None = None
...     updated_at: datetime.datetime | None = None
...
...     def before_write(self, fields):
...         """Stamp audit timestamps."""
...         now = datetime.datetime.now(tz=datetime.timezone.utc)
...         if self.id is None:
...             return {"created_at": now, "updated_at": now}
...         return {"updated_at": now}
>>> note = Note(text="draft").insert()
>>> note.created_at == note.updated_at
True

```

Returned values are validated like any other write, persisted, and set on the instance. Returning `None` contributes nothing.

!!! warning "Return your fields — never assign to `self`"

    Assigning to `self` inside `before_write()` happens to work on whole-model writes, because they serialize from the instance. `patch()` writes **only** the fields it was given, so anything you set on `self` there is silently dropped. Always return the mapping.

`fields` holds every model field on a whole-model write and only the caller's fields on `patch()`; it never contains `id` or `revision_id`, and returning either of those raises. Because the hook is instance-level, the table-level [update()][tinydantic.TinydanticModel.update] and [update_all()][tinydantic.TinydanticModel.update_all] do **not** fire it — they write by condition, with no model instance to hook. A mass write will not bump your `updated_at`:

```pycon
>>> _ = Note.update({"updated_at": None}, doc_ids=[note.id])
>>> Note.get_by_id(note.id).updated_at is None  # update(): no hook
True
>>> _ = note.patch(text="final")
>>> Note.get_by_id(note.id).updated_at is None  # patch(): hook fired
False

```

[after_read()][tinydantic.TinydanticModel.after_read] runs after a stored document is validated into an instance — on every materializing read, with the real `id` set. Changes made there affect only the in-memory instance; reads never write. A sketch:

```python
class Session(TinydanticModel, database=db):
    token: str

    def after_read(self) -> None:
        """Track which sessions this process touched."""
        SEEN_SESSION_IDS.add(self.id)
```

Two more rules worth remembering: a raising hook **aborts the write** with nothing written, and hooks are ordinary methods, so mixins can cooperate via `super().before_write(fields)`. Prefer hooks over `model_validator` for side effects: validators also fire on construction, on every read, and on every assignment — a timestamp bumped there is stamped by reads too.

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
- Enforcement costs a table scan. TinyDB has no indexes, so an enforcing write reads the whole table and compares it document by document — O(documents), on top of the read the write itself performs. `insert_multiple()` scans once for the entire batch rather than once per document, so a bulk load stays linear in the batch size; a loop of `insert()` calls does not. If a single write is slow, the table has outgrown what TinyDB is for.

## Composite constraints

Uniqueness over _several_ fields — a join model's pair, a slug per author — is a property of the model, not of any single field, so it is declared with [UniqueConstraint][tinydantic.UniqueConstraint] through the `constraints=` class keyword (a [TinydanticConfig][tinydantic.TinydanticConfig] key) rather than a field annotation:

```pycon
>>> from tinydantic import UniqueConstraint
>>> class Follow(
...     TinydanticModel,
...     database=db,
...     table_name="follows",
...     constraints=(UniqueConstraint("follower_id", "followee_id"),),
... ):
...     follower_id: int
...     followee_id: int
>>> Follow(follower_id=3, followee_id=7).insert()
Follow(id=1, follower_id=3, followee_id=7)
>>> Follow(follower_id=3, followee_id=8).insert()
Follow(id=2, follower_id=3, followee_id=8)
>>> Follow(follower_id=3, followee_id=7).insert()
Traceback (most recent call last):
  ...
tinydantic._errors.UniqueConstraintError: Values (3, 7) for unique fields ('follower_id', 'followee_id') already exist ...

```

### Normalized uniqueness with `key=`

A constraint may carry a `key=` callable — the Python analog of an expression-based unique index (Django's `UniqueConstraint(Lower("username"))`). Uniqueness is then enforced on `key(*values)` instead of the raw values, while the **stored values stay untouched** — this is how you keep `"Chris"` for display while rejecting a second `"chris"`:

```pycon
>>> class Handle(
...     TinydanticModel,
...     database=db,
...     table_name="handles",
...     constraints=(
...         UniqueConstraint(
...             "name",
...             "org_id",
...             key=lambda name, org_id: (name.casefold(), org_id),
...         ),
...     ),
... ):
...     name: str
...     org_id: int
>>> Handle(name="Chris", org_id=7).insert()
Handle(id=1, name='Chris', org_id=7)
>>> Handle(name="chris", org_id=7).insert()
Traceback (most recent call last):
  ...
tinydantic._errors.UniqueConstraintError: Values ('chris', 7) for unique fields ('name', 'org_id') already exist (comparison key ('chris', 7)) in table 'handles' ...

```

The single-field marker takes the same parameter — `email: Annotated[str, Unique(key=str.casefold)]` — and `UniqueConstraint("email")` with one field is exactly equivalent to a `Unique()` marker, so you can declare everything in one place if you prefer.

The `key=` contract:

- The callable receives the constraint's **serialized** field values (what storage holds — a `datetime` arrives as an ISO-format string), positionally, in declared field order, and must return a hashable result. Sorting-adjacent recipes follow from this — one entry per user per calendar _day_: `key=lambda uid, ts: (uid, ts[:10])`.
- It must be pure and deterministic — this is documented, not policed; an impure key silently breaks enforcement, and an exception it raises propagates as-is.
- It is never called with `None`: a constraint participates in a check only when **all** of its fields are non-`None` (the composite generalization of SQL's `NULL` under `UNIQUE`), and exempt rows skip the key entirely.
- Case-insensitivity across every string member is `key=lambda *vs: tuple(v.casefold() if isinstance(v, str) else v for v in vs)`. When canonical storage is acceptable (emails, slugs), prefer normalizing at the boundary instead — `Annotated[str, StringConstraints(to_lower=True), Unique()]` stores the lowercased value and needs no key.
- When a key produced the match, the error message shows the computed comparison key alongside the raw values, so a normalized clash (candidate `'chris'` vs stored `'Chris'`) never looks like a phantom collision.

The rest of the single-field contract carries over unchanged: same write-path coverage, same `update()`/`update_all()`/`update_multiple()` bypass, same in-process check-then-write scope. Two more rules specific to declarations:

- Constraints resolve like every other config key — nearest class in the MRO wins, so a subclass's `constraints=` **replaces** its parent's — and merge with `Unique()` markers. Exact duplicates (same field _set_, same `key` callable or both key-less) collapse to one; the same field set with _different_ keys is legal and every constraint must hold — declaring both `UniqueConstraint("v")` and `UniqueConstraint("v", key=str.casefold)` enforces exact **and** case-insensitive uniqueness.
- A constraint naming a non-field or `id` raises [ConstraintFieldError][tinydantic.ConstraintFieldError] at class definition (or `bind()`) time. Both would otherwise be silent: an unknown field reads as `None` in every body and never enforces, and `id` is never stored in the document body at all — ids are unique already.

## Where next

- [Queries](queries.md) — build query conditions from model fields, including nested ones.
- [Schema evolution](schema-evolution.md) — what happens when stored documents predate the current model, and how to migrate.
- [Storage](storage.md) — choose a backend and persist your documents to disk.
- [Configuration](configuration.md) — bind models to a database and table, and how config resolves across a class hierarchy.
