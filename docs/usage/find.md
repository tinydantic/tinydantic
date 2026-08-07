# Fluent queries

[find()][tinydantic.TinydanticModel.find] builds a [FindQuery][tinydantic.FindQuery]: a lazy, immutable description of a query that you refine with modifiers — [sort()][tinydantic.FindQuery.sort], [skip()][tinydantic.FindQuery.skip], [limit()][tinydantic.FindQuery.limit] — and execute with a terminal. Where [search()][tinydantic.TinydanticModel.search] answers "which documents match?", a chain answers the questions that come right after: in what order, which page, just the first one, how many — and, when you ask it to, deletes or updates exactly that selection.

The examples share state top to bottom, so run them in order.

```pycon
>>> from tinydb import TinyDB
>>> from tinydb.storages import MemoryStorage
>>> from tinydantic import TinydanticModel, field, q
>>> db = TinyDB(storage=MemoryStorage)
>>> class User(TinydanticModel, database=db, table_name="users"):
...     name: str
...     age: int
>>> for name, age in [
...     ("bob", 30),
...     ("alice", 25),
...     ("carol", 30),
...     ("dave", 25),
...     ("erin", 40),
... ]:
...     _ = User(name=name, age=age).insert()

```

A chain in one glance — nothing touches storage until the terminal call:

```pycon
>>> adults = User.find(field(User, "age") >= 18)  # lazy: no I/O yet
>>> [u.name for u in adults.sort("age", "-name").limit(3)]
['dave', 'alice', 'carol']
>>> oldest = User.find().sort("-age").first()
>>> oldest.name
'erin'
>>> User.find(field(User, "age") > 100).exists()
False

```

## The clause model

A chain is a _clause set_ — one condition, one ordering, one window — not a program. Three rules follow from that:

**Modifiers return new chains.** The original is never mutated, so a base query can be shared and refined in different directions:

```pycon
>>> by_name = adults.sort("name")
>>> by_age = adults.sort("-age")  # `adults` itself is unchanged
>>> [u.name for u in by_name.limit(2)]
['alice', 'bob']
>>> [u.name for u in by_age.limit(2)]
['erin', 'bob']

```

