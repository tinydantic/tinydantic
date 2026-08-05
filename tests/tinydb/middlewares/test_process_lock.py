# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""ProcessLockMiddleware: single-process detection at open time."""

from __future__ import annotations

import subprocess
import sys
import textwrap

from typing import TYPE_CHECKING

import pytest

from tinydb import TinyDB
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import JSONStorage, MemoryStorage

from tinydantic import DatabaseLockedError, TinydanticUserError
from tinydantic.tinydb.middlewares import ProcessLockMiddleware

if TYPE_CHECKING:
    from pathlib import Path


class TestProcessLock:
    """Open-time lock acquisition and release."""

    def test_second_open_in_process_raises(self, tmp_path: Path):
        """A second TinyDB instance on the same file is refused."""
        path = tmp_path / "db.json"
        db = TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        try:
            with pytest.raises(DatabaseLockedError, match=r"db\.json"):
                TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        finally:
            db.close()

    def test_close_releases_the_lock(self, tmp_path: Path):
        """After close(), the database can be opened again."""
        path = tmp_path / "db.json"
        db = TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        db.close()
        reopened = TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        reopened.close()

    def test_lock_file_is_a_sidecar(self, tmp_path: Path):
        """The lock lives beside the database, never inside it."""
        path = tmp_path / "db.json"
        db = TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        db.insert({"probe": True})
        db.close()
        assert (tmp_path / "db.json.lock").exists()
        assert db.storage is not None

    def test_storage_reads_and_writes_pass_through(self, tmp_path: Path):
        """The middleware is transparent to the wrapped storage."""
        path = tmp_path / "db.json"
        db = TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        db.insert({"title": "Dune"})
        db.close()
        plain = TinyDB(path)
        try:
            assert plain.all() == [{"title": "Dune"}]
        finally:
            plain.close()

    def test_composes_under_caching_middleware(self, tmp_path: Path):
        """CachingMiddleware(ProcessLockMiddleware(...)) works."""
        path = tmp_path / "db.json"
        db = TinyDB(
            path,
            storage=CachingMiddleware(ProcessLockMiddleware(JSONStorage)),
        )
        try:
            db.insert({"title": "Dune"})
            with pytest.raises(DatabaseLockedError):
                TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        finally:
            db.close()

    def test_memory_storage_is_refused(self):
        """No path to lock — MemoryStorage needs no process lock."""
        with pytest.raises(TinydanticUserError, match="MemoryStorage"):
            TinyDB(storage=ProcessLockMiddleware(MemoryStorage))

    def test_cross_process_open_raises(self, tmp_path: Path):
        """A second *process* is refused while the lock is held."""
        path = tmp_path / "db.json"
        db = TinyDB(path, storage=ProcessLockMiddleware(JSONStorage))
        script = textwrap.dedent(
            f"""
            import sys

            from tinydb import TinyDB
            from tinydb.storages import JSONStorage

            from tinydantic import DatabaseLockedError
            from tinydantic.tinydb.middlewares import ProcessLockMiddleware

            try:
                TinyDB(
                    {str(path)!r},
                    storage=ProcessLockMiddleware(JSONStorage),
                )
            except DatabaseLockedError:
                sys.exit(0)
            sys.exit(1)
            """,
        )
        try:
            result = subprocess.run(
                [sys.executable, "-c", script],
                check=False,
                capture_output=True,
                timeout=30,
            )
        finally:
            db.close()
        assert result.returncode == 0, result.stderr.decode()
