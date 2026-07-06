# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TinyDB update operations."""

from collections.abc import Callable, Mapping, MutableMapping


def replace(new: Mapping) -> Callable[[MutableMapping], None]:
    """Build a TinyDB update transform that replaces a document.

    The returned callable clears the target document and repopulates it
    from ``new``, so it fully replaces the stored contents rather than
    merging. Pass it to [tinydb.table.Table.update][] (this is how
    [TinydanticModel.replace][tinydantic.TinydanticModel.replace]
    overwrites a document).

    Args:
        new: The mapping to replace the document's contents with.

    Returns:
        A transform suitable for TinyDB's update operations.
    """

    def transform(doc: MutableMapping) -> None:
        """Replace ``doc``'s contents with ``new`` in place."""
        doc.clear()
        doc.update(new)

    return transform
