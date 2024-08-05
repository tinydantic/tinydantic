# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""`tinydantic` is a Python object-document mapper (ODM) for [TinyDB](https://tinydb.readthedocs.io/en/latest/).

Attributes:
    __version__: The `tinydantic` package version.
"""

from importlib import metadata

__version__: str = metadata.version("tinydantic")

__all__ = [
    "__version__",
]
