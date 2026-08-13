# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Custom TinyDB storage middlewares."""

from __future__ import annotations

import os
import sys

from typing import TYPE_CHECKING, Any

from tinydb.middlewares import Middleware

from tinydantic._errors import DatabaseLockedError, TinydanticUserError

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

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


class ProfilingMiddleware(Middleware):
    """Middleware that counts the storage operations under it.

    Wraps any [Storage][tinydb.storages.Storage] and counts each
    ``read()`` and ``write()`` call that reaches it, so the storage
    cost of an operation can be measured instead of guessed. TinyDB
    has no indexes — costs are paid in whole-table reads and
    writes — so the two counters are the numbers that matter when
    asking why something is slow, and they are exact where timings
    are noisy. Keep a reference to the middleware; it is the same
    object TinyDB uses:

    ```python
    storage = ProfilingMiddleware(JSONStorage)
    db = TinyDB("db.json", storage=storage)
    ...
    storage.read_count, storage.write_count
    ```

    Counters start at zero, live on the instance, and only ever
    count operations on the storage this instance wraps. Call
    [reset()][tinydantic.tinydb.middlewares.ProfilingMiddleware.reset]
    to zero them between measurements.

    Middlewares stack, and the position in the stack is what gets
    measured. TinyDB talks to the **outermost** wrapper, so
    ``ProfilingMiddleware(CachingMiddleware(JSONStorage))`` counts
    what the database asks for *before* caching, while
    ``CachingMiddleware(ProfilingMiddleware(JSONStorage))`` counts
    only the operations the cache lets through to the file. Wrap
    outermost to measure the database's demand; wrap innermost to
    measure real disk traffic.

    Attributes:
        read_count: Number of ``read()`` calls seen so far.
        write_count: Number of ``write()`` calls seen so far.
    """

    def __init__(self, storage_cls: type[Storage] | Middleware) -> None:
        """Wrap ``storage_cls`` with operation counting.

        Args:
            storage_cls: The storage class — or another middleware,
                such as ``CachingMiddleware(JSONStorage)`` — to
                wrap.
        """
        super().__init__(storage_cls)
        self.read_count: int = 0
        self.write_count: int = 0

    def read(self) -> Any:
        """Count the read, then forward it to the wrapped storage."""
        self.read_count += 1
        return self.storage.read()

    def write(self, data: Any) -> None:
        """Count the write, then forward it to the wrapped storage."""
        self.write_count += 1
        self.storage.write(data)

    def reset(self) -> None:
        """Zero both counters."""
        self.read_count = 0
        self.write_count = 0


def _acquire_lock(fd: int) -> None:
    """Take a non-blocking exclusive OS lock on ``fd``.

    Raises:
        OSError: If another process (or another handle in this
            process) already holds the lock.
    """
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release_lock(fd: int) -> None:
    """Release the OS lock held on ``fd``."""
    if sys.platform == "win32":
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(fd, fcntl.LOCK_UN)


class ProcessLockMiddleware(Middleware):
    """Middleware that refuses to share a database across processes.

    TinyDB is single-process software: it has no locking, and its
    in-memory table caches assume sole ownership of the file, so a
    second process silently corrupts data or loses writes. This
    middleware enforces that contract at open time. It takes a
    non-blocking exclusive OS advisory lock on a sidecar file
    (``<database path>.lock``) when the database opens; if the lock
    is already held — by another process, or by a second TinyDB
    instance in this process (two handles corrupt each other's
    table caches just as badly) — it raises
    [DatabaseLockedError][tinydantic.DatabaseLockedError]
    immediately instead of letting the misconfiguration corrupt
    data slowly:

    ```python
    db = TinyDB("db.json", storage=ProcessLockMiddleware(JSONStorage))
    ```

    The lock is released when the database is closed, and the OS
    releases it automatically if the process dies, so no stale-lock
    handling is ever needed. The sidecar ``.lock`` file itself is
    left behind (deleting lock files is inherently racy); it is
    empty and harmless.

    Warning:
        This middleware *detects* concurrent opens by cooperating
        processes — it does not make multi-process access safe,
        and it cannot stop writers that ignore advisory locks
        (text editors, scripts, other tools). Advisory locks are
        also unreliable on network filesystems (NFS, SMB); keep
        database files on local disks. See the Concurrency page.

    The wrapped storage must be file-backed: the lock path is
    derived from the storage's first argument. ``MemoryStorage``
    needs no lock — it is unshareable between processes by nature.
    """

    def __init__(self, storage_cls: type[Storage] | Middleware) -> None:
        """Wrap ``storage_cls`` with open-time process locking.

        Args:
            storage_cls: The storage class — or another middleware,
                such as ``CachingMiddleware(JSONStorage)`` — to
                wrap.
        """
        super().__init__(storage_cls)
        self._lock_fd: int | None = None

    def __call__(self, *args: Any, **kwargs: Any) -> ProcessLockMiddleware:
        """Acquire the process lock, then open the wrapped storage.

        TinyDB calls this with the storage arguments; the first
        positional argument is the database path.

        Raises:
            DatabaseLockedError: If another process (or another
                TinyDB instance in this one) holds the lock.
            TinydanticUserError: If there is no path argument to
                derive the lock file from (for example with
                ``MemoryStorage``, which needs no process lock).
        """
        if not args:
            msg = (
                "ProcessLockMiddleware needs a file-backed storage "
                "(it derives its lock file from the database "
                "path). MemoryStorage cannot be shared between "
                "processes and needs no lock."
            )
            raise TinydanticUserError(msg)
        path = os.fspath(args[0])
        fd = os.open(f"{path}.lock", os.O_RDWR | os.O_CREAT)
        try:
            _acquire_lock(fd)
        except OSError:
            os.close(fd)
            raise DatabaseLockedError(path=str(path)) from None
        try:
            super().__call__(*args, **kwargs)
        except BaseException:
            _release_lock(fd)
            os.close(fd)
            raise
        self._lock_fd = fd
        return self

    def close(self) -> None:
        """Close the wrapped storage and release the process lock."""
        self.storage.close()
        if self._lock_fd is not None:
            _release_lock(self._lock_fd)
            os.close(self._lock_fd)
            self._lock_fd = None
