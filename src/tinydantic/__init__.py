# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""A simple Python object-document mapper (ODM) for TinyDB.

`tinydantic` maps Python objects to and from documents stored in
the [TinyDB](https://tinydb.readthedocs.io/en/latest/) document
database.

Attributes:
    __version__: The `tinydantic` package version.
"""

from importlib import metadata

from tinydantic._config import TinydanticConfig
from tinydantic._errors import (
    AmbiguousConfigError,
    DatabaseLockedError,
    DatabaseNotBoundError,
    DocumentAlreadyExistsError,
    DocumentIDConditionError,
    DocumentIDRequiredError,
    DocumentIDUpdateError,
    DocumentNotFoundError,
    FindQueryError,
    RevisionFieldError,
    RevisionUpdateError,
    SelectorError,
    ShadowedFieldError,
    SortFieldError,
    StaleDocumentError,
    TinydanticError,
    TinydanticUserError,
    UniqueConstraintError,
    UnknownUpdateFieldError,
)
from tinydantic._fields import Unique
from tinydantic._model import TinydanticModel, q

__version__: str = metadata.version("tinydantic")

__all__ = [
    "AmbiguousConfigError",
    "DatabaseLockedError",
    "DatabaseNotBoundError",
    "DocumentAlreadyExistsError",
    "DocumentIDConditionError",
    "DocumentIDRequiredError",
    "DocumentIDUpdateError",
    "DocumentNotFoundError",
    "FindQueryError",
    "RevisionFieldError",
    "RevisionUpdateError",
    "SelectorError",
    "ShadowedFieldError",
    "SortFieldError",
    "StaleDocumentError",
    "TinydanticConfig",
    "TinydanticError",
    "TinydanticModel",
    "TinydanticUserError",
    "Unique",
    "UniqueConstraintError",
    "UnknownUpdateFieldError",
    "__version__",
    "q",
]
