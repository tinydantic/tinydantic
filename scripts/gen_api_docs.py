# SPDX-FileCopyrightText: Chris Wilson <christopher.david.wilson@gmail.com>
#
# SPDX-License-Identifier: Apache-2.0 OR MIT

"""Generate API documentation pages and navigation."""

# Adapted from https://mkdocstrings.github.io/recipes/#automatic-code-reference-pages

from pathlib import Path

import mkdocs_gen_files

# Must match the index file name used by the navigation.indexes feature
# provided by the Material theme.
INDEX_FILE_NAME = "index.md"

# Must match the directory specified in the "API Documentation" section
# in the mkdocs.yaml nav.
API_DOC_DIR = "reference/api"

# Must match the file name specified in the mkdocs-literate-nav
# "nav_file" config option in mkdocs.yaml (defaults to "SUMMARY.md").
LITERATE_NAV_FILE_NAME = "SUMMARY.md"

mod_symbol = (
    '<code class="doc-symbol doc-symbol-nav doc-symbol-module"></code>'
)

root = Path(__file__).parent.parent
src = root / Path("src")
api_doc_path = Path(API_DOC_DIR)
api_doc_nav_file = api_doc_path / Path(LITERATE_NAV_FILE_NAME)

nav = mkdocs_gen_files.Nav()

for path in sorted(src.rglob("*.py")):
    module_path = path.relative_to(src).with_suffix("")
    doc_path = path.relative_to(src).with_suffix(".md")
    full_doc_path = api_doc_path / Path(doc_path)

    parts = tuple(module_path.parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = doc_path.with_name(INDEX_FILE_NAME)
        full_doc_path = full_doc_path.with_name(INDEX_FILE_NAME)
    elif parts[-1] == "__main__":
        continue

    nav_parts = [f"{mod_symbol} {part}" for part in parts]
    nav[tuple(nav_parts)] = doc_path.as_posix()

    ident = ".".join(parts)

    with mkdocs_gen_files.open(full_doc_path, "w") as fd:
        # Markdown title needs to be set so the nav names in the footer
        # matches the nav in the sidebars.
        fd.write(f"---\ntitle: {mod_symbol} {parts[-1]}\n---\n\n::: {ident}")

    mkdocs_gen_files.set_edit_path(
        full_doc_path, Path("../") / path.relative_to(root)
    )

with mkdocs_gen_files.open(api_doc_nav_file, "w") as nav_file:
    nav_file.writelines(nav.build_literate_nav())
