# TinyDB Limitations

This page documents the places where TinyDB's current implementation causes friction for `tinydantic`, the workarounds we carry because of them, and the improvements we would suggest upstream. It is written so that a TinyDB maintainer can read any section standalone and understand the limitation, why it matters to an ODM layered on top, and what change would resolve it.

Two project policies anchor this page (see `AGENTS.md`):

- `tinydantic` prefers TinyDB's public API. An internal/private TinyDB API (underscore-prefixed) may be used only when the needed behavior is impossible through the public API, only with explicit approval during planning/review, and every such use must be documented in the [registry below](#private-api-usage-registry) with its reason and the upstream change that would make it unnecessary.
- Proposals to TinyDB are drafted in `upstream/` (at the repository root) and are never filed on the TinyDB issue tracker without explicit approval.

This page must be kept current: whenever TinyDB friction is found, worked around, or resolved, update the relevant section here in the same change.

All observations below were verified against TinyDB 4.9.0 (the minimum version `tinydantic` requires). Limitations that a TinyDB release has since fixed are moved to [Resolved upstream](#resolved-upstream) rather than deleted, so the history of each workaround stays readable.

## Query conditions never see the document id

**Limitation.** TinyDB evaluates every query condition against the raw document _body_ mapping — the value in the `{doc_id: body}` table dict — never against a [`Document`](https://tinydb.readthedocs.io/en/latest/api.html#tinydb.table.Document) carrying `doc_id`. All five evaluation sites behave this way: `Table.search()`, `Table.get(cond=...)`, and the updater loops inside `Table.update(cond=...)`, `Table.update_multiple()`, and `Table.remove(cond=...)`. (`Table._update_table()`'s docstring notes that skipping the `Document` wrap is a deliberate optimization.) Only `Table.__iter__` yields `Document` instances. Consequently, no query object — however it is constructed — can express "document id equals 1": the id is structurally invisible to the condition, even though it sits right there as the dict key in every evaluation loop.

**Why it matters to an ODM.** Every mainstream document ODM lets users query by the model's id attribute (Beanie and ODMantic translate `Model.id` to MongoDB's `_id`; Firestore special-cases `FieldPath.documentId()` because — exactly like TinyDB — its document key is not a body field). `tinydantic` maps its `id` field to `doc_id`, so supporting `User.get(User.id == 1)` required a translation layer: id-bearing conditions are detected in every model method and executed via `doc_id=`/`doc_ids=` operations or by iterating the table (the one API that yields `Document`s). See `src/tinydantic/_query.py` and the id-condition branches in `src/tinydantic/_model.py`.

**Suggested improvement.** An opt-in protocol that keeps the existing fast path free:

1. Give `QueryInstance` a `needs_doc_id: bool = False` attribute, propagated through `__and__`/`__or__`/`__invert__` (`self.needs_doc_id or other.needs_doc_id`).
2. Add a `DocId` query type to `tinydb.queries` whose comparisons build `QueryInstance`s with `needs_doc_id=True` and test `doc.doc_id`.
3. At each of the five evaluation sites: `if getattr(cond, "needs_doc_id", False)`, wrap the body in `self.document_class(doc, self.document_id_class(doc_id))` before calling the condition; otherwise call it with the raw body exactly as today.

Existing queries and third-party `QueryLike` objects pay nothing (the `getattr` default preserves current behavior); id queries work in every API including `update_multiple()`; the storage format is untouched. This would let `tinydantic` delete its entire translation layer.

## `update_multiple()` cannot select documents by id

**Limitation.** `Table.update(fields, cond, doc_ids)` and `Table.remove(cond, doc_ids)` both accept a `doc_ids` selector, but `Table.update_multiple(updates)` accepts only `(fields, cond)` pairs. Combined with the evaluation limitation above, there is no way to run a batched update that targets documents by id — neither via a condition (conditions cannot see ids) nor via an explicit selector (the parameter does not exist).

**Why it matters to an ODM.** `update_multiple()` is TinyDB's only batched write — the whole batch runs in one atomic read-modify-write cycle (`Table._update_table()`), which is the reason to use it over looping `update()`. `tinydantic` translates id conditions to `doc_ids=` operations where a public landing spot exists, but `update_multiple()` offers none, so supporting id conditions there (without sacrificing the batch's single-write atomicity) required the private-API use recorded in the [registry below](#private-api-usage-registry).

**Suggested improvement.** Either of:

- Accept an optional per-pair id selector, e.g. `update_multiple(updates: Iterable[tuple[fields, cond | None, doc_ids | None]])` (or a parallel `update_multiple_by_ids()`), mirroring the `update()`/`remove()` signatures.
- Ship the `needs_doc_id`/`DocId` improvement above, which subsumes this: id conditions would then work in `update_multiple()`'s existing signature.

## `update(doc_ids=…)` and `remove(doc_ids=…)` skip missing ids silently

**Limitation.** As of TinyDB 4.9.0 ([#591](https://github.com/msiemens/tinydb/issues/591)), `Table.update(fields, doc_ids=…)` and `Table.remove(doc_ids=…)` filter the requested ids down to those present in the table, operate on that subset, and return only the ids they actually touched. An id that does not exist is not reported in any way. Before 4.9.0 the same call raised a bare `KeyError` partway through the updater — which was its own problem (an uncurated exception, raised after some documents had already been mutated in the working copy).

**Why it matters to an ODM.** The new behavior makes a mixed batch a **partial write that reports success**: `update(fields, doc_ids=[1, 999])` on a table without document 999 updates document 1, returns `[1]`, and leaves the caller to notice that the returned list is shorter than the one they passed. A typo'd id in a batch is silently a different operation than the one requested. That is precisely the silent-wrong failure mode `tinydantic` exists to eliminate, and the returned-list-length check that would catch it is exactly the kind of bookkeeping users do not write.

`tinydantic` therefore keeps `TinydanticModel._check_doc_ids_exist()` (`src/tinydantic/_model.py`), which reads the table once and raises [`DocumentNotFoundError`][tinydantic.DocumentNotFoundError] for the first id that is absent, **before** any write is attempted. A batch naming a missing id is refused whole rather than applied in part, so `update()`/`remove()` keep all-or-nothing semantics across both the validated and `validate_writes=False` paths. The cost is one extra table read per id-selected write.

Note that this is deliberately _stricter_ than `Table.get(doc_ids=…)`, which has always skipped missing ids and which `tinydantic` mirrors as-is — a read that returns fewer documents than requested is self-describing, whereas a write that silently narrows its own target set is not.

**Suggested improvement.** Return enough information to distinguish "skipped" from "done", or let the caller choose. Either a `strict: bool = False` parameter on `update()`/`remove()` that raises a dedicated `MissingDocumentIDError` naming the absent ids, or a documented guarantee that the returned list can be compared against the requested one (plus a note in the docstring that it _must_ be, to detect partial application).

## Document ids are stringified before reaching storages

**Limitation.** Before table data is handed to the storage layer, document ids are converted to strings (`{str(doc_id): doc}` in `Table._update_table()`), because the reference JSON storage requires string keys. Storages and middlewares therefore never see the native int ids, and serialized output sorts ids lexicographically (`"10"` before `"2"`). See the upstream discussion [msiemens/tinydb#466](https://github.com/msiemens/tinydb/discussions/466).

**Why it matters.** Human-readable storage output (a design goal of `tinydantic`'s YAML storage) lists documents in confusing lexicographic order. `tinydantic` ships `SortIntDocIDsMiddleware` (`src/tinydantic/tinydb/middlewares.py`) purely to undo the stringification — it converts keys back to ints, pre-sorted numerically — and that middleware has to pass ints where the `Storage` protocol declares strings, an acknowledged hack.

**Suggested improvement.** Let storages opt into native id keys (for example, a class attribute on `Storage` declaring whether keys must be strings), or perform the stringification inside `JSONStorage` rather than in `Table`, so key formatting becomes a storage concern.

## Query objects answer `bool()` and `in` silently

**Limitation.** `QueryInstance` defines no `__bool__` and no `__len__`, so every condition is truthy — `bool(where("name") == "Alice")` is `True`, and so is the same expression for a value no document holds. `Query` additionally defines `__getitem__` (the alternate spelling for nested keys) but no `__iter__`, so Python's legacy sequence protocol makes `x in Query().name` iterate the query and report `True` for any `x`. A non-string path step is read as a callable to apply (`_generate_test`'s runner), so `Query().tags[0] == "red"` raises internally, is swallowed by the runner's `except (KeyError, TypeError)`, and matches nothing.

**Why it matters.** `tinydantic` presents these objects as its primary query API, so `if User.name == requested:` reads like an existence check, passes review, and is permanently true. `tinydantic` therefore ships `GuardedQuery`/`GuardedCondition` (`src/tinydantic/_query.py`), which raise `QueryConditionError` for all three. Because TinyDB constructs conditions with `QueryInstance(...)` directly — a `Query` subclass cannot change what its own comparisons return — the guard is applied by reassigning `__class__` on the object TinyDB just built. That uses no private names and preserves the test function and hashval (so guarded conditions still compare, hash, and cache identically), but it does depend on `QueryInstance` remaining a plain, `__slots__`-free class. Each of the ~15 public condition builders is overridden to apply it; a builder added by a future TinyDB would return an unguarded condition, degrading to today's behavior rather than breaking.

**Suggested improvement.** Define `__bool__` on `QueryInstance` (and `__iter__` on `Query`) to raise `TypeError`, following the numpy/pandas ambiguous-truth precedent; reject non-string path steps in `__getitem__`. Failing that, a public hook for the condition type a `Query` subclass builds (for example a `condition_class` class attribute consulted by `_generate_test`) would remove the need to retag.

## Private API usage registry

Every approved use of a TinyDB internal/private API in `tinydantic` is recorded here. An empty table means the shipped code uses only the public API.

| TinyDB internal | Used by | Status | Reason | Upstream change that would remove it |
| --- | --- | --- | --- | --- |
| `QueryInstance._hash` (read-only attribute access) | `tinydantic._query.has_id_condition()` — detecting id conditions inside composed queries | **In use** (approved 2026-08-02; shipped with the original id-query work) | Composing queries (`&`/`\|`/`~`) produces plain `QueryInstance` objects, so a custom condition type cannot survive composition — the hashval tree is the only place a marker does. The access is read-only via `getattr(cond, "_hash", None)` and degrades loudly, never silently: if a future TinyDB renames the attribute, bare id conditions are still detected by `isinstance`, and undetected compositions raise `DocumentIDConditionError` when TinyDB's evaluator runs them. | The `needs_doc_id`/`DocId` evaluator improvement above (composition would propagate a public flag); alternatively, a public accessor for a query's hash tree. |
| `Table._update_table(updater)` | `TinydanticModel._run_write_cycle()` — all `update()`/`update_multiple()` writes (which validate each matched document's merged result unless `validate_writes=False`), plus the id-condition paths of `remove()` and `upsert()` | **In use** (approved 2026-07-13 for id-condition writes; scope extended 2026-08-02 to all validated update writes) | The only way to select write targets by id inside one atomic read-modify-write cycle, and the only way to validate-then-write atomically: `update_multiple()` has no `doc_ids` parameter, conditions cannot see ids (the two limitations above), and a public two-pass validate-then-update has a read-modify-write race between passes. The custom updater evaluates every condition against `Document(body, doc_id)` wrappers inside upstream's own read → mutate → write → cache-clear lifecycle, validates merged bodies before the write, applies mutations copy-on-write (so an aborted or validation-failed cycle leaks nothing, even on `MemoryStorage`, whose `read()` shares body dicts by reference), and skips the storage write entirely when nothing matched. Benchmarked ~23% faster than the two-pass public-API alternative on a 5,000-document JSONStorage table (one full file read saved per write). | Either `update_multiple()` improvement above plus an atomic validate-hook, or the `needs_doc_id`/`DocId` evaluator change combined with a public batched read-modify-write API. |

## Resolved upstream

Limitations recorded here that a later TinyDB release has fixed. They are kept so the history of each workaround stays readable, and so a reader can tell "we never hit this" apart from "we hit it and it is gone now".

### `update()` field mappings were mistyped as callables

**Resolved in TinyDB 4.9.0** ([#621](https://github.com/msiemens/tinydb/pull/621), plus the matching retype of `tinydb.operations`).

`Table.update()` and `Table.update_multiple()` annotated their `fields` parameter as `Mapping | Callable[[Mapping], None]`. The transform they actually invoke is handed a mutable `dict`, so a correctly-typed `Callable[[MutableMapping], None]` transform was _rejected_ by static type checkers under parameter contravariance — the documented, working call was the one that failed to type-check.

Every `tinydantic` call into these methods carried a `cast("Callable[[Mapping], None]", …)` band-aid marked `TODO @cdwilson: remove this cast once the annotation is fixed in TinyDB`. TinyDB 4.9.0 retyped the parameter to `Mapping | Callable[[MutableMapping], None]`, which is exactly the signature `tinydantic.tinydb.operations.replace()` already advertised, so all four casts were deleted (`src/tinydantic/_model.py`) along with an internal `cast("dict[str, Any]", body)` inside `TinydanticModel._rotated()`.

### `Query.test()` raised on unhashable arguments

**Resolved in TinyDB 4.9.0** ([#517](https://github.com/msiemens/tinydb/issues/517)).

`Query.test(func, *args)` built its hashval from the raw `args` tuple, so passing a list or dict produced a condition that raised `TypeError: unhashable type` the first time it reached the query cache. TinyDB 4.9.0 freezes the arguments (and falls back to marking a condition uncacheable rather than crashing when a value cannot be frozen).

This matters to `tinydantic` beyond the raw fix: `has_id_condition()` detects id conditions by walking `QueryInstance._hash` (see the [registry below](#private-api-usage-registry)), so a composed query containing an unhashable `test()` argument previously lost its hashval and degraded to `DocumentIDConditionError`. Such compositions now keep their hashval and resolve normally.

### `touch()` failed on a bare relative filename

**Resolved in TinyDB 4.9.0** ([#619](https://github.com/msiemens/tinydb/pull/619)).

`tinydb.storages.touch()` derived the parent directory with `os.path.dirname(path)` and, for a path with no directory part, called `os.makedirs("")` — raising `FileNotFoundError`. `tinydantic`'s `YAMLStorage` calls that helper directly, so `TinyDB("db.yaml", storage=YAMLStorage, create_dirs=True)` failed for any bare filename; only a path with an explicit directory worked. The fix is inherited with no `tinydantic` change, and both shapes are now covered by `tests/tinydb/storages/test_yaml_storage.py`.
