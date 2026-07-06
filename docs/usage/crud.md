# CRUD tour

This page walks through every create, read, update, and delete method on [TinydanticModel][tinydantic.TinydanticModel]. It doubles as a reference: each method appears in a runnable example, and the three sharp edges worth memorizing are called out along the way.

We use an in-memory database and a `Book` model throughout. The examples share state top to bottom, so run them in order.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> db = TinyDB(storage=MemoryStorage)
>>> from tinydantic import TinydanticModel
>>> class Book(TinydanticModel, database=db, table_name='books'):
...     title: str
...     author: str
...     year: int
...     in_stock: bool = True

```

## Create

### `insert`

[insert()][tinydantic.TinydanticModel.insert] stores a single model and returns it with `id` populated.

```pycon
>>> Book(title='Dune', author='Herbert', year=1965).insert()
Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True)

```

### `insert_multiple`

[insert_multiple()][tinydantic.TinydanticModel.insert_multiple] stores several models in one call and returns the assigned ids in insertion order. The passed-in instances are _not_ mutated — use the returned ids (or re-read) if you need them.

```pycon
>>> Book.insert_multiple([
...     Book(title='Neuromancer', author='Gibson', year=1984),
...     Book(title='Snow Crash', author='Stephenson', year=1992),
... ])
[2, 3]

```

### `upsert`

[upsert()][tinydantic.TinydanticModel.upsert] updates every document matching a condition, or inserts the document if nothing matches. Either way it returns the affected ids. The first call below inserts (no `Hyperion` exists yet); the second updates the same document.

```pycon
>>> Book.upsert(Book(title='Hyperion', author='Simmons', year=1989), Book.title == 'Hyperion')
[4]
>>> Book.upsert(Book(title='Hyperion', author='Dan Simmons', year=1989), Book.title == 'Hyperion')
[4]

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
>>> Book.get(Book.title == 'Dune')
Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True)

```

By document id:

```pycon
>>> Book.get(doc_id=2)
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
>>> Book.get_by_cond(Book.author == 'Gibson')
Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=True)
>>> Book.get_by_id(4)
Book(id=4, title='Hyperion', author='Dan Simmons', year=1989, in_stock=True)
>>> Book.get_by_ids([1, 3])
[Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=True),
  Book(id=3, title='Snow Crash', author='Stephenson', year=1992, in_stock=True)]

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
>>> Book.contains(Book.title == 'Dune')
True
>>> Book.contains(doc_id=999)
False

```

### `count`

[count()][tinydantic.TinydanticModel.count] returns the number of documents matching a condition.

```pycon
>>> Book.count(Book.in_stock == True)
4

```

## Update

### `save`

[save()][tinydantic.TinydanticModel.save] persists an instance: it inserts when `id` is unset and updates in place otherwise. Mutate the model, then save.

```pycon
>>> dune = Book.get(Book.title == 'Dune')
>>> dune.in_stock = False
>>> dune.save()
Book(id=1, title='Dune', author='Herbert', year=1965, in_stock=False)

```

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
>>> Book.update({'in_stock': False}, Book.author == 'Gibson')
[2]
>>> Book.get_by_id(2)
Book(id=2, title='Neuromancer', author='Gibson', year=1984, in_stock=False)

```

A transform callable mutates each matched document in place:

```pycon
>>> def bump_year(doc):
...     doc['year'] += 1
>>> Book.update(bump_year, Book.title == 'Snow Crash')
[3]
>>> Book.get_by_id(3)
Book(id=3, title='Snow Crash', author='Stephenson', year=1993, in_stock=True)

```

### `update_multiple`

[update_multiple()][tinydantic.TinydanticModel.update_multiple] applies several `(fields, cond)` updates in one call and returns all updated ids.

```pycon
>>> Book.update_multiple([
...     ({'in_stock': True}, Book.title == 'Dune'),
...     ({'in_stock': True}, Book.author == 'Gibson'),
... ])
[1, 2]

```

> [!WARNING]
>
> **`update()` and `update_multiple()` do NOT serialize values through Pydantic.** Unlike `insert()`, `save()`, and `upsert()`, the fields you pass are written to storage exactly as given. A plain `bool`, `int`, or `str` is fine, but a rich type such as `datetime` is stored as a raw Python object instead of the JSON-safe string the model would normally produce — which will not round-trip through JSON storage. Pass JSON-safe primitives yourself (for example `datetime.isoformat()` strings), or use an instance's `save()`/`replace()` for full-model updates.

To see the difference, compare the raw stored document after an `insert()` with the raw document after an `update()`. First, `insert()` serializes the `datetime` to a JSON-safe string:

```pycon
>>> import datetime
>>> class Event(TinydanticModel, database=db, table_name='events'):
...     name: str
...     when: datetime.datetime
>>> Event(name='launch', when=datetime.datetime(2026, 1, 1, 12, 0)).insert()
Event(id=1, name='launch', when=datetime.datetime(2026, 1, 1, 12, 0))
>>> db.table('events').get(doc_id=1)
{'name': 'launch', 'when': '2026-01-01T12:00:00'}

```

But `update()` writes the raw `datetime` object straight into storage:

```pycon
>>> Event.update({'when': datetime.datetime(2027, 1, 1, 12, 0)}, Event.name == 'launch')
[1]
>>> db.table('events').get(doc_id=1)
{'name': 'launch', 'when': datetime.datetime(2027, 1, 1, 12, 0)}

```

Passing the JSON-safe string yourself keeps storage consistent:

```pycon
>>> Event.update({'when': datetime.datetime(2027, 1, 1, 12, 0).isoformat()}, Event.name == 'launch')
[1]
>>> db.table('events').get(doc_id=1)
{'name': 'launch', 'when': '2027-01-01T12:00:00'}

```

## Delete

### `delete`

[delete()][tinydantic.TinydanticModel.delete] removes the instance's document from the table. It returns nothing; querying afterwards finds nothing.

```pycon
>>> snow = Book.get(Book.title == 'Snow Crash')
>>> snow.delete()
>>> print(Book.get(Book.title == 'Snow Crash'))
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
>>> class Note(TinydanticModel, database=db, table_name='notes'):
...     text: str
>>> note = Note(text='draft').insert()
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
tinydantic._errors.DocumentNotFoundError: Document not found

```

> [!WARNING]
>
> **`save()` re-inserts a vanished document; `replace()` and `delete()` raise.** Reach for `save()` when you want idempotent "make storage match this instance" semantics, and for `replace()`/`delete()` when a missing document is a genuine error you want to hear about.
