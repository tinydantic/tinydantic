# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Tests for get(), get_or_none() and the by-id read variants."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tinydantic import DocumentNotFoundError, q

if TYPE_CHECKING:
    from tests.model.models import UserBase


class TestGet:
    """get(cond) asserts a match, like ``d[key]``."""

    def test_returns_the_matching_model(
        self,
        user_class: type[UserBase],
    ) -> None:
        """A matching condition returns the validated model."""
        user_class(name="Alice", age=37).insert()
        result = user_class.get(q(user_class.name) == "Alice")
        assert isinstance(result, user_class)
        assert result.name == "Alice"
        assert result.id is not None

    def test_missing_raises_naming_the_query(
        self,
        user_class: type[UserBase],
    ) -> None:
        """A field condition with no match names model and table."""
        with pytest.raises(DocumentNotFoundError) as excinfo:
            user_class.get(q(user_class.name) == "Nobody")
        message = str(excinfo.value)
        assert repr(user_class.get_table().name) in message
        assert repr(user_class.__name__) in message

    def test_missing_id_equality_names_the_id(
        self,
        user_class: type[UserBase],
    ) -> None:
        """A bare id equality reports the id it looked for."""
        with pytest.raises(DocumentNotFoundError, match="id 999"):
            user_class.get(q(user_class.id) == 999)

    def test_id_equality_fetches_by_document_id(
        self,
        user_class: type[UserBase],
    ) -> None:
        """get(Model.id == n) is a document-id lookup."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        assert user_class.get(q(user_class.id) == user.id).name == "Alice"

    def test_unexpected_tinydb_return_raises(
        self,
        user_class: type[UserBase],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A contract-violating Table.get() names the bad type.

        TinyDB's Table.get(cond) contract only allows None or a
        Document. The defensive fallthrough should name the
        offending type rather than raise bare.
        """
        monkeypatch.setattr(
            user_class.get_table(),
            "get",
            lambda *_, **__: 42,
        )
        with pytest.raises(TypeError, match="unexpected return type"):
            user_class.get(q(user_class.name) == "Alice")


class TestGetOrNone:
    """get_or_none(cond) is the lenient half, like ``d.get(key)``."""

    def test_returns_the_matching_model(
        self,
        user_class: type[UserBase],
    ) -> None:
        """A match returns the validated model."""
        user_class(name="Alice", age=37).insert()
        result = user_class.get_or_none(q(user_class.name) == "Alice")
        assert result is not None
        assert result.age == 37

    def test_missing_returns_none(
        self,
        user_class: type[UserBase],
    ) -> None:
        """No match is None, not an error."""
        assert user_class.get_or_none(q(user_class.name) == "Nobody") is None

    def test_missing_id_returns_none(
        self,
        user_class: type[UserBase],
    ) -> None:
        """The lenient by-id spelling goes through a condition."""
        assert user_class.get_or_none(q(user_class.id) == 999) is None


class TestGetById:
    """get_by_id() asserts the id exists."""

    def test_returns_the_model(self, user_class: type[UserBase]) -> None:
        """A stored id returns the validated model."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        result = user_class.get_by_id(user.id)
        assert isinstance(result, user_class)
        assert result.name == "Alice"

    def test_missing_raises_naming_the_id(
        self,
        user_class: type[UserBase],
    ) -> None:
        """An absent id raises, naming the id."""
        with pytest.raises(DocumentNotFoundError, match="id 999"):
            user_class.get_by_id(999)


class TestGetByIds:
    """get_by_ids() asserts every id, and is positional."""

    def test_returns_models_in_the_order_given(
        self,
        user_class: type[UserBase],
    ) -> None:
        """Results follow the caller's order, not storage order."""
        first = user_class(name="Alice", age=37).insert()
        second = user_class(name="Bob", age=24).insert()
        assert first.id is not None
        assert second.id is not None
        results = user_class.get_by_ids([second.id, first.id])
        assert [user.name for user in results] == ["Bob", "Alice"]

    def test_repeated_id_yields_a_document_per_occurrence(
        self,
        user_class: type[UserBase],
    ) -> None:
        """len(result) == len(doc_ids) always holds."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        results = user_class.get_by_ids([user.id, user.id])
        assert [u.name for u in results] == ["Alice", "Alice"]

    def test_missing_id_refuses_the_whole_batch(
        self,
        user_class: type[UserBase],
    ) -> None:
        """One absent id fails the read, naming that id."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        with pytest.raises(DocumentNotFoundError, match="id 999"):
            user_class.get_by_ids([user.id, 999])

    def test_empty_list_is_empty_result(
        self,
        user_class: type[UserBase],
    ) -> None:
        """No ids asserts nothing and returns nothing."""
        assert user_class.get_by_ids([]) == []

    def test_lenient_batch_read_uses_a_condition(
        self,
        user_class: type[UserBase],
    ) -> None:
        """search(one_of) is the best-effort batch spelling."""
        user = user_class(name="Alice", age=37).insert()
        assert user.id is not None
        found = user_class.search(q(user_class.id).one_of([user.id, 999]))
        assert [u.name for u in found] == ["Alice"]
