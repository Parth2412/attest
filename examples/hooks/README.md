# Experimental claim-emission hooks

These examples write schema `0.1.0` sidecars after supported file-edit tools succeed. They record
only the harness name, session identifier, canonical repository-relative paths, and collection
time. They never read a transcript or copy prompt text.

- Claude Code: copy the contents of `claude-code/settings.example.json` into the repository's
  `.claude/settings.json`. The official `PostToolUse` input supplies the tool-specific
  `file_path` or `notebook_path` value used by `Edit`, `Write`, and `NotebookEdit`.
- Codex: copy `codex/hooks.example.json` to `.codex/hooks.json`. The official hook input exposes
  `apply_patch` content in `tool_input.command`; the example extracts only add, update, delete,
  and move path headers.

Both command hooks are intentionally fail-open so a provenance helper cannot interrupt editing.
They cover only the named tool paths. They do not observe arbitrary shell commands, external
processes, or every possible harness operation. This limitation is tracked by `CH-03`; do not
interpret these examples as closure of that empirical validation gate.

Sources checked on 2026-09-12:

- [Claude Code hooks](https://code.claude.com/docs/en/hooks)
- [Codex hooks](https://learn.chatgpt.com/docs/hooks)
