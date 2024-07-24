# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Version tests."""

from importlib import metadata

from packaging.version import parse

from tinydantic import __version__


class TestPackageVersion:
    """Package version tests."""

    def test_version_is_a_string(self):
        """Package version is a string."""
        assert isinstance(__version__, str)

    def test_version_matches_metadata_version(self):
        """Package version matches installed metadata."""
        assert __version__ == metadata.version("tinydantic")

    def test_version_is_valid(self):
        """Package version is compliant with PyPA Version specifiers.

        See https://packaging.python.org/en/latest/specifications/version-specifiers/#version-specifiers
        """
        parse(__version__)
