# PROJECT_SPECS.md — attest

## Project Overview

- **Project Name**: attest
- **Version**: 0.0.0 workspace; seven packages at 0.1.0. F-01 through F-09 are complete; F-10
  through F-12 are not implemented.
- **Last Updated**: 2026-09-15
- **Primary Purpose**: An open-source, CI-native tool that produces cryptographically signed,
  tamper-evident provenance attestations for code changes, and verifies them as a merge gate. For
  each merged change it emits an in-toto Statement, wrapped in a DSSE envelope, signed keylessly
  via Sigstore, recorded in a transparency log, binding: ChangeSet digest ↔ authorship claims ↔
  review record ↔ signing identity.
- **Target Audience**: Platform/DevSecOps engineers who own CI (primary user), engineering leads
  (influencer), compliance/GRC leads (economic buyer), external auditors (validator).
  See `MPD-001 §4`.

> **What attest is NOT** — binding, and restated here because it constrains every line of code and
> every string in the product (`MPD-001 §2.2`): not an AI-code detector, not a code review tool,
> not a compliance guarantee, not a SLSA replacement, not a prompt archive. attest attests **chain
> of custody**, not forensic truth. It asserts *"at time T, in trusted CI environment E, these
> authorship claims were present, bound to diff digest D alongside review record R, signed by
> identity I"* — never *"an AI wrote line 42."*

---

## Current Project Status

- **Development Stage**: **Pre-alpha implementation.** BOOT-001 and F-01 through F-09 are complete.
  F-10 through F-12 remain Planned in `BRD-INDEX §7.1`.
- **Build Status**: Locked local and GitHub Actions gates are green on Python 3.12 and 3.13 across
  Linux and macOS. Every pull request and `dev`/`main` push must retain this state.
- **Test Coverage**: F-01 enforces the 95% `attest-core` branch-coverage floor. F-02 enforces the
  90% `attest-collect` floor with both Git backends, real-repository fixtures, and normative
  vectors. F-03 retains that floor at 92% with all four claim sources, strict malformed-input
  isolation, and secure filesystem tests. F-05 has 99% `attest-core`; F-06's signing module has
  95% branch coverage. F-08 has 100% verifier branch coverage, 94% across `attest-sign`, 15
  mandatory adversarial tests, and 385 killed verifier mutants. F-04 and F-09 enforce their 90%
  and 95% package gates; F-04's complete GitHub contract is at 92.64%. F-07 has 91.07% branch
  coverage across filesystem, Git CLI, optional pygit2, and OCI Referrers conformance. The full
  local gate passes 842 tests with two intentional environment-dependent skips.
- **Known Issues**:
  - F-10 through F-12 remain unimplemented; their modules and delivery surfaces stay scaffolded.
  - Six empirical challenges remain open. `CH-01` and `CH-02` closed on 2026-09-10; `CH-08`
    closed on 2026-09-11 with a supported-Git monorepo benchmark.
- **Next Milestone**: Implement the accepted F-10 CLI contract. F-11 owns publication/live workflow
  proof; F-12 later exposes `attest export`.

---

## Architecture Overview

### Tech Stack

| Layer | Choice | Status |
|---|---|---|
| Language | Python 3.12+ (target 3.12, test on 3.12 and 3.13) — **final for v1.x**, `ADR-012` | decided |
| Package/project manager | uv, with workspaces | decided |
| Build backend | hatchling, PEP 621, src layout | decided |
| Task runner | just (`Justfile`) | decided |
| Models & schema | Pydantic v2 (generated structural JSON Schema plus runtime semantic validators — `ADR-010`, `ADR-021`) | decided |
| Canonicalisation | `rfc8785` (RFC 8785 JCS) | decided |
| Signing | `sigstore` native DSSE (Fulcio + Rekor); no direct `securesystemslib` handling (`ADR-020`) | decided |
| Git access | Optional `pygit2` primary, Git CLI fallback — both CI-conformant, `ADR-007`, `ADR-034` | decided |
| HTTP | `httpx` | decided |
| CLI | `typer` + `rich` | decided |
| Logging | `structlog` | decided |
| Storage | git refs (`ADR-014`), filesystem, OCI via `oras` | decided |
| Lint/format | ruff | decided |
| Types | `mypy --strict`, no exceptions on `main` | decided |
| Import boundaries | import-linter | decided |
| Tests | pytest, hypothesis, `mutmut` (core + verifier) | decided |
| CI | GitHub Actions | decided |
| Distribution | GHCR container (primary), GitHub Action, PyPI wheel | decided |
| Database | **none in v1.0** — deliberately (`TECH-001 §3.1`) | decided |

