# BRD-F09 — Policy Engine and CI Gate

| Field | Value |
|---|---|
| Document ID | `BRD-F09` |
| Feature | `F-09` |
| Milestone | M2 |
| Package | `attest-policy` |
| Depends on | `F-01`, `F-04`, `F-08` |
| Status | Ready when F-01, F-04, F-08 are Done · no open question |

---

## 1. Purpose

Turn a verified attestation into an allow/deny decision that blocks a merge. Verification proves
the record is genuine; policy decides whether what it records is acceptable. This is the feature
that converts attest from a recorder into a control.

## 2. Scope trace

`SCOPE-08`.

## 3. Dependencies

`F-01`, `F-04`, `F-08`.

## 4. Policy document format

`NORMATIVE EXAMPLE` — this is the shape the implementation must accept.

```yaml
version: 1
policies:
  - id: POL-MAIN-001
    description: Human review required for AI-authored changes on main
    match:
      branches: ["main", "release/*"]
      paths: ["**"]
    require:
      attestation: true
      environment:
        trusted: true
      signer:
        issuer: "https://token.actions.githubusercontent.com"
        identity: "https://github.com/acme/api/.github/workflows/attest.yml@refs/heads/main"
      transparencyLog: true
      review:
        when:
          authorshipMode: ["ai-authored", "ai-assisted"]
        minHumanApprovals: 1
        approverMustNotBeAuthor: true
      authorship:
        claimsRequired: true
    onViolation: block

  - id: POL-DOCS-001
    match:
      branches: ["main"]
      paths: ["docs/**"]
    require:
      attestation: true
    onViolation: warn
```

### 4.0.1 Worked example — differentiated enforcement by path

A frequent first question is "can we exclude generated files?" The answer separates two things
that must never be conflated:

- **The ChangeSet Digest always covers every changed path.** Paths **MUST NOT** be excludable from
  the digest. If they were, an attacker would exclude the malicious file and tamper-evidence
  would collapse. This is not configurable and never will be.
- **Policy scopes enforcement, not coverage.** Different paths may carry different requirements.

```yaml
version: 1
policies:
  # Strictest: contract and infrastructure code
  - id: POL-CRITICAL-001
    match:
      branches: ["main"]
      paths: ["contracts/**", "infra/**", "**/auth/**"]
    require:
      attestation: true
      environment: { trusted: true }
      review:
        minHumanApprovals: 2
        approverMustNotBeAuthor: true
      authorship: { claimsRequired: true }
    onViolation: block

  # Normal: application source
  - id: POL-APP-001
    match:
      branches: ["main"]
      paths: ["src/**", "packages/**"]
    require:
      attestation: true
      environment: { trusted: true }
      review:
        when: { authorshipMode: ["ai-authored", "ai-assisted"] }
        minHumanApprovals: 1
        approverMustNotBeAuthor: true
    onViolation: block

  # Recorded but not enforced: generated and vendored content
  - id: POL-GENERATED-001
    match:
      branches: ["main"]
      paths: ["dist/**", "**/*.lock", "**/*.snap", "**/generated/**"]
    require:
      attestation: true
    onViolation: warn
```

Full coverage in the signed record; differentiated enforcement in policy. Implementations **MUST
NOT** add any mechanism to exclude paths from the digest, and any such request is answered by
pointing at this section.

### 4.1 Closed vocabulary

Per `ADR-008` the vocabulary is fixed. v1.0 predicates:

| Key | Type |
|---|---|
| `require.attestation` | boolean |
| `require.environment.trusted` | boolean |
| `require.signer.issuer` | exact string |
| `require.signer.identity` | anchored pattern |
| `require.transparencyLog` | boolean |
| `require.review.minHumanApprovals` | integer |
| `require.review.approverMustNotBeAuthor` | boolean |
| `require.review.when.authorshipMode` | list of modes |
| `require.authorship.claimsRequired` | boolean |
| `require.checks.mustPass` | list of check names |
| `onViolation` | `block` \| `warn` |

