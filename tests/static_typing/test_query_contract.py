# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""The static-typing contract for query building.

Nothing here runs as a test. Every function is a claim about what
mypy and pyright infer, checked by `poe types`; a claim that stops
holding fails the type check instead of silently drifting away from
what `docs/usage/queries.md` promises.
"""

from pydantic import BaseModel
from tinydb import TinyDB
from tinydb.queries import QueryInstance
from tinydb.storages import MemoryStorage
from typing_extensions import assert_type

from tinydantic import FindQuery, TinydanticModel, q

_db = TinyDB(storage=MemoryStorage)


class Address(BaseModel):
    """Nested model, for nested-field queries."""

    city: str


class User(TinydanticModel, database=_db, table_name="users"):
    """Model under test."""

    name: str
    age: int
    address: Address


class Post(TinydanticModel, database=_db, table_name="posts"):
    """Model whose fields carry ordinary defaults."""

    title: str
    views: int = 0
    tags: list[str] = []  # noqa: RUF012
    draft: bool = True


def bare_field_access_types_as_the_annotation() -> None:
    """Pin the mismatch that q() exists to correct.

    A checker reads the annotation, so a bare comparison types as
    `bool`. If this claim ever stops holding — a typed descriptor,
    a checker plugin — the docs in `queries.md` and `quickstart.md`
    describe a problem that no longer exists.
    """
    assert_type(User.name == "Alice", bool)
    assert_type(User.age > 30, bool)


def q_makes_conditions_type_as_conditions() -> None:
    """q() restores the runtime truth for the checker.

    Only the ordering operators are asserted directly: TinyDB leaves
    `Query.__eq__` without a return annotation, so mypy types every
    `==` condition as `Any` while pyright infers `QueryInstance`.
    Equality conditions are therefore pinned the way users meet them
    — as arguments to a read method, below.
    """
    assert_type(q(User.age) > 30, QueryInstance)
    assert_type(q(User.age) <= 30, QueryInstance)


def every_condition_spelling_is_accepted() -> None:
    """Each documented way to build a condition type-checks.

    Asserting the search result rather than the condition keeps the
    claim meaningful under both checkers, and matches what breaks
    for a user when a spelling stops being accepted.
    """
    assert_type(User.search(q(User.name) == "Alice"), list[User])
    assert_type(User.search(q("name") == "Alice"), list[User])
    assert_type(User.search(q(User.address.city) == "Berlin"), list[User])
    assert_type(User.search(q(User.id) == 1), list[User])
    assert_type(User.search(q(User.name).matches("A.*")), list[User])
    assert_type(User.search(q(User.name).search("lic")), list[User])
    assert_type(
        User.search(q(User.age).test(bool)),
        list[User],
    )
    assert_type(User.search(q(User.id).one_of([1, 3])), list[User])


def q_conditions_compose() -> None:
    """Logical operators keep a composed condition acceptable."""
    assert_type(~(q(User.age) > 30), QueryInstance)
    assert_type(
        User.search((q(User.age) > 30) & (q(User.name) == "Alice")),
        list[User],
    )
    assert_type(
        User.search((q(User.name) == "Alice") | (q(User.name) == "Bob")),
        list[User],
    )


def read_methods_keep_their_return_types() -> None:
    """Keep return types intact across every read entry point.

    Overloaded methods are the ones that matter. Passing a bare
    comparison to `get()` costs mypy the whole return type (it falls
    back to `Any`), which is why the docs steer readers to q()
    rather than to `# type: ignore`.
    """
    assert_type(User.search(q(User.name) == "Alice"), list[User])
    assert_type(User.get(q(User.name) == "Alice"), User | None)
    assert_type(User.get_or_raise(q(User.name) == "Alice"), User)
    assert_type(User.count(q(User.age) > 30), int)
    assert_type(User.contains(q(User.age) > 30), bool)
    assert_type(User.find(q(User.age) > 30), FindQuery[User])


def find_chains_keep_their_element_type() -> None:
    """Keep a chain bound to the model it came from."""
    chain = User.find(q(User.age) > 30).sort("age").limit(10)
    assert_type(chain, FindQuery[User])
    assert_type(chain.all(), list[User])
    assert_type(chain.first(), User | None)
    assert_type(chain.first_or_raise(), User)
    assert_type(chain.count(), int)
    assert_type(chain.exists(), bool)


def instance_attributes_are_ordinary_values() -> None:
    """Instance access is unaffected by the class-level sugar."""
    user = User(name="Alice", age=30, address=Address(city="Portland"))
    assert_type(user.name, str)
    assert_type(user.age, int)
    assert_type(user.name.upper(), str)
    assert_type(user.id, int | None)


def ordinary_field_defaults_type_check() -> None:
    """Plain defaults must stay legal on the class definition.

    `Post` above declares `views = 0` and `tags = []` with no
    wrapper. The typed-descriptor alternative to q() breaks exactly
    this (a bare default stops assigning to `Mapped[T]`), and that
    cost is the recorded reason it was rejected — see
    `docs/contributing/static_typing.md`.
    """
    post = Post(title="hello")
    assert_type(post.views, int)
    assert_type(post.tags, list[str])
    assert_type(post.draft, bool)
