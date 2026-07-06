# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""The TinydanticModel base class and query helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast, overload

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_snake
from tinydb.queries import Query, where
from tinydb.table import Document, Table

from tinydantic.config import (
    CONFIG_ATTR,
    TinydanticConfig,
    check_config_ambiguity,
    get_config_value,
)
from tinydantic.errors import (
    DatabaseNotBoundError,
    DocumentIDRequiredError,
    DocumentNotFoundError,
)
from tinydantic.tinydb.operations import replace

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping
    from typing import Self

    # pydantic's ModelMetaclass lives in a private module. We
    # type-check against the real class but resolve it at runtime as
    # type(BaseModel), so tinydantic never imports pydantic internals
    # at runtime and survives pydantic moving the module.
    from pydantic._internal._model_construction import ModelMetaclass
    from tinydb import TinyDB
    from tinydb.queries import QueryLike
else:
    ModelMetaclass = type(BaseModel)


def q(field: Any) -> Query:
    """Tell the type checker a field expression is a TinyDB Query.

    At runtime, class-level field access like ``User.name`` already
    returns a [Query][tinydb.queries.Query] (see
    [TinydanticModelMetaclass][tinydantic._model.TinydanticModelMetaclass]),
    but static type checkers see the field annotation instead, so
    ``User.name == "Alice"`` types as ``bool``. Wrapping the field in
    ``q()`` gives the type checker the runtime truth:

    ```python
    User.search(q(User.name) == "Alice")
    ```

    Args:
        field: A class-level field expression (e.g. ``User.name``).

    Returns:
        The same object, typed as a Query.

    Raises:
        TypeError: If ``field`` is not actually a TinyDB Query — for
            example when called with an instance attribute or a plain
            string instead of class-level field access.
    """
    if not isinstance(field, Query):
        msg = (
            f"q() expected a TinyDB Query (class-level field access "
            f"like Model.field), got {type(field).__name__!r}"
        )
        raise TypeError(msg)
    return field


class TinydanticModelMetaclass(ModelMetaclass):
    """Metaclass providing class-level field queries.

    Accessing a model *field* on the model *class* (not an instance)
    returns ``tinydb.queries.where(field_name)``, so expressions like
    ``User.name == "Alice"`` build TinyDB queries directly from the
    model definition.
    """

    def __getattr__(cls, attr: str) -> Any:  # noqa: N805
        """Return a field Query, falling back to normal lookup.

        Pydantic calls ``__getattr__`` for each field while the model
        class is still being built; returning a Query then would break
        model construction (``RuntimeError: Empty query was
        evaluated``). The ``__pydantic_complete__`` guard defers query
        behavior until the model is fully built.
        """
        if cls.__pydantic_complete__ and attr in cls.model_fields:
            return where(attr)
        return super().__getattr__(attr)  # type: ignore[misc]


