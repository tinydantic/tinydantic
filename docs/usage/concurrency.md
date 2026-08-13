# Concurrency

TinyDB — and therefore `tinydantic` — supports exactly one execution model: **a single process, with all database access on a single thread**. This page explains what that contract means and why it exists, the one stale-write hazard that remains _inside_ the contract (and the `use_revision` mechanism that closes it), how to make a second process fail loudly instead of corrupting slowly, and what backups and restores do to all of the above.

## The contract: one process, one thread

TinyDB contains no locking of any kind. Every mutation is a whole-table read-modify-write against the storage, and every `TinyDB` instance keeps in-memory caches (query results, the next document id) that assume it is the file's only user. Two consequences follow:

- **Two processes sharing a database file corrupt it.** Each process rewrites the entire file from its own stale in-memory view, so the last writer silently discards everything the other wrote — when interleaved writes don't tear the file into invalid JSON first. There is no middleware or lock that makes this safe; see [Detecting a second process](#detecting-a-second-process) for making it _loud_ instead.
- **Two threads in one process race the same way.** TinyDB's own operations are unguarded read-modify-write cycles, so even two concurrent `insert()` calls can lose documents. `tinydantic` deliberately adds no internal locks — a lock around each operation would protect too little (the dangerous window is _between_ your read and your write, not inside either) while implying a thread-safety promise the storage layer cannot keep.