The workspace resolves through committed `uv.lock`. The evidence-backed bootstrap versions are
`pygit2==1.20.0`, `rfc8785==0.1.4`, `sigstore==4.5.0`, `pydantic==2.13.5`, and
`jsonschema==4.26.0`; `uv.lock` is the complete source of truth (`BOOT-001 §4.1`).

### System Architecture

- **Pattern**: Pure core, impure edges. Digest, canonicalisation, models, and policy evaluation
  are pure functions; all I/O lives at the edges. Peer adapters are independent,
  `attest-export` is the bounded application layer over store/sign, and `attest-cli` is the
  top-level composition root (`ADR-022`).
- **Key principles** (`ARCH-001 §1`): the specification is the product · verification never trusts
  the producer · fail closed in the gate, fail open in collection · everything signed is
  reproducible · offline verification must be possible · no hidden network calls.
- **Trust model** (`ARCH-001 §6`): repository contents, trailers, sidecar claims, and git notes are
  **untrusted** — recorded faithfully, never used for a security decision. Forge review records are
  **semi-trusted**. The CI workload OIDC identity, the Fulcio certificate, and the Rekor inclusion
  proof are the **only** root of trust.
- **Primary data flow** (`ARCH-001 §4`, `attest run` in CI): environment → git ChangeSet → digest →
  authorship claims → review records → Statement → schema validation → sign (DSSE + Fulcio +
  Rekor) → store → **re-verify own output** → policy → exit code. Step 10, the self-re-verification,
  is normative (`ADR-005`).
- **External dependencies**: Sigstore Fulcio and Rekor (public good instances; staging for all
  tests), GitHub REST/GraphQL, optionally an OCI registry.

### Directory Structure

**Actual, today:**

```
project/
├── .github/workflows/ci.yml
├── .attest/{config.yaml,policy.yaml,claims.d/}
├── .importlinter · .pre-commit-config.yaml · Justfile · pyproject.toml · uv.lock
├── AGENTS.md · CLAUDE.md · GEMINI.md · PROJECT_SPECS.md · COMPATIBILITY.md
├── CHANGELOG.md · CONTRIBUTING.md · SECURITY.md · README.md
├── LICENSE (Apache-2.0) · LICENSE.spec (CC-BY-4.0)
├── docs/                   15 governing documents + 12 BRDs
├── scripts/                four quality/ADR tools + the Multica provisioner
├── spec/                   SPEC-001 mirror; pre-feature schema/vector placeholders
├── examples/{hooks/,workflows/}
├── action/{action.yml,Dockerfile}
├── packages/               seven distributions; F-01–F-09 active, one F-10 prerequisite open, F-10–F-12 scaffolded
├── skills/                 three attest-specific agent skills
└── agents/                 nine attest agent charters
```

---

## Core Features & Modules

Build order is **normative** (`BRD-INDEX §2`). Later features consume earlier contracts; building
out of order means inventing those contracts.

