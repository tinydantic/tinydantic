# Testing

Code that talks to a database is only as testable as its data isolation. `tinydantic` makes this easy: bind your models to an in-memory [TinyDB][tinydb.database.TinyDB] in a fixture, give each test its own clean table, and you never touch the disk. This page covers the two isolation patterns this project uses in its own suite — a fresh subclass per test, and late binding with [bind()][tinydantic.TinydanticModel.bind] — plus [truncate()][tinydantic.TinydanticModel.truncate] for resetting state between tests.

## Start with in-memory storage

[MemoryStorage][tinydb.storages.MemoryStorage] keeps the whole database in a Python dict, so it is fast, needs no cleanup, and disappears when the object goes out of scope. It is the right default for tests — the same choice every other page in this guide makes. See [Storage](storage.md) for the full backend tour.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import TinydanticModel
>>> db = TinyDB(storage=MemoryStorage)
>>> class Note(TinydanticModel, database=db, table_name='notes'):
...     text: str
>>> Note(text='scratch').insert()
Note(id=1, text='scratch')

```

The question a test suite has to answer is: how do you give _each_ test a database in this pristine state, so tests never leak state into one another? There are two good answers.

## The subclass-in-fixture pattern

The pattern `tinydantic`'s own suite uses is to define a fresh model **subclass**, bound to a fresh in-memory database, inside a pytest fixture. Each test that requests the fixture gets its own class and its own storage, so there is no shared state to leak — isolation falls out of scope, with nothing to tear down.

Because pytest fixtures rely on the collector and cannot run as doctests, the example below is illustrative — it is a `conftest.py` plus a test module, not a runnable doctest block:

```python
# conftest.py
import pytest

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from tinydantic import TinydanticModel


class User(TinydanticModel):
    """Unbound base model — no database= on the class statement."""

    name: str
    email: str


@pytest.fixture
def user_model():
    """Yield a User subclass bound to a fresh in-memory database."""
    db = TinyDB(storage=MemoryStorage)

    class BoundUser(User, table_name="users"):
        """A per-test subclass bound to its own database."""

    return BoundUser
```

```python
# test_users.py
def test_insert_assigns_id(user_model):
    user = user_model(name="Ada", email="ada@example.com").insert()
    assert user.id == 1


def test_each_test_starts_empty(user_model):
    # A brand-new subclass over a brand-new database: nothing carries over.
    assert user_model.all() == []
```

The key move is defining the model _class_ inside the fixture (or subclassing an unbound base, as above). A class defined at module scope is a single shared object; binding and mutating it across tests reintroduces exactly the shared state you were trying to avoid. A fresh subclass per test sidesteps that entirely.

> [!NOTE]
>
> Config resolves down the MRO, so `BoundUser` inherits `User`'s fields while setting its own `database=` and `table_name=`. Defining the base model unbound (no `database=`) and binding only the per-test subclass keeps production code free of test wiring. See [Configuration](configuration.md) for how inheritance and overriding work.

## `bind()` for application factories

The [application-factory](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) pattern — a function that builds a fresh app (and its database) on each call — is common in web apps and pairs naturally with testing. Define your models unbound at import time, then call [bind()][tinydantic.TinydanticModel.bind] inside the factory once the database exists. Tests call the factory with an in-memory database; production calls it with a file-backed one.

```python
# app.py
from tinydb import TinyDB

from tinydantic import TinydanticModel


class User(TinydanticModel, table_name="users"):  # unbound: no database=
    name: str
    email: str


def create_app(database: TinyDB):
    """Bind models to the given database and build the app."""
    User.bind(database=database)
    # ... construct and return the application object ...
    return ...
```

```python
# conftest.py
import pytest

from tinydb import TinyDB
from tinydb.storages import MemoryStorage

from app import create_app


@pytest.fixture
def app():
    return create_app(TinyDB(storage=MemoryStorage))
```

`bind()` updates only the keys you pass and leaves the rest (including inherited ones) intact, so the same models can be pointed at a test database in the fixture and a real one in `main()`.

## Swapping databases with `bind()`

Because `bind()` re-points a model at a different database at runtime, you can demonstrate the isolation it buys directly. Here a single `Widget` class writes to one in-memory database, then rebinds to a second, fresh one — and the swap gives a completely empty starting point, exactly what a fresh fixture provides:

```pycon
>>> class Widget(TinydanticModel, table_name='widgets'):
...     name: str
>>> db_one = TinyDB(storage=MemoryStorage)
>>> Widget.bind(database=db_one)
>>> Widget(name='first').insert()
Widget(id=1, name='first')
>>> Widget.all()
[Widget(id=1, name='first')]

```

Rebind to a second database and the model sees a clean slate — `db_one`'s data is untouched behind it, and ids start over from `1`:

```pycon
>>> db_two = TinyDB(storage=MemoryStorage)
>>> Widget.bind(database=db_two)
>>> Widget.all()
[]
>>> Widget(name='fresh').insert()
Widget(id=1, name='fresh')

```

## `truncate()` between tests

When a test _reuses_ one database (for example a session-scoped file that is expensive to recreate), reset the table between tests instead of rebinding. [truncate()][tinydantic.TinydanticModel.truncate] empties the table and resets its id counter, so the next test starts at `id=1`:

```pycon
>>> Widget.truncate()
>>> Widget.all()
[]
>>> Widget(name='after reset').insert()
Widget(id=1, name='after reset')

```

At the raw TinyDB layer the equivalent is [db.drop_tables()][tinydb.database.TinyDB.drop_tables] — which is what this project's own `db` fixture calls before and after every test to isolate the shared session-scoped database:

```python
# conftest.py (this project's own pattern)
@pytest.fixture
def db(db_session):
    """Yield a TinyDB with tables dropped before and after each test."""
    db_session.drop_tables()
    yield db_session
    db_session.drop_tables()
```

> [!TIP]
>
> A fresh in-memory database per test (the subclass-in-fixture pattern) gives the strongest isolation and needs no reset step — reach for `truncate()` / `drop_tables()` only when you deliberately share one database across tests.

## Where next

- [Configuration](configuration.md) — how `bind()` and config inheritance resolve across a class hierarchy.
- [Storage](storage.md) — in-memory versus file-backed backends and their lifecycle.
- [FastAPI](fastapi.md) — the application-factory and `bind()` patterns applied to a real API, tested with `TestClient`.
