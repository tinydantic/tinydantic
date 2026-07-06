# Usage

This section is a practical, task-oriented tour of `tinydantic` — from installation to defining models, storing and querying documents, and wiring `tinydantic` into real applications. Every code example on these pages is executed as a doctest in CI, so what you read is exactly what the library does.

- [Introduction](introduction.md) — what `tinydantic` is and how it relates to TinyDB and Pydantic.
- [Installation](installation.md) — installing `tinydantic` from PyPI.
- [Quickstart](quickstart.md) — the shortest path from an empty database to inserting, reading, updating, and deleting a document.
- [CRUD tour](crud.md) — a reference-style walkthrough of every create, read, update, and delete method, including the sharp edges worth knowing about.
- [Queries](queries.md) — building TinyDB queries from model fields: comparisons, logical composition, nested fields, and static type checking with `q()`.
- [Models](models.md) — defining document models and getting the most out of Pydantic.
- [Storage](storage.md) — choosing and configuring TinyDB storage backends.
- [Configuration](configuration.md) — binding models to databases and tables.
- [Testing](testing.md) — patterns for testing code that uses `tinydantic`.
- [FastAPI](fastapi.md) — using `tinydantic` models in a FastAPI application.
