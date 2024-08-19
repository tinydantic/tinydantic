# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
# SPDX-FileCopyrightText: Markus Siemens <markus@m-siemens.de>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""TinyDB storage classes."""

from __future__ import annotations

import io
import os
import warnings

from pathlib import Path
from typing import Any

import yaml

from tinydb.storages import Storage, touch


# This YAMLStorage class is adapted from TinyDB's JSONStorage class:
# https://github.com/msiemens/tinydb/blob/master/tinydb/storages.py
class YAMLStorage(Storage):
    """Store the data in a YAML file."""

    def __init__(
        self,
        path: str,
        *,
        create_dirs: bool = False,
        encoding: str | None = None,
        access_mode: str = "r+",
        **kwargs,
    ) -> None:
        """Create a new instance.

        Also creates the storage file, if it doesn't exist and the
        access mode is appropriate for writing.

        Note: Using an access mode other than `r` or `r+` will probably
        lead to data loss or data corruption!

        :param path: Where to store the YAML data.
        :param access_mode: mode in which the file is opened (r, r+)
        :type access_mode: str
        """
        super().__init__()

        self._mode = access_mode
        self.kwargs = kwargs

        if access_mode not in ("r", "rb", "r+", "rb+"):
            warnings.warn(
                "Using an `access_mode` other than 'r', 'rb', 'r+' "
                "or 'rb+' can cause data loss or corruption",
                stacklevel=2,
            )

        # Create the file if it doesn't exist and creating is allowed by
        # the access mode
        if any(
            character in self._mode for character in ("+", "w", "a")
        ):  # any of the writing modes
            touch(path, create_dirs=create_dirs)

        # Open the file for reading/writing
        self._handle = Path(path).open(mode=self._mode, encoding=encoding)  # noqa: SIM115

    def close(self) -> None:
        """Close the file object."""
        self._handle.close()

    def read(self) -> dict[str, dict[str, Any]] | None:
        """Read data from storage.

        :return: A python dict containing the database data from
            storage.
        :rtype: dict[str, dict[str, Any]] | None
        """
        # Get the file size by moving the cursor to the file end and
        # reading its location
        self._handle.seek(0, os.SEEK_END)
        size = self._handle.tell()

        if not size:
            # File is empty, so we return ``None`` so TinyDB can
            # properly initialize the database
            return None

        # Return the cursor to the beginning of the file
        self._handle.seek(0)

        # Load the YAML contents of the file
        return yaml.safe_load(self._handle)

    def write(self, data: dict[str, dict[str, Any]]) -> None:
        """Write data to storage."""
        # Move the cursor to the beginning of the file just in case
        self._handle.seek(0)

        # Serialize the database state using the user-provided arguments
        serialized = yaml.dump(data, **self.kwargs)

        # Write the serialized data to the file
        try:
            self._handle.write(serialized)
        except io.UnsupportedOperation as exc:
            err_msg = (
                f'Cannot write to the database. Access mode is "{self._mode}"'
            )
            raise OSError(err_msg) from exc

        # Ensure the file has been written
        self._handle.flush()
        os.fsync(self._handle.fileno())

        # Remove data that is behind the new cursor in case the file has
        # gotten shorter
        self._handle.truncate()
