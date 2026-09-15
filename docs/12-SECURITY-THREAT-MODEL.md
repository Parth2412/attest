# attest — Security Threat Model

| Field | Value |
|---|---|
| Document ID | `SEC-001` |
| Version | `1.3.0` |
| Status | **NORMATIVE** for threats and controls |
| Last updated | 2026-09-15 |

---

## 1. Scope of the model

attest is a security tool, so its own threat model is part of its credibility. This document
covers threats to the **integrity and meaning of attestations**, and threats introduced by
running attest in a CI job that holds signing permissions.

Out of model: the security of Sigstore infrastructure itself, the forge's own security, and
general repository security.

---

## 2. Security objectives

| # | Objective |
|---|---|
| O1 | An attestation cannot be modified after signing without detection |
| O2 | The signer of an attestation is unambiguously identifiable |
| O3 | An attestation cannot be replayed against a different set of changes |
| O4 | Absence or suppression of an attestation is detectable by policy |
| O5 | attest never leaks secrets, prompts, or source code |
| O6 | attest cannot be used as an execution vector in a privileged CI job |
| O7 | The system never asserts more than it can support |

---

## 3. Assets

| Asset | Why it matters |
|---|---|
| Signing identity (CI workload OIDC token) | Compromise permits forging attestations |
| Attestation bundles | The evidence itself |
| Test vectors and specification | The definition of correctness |
| Policy files | Determine what is enforced |
| Release artifacts | Supply-chain target |

---

## 4. Threats and controls

### T-01 — Forged authorship claim
**Actor:** anyone who can write to the repository · **Likelihood:** high · **Impact:** low

Anyone can create `.attest/claims.d/fake.json` claiming any agent authored anything.

**Accepted, not mitigated.** This is inherent to the claim model (`ADR-003`). attest binds
untrusted claims to a trusted identity and an immutable change digest; it never asserts the claims
are true.

**C-01:** `SPEC-001 §1.2` states the limitation normatively; verification output surfaces it; the
README states it prominently. A documented limitation is a design decision.

---

### T-02 — Attestation replayed against a different ChangeSet
**Likelihood:** medium · **Impact:** high

An attacker attaches a valid attestation for a benign change to a malicious change.

**C-02:** The subject digest binds the attestation to the exact ChangeSet (`ADR-002`).
Verification steps 9 and 10 (`SPEC-001 §8`) reject mismatches. `AC-F08-110` tests this directly.

---

### T-03 — Signature valid, identity attacker-controlled
**Likelihood:** medium · **Impact:** critical

Anyone can obtain a Fulcio certificate and sign a fabricated attestation. If verification checks
only the signature, it "verifies".

**C-03:** Identity verification is mandatory and unbypassable (`ADR-004`, `REQ-F08-040`). The API
makes the constraint a required argument, so it cannot be forgotten. Unbounded patterns are
rejected (`REQ-F08-050`). A static-analysis test hunts for bypasses (`AC-F08-040`).

**This is the most important control in the system.**

---

### T-04 — Attestation suppression
**Likelihood:** high · **Impact:** high

The easiest attack is producing no attestation at all.

**C-04:** The policy decision assigns blocking absence exit `5` (`REQ-F09-030`), and the F-11
Action publishes that result as a **required** status check (`REQ-F11-110`). Branch protection must
pin the check to the expected GitHub App where supported. Residual risk remains because attest does
not control branch protection and F-09's exact check-name predicate is not an app-identity claim.
Documentation must state that a gate which is not required is advisory.

---

### T-05 — Malicious policy file as an execution vector
**Likelihood:** medium · **Impact:** critical

The gate runs in a job with `id-token: write`. Code execution there means forged attestations.

**C-05:** Policy is a closed declarative vocabulary with no scripting (`ADR-008`). The pure loader
enforces byte/depth bounds and rejects duplicate keys, tags, anchors, aliases, merges, extra
documents, and non-standard scalar construction before strict Pydantic validation
(`AC-F09-090`, `ADR-042`).

---

### T-06 — Secret or personal data leakage via prompts
**Likelihood:** high · **Impact:** high

Prompts routinely contain API keys, customer data, and personal data. Storing them in a signed,
publicly-logged artifact would be severe.

**C-06:** Raw prompt text is **never** carried into the predicate. Only `promptDigest`. A `prompt`
field in a sidecar is ignored with a warning (`REQ-F03-040`). A negative test asserts no input can
cause prompt text to reach the output (`AC-F03-040`).

Note the transparency log is **public** in the default configuration. Anything in an attestation
is effectively published. This must be stated in the README, not buried.

---

### T-07 — Source code leakage into attestations
**Likelihood:** medium · **Impact:** high

**C-07:** The predicate carries paths, digests, and counts — never file content. Export explicitly
excludes source (`REQ-F12-090`). Organisations concerned about path disclosure should be told to
use a private Rekor instance; the README must cover this.

---

### T-08 — Reviewer identity spoofing
**Likelihood:** low · **Impact:** high

**C-08:** Reviewer identity uses immutable numeric IDs, never renameable logins
(`REQ-F04-010`, `REQ-F09-110`). The forge API response digest is recorded so the basis is
traceable.

---

### T-09 — Supply-chain compromise of attest itself
**Likelihood:** low · **Impact:** critical