**Each clause is stated once.** Calling a modifier twice on the same chain raises [FindQueryError][tinydantic.FindQueryError] instead of guessing what you meant (see [Sorting](#sorting) for why guessing is dangerous):

```pycon
>>> adults.sort("name").sort("-age")
Traceback (most recent call last):
    ...
tinydantic._errors.FindQueryError: sort() was already called on this query. Clauses do not accumulate; state each clause once, combining keys in one call: .sort('name', '-age').

```

**The pipeline is fixed: match → sort → skip → limit, regardless of call order.** `limit(2).sort(...)` does _not_ mean "take two documents, then sort them" — sorting always happens before the window is cut, exactly as in SQL (`ORDER BY` before `LIMIT`) and MongoDB (cursor options, applied server-side in fixed order):

```pycon
>>> spelled_backward = User.find().limit(2).sort("-age")
>>> spelled_forward = User.find().sort("-age").limit(2)
>>> spelled_backward.all() == spelled_forward.all()
True

```

## Whole-table queries and the `None` guard

`find()` with **no argument** is the explicit whole-table spelling — useful for top-N reads that need ordering but no condition:

```pycon
>>> [u.name for u in User.find().sort("-age").limit(2)]
['erin', 'bob']

```

Passing `None` as a _value_ is a different situation: it usually means a condition variable was never set, and treating it as "the whole table" would silently widen the query to every document. tinydantic refuses at construction:

```pycon
>>> cond = None  # e.g. a filter builder returned None
>>> User.find(cond)
Traceback (most recent call last):
    ...
tinydantic._errors.SelectorError: find() got None instead of a query condition — a condition variable is unexpectedly None. To query the whole table, call find() with no argument.

```

## Sorting

Sort keys are **Python field names** (what you would pass to `getattr`), with a `-` prefix for descending. Multiple keys read left to right, most significant first:

```pycon
>>> [(u.age, u.name) for u in User.find().sort("age", "-name")]
[(25, 'dave'), (25, 'alice'), (30, 'carol'), (30, 'bob'), (40, 'erin')]

```

Ties preserve document order (Python's sort is stable), so equal-key documents come out in doc-id order. And because sorting runs on **validated model instances** — never on raw stored bodies — a `datetime` field compares chronologically, custom types compare by their real values, and every field is guaranteed to exist.

An unknown name fails at the `.sort()` call itself, not three stack frames later at the terminal, and storage aliases are not sort keys — the attribute name is:

```pycon
>>> User.find().sort("nickname")
Traceback (most recent call last):
    ...
tinydantic._errors.SortFieldError: 'nickname' is not a sortable field of 'User'. Sort keys are Python field names (not storage aliases); known fields: ['age', 'id', 'name']

```

For anything the name form cannot express — nested paths, computed keys — pass a callable instead, with `reverse=` for direction:

```pycon
>>> [u.name for u in User.find().sort(key=lambda u: (u.age, u.name), reverse=True)]
['erin', 'carol', 'bob', 'dave', 'alice']

```

The two forms are mutually exclusive; mixing field names with `key=` or `reverse=` raises `FindQueryError`.

> [!NOTE]
>
> **Why a second `.sort()` raises instead of accumulating or replacing.** The ecosystem genuinely disagrees about what `.sort("name").sort("-age")` should mean. Beanie _appends_: the second call becomes a tiebreaker behind `name`, often affecting nothing. Python's own stable-sort idiom (`xs.sort(key=name); xs.sort(key=age)`) and pandas' chained `sort_values` make the _last_ sort primary — the exact opposite priority. Django and MongoEngine _replace_, discarding the first call entirely. Whichever meaning tinydantic picked silently, users arriving from one of the other systems would get a plausible-looking but wrongly-ordered result. So repetition is an error, and the message teaches the one unambiguous spelling: state the whole ordering in one call, `.sort("name", "-age")`.

### `None` values in sorted fields

Python refuses to order `None` against numbers, and tinydantic does not invent a NULLS FIRST/LAST policy on top (databases themselves disagree on the default — any silent choice would surprise someone). A `None` in a sorted field raises `TypeError`, and the `key=` form expresses whichever placement you want, explicitly:

```pycon
>>> class Score(TinydanticModel, database=db, table_name="scores"):
...     value: int | None = None
>>> _ = Score(value=3).insert()
>>> _ = Score(value=None).insert()
>>> _ = Score(value=1).insert()
>>> Score.find().sort("value").all()
Traceback (most recent call last):
    ...
TypeError: '<' not supported between instances of 'NoneType' and 'int'
>>> [
...     s.value
...     for s in Score.find().sort(key=lambda s: (s.value is None, s.value or 0))
... ]
[1, 3, None]
>>> [
...     s.value
...     for s in Score.find().sort(
...         key=lambda s: (s.value is not None, s.value or 0)
...     )
... ]
[None, 1, 3]

```

## Terminals operate on exactly the `.all()` set

Every terminal answers about the same windowed, ordered result that [all()][tinydantic.FindQuery.all] returns — [first()][tinydantic.FindQuery.first] is `all()[0]`-or-`None`, [count()][tinydantic.FindQuery.count] counts the window (not the raw match), [exists()][tinydantic.FindQuery.exists] is its truth, and iterating a chain yields the same list:

```pycon
>>> page = User.find().sort("name").skip(1).limit(2)
>>> [u.name for u in page.all()]
['bob', 'carol']
>>> page.count()
2
>>> first = page.first()
>>> first.name
'bob'
>>> past_the_end = User.find().sort("name").skip(30)
>>> past_the_end.count(), past_the_end.exists(), past_the_end.first()
(0, False, None)

```

[first_or_raise()][tinydantic.FindQuery.first_or_raise] is the strict variant for call sites where an empty window is an error — the chain counterpart to [get_or_raise()][tinydantic.TinydanticModel.get_or_raise], raising the same [DocumentNotFoundError][tinydantic.DocumentNotFoundError]:

```pycon
>>> User.find(field(User, "age") > 100).first_or_raise()
Traceback (most recent call last):
    ...
tinydantic._errors.DocumentNotFoundError: No 'User' document in table 'users'

```

A chain itself has **no truth value** — `if User.find(cond):` would otherwise always be true, silently, forever. Use `.exists()` or `.count()`:

```pycon
>>> bool(User.find(field(User, "age") > 100))
Traceback (most recent call last):
    ...
tinydantic._errors.FindQueryError: A FindQuery has no truth value (it is a lazy query description). Use .exists() or .count().

```

Terminals execute **fresh** on every call — results are never cached on the chain, so a reused base query always reflects the current table state.

## Write terminals

[delete()][tinydantic.FindQuery.delete] and [update()][tinydantic.FindQuery.update] apply the same invariant: they operate on exactly the documents `.all()` would return — **including the sort/skip/limit window**. Under the hood they resolve the window to concrete document ids and delegate to the existing verbs, so atomicity, validation, and the curated errors are identical to [remove()][tinydantic.TinydanticModel.remove] and [update()][tinydantic.TinydanticModel.update].

> [!WARNING]
>
> This is a deliberate departure from Beanie, where `find(...).sort(...).limit(10).delete()` silently ignores the modifiers and deletes _every_ match. In tinydantic the window is honored: what you saw with `.all()` is what a write terminal touches.

The signature use case is keep-newest-N pruning — sort descending, skip the keepers, delete the rest:

```pycon
>>> _ = User(name="frank", age=50).insert()
>>> User.find().sort("-id").skip(4).delete()  # keep the 4 newest users
[2, 1]
>>> User.find().count()
4

```

`update()` mirrors the verb exactly — mapping or transform callable, the same `extra_keys=` policy, the same errors, merged-result validation, and atomic all-or-nothing writes:

```pycon
>>> User.find(field(User, "age") >= 30).sort("age").limit(2).update({"age": 35})
[3, 5]
>>> sorted(u.age for u in User.find().all())
[25, 35, 35, 50]

```

A window that matches nothing is a no-op: it returns `[]` and performs **zero storage writes** (malformed payloads still raise — passing an `id` key or an unknown field fails the same way it would on a non-empty window).

Deleting or updating the _whole table_ through a bare `find()` is legal — the no-argument spelling is explicit, so it cannot happen by accident — but [truncate()][tinydantic.TinydanticModel.truncate] and [update_all()][tinydantic.TinydanticModel.update_all] remain the idiomatic spellings: they say what they do at a glance, and `truncate()` does one storage pass instead of materializing ids first.

## Recipe: pagination

`skip`/`limit` off a shared, ordered base; `first_or_raise()` turns "this page must have a lead item" into an error your handler can catch (an HTTP handler would map it to 404):

```pycon
>>> PER_PAGE = 2
>>> listing = User.find().sort("-age")
>>> def page(n):
...     return listing.skip(n * PER_PAGE).limit(PER_PAGE).all()
>>> [u.name for u in page(0)]
['frank', 'carol']
>>> [u.name for u in page(1)]
['erin', 'dave']
>>> listing.skip(9 * PER_PAGE).limit(PER_PAGE).first_or_raise()
Traceback (most recent call last):
    ...
tinydantic._errors.DocumentNotFoundError: No 'User' document in table 'users'

```

## When a chain is overkill

A one-shot condition read needs no chain: [search()][tinydantic.TinydanticModel.search], [get()][tinydantic.TinydanticModel.get], [count()][tinydantic.TinydanticModel.count], and [contains()][tinydantic.TinydanticModel.contains] remain the direct spellings, and `find(cond).all()` is exactly `search(cond)`. Reach for `find()` when ordering, windowing, or a reusable base query enters the picture — the conditions themselves are the same ones described on the [Queries](queries.md) page, including [querying by id](queries.md).
