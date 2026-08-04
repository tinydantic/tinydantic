# CRUD tour

This page walks through every create, read, update, and delete method on [TinydanticModel][tinydantic.TinydanticModel]. It doubles as a reference: each method appears in a runnable example, and the sharp edges worth memorizing are called out along the way.

We use an in-memory database and a `Book` model throughout. The examples share state top to bottom, so run them in order.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> db = TinyDB(storage=MemoryStorage)
>>> from tinydantic import TinydanticModel
>>> class Book(TinydanticModel, database=db, table_name="books"):
...     title: str
...     author: str
...     year: int
...     in_stock: bool = True

```

## Create

### `insert`

[insert()][tinydantic.TinydanticModel.insert] stores a single model and returns it with `id` populated.

```pycon
>>> Book(title="Dune", author="Herbert", year=1965).insert()
Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True)

```

### `insert_multiple`

[insert_multiple()][tinydantic.TinydanticModel.insert_multiple] stores several models in one call. Exactly like `insert()`, each passed-in model gets its assigned `id` set in place, and the same instances come back in insertion order.

```pycon
>>> Book.insert_multiple(
...     [
...         Book(title="Neuromancer", author="Gibson", year=1984),
...         Book(title="Snow Crash", author="Stephenson", year=1992),
...     ]
... )
[Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=True),
  Book(id=3, title='Snow Crash', author='Stephenson', year=1992, in_stock=True)]

```

### `upsert`

[upsert()][tinydantic.TinydanticModel.upsert] updates every document matching a condition, or inserts the document if nothing matches. Either way it returns the affected ids — and when exactly one document is affected, it also sets the passed instance's `id` in place, just like [insert()][tinydantic.TinydanticModel.insert]. (When several documents match, linking the instance to any one of them would be arbitrary, so `id` is left untouched.) The first call below inserts (no `Hyperion` exists yet); the second updates the same document and links the instance to it:

```pycon
>>> Book.upsert(
...     Book(title="Hyperion", author="Simmons", year=1989),
...     Book.title == "Hyperion",
... )
[4]
>>> hyperion = Book(title="Hyperion", author="Dan Simmons", year=1989)
>>> Book.upsert(hyperion, Book.title == "Hyperion")
[4]
>>> hyperion.id
4

```

## Read

The table now holds four books. Read methods return validated model instances with `id` set from the stored document id.

### `all`

[all()][tinydantic.TinydanticModel.all] returns every document as a list of models.

```pycon
>>> Book.all()
[Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True),
  Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=True),
  Book(id=3, title='Snow Crash', author='Stephenson', year=1992, in_stock=True),
  Book(id=4, title='Hyperion', author='Dan Simmons', year=1989, in_stock=True)]

```

### `get`

[get()][tinydantic.TinydanticModel.get] fetches a single document. It accepts a query condition, a `doc_id=`, or a `doc_ids=` list — but at most one of the three (passing more than one raises `ValueError`).

By condition:

```pycon
>>> Book.get(Book.title == "Dune")
Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True)

```

By document id:

```pycon
>>> Book.get(doc_id=2)
Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=True)

```

Because `id` maps to the document id, a condition on `Book.id` is a document-id lookup — `Book.get(Book.id == 2)` and `Book.get(doc_id=2)` are equivalent (see [Queries](queries.md)):

```pycon
>>> Book.get(Book.id == 2)
Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=True)

```

By a list of document ids — this returns a `list`:

```pycon
>>> Book.get(doc_ids=[3, 1, 999])
[Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True),
  Book(id=3, title='Snow Crash', author='Stephenson', year=1992, in_stock=True)]

```

> [!WARNING]
>
> **`doc_ids` skips missing ids and ignores your ordering.** We asked for `[3, 1, 999]` and got documents `1` and `3` back, in storage order — not `[3, 1]`. The nonexistent id `999` was silently dropped, so the result can be shorter than the list you passed. Never assume the returned order matches your input or that every id produced a document. If you need results in a specific order, sort them yourself after reading.

### `get_by_cond`, `get_by_id`, `get_by_ids`

These are precisely typed aliases for the three `get()` call shapes. Use them when you want a static type checker to know exactly what comes back.

```pycon
>>> Book.get_by_cond(Book.author == "Gibson")
Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=True)
>>> Book.get_by_id(4)
Book(id=4, title='Hyperion', author='Dan Simmons', year=1989, in_stock=True)
>>> Book.get_by_ids([1, 3])
[Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True),
  Book(id=3, title='Snow Crash', author='Stephenson', year=1992, in_stock=True)]

