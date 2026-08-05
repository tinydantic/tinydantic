# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Custom TinyDB storage middlewares."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from tinydb.middlewares import Middleware

if TYPE_CHECKING:
    from tinydb.storages import Storage


# IMPORTANT: This middleware may break some storages because it passes
# integer doc_id's to the underlying storage classes.
class SortIntDocIDsMiddleware(Middleware):
    """Middleware that sorts documents by integer ``doc_id`` on write.

    Wraps a [Storage][tinydb.storages.Storage] and, on each write,
    converts the stringified document ids back to integers and
    inserts them in ascending numeric order, so documents are
    serialized by ``doc_id`` (where ``"10"`` would otherwise sort
    before ``"2"`` as a string). Tables are serialized in sorted-name
    order. Serializers that preserve insertion order — ``json.dump``
    and ``yaml.dump`` with ``sort_keys=False``, or any
    order-preserving storage — write the documents in that order;
    serializers that sort keys themselves sort the integer ids
    numerically, which agrees with it.

    The storage's own dump arguments (such as ``sort_keys``) are
    left untouched, so field order inside each document follows the
    storage's configuration — insertion order by default for JSON,
    sorted for PyYAML unless ``sort_keys=False`` is passed.

    Warning:
        This middleware may break storages that cannot serialize
        integer keys, since it passes integer ``doc_id`` values
        through to the underlying storage.
    """

    def __init__(self, storage_cls: type[Storage] | Middleware) -> None:
        """Wrap ``storage_cls`` with integer-``doc_id`` sorting.

        Args:
            storage_cls: The storage class — or another middleware,
                such as ``CachingMiddleware(JSONStorage)`` — to
                wrap.
        """
        super().__init__(storage_cls)

    def write(self, data: dict[str, dict[str, Any]]) -> None:
        """Write ``data`` with documents sorted by integer ``doc_id``.

        Args:
            data: The table data to write, keyed by table name then
                document id.
        """
        # Convert doc_id from strings back to integers, inserting
        # them in ascending numeric order (dicts preserve insertion
        # order, and order-preserving serializers write it out).
        #
        # Note: the conversion is required even though doc_id's type
        # is integer because doc_id is preemptively converted to a
        # string before being passed to the middleware/storage class
        # (see https://github.com/msiemens/tinydb/discussions/466).
        int_keys_data: dict[str, dict[int, Any]] = {}
        for table in sorted(data):
            int_keys_data[table] = {
                int(doc_id): value
                for doc_id, value in sorted(
                    data[table].items(),
                    key=lambda item: int(item[0]),
                )
            }

        # Instruct the storage class to write the data using integer
        # keys. This works for JSONStorage because json.dumps() will
        # coerce integer document IDs to strings (JSON requires that
        # keys are strings). It also works for YAMLStorage because
        # the YAML spec allows integer keys.
        #
        # TinyDB's Storage.write() expects data to be of type
        # dict[str, dict[str, Any]] but we're passing in data of type
        # dict[str, dict[int, Any]] instead.
        #
        # As a result, we need to tell the type checker to ignore
        # arg-type type errors.
        self.storage.write(data=int_keys_data)  # type: ignore[arg-type]
