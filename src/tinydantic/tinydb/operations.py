# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from typing import Callable, Mapping, MutableMapping


def replace(new: Mapping) -> Callable[[MutableMapping], None]:
    """TODO: needs docstring."""

    def transform(doc: MutableMapping) -> None:
        """TODO: needs docstring."""
        doc.clear()
        doc.update(new)

    return transform
