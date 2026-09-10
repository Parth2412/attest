# attest — Claude Code Rules

| Field | Value |
|---|---|
| Document ID | `CLAUDE.md` |
| Version | `1.0.1` |
| Status | Harness rules — **commentary**, never normative |
| Last updated | 2026-09-11 |

> **Authority.** This file tells a Claude Code session *how to operate* in this repository. It is
> **not** normative for anything the project builds. `AGENTS.md` at the repository root is
> **NORMATIVE for agent behaviour**, and the document authority table in
> `MPD-001 §12` governs everything else. Where this file and a normative document disagree, the
> normative document wins and this file is a defect to be fixed.

---

## 0. Read this before your first tool call

1. `AGENTS.md` (repository root) — the five prohibitions, the library-verification rule, the
   uncertainty vocabulary. Non-negotiable.
2. `GLOSS-001` — the vocabulary. Loose terminology is where drift starts.
3. `SPEC-001` — the format. **The format is the product.**
4. The single `BRD-Fxx` in scope for this session. **Nothing else.**

Reading the whole document set is a mistake, not diligence. `AGENTS.md §5` and `DEV-001 §6.1`
both say so: irrelevant context produces invented connections.

## 1. Hard stops — read `AGENTS.md §3` in full, but these are the ones that get violated

These are restated here because a harness session is exactly where they get broken.

| Never | Why |
|---|---|
| Regenerate a failing test vector's expected value | Destroys the specification. The single most damaging action available in this repo. `AGENTS.md §3.3`, `QA-001 §4` |
| Add any path that lets verification succeed without an identity constraint | The product becomes security theatre. `ADR-004`, `REQ-F08-040` |
| Write a library call from memory | `AGENTS.md §4`. Confirm the installed version, read the installed source, run a throwaway script, *then* implement |
| Edit a normative document without an ADR | `AGENTS.md §3.2`. ADRs are append-only |
| Reopen a closed decision (`ADR-012`–`ADR-017`) | Language, predicate URI, storage, inclusion proof, control mappings, licence are closed |
| Start a feature whose blocking `CH-xx` is open | `CHALLENGE-001 §2`, §12 |
| Use banned language (`GLOSS-001 §2.2`) anywhere | CI job fails the build. Includes commit messages |
| Fix an unrelated bug you noticed | Scope violation. Report it, do not fix it |

When unsure, use the exact vocabulary from `AGENTS.md §8`: `BLOCKED:`, `UNVERIFIED:`,
`ASSUMED:`, `SPEC-GAP:`, `CONFLICT:`. Never resolve a `SPEC-GAP` or `CONFLICT` yourself.

---

## 2. PROJECT_SPECS.md — living documentation

`PROJECT_SPECS.md` at the repository root is the single source of truth for **project state** —
what exists, what runs, what is decided. It is descriptive, never normative.

### When to read it
Before making any change, to understand current state, what is already built, and known issues.

### When to update it
Immediately after any of the following:
- Feature (`F-xx`) started, completed, or descoped
- Challenge (`CH-xx`) closed in `CHALLENGE-001 §12`
- Dependency added, removed, or version-bumped
- Architecture or data-flow change (which also requires an ADR)
- CLI command or exit code added or changed
- Predicate, schema, or test-vector change
- Configuration or environment variable change
- Release or distribution change
- Major bug fix

Update the file **in the same commit as the code change**. Do not batch.

### What to keep accurate (prioritise accuracy over completeness)
- Tech stack versions — cross-check against `uv.lock` and each `packages/*/pyproject.toml`
- Directory structure — reflect reality, not `BOOT-001`'s target tree
- CLI surface — match the implemented commands, not `BRD-F10 §3`'s plan
- Feature status — match `BRD-INDEX §7`
- Challenge status — match `CHALLENGE-001 §12`
- Recent Changes Log — keep the last 10–15 entries

### What NOT to do
- Do not leave outdated sections rather than deleting them
- Do not document planned state as current state — this repo has a whole document set for planned
  state, and confusing the two is how a "no gaps" project acquires gaps
- Do not skip the update because the change "seems small"

### File structure to follow

