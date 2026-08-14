# Upstream Limitations

`tinydantic` is a thin layer over two upstream projects: [TinyDB](https://github.com/msiemens/tinydb) supplies the storage and query engine, [Pydantic](https://github.com/pydantic/pydantic) supplies the model and validation machinery. This page documents the places where those projects' current implementations cause friction for `tinydantic`, the workarounds we carry because of them, and the improvements we would suggest upstream. Each section is written so that a maintainer of the project in question can read it standalone and understand the limitation, why it matters to an ODM layered on top, and what change would resolve it.

There is one section per upstream project — [TinyDB](#tinydb) and [Pydantic](#pydantic) — and each carries its own private-API registry and its own resolved-upstream log.

Two project policies anchor this page (see `AGENTS.md`):

- `tinydantic` prefers each upstream project's public API. An internal/private API (underscore-prefixed, or living in a module marked private) may be used only when the needed behavior is impossible through the public API, only with explicit approval during planning/review, and every such use must be documented in that project's registry ([TinyDB](#tinydb-private-api-usage-registry), [Pydantic](#pydantic-private-api-usage-registry)) with its reason and the upstream change that would make it unnecessary.
- Every limitation and every private-API use also has a **tracking issue** in the `tinydantic` repository, labelled `upstream`, linked from its section or registry row here. Filing that issue is required as soon as the friction is found — including when the decision is to carry the workaround indefinitely. This page is the durable explanation; the issue is the unit of work.
- Proposals to an upstream project are drafted **in that tracking issue** and are never filed on the upstream project's tracker without explicit maintainer approval. Agents never write to an upstream repository at all.

This page must be kept current: whenever upstream friction is found, worked around, or resolved, update the relevant section here in the same change.

Limitations that an upstream release has since fixed are moved to that project's resolved-upstream log ([TinyDB](#resolved-upstream-in-tinydb), [Pydantic](#resolved-upstream-in-pydantic)) rather than deleted, so the history of each workaround stays readable.

## TinyDB

All observations in this section were verified against TinyDB 4.9.0 (the minimum version `tinydantic` requires).

### Query conditions never see the document id

**Tracking issue:** [#133](https://github.com/tinydantic/tinydantic/issues/133)

**Limitation.** TinyDB evaluates every query condition against the raw document _body_ mapping — the value in the `{doc_id: body}` table dict — never against a [`Document`](https://tinydb.readthedocs.io/en/latest/api.html#tinydb.table.Document) carrying `doc_id`. All five evaluation sites behave this way: `Table.search()`, `Table.get(cond=...)`, and the updater loops inside `Table.update(cond=...)`, `Table.update_multiple()`, and `Table.remove(cond=...)`. (`Table._update_table()`'s docstring notes that skipping the `Document` wrap is a deliberate optimization.) `Table.__iter__`, `search()`, `all()`, and `get()` all _return_ `Document` instances — but none of them evaluate the condition against one. Consequently, no query object — however it is constructed — can express "document id equals 1": the id is structurally invisible to the condition, even though it sits right there as the dict key in every evaluation loop.

**Why it matters to an ODM.** Every mainstream document ODM lets users query by the model's id attribute (Beanie and ODMantic translate `Model.id` to MongoDB's `_id`; Firestore special-cases `FieldPath.documentId()` because — exactly like TinyDB — its document key is not a body field). `tinydantic` maps its `id` field to `doc_id`, so supporting `User.get(User.id == 1)` required a translation layer: id-bearing conditions are detected in every model method and executed via `Table.update(doc_ids=…)`/`Table.remove(doc_ids=…)` operations or by iterating the table (the one API that hands the condition a `Document`). See `src/tinydantic/_query.py` and the id-condition branches in `src/tinydantic/_model.py`.

**Suggested improvement.** An opt-in protocol that keeps the existing fast path free:

1. Give `QueryInstance` a `needs_doc_id: bool = False` attribute, propagated through `__and__`/`__or__`/`__invert__` (`self.needs_doc_id or other.needs_doc_id`).
2. Add a `DocId` query type to `tinydb.queries` whose comparisons build `QueryInstance`s with `needs_doc_id=True` and test `doc.doc_id`.
3. At each of the five evaluation sites: `if getattr(cond, "needs_doc_id", False)`, wrap the body in `self.document_class(doc, self.document_id_class(doc_id))` before calling the condition; otherwise call it with the raw body exactly as today.

Existing queries and third-party `QueryLike` objects pay nothing (the `getattr` default preserves current behavior); id queries work in every API including `update_multiple()`; the storage format is untouched. This would let `tinydantic` delete its entire translation layer.

### `Table.update_multiple()` cannot select documents by id

**Tracking issue:** [#134](https://github.com/tinydantic/tinydantic/issues/134)

**Limitation.** `Table.update(fields, cond, doc_ids)` and `Table.remove(cond, doc_ids)` both accept a `doc_ids` selector, but `Table.update_multiple(updates)` accepts only `(fields, cond)` pairs. Combined with the evaluation limitation above, there is no way to run a batched update that targets documents by id — neither via a condition (conditions cannot see ids) nor via an explicit selector (the parameter does not exist).

**Why it matters to an ODM.** `Table.update_multiple()` is TinyDB's only batched write — the whole batch runs in one atomic read-modify-write cycle (`Table._update_table()`), which is the reason to use it over looping `Table.update()`. `tinydantic` translates id conditions to `doc_ids=` operations where a public landing spot exists, but `Table.update_multiple()` offers none, so supporting id conditions in `tinydantic`'s own [`update_many()`][tinydantic.TinydanticModel.update_many] wrapper (without sacrificing the batch's single-write atomicity) required the private-API use recorded in the [registry below](#tinydb-private-api-usage-registry).

**Suggested improvement.** Either of:

- Accept an optional per-pair id selector, e.g. `update_multiple(updates: Iterable[tuple[fields, cond | None, doc_ids | None]])` (or a parallel `update_multiple_by_ids()`), mirroring the `update()`/`remove()` signatures.
- Ship the `needs_doc_id`/`DocId` improvement above, which subsumes this: id conditions would then work in `update_multiple()`'s existing signature.

### `Table.upsert()` silently ignores the condition when the document carries a `doc_id`

**Tracking issue:** [#148](https://github.com/tinydantic/tinydantic/issues/148)

**Limitation.** `Table.upsert(document, cond)` treats its two selectors as either/or: when `document` is a [`Document`](https://tinydb.readthedocs.io/en/latest/api.html#tinydb.table.Document) carrying a `doc_id`, the implementation extracts that id and calls `Table.update(document, cond, doc_ids=[doc_id])` — and `update()` checks `doc_ids` before `cond`, so a condition passed alongside a `Document` is **never evaluated**. Nothing raises or warns; the call simply performs a different operation (upsert by id) than the one written (upsert by condition). Consequently the public API cannot express "update the documents matching this condition; if none match, insert at this specific id": passing both selects by id and silently drops the condition, while a plain dict body cannot carry an id into the fall-through insert.

**Why it matters to an ODM.** `tinydantic` maps its `id` field to `doc_id`, and its [`upsert()`][tinydantic.TinydanticModel.upsert] honors a set `document.id` on the no-match insert exactly as [`insert()`][tinydantic.TinydanticModel.insert] does — a set id says "put it here" (tinydantic [#120](https://github.com/tinydantic/tinydantic/issues/120) fixed the earlier behavior of silently discarding it). Expressing that means serializing the model as a `Document` so its id survives to the insert — and handing that `Document` plus the user's condition to `Table.upsert()` would silently turn every condition-upsert into an id-upsert. `TinydanticModel.upsert()` (`src/tinydantic/_model.py`) therefore inlines upstream's own update-then-insert instead of delegating: `Table.update(document, cond)` first, and when nothing matched, `Table.insert(document)` with the id-bearing `Document` — public API throughout, the same two storage cycles `Table.upsert()` itself spends, with the insert's "id already taken" `ValueError` translated to [`DocumentAlreadyExistsError`][tinydantic.DocumentAlreadyExistsError]. (Id-bearing _conditions_ take the atomic private-API path recorded in the [registry below](#tinydb-private-api-usage-registry) for other reasons.)

**Suggested improvement.** When both selectors are supplied, either honor the condition — evaluate `cond`, with the `doc_id` seeding only the fall-through insert, which is strictly more expressive and is what the call reads as — or refuse the combination with a `ValueError`, as the doc_id-less-and-cond-less call already does. Either is better than the silent precedence; at minimum, the docstring ("optional if you've passed a Document with a doc_id") should state that a `Document`'s id does not merely make `cond` optional but overrides it entirely.

### `Query.matches()` is documented as whole-value and anchors only at the start

**Tracking issue:** [#144](https://github.com/tinydantic/tinydantic/issues/144)

**Limitation.** [`Query.matches()`](https://tinydb.readthedocs.io/en/latest/api.html#tinydb.queries.Query.matches) documents itself as "Run a regex test against a dict value (whole string has to match)" and implements the test with `re.match`, which anchors at the start of the value only. `matches(r".*@example\.com")` therefore matches `"alice@example.com.evil"`. `re.fullmatch` is the function the docstring describes; `Query.search()` (the deliberately unanchored spelling) uses `re.search`.

**Why it matters to an ODM.** The pattern users reach for is an allow-list — "this field must look like _this_" — and the docstring tells them it is one. It is not, and nothing about the result says so: the query returns rows, just more of them than intended. `tinydantic` presents these builders as its primary query API and had copied the upstream wording verbatim into `GuardedQuery.matches()` and the [Queries](../usage/queries.md) page, so the same wrong contract was published twice more.

There is no code workaround, and none is wanted: changing the behavior would silently narrow every existing caller's results. `tinydantic` carries the correction in prose instead — `GuardedQuery.matches()` (`src/tinydantic/_query.py`) and the Queries page both name the anchoring and point at `$`.

**Suggested improvement.** Correct the docstring — "the pattern is matched against the start of the value (`re.match`); end it with `$` to require a whole-value match" — and, optionally, add a `fullmatch=` flag or a `Query.fullmatch()` builder for the behavior the current wording promises. A behavior change to `re.fullmatch` is explicitly _not_ proposed.

### `Table.update(doc_ids=…)` and `Table.remove(doc_ids=…)` skip missing ids silently

**Tracking issue:** [#135](https://github.com/tinydantic/tinydantic/issues/135)

**Limitation.** As of TinyDB 4.9.0 ([#591](https://github.com/msiemens/tinydb/issues/591)), `Table.update(fields, doc_ids=…)` and `Table.remove(doc_ids=…)` filter the requested ids down to those present in the table, operate on that subset, and return only the ids they actually touched. An id that does not exist is not reported in any way. Before 4.9.0 the same call raised a bare `KeyError` partway through the updater — which was its own problem (an uncurated exception, raised after some documents had already been mutated in the working copy).

**Why it matters to an ODM.** The new behavior makes a mixed batch a **partial write that reports success**: `update(fields, doc_ids=[1, 999])` on a table without document 999 updates document 1, returns `[1]`, and leaves the caller to notice that the returned list is shorter than the one they passed. A typo'd id in a batch is silently a different operation than the one requested. That is precisely the silent-wrong failure mode `tinydantic` exists to eliminate, and the returned-list-length check that would catch it is exactly the kind of bookkeeping users do not write.

`tinydantic` therefore keeps `TinydanticModel._check_doc_ids_exist()` (`src/tinydantic/_model.py`), which reads the table once and raises [`DocumentNotFoundError`][tinydantic.DocumentNotFoundError] for the first id that is absent, **before** any write is attempted. It backs [`update_by_ids()`][tinydantic.TinydanticModel.update_by_ids] and [`remove_by_ids()`][tinydantic.TinydanticModel.remove_by_ids], so a batch naming a missing id is refused whole rather than applied in part — all-or-nothing across both the validated and `validate_writes=False` paths. The cost is one extra table read per id-selected write.

`tinydantic` applies the same assertion to reads: [`get_by_ids()`][tinydantic.TinydanticModel.get_by_ids] refuses a batch naming an absent id rather than mirroring `Table.get(doc_ids=…)`, which silently returns a shorter list in storage order. Asserting also makes the read _positional_ — one document per id, in the caller's order — which the upstream behavior cannot promise. Best-effort selection stays available through conditions (`search(Model.id.one_of(...))`), which filter by design.

**Suggested improvement.** Return enough information to distinguish "skipped" from "done", or let the caller choose. Either a `strict: bool = False` parameter on `update()`/`remove()` that raises a dedicated `MissingDocumentIDError` naming the absent ids, or a documented guarantee that the returned list can be compared against the requested one (plus a note in the docstring that it _must_ be, to detect partial application).

### Document ids are stringified before reaching storages

**Tracking issue:** [#136](https://github.com/tinydantic/tinydantic/issues/136)

**Limitation.** Before table data is handed to the storage layer, document ids are converted to strings (`{str(doc_id): doc}` in `Table._update_table()`), because the reference JSON storage requires string keys. Storages and middlewares therefore never see the native int ids, and serialized output sorts ids lexicographically (`"10"` before `"2"`). See the upstream discussion [msiemens/tinydb#466](https://github.com/msiemens/tinydb/discussions/466).

**Why it matters.** Human-readable storage output (a design goal of `tinydantic`'s YAML storage) lists documents in confusing lexicographic order. `tinydantic` ships `SortIntDocIDsMiddleware` (`src/tinydantic/tinydb/middlewares.py`) purely to undo the stringification — it converts keys back to ints, pre-sorted numerically — and that middleware has to pass ints where the `Storage` protocol declares strings, an acknowledged hack.

**Suggested improvement.** Let storages opt into native id keys (for example, a class attribute on `Storage` declaring whether keys must be strings), or perform the stringification inside `JSONStorage` rather than in `Table`, so key formatting becomes a storage concern.

### Query objects answer `bool()` and `in` silently

**Tracking issue:** [#137](https://github.com/tinydantic/tinydantic/issues/137)

**Limitation.** `QueryInstance` defines no `__bool__` and no `__len__`, so every condition is truthy — `bool(where("name") == "Alice")` is `True`, and so is the same expression for a value no document holds. `Query` additionally defines `__getitem__` (the alternate spelling for nested keys) but no `__iter__`, so Python's legacy sequence protocol makes `x in Query().name` iterate the query and report `True` for any `x`. A non-string path step is read as a callable to apply (`_generate_test`'s runner), so `Query().tags[0] == "red"` raises internally, is swallowed by the runner's `except (KeyError, TypeError)`, and matches nothing.

**Why it matters.** `tinydantic` presents these objects as its primary query API, so `if User.name == requested:` reads like an existence check, passes review, and is permanently true. `tinydantic` therefore ships `GuardedQuery`/`GuardedCondition` (`src/tinydantic/_query.py`), which raise `QueryTypeError` for all three. Because TinyDB constructs conditions with `QueryInstance(...)` directly — a `Query` subclass cannot change what its own comparisons return — the guard is applied by reassigning `__class__` on the object TinyDB just built. That uses no private names and preserves the test function and hashval (so guarded conditions still compare, hash, and cache identically), but it does depend on `QueryInstance` remaining a plain, `__slots__`-free class. Each of the ~15 public condition builders is overridden to apply it; a builder added by a future TinyDB would return an unguarded condition, degrading to today's behavior rather than breaking.

**Suggested improvement.** Define `__bool__` on `QueryInstance` (and `__iter__` on `Query`) to raise `TypeError`, following the numpy/pandas ambiguous-truth precedent; reject non-string path steps in `__getitem__`. Failing that, a public hook for the condition type a `Query` subclass builds (for example a `condition_class` class attribute consulted by `_generate_test`) would remove the need to retag.

### TinyDB private API usage registry

Every approved use of a TinyDB internal/private API in `tinydantic` is recorded here. An empty table means the shipped code uses only the public API.

| TinyDB internal | Used by | Status | Reason | Upstream change that would remove it |
| --- | --- | --- | --- | --- |
| `QueryInstance._hash` (read-only attribute access) | `tinydantic._query.has_id_condition()` — detecting id conditions inside composed queries | **In use** (approved 2026-08-02; shipped with the original id-query work). Tracking: [#133](https://github.com/tinydantic/tinydantic/issues/133) | Composing queries (`&`/`\|`/`~`) produces plain `QueryInstance` objects, so a custom condition type cannot survive composition — the hashval tree is the only place a marker does. The access is read-only via `getattr(cond, "_hash", None)` and degrades loudly, never silently: if a future TinyDB renames the attribute, bare id conditions are still detected by `isinstance`, and undetected compositions raise `DocumentIDConditionError` when TinyDB's evaluator runs them. | The `needs_doc_id`/`DocId` evaluator improvement above (composition would propagate a public flag); alternatively, a public accessor for a query's hash tree. |
| `Table._update_table(updater)` | `TinydanticModel._run_write_cycle()` — all `update()`/`update_by_ids()`/`update_all()`/`update_many()` writes (which validate each matched document's merged result unless `validate_writes=False`), plus the id-condition paths of `remove()` and `upsert()` | **In use** (approved 2026-07-13 for id-condition writes; scope extended 2026-08-02 to all validated update writes). Tracking: [#134](https://github.com/tinydantic/tinydantic/issues/134) | The only way to select write targets by id inside one atomic read-modify-write cycle, and the only way to validate-then-write atomically: `Table.update_multiple()` has no `doc_ids` parameter, conditions cannot see ids (the two limitations above), and a public two-pass validate-then-update has a read-modify-write race between passes. The custom updater evaluates every condition against `Document(body, doc_id)` wrappers inside upstream's own read → mutate → write → cache-clear lifecycle, validates merged bodies before the write, applies mutations copy-on-write (so an aborted or validation-failed cycle leaks nothing, even on `MemoryStorage`, whose `read()` shares body dicts by reference), and skips the storage write entirely when nothing matched. Benchmarked ~23% faster than the two-pass public-API alternative on a 5,000-document JSONStorage table (one full file read saved per write). | Either the `update_multiple()` improvement above plus an atomic validate-hook, or the `needs_doc_id`/`DocId` evaluator change combined with a public batched read-modify-write API. |

### Resolved upstream in TinyDB

Limitations recorded here that a later TinyDB release has fixed. They are kept so the history of each workaround stays readable, and so a reader can tell "we never hit this" apart from "we hit it and it is gone now".

#### `update()` field mappings were mistyped as callables

**Resolved in TinyDB 4.9.0** ([#621](https://github.com/msiemens/tinydb/pull/621), plus the matching retype of `tinydb.operations`).

`Table.update()` and `Table.update_multiple()` annotated their `fields` parameter as `Mapping | Callable[[Mapping], None]`. The transform they actually invoke is handed a mutable `dict`, so a correctly-typed `Callable[[MutableMapping], None]` transform was _rejected_ by static type checkers under parameter contravariance — the documented, working call was the one that failed to type-check.

Every `tinydantic` call into these methods carried a `cast("Callable[[Mapping], None]", …)` band-aid marked `TODO @cdwilson: remove this cast once the annotation is fixed in TinyDB`. TinyDB 4.9.0 retyped the parameter to `Mapping | Callable[[MutableMapping], None]`, which is exactly the signature `tinydantic.tinydb.operations.replace()` already advertised, so all four casts were deleted (`src/tinydantic/_model.py`) along with an internal `cast("dict[str, Any]", body)` inside `TinydanticModel._rotated()`.

#### `Query.test()` raised on unhashable arguments

**Resolved in TinyDB 4.9.0** ([#517](https://github.com/msiemens/tinydb/issues/517)).

`Query.test(func, *args)` built its hashval from the raw `args` tuple, so passing a list or dict produced a condition that raised `TypeError: unhashable type` the first time it reached the query cache. TinyDB 4.9.0 freezes the arguments (and falls back to marking a condition uncacheable rather than crashing when a value cannot be frozen).

This matters to `tinydantic` beyond the raw fix: `has_id_condition()` detects id conditions by walking `QueryInstance._hash` (see the [registry above](#tinydb-private-api-usage-registry)), so a composed query containing an unhashable `test()` argument previously lost its hashval and degraded to `DocumentIDConditionError`. Such compositions now keep their hashval and resolve normally.

#### `touch()` failed on a bare relative filename

**Resolved in TinyDB 4.9.0** ([#619](https://github.com/msiemens/tinydb/pull/619)).

`tinydb.storages.touch()` derived the parent directory with `os.path.dirname(path)` and, for a path with no directory part, called `os.makedirs("")` — raising `FileNotFoundError`. `tinydantic`'s `YAMLStorage` calls that helper directly, so `TinyDB("db.yaml", storage=YAMLStorage, create_dirs=True)` failed for any bare filename; only a path with an explicit directory worked. The fix is inherited with no `tinydantic` change, and both shapes are now covered by `tests/tinydb/storages/test_yaml_storage.py`.

## Pydantic

All observations in this section were verified against Pydantic 2.11 (the minimum version `tinydantic` requires) and re-checked against 2.13.

### `model_config` merges across bases in "last wins" order, not MRO

**Tracking issue:** [#138](https://github.com/tinydantic/tinydantic/issues/138)

**Limitation.** Pydantic builds a model's effective [`model_config`][pydantic.BaseModel.model_config] by walking the bases left to right and letting each one overwrite what came before, so the _last_ base to set a key wins. Python's MRO says the _first_ one does. The two orderings are exact opposites, and nothing warns when they disagree ([pydantic#9992](https://github.com/pydantic/pydantic/issues/9992), open, carrying the v3 milestone):

```python
class A(BaseModel):
    model_config = ConfigDict(strict=True)


class B(BaseModel):
    model_config = ConfigDict(strict=False)


class C(A, B):
    pass


C.__mro__  # (C, A, B, BaseModel, object) — A wins under Python's rules
C.model_config["strict"]  # False — B wins under Pydantic's
```

Every other attribute on `C` — methods, class variables, `__tinydantic_config__` — resolves through `A`. Only `model_config` resolves through `B`.

**Why it matters to an ODM.** An ODM's configuration decides _where writes land_. `tinydantic` models are bound to a database and a table (`database=`, `table_name=`), and mixin-plus-base composition is the normal way to build them: a `Timestamped` mixin combined with a base class that carries the binding, or two bases that each bind a different database. Under "last wins", `class Report(ProductionBase, ScratchBase)` would read its binding from `ScratchBase` while every reader of the code — and every other attribute on the class — says `ProductionBase`. That is not a misconfigured flag; it is documents silently written to the wrong table, discovered later or never.

`tinydantic` therefore keeps its configuration out of `model_config` entirely. Each class stores only the keys explicitly set on it in its own `__tinydantic_config__` attribute, and lookup walks `cls.__mro__` for the first class that provides the key — plain Python attribute semantics, which is what a reader already expects. For the one case where the two orderings could genuinely disagree (two _unrelated_ bases providing conflicting values for the same key), `tinydantic` refuses to guess and raises [`AmbiguousConfigError`][tinydantic.AmbiguousConfigError] at class-definition time. See `src/tinydantic/_config.py` and the [Configuration](../usage/configuration.md#design-notes-why-config-is-not-in-model_config) page.

The cost of the workaround is real but small: `tinydantic` config does not show up in `model_config`, and users who expect one config dict have two to learn.

**Suggested improvement.** Merge `model_config` in MRO order — `for base in reversed(cls.__mro__)` rather than left-to-right over `bases` — so config resolution matches every other attribute on the class. That is a breaking change for models that today depend on the inverted order, which is presumably why it carries the v3 milestone. A non-breaking interim step would help downstream libraries regardless: warn at class-creation time when two bases set the same `model_config` key to different values, which is exactly the case where the current order is doing something the reader did not ask for.

### `protected_namespaces` replaces the default instead of extending it

**Tracking issue:** [#139](https://github.com/tinydantic/tinydantic/issues/139)

**Limitation.** `protected_namespaces` is an ordinary `ConfigDict` key, so setting it on a subclass _replaces_ the inherited value rather than adding to it. A library that wants to reserve its own prefix has to restate Pydantic's defaults alongside it, and there is no public constant to restate them from — the value lives in `pydantic._internal._config.config_defaults`. Forgetting to restate them is silent: nothing warns that a model just gave up namespace protection.

```python
class Plain(BaseModel):
    # UserWarning: conflicts with protected namespace 'model_dump'
    model_dump_toml: str


class Own(BaseModel):
    model_config = ConfigDict(protected_namespaces=("app_",))
    # no warning at all — Pydantic's default is gone, not extended
    model_dump_toml: str
```

**Why it matters to an ODM.** `tinydantic` reserves the `tinydantic_` prefix so that a method added in a future release cannot collide with a field name a user has already stored — the use case Samuel Colvin described in [pydantic#10315](https://github.com/pydantic/pydantic/issues/10315) when the `model_` default was narrowed. Setting `protected_namespaces=("tinydantic_",)` did exactly that, and silently dropped Pydantic's own forward-compat protection for `model_validate*`/`model_dump*` names.

That gap is narrower than it first looks, because `tinydantic` already refuses field names that collide with an attribute that exists _today_: `ShadowedFieldError` covers every attribute on the class, where Pydantic's namespaces cover two prefixes. A field named `model_dump_json` is refused by `tinydantic` either way. What the dropped default cost was protection against names Pydantic might claim _tomorrow_ — a field named `model_dump_toml` was accepted with no warning, and would start raising `ShadowedFieldError` at import time the day a Pydantic release adds that method, with the name already baked into stored documents.

`tinydantic` now restates the defaults explicitly (`src/tinydantic/_model.py`):

```python
protected_namespaces = ("tinydantic_", "model_validate", "model_dump")
```

so a `tinydantic` model is never _less_ protected than the plain `BaseModel` a user would otherwise have written. The literal is a copy of a private default, so it needs re-checking whenever the Pydantic floor moves — `tests/model/test_model_config.py` reads the default out of Pydantic and asserts `tinydantic`'s tuple still covers it, so a Pydantic release that reserves a new prefix fails the suite rather than quietly losing the protection.

**Suggested improvement.** Either export the default as a public constant (`pydantic.config.DEFAULT_PROTECTED_NAMESPACES`) so downstream libraries can extend rather than copy it, or make `protected_namespaces` accumulate across the MRO the way a set of reservations naturally should — a subclass reserving its own prefix almost never means "and drop the ones my base reserved". The second is the smaller change for users and removes the failure mode entirely.

### Pydantic private API usage registry

Every approved use of a Pydantic internal/private API in `tinydantic` is recorded here.

| Pydantic internal | Used by | Status | Reason | Upstream change that would remove it |
| --- | --- | --- | --- | --- |
| `pydantic._internal._model_construction.ModelMetaclass` (name only, under `TYPE_CHECKING`) | `TinydanticModelMetaclass`, the metaclass of `TinydanticModel` (`src/tinydantic/_model.py`) | **In use** (shipped with the original model work; recorded here 2026-08-08). Tracking: [#140](https://github.com/tinydantic/tinydantic/issues/140) | `tinydantic` must run at class-creation time — to capture `database=`/`table_name=` class keywords, resolve `__tinydantic_config__`, and detect shadowed fields — which requires subclassing `BaseModel`'s metaclass. Pydantic exports no public name for it. The exposure is limited to type-checking: the import sits in an `if TYPE_CHECKING` block and the runtime branch resolves the same class as `type(BaseModel)`, so no Pydantic internal is imported at runtime and moving the module would not break an installed `tinydantic`. | A public re-export, e.g. `pydantic.ModelMetaclass`, so the type-checking import can name a supported path. |
| `pydantic._internal._config.config_defaults["protected_namespaces"]` (test-only) | `tests/model/test_model_config.py` — asserting `tinydantic`'s reservations still cover Pydantic's defaults | **In use** (added with the `protected_namespaces` fix above). Tracking: [#139](https://github.com/tinydantic/tinydantic/issues/139) | The default has no public accessor, and the alternative to reading it is hard-coding the same tuple in the test that is supposed to catch it drifting. Test-only, so no shipped code depends on it; if Pydantic moves the attribute the test fails loudly rather than silently passing. | The `DEFAULT_PROTECTED_NAMESPACES` constant suggested above. |

### Resolved upstream in Pydantic

Limitations recorded here that a later Pydantic release has fixed.

#### The whole `model_` prefix was reserved by default

**Resolved in Pydantic 2.10** ([#10315](https://github.com/pydantic/pydantic/issues/10315), [PR #10441](https://github.com/pydantic/pydantic/pull/10441)).

`protected_namespaces` defaulted to `("model_",)`, so any field beginning with `model_` drew a `UserWarning` — including ordinary domain vocabulary such as `model_id`, `model_name`, or `model_version`, none of which collide with anything Pydantic defines. The advertised escape (`model_config["protected_namespaces"] = ()`) turned the protection off wholesale, which is a poor trade for a false positive. Pydantic 2.10 narrowed the default to `("model_validate", "model_dump")`, so only names that plausibly shadow a real method are flagged.

`tinydantic`'s floor is Pydantic 2.11, so this is inherited with no `tinydantic` change and no advice for users to work around. It also made restating the defaults cheap enough to be the right fix for the [limitation above](#protected_namespaces-replaces-the-default-instead-of-extending-it): copying a two-entry list of method-name prefixes is defensible, where copying a blanket `model_` reservation would not have been.
