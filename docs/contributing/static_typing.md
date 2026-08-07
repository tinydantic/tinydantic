# Static Typing Design

This page records why `tinydantic` corrects the `Model.field` type mismatch with an opt-in helper ([q()][tinydantic.q]) rather than with a `mypy` plugin or a typed descriptor, so the decision can be re-opened deliberately instead of re-litigated by accident.

Verified against `mypy` 2.3.0, `pyright` 1.1.411, and `pydantic` 2.13.4 on Python 3.10.

## The mismatch

A type checker reads annotations; it cannot read a metaclass. `name: str` tells it that `User.name` is a `str`, and no amount of runtime machinery changes that conclusion. Because `tinydantic`'s metaclass returns a TinyDB [Query][tinydb.queries.Query] for class-level field access, the checker is wrong in both directions on the same attribute:

| Expression | Type checker | Runtime |
| --- | --- | --- |
| `User.search(User.name == "Alice")` | error — `bool` is not `QueryLike` | correct query |
| `User.name.upper()` | fine — `str.upper()` | `TypeError` |

The first direction is noisy but harmless. The second is the dangerous one, and nothing in the current design catches it.

## The decision

`q()` is a runtime no-op that returns its argument re-typed as a `Query`. Wrapping a field silences the false error and preserves inference through overloaded methods; skipping it costs nothing at runtime.

Documentation examples deliberately stay on the bare form, with `q()` introduced once in the [quickstart](../usage/quickstart.md#if-you-use-a-type-checker) and once in [Queries](../usage/queries.md#static-type-checking). `tinydantic` targets scripts and small tools where a type checker is often absent; putting `q()` on every example would tax every reader to serve a subset of them. SQLModel makes the same call — its [where tutorial](https://sqlmodel.tiangolo.com/tutorial/where/) uses bare comparisons throughout and introduces `col()` only in a closing section on editor errors.

## Rejected: a typed descriptor (`Mapped[T]`)

SQLAlchemy 2.0's approach. Fields are annotated with a wrapper whose `__get__` overloads distinguish class access from instance access, so the checker derives the right type for both:

```python
class Mapped(Generic[T]):
    @overload
    def __get__(
        self, obj: None, owner: type
    ) -> Query: ...  # User.name -> Query
    @overload
    def __get__(self, obj: object, owner: type) -> T: ...  # user.name -> str
    def __set__(
        self, obj: object, value: T
    ) -> None: ...  # required, see below

    @classmethod
    def __get_pydantic_core_schema__(cls, source, handler):
        (inner,) = source.__args__
        return handler.generate_schema(inner)


class User(TinydanticModel, database=db):
    name: Mapped[str]
```

This was prototyped and it works, on both checkers and at runtime. `User.name` types as `Query`, `user.name` as `str`, `User.search(User.name == "Alice")` needs no `q()`, `User.name.upper()` becomes an error, and pydantic still validates as the inner type — including through `Mapped[Annotated[str, Field(min_length=3)]]`, whose constraint and JSON Schema survive intact. It is the only approach that fixes both directions, and it needs no plugin, so it works with every checker.

It was rejected on ergonomics:

- **Bare defaults stop type-checking.** `tags: Mapped[list[str]] = []` is an assignment mismatch on both checkers (`"list[Any]" is not assignable to "Mapped[list[str]]"`). Every defaulted field would have to be rewritten as `Field(default=...)`. SQLAlchemy escapes this only because its defaults always route through `mapped_column(default=...)`; `tinydantic` has no such funnel.
- **`__set__` is load-bearing.** Without it, `User(name="Alice")` errors — pydantic's `dataclass_transform` synthesizes `__init__` from the declared type, and the descriptor's `__set__` type is what makes the constructor accept a `str` again. A subtle dependency on checker behavior that is not part of any spec `tinydantic` controls.
- **The cost lands on every user.** `q()` is paid per query expression, and only by projects that type-check. `Mapped[T]` is paid per field declaration, by everyone, including the majority who never run a checker — and it spreads into `Annotated` combinations (`Mapped[Annotated[str, Unique()]]`).
- **It contradicts the pitch.** "Your pydantic model, stored in TinyDB" stops being true when every annotation needs a wrapper.

## Rejected: a `mypy` plugin

A plugin registered as `plugins = ["tinydantic.mypy"]` can fix both directions with no change to how users write models. The relevant hook is `get_class_attribute_hook`, which intercepts attribute access on a class object specifically — exactly the case that is mistyped:

```python
class TinydanticPlugin(Plugin):
    def get_class_attribute_hook(self, fullname: str):
        cls_name, _, attr = fullname.rpartition(".")
        if _is_tinydantic_model(cls_name) and _is_field(cls_name, attr):
            return _as_query  # AttributeContext -> tinydb.queries.Query
        return None
```

Rejected because it covers half the ecosystem at best. `pyright` has no plugin system and its maintainers have declined to add one, so every Pylance user — the VS Code default, and the checker FastAPI users skew toward — would see no improvement. `mypy`'s plugin API is also semi-internal and changes between releases; pydantic's own plugin is a standing maintenance cost, and pydantic v2 moved as much as it could out of it.

## What would re-open this

- Pydantic gaining first-class support for descriptor-typed fields, which would remove the defaults problem that sinks `Mapped[T]`.
- A typing-spec mechanism for expressing "class access differs from instance access" without changing the annotation.
- Evidence that the audience has shifted toward large type-checked applications, where per-field ceremony is normal and the reverse-direction trap costs real time.
