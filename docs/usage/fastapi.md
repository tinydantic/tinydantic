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
>>> class User(TinydanticModel, database=db, table_name='users'):
...     name: str
...     email: str
>>>
>>> class UserCreate(BaseModel):
...     name: str
...     email: str
>>>
>>> app = FastAPI()
>>>
>>> @app.post('/users', status_code=status.HTTP_201_CREATED)
... def create_user(payload: UserCreate) -> User:
...     return User(**payload.model_dump()).insert()
>>>
>>> @app.get('/users/{user_id}')
... def read_user(user_id: int) -> User:
...     user = User.get_by_id(user_id)
...     if user is None:
...         raise HTTPException(status_code=404, detail='User not found')
...     return user
>>>
>>> @app.get('/users')
... def list_users() -> list[User]:
...     return User.all()
>>>
>>> client = TestClient(app)

```

A few things worth calling out:

- **The request body is a separate schema.** `UserCreate` has no `id`, so clients cannot set one — the server assigns it. Returning a `User` (which _does_ expose `id`) means the response echoes the created resource, id included.
- **`get_by_id` returns `None` when nothing matches**, which the handler turns into a `404`. This is the precisely-typed read variant from the [CRUD tour](crud.md); it returns `User | None`, so the `is None` check is exactly what a type checker expects.
- **The endpoints are plain `def`, not `async def`** — the deliberate choice explained in the last section.

### `POST /users` — create

Posting a body creates the document and returns it with `id` populated and a `201 Created` status:

```pycon
>>> response = client.post('/users', json={'name': 'Ada', 'email': 'ada@example.com'})
>>> response.status_code
201
>>> response.json()
{'id': 1, 'name': 'Ada', 'email': 'ada@example.com'}

```

A second create is assigned the next id:

```pycon
>>> client.post('/users', json={'name': 'Grace', 'email': 'grace@example.com'}).json()
{'id': 2, 'name': 'Grace', 'email': 'grace@example.com'}

```

### `GET /users/{user_id}` — read one

Fetching an existing id returns the document; the `id` in the path maps straight to TinyDB's document id:

```pycon
>>> response = client.get('/users/1')
>>> response.status_code
200
>>> response.json()
{'id': 1, 'name': 'Ada', 'email': 'ada@example.com'}

```

A missing id returns `404` with the handler's detail message, because `get_by_id` returned `None`:

```pycon
>>> response = client.get('/users/999')
>>> response.status_code
404
>>> response.json()
{'detail': 'User not found'}

```

### `GET /users` — list all

The collection endpoint returns every document via [all()][tinydantic.TinydanticModel.all], serialized through the `User` response model:

```pycon
>>> response = client.get('/users')
>>> response.status_code
200
>>> response.json()
[{'id': 1, 'name': 'Ada', 'email': 'ada@example.com'},
  {'id': 2, 'name': 'Grace', 'email': 'grace@example.com'}]

```

## Async, FastAPI, and TinyDB

TinyDB is a synchronous library, and `tinydantic` is a thin synchronous layer over it. That is not a limitation to work around in FastAPI — it is the grain to work with.

**Prefer plain `def` endpoints.** When you declare a path operation with `def` (not `async def`), FastAPI runs it in an external threadpool so its blocking I/O never stalls the event loop. This is the correct default for TinyDB-backed handlers: your `def create_user` above is already doing the right thing, with no extra code. The endpoints in this page are all plain `def` for exactly this reason.

**In `async def` contexts, offload the blocking call.** If you are inside an `async def` handler (perhaps because it also awaits other async work), do not call `tinydantic` methods directly — a blocking call on the event-loop thread stalls every other request. Push it to a worker thread with [asyncio.to_thread][]:

```python
import asyncio

from fastapi import FastAPI

app = FastAPI()


@app.get("/users/{user_id}")
async def read_user(user_id: int):
    # Runs the blocking TinyDB read off the event loop.
    user = await asyncio.to_thread(User.get_by_id, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

**TinyDB has no concurrency safety.** TinyDB does no locking and is not safe for concurrent access — neither across processes nor across threads writing at the same time. Two practical rules follow:

- **Run a single process.** Do not put a TinyDB file behind multiple worker processes (for example `uvicorn --workers 4` or several Gunicorn workers). Each process holds its own view of the file and they will clobber one another. Use one process — scale with the threadpool, not with processes.
- **Serialize writes.** Route writes through one place. FastAPI's threadpool can run several `def` handlers at once, so guard write paths with a lock (or funnel them through a single worker) if concurrent writes are possible.

> [!NOTE]
>
> `tinydantic`'s recommendation is sync-first, deliberately. The async lifecycle shims that exist for TinyDB are unmaintained, are `async with`-scoped in a way that conflicts with `tinydantic`'s long-lived class binding, and rely on file locking that is silently absent on some platforms (spec non-goals, analyzed 2026-07-05). Plain `def` handlers in FastAPI's threadpool, plus `asyncio.to_thread` where you genuinely need it, cover the real use cases without that risk. Revisit if a future version adds first-class async support.

None of this is a compromise for `tinydantic`'s intended audience.

> [!TIP]
>
> These are the same properties that make TinyDB ideal for what `tinydantic` targets: prototypes, small tools, tests, and single-process services where a JSON file is the whole database. If you outgrow a single process, that is the signal to move to a client/server database — not to bolt concurrency onto TinyDB.

## Where next

- [Testing](testing.md) — the `bind()` and application-factory patterns used to point these models at an in-memory database in tests.
- [CRUD tour](crud.md) — the `insert()`, `get_by_id()`, and `all()` methods these endpoints are built on.
- [Configuration](configuration.md) — binding models to a database, including late binding in an app factory.
