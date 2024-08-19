# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydb import TinyDB
from tinydb.storages import JSONStorage

from tinydantic.tinydb.middlewares import SortIntDocIDsMiddleware

if TYPE_CHECKING:
    from pathlib import Path
    from typing import Iterable


@pytest.fixture
def sorted_json_db(json_storage_path: Path) -> Iterable[TinyDB]:
    """TODO: needs docstring."""
    with TinyDB(
        path=json_storage_path,
        storage=SortIntDocIDsMiddleware(JSONStorage),
        indent=4,  # implies separators=(",", ": ")
    ) as db:
        db.drop_tables()
        yield db