```markdown
# PROJECT_SPECS.md

## Project Overview
- **Project Name**:
- **Version**:
- **Last Updated**: [timestamp]
- **Primary Purpose**:
- **Target Audience**:

## Current Project Status
- **Development Stage**: [Pre-bootstrap/Alpha/Beta/Production/Maintenance]
- **Build Status**:
- **Test Coverage**:
- **Known Issues**:
- **Next Milestone**:

## Architecture Overview

### Tech Stack
### System Architecture
### Directory Structure

## Core Features & Modules
[Each F-xx: description, package, BRD, status]

## CLI Surface
[Implemented commands, flags, exit codes]

## Wire Formats & Contracts
[Predicate type URI, digest algorithm, schema version, storage layout]

## Data Storage
[There is no database in v1.0 — see TECH-001 §3.1]

## Development Workflow
### Setup Instructions
### Testing Strategy
### Release Process

## Configuration Management

## Performance & Monitoring

## Security Considerations

## Open Challenges
[CH-xx status mirror of CHALLENGE-001 §12]

## Recent Changes Log
[Keep last 10–15 entries]

## Team & Contacts

## Documentation Links
```

---

## 3. Bootstrap — run this on every new machine

```bash
# Toolchain
curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version && just --version && git --version
```

Then check where the project actually is before doing anything:

```bash
# Which challenges are still open? (gates every feature)
grep -A 15 '^## 12. Outcome log' docs/14-OPEN-CHALLENGES-AND-VALIDATION.md

# Has the scaffold been created yet?
test -f pyproject.toml && just check
```

### 3.1 The gate that comes before everything

**Week 0 (`CHALLENGE-001 §13`) runs before the scaffold exists.** Five days, throwaway code only,
none of it committed to this repository:

| Day | Work | Closes |
|---|---|---|
| 1–2 | `CSD-1` spike across five real repos, two machines, two OSes, cross-checked against `git` CLI | `CH-01` |
| 3–4 | Verify the eight library assumptions by executing code — **C is the critical one** | `CH-02` |
| 5 | Three harness hooks; start a week of real use; hand-build the mock evidence bundle; email two auditors | `CH-03`, `CH-04` start |

`CH-01` and `CH-02` **MUST** be recorded closed in `CHALLENGE-001 §12` before `BOOT-001` runs.
`BRD-F01` and `BRD-F02` may not start until then. Do not treat this as optional sequencing
advice — `CSD-1` is a wire format, and a flaw found after publication invalidates every
attestation ever produced.

### 3.2 Verify the completed scaffold

BOOT-001 is complete. Its scaffold contains **zero business logic**; feature work starts with
BRD-F01.

```bash
uv sync --all-packages
uv run pre-commit install
just check && just banned && just trace && just vectors && just adversarial
```

The schema target must still fail cleanly until BRD-F01 implements generation (`ADR-023`).

---

## 4. Agent team

attest is a small, deep project: one specification, seven packages, twelve features, a 90-day
plan. The team is sized to that, not to a company.

| Agent | Role | Owns | Features |
|---|---|---|---|
| **Lambda** | Coordinator & Tech Lead | Build order, ADR intake, milestone gates, traceability matrix | — |
| **Atlas** | Core & Spec Engineer | `attest-core`, `spec/`, schema generation, test vectors | `F-01`, `F-05` |
| **Sage** | Collectors & Storage Engineer | `attest-collect`, `attest-store` | `F-02`, `F-03`, `F-04`, `F-07` |
| **Cipher** | Signing, Verification & Security | `attest-sign`, `SEC-001`; **security reviewer on every PR** | `F-06`, `F-08` |
| **Pixel** | Policy & CLI | `attest-policy`, `attest-cli` | `F-09`, `F-10` |
| **Forge** | DevOps & Packaging | `.github/workflows/`, `action/`, container, PyPI/GHCR release | `F-11` |
| **Quill** | Docs, Spec Publication & Compliance | `docs/`, `CHANGELOG.md`, `PROJECT_SPECS.md`, `attest-export` control mappings | `F-12` |
| **Nexus** | Code Quality Reviewer | Reviews every PR — correctness, tests, determinism | — |
| **Arbiter** | Release Authority | The `just release-gate` gate, version bumps, tags | — |

