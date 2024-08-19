# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Base classes for creating `tinydantic` document models."""

from __future__ import annotations

from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Iterable,
    Mapping,
    cast,
)

import tinydb
import tinydb.queries
import tinydb.table

from pydantic import BaseModel, Field
from pydantic._internal._model_construction import ModelMetaclass

from tinydantic.errors import DocumentIDRequiredError, DocumentNotFoundError
from tinydantic.tinydb.operations import replace

if TYPE_CHECKING:
    import sys

    if sys.version_info > (3, 10):
        from typing import Self
    else:
        from typing_extensions import Self


class DocumentMeta(ModelMetaclass):
    def __getattr__(cls, attr: str) -> Any:  # noqa: N805
        # Pydantic calls this multiple times for each field during model
        # building, which results in an empty Query object being
        # returned and called. (i.e. RuntimeError: Empty query was
        # evaluated)
        #
        # To prevent this error, we check `cls.__pydantic_complete__` to
        # ensure that model building is complete before returning a
        # Query object.
        if cls.__pydantic_complete__ and attr in cls.model_fields:
            return tinydb.queries.where(attr)

        return super().__getattr__(attr)


# TODO @cdwilson: the document ID type is currently hard-coded to int in
# this module (the default for TinyDB), but TinyDB allows the
# Table.document_id_class to be changed to a different type.
class Document(BaseModel, metaclass=DocumentMeta):
    """A base class for creating `tinydantic` document models.

    Document models should subclass
    [Document][tinydantic.Document] to define fields specific
    to each document type.

    Examples:
        ```python
        class User(Document):
            database = db
            name: str
        ```
    """

    # --- class attributes ---

    database: ClassVar[tinydb.TinyDB]
    """TinyDB database where documents of this type are stored."""

    table_name: ClassVar[str | None] = None
    """Optional database table name for documents of this type.

    The default value is `None` which will use the lower-case version
    of the document model's class name (i.e. `cls.__name__.lower()`).
    For example, if the class name is `User`, the generated table name
    in the database would be `user`.

    This option can be useful when plural database table names are
    preferred—for example, naming a table `users` instead of `user`.
    """

    # --- instance attributes ---

    id: int | None = Field(
        default=None,
        exclude=True,
        description="Document ID",
    )

    # --- class methods ---

    @classmethod
    def get_table(cls) -> tinydb.table.Table:
        """Get the TinyDB table for this document type."""
        if not cls.table_name:
            return cls.database.table(name=cls.__name__.lower())
        return cls.database.table(name=cls.table_name)

    @classmethod
    def from_tinydb_document(cls, document: Mapping) -> Self:
        """TODO: needs docstring."""
        instance = cls.model_validate(document)
        if isinstance(document, tinydb.table.Document):
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
    def search(cls, condition: tinydb.queries.QueryLike) -> list[Self]:
        """TODO: needs docstring."""
        raise NotImplementedError

    # TODO @cdwilson: should this be split into different methods based
    # on the type of argument?
    @classmethod
    def get(
        cls,
        condition: tinydb.queries.QueryLike | None = None,
        document_id: int | None = None,
        document_ids: list[int] | None = None,
    ) -> Self | list[Self] | None:
        """TODO: needs docstring."""
        result = cls.get_table().get(
            cond=condition,
            doc_id=document_id,
            doc_ids=document_ids,
        )

        if result is None:
            return None

        if isinstance(result, tinydb.table.Document):
            return cls.from_tinydb_document(result)

        if isinstance(result, list):
            return [cls.from_tinydb_document(doc) for doc in result]

        raise TypeError

    @classmethod
    def contains(
        cls,
        condition: tinydb.queries.QueryLike | None = None,
        document_id: int | None = None,
    ) -> bool:
        """TODO: needs docstring."""
        raise NotImplementedError

    @classmethod
    def update(
        cls,
        fields: Mapping | Callable[[Mapping], None],
        condition: tinydb.queries.QueryLike | None = None,
        document_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """TODO: needs docstring."""
        raise NotImplementedError

    @classmethod
    def update_multiple(
        cls,
        updates: Iterable[
            tuple[
                Mapping | Callable[[Mapping], None],
                tinydb.queries.QueryLike,
            ]
        ],
    ) -> list[int]:
        """TODO: needs docstring."""
        raise NotImplementedError

    @classmethod
    def upsert(
        cls,
        document: Self,
        cond: tinydb.queries.QueryLike | None = None,
    ) -> list[int]:
        """TODO: needs docstring."""
        raise NotImplementedError

    @classmethod
    def remove(
        cls,
        condition: tinydb.queries.QueryLike | None = None,
        document_ids: Iterable[int] | None = None,
    ) -> list[int]:
        """TODO: needs docstring."""
        raise NotImplementedError

    @classmethod
    def truncate(cls) -> None:
        """TODO: needs docstring."""
        cls.get_table().truncate()

    @classmethod
    def count(cls, condition: tinydb.queries.QueryLike) -> int:
        """TODO: needs docstring."""
        return cls.get_table().count(condition)

    @classmethod
    def clear_cache(cls) -> None:
        """TODO: needs docstring."""
        cls.get_table().clear_cache()

    # --- instance methods ---

    def to_tinydb_document(
        self,
        *,
        force_dict: bool = False,
    ) -> dict[str, Any] | tinydb.table.Document:
        """TODO: needs docstring."""
        doc = self.model_dump()

        if (force_dict is False) and (self.id is not None):
            doc = tinydb.table.Document(doc, self.id)

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
                Callable[[Mapping], None],
                replace(self.to_tinydb_document(force_dict=True)),
            ),
            doc_ids=[self.id],
        )

        if not updated_doc_ids:
            raise DocumentNotFoundError

    def save(self) -> None:
        """TODO: needs docstring."""
        self.id = self.get_table().upsert(self.to_tinydb_document())[0]
