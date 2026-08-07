# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: MIT

"""Static-typing regression tests.

Modules here assert nothing at runtime — they are checked by
`poe types` (mypy and pyright), which is where their failures
appear. See `docs/contributing/static_typing.md` for the design
decision they pin.
"""