Ownership is about *who is accountable*, not who is permitted. Any agent may read anything.

Each agent's charter is `agents/<name>/AGENT.md`. Read yours before starting work — it defines
scope, owned packages, non-negotiables, workflow, and collaboration boundaries. The index is
`agents/README.md`.

> **⚠ Twelve other directories under `agents/` are GovernsAI charters copied from an unrelated
> project** — `auditor`, `beacon`, `compass`, `helix`, `ledger`, `mercury`, `nova`, `orion`,
> `scribe`, `talon`, `vanguard`, `vega`. They reference Multica, `precheck`, and `dashboard`, none
> of which exist here. **They are not part of the attest team and must not be read as guidance.**
> They are safe to delete.

If you are not assigned a specific role, default to Lambda's coordination behaviour: read state,
pick the next feature in `BRD-INDEX §2` order whose dependencies and challenges are closed, and
scope the session to exactly one BRD.

---

## 5. Session protocol (NORMATIVE restatement of `AGENTS.md §5`)

1. **Read** `AGENTS.md`, `GLOSS-001`, `SPEC-001`, and the single `BRD-Fxx` in scope.
2. **Check the gates.** Every dependency feature Done in `BRD-INDEX §7`, every blocking `CH-xx`
   closed in `CHALLENGE-001 §12`. If either fails, stop and say so.
3. **Plan.** List every `REQ-Fxx-NNN` you will implement and the file each touches. Wait for
   approval before writing code.
4. **Verify dependencies** per `AGENTS.md §4`. `uv pip show <pkg>`, read the installed source, run
   a throwaway script. Never from memory.
5. **Write tests first**, each carrying its acceptance-criterion marker:
   ```python
   @pytest.mark.ac("AC-F02-010")
   def test_rename_is_delete_plus_add() -> None: ...
   ```
6. **Implement** the minimum that satisfies the requirements. No speculative features.
7. **`just check` after every meaningful change.** Type errors and import-linter violations are
   the early warning system for hallucinated structure.
8. **Self-review** against `AGENTS.md §9`.
9. **Report**: `REQ-` ids done, `REQ-` ids not done, everything `UNVERIFIED`, every `ASSUMED`.

**One BRD per session.** Long sessions drift (`DEV-001 §6.1`).

---

## 6. SDLC — how code flows

```
feat/F-NN-<slug> → PR (--base dev) → Nexus review + Cipher review → Lambda merge → dev
dev → Arbiter release gate → main → tag v<semver>
```

**Rules every agent follows:**

1. All PRs target `dev`. Never open a PR directly to `main`.
2. Branch names carry their feature id: `feat/F-06-sigstore-signing` (`DEV-001 §4`).
3. Commits are Conventional Commits, and the body **MUST** list the `REQ-` ids implemented.
4. Both **Nexus** (quality/correctness) and **Cipher** (security/architecture) approve before
   Lambda merges. Any PR touching `attest-sign/verifier.py`, `spec/testvectors/`, `spec/schemas/`,
   or a normative document needs Cipher explicitly.
5. An agent may not start a new feature until their open PR is merged.
6. At session start, run `gh pr list --author @me` and clear review comments first.
7. Squash merge. `CSD-1` is designed to survive squash-merge (`ADR-002`).

**Every PR description contains:**
- The `REQ-` and `AC-` ids covered
- The Definition-of-Done checklist from the BRD, with real ticks
- Any `UNVERIFIED:` or `ASSUMED:` items from the session

**Dogfooding (NORMATIVE, `TECH-001 §7`).** This repository's own AI-assisted commits carry the
claim trailer from `DEV-001 §4`:

```
X-Attest-Claim: agent=claude-code; model=anthropic/<model>; session=<id>
```

From commit one. It is the best possible proof the tool works, and it is the `CH-03` data source.

**Releases.** Only Arbiter merges `dev → main`, and only when the full release gate in
`QA-001 §12` is green — including "the release itself is attested by attest, and that attestation
verifies publicly". A release that cannot attest itself does not ship.

---

## 7. Local development

