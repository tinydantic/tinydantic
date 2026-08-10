# Security considerations

`tinydantic` embeds TinyDB: a local, single-process, plaintext datastore built for trusted environments — prototypes, small tools, tests, and single-process services. The library validates every document crossing the model boundary, but it cannot protect the database file from the operating system, other processes, or a hostile regular expression. This page collects what you must handle yourself, especially before anything network-facing touches a `tinydantic` model.

## The database file

The database is one plaintext file. [JSONStorage][tinydb.storages.JSONStorage] and [YAMLStorage][tinydantic.tinydb.storages.YAMLStorage] create it with the process umask — on most systems that means world-readable — and everything your models store, tokens and personal data included, is legible to anyone who can read the file. Restrict it at creation:

```pycon
>>> import tempfile
>>> from pathlib import Path
>>> from tinydb import TinyDB
>>> tmpdir = tempfile.TemporaryDirectory()
>>> db_path = Path(tmpdir.name) / "db.json"
>>> db = TinyDB(db_path)
>>> db_path.chmod(0o600)
>>> db.close()
>>> tmpdir.cleanup()

```

Alternatively call `os.umask(0o077)` early in process startup so every file the process creates is owner-only. And two placement rules that cost nothing: never put the database file under a web server's document root (it would be one `GET /db.json` away from public), and never commit it to a repository.

## Untrusted input in queries

Three different things can come from a user, with three different risk levels.

Untrusted **values** in comparisons are safe. A query like `User.name == request_value` compares the value against stored data — it is never interpreted, so there is nothing to inject:

```pycon
>>> import re
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import TinydanticModel
>>> db2 = TinyDB(storage=MemoryStorage)
>>> class User(TinydanticModel, database=db2, table_name="users"):
...     name: str
>>> User(name="Alice (admin)").insert()
User(id=1, name='Alice (admin)')
>>> User.get(User.name == "Alice (admin)")
User(id=1, name='Alice (admin)')

```

Untrusted **regex patterns** are not safe. `.matches()` and `.search()` compile their argument with Python's `re` module and run it against every document in the table — and an attacker-chosen pattern can trigger catastrophic backtracking (ReDoS), pinning a CPU core for minutes with a few dozen characters. Never pass user input as a pattern. When users supply search _text_, escape it so it matches literally:

```pycon
>>> term = "(admin)"
>>> User.search(User.name.search(re.escape(term)))
[User(id=1, name='Alice (admin)')]

```

Untrusted **field names** are somewhere in between. [field()][tinydantic.field] refuses any name the model does not declare, so it will not probe keys your models never expose. TinyDB's `where("some_key")` has no such check — it builds a query against any document key, stored extra keys included — so never hand it user input. Keep field names server-chosen either way; user input belongs on the value side of a query.

## Untrusted input in updates

The update verbs are guarded by default. Mapping values are validated against their field's type, each matched document's merged result is validated before anything is written, and keys that are not model fields are rejected:

```pycon
>>> User.update({"is_admin": True}, User.name == "Alice (admin)")
Traceback (most recent call last):
  ...
tinydantic._errors.UnknownUpdateFieldError: ...

```

That default is what stands between a quick CRUD endpoint and a mass-assignment hole: without it, `User.update(payload, cond)` would persist every attacker-chosen key verbatim. The `extra_keys="allow"` escape hatch exists for databases legitimately shared with other tools — but it writes unknown keys **unvalidated**, so never feed a raw request payload through it. The same reasoning applies to `extra='allow'` models: do not construct them directly from untrusted request bodies. [Schema evolution](schema-evolution.md) covers the legitimate uses of both.

One field deserves its own mention: on a [use_revision](concurrency.md#optimistic-concurrency-use_revision) model, `revision_id` is client-settable through the constructor. That is by design — the `If-Match` flow works by adopting the token the client sent — but it means a model built straight from an untrusted request body lets the caller choose its own concurrency token and defeat the conflict check. Build such models from an explicit request schema (`UserUpdate`, not `User`) and set `revision_id` yourself from the header. The token is excluded from `model_dump()` and from the JSON Schema, so it will not leak _outward_ on its own.

## YAML files

`YAMLStorage` reads with `yaml.safe_load`, so a hostile database file cannot execute code. It can still take the process down: YAML anchors and aliases expand recursively, and a hand-crafted file a few hundred bytes long can expand to gigabytes in memory (the "billion laughs" attack). `safe_load` does not prevent that — so **YAML database files must be trusted input**. Human-edited by people you trust is the use case; uploaded or user-supplied files are not.

On the write side the storage is guarded: it serializes with `yaml.safe_dump`, which fails fast — before the file is touched — on any value the safe loader could not read back, so a write can never brick the database file with unreadable tags.

## Concurrency

Neither TinyDB nor `tinydantic` locks the database file, and concurrent writers will corrupt it. The [Concurrency page](concurrency.md) covers the single-process contract, `use_revision` optimistic concurrency for stale writes, and `ProcessLockMiddleware` for making a second process fail at startup instead of corrupting slowly; the [FastAPI page](fastapi.md#async-fastapi-and-tinydb) shows the two serving patterns that satisfy the contract by construction.

## Where next

- [Storage](storage.md) — choosing a backend, including `YAMLStorage` and middleware.
- [Schema evolution](schema-evolution.md) — the `extra` policies and the `extra_keys=` escape referenced above.
- [FastAPI](fastapi.md) — putting `tinydantic` behind HTTP without breaking its single-process rules.
