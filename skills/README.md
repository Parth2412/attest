# Skills

Two kinds of skill live in this repository.

| Location | Kind | Registered in |
|---|---|---|
| `skills/` | Project-local — written for attest, encoding this project's normative workflow | `skills-lock.json` as `"sourceType": "local"` |
| `.agents/skills/` | Vendored — copied verbatim from an upstream source at a recorded content hash | `skills-lock.json` with `computedHash` |

`.claude/skills/` contains symlinks into `.agents/skills/` so Claude Code discovers them.
`.agents/skills/` is the real, harness-neutral location; other harnesses read it directly.

## Project-local skills

| Skill | Use when |
|---|---|
| [`brd-session`](brd-session/SKILL.md) | Implementing any feature. The default loop: scope one BRD, check the challenge and dependency gates, plan, verify libraries, tests-first with `AC-` markers, report honestly |
| [`verify-library-api`](verify-library-api/SKILL.md) | Before any call into `sigstore`, `pygit2`, `rfc8785`, `securesystemslib`, `pydantic`, `oras`. Enforces `AGENTS.md §4` |
| [`adr-workflow`](adr-workflow/SKILL.md) | Recording a decision. The only legal way to change a normative document. Also lists the six closed decisions that must not be reopened |

## Vendored skills

| Skill | Source | Licence note |
|---|---|---|
| `brainstorming` | `obra/superpowers` | Design exploration **before** an ADR, never instead of one |
| `find-skills` | `vercel-labs/skills` | Discovering an applicable skill |
| `skill-creator` | `anthropics/skills` | Authoring a new project skill |
| `python-testing-patterns` | `wshobson/agents` | pytest structure, fixtures, parametrisation |
| `python-performance-optimization` | `wshobson/agents` | Only when an `ARCH-001 §11` target is missed. Do not pre-optimise |

Frontend and JavaScript skills are deliberately **not** vendored. attest has no frontend in v1.0
(`OOS-03`, web dashboard deferred to v1.2), and unused skills are context noise.

## Vendoring policy

1. Copy the skill directory verbatim into `.agents/skills/<name>/`. Do not edit vendored content —
   local modifications defeat the hash and hide upstream drift.
2. Add a symlink in `.claude/skills/<name>` → `../../.agents/skills/<name>`.
3. Add an entry to `skills-lock.json` with `source`, `sourceType`, and the recomputed
   `computedHash`.
4. Record the upstream licence. Vendored content keeps its own licence, not this repository's
   Apache-2.0.

## Authority

**No skill overrides `AGENTS.md`.** Skills are reference patterns and workflow aids. `AGENTS.md`
is NORMATIVE for agent behaviour, and the document authority table in `MPD-001 §12` governs
everything else. A skill that appears to contradict a normative document is a defect in the
skill — report it as `CONFLICT:` and do not follow it.
