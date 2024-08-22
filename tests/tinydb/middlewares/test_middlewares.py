# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import TYPE_CHECKING

from tinydb.table import Document

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestSortIntDocIDsMiddleware:
    """TODO: needs docstring."""

    def test_sort_order_positive_doc_ids(
        self,
        json_storage_path: Path,
        sorted_json_db: TinyDB,
    ):
        """TODO: needs docstring."""
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
                    "age": 37,
                    "name": "Alice"
                },
                "6": {
                    "age": 58,
                    "name": "Charlie"
                },
                "10": {
                    "age": 28,
                    "name": "Bob"
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
        """TODO: needs docstring."""
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
                    "age": 28,
                    "name": "Bob"
                },
                "-6": {
                    "age": 58,
                    "name": "Charlie"
                },
                "-3": {
                    "age": 37,
                    "name": "Alice"
                }
            }
        }
        """).rstrip("\n")

        # verify that the raw JSON text from the database matches the
        # expected_text above
        assert db_text == expected_text

    def test_sort_order_positive_and_negative_doc_ids(
        self,
        json_storage_path: Path,
        sorted_json_db: TinyDB,
    ):
        """TODO: needs docstring."""
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
                    "age": 37,
                    "name": "Alice"
                },
                "0": {
                    "age": 58,
                    "name": "Charlie"
                },
                "10": {
                    "age": 28,
                    "name": "Bob"
                }
            }
        }
        """).rstrip("\n")

        # verify that the raw JSON text from the database matches the
        # expected_text above
        assert db_text == expected_text
