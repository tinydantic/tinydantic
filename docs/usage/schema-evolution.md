# Schema evolution

Your model class is your schema — but the documents in a TinyDB file can predate it. An older version of your app may have written them, another tool may share the file, or someone may have hand-edited a YAML table. Because a `tinydantic` read is a validation, this page answers the question that arises: what happens when the stored document and the current model disagree — and how do you migrate data deliberately instead of by accident?

The examples share state top to bottom, so run them in order.

## Unknown keys and `extra`

Pydantic's default `extra='ignore'` policy applies to `tinydantic` models: keys in the stored document that the model does not declare are silently dropped when the document is read. Suppose an earlier version of your app stored a `rating` field that the current model no longer has:

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import TinydanticModel
>>> db = TinyDB(storage=MemoryStorage)
>>> db.table("books").insert({"title": "Dune", "rating": 5})
1
>>> class Book(TinydanticModel, database=db, table_name="books"):
...     title: str
>>> book = Book.get_by_id(1)
>>> book
Book(id=1, title='Dune')

```

The instance has no `rating` — but the stored document still does. What happens to that key next depends entirely on which write verb you use. [save()][tinydantic.TinydanticModel.save] and [update()][tinydantic.TinydanticModel.update] merge into the stored document, so the key survives:

```pycon
>>> db.table("books").get(doc_id=1)
{'title': 'Dune', 'rating': 5}
>>> book.save()
Book(id=1, title='Dune')
>>> db.table("books").get(doc_id=1)
{'title': 'Dune', 'rating': 5}
>>> Book.update_by_ids({"title": "Dune (1965)"}, [1])
[1]
>>> db.table("books").get(doc_id=1)
{'title': 'Dune (1965)', 'rating': 5}

```

[replace()][tinydantic.TinydanticModel.replace] swaps the entire stored document for the model's current serialized state — and the model's state does not include `rating`:

```pycon
>>> book.replace()
>>> db.table("books").get(doc_id=1)
{'title': 'Dune'}

```

> [!WARNING]
>
> Read a document, call `replace()`, and every key the model does not declare is permanently deleted from storage — silently. Under the default `extra='ignore'` you never see those keys, so nothing warns you they existed. If your file holds keys from older schema versions or other tools, either avoid `replace()` or opt into round-tripping with `extra='allow'` (below).

The behavior, verb by verb:

| Verb | Unknown stored keys |
| --- | --- |
| any read | dropped from the instance; storage untouched |
| `save()` | preserved — merges into the stored document |
| `update()` / `update_all()` / `update_many()` | preserved — validation ignores but keeps them |
| `replace()` | **deleted from storage** — writes the model's view |

### Round-tripping with `extra='allow'`

To adopt an existing TinyDB file — or share one with other tools — without risking silent data loss, set pydantic's `extra='allow'`. Unknown keys then ride along on the instance and survive every write verb, `replace()` included:

```pycon
>>> from pydantic import ConfigDict
>>> db.table("films").insert({"title": "Alien", "rating": 4})
1
>>> class Film(TinydanticModel, database=db, table_name="films"):
...     model_config = ConfigDict(extra="allow")
...     title: str
>>> film = Film.get_by_id(1)
>>> film
Film(id=1, title='Alien', rating=4)
>>> film.replace()
>>> db.table("films").get(doc_id=1)
{'title': 'Alien', 'rating': 4}

```

The trade-off: those extra keys appear in `model_dump()` and everything built from it — including API responses serialized from your models, à la FastAPI. If stale or foreign keys must not leak to callers, keep the default `ignore` policy and avoid `replace()`, or shape responses with an explicit `response_model`. And never build `extra='allow'` instances directly from untrusted request payloads — see [Security considerations](security.md#untrusted-input-in-updates).

### Failing loudly with `extra='forbid'`

The strict option: `extra='forbid'` turns any unknown stored key into a read-time `ValidationError`, so schema drift can never pass unnoticed:

```pycon
>>> class StrictFilm(TinydanticModel, database=db, table_name="films"):
...     model_config = ConfigDict(extra="forbid")
...     title: str
>>> StrictFilm.get_by_id(1)
Traceback (most recent call last):
  ...
pydantic_core._pydantic_core.ValidationError: 1 validation error for StrictFilm
  ...

```

This is the right setting when the model is the only writer and any unknown key means a bug — but it makes every migration mandatory before the data can even be read.

> [!NOTE]
>
> One key is reserved by opt-in machinery: on models with `use_revision=True` (see [Concurrency](concurrency.md)), `revision_id` is `tinydantic`'s optimistic-concurrency token. Documents written _before_ the opt-in have no such key and are adopted conflict-free on their first revisioned write — but if your documents already use a `revision_id` key of their own, rename it (a one-line `update_all()` transform, below) _before_ enabling `use_revision`, or reads will try to parse your data as tokens.

## Migration patterns

TinyDB has no migration framework, and `tinydantic` does not add one — the verbs you already have are enough for the migrations a document store of this size needs. Each recipe below is doctested end-to-end.

The workhorse is [update_all()][tinydantic.TinydanticModel.update_all] with a transform callable: the transform receives each stored document body as a plain `dict` and mutates it in place, and `tinydantic` validates every transformed result against the model _before anything is written_ — a bad transform aborts the whole batch with storage untouched.

### Adding a field

Declare the new field with a default and old documents simply validate lazily on read — no migration required:

```pycon
>>> class Book(TinydanticModel, database=db, table_name="books"):
...     title: str
...     in_print: bool = True
>>> Book.get_by_id(1)
Book(id=1, title='Dune', in_print=True)
>>> db.table("books").get(doc_id=1)
{'title': 'Dune'}

