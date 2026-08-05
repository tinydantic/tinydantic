# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the SortIntDocIDsMiddleware storage middleware."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from tinydb import TinyDB
from tinydb.middlewares import CachingMiddleware
from tinydb.storages import JSONStorage, MemoryStorage
from tinydb.table import Document

from tinydantic.tinydb.middlewares import SortIntDocIDsMiddleware


class TestSortIntDocIDsMiddleware:
    """Verify documents are sorted by integer doc_id on write."""

    def test_sort_order_positive_doc_ids(
        self,
        json_storage_path: Path,
        sorted_json_db: TinyDB,
    ):
        """Positive doc_ids serialize in ascending numeric order."""
        # Insert documents into the "user" table
        user_table = sorted_json_db.table("user")

        user_table.insert(
            Document(value={"name": "Alice", "age": 37}, doc_id=3),
        )
        user_table.insert(
            Document(value={"name": "Bob", "age": 28}, doc_id=10),
        )
        user_table.insert(
            Document(value={"name": "Charlie", "age": 58}, doc_id=6),
        )

        # close the database before we access the database file (this
        # also flushes the cache if any caching middleware is being
        # used)
        sorted_json_db.close()

        # read the raw JSON text from the database file
        with Path.open(json_storage_path) as file:
            db_text = file.read()

        expected_text = dedent("""\
        {
            "user": {
                "3": {
                    "name": "Alice",
                    "age": 37
                },
                "6": {
                    "name": "Charlie",
                    "age": 58
                },
                "10": {
                    "name": "Bob",
                    "age": 28
                }
            }
        }
        """).rstrip("\n")

        # verify that the raw JSON text from the database matches the
        # expected_text above
        assert db_text == expected_text

    def test_sort_order_negative_doc_ids(
        self,
        json_storage_path: Path,
        sorted_json_db: TinyDB,
    ):
        """Negative doc_ids serialize in ascending numeric order."""
        # Insert documents into the "user" table
        user_table = sorted_json_db.table("user")

        user_table.insert(
            Document(value={"name": "Alice", "age": 37}, doc_id=-3),
        )
        user_table.insert(
            Document(value={"name": "Bob", "age": 28}, doc_id=-10),
        )
        user_table.insert(
            Document(value={"name": "Charlie", "age": 58}, doc_id=-6),
        )

        # close the database before we access the database file (this
        # also flushes the cache if any caching middleware is being
        # used)
        sorted_json_db.close()

        # read the raw JSON text from the database file
        with Path.open(json_storage_path) as file:
            db_text = file.read()

        expected_text = dedent("""\
        {
            "user": {
                "-10": {
                    "name": "Bob",
                    "age": 28
                },
                "-6": {
                    "name": "Charlie",
                    "age": 58
                },
                "-3": {
                    "name": "Alice",
                    "age": 37
                }
            }
        }
        """).rstrip("\n")

        # verify that the raw JSON text from the database matches the
        # expected_text above
        assert db_text == expected_text

    def test_composes_over_caching_middleware(self, tmp_path: Path):
        """The middleware works wrapped around CachingMiddleware.

        CachingMiddleware has no ``kwargs`` attribute, so any
        implementation that reaches into the wrapped storage's
        kwargs breaks this composition.
        """
        db_path = tmp_path / "cached.json"
        with TinyDB(
            path=db_path,
            storage=SortIntDocIDsMiddleware(
                CachingMiddleware(JSONStorage),
            ),
            indent=4,
        ) as db:
            user_table = db.table("user")
            user_table.insert(
                Document(value={"name": "Bob", "age": 28}, doc_id=10),
            )
            user_table.insert(
                Document(value={"name": "Alice", "age": 37}, doc_id=3),
            )

        db_text = db_path.read_text()

        expected_text = dedent("""\
        {
            "user": {
                "3": {
                    "name": "Alice",
                    "age": 37
                },
                "10": {
                    "name": "Bob",
                    "age": 28
                }
            }
        }
        """).rstrip("\n")

        assert db_text == expected_text

    def test_works_with_memory_storage(self):
        """The middleware needs nothing storage-specific.

        MemoryStorage takes no dump kwargs at all; the middleware
        must not require them.
        """
        with TinyDB(storage=SortIntDocIDsMiddleware(MemoryStorage)) as db:
            user_table = db.table("user")
            user_table.insert(
                Document(value={"name": "Bob", "age": 28}, doc_id=10),
            )
            user_table.insert(
                Document(value={"name": "Alice", "age": 37}, doc_id=3),
            )

            assert {doc.doc_id for doc in user_table} == {3, 10}

    def test_user_sort_keys_choice_is_respected(self, tmp_path: Path):
        """An explicit sort_keys=False survives a write untouched.

        Documents are still serialized in numeric doc_id order —
        the middleware pre-sorts the data instead of overriding the
        storage's ``sort_keys`` setting.
        """
        db_path = tmp_path / "unsorted_fields.json"
        with TinyDB(
            path=db_path,
            storage=SortIntDocIDsMiddleware(JSONStorage),
            sort_keys=False,
            indent=4,
        ) as db:
            user_table = db.table("user")
            user_table.insert(
                Document(value={"name": "Bob", "age": 28}, doc_id=10),
            )
            user_table.insert(
                Document(value={"name": "Alice", "age": 37}, doc_id=3),
            )

            middleware = db.storage
            assert isinstance(middleware, SortIntDocIDsMiddleware)
            storage = middleware.storage
            assert isinstance(storage, JSONStorage)
            assert storage.kwargs["sort_keys"] is False

        db_text = db_path.read_text()

        expected_text = dedent("""\
        {
            "user": {
                "3": {
                    "name": "Alice",
                    "age": 37
                },
                "10": {
                    "name": "Bob",
                    "age": 28
                }
            }
        }
        """).rstrip("\n")

        assert db_text == expected_text

    def test_tables_serialize_in_sorted_name_order(self, tmp_path: Path):
        """Tables serialize sorted by name, fields in model order."""
        db_path = tmp_path / "tables.json"
        with TinyDB(
            path=db_path,
            storage=SortIntDocIDsMiddleware(JSONStorage),
            indent=4,
        ) as db:
            db.table("user").insert(
                Document(value={"name": "Alice", "age": 37}, doc_id=1),
            )
            db.table("admin").insert(
                Document(value={"name": "Bob", "age": 28}, doc_id=1),
            )

        db_text = db_path.read_text()

        expected_text = dedent("""\
        {
            "admin": {
                "1": {
                    "name": "Bob",
                    "age": 28
                }
            },
            "user": {
                "1": {
                    "name": "Alice",
                    "age": 37
                }
            }
        }
        """).rstrip("\n")

        assert db_text == expected_text

    def test_sort_order_positive_and_negative_doc_ids(
        self,
        json_storage_path: Path,
        sorted_json_db: TinyDB,
    ):
        """Mixed positive/negative doc_ids sort in ascending order."""
        # Insert documents into the "user" table
        user_table = sorted_json_db.table("user")

        user_table.insert(
            Document(value={"name": "Alice", "age": 37}, doc_id=-3),
        )
        user_table.insert(
            Document(value={"name": "Bob", "age": 28}, doc_id=10),
        )
        user_table.insert(
            Document(value={"name": "Charlie", "age": 58}, doc_id=0),
        )

        # close the database before we access the database file (this
        # also flushes the cache if any caching middleware is being
        # used)
        sorted_json_db.close()

        # read the raw JSON text from the database file
        with Path.open(json_storage_path) as file:
            db_text = file.read()

        expected_text = dedent("""\
        {
            "user": {
                "-3": {
                    "name": "Alice",
                    "age": 37
                },
                "0": {
                    "name": "Charlie",
                    "age": 58
                },
                "10": {
                    "name": "Bob",
                    "age": 28
                }
            }
        }
        """).rstrip("\n")

        # verify that the raw JSON text from the database matches the
        # expected_text above
        assert db_text == expected_text
