# BRD-F03 — Authorship Claim Collector

| Field | Value |
|---|---|
| Document ID | `BRD-F03` |
| Feature | `F-03` |
| Milestone | M1 |
| Package | `attest-collect` |
| Depends on | `F-01` |
| Status | Ready · F-01 Done · governed by ADR-035 |

---

## 1. Purpose

Gather authorship claims from every available source and normalise them into `AuthorshipClaim`
objects, recording for each claim how it was learned. This is the cross-vendor surface: it is what
makes attest work with Claude Code, Cursor, Copilot, Codex, Aider, and tools that do not exist
yet, without any vendor cooperation.

**Reminder of the claim model (`ADR-003`):** claims are self-reported and forgeable. This feature
records them faithfully and records their source. It performs **no** inference and **no**
detection.

## 2. Scope trace

`SCOPE-02`. Implements `SPEC-001 §6.3`, `ARCH-001 §7`.

## 3. Dependencies

`F-01`. Not blocked, but its real-world value depends on `CH-03` (can harnesses reliably emit
claims) — the highest-scored technical risk (`RISK-07`). Run `CH-03` in parallel; its outcome
gates the M2 exit, not this feature's implementation.

## 4. Data contracts

```python
AuthorshipDiagnosticCode = Literal[
    "ERR-COLLECT-111",
    "ERR-COLLECT-112",
    "ERR-COLLECT-113",
    "ERR-COLLECT-114",
    "ERR-COLLECT-116",
    "ERR-COLLECT-117",
    "ERR-COLLECT-118",
    "WARN-COLLECT-003",
    "WARN-COLLECT-004",
]

@dataclass(frozen=True, slots=True)
class KnownAgentPattern:
    pattern: str
    agent: AgentRef

@dataclass(frozen=True, slots=True)
class CollectContext:
    repo_path: Path
    base_commit: str
    head_commit: str
    notes_ref: str = "refs/notes/ai"
    known_agent_patterns: tuple[KnownAgentPattern, ...] = ()

@dataclass(frozen=True, slots=True)
class AuthorshipWarning:
    code: AuthorshipDiagnosticCode
    message: str
    remediation: str
    reference: str

@dataclass(frozen=True, slots=True)
class ClaimCollectorResult:
    claims: tuple[AuthorshipClaim, ...]
    warnings: tuple[AuthorshipWarning, ...]

class ClaimCollector(Protocol):
    kind: ClaimSourceKind
    def collect(self, ctx: CollectContext) -> ClaimCollectorResult: ...

@dataclass(frozen=True, slots=True)
class AuthorshipCollection:
    authorship: Authorship
    warnings: tuple[AuthorshipWarning, ...]

def collect_authorship(
    ctx: CollectContext, collectors: Sequence[ClaimCollector], changed_paths: Sequence[str]
) -> AuthorshipCollection: ...
```

`CollectContext.base_commit` and `head_commit` are already-resolved full lowercase commit OIDs.
Before any optional collector runs, the public operation **MUST** prove that `repo_path` is a Git
repository and both commits are readable. That boundary uses existing `ERR-COLLECT-102`,
`ERR-COLLECT-103`, and `ERR-COLLECT-106` classifications and is fatal. Collector results and
their nested values are immutable.

The supplied collector sequence defines duplicate precedence. The standard sequence is sidecar,
trailer, Git note, then manual. Each built-in collector processes inputs deterministically:
sidecars by ASCII filename, commits by full OID ascending, note session keys ascending, and manual
values in CLI occurrence order. The first claim for a duplicate `claimId` is retained. Final
claims are sorted by `claimId`; final warnings are sorted by `(code, reference)`.

### 4.1 Sources

| Source | Location | Notes |
|---|---|---|
| Sidecar | `.attest/claims.d/*.json` | Primary; schema in `ARCH-001 §7` |
| Trailer | Commit message trailers in range | `Co-Authored-By:` and `X-Attest-Claim:` |
| Git note | Configured `refs/notes/*` ref; default `refs/notes/ai` | Git AI `authorship/3.0.0` interoperability |
| Manual | Repeated `--claim` CLI flag | Explicit human declaration; same payload grammar as `X-Attest-Claim` |