Keeping all database access on one thread is easier than it sounds — it is the natural shape of a script, a CLI tool, or a test suite, and the [FastAPI page](fastapi.md#async-fastapi-and-tinydb) shows two patterns that get it by construction in a web service.

Within the contract, [CachingMiddleware][tinydb.middlewares.CachingMiddleware] composes safely with everything on this page: with one process and one thread, its cache _is_ the authoritative database state, flushed lazily. Its documented cost stands — writes still in the cache are lost if the process crashes before a flush.

## The window that remains: staleness across requests

Single-threaded execution removes interleaving, but it cannot remove _time_. The classic lost update needs no threads at all:

1. Request one loads a document into an edit form and returns.
2. The user thinks for five minutes. Meanwhile another request edits the same document.
3. The user submits. The handler saves a document built from what they were looking at — silently reverting the other request's edit.

Three requests, strictly sequential, and a write was lost. `save()` writes the whole document, so the staleness of _any_ field the user saw becomes the stored truth. This is the problem optimistic concurrency solves.

## Optimistic concurrency: `use_revision`

Opt in per model with the `use_revision=True` class kwarg (inherited like every [configuration](configuration.md) key). The model gains a `revision_id` field — an opaque [UUID][uuid.UUID] token naming the document's last write:

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import StaleDocumentError, TinydanticModel
>>>
>>> db = TinyDB(storage=MemoryStorage)
>>>
>>> class Book(TinydanticModel, database=db, use_revision=True):
...     title: str
...     stock: int = 0
>>>
>>> book = Book(title="Dune", stock=5).insert()
>>> book.revision_id is not None
True

```

The token is deliberately absent from `model_dump()` and from the JSON Schema, so it never rides into a FastAPI response or a published OpenAPI document as an unexplained field. It is bookkeeping, not part of your document — read it off the instance when you need it, as the ETag recipe below does:

```pycon
>>> book.model_dump()
{'id': 1, 'title': 'Dune', 'stock': 5}
>>> sorted(Book.model_json_schema()["properties"])
['id', 'stock', 'title']
>>> book.revision_id is not None  # still yours to read
True

```

Every write path mints a fresh token for the documents it touches ("rotates" it). The instance methods that hold a token from their read — `save()`, `replace()`, and `delete()` — _check_ it first: if the stored token no longer matches, another writer got there in between, and nothing is written:

```pycon
>>> assert book.id is not None
>>> stale = Book.get_by_id(book.id)  # a second copy, same token
>>> book.stock = 4
>>> book = book.save()  # rotates: stale's token is now old
>>> stale.stock = 3  # computed from a world where stock was 5
>>> stale.save()
Traceback (most recent call last):
  ...
tinydantic._errors.StaleDocumentError: 'Book' document 1 in table 'book' was modified since this instance read it. Reload and retry, or pass ignore_revision=True for deliberate last-write-wins.

```

The stale write was refused and the store still holds `stock=4`. Recovery is always the same shape — reload, re-decide against fresh state, retry:

```pycon
>>> current = Book.get_by_id(book.id)
>>> current.stock -= 1  # re-derive the decision from fresh state
>>> current = current.save()
>>> Book.get_by_id(book.id).stock
3

```

When last-write-wins is genuinely what you want — an admin override, a migration script, a conflict handler that decided "mine wins" — say so explicitly. The token still rotates, so _other_ holders correctly go stale:

```pycon
>>> stale.stock = 99  # a value the current document does not have
>>> stale = stale.save(ignore_revision=True)  # deliberate overwrite
>>> Book.get_by_id(book.id).stock
99

```

`delete()` checks too — a stale delete is the most destructive stale write there is — and takes the same `ignore_revision=True` escape. A concurrently _deleted_ document is also a conflict: `save()` on a revisioned model never silently resurrects one ([StaleDocumentError][tinydantic.StaleDocumentError] reports which case you hit via its `deleted` attribute).

### `patch()` rotates but never checks

[patch()][tinydantic.TinydanticModel.patch] is the deliberate field-merge tool: it writes only the fields you name, so concurrent changes to _unrelated_ fields survive. A revision check would make it conflict on exactly the merges it exists to allow, so it rotates without checking, and the instance absorbs the fresh token (a later `save()` won't spuriously conflict). The rule of thumb:

- **Patch what you decided.** `book.patch(title="Dune (1965)")` — the value came from outside the document; no read went stale.
- **Save what you derived.** `stock - 1` was computed _from_ a read; route it through the load-mutate-`save()` loop above, where the check lives.

The update verbs — `update()`, `update_by_ids()`, `update_all()`, `update_many()`, `FindQuery.update()` — hold no instance and no token, so they cannot check. `upsert()` does take an instance, and on a revisioned model that instance carries a token, but its contract is "write this regardless of current state", so it deliberately does not check either. All six rotate every document they touch, correctly invalidating tokens held elsewhere. Writing `revision_id` yourself through any update path raises [RevisionUpdateError][tinydantic.RevisionUpdateError] — a forged token could mask concurrent writes.

### Tokens travel: the ETag pattern

The token's real power is that it survives the round trip through a client. A web edit flow spans requests — the instance that read the document is long gone when the user submits — so hand the token to the client and require it back, which is exactly HTTP's `ETag` / `If-Match` conditional-update protocol:

```pycon
>>> from typing import Annotated
>>> from uuid import UUID
>>> from fastapi import FastAPI, Header, HTTPException, Response
>>> from fastapi.testclient import TestClient
>>>
>>> app = FastAPI()
>>>
>>> @app.get("/books/{book_id}")
... async def read_book(book_id: int, response: Response) -> Book:
...     book = Book.get_or_none(Book.id == book_id)
...     if book is None:
...         raise HTTPException(status_code=404)
...     response.headers["ETag"] = str(book.revision_id)
...     return book
>>>
>>> @app.put("/books/{book_id}")
... async def replace_book(
...     book_id: int,
...     payload: dict,
...     if_match: Annotated[str, Header()],
... ) -> Book:
...     book = Book.get_or_none(Book.id == book_id)
...     if book is None:
...         raise HTTPException(status_code=404)
...     book.revision_id = UUID(if_match)  # adopt the client's token
...     book.title = payload["title"]
...     try:
...         return book.save()
...     except StaleDocumentError:
...         raise HTTPException(
...             status_code=412,
...             detail="Book changed since you loaded it",
...         ) from None
>>>
>>> client = TestClient(app)
>>> etag = client.get(f"/books/{book.id}").headers["ETag"]
>>> client.put(
...     f"/books/{book.id}",
...     json={"title": "Dune (1965)"},
...     headers={"If-Match": etag},
... ).status_code
200
>>> client.put(  # the same token again: now stale
...     f"/books/{book.id}",
...     json={"title": "Dune!"},
...     headers={"If-Match": etag},
... ).status_code
412

```

The `412 Precondition Failed` tells the client to re-fetch, re-apply the user's intent, and retry — the HTTP spelling of the reload-and-retry loop.

### Existing databases

Documents written before `use_revision` was enabled have no token; a held token of `None` matches them, so the first revisioned `save()` adopts each document conflict-free. One caveat: if your documents already use a `revision_id` key of their own, enabling `use_revision` would misread it — rename that key first (see [Schema evolution](schema-evolution.md)). A model that _declares_ its own `revision_id` field while opting in is refused at class definition with [RevisionFieldError][tinydantic.RevisionFieldError]. (On models that _don't_ opt in, the name stays yours — though `TinydanticModel` declares it statically so revisioned code type-checks, so declaring your own needs a `# type: ignore[assignment]` under mypy.)

## Detecting a second process

Nothing above helps if a second _process_ opens the database — revision checks cannot be made atomic across processes, and TinyDB's caches don't even see the other process's writes. The contract is one process, and [ProcessLockMiddleware][tinydantic.tinydb.middlewares.ProcessLockMiddleware] enforces it at open time: it takes a non-blocking exclusive OS lock on a sidecar file (`<database path>.lock`) and raises [DatabaseLockedError][tinydantic.DatabaseLockedError] immediately if the lock is already held — a startup error instead of slow corruption:

```pycon
>>> import tempfile
>>> from pathlib import Path
>>> from tinydb.storages import JSONStorage
>>> from tinydantic.tinydb.middlewares import ProcessLockMiddleware
>>>
>>> path = Path(tempfile.mkdtemp()) / "app.json"
>>> app_db = TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
>>> TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
Traceback (most recent call last):
  ...
tinydantic._errors.DatabaseLockedError: The database '...' is already open in another process (its lock file is held). TinyDB has no multi-process safety — close the other process, or use a separate database file.
>>> app_db.close()  # releases the lock; the OS also releases it if the process dies

```

A second TinyDB instance on the same file _within_ one process is refused too — two instances corrupt each other's caches just as surely as two processes do. The `.lock` sidecar file is left behind after close (deleting lock files is inherently racy); it is empty and harmless.

> [!WARNING]
>
> This middleware _detects_ the misconfiguration — it does not make multi-process access safe, and advisory locks only bind cooperating processes: text editors, scripts, and backup tools ignore them, and they are unreliable on network filesystems (NFS, SMB). Keep database files on local disks. If you genuinely need multiple processes, that is the signal to move to a client/server database — not to bolt locking onto TinyDB.

## Backups and restores

Sequential identifiers only name things _within one linear history_, and restoring a backup forks that history. After a restore, TinyDB hands out `doc_id`s that were already used on the abandoned branch, so references that escaped the database before the restore — URLs in sent emails, bookmarks, ids stored in other systems — can resolve to unrelated documents. Revision tokens are the write-side defense: they are random, never reused, and therefore _cannot_ match across the fork — a held pre-restore token conflicts with any post-restore document, including an imposter reusing a recycled `doc_id`. **Conflicts right after a restore are the mechanism working**, not a bug.

Reads have no token to check, so a fresh `get_by_id()` trusts the id it is given. If identifiers must survive restores and travel outside the database, give documents a stable name of their own:

```python
from uuid import UUID, uuid4

from pydantic import Field


class Order(TinydanticModel, database=db, use_revision=True):
    uid: UUID = Field(default_factory=uuid4)  # stable public identity
    total: float = 0.0


# resolve external references by uid, not doc_id:
# Order.get(q(Order.uid) == incoming_uid)
```

Put the `uid` in URLs and foreign systems; keep `doc_id` internal. (This is deliberately an application-level recipe, not a library feature — pydantic already does all the work.)

## What remains unguarded

Honesty about the edges, so you can decide what matters for your deployment:

- **Crash mid-write.** TinyDB rewrites the file in place with no atomic-rename step, so a crash or power loss during a write can tear the file. Neither revisions nor the process lock help; keep backups of files you care about.
- **Non-cooperating writers.** A human editing the YAML file, or any tool writing directly, bypasses both mechanisms. A hand-edit that changes content but not the `revision_id` silently invalidates nothing.
- **Multi-document invariants.** Tokens are per-document and there are no transactions; an operation spanning two documents can succeed on one and conflict on the other, with no rollback.

## Where next

- [FastAPI](fastapi.md) — the two single-threaded serving patterns this contract blesses, and when to move between them.
- [Security considerations](security.md) — file permissions and untrusted input, the other half of deployment hygiene.
- [Schema evolution](schema-evolution.md) — how stored documents and models drift, including the `revision_id` key caveat.
- [Storage](storage.md) — middleware composition, including `CachingMiddleware`.