```

The default exists only on the instance; storage still lacks the key. That is usually fine — every future read fills it in — but if other tools read the file, backfill explicitly:

```pycon
>>> Book.update_all({"in_print": True})
[1]
>>> db.table("books").get(doc_id=1)
{'title': 'Dune', 'in_print': True}

```

### Renaming a field

A rename is a transform that pops the old key and sets the new one:

```pycon
>>> db.table("authors").insert_multiple(
...     [{"name": "Frank Herbert"}, {"name": "Octavia Butler"}]
... )
[1, 2]
>>> class Author(TinydanticModel, database=db, table_name="authors"):
...     full_name: str
>>> def rename_name(doc):
...     doc["full_name"] = doc.pop("name")
>>> Author.update_all(rename_name)
[1, 2]
>>> Author.all()
[Author(id=1, full_name='Frank Herbert'), Author(id=2, full_name='Octavia Butler')]

```

Note the ordering freedom: `Author` could not have _read_ these documents before the migration (`full_name` was missing), but the transform only has to produce documents that validate — merged-result validation runs on its output, not its input.

### Removing a field

Deleting a field from the model does not delete it from storage — under `extra='ignore'` the key just lingers, invisible to the model (and subject to the `replace()` behavior above). Purge it deliberately when you want storage clean:

```pycon
>>> db.table("games").insert({"title": "Myst", "rating": 5})
1
>>> class Game(TinydanticModel, database=db, table_name="games"):
...     title: str
>>> def drop_rating(doc):
...     doc.pop("rating", None)
>>> Game.update_all(drop_rating)
[1]
>>> db.table("games").get(doc_id=1)
{'title': 'Myst'}

```

### Changing a type

Pydantic's lax mode can mask a type change: a `year` stored as a string coerces cleanly to an `int` field on every read, so the model works while storage stays stale.

```pycon
>>> db.table("albums").insert({"title": "Kind of Blue", "year": "1959"})
1
>>> class Album(TinydanticModel, database=db, table_name="albums"):
...     title: str
...     year: int
>>> Album.get_by_id(1)
Album(id=1, title='Kind of Blue', year=1959)
>>> db.table("albums").get(doc_id=1)
{'title': 'Kind of Blue', 'year': '1959'}

```

Canonicalize storage with a transform so other readers (and any future `Strict` annotation) see the real type:

```pycon
>>> def year_to_int(doc):
...     doc["year"] = int(doc["year"])
>>> Album.update_all(year_to_int)
[1]
>>> db.table("albums").get(doc_id=1)
{'title': 'Kind of Blue', 'year': 1959}

```

### Versioned migrations

When a table accumulates several generations of documents, give the schema a version field and write one idempotent transform per upgrade. Old and new bodies coexist in the file until one `update_all()` brings them all to the current version:

```pycon
>>> db.table("profiles").insert_multiple(
...     [
...         {"schema_version": 1, "name": "Alice"},
...         {"schema_version": 2, "full_name": "Bob", "bio": "likes databases"},
...     ]
... )
[1, 2]
>>> class Profile(TinydanticModel, database=db, table_name="profiles"):
...     schema_version: int = 2
...     full_name: str
...     bio: str = ""
>>> def migrate_to_v2(doc):
...     if doc["schema_version"] == 1:
...         doc["full_name"] = doc.pop("name")
...         doc["bio"] = ""
...         doc["schema_version"] = 2
>>> Profile.update_all(migrate_to_v2)
[1, 2]
>>> Profile.all()
[Profile(id=1, schema_version=2, full_name='Alice', bio=''),
  Profile(id=2, schema_version=2, full_name='Bob', bio='likes databases')]

```

Because the transform checks the version before touching anything, re-running it is safe — a property worth keeping for every migration you write.

Documents so old that no current model can express them are the signal to drop below the model layer: read and rewrite them through the raw TinyDB table (`db.table(...)` — TinyDB's public API) in a one-off script, then let the model take over:

```pycon
>>> [dict(raw) for raw in db.table("profiles").all()]
[{'schema_version': 2, 'full_name': 'Alice', 'bio': ''},
  {'schema_version': 2, 'full_name': 'Bob', 'bio': 'likes databases'}]

```

## Where next

- [CRUD tour](crud.md) — the `update_all()`, `save()`, and `replace()` verbs these recipes are built on, including the `extra_keys=` escape for writing keys the model does not know.
- [Models](models.md) — what `tinydantic` writes to storage and why it round-trips.
- [Security considerations](security.md) — why `extra='allow'` and untrusted input do not mix.