```

### `get_or_raise`

[get_or_raise()][tinydantic.TinydanticModel.get_or_raise] is the strict counterpart to `get()`: where a missing document would return `None`, it raises [DocumentNotFoundError][tinydantic.DocumentNotFoundError] instead. Reach for it when a missing document is a bug (or a 404), not an expected outcome. It accepts exactly one selector — a condition or a `doc_id=`.

```pycon
>>> Book.get_or_raise(Book.title == "Dune")
Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True)
>>> Book.get_or_raise(doc_id=999)
Traceback (most recent call last):
  ...
tinydantic._errors.DocumentNotFoundError: No document with id 999 in table 'books' (model 'Book')

```

### `search`

[search()][tinydantic.TinydanticModel.search] returns _all_ documents matching a condition.

```pycon
>>> Book.search(Book.year > 1985)
[Book(id=3, title='Snow Crash', author='Stephenson', year=1992, in_stock=True),
  Book(id=4, title='Hyperion', author='Dan Simmons', year=1989, in_stock=True)]

```

### `contains`

[contains()][tinydantic.TinydanticModel.contains] reports whether any matching document exists, by condition or by `doc_id=`.

```pycon
>>> Book.contains(Book.title == "Dune")
True
>>> Book.contains(doc_id=999)
False

```

### `count`

[count()][tinydantic.TinydanticModel.count] returns the number of documents matching a condition — or, called with no arguments, the total number of documents in the table.

```pycon
>>> Book.count(Book.in_stock == True)
4
>>> Book.count()
4

```

## Update

### `save`

[save()][tinydantic.TinydanticModel.save] persists an instance: it inserts when `id` is unset and updates in place otherwise. Mutate the model, then save.

```pycon
>>> dune = Book.get(Book.title == "Dune")
>>> dune.in_stock = False
>>> dune.save()
Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=False)

```

Mutate-then-save is guarded at both ends. Assignment itself is validated (`validate_assignment` is on for every tinydantic model), so the mutate step refuses an invalid value at the offending line:

```pycon
>>> dune.year = "not a year"
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for Book
  ...

```

And `save()` re-validates the full serialized document before writing — the same check the next read performs — so corruption that assignment validation cannot see (appending a bad value into a list field, mutating a nested model in place) is refused at the write boundary instead of poisoning the table:

```pycon
>>> object.__setattr__(
...     dune, "year", "still not a year"
... )  # bypasses assignment validation
>>> dune.save()
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for Book
  ...
>>> dune.year = 1965  # repair the instance; storage was never touched
>>> Book.get_by_id(1).year
1965

```

Every whole-model write path (`insert()`, `save()`, `replace()`, `upsert()`) shares this boundary check. Models can opt out with the `validate_writes=False` class kwarg — the escape hatch for performance-critical bulk writes; see [Configuration](configuration.md).

### `replace`

[replace()][tinydantic.TinydanticModel.replace] overwrites the entire stored document with the instance's current state — fields absent from the model are removed. It returns nothing and requires an existing document.

```pycon
>>> dune.year = 1966
>>> dune.replace()
>>> Book.get_by_id(1)
Book(id=1, title='Dune', author='Herbert', year=1966, in_stock=False)

```

### `update`

[update()][tinydantic.TinydanticModel.update] merges a fields mapping (or applies a transform callable) into every document matching a condition, and returns the updated ids.

```pycon
>>> Book.update({"in_stock": False}, Book.author == "Gibson")
[2]
>>> Book.get_by_id(2)
Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=False)

```

A transform callable mutates each matched document in place:

```pycon
>>> def bump_year(doc):
...     doc["year"] += 1
>>> Book.update(bump_year, Book.title == "Snow Crash")
[3]
>>> Book.get_by_id(3)
Book(id=3, title='Snow Crash', author='Stephenson', year=1993, in_stock=True)

```

Update mappings cannot set `id` — it maps to TinyDB's `doc_id`, which an update cannot change. Trying raises [DocumentIDUpdateError][tinydantic.DocumentIDUpdateError]:

```pycon
>>> Book.update({"id": 99}, Book.title == "Dune")
Traceback (most recent call last):
  ...
tinydantic._errors.DocumentIDUpdateError: update() cannot set 'id'

```

`update()` requires exactly one selector — a condition or explicit `doc_ids=`. TinyDB's own `update()` treats a bare call as "update every document" and silently prefers `doc_ids` when both are given; tinydantic raises [SelectorError][tinydantic.SelectorError] in both cases, so a dropped condition can never quietly rewrite the whole table:

```pycon
>>> Book.update({"in_stock": False})
Traceback (most recent call last):
  ...
