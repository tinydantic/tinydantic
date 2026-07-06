# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Tests for validating TinyDB documents into models."""

from __future__ import annotations

from typing import TYPE_CHECKING

import tinydb.table

if TYPE_CHECKING:
    from tests.model.models import UserBase


class TestModelValidation:
    """Tests for TinydanticModel.from_tinydb_document."""

    def test_validate_document_from_dict(self, user_class: type[UserBase]):
        """A plain dict validates into a model with id left unset."""
        tinydb_document = {
            "name": "Alice",
            "age": 37,
        }
        user = user_class.from_tinydb_document(tinydb_document)
        assert user.name == "Alice"
        assert user.age == 37

    def test_validate_document_from_tinydb_document(
        self,
        user_class: type[UserBase],
    ):
        """A TinyDB Document validates with its doc_id mapped to id."""
        tinydb_document = tinydb.table.Document(
            value={
                "name": "Alice",
                "age": 37,
            },
            doc_id=0,
        )
        user = user_class.from_tinydb_document(tinydb_document)
        assert user.name == "Alice"
        assert user.age == 37
        assert user.id == 0
