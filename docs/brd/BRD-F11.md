# BRD-F11 — GitHub Action Packaging

| Field | Value |
|---|---|
| Document ID | `BRD-F11` |
| Feature | `F-11` |
| Milestone | M2 |
| Package | `action/` |
| Depends on | `F-06`, `F-07`, `F-09`, `F-10` |
| Status | Ready when F-06, F-07, F-09, F-10 are Done · no open question |

---

## 1. Purpose

Make attest usable in under five minutes by someone who has never written Python. The Action is
the real distribution channel; PyPI is for the minority.

## 2. Scope trace

`SCOPE-10`.

## 3. Action interface

`NORMATIVE EXAMPLE`

```yaml
- uses: acme/attest-action@v1
  with:
    mode: run              # run | verify | gate
    policy: .attest/policy.yaml
    base-ref: ${{ github.event.pull_request.base.sha }}
    head-ref: ${{ github.event.pull_request.head.sha }}
    push-attestation: 'true'
    fail-on-violation: 'true'
```

Outputs: `changeset-digest`, `attestation-ref`, `decision`, `log-index`.

Required permissions, documented prominently:

```yaml
permissions:
  contents: write        # only if push-attestation is true
  id-token: write        # required for keyless signing
  pull-requests: read
  checks: read
```

## 4. Requirements

| ID | Requirement |
|---|---|
| `REQ-F11-010` | The Action **MUST** be container-based using the published image, pinned by digest, not by tag. |
| `REQ-F11-020` | The Action **MUST** fail fast with a clear message naming the missing permission when `id-token: write` is absent. |
| `REQ-F11-030` | The Action **MUST** detect and report a shallow checkout, naming `fetch-depth: 0`. |
| `REQ-F11-040` | The Action **MUST** expose the documented outputs on both success and policy-violation paths. |
| `REQ-F11-050` | The Action **MUST** post a job summary rendering the decision, the authorship mode, and the review record in human-readable form. |
| `REQ-F11-060` | The Action **MUST NOT** require any secret for its core loop; keyless signing uses the workflow identity. |
| `REQ-F11-070` | The Action **MUST** work on `pull_request` and `push` events, and **MUST** document the security implications of `pull_request_target`. |
| `REQ-F11-080` | Versioning **MUST** follow the `v1` moving-major-tag convention plus immutable version tags. |
| `REQ-F11-090` | The Action's own release **MUST** be attested by attest itself (dogfooding). |
| `REQ-F11-100` | Cold start **MUST** be under 15 s p95 on a standard runner. |

## 5. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F11-010` | The action manifest references an image digest, asserted by a lint test. |
| `AC-F11-020` | A workflow missing `id-token: write` fails with a message containing that exact string. |
| `AC-F11-030` | A default-depth checkout produces the `fetch-depth: 0` remediation. |
| `AC-F11-040` | Outputs are populated in a violation run, not only a success run. |
| `AC-F11-050` | The job summary renders on a real run and contains the decision and authorship mode. |
| `AC-F11-060` | An end-to-end workflow with zero repository secrets completes successfully. |
| `AC-F11-070` | Test workflows exist for `pull_request` and `push`; docs cover `pull_request_target` risk. |
| `AC-F11-080` | `v1` resolves to the newest v1.x; immutable tags exist. |
| `AC-F11-090` | The release workflow produces an attestation for the Action release, and it verifies. |
| `AC-F11-100` | Timing measured across 20 runs meets the p95 target. |

## 6. Out of scope

GitLab and Bitbucket templates (v1.1), marketplace listing optimisation, self-hosted runner
specialisation.

## 7. Definition of Done

- [ ] All `REQ-F11-*` implemented, all `AC-F11-*` green
- [ ] A copy-pasteable quickstart workflow in the README works unmodified on a fresh repository
- [ ] Dogfooding release attestation verifies publicly
- [ ] Cross-cutting obligations satisfied
