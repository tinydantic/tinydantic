# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for YAMLStorage's write-time safety.

``YAMLStorage.read`` uses ``yaml.safe_load``, so anything the
storage writes must stay loadable by the safe loader. A full-Dumper
``yaml.dump`` would happily serialize arbitrary Python objects as
``!!python/object`` tags that the storage's own ``read`` then
refuses to load — bricking the database file until hand-edited.
These tests pin the safe behavior: objects the safe dumper cannot
represent fail fast at write time, before the file is touched.
"""

from __future__ import annotations

import subprocess
import sys

from typing import TYPE_CHECKING

import pytest
import yaml

from tinydb import TinyDB

from tinydantic.tinydb import storages
from tinydantic.tinydb.storages import YAMLStorage

if TYPE_CHECKING:
    from pathlib import Path


class _Gadget:
    """An arbitrary non-YAML-safe object."""


@pytest.fixture
def yaml_db_path(tmp_path: Path) -> Path:
    """Return a fresh YAML database file path."""
    return tmp_path / "db.yaml"


def test_round_trips_plain_data(yaml_db_path: Path) -> None:
    """Plain JSON-safe data still round-trips through the file."""
    with TinyDB(path=yaml_db_path, storage=YAMLStorage) as db:
        db.table("users").insert({"name": "Alice", "age": 30})
    with TinyDB(path=yaml_db_path, storage=YAMLStorage) as db:
        assert db.table("users").all() == [{"name": "Alice", "age": 30}]


def test_rejects_python_objects_at_write_time(yaml_db_path: Path) -> None:
    """Writing an arbitrary Python object raises RepresenterError.

    The error must surface at write time — the safe dumper has no
    representer for arbitrary objects — instead of full-Dumper
    ``yaml.dump`` embedding a ``!!python/object`` tag the storage's
    own ``safe_load`` read would then choke on.
    """
    with TinyDB(path=yaml_db_path, storage=YAMLStorage) as db:
        table = db.table("users")
        table.insert({"name": "Alice"})
        with pytest.raises(yaml.representer.RepresenterError):
            table.insert({"gadget": _Gadget()})


def test_file_stays_readable_after_rejected_write(yaml_db_path: Path) -> None:
    """A rejected write leaves the database file loadable.

    The write must fail before the file is touched, so previously
    stored documents survive and ``read`` keeps working — the
    database is never bricked.
    """
    with TinyDB(path=yaml_db_path, storage=YAMLStorage) as db:
        table = db.table("users")
        table.insert({"name": "Alice"})
        with pytest.raises(yaml.representer.RepresenterError):
            table.insert({"gadget": _Gadget()})
    with TinyDB(path=yaml_db_path, storage=YAMLStorage) as db:
        assert db.table("users").all() == [{"name": "Alice"}]


def test_missing_pyyaml_raises_helpful_error(
    yaml_db_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without PyYAML, constructing YAMLStorage names the extra."""
    monkeypatch.setattr(storages, "yaml", None)
    with pytest.raises(ImportError, match=r"tinydantic\[yaml\]"):
        YAMLStorage(str(yaml_db_path))


def test_importing_tinydantic_never_needs_pyyaml() -> None:
    """A bare install can import tinydantic and its storages."""
    code = (
        "import sys; sys.modules['yaml'] = None\n"
        "import importlib\n"
        "sys.modules.pop('yaml')\n"
        "import builtins\n"
        "real_import = builtins.__import__\n"
        "def block(name, *args, **kwargs):\n"
        "    if name == 'yaml' or name.startswith('yaml.'):\n"
        "        raise ImportError('blocked')\n"
        "    return real_import(name, *args, **kwargs)\n"
        "builtins.__import__ = block\n"
        "import tinydantic\n"
        "import tinydantic.tinydb.storages as s\n"
        "assert s.yaml is None\n"
        "print('ok')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