### 4.2 Trailer grammar

```
X-Attest-Claim: agent=<name>; claim-id=<ULID-or-UUIDv7>; agent-version=<v>; model=<provider>/<name>; session=<id>; prompt-digest=<sha256>; paths=<a,b>; claimed-at=<RFC3339>
Co-Authored-By: <Display Name> <email>
```

The `X-Attest-Claim` payload and the value of each manual `--claim` are closed,
semicolon-delimited key/value grammars. Key order is irrelevant. ASCII whitespace may surround a
semicolon; it is not part of a value. The following keys are the complete vocabulary:

| Key | Required | Mapping |
|---|---|---|
| `agent` | yes | `agent.name` |
| `claim-id` | no | `claimId`; generate a UUIDv7 when absent |
| `agent-version` | no | `agent.version` |
| `model` | no | exactly one non-edge `/`, mapped to `model.provider/name` |
| `session` | no | `sessionId` |
| `prompt-digest` | no | `promptDigest`; exactly 64 lowercase hex |
| `paths` | no | non-empty comma-separated canonical Git paths |
| `claimed-at` | no | `claimedAt`; RFC 3339 timestamp |

Keys are case-sensitive. Duplicate or unknown keys, duplicate delimiters, missing `=`, empty
values, an invalid optional value, or non-canonical paths make that one trailer or manual input
malformed. There is no quoting or escaping layer; delimiter bytes inside a canonical path are
percent encoded by `SPEC-001 §4.1`. A generated UUIDv7 is source identity only and **MUST NOT**
populate `claimedAt` or affect a trust decision.

Commit trailer collection examines every commit reachable from `head_commit` but not
`base_commit`, then processes the full OIDs ascending. `source.digest` is over the exact raw commit
message bytes after the commit object's header/message separator. It is not over output
normalised by a trailer parser.

`Co-Authored-By` is mapped to a claim **only** when its complete value matches a configured
`KnownAgentPattern.pattern`. Matching uses case-sensitive whole-string shell-glob semantics.
Patterns are evaluated in configuration order; the first match supplies the complete configured
`AgentRef`. Unmatched entries are ignored silently. A human co-author **MUST NOT** become an AI
authorship claim by inference.

### 4.3 Git AI `authorship/3.0.0` profile

The Git-note collector supports exactly the upstream `authorship/3.0.0` structure at a configured
well-formed `refs/notes/*` ref. It visits the same sorted `base..head` commit set as trailer
collection. A missing optional ref means no Git-note claims and emits no warning. An unreadable
ref, unsupported schema version, or malformed note emits `ERR-COLLECT-116` as a warning and does
not abort another note or collector.

The collector validates the attestation section, divider, and complete metadata object. It emits
one claim for each AI session or legacy prompt key actually referenced by an attestation entry;
known-human `h_` keys are ignored. Multiple trace keys belonging to one `s_` session are combined,
and its unique referenced paths become one scope sorted by decoded raw path bytes.

| Git AI field | Authorship Claim mapping |
|---|---|
| `agent_id.tool` | `agent.name`, verbatim |
| `agent_id.id` | `sessionId`, verbatim |
| `agent_id.model` | `model` only when the value explicitly has a valid `provider/name` pair; otherwise omitted |
| Referenced file paths | UTF-8 bytes encoded canonically into `scope.paths` |
| Raw note blob | SHA-256 in `source.digest` |

Path parsing matches the validated upstream parser: when a file-path line starts and ends with
`"`, only those outer quotes are removed; no unescaping is performed. A note requiring any other
interpretation is malformed rather than guessed. Session and prompt records not referenced by an
attestation entry do not assert contribution and produce no claim.