attest runs in privileged CI jobs across many organisations.

**C-09:** Small, audited dependency tree; `pip-audit` and `bandit` in CI; SBOM per release;
releases signed and attested by attest itself; the Action pins the image by digest, not tag
(`REQ-F11-010`). CI consumes external actions only at reviewed full commit SHAs, pins its uv
version, and installs exclusively from the committed lock (`ADR-027`).

---

### T-10 — Malicious pull request exfiltrating the signing identity
**Likelihood:** medium · **Impact:** critical

A PR from a fork, in a workflow using `pull_request_target`, may run attacker-controlled code with
access to the workflow token.

**C-10:** Documentation **MUST** cover this explicitly (`REQ-F11-070`). Recommended patterns:
prefer `pull_request` where possible; when `pull_request_target` is required, never check out
untrusted code in the signing job. attest cannot enforce this — it is a workflow design issue —
so the documentation obligation is the control.

---

### T-11 — Downgrade to a weaker predicate version
**Likelihood:** low · **Impact:** medium

**C-11:** Unknown predicate types are rejected outright (`REQ-F08-090`). Policy can constrain
acceptable versions. Old versions remain verifiable but are identifiable.

---

### T-12 — Test vector tampering
**Likelihood:** low · **Impact:** critical

Vectors define correctness. Silently changing one changes the specification.

**C-12:** Vectors are normative (`QA-001 §4`); regenerating expected values to pass a failing test
is forbidden (`AGENTS.md §3.3`); changes require an ADR; vector directories should be
`CODEOWNERS`-protected.

---

### T-13 — Time-of-check to time-of-use between attestation and merge
**Likelihood:** medium · **Impact:** medium

An attestation is produced for head commit X; the branch is then updated to Y before merge.

**C-13:** The gate **MUST** be re-run on the final merge candidate, and the required status check
**MUST** be configured to require branches to be up to date. This is a configuration obligation
documented in the quickstart, not something attest can enforce alone. Stated as a residual risk.

---

### T-14 — Incomplete forge identity context bypasses separation of duties

**Likelihood:** medium · **Impact:** high

An unmapped or omitted commit author/committer could be treated as a non-author reviewer, allowing
self-approval to satisfy policy.

**C-14:** The F-04 GitHub context resolver binds every requested field to the current PR response,
exhaustively accounts for the exact comparison, and fails closed on PR drift, caps,
missing/duplicate pages, count drift, endpoint mismatch, or any unmapped author or committer
association. Names and email addresses are never mapped heuristically
(`REQ-F04-150`, `ADR-045`).

---

### T-15 — CLI input or generated workflow becomes a privileged execution vector

**Likelihood:** medium · **Impact:** critical

The CLI processes repository-controlled files and generates a workflow with OIDC and repository
write permission. Symlink races, unsafe YAML, arbitrary plugin hooks, or a
`pull_request_target` checkout could disclose credentials or execute attacker code.

**C-15:** F-10 uses closed bounded models, safe YAML/JSON, no-follow regular-file reads, revalidated
atomic writes, no interactive/plugin/script configuration, and deny-by-default egress. Its workflow
uses `pull_request`, never `pull_request_target`, and invokes only caller-supplied full-SHA checkout
and attest Actions. F-11 must prove the published Action does not execute repository content and is
pinned to an immutable image digest before release (`REQ-F10-160`, `REQ-F10-190`, `ADR-045`).

---

## 5. Residual risks (accepted and documented)

| # | Residual risk | Why accepted |
|---|---|---|
| R1 | Unclaimed AI use is invisible | Inherent to the claim model; detection is worse |
| R2 | A gate that is not a required check is decorative | attest cannot control branch protection; documented |
| R3 | Public transparency log publishes metadata | Default is public; private Rekor documented as the mitigation |
| R4 | Review record proves approval, not comprehension | Unknowable; never claimed |
| R5 | A compromised CI system can produce genuine attestations for malicious code | attest attests custody, not correctness |

Every residual risk **MUST** appear in the README limitations section. Discovering them yourself
and publishing them is worth more than the risk they represent.

---

## 6. Security testing obligations

| Obligation |
|---|
| Adversarial verification suite (`BRD-F08 §7`) runs on every commit |
| Property test: no single-byte mutation of a bundle ever verifies |
| Secret-leak test: no token appears in any output stream across the full suite |
| Prompt-leak test: no input causes prompt text to reach a predicate |
| Safe-YAML test: policy loading cannot trigger construction |
| No-egress test: `attest-core` and `attest-policy` make no network calls |
| CLI no-egress test permits only explicit forge/signing/storage/online-refresh/doctor operations and confirms no telemetry |
| CLI hostile-file suite covers bounds, unsafe YAML/JSON, symlinks, devices, input races, create-only output, and atomic overwrite |
| Generated-workflow tests reject `pull_request_target`, mutable Action refs, excess permissions, and any untrusted-code execution path |
| `pip-audit` and `bandit` gate releases |

---

## 7. Vulnerability disclosure

`SECURITY.md` at the repository root **MUST** specify: a contact address, a 90-day coordinated
disclosure window, and a commitment that verification-bypass reports are treated as critical
severity regardless of exploitation difficulty.

For this product, a verification bypass is the worst possible class of bug — it silently converts
every attestation into a false assurance. Treat it accordingly.
