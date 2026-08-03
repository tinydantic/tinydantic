# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Field markers for tinydantic models.

Markers are attached to fields through [typing.Annotated][], the
pydantic-v2-idiomatic place for per-field metadata:

```python
from typing import Annotated

from tinydantic import TinydanticModel, Unique


class User(TinydanticModel, database=db):
    email: Annotated[str, Unique()]
```
"""

from __future__ import annotations

from dataclasses import dataclass


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
    """