The supported profile was validated against
[`git-ai` commit `0670e7ef`](https://github.com/git-ai-project/git-ai/tree/0670e7ef27590af0e8ff5409267f3f4b09b8fcb4)
on 2026-09-12. A different schema version requires an ADR.

### 4.4 Source identity and digest boundaries

| Kind | `source.reference` | Bytes covered by `source.digest` |
|---|---|---|
| `sidecar` | `.attest/claims.d/<claimId>.json` | Exact file bytes |
| `trailer` | `commit:<oid>:<token>:<one-based occurrence>` | Exact raw commit-message bytes |
| `git-note` | `<notes-ref>:<commit-oid>:<session-or-prompt-key>` | Exact raw note-blob bytes |
| `manual` | `cli:--claim:<one-based occurrence>` | Exact UTF-8 flag-value bytes |

For trailer references, `<token>` is the canonical lowercase `x-attest-claim` or
`co-authored-by`. Trailer-token matching is ASCII case-insensitive, while payload keys remain
case-sensitive. Occurrences are counted independently for each token in raw commit-message order.
The sidecar filename and reference use the supplied `claimId`. Trailer, Git-note, and manual
inputs use a supplied `claim-id` when available and otherwise receive a newly generated UUIDv7.
No collector hashes parsed, normalised, or re-serialised input as a substitute for the raw source
bytes.

### 4.5 Mode edge cases

Coverage is evaluated independently per eligible claim, never by unioning scopes from multiple
claims. Scope absence covers the entire ChangeSet only when at least one changed path exists.
For a non-empty ChangeSet, a scope containing all changed paths is full coverage even if it also
contains outside paths; a non-empty proper intersection is partial coverage. Outside paths remain
on the claim and emit `WARN-COLLECT-004`.

Claims from `manual` are retained and set `claimsPresent=True` but are not eligible for the
`ai-authored` or `ai-assisted` rows in `SPEC-001 §6.3`. Claims with no eligible non-empty
intersection, and every claim-bearing empty ChangeSet, produce `mode=unknown`. The `.attest/`
marker is an existing directory at the repository root and is consulted only when no claims are
present.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F03-010` | Each sidecar file **MUST** be validated against the claim schema; an invalid file **MUST** produce `ERR-COLLECT-111` and **MUST NOT** abort collection of other files. |
| `REQ-F03-020` | Every claim **MUST** carry `source.kind`, `source.reference`, and `source.digest` (SHA-256 of the raw source bytes). |
| `REQ-F03-030` | `claimId` **MUST** be unique within an attestation; duplicates across sources **MUST** be de-duplicated by `claimId`, retaining the first and warning. |
| `REQ-F03-040` | Raw prompt text **MUST NOT** be read into the predicate. Only `promptDigest` is carried. If a sidecar contains a `prompt` field, it **MUST** be ignored and a warning emitted. |
| `REQ-F03-050` | `Authorship.mode` **MUST** be derived exactly per the table in `SPEC-001 §6.3`. No other heuristic is permitted. |
| `REQ-F03-060` | Mode derivation **MUST** validate both claim-scope and `F-02` paths as canonical `SPEC-001 §4.1` representations and compare their decoded raw bytes. |
| `REQ-F03-070` | A claim whose `scope.paths` reference paths absent from the ChangeSet **MUST** be retained and flagged with a warning, not dropped. |
| `REQ-F03-080` | `Co-Authored-By` **MUST** map to a claim only when the identity matches a configured agent pattern; unmatched entries are ignored silently. |
| `REQ-F03-090` | `claimedAt` **MUST** be recorded as supplied and **MUST NOT** be used for any ordering or trust decision. |
| `REQ-F03-100` | The absence of claims **MUST** be recorded affirmatively via `claimsPresent=False`, never inferred from an empty array by consumers. |
| `REQ-F03-110` | Collector failure **MUST** degrade gracefully: record a warning, continue with other collectors. Only a total inability to read the repository is fatal. |
| `REQ-F03-120` | Unknown `agent.name` values **MUST** be accepted and recorded verbatim; the registry in `SPEC-001 §13` is informative only. |
| `REQ-F03-130` | Sidecar files **MUST NOT** be deleted, moved, or rewritten by attest. Collection is read-only. |
| `REQ-F03-140` | Claim ordering in the predicate **MUST** be deterministic: sorted by `claimId` ascending. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F03-010` | One malformed and two valid sidecar files yield two claims plus `ERR-COLLECT-111` reported as a warning. |
| `AC-F03-020` | Sidecar, trailer, Git-note, and manual claims have the exact references in §4.4 and digests matching their defined raw source bytes. |
| `AC-F03-030` | The same `claimId` in a sidecar and a trailer yields one claim and a duplicate warning. |
| `AC-F03-040` | A sidecar containing `"prompt": "secret"` yields `WARN-COLLECT-003`; no prompt text reaches the serialised predicate and the string `secret` is absent from the output. |
| `AC-F03-050` | Full and partial eligible coverage produce `ai-authored` and `ai-assisted`; no claims with/without the marker produce `human-authored`/`unknown`; manual-only and claim-bearing empty ChangeSets produce `unknown`. |
| `AC-F03-060` | Mode derivation uses decoded raw-byte equality against canonical F-02 paths, covers non-ASCII and invalid-UTF-8 fixtures, and rejects a non-canonical public changed path with `ERR-COLLECT-115`. |
| `AC-F03-070` | A claim scoped outside the ChangeSet is retained with `WARN-COLLECT-004`. |
| `AC-F03-080` | `Co-Authored-By: Jane Doe <jane@example.com>` produces no claim; a case-sensitive whole-string glob match produces the configured agent and first configured match wins. |
| `AC-F03-090` | A `claimedAt` in the future is recorded unchanged and does not alter ordering. |
| `AC-F03-100` | With no claims, `claimsPresent` is `False` and present in the serialised output. |
| `AC-F03-110` | An unreadable notes ref produces `ERR-COLLECT-116` as a warning and preserves sidecar claims; total repository unreadability remains fatal. |
| `AC-F03-120` | `agent.name = "some-future-tool"` is accepted and preserved. |
| `AC-F03-130` | After a run, `.attest/claims.d/` is byte-identical to before. |
| `AC-F03-140` | Shuffling file read order produces an identical claim array. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-COLLECT-111` | Malformed sidecar claim file | Validate against the claim schema |
| `ERR-COLLECT-112` | Unreadable claims directory | Check permissions |
| `ERR-COLLECT-113` | Malformed trailer | Correct the trailer grammar |
| `ERR-COLLECT-114` | Duplicate `claimId` | Ensure emitters generate unique IDs |
| `ERR-COLLECT-115` | A public changed path is not canonical | Supply the canonical percent-encoded Git path |
| `ERR-COLLECT-116` | Git note is unreadable, unsupported, or malformed | Fetch and validate the configured Git AI notes ref |
| `ERR-COLLECT-117` | Malformed manual claim | Correct the `--claim` value grammar |
| `ERR-COLLECT-118` | A claim collector failed unexpectedly | Check the named collector and retry |

`ERR-COLLECT-111`, `112`, `113`, `114`, `116`, `117`, and `118` are carried by
`AuthorshipWarning` and are non-fatal at the F-03 boundary. `ERR-COLLECT-115` is fatal. Existing
`ERR-COLLECT-102`, `103`, and `106` remain fatal when repository or commit validation fails.

### 7.1 Warning codes

| Code | Condition | Remediation |
|---|---|---|
| `WARN-COLLECT-003` | A raw `prompt` sidecar property was omitted | Supply only `promptDigest` when prompt correlation is required |
| `WARN-COLLECT-004` | A claim scope contains paths outside the ChangeSet | Confirm the claim scope and collected base/head commits |

## 8. Out of scope

- Verifying that claims are true (`ADR-003` — permanently out of scope)
- Writing claim files (harness hooks do that; shipped as examples, not as product code in v1.0)
- Statistical detection (`OOS-05`)

## 9. Definition of Done

- [ ] All `REQ-F03-*` implemented, all `AC-F03-*` green
- [ ] A negative test asserts no prompt text can reach the predicate under any input
- [ ] Example harness hook scripts provided under `examples/hooks/` for at least two harnesses
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
