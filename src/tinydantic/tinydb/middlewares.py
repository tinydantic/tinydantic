# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

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
    converts the stringified document ids back to integers and forces
    the underlying storage to sort keys, so documents are serialized in
    numeric ``doc_id`` order rather than lexicographic string order
    (where ``"10"`` would sort before ``"2"``).

    Warning:
        This middleware may break storages that cannot serialize integer
        keys, since it passes integer ``doc_id`` values through to the
        underlying storage.
    """

    def __init__(self, storage_cls: type[Storage]) -> None:
        """Wrap ``storage_cls`` with integer-``doc_id`` sorting.

        Args:
            storage_cls: The storage class to wrap.
        """
        super().__init__(storage_cls)

    def write(self, data: dict[str, dict[str, Any]]) -> None:
        """Write ``data`` with documents sorted by integer ``doc_id``.

        Args:
            data: The table data to write, keyed by table name then
                document id.
        """
        # 3-step "trick" to numerically sort the documents in each table
        # by their integer doc_id:

        # 1. Dict comprehension to convert doc_id from strings to
        #    integers.
        #
        #    Note: this is required even though the type of doc_id is
        #    integer because doc_id is preemptively converted to a
        #    string before being passed to the middleware/storage class
        #    (see https://github.com/msiemens/tinydb/discussions/466).
        int_keys_data: dict[str, dict[int | str, Any]] = {}
        for table, table_data in data.items():
            int_keys_data[table] = {
                int(doc_id): value for doc_id, value in table_data.items()
            }

        # 2. Force the storage class to sort by key on write.
        #
        #    For example:
        #    json.dumps(data, fp, sort_keys=True, ...)
        #    yaml.dump(data, fp, sort_keys=True, ...)
        #    etc...
        #
        #    Note: this requires that the storage class supports the
        #    sort_keys keyword argument to dump, and it overwrites the
        #    value specified when the storage class was initialized.
        self.storage.kwargs["sort_keys"] = True  # type: ignore[attr-defined]

        # 3. Instruct the storage class to write the data using integer
        #    keys. This works for JSONStorage because json.dumps() will
        #    coerce integer document IDs to strings (JSON requires that
        #    keys are strings). It also works for YAMLStorage because
        #    the YAML spec allows integer keys.
        #
        #    TinyDB's Storage.write() expects data to be of type
        #    dict[str, dict[str, Any]] but we're passing in data of type
        #    dict[str, dict[int, Any]] instead.
        #
        #    As a result, we need to tell the type checker to ignore
        #    arg-type type errors.
        self.storage.write(data=int_keys_data)  # type: ignore[arg-type]