No expressions, no scripting, no arbitrary field access.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F09-010` | Policy evaluation **MUST** be a pure function of `(Predicate, VerificationResult, Policy)`. No I/O. |
| `REQ-F09-020` | Policies **MUST** be validated against a schema at load; unknown keys **MUST** be rejected with `ERR-POLICY-601`, never ignored. |
| `REQ-F09-030` | A missing attestation where `require.attestation` is true **MUST** yield exit code `5`, not `3`, so "absent" is distinguishable from "denied". |
| `REQ-F09-040` | A verification failure **MUST** yield exit code `4`, evaluated before any policy predicate. |
| `REQ-F09-050` | When multiple policies match, **all** **MUST** be evaluated; the decision is the most severe outcome. |
| `REQ-F09-060` | The `Decision` **MUST** enumerate every evaluated policy, every predicate, and the specific reason for each violation. |
| `REQ-F09-070` | `onViolation: warn` **MUST** exit `0` while reporting the violation. |
| `REQ-F09-080` | Branch and path matching **MUST** use documented glob semantics, specified and tested, not left to library defaults. |
| `REQ-F09-090` | Policy files **MUST NOT** be executable and **MUST NOT** be able to trigger any code execution, network call, or filesystem access. |
| `REQ-F09-100` | The policy in effect **MUST** be identified in output by file path and content digest, so a reviewer can confirm which policy ran. |
| `REQ-F09-110` | `approverMustNotBeAuthor` **MUST** use immutable reviewer IDs, never logins. |
| `REQ-F09-120` | An empty or absent policy file **MUST** default to reporting only, never to blocking, and **MUST** say so explicitly. |
| `REQ-F09-130` | Policy schema `version` **MUST** be honoured; unknown versions raise `ERR-POLICY-602`. |
| `REQ-F09-140` | The policy engine **MUST NOT** expose any mechanism to exclude paths from the ChangeSet Digest. Path matching affects enforcement only. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F09-010` | Evaluation with identical inputs is deterministic; no I/O occurs, asserted by a no-syscall test harness. |
| `AC-F09-020` | A policy with a misspelled key raises `ERR-POLICY-601` naming the key. |
| `AC-F09-030` | Missing attestation yields exit `5`. |
| `AC-F09-040` | A tampered bundle yields exit `4` regardless of policy content. |
| `AC-F09-050` | Two matching policies, one `warn` one `block`, yield `block`. |
| `AC-F09-060` | Decision output names every evaluated policy ID and every failed predicate. |
| `AC-F09-070` | A `warn` violation exits `0` with the violation printed. |
| `AC-F09-080` | Glob cases (`release/*` vs `release/**`, `docs/**`) match per a documented table. |
| `AC-F09-090` | A policy file containing YAML tags or anchors intended to trigger construction is rejected safely; loading uses a safe loader. |
| `AC-F09-100` | Output contains the policy path and its SHA-256. |
| `AC-F09-110` | A renamed approver login does not defeat `approverMustNotBeAuthor`. |
| `AC-F09-120` | No policy file yields exit `0` plus an explicit "reporting only" notice. |
| `AC-F09-130` | `version: 99` raises `ERR-POLICY-602`. |
| `AC-F09-140` | No policy key can alter the digest; a test asserts the digest is identical under every policy in the example set. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-POLICY-601` | Unknown or malformed policy key | Check the vocabulary table in `BRD-F09 §4.1` |
| `ERR-POLICY-602` | Unsupported policy version | Upgrade attest or lower the version |
| `ERR-POLICY-603` | Policy file unreadable | Check path and permissions |
| `ERR-POLICY-610` | Policy violation (informational code accompanying exit 3) | Address the named violation |

## 8. Out of scope

Organisation-wide policy distribution (v1.1). Automatic remediation. Scripting (`ADR-008`).

## 9. Definition of Done

- [ ] All `REQ-F09-*` implemented, all `AC-F09-*` green
- [ ] Decision-table test covering every predicate × every outcome
- [ ] A real repository demonstrates a blocked merge via required status check
- [ ] Safe-YAML-loading test included
- [ ] Coverage ≥ 95% (pure package)
- [ ] Cross-cutting obligations satisfied