tinydantic._errors.SelectorError: update() needs a selector ...

```

### `update_all`

Updating every document is spelled [update_all()][tinydantic.TinydanticModel.update_all] — the same split `remove()` and `truncate()` make for deletion. A distinct verb keeps mass writes greppable and impossible to reach by accident:

```pycon
>>> Book.update_all({"in_stock": True})
[1, 2, 3, 4]

```

Mappings and transform callables get exactly the treatment `update()` gives them — per-value validation, merged-result validation, atomic all-or-nothing writes, and the same `extra_keys=` escape (all described below).

### `update_multiple`

[update_multiple()][tinydantic.TinydanticModel.update_multiple] applies several `(fields, cond)` updates in one call and returns all updated ids.

```pycon
>>> Book.update_multiple(
...     [
...         ({"in_stock": True}, Book.title == "Dune"),
...         ({"in_stock": True}, Book.author == "Gibson"),
...     ]
... )
[1, 2]

```

Pairs may use conditions on `Book.id` (see [Queries](queries.md)) and mix them freely with field conditions — the whole batch still runs as one atomic write:

```pycon
>>> Book.update_multiple(
...     [
...         ({"in_stock": False}, Book.id == 1),
...     ]
... )
[1]

```

Field values in the mapping get the same treatment `insert()` and `save()` give whole models: each value is validated against its field's type and serialized to a JSON-safe primitive before it reaches storage. A rich value such as a `datetime` lands in storage as the same ISO string an `insert()` would have written:

```pycon
>>> import datetime
>>> class Event(TinydanticModel, database=db, table_name="events"):
...     name: str
...     when: datetime.datetime
>>> Event(name="launch", when=datetime.datetime(2026, 1, 1, 12, 0)).insert()
Event(id=1, name='launch', when=datetime.datetime(2026, 1, 1, 12, 0))
>>> Event.update(
...     {"when": datetime.datetime(2027, 1, 1, 12, 0)}, Event.name == "launch"
... )
[1]
>>> db.table("events").get(doc_id=1)
{'name': 'launch', 'when': '2027-01-01T12:00:00'}

```

And because values are validated, an update that would corrupt a field refuses to run:

```pycon
>>> Event.update({"when": "not a datetime"}, Event.name == "launch")
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for datetime
  Input should be a valid datetime or date, invalid character in year [type=datetime_from_date_parsing, input_value='not a datetime', input_type=str]
  ...

```

Validation goes further than single values: each matched document's _merged result_ — the stored body plus your new fields, or a transform callable's output — is validated as a whole document (with the real document id visible to `model_validator(mode="after")` hooks) before anything is written. A batch is all-or-nothing: if any matched document's merge fails validation, nothing is written. So cross-field invariants hold through partial updates, and a transform that writes junk is refused too:

```pycon
>>> def corrupt(doc):
...     doc["year"] = "junk"
>>> Book.update(corrupt, Book.title == "Dune")
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for Book
  ...

```

Mapping keys that are not model fields are rejected — they would bypass validation entirely — with a per-call escape hatch for databases shared with other tools or schema-evolution keys this model does not know yet:

```pycon
>>> Book.update({"shelf": "A3"}, Book.title == "Dune")
Traceback (most recent call last):
  ...
tinydantic._errors.UnknownUpdateFieldError: update() mapping for 'Book' ...
>>> Book.update({"shelf": "A3"}, Book.title == "Dune", extra_keys="allow")
[1]

```

> [!NOTE]
>
> Keys written via `extra_keys="allow"` are stored **unvalidated** (pydantic ignores keys it does not know), and stored extra keys are likewise ignored — but preserved — when updates validate merged documents. Models can opt out of merged-result validation entirely with the `validate_writes=False` class kwarg; per-field value validation (the `datetime` example above) always applies to mappings. `update()`, `update_all()`, and `update_multiple()` also do **not** enforce [unique fields](models.md#unique-fields) — they are the deliberate loose path; every other write verb checks uniqueness.

### `patch`

[patch()][tinydantic.TinydanticModel.patch] is the instance-level partial update: it validates the given fields, writes **only those fields** to the stored document, and updates the instance to match — one call, no drift between object and storage.

```pycon
>>> neuromancer = Book.get_by_id(2)
>>> neuromancer.patch(year=1985)
Book(id=2, title='Neuromancer', author='Gibson', year=1985, in_stock=True)

