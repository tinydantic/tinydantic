# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for the fluent find() query API."""

from __future__ import annotations

from tinydantic import (
    FindQueryError,
    SortFieldError,
    TinydanticUserError,
)


class TestErrorHierarchy:
    """FindQueryError and SortFieldError join the curated surface."""

    def test_find_query_error_is_user_error_and_value_error(
        self,
    ) -> None:
        """FindQueryError subclasses TinydanticUserError+ValueError."""
        assert issubclass(FindQueryError, TinydanticUserError)
        assert issubclass(FindQueryError, ValueError)

    def test_sort_field_error_is_find_query_error(self) -> None:
        """SortFieldError subclasses FindQueryError."""
        assert issubclass(SortFieldError, FindQueryError)
