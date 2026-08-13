# Storage

Every `tinydantic` model reads and writes through a [TinyDB](https://tinydb.readthedocs.io/en/latest/) database, and TinyDB's storage is pluggable: in-memory for tests, a JSON file for the common persistent case, YAML if you want human-editable data, and middlewares that wrap any of these. This page walks through each option and the lifecycle details — closing files, context managers — that matter once your data lives on disk.

## In-memory (tests and scratch work)

[MemoryStorage][tinydb.storages.MemoryStorage] keeps everything in a Python dict. Nothing is written to disk, so it is perfect for tests, examples, and throwaway experiments — and it is what every other page in this guide uses.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import TinydanticModel
>>> db = TinyDB(storage=MemoryStorage)
>>> class Note(TinydanticModel, database=db, table_name="notes"):
...     text: str
>>> Note(text="scratch").insert()
Note(id=1, text='scratch')

```

When the `db` goes out of scope the data is gone. For anything you want to keep, reach for a file-backed storage.

## JSON file (the default persistent store)

Passing a path to [TinyDB][tinydb.database.TinyDB] uses [JSONStorage][tinydb.storages.JSONStorage], which serializes the whole database to a JSON file. The examples below use a [tempfile.TemporaryDirectory][] so they clean up after themselves; in a real application you would use a fixed path such as `TinyDB('db.json')`.

```pycon
>>> import os
>>> import tempfile
>>> tmpdir = tempfile.TemporaryDirectory()
>>> path = os.path.join(tmpdir.name, "db.json")
>>> db = TinyDB(path)
>>> class Person(TinydanticModel, database=db, table_name="people"):
...     name: str
>>> Person(name="Ada").insert()
Person(id=1, name='Ada')

```

The document is now on disk as plain JSON — exactly the JSON-safe primitives `tinydantic` produces (see [Models](models.md)):

```pycon
>>> db.close()
>>> with open(path) as f:
...     print(f.read())
{"people": {"1": {"name": "Ada"}}}

```

### Closing file storages

A file-backed TinyDB holds an open file handle. Call [close()][tinydb.database.TinyDB.close] when you are done, or use TinyDB as a context manager so the file is closed for you. Data written earlier persists, so a fresh `TinyDB` on the same path reads it straight back — here rebinding the existing model with [bind()][tinydantic.TinydanticModel.bind] (see [Configuration](configuration.md)):

```pycon
>>> reopened = TinyDB(path)
>>> Person.bind(database=reopened)
>>> Person.all()
[Person(id=1, name='Ada')]
>>> reopened.close()
>>> tmpdir.cleanup()

```

> [!TIP]
>
> `TinyDB` supports the context-manager protocol: `with TinyDB('db.json') as db:` closes the file on exit. TinyDB flushes on every write, so an unclosed handle will not lose data — but closing it releases the OS file handle promptly, which matters for long-running processes and on Windows, where an open handle blocks other openers.

## YAML files

`tinydantic` ships a [YAMLStorage][tinydantic.tinydb.storages.YAMLStorage] for human-editable, diff-friendly data. It needs the `yaml` extra — `pip install tinydantic[yaml]` — which pulls in [PyYAML](https://pyyaml.org/) (plain `tinydantic` installs stay YAML-free; constructing `YAMLStorage` without the extra raises an `ImportError` naming this install command). Import it from `tinydantic.tinydb.storages` and pass the class as `storage=`:

```pycon
>>> from tinydantic.tinydb.storages import YAMLStorage
>>> tmpdir = tempfile.TemporaryDirectory()
>>> yaml_path = os.path.join(tmpdir.name, "db.yaml")
>>> db = TinyDB(yaml_path, storage=YAMLStorage)
>>> class Item(TinydanticModel, database=db, table_name="items"):
...     name: str
>>> Item(name="widget").insert()
Item(id=1, name='widget')
>>> db.close()
>>> with open(yaml_path) as f:
...     print(f.read())
items:
  '1':
    name: widget
<BLANKLINE>
>>> tmpdir.cleanup()

```

> [!WARNING]
>
> YAML database files must be trusted input: `yaml.safe_load` prevents code execution, but anchors and aliases still expand, so a hostile hand-edited file can exhaust memory. See [Security considerations](security.md#yaml-files).

## Composing with middleware

A [Middleware][tinydb.middlewares.Middleware] wraps a storage class to change _how_ reads and writes happen without changing the model API. TinyDB's [CachingMiddleware][tinydb.middlewares.CachingMiddleware] buffers writes in memory and flushes them in batches, which greatly reduces disk I/O for write-heavy workloads. Wrap the storage _class_ (not an instance) and pass the result as `storage=`:

```pycon
>>> from tinydb.storages import JSONStorage
>>> from tinydb.middlewares import CachingMiddleware
>>> tmpdir = tempfile.TemporaryDirectory()
>>> cache_path = os.path.join(tmpdir.name, "db.json")
>>> db = TinyDB(cache_path, storage=CachingMiddleware(JSONStorage))
>>> class Log(TinydanticModel, database=db, table_name="logs"):
...     msg: str
>>> Log(msg="cached").insert()
Log(id=1, msg='cached')

```

> [!WARNING]
>
> `CachingMiddleware` holds writes in memory until its buffer fills or the database is closed. **You must call [close()][tinydb.database.TinyDB.close] (or use a context manager) to flush pending writes**, or the last batch never reaches disk. After closing, the file contains everything:

```pycon
>>> db.close()
>>> with open(cache_path) as f:
...     print(f.read())
{"logs": {"1": {"msg": "cached"}}}
>>> tmpdir.cleanup()

```

### Keeping document ids in numeric order

TinyDB stores document ids as strings, so a table with ten documents serializes `"1"`, `"10"`, `"2"` — lexicographic order, which undoes much of the reason to choose a human-readable format in the first place. [SortIntDocIDsMiddleware][tinydantic.tinydb.middlewares.SortIntDocIDsMiddleware] converts the ids back to integers on write and inserts them in ascending numeric order:

```pycon
>>> from tinydantic.tinydb.middlewares import SortIntDocIDsMiddleware
>>> tmpdir = tempfile.TemporaryDirectory()
>>> sorted_path = os.path.join(tmpdir.name, "db.yaml")
>>> db = TinyDB(sorted_path, storage=SortIntDocIDsMiddleware(YAMLStorage))
>>> class Ticket(TinydanticModel, database=db, table_name="tickets"):
...     summary: str
>>> _ = Ticket.insert_many([Ticket(summary=f"ticket {n}") for n in range(1, 11)])
>>> db.close()
>>> with open(sorted_path) as f:
...     print(f.read()[:62], end="")
tickets:
  1:
    summary: ticket 1
  2:
    summary: ticket 2
>>> tmpdir.cleanup()

```

Without it, that file would open with `1`, `10`, `2`. The trade-off is in the name: the middleware hands integer keys to the storage below it, which is fine for JSON and YAML but may break a storage that can only serialize string keys.

### Counting storage operations

TinyDB has no indexes, so costs are paid in whole-table reads and writes — and when something is slow, the first question is how many of those an operation triggered. [ProfilingMiddleware][tinydantic.tinydb.middlewares.ProfilingMiddleware] counts every `read()` and `write()` that reaches the storage it wraps. Keep a reference to the middleware — it is the same object TinyDB uses:

```pycon
>>> from tinydantic.tinydb.middlewares import ProfilingMiddleware
>>> storage = ProfilingMiddleware(MemoryStorage)
>>> db = TinyDB(storage=storage)
>>> class Event(TinydanticModel, database=db, table_name="events"):
...     name: str
>>> Event(name="boot").insert()
Event(id=1, name='boot')
>>> storage.read_count, storage.write_count
(2, 1)
>>> Event.all()
[Event(id=1, name='boot')]
>>> storage.read_count
3
>>> storage.reset()
>>> storage.read_count, storage.write_count
(0, 0)

```

The counters are exact where timings are noisy, which makes them the right evidence for a performance bug report — an issue's measurement harness can state "3 storage reads" and be reproducible on any machine. Middlewares stack, and the position in the stack is what gets measured: `ProfilingMiddleware(CachingMiddleware(JSONStorage))` counts only what the cache lets through to disk, while `CachingMiddleware(ProfilingMiddleware(JSONStorage))` counts what the database asks for before caching.

## Beyond the built-ins

TinyDB's [storage documentation](https://tinydb.readthedocs.io/en/latest/usage.html#storage-types) lists more options, and third-party packages add backends such as SQLite. Any storage that presents the TinyDB `Storage` interface works with `tinydantic` unchanged, because `tinydantic` only ever hands the storage layer JSON-safe primitives.

> [!NOTE]
>
> `YAMLStorage` and the other helpers under `tinydantic.tinydb` are kept free of any dependency on `tinydantic`'s core, so they can later be extracted into a standalone TinyDB-extensions package. Import them from `tinydantic.tinydb.storages` today; if that extraction happens, the import path is the only thing that would change.

## Where next

- [Configuration](configuration.md) — bind models to a database and table, late binding with `bind()`, and how config resolves across a class hierarchy.
- [Models](models.md) — what `tinydantic` actually writes to storage and why it round-trips.
