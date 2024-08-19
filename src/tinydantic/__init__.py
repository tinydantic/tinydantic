# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""`tinydantic` is a simple Python object-document mapper (ODM) for the
[TinyDB](https://tinydb.readthedocs.io/en/latest/) document database.

Attributes:
    __version__: The `tinydantic` package version.
"""  # noqa: D205

from importlib import metadata

from tinydantic._document import Document

__version__: str = metadata.version("tinydantic")

__all__ = [
    "__version__",
    "Document",
]
