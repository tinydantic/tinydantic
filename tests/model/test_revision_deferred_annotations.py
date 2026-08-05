# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Revision injection under PEP 649 deferred annotations.

This module deliberately omits ``from __future__ import
annotations``: on Python 3.14+ its class bodies then emit deferred
annotate functions (PEP 649 default semantics) instead of eager
``__annotations__`` dicts — the shape every other test module opts
out of via the future import, and the shape user code without the
import gets. The regression this guards: injecting ``revision_id``
by assigning an eager ``__annotations__`` dict shadowed the
deferred annotations and erased the user's own field annotations.
On Python 3.13 and earlier this module simply exercises the eager
path like everywhere else.
"""

from typing import TYPE_CHECKING
from uuid import UUID

import pytest

from tinydantic import RevisionFieldError, TinydanticModel

if TYPE_CHECKING:
    from tinydb import TinyDB


class TestDeferredAnnotationInjection:
    """use_revision injection must preserve user annotations."""

    def test_user_fields_survive_injection(self, db: "TinyDB"):
        """Injected revision_id merges with the declared fields."""

        class Book(TinydanticModel, database=db, use_revision=True):
            """Test model with an annotated, defaulted field."""

            title: str
            stock: int = 0

        assert set(Book.model_fields) == {
            "id",
            "title",
            "stock",
            "revision_id",
        }
        book = Book(title="Dune", stock=5).insert()
        assert isinstance(book.revision_id, UUID)
        assert book.stock == 5

    def test_collision_detected(self, db: "TinyDB"):
        """The declared-field check reads deferred annotations."""
        with pytest.raises(RevisionFieldError):

            class Book(TinydanticModel, database=db, use_revision=True):
                """Test model that declares the managed field."""

                revision_id: str  # type: ignore[assignment]
