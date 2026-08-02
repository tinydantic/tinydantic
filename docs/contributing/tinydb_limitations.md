# TinyDB Limitations

This page documents the places where TinyDB's current implementation causes friction for `tinydantic`, the workarounds we carry because of them, and the improvements we would suggest upstream. It is written so that a TinyDB maintainer can read any section standalone and understand the limitation, why it matters to an ODM layered on top, and what change would resolve it.

Two project policies anchor this page (see `AGENTS.md`):

- `tinydantic` prefers TinyDB's public API. An internal/private TinyDB API (underscore-prefixed) may be used only when the needed behavior is impossible through the public API, only with explicit approval during planning/review, and every such use must be documented in the [registry below](#private-api-usage-registry) with its reason and the upstream change that would make it unnecessary.
- Proposals to TinyDB are drafted in `upstream/` (at the repository root) and are never filed on the TinyDB issue tracker without explicit approval.

This page must be kept current: whenever TinyDB friction is found, worked around, or resolved, update the relevant section here in the same change.

All observations below were verified against TinyDB 4.8.2.

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

## `update()` field mappings are mistyped as callables

**Limitation.** `Table.update()` and `Table.update_multiple()` annotate their `fields` parameter as `Callable[[Mapping], None]`, but both accept (and the documentation describes) plain mappings as well — the implementation branches on `callable(fields)`. Static type checkers therefore reject the documented mapping form.

**Why it matters.** Every `tinydantic` call into these methods carries a `cast("Callable[[Mapping], None]", fields)` band-aid, marked with `TODO @cdwilson: remove this cast once the annotation is fixed in TinyDB` (see `src/tinydantic/_model.py`). The transform parameter is also under-annotated for its actual contract: the callable receives a mutable `dict`, so `Callable[[MutableMapping], None]` would describe it better.

**Suggested improvement.** Annotate as `fields: Mapping | Callable[[MutableMapping], None]` (and the corresponding tuple type in `update_multiple`).

## Document ids are stringified before reaching storages

**Limitation.** Before table data is handed to the storage layer, document ids are converted to strings (`{str(doc_id): doc}` in `Table._update_table()`), because the reference JSON storage requires string keys. Storages and middlewares therefore never see the native int ids, and serialized output sorts ids lexicographically (`"10"` before `"2"`). See the upstream discussion [msiemens/tinydb#466](https://github.com/msiemens/tinydb/discussions/466).

**Why it matters.** Human-readable storage output (a design goal of `tinydantic`'s YAML storage) lists documents in confusing lexicographic order. `tinydantic` ships `SortIntDocIDsMiddleware` (`src/tinydantic/tinydb/middlewares.py`) purely to undo the stringification — it converts keys back to ints and forces `sort_keys=True` — and that middleware has to reach into the wrapped storage's `kwargs` and pass ints where the `Storage` protocol declares strings, both acknowledged hacks.

**Suggested improvement.** Let storages opt into native id keys (for example, a class attribute on `Storage` declaring whether keys must be strings), or perform the stringification inside `JSONStorage` rather than in `Table`, so key formatting becomes a storage concern.

## Private API usage registry

Every approved use of a TinyDB internal/private API in `tinydantic` is recorded here. An empty table means the shipped code uses only the public API.

| TinyDB internal | Used by | Status | Reason | Upstream change that would remove it |
| --- | --- | --- | --- | --- |
| `QueryInstance._hash` (read-only attribute access) | `tinydantic._query.has_id_condition()` — detecting id conditions inside composed queries | **In use** (approved 2026-08-02; shipped with the original id-query work) | Composing queries (`&`/`\|`/`~`) produces plain `QueryInstance` objects, so a custom condition type cannot survive composition — the hashval tree is the only place a marker does. The access is read-only via `getattr(cond, "_hash", None)` and degrades loudly, never silently: if a future TinyDB renames the attribute, bare id conditions are still detected by `isinstance`, and undetected compositions raise `DocumentIDConditionError` when TinyDB's evaluator runs them. | The `needs_doc_id`/`DocId` evaluator improvement above (composition would propagate a public flag); alternatively, a public accessor for a query's hash tree. |
| `Table._update_table(updater)` | `TinydanticModel._run_id_condition_write_cycle()` — the id-condition write paths of `update()`, `remove()`, `upsert()`, and `update_multiple()` | **In use** (approved 2026-07-13) | The only way to select write targets by id inside one atomic read-modify-write cycle: `update_multiple()` has no `doc_ids` parameter, and conditions cannot see ids (the two limitations above). The custom updater evaluates every condition against `Document(body, doc_id)` wrappers inside upstream's own read → mutate → write → cache-clear lifecycle, applies mutations copy-on-write (so an aborted cycle leaks nothing, even on `MemoryStorage`, whose `read()` shares body dicts by reference), and skips the storage write entirely when nothing matched. Benchmarked ~23% faster than the two-pass public-API alternative on a 5,000-document JSONStorage table (one full file read saved per write). | Either `update_multiple()` improvement above; the `needs_doc_id`/`DocId` evaluator change removes the need entirely. |
