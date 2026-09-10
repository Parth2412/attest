# BRD-F05 — Attestation Builder

| Field | Value |
|---|---|
| Document ID | `BRD-F05` |
| Feature | `F-05` |
| Milestone | M1 |
| Package | `attest-core` |
| Depends on | `F-01`, `F-02`, `F-03` |
| Status | Ready when F-01, F-02, F-03 are Done · no open question |

---

## 1. Purpose

Assemble collector outputs into a complete, schema-valid in-toto `Statement`. Pure function: no
I/O, fully deterministic, exhaustively testable from fixtures.

## 2. Scope trace

`SCOPE-04`. Implements `SPEC-001 §3`, §6.1, §6.6.

## 3. Dependencies

`F-01` (types), `F-02` (ChangeSet), `F-03` (claims). `F-04` (review) is optional at M1; a
`Review` with `state="unknown"` is supplied when absent.

## 4. Data contract

```python
def build_statement(
    change_set: ChangeSetInfo,
    authorship: Authorship,
    review: Review,
    checks: Sequence[Check],
    collection: Collection,
) -> Statement: ...
```

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F05-010` | `build_statement` **MUST** be pure: same inputs, byte-identical canonical output. |
| `REQ-F05-020` | `subject[0].digest["sha256"]` **MUST** be set from `change_set.digest`; the function **MUST NOT** recompute it. |
| `REQ-F05-030` | The Statement **MUST** be validated against the generated JSON Schema before being returned; failure raises `ERR-BUILD-210`. |
| `REQ-F05-040` | `predicateType` **MUST** be the constant from `attest-core`, never a literal string at the call site. |
| `REQ-F05-050` | `collection.collector.version` **MUST** be the real installed package version, read at runtime. |
| `REQ-F05-060` | `collection.environment.trusted` **MUST** be `True` only for recognised CI environments with a verifiable workload identity; `local` is always `False`. |
| `REQ-F05-070` | `collectedAt` **MUST** be UTC, second precision, and **MUST** be injectable for testing. |
| `REQ-F05-080` | Optional fields with no data **MUST** be omitted from serialisation, never emitted as `null` or empty string. |
| `REQ-F05-090` | The builder **MUST NOT** invent, infer, or default any value not supplied by a collector. Missing data maps to omission or an explicit `unknown`. |
| `REQ-F05-100` | Arrays **MUST** be deterministically ordered: claims by `claimId`, reviewers by `submittedAt` then identity, checks by name. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F05-010` | Building twice from identical inputs yields byte-identical canonical output. |
| `AC-F05-020` | A mutated `change_set.digest` propagates to the subject without recomputation. |
| `AC-F05-030` | An intentionally invalid input combination raises `ERR-BUILD-210` before return. |
| `AC-F05-040` | Grep confirms no hard-coded predicate type string outside the constant definition. |
| `AC-F05-050` | The emitted version matches `importlib.metadata.version`. |
| `AC-F05-060` | A local run yields `trusted: false`. |
| `AC-F05-070` | An injected clock produces the expected timestamp exactly. |
| `AC-F05-080` | Serialised output contains no `null` values and no empty strings. |
| `AC-F05-090` | With review data absent, `review.state` is `unknown`, not `approved` or `none`. |
| `AC-F05-100` | Shuffling input arrays yields identical output. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-BUILD-210` | Assembled Statement fails schema validation | Report as a bug; include the diagnostic dump |
| `ERR-BUILD-211` | Required collector output missing | Ensure the collector ran; check warnings |

## 8. Out of scope

Signing (F-06), storage (F-07), policy (F-09).

## 9. Definition of Done

- [ ] All `REQ-F05-*` implemented, all `AC-F05-*` green
- [ ] Golden-file test: a fixed input set produces a committed golden Statement, byte-compared
- [ ] Coverage ≥ 95% (this is `attest-core`)
- [ ] Cross-cutting obligations satisfied
