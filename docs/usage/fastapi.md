# FastAPI

A `tinydantic` model _is_ a Pydantic model, so it drops straight into [FastAPI](https://fastapi.tiangolo.com/) as a response model — the same class that reads and writes your documents also describes the JSON your API returns. This page builds a small CRUD API for a `User` resource, exercises every endpoint with FastAPI's [TestClient](https://fastapi.tiangolo.com/reference/testclient/), and closes with the guidance that matters when you put TinyDB behind an async framework.

## A small CRUD API

The setup below is everything the API needs: an in-memory database (see [Storage](storage.md)), the `User` model that doubles as the response model, a plain Pydantic `UserCreate` schema for request bodies, and three endpoints. Because a `tinydantic` model keeps its `id` field in `model_dump()`, responses include the assigned `id` for free — no separate output schema required.

```pycon
>>> from fastapi import FastAPI, HTTPException, status
>>> from fastapi.testclient import TestClient
>>> from pydantic import BaseModel
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import TinydanticModel
>>>
>>> db = TinyDB(storage=MemoryStorage)
>>>
>>> class User(TinydanticModel, database=db, table_name="users"):
...     name: str
...     email: str
>>>
>>> class UserCreate(BaseModel):
...     name: str
...     email: str
>>>
>>> app = FastAPI()
>>>
>>> @app.post("/users", status_code=status.HTTP_201_CREATED)
... async def create_user(payload: UserCreate) -> User:
...     return User(**payload.model_dump()).insert()
>>>
>>> @app.get("/users/{user_id}")
... async def read_user(user_id: int) -> User:
...     user = User.get_by_id(user_id)
...     if user is None:
...         raise HTTPException(status_code=404, detail="User not found")
...     return user
>>>
>>> @app.get("/users")
... async def list_users() -> list[User]:
...     return User.all()
>>>
>>> client = TestClient(app)

```

A few things worth calling out:

- **The request body is a separate schema.** `UserCreate` has no `id`, so clients cannot set one — the server assigns it. Returning a `User` (which _does_ expose `id`) means the response echoes the created resource, id included.
- **`get_by_id` returns `None` when nothing matches**, which the handler turns into a `404`. This is the precisely-typed read variant from the [CRUD tour](crud.md); it returns `User | None`, so the `is None` check is exactly what a type checker expects.
- **The endpoints are `async def`, calling `tinydantic` inline** — Pattern A from the last section, which keeps every database operation on a single thread by construction.

### `POST /users` — create

Posting a body creates the document and returns it with `id` populated and a `201 Created` status:

```pycon
>>> response = client.post(
...     "/users", json={"name": "Ada", "email": "ada@example.com"}
... )
>>> response.status_code
201
>>> response.json()
{'id': 1, 'name': 'Ada', 'email': 'ada@example.com'}

```

A second create is assigned the next id:

```pycon
>>> client.post(
...     "/users", json={"name": "Grace", "email": "grace@example.com"}
... ).json()
{'id': 2, 'name': 'Grace', 'email': 'grace@example.com'}

```

### `GET /users/{user_id}` — read one

Fetching an existing id returns the document; the `id` in the path maps straight to TinyDB's document id:

```pycon
>>> response = client.get("/users/1")
>>> response.status_code
200
>>> response.json()
{'id': 1, 'name': 'Ada', 'email': 'ada@example.com'}

```

A missing id returns `404` with the handler's detail message, because `get_by_id` returned `None`:

```pycon
>>> response = client.get("/users/999")
>>> response.status_code
404
>>> response.json()
{'detail': 'User not found'}

```

### `GET /users` — list all

The collection endpoint returns every document via [all()][tinydantic.TinydanticModel.all], serialized through the `User` response model:

```pycon
>>> response = client.get("/users")
>>> response.status_code
200
>>> response.json()
[{'id': 1, 'name': 'Ada', 'email': 'ada@example.com'},
  {'id': 2, 'name': 'Grace', 'email': 'grace@example.com'}]

```

## Async, FastAPI, and TinyDB

TinyDB is a synchronous library with **no concurrency safety of any kind** — no locking, and in-memory caches that assume a single user (the full story is on the [Concurrency page](concurrency.md)). The contract that follows is: one process, and all database access on one thread. In FastAPI that contract is not a burden — you can get it _by construction_, in two patterns. Start with Pattern A; move to Pattern B when you hit its limits.

### Pattern A: `async def` handlers, inline calls

Declare every endpoint `async def` and call `tinydantic` directly, exactly as the CRUD API above does. FastAPI runs `async def` handlers on the event loop — **one thread** — and a `tinydantic` call contains no `await`, so each database operation runs start-to-finish before any other handler resumes. No interleaving, no races, no locks: the serialization the contract demands falls out of the execution model. This is the simplest correct FastAPI + `tinydantic` app, and the right default for everything `tinydantic` targets.

The trade to understand: a blocking call on the event loop stalls _all_ request handling for its duration. For TinyDB-scale operations — milliseconds against a small local file — that pause is unobservable. It only starts to matter when operations get slow (see the transition criteria below).

> [!WARNING]
>
> Two easy ways to break Pattern A's guarantee, both of which reintroduce the threadpool:
>
> - **Plain `def` endpoints.** FastAPI runs those in a _multi-threaded_ pool — several can run at once, racing on the database. If a handler touches `tinydantic`, make it `async def`.
> - **`asyncio.to_thread` / `run_in_threadpool`.** Wrapping calls this way sends them to the same multi-threaded pool. Don't offload `tinydantic` calls piecemeal; if the loop stall genuinely hurts, adopt Pattern B wholesale.

### Pattern B: one dedicated database thread

When the event loop must stay responsive during database work, move **all** `tinydantic` calls to a single-worker executor — one thread, serving operations in queue order. Serialization is still structural (there is only one thread that ever touches the database); the loop is free while it works:

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from fastapi import FastAPI, HTTPException

app = FastAPI()

# ONE worker: all database operations run on this thread, in order.
db_executor = ThreadPoolExecutor(max_workers=1)


async def in_db_thread(func, /, *args, **kwargs):
    """Run a tinydantic call on the dedicated database thread."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        db_executor, partial(func, *args, **kwargs)
    )


@app.get("/users/{user_id}")
async def read_user(user_id: int) -> User:
    user = await in_db_thread(User.get_by_id, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

The discipline that keeps Pattern B correct: **every** database call goes through the executor — one stray inline call (or a `def` endpoint) and you have two threads again. `max_workers=1` is the entire safety argument; raising it reintroduces the races the contract exists to prevent.

### When to move from A to B

Pattern A's cost is loop stall equal to your slowest database operation, so watch for these symptoms:

- **Latency under concurrency**: p99 grows with request rate while p50 stays flat — requests are queueing behind database calls.
- **Slow endpoints stall unrelated ones**: a heavy `search()` or a large-file write makes health checks and static endpoints time out.
- **Operations outgrow "milliseconds"**: the database file has grown to where whole-file rewrites (how TinyDB writes) take tens of milliseconds or more.

As rough guidance: an operation stalling the loop for 1 ms caps you around a thousand requests/second — far beyond what a TinyDB-backed tool sees — while a 100 ms rewrite of a bloated file is felt by every concurrent user, and is your cue. The migration is mechanical: add the executor and helper, wrap each call site (`User.get_by_id(x)` → `await in_db_thread(User.get_by_id, x)`), and change nothing about models or storage. If even a single serialized database thread is the bottleneck after that, you have outgrown TinyDB itself — move to a client/server database rather than adding threads.

### Concurrent _requests_ still interleave

Both patterns serialize database _operations_; neither serializes _user intent_. Two users can still load the same document into edit forms and submit conflicting saves minutes apart — no threads involved, just time. That is what `use_revision=True` optimistic concurrency is for, including the `ETag` / `If-Match` / `412` flow for exactly this API shape — see [Concurrency](concurrency.md#optimistic-concurrency-use_revision). And for partial updates, prefer [patch()][tinydantic.TinydanticModel.patch]: `user.patch(**payload.model_dump(exclude_unset=True))` writes only the named fields, so concurrent edits to unrelated fields survive. Like the other instance-level writes, `patch()` fires [before_write()][tinydantic.TinydanticModel.before_write], so audit timestamps stamped in that hook keep working on PATCH endpoints — the table-level `update()` and `update_all()` are the ones that fire no hook.

**Run a single process.** Never put a TinyDB file behind multiple workers (`uvicorn --workers 4`, Gunicorn workers) — each process rewrites the whole file from its own view and they destroy each other's writes. Add [ProcessLockMiddleware][tinydantic.tinydb.middlewares.ProcessLockMiddleware] to your storage so that misconfiguration fails at startup instead of corrupting slowly.

> [!NOTE]
>
> `tinydantic`'s recommendation is sync-first, deliberately. The async lifecycle shims that exist for TinyDB are unmaintained, are `async with`-scoped in a way that conflicts with `tinydantic`'s long-lived class binding, and rely on file locking that is silently absent on some platforms. Pattern A — and Pattern B where the loop must stay responsive — covers the real use cases without that risk. Revisit if a future version adds first-class async support.

None of this is a compromise for `tinydantic`'s intended audience.

> [!TIP]
>
> These are the same properties that make TinyDB ideal for what `tinydantic` targets: prototypes, small tools, tests, and single-process services where a JSON file is the whole database. If you outgrow a single process, that is the signal to move to a client/server database — not to bolt concurrency onto TinyDB.

## Where next

- [Concurrency](concurrency.md) — the single-process contract in full: `use_revision` optimistic concurrency, the ETag pattern, `ProcessLockMiddleware`, and backup/restore semantics.
- [Security considerations](security.md) — file permissions and untrusted input, before anything network-facing goes live.
- [Testing](testing.md) — the `bind()` and application-factory patterns used to point these models at an in-memory database in tests.
- [CRUD tour](crud.md) — the `insert()`, `get_by_id()`, and `all()` methods these endpoints are built on.
- [Configuration](configuration.md) — binding models to a database, including late binding in an app factory.