class TinydanticModel(BaseModel, metaclass=TinydanticModelMetaclass):
    """Base class for tinydantic models.

    Subclass to define a document model, passing tinydantic
    configuration as class keyword arguments:

    ```python
    from tinydb import TinyDB
    from tinydantic import TinydanticModel

    db = TinyDB("db.json")


    class User(TinydanticModel, database=db, table_name="users"):
        name: str
    ```

    Configuration is stored per class in ``__tinydantic_config__`` and
    resolved by walking the MRO — deliberately NOT in pydantic's
    ``model_config``; see the [tinydantic.config][] module docstring
    for the design rationale (pydantic#9992).
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(
        # Reserve the tinydantic_ prefix so future tinydantic methods
        # cannot collide with user-defined fields (the use case Samuel
        # Colvin described in pydantic#10315).
        protected_namespaces=("tinydantic_",),
    )

    __tinydantic_config__: ClassVar[TinydanticConfig] = {}

    # --- model fields ---

    id: int | None = Field(
        default=None,
        description="Document ID",
    )

    # --- configuration ---

    def __init_subclass__(
        cls,
        database: TinyDB | None = None,
        table_name: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Capture tinydantic class keywords.

        Pydantic pops its own known config keys from class keyword
        arguments and forwards the rest here (a public extension
        point), so no metaclass involvement is needed for
        configuration. Only explicitly provided values are stored on
        this class — ``None`` means "not provided", and resolution
        falls through to base classes via
        [get_config_value][tinydantic.config.get_config_value].
        """
        super().__init_subclass__(**kwargs)
        config: TinydanticConfig = {}
        if database is not None:
            config["database"] = database
        if table_name is not None:
            config["table_name"] = table_name
        setattr(cls, CONFIG_ATTR, config)

    @classmethod
    def __pydantic_init_subclass__(cls, **kwargs: Any) -> None:
        """Validate config after pydantic finishes building the class.

        Raises:
            AmbiguousConfigError: If unrelated base classes supply
                conflicting tinydantic config (see
                [check_config_ambiguity][tinydantic.config.check_config_ambiguity]).
        """
        super().__pydantic_init_subclass__(**kwargs)
        check_config_ambiguity(cls)

    @classmethod
    def bind(
        cls,
        *,
        database: TinyDB | None = None,
        table_name: str | None = None,
    ) -> None:
        """Bind or rebind tinydantic config after class definition.

        The late-binding escape hatch for tests and application
        factories where no TinyDB instance exists at import time:

        ```python
        class User(TinydanticModel):
            name: str


        User.bind(database=TinyDB("db.json"))
        ```

        Only the keys passed are updated; other keys keep their
        current (possibly inherited) values. Binding a subclass never
        affects its parents.
        """
        config = cast(
            "TinydanticConfig",
            dict(cls.__dict__.get(CONFIG_ATTR, {})),
        )
        if database is not None:
            config["database"] = database
        if table_name is not None:
            config["table_name"] = table_name
        setattr(cls, CONFIG_ATTR, config)

    @classmethod
    def get_database(cls) -> TinyDB:
        """Get the TinyDB database this model is bound to.

        Returns:
            The bound TinyDB database.

        Raises:
            DatabaseNotBoundError: If no database is configured
                anywhere in the class hierarchy.
        """
        database: TinyDB | None = get_config_value(cls, "database")
        if database is None:
            raise DatabaseNotBoundError(cls.__name__)
        return database

    @classmethod
    def get_table(cls) -> Table:
        """Get the TinyDB table for this model.

        Uses the configured ``table_name`` when set, otherwise the
        snake_case form of the class name (``AdminUser`` →
        ``admin_user``).
        """
        table_name: str | None = get_config_value(cls, "table_name")
        if not table_name:
            return cls.get_database().table(name=to_snake(cls.__name__))
        return cls.get_database().table(name=table_name)

    @classmethod
    def from_tinydb_document(cls, document: Mapping) -> Self:
        """TODO: needs docstring."""
        instance = cls.model_validate(document)
        if isinstance(document, Document):
            instance.id = document.doc_id
        return instance

    @classmethod
    def insert_multiple(cls, documents: Iterable[Self]) -> list[int]:
        """TODO: needs docstring."""
        return cls.get_table().insert_multiple(
            [doc.to_tinydb_document() for doc in documents],
        )

    @classmethod
    def all(cls) -> list[Self]:
        """TODO: needs docstring."""
        return [cls.from_tinydb_document(doc) for doc in iter(cls.get_table())]

    @classmethod
    def search(cls, cond: QueryLike) -> list[Self]:
        """Get all documents matching ``cond`` as validated models."""
        return [
            cls.from_tinydb_document(doc)
            for doc in cls.get_table().search(cond)
        ]

    @overload
    @classmethod
    def get(cls, cond: QueryLike) -> Self | None: ...

    @overload
    @classmethod
    def get(cls, *, doc_id: int) -> Self | None: ...

    @overload
    @classmethod
    def get(cls, *, doc_ids: list[int]) -> list[Self]: ...

    @classmethod
    def get(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_id: int | None = None,
        doc_ids: list[int] | None = None,
    ) -> Self | list[Self] | None:
        """Get one document (or several by id) as validated models.

        Mirrors [tinydb.table.Table.get][], with one tightening: at
        most one of ``cond``, ``doc_id``, ``doc_ids`` may be provided
        (TinyDB silently applies a precedence order; tinydantic raises
        ``ValueError``). The typed variants
        [get_by_cond][tinydantic.TinydanticModel.get_by_cond],
        [get_by_id][tinydantic.TinydanticModel.get_by_id], and
        [get_by_ids][tinydantic.TinydanticModel.get_by_ids] offer
        precise return types per call shape.

        When ``doc_ids`` is given, TinyDB returns only the documents
        that exist (missing ids are silently skipped), so the result is
        a ``list`` that may be shorter than the ids requested and is
        ordered by storage iteration, not by the ids passed in.

        Raises:
            ValueError: If more than one selector is provided.
        """
        provided = [s for s in (cond, doc_id, doc_ids) if s is not None]
        if len(provided) > 1:
            msg = "Provide at most one of cond, doc_id, or doc_ids"
            raise ValueError(msg)

        result = cls.get_table().get(
            cond=cond,
            doc_id=doc_id,
            doc_ids=doc_ids,
        )

        if result is None:
            return None

        if isinstance(result, Document):
            return cls.from_tinydb_document(result)

        if isinstance(result, list):
            return [cls.from_tinydb_document(doc) for doc in result]

        raise TypeError

    @classmethod
    def get_by_cond(cls, cond: QueryLike) -> Self | None:
        """Get the first document matching ``cond``, or ``None``."""
        return cls.get(cond)

    @classmethod
    def get_by_id(cls, doc_id: int) -> Self | None:
        """Get the document with the given id, or ``None``."""
        return cls.get(doc_id=doc_id)

    @classmethod
    def get_by_ids(cls, doc_ids: list[int]) -> list[Self]:
        """Get documents for the given ids (see get() for semantics)."""
        return cls.get(doc_ids=doc_ids)

    @classmethod
    def contains(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_id: int | None = None,
    ) -> bool:
        """Check whether a matching document exists.

        Raises:
            ValueError: If both ``cond`` and ``doc_id`` are provided.
        """
        if cond is not None and doc_id is not None:
            msg = "Provide at most one of cond or doc_id"
            raise ValueError(msg)
        return cls.get_table().contains(cond=cond, doc_id=doc_id)

    @classmethod
    def update(
        cls,
        fields: Mapping | Callable[[Mapping], None],
        cond: QueryLike | None = None,
        *,
        doc_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """Update matching documents with new fields or a transform.

        Returns:
            The ids of all updated documents.
        """
        return cls.get_table().update(
            # See replace() for why this cast is needed.
            # TODO @cdwilson: remove this cast once the annotation is
            # fixed in TinyDB.
            cast("Callable[[Mapping], None]", fields),
            cond=cond,
            doc_ids=doc_ids,
        )

    @classmethod
    def update_multiple(
        cls,
        updates: Iterable[
            tuple[
                Mapping | Callable[[Mapping], None],
                QueryLike,
            ]
        ],
    ) -> list[int]:
        """Apply several (fields_or_transform, cond) updates at once.

        Returns:
            The ids of all updated documents.
        """
        return cls.get_table().update_multiple(
            # See replace() for why this cast is needed.
            cast(
                "Iterable[tuple[Callable[[Mapping], None], QueryLike]]",
                updates,
            ),
        )

    @classmethod
    def upsert(
        cls,
        document: Self,
        cond: QueryLike | None = None,
    ) -> list[int]:
        """Update documents matching ``cond``, or insert ``document``.

        Returns:
            The ids of the updated (or inserted) documents.
        """
        return cls.get_table().upsert(
            document.to_tinydb_document(force_dict=cond is not None),
            cond,
        )

    @classmethod
    def remove(
        cls,
        cond: QueryLike | None = None,
        *,
        doc_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """Remove matching documents.

        Returns:
            The ids of all removed documents.
        """
        return cls.get_table().remove(cond=cond, doc_ids=doc_ids)

    @classmethod
    def truncate(cls) -> None:
        """TODO: needs docstring."""
        cls.get_table().truncate()

    @classmethod
    def count(cls, cond: QueryLike) -> int:
        """TODO: needs docstring."""
        return cls.get_table().count(cond)

    @classmethod
    def clear_cache(cls) -> None:
        """TODO: needs docstring."""
        cls.get_table().clear_cache()

    # --- instance methods ---

    def to_tinydb_document(
        self,
        *,
        force_dict: bool = False,
    ) -> dict[str, Any] | Document:
        """Convert this model to a TinyDB-storable document.

        Uses JSON-mode serialization so rich pydantic types (datetime,
        UUID, enums, nested models, ...) become JSON-safe primitives
        that round-trip through any TinyDB storage (spec 3.7). The
        ``id`` field is never embedded in the document — it maps to
        TinyDB's ``doc_id``.

        Args:
            force_dict: Return a plain dict even when ``id`` is set
                (otherwise a [Document][tinydb.table.Document] carrying
                ``doc_id`` is returned).
        """
        doc = self.model_dump(mode="json", exclude={"id"})

        if (force_dict is False) and (self.id is not None):
            doc = Document(doc, self.id)

        return doc

    def insert(self) -> Self:
        """TODO: needs docstring."""
        self.id = self.get_table().insert(self.to_tinydb_document())

        return self

    def replace(self) -> None:
        """TODO: needs docstring."""
        if self.id is None:
            raise DocumentIDRequiredError

        updated_doc_ids = self.get_table().update(
            # In TinyDB, the Table.update/update_multiple methods
            # currently annotate the fields parameter with the type
            # Callable[[Mapping], None].
            #
            # However, the doc parameter that is passed to this
            # transform function is actually a python dict (which is a
            # type of MutableMapping).
            #
            # This cast is simply a band-aid to keep the type checker
            # happy.
            #
            # TODO @cdwilson: remove this cast once the annotation is
            # fixed in TinyDB.
            cast(
                "Callable[[Mapping], None]",
                replace(self.to_tinydb_document(force_dict=True)),
            ),
            doc_ids=[self.id],
        )

        if not updated_doc_ids:
            raise DocumentNotFoundError

    def delete(self) -> None:
        """Remove this model's document from its table.

        Raises:
            DocumentIDRequiredError: If ``id`` is not set (the model
                was never inserted).
            DocumentNotFoundError: If no document with this ``id``
                exists in the table.
        """
        if self.id is None:
            raise DocumentIDRequiredError
        try:
            removed = self.get_table().remove(doc_ids=[self.id])
        except KeyError:
            raise DocumentNotFoundError from None
        if not removed:
            raise DocumentNotFoundError

    def save(self) -> Self:
        """Insert this model if it is new, otherwise update it by id.

        Returns:
            This instance (with ``id`` set if it was newly inserted).
        """
        if self.id is None:
            return self.insert()
        self.id = self.get_table().upsert(self.to_tinydb_document())[0]
        return self
