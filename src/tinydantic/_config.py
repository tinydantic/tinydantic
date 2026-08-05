# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

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
[AmbiguousConfigError][tinydantic.AmbiguousConfigError]
at class-definition time instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypedDict

from tinydantic._errors import AmbiguousConfigError

if TYPE_CHECKING:
    from tinydb import TinyDB

# Name of the per-class attribute holding explicitly-set config.
CONFIG_ATTR = "__tinydantic_config__"

_CONFIG_KEYS = (
    "database",
    "shadowed_fields",
    "table_name",
    "use_revision",
    "validate_writes",
)


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

    shadowed_fields: tuple[str, ...]
    """Field names allowed to shadow class attributes.

    Fields listed here may share a name with an existing class
    attribute (a tinydantic or pydantic method, or one of your
    own). Everything about them works — storage, instance access,
    ``q("name")`` queries — except the ``Model.field`` query
    sugar, which keeps resolving to the real attribute. Unlisted
    shadowed fields raise
    [ShadowedFieldError][tinydantic.ShadowedFieldError] at class
    definition.
    """

    use_revision: bool
    """Whether this model uses optimistic concurrency (default False).

    When True, the model gains a ``revision_id: UUID | None``
    field, rotated (assigned a fresh ``uuid4``) by every write
    path. ``save()``, ``replace()``, and ``delete()`` compare the
    instance's held token against the stored one first and raise
    [StaleDocumentError][tinydantic.StaleDocumentError] when
    another writer got there in between (pass
    ``ignore_revision=True`` for deliberate last-write-wins);
    ``patch()`` and the table-level write verbs rotate without
    checking. See the Concurrency page for the full protocol.

    Unlike the other config keys, ``use_revision`` cannot be
    late-bound with ``bind()`` — the injected field must exist
    before pydantic builds the class.
    """

    validate_writes: bool
    """Whether write paths re-validate full documents (default True).

    When True (the default), every write refuses to persist a
    document body that would fail validation on its next read:
    whole-model writes validate their serialized payload, and
    ``update()``/``update_multiple()`` validate each matched
    document's merged result before anything is written. Set False
    to skip this re-validation — the escape hatch for
    performance-critical bulk writes, where per-document
    validation cost matters more than the guarantee.
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
        key: The [TinydanticConfig][tinydantic.TinydanticConfig]
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
