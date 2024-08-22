# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TODO: needs docstring."""

from __future__ import annotations

from tinydantic._document import Document

# These "*Base" models subclass Document but do not set
# Document.database or Document.table_name class variables.
#
# To use these models in fixtures/tests, make sure to subclass them and
# set the database (and optionally table_name) class variables in the
# subclass.
#
# For example:
#
#   def user_class(db):
#       class User(UserBase):
#           database = db         # noqa: ERA001
#           table_name = "users"  # noqa: ERA001
#
#       return User               # noqa: ERA001


class UserBase(Document):
    """TODO: needs docstring."""

    name: str
    age: int | None = None
