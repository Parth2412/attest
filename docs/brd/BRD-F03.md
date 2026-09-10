# BRD-F03 — Authorship Claim Collector

| Field | Value |
|---|---|
| Document ID | `BRD-F03` |
| Feature | `F-03` |
| Milestone | M1 |
| Package | `attest-collect` |
| Depends on | `F-01` |
| Status | Ready when F-01 Done · no open question |

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
class ClaimCollector(Protocol):
    kind: ClaimSourceKind
    def collect(self, ctx: CollectContext) -> list[AuthorshipClaim]: ...

def collect_authorship(
    ctx: CollectContext, collectors: Sequence[ClaimCollector], changed_paths: Sequence[str]
) -> Authorship: ...
```

### 4.1 Sources

| Source | Location | Notes |
|---|---|---|
| Sidecar | `.attest/claims.d/*.json` | Primary; schema in `ARCH-001 §7` |
| Trailer | Commit message trailers in range | `Co-Authored-By:` and `X-Attest-Claim:` |
| Git note | Configured notes ref | Git AI interoperability |
| Manual | `--claim` CLI flag | Explicit human declaration |

### 4.2 Trailer grammar

```
X-Attest-Claim: agent=<name>; agent-version=<v>; model=<provider>/<name>; session=<id>; paths=<a,b>
Co-Authored-By: <Display Name> <email>
```

`Co-Authored-By` is mapped to a claim **only** when the identity matches the configured
known-agent pattern list. A human co-author **MUST NOT** become an AI authorship claim.

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
| `AC-F03-020` | Every produced claim has a non-empty `source.digest` matching the SHA-256 of the file bytes. |
| `AC-F03-030` | The same `claimId` in a sidecar and a trailer yields one claim and a duplicate warning. |
| `AC-F03-040` | A sidecar containing `"prompt": "secret"` yields a claim with no prompt text anywhere in the serialised predicate; the string `secret` is absent from the output. |
| `AC-F03-050` | Claims covering all changed paths yield `ai-authored`; a subset yields `ai-assisted`; none with an `.attest/` marker yields `human-authored`; none without yields `unknown`. |
| `AC-F03-060` | Mode derivation uses decoded raw-byte equality against the F-02 path set, including canonical non-ASCII and invalid-UTF-8 path fixtures and a case where scope paths differ. |
| `AC-F03-070` | A claim scoped to a deleted-from-ChangeSet path is retained with a warning. |
| `AC-F03-080` | `Co-Authored-By: Jane Doe <jane@example.com>` produces no claim; a configured agent identity does. |
| `AC-F03-090` | A `claimedAt` in the future is recorded unchanged and does not alter ordering. |
| `AC-F03-100` | With no claims, `claimsPresent` is `False` and present in the serialised output. |
| `AC-F03-110` | An unreadable notes ref produces a warning; sidecar claims are still collected. |
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
