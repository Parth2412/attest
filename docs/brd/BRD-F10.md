# BRD-F10 — CLI

| Field | Value |
|---|---|
| Document ID | `BRD-F10` |
| Feature | `F-10` |
| Milestone | M1 |
| Package | `attest-cli` |
| Depends on | `F-01`…`F-08` |
| Status | Ready when F-01…F-08 are Done · no open question |

---

## 1. Purpose

The composition root and the entire user-facing surface. Contains orchestration and presentation
only — no business logic. Its contract with CI is the exit code table, which is effectively
frozen from first release.

## 2. Scope trace

`SCOPE-09`.

## 3. Command surface

| Command | Purpose | Exit codes |
|---|---|---|
| `attest init` | Scaffold `.attest/config.yaml`, a starter policy, and a workflow file with the correct identity constraint | 0, 2 |
| `attest collect` | Run collectors, emit an intermediate JSON document | 0, 1, 2 |
| `attest build` | Build a Statement from collected input | 0, 1, 2 |
| `attest sign` | Sign a Statement into a bundle | 0, 1, 2, 6 |
| `attest push` | Store a bundle | 0, 1, 2, 6 |
| `attest verify` | Verify a bundle against an identity constraint | 0, 4, 5 |
| `attest gate` | Verify plus evaluate policy | 0, 3, 4, 5 |
| `attest run` | collect → build → sign → push → verify → gate | 0, 1, 3, 4, 5, 6 |
| `attest inspect` | Human-readable rendering of a bundle | 0, 2, 5 |
| `attest export` | Evidence bundle (F-12) | 0, 2, 5 |
| `attest config show` | Resolved configuration with value provenance | 0, 2 |
| `attest doctor` | Environment diagnostics | 0, 2 |
| `attest version` | Version and build metadata | 0 |

## 4. Requirements

| ID | Requirement |
|---|---|
| `REQ-F10-010` | Exit codes **MUST** match `GLOSS-001 §7` exactly and **MUST NOT** change without a major version bump. |
| `REQ-F10-020` | Every command **MUST** support `--json` producing a stable, documented, schema-versioned machine-readable output on stdout. |
| `REQ-F10-030` | Human-readable output **MUST** go to stderr when `--json` is active, so stdout stays pure JSON. |
| `REQ-F10-040` | The CLI **MUST NOT** contain business logic; command handlers orchestrate and map results to exit codes only. |
| `REQ-F10-050` | Configuration precedence **MUST** follow `ARCH-001 §8`, and `attest config show --resolved` **MUST** report the source of each value. |
| `REQ-F10-060` | Secrets **MUST NOT** be accepted as CLI flags; only environment variables or files. |
| `REQ-F10-070` | Every error **MUST** print its code, a plain-language message, and the remediation hint. |
| `REQ-F10-080` | `attest --help` **MUST** return in under 300 ms; heavy imports **MUST** be deferred into subcommands. |
| `REQ-F10-090` | Colour **MUST** be disabled automatically when not a TTY and when `NO_COLOR` is set. |
| `REQ-F10-100` | `attest verify` **MUST** require an identity constraint from flag or config, and **MUST** exit `2` if none is resolvable. |
| `REQ-F10-110` | `attest run` **MUST** be resumable in the sense that each stage's intermediate output can be produced and consumed independently. |
| `REQ-F10-120` | `attest doctor` **MUST** report: git backend in use, ambient identity availability, CI environment detection, network reachability of signing endpoints, and resolved policy path — without performing a real signature. |
| `REQ-F10-130` | No command **MUST** send telemetry. If telemetry is ever added it **MUST** be opt-in and documented; v1.0 has none. |

## 5. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F10-010` | A snapshot test asserts the full exit-code table; changing a code fails the test. |
| `AC-F10-020` | `--json` output validates against the committed CLI output schema for every command. |
| `AC-F10-030` | With `--json`, stdout parses as JSON with no human text interleaved. |
| `AC-F10-040` | Import analysis shows no domain logic modules defined in `attest-cli`. |
| `AC-F10-050` | A value set in three places resolves per precedence, with the winning source named. |
| `AC-F10-060` | No command defines a flag whose name matches a secret pattern; asserted by a test over the command tree. |
| `AC-F10-070` | Every error path prints code, message, and remediation. |
| `AC-F10-080` | `attest --help` timing test passes under 300 ms. |
| `AC-F10-090` | Piping output produces no ANSI escapes; `NO_COLOR=1` likewise. |
| `AC-F10-100` | `attest verify` with no constraint exits `2` with a message explaining why a constraint is mandatory. |
| `AC-F10-110` | The staged pipeline produces the same final bundle as `attest run`. |
| `AC-F10-120` | `attest doctor` in a clean container reports each item and creates no signature. |
| `AC-F10-130` | A no-egress test confirms no network call outside signing, storage, and forge operations. |

## 6. Out of scope

TUI, interactive prompts in CI, shell completions beyond what the framework provides free.

## 7. Definition of Done

- [ ] All `REQ-F10-*` implemented, all `AC-F10-*` green
- [ ] Every command has a `CliRunner` test for success and each failure path
- [ ] CLI output JSON schema committed and drift-checked
- [ ] `attest init` produces a workflow that runs successfully unmodified on a fresh repository
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
