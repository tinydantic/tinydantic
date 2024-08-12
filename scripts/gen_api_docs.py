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
some additional context on the original motivation for this.

[1]: https://github.com/lukasgeiter/mkdocs-awesome-pages-plugin
[2]: https://github.com/oprypin/mkdocs-literate-nav
[3]: https://github.com/oprypin/mkdocs-section-index
"""

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

# Is the Python project using a src layout?
# https://packaging.python.org/en/latest/discussions/src-layout-vs-flat-layout/
src_layout = True  # default True

# Control the display of the "mod" (module) symbol in the nav.
#
# Note: these options provide additional control over the display of
# the mod symbol beyond the config options built into mkdostrings:
# https://mkdocstrings.github.io/python/usage/configuration/headings/
show_mod_symbol_left_nav = True  # default True
show_mod_symbol_footer_nav = True  # default True

# Control the display of the full path for the Python module object in
# the nav.
#
# Note: these options provide additional control over the display of
# the module path beyond the config options built into mkdocstrings:
# https://mkdocstrings.github.io/python/usage/configuration/headings/
show_mod_full_path_left_nav = False  # default False
show_mod_full_path_footer_nav = True  # default True

# --- End User Configurable Options ---

mod_symbol = (
    '<code class="doc-symbol doc-symbol-nav doc-symbol-module"></code> '
)

mod_symbol_left_nav = mod_symbol if show_mod_symbol_left_nav else ""
mod_symbol_footer_nav = mod_symbol if show_mod_symbol_footer_nav else ""

root = Path(__file__).parent.parent
src = root / Path("src")
api_doc_path = Path(API_DOC_DIR)

for path in sorted(src.rglob("*.py")):
    module_path = path.relative_to(src).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = api_doc_path / Path(doc_path)

    parts = tuple(module_path.parts)
    ident = ".".join(parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name(INDEX_FILE_NAME)
        full_doc_path = full_doc_path.with_name(INDEX_FILE_NAME)
        ident = ".".join(parts)

        mod_path_left_nav = ident if show_mod_full_path_left_nav else parts[-1]
        mod_path_footer_nav = (
            ident if show_mod_full_path_footer_nav else parts[-1]
        )

        # Generate an awesome-pages file for the package and include
        # the index file in the nav.
        with mkdocs_gen_files.open(
            full_doc_path.with_name(AWESOME_PAGES_FILE_NAME),
            "w",
        ) as fd:
            # fmt: off
            fd.write(
                f"title: {mod_symbol_left_nav}{mod_path_left_nav}\n"
                "nav:\n"
                f"  - {mod_symbol_footer_nav}{mod_path_footer_nav}: {INDEX_FILE_NAME}\n"  # noqa: E501
            )
            # fmt: on

        if len(parts) > 1:
            # If the package is a subpackage, append the package name
            # to the nav in the parent package's awesome-pages file.
            with mkdocs_gen_files.open(
                full_doc_path.parent.with_name(AWESOME_PAGES_FILE_NAME),
                "a",
            ) as fd:
                fd.write(f"  - {parts[-1]}\n")
    elif parts[-1] == "__main__":
        # Skip generating docs for __main__.py files.
        continue
    else:
        mod_path_left_nav = ident if show_mod_full_path_left_nav else parts[-1]
        mod_path_footer_nav = (
            ident if show_mod_full_path_footer_nav else parts[-1]
        )

        # Append the module name to the package's awesome-pages file.
        with mkdocs_gen_files.open(
            full_doc_path.with_name(AWESOME_PAGES_FILE_NAME),
            "a",
        ) as fd:
            fd.write(f"  - {parts[-1]}\n")

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
        fd.write(f"::: {ident}")

    # See Note in https://mkdocstrings.github.io/recipes/#generate-pages-on-the-fly
    if src_layout:
        mkdocs_gen_files.set_edit_path(
            full_doc_path, Path("../") / path.relative_to(root)
        )
