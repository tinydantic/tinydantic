# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""tinydantic errors."""


class DocumentNotFoundError(Exception):
    """TODO: needs docstring."""

    def __init__(self) -> None:
        """TODO: needs docstring."""
        super().__init__("Document not found")


class DocumentIDRequiredError(ValueError):
    """TODO: needs docstring."""

    def __init__(self) -> None:
        """TODO: needs docstring."""
        super().__init__("Document id is required")