There is no server, no database, and no docker-compose stack in v1.0 (`ARCH-001 §10`,
`TECH-001 §3.1`). Everything is a CLI run and a test suite.

### Commands (`BOOT-001 §6`)

| Command | Purpose |
|---|---|
| `just check` | lint + types + imports + test — the local gate before every commit |
| `just fmt` | ruff fix + format |
| `just types` | `mypy` (strict, all packages) |
| `just imports` | import-linter contracts |
| `just test` / `just test-cov` | pytest |
| `just vectors` | normative test-vector conformance |
| `just adversarial` | forgery, tampering, replay suite |
| `just schema` / `just schema-check` | regenerate JSON Schema / fail on drift |
| `just banned` | banned-language check (`GLOSS-001 §2.2`) |
| `just trace` | requirement → acceptance → test traceability |
| `just security` | bandit + pip-audit |
| `just adr "<title>"` | append a new ADR |
| `just release-gate` | the full gate from `QA-001 §12` |

### Environment

| Variable | Purpose |
|---|---|
| `ATTEST_*` | Configuration overrides — precedence in `ARCH-001 §8` |
| `NO_COLOR` | Disables colour (`REQ-F10-090`) |
| `GITHUB_TOKEN` | Forge collector auth (`F-04`). Environment or file only — **never a CLI flag** (`REQ-F10-060`) |

Configuration precedence, highest first: CLI flags → `ATTEST_*` env → `.attest/config.yaml` →
built-in defaults. `attest config show --resolved` prints the winning source for every value.

### Key local rules

- **Sigstore staging only in tests.** Writing test attestations to the production transparency log
  pollutes a public append-only log that cannot be cleaned. `TECH-001 §6`, `QA-001 §10`. A guard
  test fails the suite if a production endpoint is configured in test settings.
- **No test may depend on the wall clock or on network availability** except explicitly-marked
  nightly jobs. Clocks are injected.
- **Git fixtures are built programmatically in `tmp_path`.** No committed binary repositories.
- **`.attest/claims.d/*.json` is gitignored.** Claim sidecars are local and per-developer.
- **Never `print()`.** Structured logger or the CLI output layer (`AGENTS.md §7`).

---

## 8. Task tracking

This project already has normative trackers. **Do not create a parallel task board** — it would
drift from them, and drift is the failure mode this document set exists to prevent.

| What | Where | Who maintains |
|---|---|---|
| Empirical unknowns and their gates | `CHALLENGE-001 §12` outcome log | Lambda |
| Requirement → acceptance → test coverage | `BRD-INDEX §7` traceability matrix | The feature's owner, in the same PR |
| Feature status | `BRD-INDEX §3` + `PROJECT_SPECS.md` | The feature's owner |
| Decisions | `ADR-LOG` (append-only, via `just adr`) | Whoever makes the decision |
| Shipped changes | `CHANGELOG.md` | Every PR (`X-10`) |
| Milestone exit gates | `ROADMAP-001` §2–4 | Lambda, Arbiter |

Rules:

1. Update the `BRD-INDEX §7` row in the **same commit** as the test that fills it.
2. Never mark a feature Done while any `AC-` for it lacks a referencing test — `just trace`
   enforces this, and turning off the check is not a fix.
3. Close a challenge only by recording its outcome in `CHALLENGE-001 §12`, plus an ADR if the
   outcome changed a decision.
4. If you find work that does not trace to a `REQ-` id in a BRD, it is out of scope
   (`MPD-001 §3.2`). Report it; do not build it.

---

## 9. Multica — the board

The board is **routing and state**. It is never a source of truth for requirements — those live in
the document set, and a ticket that disagrees with its BRD is a defect in the ticket
(`MPD-001 §12`).

Self-hosted at `http://localhost:3000` (backend `:8080`), workspace `attest`, issue prefix `ATT`.
Provisioned by `scripts/multica-setup.sh`, which is idempotent — re-run it after editing.

### Topology