```

Because only the named fields are written, `patch()` avoids the lost-update trap that whole-document `save()` leaves open: a stale copy patching one field cannot clobber another writer's change to a different field.

```pycon
>>> stale_copy = Book.get_by_id(2)
>>> stale_copy.patch(in_stock=False)  # holds year=1985 already
Book(id=2, title='Neuromancer', author='Gibson', year=1985, in_stock=False)
>>> Book.get_by_id(2)  # both changes survived in storage
Book(id=2, title='Neuromancer', author='Gibson', year=1985, in_stock=False)

```

`patch()` is strict: it requires a persisted instance, the document must still exist, and only model fields are accepted (there is no `extra_keys=` escape at instance level — use [update][tinydantic.TinydanticModel.update] for non-model keys):

```pycon
>>> Book(title="Ghost", author="X", year=2000).patch(year=2001)
Traceback (most recent call last):
  ...
tinydantic._errors.DocumentIDRequiredError: Cannot patch() ...
>>> neuromancer.patch(shelf="B2")
Traceback (most recent call last):
  ...
tinydantic._errors.UnknownUpdateFieldError: update() mapping ...

```

An empty `patch()` writes nothing but still verifies the document exists, so its error behavior does not depend on the payload — handy for HTTP PATCH endpoints fed `model_dump(exclude_unset=True)`.

### Choosing a write verb

Five verbs, five different contracts — in HTTP terms:

| Verb | HTTP analogy | Writes | If the document vanished |
| --- | --- | --- | --- |
| [save()][tinydantic.TinydanticModel.save] | PUT | the whole instance | re-inserts under the same id |
| [replace()][tinydantic.TinydanticModel.replace] | PUT (strict) | the whole instance | raises `DocumentNotFoundError` |
| [patch()][tinydantic.TinydanticModel.patch] | PATCH | only the named fields | raises `DocumentNotFoundError` |
| [update()][tinydantic.TinydanticModel.update] | bulk UPDATE-WHERE | mapped fields of every match | not applicable (matches nothing) |
| [update_all()][tinydantic.TinydanticModel.update_all] | bulk UPDATE, no WHERE | mapped fields of every document | not applicable |

Reach for `patch()` when you mean "change these fields of this document" — it is the one verb whose write scope matches that intent, so concurrent changes to unrelated fields survive.

## Delete

### `delete`

[delete()][tinydantic.TinydanticModel.delete] removes the instance's document from the table. It returns nothing; querying afterwards finds nothing.

```pycon
>>> snow = Book.get(Book.title == "Snow Crash")
>>> snow.delete()
>>> print(Book.get(Book.title == "Snow Crash"))
None

```

### `remove`

[remove()][tinydantic.TinydanticModel.remove] deletes every document matching a condition (or a list of `doc_ids=`) and returns the removed ids.

```pycon
>>> Book.remove(Book.year < 1970)
[1]

```

### `truncate`

[truncate()][tinydantic.TinydanticModel.truncate] empties the table entirely and resets its id counter.

```pycon
>>> Book.truncate()
>>> Book.all()
[]

```

## Sharp edge: `save()` vs `replace()`/`delete()` on a vanished document

The last sharp edge is about what happens when an instance's document has disappeared from the table (for example, deleted by another process). [save()][tinydantic.TinydanticModel.save] and [replace()][tinydantic.TinydanticModel.replace]/[delete()][tinydantic.TinydanticModel.delete] behave differently.

`save()` is forgiving: if the document is gone, it re-inserts it under the same id.

```pycon
>>> class Note(TinydanticModel, database=db, table_name="notes"):
...     text: str
>>> note = Note(text="draft").insert()
>>> note
Note(id=1, text='draft')
>>> Note.remove(doc_ids=[note.id])  # the document vanishes out of band
[1]
>>> Note.all()
[]
>>> note.save()  # save re-inserts it
Note(id=1, text='draft')
>>> Note.all()
[Note(id=1, text='draft')]

```

`replace()` and `delete()` are strict: they require the document to still exist and raise when it does not.

```pycon
>>> Note.remove(doc_ids=[note.id])  # vanish it again
[1]
>>> note.delete()
Traceback (most recent call last):
  ...
tinydantic._errors.DocumentNotFoundError: No document with id 1 in table 'notes' (model 'Note')

```

> [!WARNING]
>
> **`save()` re-inserts a vanished document; `replace()` and `delete()` raise.** Reach for `save()` when you want idempotent "make storage match this instance" semantics, and for `replace()`/`delete()` when a missing document is a genuine error you want to hear about.