| ID | Feature | Package | Milestone | Depends on | Challenge gate | Owner | Status |
|---|---|---|---|---|---|---|---|
| `F-01` | Core domain model and predicate schema | `attest-core` | M1 | — | `CH-01`, `CH-02` | Atlas | ✓ done |
| `F-02` | Git ChangeSet collector (`CSD-1`) | `attest-collect` | M1 | F-01 | `CH-01`, `CH-08` | Sage | ✓ done |
| `F-03` | Authorship claim collector | `attest-collect` | M1 | F-01 | — | Sage | ✓ done |
| `F-04` | Review record collector (GitHub) | `attest-collect` | M2 | F-01 | — | Sage | ✓ done |
| `F-05` | Attestation builder | `attest-core`, `attest-collect` | M1 | F-01, F-02, F-03 | — | Atlas | ✓ done |
| `F-06` | Sigstore signing | `attest-sign` | M1 | F-01, F-05 | `CH-02` | Cipher | ✓ done |
| `F-07` | Storage and retrieval | `attest-store` | M2 | F-01, F-06 | — | Sage | ✓ done |
| `F-08` | Verification | `attest-sign` | M1 | F-01, F-06 | `CH-02` | Cipher | ◐ inspection prerequisite |
| `F-09` | Policy engine and CI gate | `attest-policy` | M2 | F-01, F-04, F-08 | — | Pixel | ✓ done |
| `F-10` | CLI | `attest-cli` | M2 | F-01…F-09 | — | Pixel | ☐ contract accepted |
| `F-11` | GitHub Action packaging | `action/` | M2 | F-06, F-07, F-09, F-10 | `CH-09` (DoD) | Forge | ☐ not started |
| `F-12` | Evidence export and control mapping | `attest-export` | M3 | F-07, F-08 | `CH-04` (DoD) | Quill | ☐ not started |

### The two irreducible ideas (`MPD-001 §5.2`)

Everything else is plumbing.

1. **A deterministic ChangeSet digest any implementation can reproduce.** `CSD-1` digests git
   *object identities* — never rendered diff text, which varies by algorithm, context width,
   whitespace flags, and renderer. Rename and copy detection are **off**; renames appear as
   delete + add (`ADR-001`).
2. **Identity-bound verification, not merely signature verification.** A valid signature proves
   *someone* signed. Verification **MUST** assert the signing certificate's identity and issuer
   match an expected CI workflow identity. Without this the product is security theatre
   (`ADR-004`, `SEC-001 T-03` — the most important control in the system).

---

## CLI Surface

**Nothing is implemented.** Active F-10 surface accepted by `ADR-045`; exact options, artifacts,
configuration, schemas, and mappings live in `BRD-F10`:

| Command | Purpose | Exit codes |
|---|---|---|
| `attest init` | Scaffold config, starter policy, and secure workflow | 0, 1, 2 |
| `attest collect` | Run collectors, emit a Collection Artifact | 0, 1, 2, 6 |
| `attest build` | Build a Statement from collected input | 0, 1, 2 |
| `attest sign` | Sign a Statement into a bundle | 0, 1, 2, 6 |
| `attest push` | Store a bundle | 0, 1, 2, 6 |
| `attest verify` | Verify a bundle against identity and issuer constraints | 0, 1, 2, 4, 5 |
| `attest gate` | Verify plus evaluate policy | 0, 1, 2, 3, 4, 5 |
| `attest run` | collect → build → sign → push → verify → gate | 0, 1, 2, 3, 4, 5, 6 |
| `attest inspect` | Parse and render with explicit `unverified-identity` status | 0, 1, 2, 5 |
| `attest config show` | Resolved configuration with value provenance | 0, 1, 2 |
| `attest doctor` | Environment diagnostics, performing no signature | 0, 1, 2 |
| `attest version` | Version and build metadata | 0, 1 |

`attest export` is reserved and unregistered until F-12. Verify/gate/run require both identity and
issuer from flag or config and exit `2` if either is unresolved (`REQ-F10-100`); no bypass exists.

---

## Wire Formats & Contracts

Full matrix in `COMPATIBILITY.md §2`. Headlines:

| Contract | Current | Stability |
|---|---|---|
| Predicate type URI | `https://parth2412.github.io/attest/ai-authorship/v0.1` | **v0.x explicitly unstable**; freezes at v1.0 (`ADR-013`) |
| Digest algorithm | `CSD-1` | Any change is a new `CSD-N`; old N verifiable forever |
| Statement type | `https://in-toto.io/Statement/v1` | external |
| DSSE payload type | `application/vnd.in-toto+json` | external |
| Subject | `name = "changeset"`, digest = ChangeSet Digest — **not** the commit SHA (`ADR-002`) | frozen by design |
| Storage | `refs/attestations/<digest>[-<locator>]` (`ADR-014`, `ADR-044`) | git notes are **not** used for storage |
| Exit codes | `GLOSS-001 §7` | frozen from first release |
| JSON Schema | structural schema generated from Pydantic; CI fails on drift (`ADR-010`, `ADR-021`) | never hand-edited; semantic invariants remain runtime checks |