| Project | Contents |
|---|---|
| `Week 0 — Validation` | `CH-01`…`CH-04`, `BOOT-001`. **Nothing else may start until `CH-01` and `CH-02` are closed.** |
| `M1 — Signed core` | `F-01`, `F-02`, `F-03`, `F-05`, `F-06`, `F-08`, `F-10`, `CH-08`, spec publication, `v0.1.0`, M1 gate |
| `M2 — Enforcement` | `F-04`, `F-07`, `F-09`, `F-11`, `CH-05`, `CH-09`, M2 gate |
| `M3 — Evidence` | `F-12`, `CH-04` close-out, `CH-06`, `CH-07`, M3 gate |

Multi-session features are parent issues with children (`F-01` → `F-01a`…`F-01e`). Challenges that
gate a specific feature's Definition of Done hang off that feature (`CH-08` under `F-02`, `CH-09`
under `F-11`, `CH-04` close-out under `F-12`).

### Labels carry the traceability spine

`F-01`…`F-12` · `CH-01`…`CH-09` · `W0`/`M1`/`M2`/`M3` · `pkg:attest-core` … · `gate:CH-0N`
(this issue is blocked by that challenge) · `blocks:F-0N` (this challenge blocks that feature) ·
kind: `validation`, `bootstrap`, `gate`, `spec`, `security`, `docs`, `release`.

```bash
multica issue list --limit 500                    # the board
multica issue get ATT-12                          # one ticket
multica issue status ATT-12 in_progress           # move it
multica issue comment add ATT-12 --content "..."  # report BLOCKED:/UNVERIFIED:/SPEC-GAP:
multica issue runs ATT-12                         # execution history
```

### What starts an agent

Assignment alone does **not** enqueue work — all 38 issues sit in `backlog` assigned to their
owners and nothing runs. Moving an issue out of `backlog` is what dispatches it. Keep gated work in
`backlog` until its gate clears; that is the enforcement mechanism, not a convention.

Creating an agent fires one empty-prompt chat probe. Expected, harmless, ignore it.

### Version caveat

The installed CLI is **0.2.32**; the cloned repo's docs describe a newer build. Two differences
found by testing the binary, not by reading:

- `multica issue metadata` does **not** exist in 0.2.32 — labels carry the traceability instead
- `multica issue label add <issue-id> <label-id>` is the attach path; there is no `--label` flag on
  `issue create` or `issue update`

Verify a command against `multica <cmd> --help` before scripting it. Same rule as `AGENTS.md §4`,
applied to the CLI.

---

## 10. Skills

Repository-specific skills live in `skills/`. Generic third-party harness caches are kept outside
the repository so they cannot enter product lint, security, or packaging scope.

| Skill | Source | Use for |
|---|---|---|
| `brd-session` | local | The one-BRD-per-session loop — the default workflow here |
| `verify-library-api` | local | Before any call into `sigstore`, `pygit2`, `rfc8785`, … (`AGENTS.md §4`) |
| `adr-workflow` | local | Recording a decision; the only legal way to change a normative document |

Skills are workflow aids, not authority — no skill overrides `AGENTS.md`.

---

## 11. Validation checklist before closing any task

- [ ] Every `REQ-Fxx-*` in scope implemented, or explicitly reported as not done
- [ ] Every `AC-Fxx-*` has a test carrying `@pytest.mark.ac("AC-Fxx-NNN")`, and it passes
- [ ] `just check` green — ruff, mypy strict, import-linter, pytest
- [ ] `just vectors` green; **no test vector's expected value was changed**
- [ ] `just banned` and `just trace` green
- [ ] Coverage floor met: 95% for `attest-core`, the verifier, and `attest-policy`; 90% elsewhere
- [ ] Cross-cutting obligations `X-01`…`X-10` (`BRD-INDEX §6`) satisfied
- [ ] No verification bypass introduced — no flag, env var, config key, or code path
- [ ] No new dependency without an ADR; no normative document edited without an ADR
- [ ] `BRD-INDEX §7` rows updated
- [ ] `CHANGELOG.md` entry added
- [ ] `PROJECT_SPECS.md` updated if state changed
- [ ] `COMPATIBILITY.md` updated if a version, runtime floor, or wire contract changed
- [ ] Every library call verified against the installed version, or reported `UNVERIFIED`
- [ ] Every assumption reported
