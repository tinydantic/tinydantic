# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

from importlib.metadata import version

from packaging.version import parse

from tinydantic import __version__


class TestVersion:
    def test_version_is_a_string(self):
        assert isinstance(__version__, str)

    def test_version_matches_metadata_version(self):
        assert __version__ == version("tinydantic")

    def test_version_is_valid(self):
        parse(__version__)