**Conventions** (`GLOSS-001 §8`): timestamps are RFC 3339 UTC with `Z`, second precision, never
naive. Digests are lowercase hex. Git OIDs are full 40-character lowercase hex — abbreviated OIDs
**MUST NOT** appear in any signed field. Canonical JSON is RFC 8785 for anything digested or
signed. JSON on the wire is `camelCase`; Python is `snake_case`; Pydantic aliases bridge them and
the conversion is never hand-written.

---

## Data Storage

**There is no database in v1.0, deliberately** (`TECH-001 §3.1`). Adding one early is precisely how
a decentralised tool accidentally becomes a service. Attestations are stored in a git ref
namespace, on the filesystem, or in an OCI registry (`F-07`).

If and when the hosted evidence store arrives (`OOS-01`, v1.1): SQLAlchemy 2.x + Alembic on
PostgreSQL. Not before, and not "so it's ready".

---

## Development Workflow

### Setup Instructions

The scaffold is installable for development:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone <repo> && cd attest
uv sync --all-packages
uv run pre-commit install
just check
```

### Testing Strategy

Full obligations in `QA-001`. Priorities, in order: correctness of digest and canonicalisation →
strength of verification → determinism → honest degradation → everything else. The failure mode
that matters is not a crash; it is **a silently wrong attestation that verifies today and misleads
at audit time**.

| Layer | Share | Scope |
|---|---|---|
| Unit (pure) | ~55% | `attest-core`, `attest-policy` — no I/O, exhaustive |
| Vector conformance | ~10% | `spec/testvectors/` — the normative definition of correctness |
| Property-based | ~5% | Digest and canonicalisation invariants (hypothesis) |
| Integration | ~20% | Real git repositories in `tmp_path`, recorded HTTP, Sigstore **staging** |
| Adversarial | ~5% | Forgery, tampering, replay (`BRD-F08 §7`) |
| End-to-end | ~5% | Full workflow in CI on a real repository |

Coverage floors: 95% for `attest-core`, the verifier module, and `attest-policy`; 90% elsewhere.
Coverage is a floor, not a goal — 100% with weak assertions is worse than 90% with adversarial
ones.

**A failing test vector means the implementation is wrong until a human says otherwise.**
Regenerating the expected value to make a test pass is forbidden (`QA-001 §4`, `AGENTS.md §3.3`)
and would silently destroy the specification.

### Release Process

Gate defined in `QA-001 §12`; executed by Arbiter. A release does not ship unless every box is
ticked — including **the release itself is attested by attest, and that attestation verifies
publicly** (`TECH-001 §7`, dogfooding is normative), and **attestations from every prior version
still verify**.

---

## Configuration Management

- **Precedence** (`ARCH-001 §8`), highest first: CLI flags → named `ATTEST_*` variables →
  `.attest/config.yaml` → built-ins. Organisation policy is inactive/never fetched in v0.1.
- **Config files**: `.attest/config.yaml`, `.attest/policy.yaml`. Claim sidecars live in
  `.attest/claims.d/*.json` and are gitignored — local and per-developer.
- **Resolved configuration MUST be printable** via `attest config show --resolved`, annotated with
  the source of every value. Configuration debugging in CI is otherwise miserable.
- **Secrets**: never accepted as CLI flags — environment or file only (`REQ-F10-060`,
  `AGENTS.md §7`).
- **Telemetry**: none in v1.0 (`REQ-F10-130`). If ever added it must be opt-in and documented.

---

## Performance & Monitoring

Targets from `ARCH-001 §11`. Performance is not a differentiator here; **predictability is** — a
gate that intermittently times out gets disabled by the first frustrated engineer, and a disabled
gate is worth nothing.

| Operation | Target | Validated by |
|---|---|---|
| `CSD-1` on 1,000 changed files | < 500 ms | `CH-08`, week 2 |
| Full `attest run` in CI | < 15 s p95 | `REQ-F11-100`, `CH-09`, week 8 |
| `attest verify` offline | < 2 s | `F-08` |
| Container cold start | < 3 s | `CH-09` |
| `attest --help` | < 300 ms | `AC-F10-080` — heavy imports deferred into subcommands |

Ongoing product metric: the share of attestations with `mode == "unknown"`. Above 50% after
onboarding triggers kill criterion `K4` — a cryptographically impeccable record of nothing.

---

## Security Considerations

Full model in `SEC-001`. Objectives: an attestation cannot be modified undetected · the signer is
unambiguously identifiable · it cannot be replayed against a different ChangeSet · its absence is
detectable by policy · no secrets, prompts, or source code leak · attest cannot be an execution
vector in a privileged CI job · the system never asserts more than it can support.

| Threat | Control |
|---|---|
| `T-01` forged authorship claim | **Accepted, not mitigated** — inherent to the claim model (`ADR-003`). Stated normatively, surfaced in verification output |
| `T-02` replay against a different ChangeSet | Subject digest binds the attestation to the exact ChangeSet (`ADR-002`) |
| `T-03` valid signature, attacker identity | **Mandatory, unbypassable identity verification** (`ADR-004`). The most important control in the system |
| `T-04` attestation suppression | Gate as a **required** status check; exit code 5. Residual: attest does not control branch protection |
| `T-05` malicious policy as an execution vector | Closed declarative vocabulary, no scripting, safe YAML loader (`ADR-008`) |
| `T-06` prompt/secret leakage | Only `promptDigest` is carried; raw prompt text is **never** stored. The transparency log is public by default |
| `T-07` source-code leakage | Predicate carries paths, digests, counts — never content |
| `T-09` supply-chain compromise of attest | Small audited dependency tree, `pip-audit` + `bandit` in CI, SBOM per release, Action pins the image **by digest** |
| `T-12` test-vector tampering | Vectors are normative; regeneration forbidden; changes need an ADR; `CODEOWNERS`-protected |

**Residual risks** — every one must appear in the README limitations section: unclaimed AI use is
invisible · a gate that is not a required check is decorative · the public transparency log
publishes metadata · a review record proves approval, not comprehension · a compromised CI system
can produce genuine attestations for malicious code.

`SECURITY.md` must specify a contact, a 90-day coordinated disclosure window, and that
**verification-bypass reports are critical severity regardless of exploitation difficulty**.

---

## Open Challenges

Mirror of `CHALLENGE-001 §12`. That file is the source of truth; this table is a convenience copy
and must be updated in the same commit.

| ID | Challenge | Kind | Blocks | Status |
|---|---|---|---|---|
| `CH-01` | Does `CSD-1` survive real repositories? | Technical | F-01, F-02 | **CLOSED 2026-09-10** |
| `CH-02` | Do the pinned libraries do what the BRDs assume? | Technical | F-06, F-08 | **CLOSED 2026-09-10** |
| `CH-03` | Can agent harnesses reliably emit claims? | Product | M2 exit | **OPEN** |
| `CH-04` | Does the evidence shape satisfy a real auditor? | Market | F-12 DoD | **OPEN** |
| `CH-05` | Will teams enable a blocking gate? | Product | M2 exit | **OPEN** |
| `CH-06` | Will anyone pay, and who signs? | Market | M3 exit | **OPEN** |
| `CH-07` | Will anyone else implement the spec? | Strategic | standards thesis | **OPEN** |
| `CH-08` | Does it hold at monorepo scale? | Technical | F-02 DoD | **CLOSED 2026-09-11** |
| `CH-09` | Is container cold start acceptable? | Technical | F-11 DoD | **OPEN** |

`CH-02` assumption **C** was demonstrated by signing as identity X and confirming that
verification constrained to identity Y failed. The comprehensive strict staging and library
boundary run is `34495967107` in `Parth2412/attest-csd-conformance` PR #3.

**All six documentation questions `OQ-01`…`OQ-06` are closed** by `ADR-012`–`ADR-017`. Nothing may
be added to that table without a corresponding ADR.

---

## Recent Changes Log

- **2026-09-15**: Completed `REQ-F08-170` with parse-only Bundle inspection, ordered
  structure/payload/schema/model checks, explicit `unverified-identity` success, and no trusted
  identity or policy-evidence fields.
- **2026-09-15**: Completed `REQ-F04-150` with strict pull-request event parsing, PR-field fencing,
  exact paginated Compare resolution, forge merge-base selection, and fail-closed immutable author
  and committer identity collection.
- **2026-09-15**: Accepted `ADR-045`, freezing the exact F-10 CLI/config/artifact/output/security
  contract, reopening F-04 for exact GitHub ChangeSet context and F-08 for labelled parse-only
  inspection, reserving export for F-12, and assigning live fresh-repository proof to F-11.
- **2026-09-13**: Implemented F-08's six-step independent verifier with mandatory exact issuer and
  bounded workflow identity, explicit offline trust sources, historical real-bundle evidence,
  hardened caller-selected Git recomputation, fail-closed diagnostics, the complete adversarial
  suite, 100% verifier coverage, and a zero-survivor mutation gate. F-08 completed under the
  owner-authorized `ADR-040` solo-maintainer exception; no independent human review is claimed.
- **2026-09-13**: `ADR-039` closed Sigstore 4.5.0's empty-issuer truthiness edge by requiring
  `IdentityConstraint` to reject empty or non-string issuers with `ERR-VERIFY-011` before policy
  construction.
- **2026-09-12**: Completed F-06 with exact Sigstore-native DSSE signing, explicit staging or
  production selection, ambient GitHub Actions OIDC, mandatory inclusion-proof postconditions,
  hard process deadlines, stage-aware retries, and live staging/offline verification. Began F-08
  under `ADR-038`, which makes trust selection, check outcomes, bounded identity patterns, and
  caller-selected repository recomputation explicit before implementation.
- **2026-09-12**: Completed F-05 with a pure deterministic Statement builder, JSON Schema before
  Pydantic semantic validation, total array ordering, committed golden canonical bytes, runtime
  `attest-collect` version metadata, injected UTC clock, and exact GitHub Actions trust signals
  that never retain OIDC request credentials. The 297-test workspace is at 96% coverage;
  `attest-core` is at 99% and the environment module at 100%.
- **2026-09-12**: Completed F-03 with deterministic sidecar, trailer, Git AI
  `authorship/3.0.0`, and manual collectors; exact raw-source digests; graceful degradation;
  secure no-symlink file handling; 91% package branch coverage; and experimental Claude Code and
  Codex hooks. `CH-03` remains open pending the bounded real-world emission experiment.
- **2026-09-11**: Completed F-02 with deterministic pygit2 and Git CLI collectors, stable
  diagnostics, 92% package branch coverage, wheel-level optional-backend validation, and closure
  of the `CH-08` monorepo-scale gate.
- **2026-09-11**: `ADR-028` removed invalid inactive workflow placeholders after GitHub registered
  the comment-only files as failed workflows. F-06 and F-11 now create their paths only when valid.
- **2026-09-11**: `ADR-027` made bootstrap CI deterministic and supply-chain pinned: immutable
  action SHAs, exact uv selection, locked installs, asserted Python 3.12/3.13 selection across
  Linux and macOS, and post-merge runs on `dev` and `main`.
- **2026-09-10**: Completed BOOT-001: seven installable package scaffolds, full document mirrors,
  locked dependencies, executable quality gates, public policy files, and CI workflow. Archived
  unrelated GovernsAI charters and generic agent-skill caches outside the repository. `ADR-026`
  records the executed monorepo tool boundaries.
- **2026-09-10**: `CH-01` and `CH-02` closed with cross-platform CSD and Sigstore staging/library
  conformance. `ADR-018`–`ADR-021` corrected canonical Git paths, commit-independent ChangeSet
  digests, Sigstore-native DSSE/bundle handling, and structural-versus-semantic validation.
- **2026-09-10**: `ADR-022` corrected the evidence-export application layer and dependency
  ownership; `ADR-023` corrected generated-artifact and import-smoke lifecycles; `ADR-024` bounded
  the language allowlist; `ADR-025` made pre-feature gates lifecycle-aware.
- **2026-08-01**: Agent-harness configuration added — `AGENTS.md` (verbatim from
  `project-info/09-AGENTS.md`, normative), `CLAUDE.md`, `GEMINI.md`, `COMPATIBILITY.md`, this file,
  and three project-local skills. Generic skill caches were later archived during bootstrap.
- **2026-08-01**: Multica board provisioned on a self-hosted instance (`localhost:3000`, workspace
  `attest`, prefix `ATT`) via `scripts/multica-setup.sh` — 9 agents, 4 projects (Week 0, M1, M2,
  M3), 38 issues, 53 labels carrying the `F-xx`/`CH-xx`/`pkg:`/`gate:` traceability spine. All
  issues sit in `backlog`; moving one out of `backlog` is what dispatches an agent, so the gate
  ordering is enforced by board state, not by convention.
- **2026-08-01**: Nine attest agent charters written — Lambda, Atlas, Sage, Cipher, Pixel, Forge,
  Quill, Nexus, Arbiter — plus `agents/README.md` as the team index.
- **2026-07-26**: Repository initialised. `README.md` placeholder only.
- **2026-07-25**: Document set baselined at `../project-info/` — `MPD-001`, `GLOSS-001`,
  `SPEC-001`, `ARCH-001`, `TECH-001`, `ADR-LOG` (ADR-001…017), `BRD-INDEX`, `BRD-F01`…`BRD-F12`,
  `QA-001`, `DEV-001`, `AGENTS.md`, `ROADMAP-001`, `RISK-001`, `SEC-001`, `BOOT-001`,
  `CHALLENGE-001`.

---

## Team & Contacts

- **Project Lead / Owner**: Parth (ZettaCore) — owner of `MPD-001`
- **Agent team**: defined in `CLAUDE.md §4` — Lambda (coordination), Atlas (core/spec), Sage
  (collectors/storage), Cipher (sign/verify/security), Pixel (policy/CLI), Forge (DevOps),
  Quill (docs/compliance), Nexus (quality review), Arbiter (release)
- **Code reviewers**: Nexus and Cipher provide internal quality/security review. F-08 completed
  under the owner-authorized `ADR-040` solo-maintainer exception because no separate human
  collaborator was available; no independent human review is claimed.
- **Charters**: `agents/<name>/AGENT.md` for all nine, indexed at `agents/README.md`.

---

## Documentation Links

Paths are relative to the repository root.

| ID | Document | Normative for |
|---|---|---|
| `MPD-001` | `docs/00-MASTER-PROJECT-DOCUMENT.md` | Scope (§3), document authority (§12) |
| `GLOSS-001` | `docs/01-GLOSSARY-AND-CONVENTIONS.md` | Terminology, identifiers, exit codes |
| `SPEC-001` | `docs/02-SPEC-001-AI-AUTHORSHIP-PREDICATE.md` | **The format.** Digests, canonicalisation, verification rules |
| `ARCH-001` | `docs/03-SYSTEM-ARCHITECTURE.md` | Component boundaries, data flow, package rules |
| `TECH-001` | `docs/04-TECH-STACK-PYTHON.md` | Libraries, versions, tooling |
| `ADR-LOG` | `docs/05-ADR-LOG.md` | Recorded decisions |
| `BRD-INDEX` | `docs/06-BRD-INDEX-AND-TRACEABILITY.md` | Build order, traceability, anti-gap checklist |
| `BRD-F01`…`F12` | `docs/brd/BRD-F01.md` … `docs/brd/BRD-F12.md` | Feature behaviour and acceptance criteria |
| `QA-001` | `docs/07-TESTING-AND-QUALITY-STRATEGY.md` | Test obligations, release gates |
| `DEV-001` | `docs/08-REPO-SCAFFOLD-AND-DEV-WORKFLOW.md` | Repository layout, workflow, DoD |
| `AGENTS.md` | `./AGENTS.md` | **Agent behaviour** |
| `ROADMAP-001` | `docs/10-ROADMAP-90-DAY.md` | Week-by-week plan, milestone gates |
| `RISK-001` | `docs/11-RISK-REGISTER-AND-KILL-CRITERIA.md` | Risks, kill criteria |
| `SEC-001` | `docs/12-SECURITY-THREAT-MODEL.md` | Threats and controls |
| `BOOT-001` | `docs/13-BOOTSTRAP-AND-BOILERPLATE.md` | Scaffold, file contents, tooling config |
| `CHALLENGE-001` | `docs/14-OPEN-CHALLENGES-AND-VALIDATION.md` | Validation gates, empirical unknowns |
| `COMPAT-001` | `./COMPATIBILITY.md` | — (descriptive) |
| `CLAUDE.md` | `./CLAUDE.md` | — (harness commentary) |
