# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Package version info."""

from importlib import metadata

__all__ = [
    "__version__",
]

__version__ = metadata.version("tinydantic")
