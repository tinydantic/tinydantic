# CLAUDE.md

@AGENTS.md

Shared, agent-agnostic project conventions live in `AGENTS.md` (imported above). Only Claude-specific guidance goes here.

- Commits and issues Claude helped write end with an `Assisted-by:` trailer — see "Issues and reviews" in `AGENTS.md` for the format and the `Signed-off-by` prohibition. For Claude the trailer is `Assisted-by: Claude:<model-id>`, with any bracketed context-window suffix dropped (`Claude:claude-opus-5`, not `Claude:claude-opus-5[1m]`). A PR is covered by the trailers on its commits; its body needs none.
- Do not add a `Co-Authored-By:` trailer. `Assisted-by:` replaced it — it states the same thing more precisely and matches the [kernel convention](https://docs.kernel.org/process/coding-assistants.html) the project follows.
