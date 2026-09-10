# attest — Agent Team

Nine agents, one specification, seven packages, twelve features.

Each `AGENT.md` defines a role any AI system (Claude Code, Gemini CLI, Codex) can load and operate
as. When assigned work, an agent reads its own file to understand its scope, owned packages,
non-negotiables, workflow, and collaboration boundaries.

**No agent file overrides `AGENTS.md`.** `AGENTS.md` at the repository root is NORMATIVE for agent
behaviour, and the document authority table in `MPD-001 §12` governs everything else. An agent file
that appears to contradict a normative document is a defect in the agent file.

---

## The team

| Agent | Role | Owns | Features |
|---|---|---|---|
| [Lambda](lambda/AGENT.md) | Coordinator & Tech Lead | Build order, gate enforcement, ADR intake, `BRD-INDEX §7`, merge into `dev` | — |
| [Atlas](atlas/AGENT.md) | Core & Specification Engineer | `attest-core`, `spec/schemas`, `spec/testvectors` | `F-01`, `F-05` |
| [Sage](sage/AGENT.md) | Collectors & Storage Engineer | `attest-collect`, `attest-store` | `F-02`, `F-03`, `F-04`, `F-07` |
| [Cipher](cipher/AGENT.md) | Signing, Verification & Security Reviewer | `attest-sign`, `SEC-001`, `SECURITY.md` · **reviews every PR** | `F-06`, `F-08` |
| [Pixel](pixel/AGENT.md) | Policy & CLI Engineer | `attest-policy`, `attest-cli` | `F-09`, `F-10` |
| [Forge](forge/AGENT.md) | DevOps & Packaging Engineer | `.github/workflows`, `action/`, container, release pipeline | `F-11` |
| [Quill](quill/AGENT.md) | Documentation, Spec Publication & Compliance | `docs/`, `README.md`, `CHANGELOG.md`, `attest-export` | `F-12` |
| [Nexus](nexus/AGENT.md) | Code Quality & Correctness Reviewer | **reviews every PR** | — |
| [Arbiter](arbiter/AGENT.md) | Release Authority | `dev → main`, version bumps, tags, `QA-001 §12` gate | — |

Ownership is about accountability, not permission. Any agent may read anything.

---

## Feature → owner map

Build order is normative (`BRD-INDEX §2`). Do not build out of order — later features consume
earlier contracts.

```
M1  F-01 Atlas → F-02 Sage, F-03 Sage → F-05 Atlas → F-06 Cipher → F-08 Cipher → F-10 Pixel
M2  F-04 Sage · F-07 Sage · F-09 Pixel → F-11 Forge
M3  F-12 Quill
```

---

## How to activate an agent

```bash
cat agents/<name>/AGENT.md
```

Then, before any work:

1. `AGENTS.md` — normative agent rules
2. `GLOSS-001` — vocabulary
3. `SPEC-001` — the format (only the sections the BRD cites)
4. The single `BRD-Fxx` in scope

Nothing else. Reading the whole document set is a mistake, not diligence — irrelevant context
produces invented connections (`AGENTS.md §5`, `DEV-001 §6.1`).

State tracking lives in `CHALLENGE-001 §12` (challenge outcomes) and `BRD-INDEX §7` (traceability).
There is no separate task board, deliberately.

---

## The two gates every agent checks first

| Gate | Rule |
|---|---|
| Challenge gate (`CHALLENGE-001 §12`) | `F-01`/`F-02` blocked while `CH-01` or `CH-02` is OPEN · `F-06`/`F-08` blocked while `CH-02` is OPEN · `F-02` DoD needs `CH-08` · `F-11` DoD needs `CH-09` · `F-12` DoD needs `CH-04` |
| Dependency gate (`BRD-INDEX §2`) | Every dependency feature Done in `BRD-INDEX §7` before the dependent starts |

If a gate fails: report `BLOCKED:` and stop. Do not start "the parts that are not blocked".

**Week 0 comes before everything** (`CHALLENGE-001 §13`) — five days of throwaway code, none of it
committed, closing `CH-01` and `CH-02`. `BOOT-001` does not run until both are closed.

---

## SDLC

```
feat/F-NN-<slug> → PR (--base dev) → Nexus + Cipher approve → Lambda merges → dev
dev → Arbiter release gate → main → tag v<semver>
```

- All PRs target `dev`. Never open a PR directly to `main`.
- Branch names carry their feature id: `feat/F-06-sigstore-signing`.
- Conventional Commits; the body **MUST** list the `REQ-` ids implemented.
- **Both** Nexus (quality) and Cipher (security/architecture) approve before Lambda merges.
- An agent may not start a new feature while their PR is open.
- Squash merge — `CSD-1` is designed to survive it (`ADR-002`).
- Only Arbiter merges to `main`, and only on a fully green `QA-001 §12` gate.

Every AI-assisted commit carries the dogfooding trailer (`DEV-001 §4`):

```
X-Attest-Claim: agent=claude-code; model=anthropic/<model>; session=<id>
```
