# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Field markers and constraints for tinydantic models.

Markers are attached to fields through [typing.Annotated][], the
pydantic-v2-idiomatic place for per-field metadata:

```python
from typing import Annotated

from tinydantic import TinydanticModel, Unique


class User(TinydanticModel, database=db):
    email: Annotated[str, Unique()]
```

Multi-field (composite) uniqueness is declared with
[UniqueConstraint][tinydantic.UniqueConstraint] via the
``constraints=`` class keyword instead, because a composite
constraint is a property of the model, not of any single field:

```python
class Follow(
    TinydanticModel,
    database=db,
    constraints=(UniqueConstraint("follower_id", "followee_id"),),
):
    follower_id: int
    followee_id: int
```
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable


@dataclass(frozen=True)
class Unique:
    """Mark a field's values as unique within the model's table.

    Enforced with a check-then-write scan on create-style and
    instance-level writes (``insert``, ``insert_multiple``,
    ``save``, ``replace``, ``upsert``, ``patch``); violations
    raise
    [UniqueConstraintError][tinydantic.UniqueConstraintError].
    ``None`` values are exempt (SQL ``NULL`` semantics), the
    table-level bulk ``update()``/``update_multiple()`` path is a
    documented bypass, and the check is in-process only — see the
    models guide for the full contract.

    Attributes:
        key: Optional comparison-key callable. When set,
            uniqueness is enforced on ``key(value)`` instead of
            the stored value itself — for example
            ``Unique(key=str.casefold)`` for case-insensitive
            uniqueness that preserves the stored casing. The
            callable receives the field's **serialized** value
            (what storage holds), must be pure and deterministic,
            and must return a hashable result. It is never called
            with ``None`` (exempt values skip the check).
    """

    key: Callable[[Any], Hashable] | None = None

    def __post_init__(self) -> None:
        """Reject a non-callable comparison key."""
        if self.key is not None and not callable(self.key):
            msg = f"Unique key must be callable, got {self.key!r}"
            raise ValueError(msg)


@dataclass(frozen=True, init=False)
class UniqueConstraint:
    """Uniqueness over one or more fields, optionally normalized.

    Declared through the ``constraints=`` class keyword (a
    [TinydanticConfig][tinydantic.TinydanticConfig] key). A write
    that would duplicate the constraint's value tuple raises
    [UniqueConstraintError][tinydantic.UniqueConstraintError].
    A row participates in the check only when **all** of the
    constraint's fields are non-``None`` (SQL composite
    ``UNIQUE``/``NULL`` semantics); the table-level bulk
    ``update()``/``update_multiple()`` path is a documented
    bypass, and the check is in-process only.

    Attributes:
        fields: The constrained field names, in declared order.
        key: Optional comparison-key callable — the Python analog
            of an expression-based unique index. When set,
            uniqueness is enforced on ``key(*values)`` instead of
            the raw value tuple. The callable receives the
            constraint's **serialized** field values (what
            storage holds — a ``datetime`` arrives as an ISO
            string), positionally, in declared field order; it
            must be pure and deterministic and return a hashable
            result. It is never called when any field value is
            ``None``. Example — slug unique per author, ignoring
            case::

                UniqueConstraint(
                    "author_id",
                    "slug",
                    key=lambda a, s: (a, s.casefold()),
                )
    """

    fields: tuple[str, ...]
    key: Callable[..., Hashable] | None

    def __init__(
        self,
        *fields: str,
        key: Callable[..., Hashable] | None = None,
    ) -> None:
        """Validate and freeze the constraint.

        Args:
            fields: One or more model field names.
            key: Optional comparison-key callable (see the class
                docstring for the contract).

        Raises:
            ValueError: On zero fields, duplicate field names, or
                a non-callable ``key``.
        """
        if not fields:
            msg = "UniqueConstraint requires at least one field"
            raise ValueError(msg)
        duplicates = sorted(
            {name for name in fields if fields.count(name) > 1},
        )
        if duplicates:
            names = ", ".join(repr(name) for name in duplicates)
            msg = f"UniqueConstraint got duplicate field(s): {names}"
            raise ValueError(msg)
        if key is not None and not callable(key):
            msg = f"UniqueConstraint key must be callable, got {key!r}"
            raise ValueError(msg)
        object.__setattr__(self, "fields", tuple(fields))
        object.__setattr__(self, "key", key)
