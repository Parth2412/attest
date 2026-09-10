# attest — Gemini CLI Rules

| Field | Value |
|---|---|
| Document ID | `GEMINI.md` |
| Version | `1.0.0` |
| Status | Harness pointer — **commentary**, never normative |
| Last updated | 2026-08-01 |

This repository keeps **one** copy of each rule set, because duplicated rules drift and drift is
the exact failure mode this project's document set exists to prevent (`MPD-001 §12`).

Read, in this order:

1. **`AGENTS.md`** (repository root) — **NORMATIVE for agent behaviour.** The five prohibitions,
   the library-verification rule, the uncertainty vocabulary. Applies to every harness, including
   this one, without modification.
2. **`CLAUDE.md`** — the harness operating rules: session protocol, gates, SDLC, commands, task
   tracking, validation checklist. Every rule in it applies to Gemini CLI sessions verbatim. Where
   it names a Claude-specific path (`.claude/skills/`), the equivalent here is
   `.agents/skills/`, which is harness-neutral and is the real location.
3. **`PROJECT_SPECS.md`** — current project state before you change anything.
4. **`COMPATIBILITY.md`** — component versions, runtime floors, and wire-format contracts.

Do not maintain a separate Gemini rule set. If a rule genuinely needs to differ by harness, add it
to `CLAUDE.md` in a clearly-labelled per-harness table rather than forking this file.
