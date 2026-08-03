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
    DatabaseNotBoundError,
    DocumentAlreadyExistsError,
    DocumentIDConditionError,
    DocumentIDRequiredError,
    DocumentIDUpdateError,
    DocumentNotFoundError,
    SelectorError,
    TinydanticError,
    TinydanticUserError,
    UnknownUpdateFieldError,
)
from tinydantic._model import TinydanticModel, q

__version__: str = metadata.version("tinydantic")

__all__ = [
    "AmbiguousConfigError",
    "DatabaseNotBoundError",
    "DocumentAlreadyExistsError",
    "DocumentIDConditionError",
    "DocumentIDRequiredError",
    "DocumentIDUpdateError",
    "DocumentNotFoundError",
    "SelectorError",
    "TinydanticConfig",
    "TinydanticError",
    "TinydanticModel",
    "TinydanticUserError",
    "UnknownUpdateFieldError",
    "__version__",
    "q",
]
