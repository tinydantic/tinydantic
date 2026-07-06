# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Configuration machinery for tinydantic models.

Design note — why tinydantic config does NOT live in ``model_config``:

Pydantic merges ``model_config`` across multiple base classes in
"last wins" order — the *opposite* of Python's MRO (see
https://github.com/pydantic/pydantic/issues/9992). Community fixes
were rejected as breaking changes, and the behavior may change in
pydantic v3. Storing tinydantic's keys there would (a) inherit those
surprising semantics, (b) risk future key collisions with
``ConfigDict``, and (c) couple binding resolution to behavior pydantic
itself may flip.

Instead, every model class stores only the config keys *explicitly set
on it* in its own ``__tinydantic_config__`` class attribute, and
lookup walks ``cls.__mro__`` for the first class that provides the
key — standard Python attribute semantics. For the one scenario where
pydantic's ordering and Python's ordering could disagree (two
*unrelated* bases providing conflicting values), tinydantic refuses to
guess and raises
[AmbiguousConfigError][tinydantic.errors.AmbiguousConfigError]
at class-definition time instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from tinydantic.errors import AmbiguousConfigError

if TYPE_CHECKING:
    from tinydb import TinyDB

# Name of the per-class attribute holding explicitly-set config.
CONFIG_ATTR = "__tinydantic_config__"

_CONFIG_KEYS = ("database", "table_name")


class TinydanticConfig(TypedDict, total=False):
    """Configuration options for tinydantic models.

    This is a plain [TypedDict][typing.TypedDict] — deliberately NOT a
    ``pydantic.ConfigDict`` subclass; see the module docstring for the
    design rationale. Values are provided as class keyword arguments:

    ```python
    class User(TinydanticModel, database=db, table_name="users"):
        name: str
    ```
    """

    database: TinyDB
    """TinyDB database where documents of this model are stored."""

    table_name: str | None
    """Database table name for documents of this model.

    When unset (or falsy), the table name is derived from the model
    class name converted to snake_case — for example, a model class
    named ``AdminUser`` uses the table ``admin_user``.
    """


def get_config_value(
    model_class: type,
    key: str,
    default: Any = None,
) -> Any:
    """Resolve a tinydantic config key for a model class.

    Walks ``model_class.__mro__`` and returns the value from the first
    class whose own ``__tinydantic_config__`` contains ``key`` —
    standard Python attribute-lookup semantics, unlike pydantic's
    ``model_config`` merge (see the module docstring).

    Args:
        model_class: The model class to resolve the key for.
        key: The [TinydanticConfig][tinydantic.config.TinydanticConfig]
            key to look up.
        default: Value returned when no class in the MRO provides the
            key.

    Returns:
        The resolved value, or ``default``.
    """
    for klass in model_class.__mro__:
        config = klass.__dict__.get(CONFIG_ATTR)
        if config is not None and key in config:
            return config[key]
    return default


def check_config_ambiguity(model_class: type) -> None:
    """Raise if unrelated bases supply conflicting config values.

    For each config key not set on ``model_class`` itself, this checks
    whether two classes in the MRO that are *not* part of one
    inheritance chain (neither is a subclass of the other) provide
    different values. Ordinary single-chain overrides — a subclass
    overriding its parent — are never flagged.

    Args:
        model_class: The freshly created model class to validate.

    Raises:
        AmbiguousConfigError: If a genuine multi-base conflict exists.
    """
    own = model_class.__dict__.get(CONFIG_ATTR) or {}
    for key in _CONFIG_KEYS:
        if key in own:
            continue
        providers = [
            klass
            for klass in model_class.__mro__[1:]
            if key in (klass.__dict__.get(CONFIG_ATTR) or {})
        ]
        if not providers[1:]:
            continue
        first = providers[0]
        first_value = first.__dict__[CONFIG_ATTR][key]
        for other in providers[1:]:
            if issubclass(first, other):
                # Normal override along one inheritance chain: the
                # earlier (more derived) class legitimately wins.
                continue
            if first_value != other.__dict__[CONFIG_ATTR][key]:
                raise AmbiguousConfigError(
                    model_name=model_class.__name__,
                    key=key,
                    first=first.__name__,
                    second=other.__name__,
                )
