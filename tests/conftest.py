# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from pathlib import Path
from typing import Final, Iterable

import pytest

from tinydb import TinyDB
from tinydb.storages import JSONStorage, MemoryStorage

from tinydantic.tinydb.middlewares import SortIntDocIDsMiddleware
from tinydantic.tinydb.storages import YAMLStorage

TEST_DATABASE_NAME: Final[str] = "test_db"


# tmp_path is function-scoped so we can't use it in the `db` fixture.
# Instead we use tmp_path_factory which is a session-scoped fixture.
@pytest.fixture(scope="session")
def json_storage_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """TODO: needs docstring."""
    return (
        tmp_path_factory.mktemp("json_storage") / f"{TEST_DATABASE_NAME}.json"
    )


# tmp_path is function-scoped so we can't use it in the `db` fixture.
# Instead we use tmp_path_factory which is a session-scoped fixture.
@pytest.fixture(scope="session")
def yaml_storage_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """TODO: needs docstring."""
    return (
        tmp_path_factory.mktemp("yaml_storage") / f"{TEST_DATABASE_NAME}.yaml"
    )


@pytest.fixture(
    scope="session",
    params=[
        "memory_storage",
        "json_storage",
        "pp_json_storage",
        "sort_keys_pp_json_storage",
        "sort_doc_ids_middleware_pp_json_storage",
        "yaml_storage",
    ],
)
def db_session(
    request: pytest.FixtureRequest,
    json_storage_path: Path,
    yaml_storage_path: Path,
) -> Iterable[TinyDB]:
    """TODO: needs docstring."""
    if request.param == "memory_storage":
        with TinyDB(
            storage=MemoryStorage,
        ) as db:
            yield db
    elif request.param == "json_storage":
        with TinyDB(
            path=json_storage_path,
            storage=JSONStorage,
        ) as db:
            yield db
    elif request.param == "pp_json_storage":
        with TinyDB(
            path=json_storage_path,
            storage=JSONStorage,
            indent=4,  # implies separators=(",", ": ")
        ) as db:
            yield db
    elif request.param == "sort_keys_pp_json_storage":
        with TinyDB(
            path=json_storage_path,
            storage=JSONStorage,
            sort_keys=True,
            indent=4,  # implies separators=(",", ": ")
        ) as db:
            yield db
    elif request.param == "sort_doc_ids_middleware_pp_json_storage":
        with TinyDB(
            path=json_storage_path,
            storage=SortIntDocIDsMiddleware(
                JSONStorage,
            ),  # sets sort_keys=True
            indent=4,  # implies separators=(",", ": ")
        ) as db:
            yield db
    elif request.param == "yaml_storage":
        with TinyDB(
            path=yaml_storage_path,
            storage=YAMLStorage,
        ) as db:
            yield db
    else:
        raise ValueError


@pytest.fixture
def db(db_session: TinyDB) -> Iterable[TinyDB]:
    """TODO: needs docstring."""
    db_session.drop_tables()
    yield db_session
    db_session.drop_tables()
