# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Generate API documentation pages and navigation.

This script is an adaption of the recipe described in
<https://mkdocstrings.github.io/recipes/#automatic-code-reference-pages>
for use with the [mkdocs-awesome-pages-plugin][1].

Unlike the original recipe, this script does not depend on the
[mkdocs-literate-nav][2] and [mkdocs-section-index][3] dependencies.

See <https://github.com/mkdocstrings/mkdocstrings/discussions/686> for
some additional context on the original motivation for this, and
<https://github.com/mkdocstrings/mkdocstrings/discussions/687> where
this script was originally posted.

[1]: https://github.com/lukasgeiter/mkdocs-awesome-pages-plugin
[2]: https://github.com/oprypin/mkdocs-literate-nav
[3]: https://github.com/oprypin/mkdocs-section-index

Warning:
    This script currently only works for packages using the [src
    layout](https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/).
"""

from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files

# --- User Configurable Options ---

# Must match the index file name used by the navigation.indexes feature
# provided by the Material theme.
INDEX_FILE_NAME = "index.md"

# Path where the generated API docs will be located (relative to the
# docs directory).
API_DOC_DIR = "reference/api"

# Must match the file name specified in the awesome-pages "filename"
# config option in mkdocs.yaml (defaults to ".pages").
AWESOME_PAGES_FILE_NAME = ".pages"

# Control the display of the "mod" (module) symbol in the nav.
#
# Note: these options provide additional control over the display of
# the mod symbol beyond the config options built into mkdostrings:
# https://mkdocstrings.github.io/python/usage/configuration/headings/
show_mod_symbol_left_nav = True
show_mod_symbol_footer_nav = True

# Control the display of the full path for the Python module object in
# the nav.
#
# Note: these options provide additional control over the display of
# the module path beyond the config options built into mkdocstrings:
# https://mkdocstrings.github.io/python/usage/configuration/headings/
show_full_path_left_nav = False
show_full_path_footer_nav = True

# Generate a section index page for __init__.py modules
init_as_section_index_page = True

# Skip generating pages for __main__.py modules
skip_main_modules = True

# Skip generating pages for magic modules (e.g. __module__.py)
# Note: this does not include __init__.py or __main__.py (see above)
skip_magic_modules = False

# Skip generating pages for private modules (e.g. _module.py)
skip_private_modules = True

# --- End User Configurable Options ---

mod_symbol = (
    '<code class="doc-symbol doc-symbol-nav doc-symbol-module"></code> '
)

mod_symbol_left_nav = mod_symbol if show_mod_symbol_left_nav else ""
mod_symbol_footer_nav = mod_symbol if show_mod_symbol_footer_nav else ""

root = Path(__file__).parent.parent
src = root / Path("src")
api_doc_path = Path(API_DOC_DIR)


def sort_init_first(path: Path) -> tuple[Path, bool, str]:
    """Custom sort key which places __init__.py files first."""
    # Check if the file name is __init__.py
    is_init = path.name == "__init__.py"
    # Create a tuple with the directory part and whether it's
    # __init__.py
    return (path.parent, not is_init, path.name)


for path in sorted(sorted(src.rglob("*.py")), key=sort_init_first):
    module_path = path.relative_to(src).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = api_doc_path / Path(doc_path)

    module_parts = tuple(module_path.parts)
    module_ident = ".".join(module_parts)
    module_name = module_parts[-1]
    module_ref = module_ident

    if module_name == "__init__":
        package_parts = module_parts[:-1]
        package_ident = ".".join(package_parts)
        package_name = package_parts[-1]
        module_ref = package_ident

        package_path_left_nav = (
            package_ident if show_full_path_left_nav else package_name
        )
        package_path_footer_nav = (
            package_ident if show_full_path_footer_nav else package_name
        )

        package_awesome_pages_file_content = (
            f"title: {mod_symbol_left_nav}{package_path_left_nav}\nnav:\n"
        )

        if init_as_section_index_page:
            full_doc_path = full_doc_path.with_name(INDEX_FILE_NAME)
            package_awesome_pages_file_content += f"  - {mod_symbol_footer_nav}{package_path_footer_nav}: {INDEX_FILE_NAME}\n"  # noqa: E501

        # Generate an awesome-pages file for the package
        with mkdocs_gen_files.open(
            full_doc_path.with_name(AWESOME_PAGES_FILE_NAME),
            "w",
        ) as fd:
            fd.write(package_awesome_pages_file_content)

        if len(package_parts) > 1:
            # If the package is a subpackage, append the package name
            # to the nav in the parent package's awesome-pages file.
            with mkdocs_gen_files.open(
                full_doc_path.parent.with_name(AWESOME_PAGES_FILE_NAME),
                "a",
            ) as fd:
                fd.write(f"  - {package_name}\n")

    if module_name == "__main__" and skip_main_modules:
        # Skip generating pages for __main__.py modules
        continue

    if (
        module_name not in ("__init__", "__main__")
        and module_name.startswith("__")
        and module_name.endswith("__")
        and skip_magic_modules
    ):
        # Skip generating pages for magic modules (e.g. __module__.py)
        continue

    if (
        module_name not in ("__init__", "__main__")
        and not (module_name.startswith("__") and module_name.endswith("__"))
        and module_name.startswith("_")
        and skip_private_modules
    ):
        # Skip generating pages for private modules (e.g. _module.py)
        continue

    if module_name == "__init__" and init_as_section_index_page:
        module_parts = module_parts[:-1]
        module_ident = ".".join(module_parts)
        module_name = module_parts[-1]
    else:
        mod_path_left_nav = (
            module_ident if show_full_path_left_nav else module_name
        )
        mod_path_footer_nav = (
            module_ident if show_full_path_footer_nav else module_name
        )

        # Append the module name to the package's awesome-pages file.
        with mkdocs_gen_files.open(
            full_doc_path.with_name(AWESOME_PAGES_FILE_NAME),
            "a",
        ) as fd:
            fd.write(f"  - {module_name}\n")

        # For more control over module documentation, a separate dir
        # is created for each module with an index and an awesome-pages
        # file, for example:
        #
        # module/
        #   .pages
        #   index.md
        #
        full_doc_path = full_doc_path.with_suffix("") / Path(INDEX_FILE_NAME)
        with mkdocs_gen_files.open(
            full_doc_path.with_name(AWESOME_PAGES_FILE_NAME),
            "w",
        ) as fd:
            # Create the awesome-pages file for the module.
            # fmt: off
            fd.write(
                f"title: {mod_symbol_left_nav}{mod_path_left_nav}\n"
                "nav:\n"
                f"  - {mod_symbol_footer_nav}{mod_path_footer_nav}: {INDEX_FILE_NAME}\n"  # noqa: E501
            )
            # fmt: on

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        # Generate the documentation page for the python module.
        fd.write(f"::: {module_ref}\n")

    # See Note in https://mkdocstrings.github.io/recipes/#generate-pages-on-the-fly
    mkdocs_gen_files.set_edit_path(
        full_doc_path, Path("../") / path.relative_to(root)
    )
