# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""ProfilingMiddleware: storage operation counters."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tinydb import TinyDB
from tinydb.storages import JSONStorage, MemoryStorage

from tinydantic.tinydb.middlewares import ProfilingMiddleware

if TYPE_CHECKING:
    from pathlib import Path


class TestProfilingMiddleware:
    """Read/write counting and counter lifecycle."""

    def test_counters_start_at_zero(self):
        """A fresh middleware has counted nothing."""
        storage = ProfilingMiddleware(MemoryStorage)
        assert storage.read_count == 0
        assert storage.write_count == 0

    def test_read_and_write_calls_are_counted(self):
        """Each read()/write() call increments its counter by one."""
        storage = ProfilingMiddleware(MemoryStorage)
        storage()  # bind the underlying storage, as TinyDB would
        storage.write({"t": {"1": {"n": 1}}})
        storage.read()
        storage.read()
        assert storage.write_count == 1
        assert storage.read_count == 2

    def test_operations_are_forwarded(self):
        """Counting does not alter what the storage stores."""
        storage = ProfilingMiddleware(MemoryStorage)
        storage()
        storage.write({"t": {"1": {"n": 1}}})
        assert storage.read() == {"t": {"1": {"n": 1}}}

    def test_counts_operations_through_tinydb(self):
        """Table operations are counted on the kept reference."""
        storage = ProfilingMiddleware(MemoryStorage)
        with TinyDB(storage=storage) as db:
            table = db.table("t")
            table.insert({"n": 1})
            assert storage.write_count == 1
            reads_after_insert = storage.read_count
            assert reads_after_insert > 0
            table.all()
            assert storage.read_count == reads_after_insert + 1

    def test_wraps_file_storage(self, tmp_path: Path):
        """A file-backed storage is counted and still hits disk."""
        path = tmp_path / "db.json"
        storage = ProfilingMiddleware(JSONStorage)
        with TinyDB(path, storage=storage) as db:
            db.insert({"n": 1})
            assert storage.write_count == 1
        assert path.read_text() == '{"_default": {"1": {"n": 1}}}'

    def test_reset_zeroes_both_counters(self):
        """reset() returns the middleware to its initial state."""
        storage = ProfilingMiddleware(MemoryStorage)
        storage()
        storage.write({})
        storage.read()
        storage.reset()
        assert storage.read_count == 0
        assert storage.write_count == 0

    def test_instances_count_independently(self):
        """Counters live on the instance, not the class."""
        counted = ProfilingMiddleware(MemoryStorage)
        idle = ProfilingMiddleware(MemoryStorage)
        counted()
        counted.write({})
        assert counted.write_count == 1
        assert idle.write_count == 0
