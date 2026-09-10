# attest — Master Project Document

| Field | Value |
|---|---|
| Document ID | `MPD-001` |
| Version | `1.0.1` |
| Status | Baselined |
| Owner | Parth (ZettaCore) |
| Last updated | 2026-09-10 |
| Supersedes | — |

> **Read this first.** This document is the entry point. It is *descriptive*, not normative,
> except for §3 (Scope) and §12 (Document Authority). Where this document and a normative
> document disagree, **the normative document wins**. See §12.

---

## 1. Problem statement

Git records *who committed* a change. It does not record *what produced it*.

A modern commit message says `Alice merged PR #482`. It does not say:

- which model wrote the diff, at which version,
- under which agent harness and session,
- whether a human actually read it before approval,
- or whether any of that can still be proven six months later during an audit.

Three forces make this an urgent, budgeted problem rather than a philosophical one:

1. **Volume has outpaced review.** Review time per PR has risen sharply while a large share of
   PRs now merge with no human review at all. The control that compliance frameworks assume
   ("a human reviewed and understood this change") is quietly failing.
2. **Quality and security are measurably degrading.** Independent measurement shows code churn
   roughly doubling in the AI era, duplication rising, and a large fraction of AI-generated code
   introducing at least one OWASP Top 10 class defect.
3. **Regulators have arrived.** EU AI Act record-keeping obligations, SOC 2 CC8.1 change
   management, ISO/IEC 42001, and NIST SP 800-218A all now require evidence about how software
   was produced — and existing tooling produces *analytics*, not *evidence*.

The gap: **there is no cross-vendor, tamper-evident, verifiable record binding a merged code
change to the model, session, and human reviewer behind it.**

Existing tools sit either side of the gap:

| Category | Examples | Why it does not close the gap |
|---|---|---|
| AI-usage analytics | Git AI, Cursor AI Code Tracking, Copilot co-author trailers | Mutable, unsigned, vendor-scoped. Dashboard-grade, not audit-grade. |
| Build/artifact provenance | Chalk, Chainloop, SLSA tooling | Signs the *build*, not the *authoring act*. Starts after the code exists. |
| AI code review | CodeRabbit, Greptile, Graphite, Qodo | Finds bugs. Produces no durable, verifiable record. |
| Agent identity/authz | Descope, WorkOS, Permit.io | Governs runtime agent access, not code provenance. |

---

## 2. Product definition

**attest** is an open-source, CI-native tool that produces **cryptographically signed,
tamper-evident provenance attestations** for code changes, and verifies them as a merge gate.

For each merged change it emits an in-toto Statement, wrapped in a DSSE envelope, signed
keylessly via Sigstore, and recorded in a transparency log. The statement binds together:

```
  ChangeSet digest  ←→  Authorship claims  ←→  Review record  ←→  Signing identity
   (what changed)      (which model/agent)     (which human)      (which CI job)
```

### 2.1 The one-sentence positioning

> attest turns "an AI probably wrote some of this" into a signed, verifiable, exportable
> record that survives an auditor, a regulator, and an incident review.

### 2.2 What attest is NOT

This section exists to prevent scope drift and over-claiming. It is binding.

| attest is NOT | Why this matters |
|---|---|
| An AI-code *detector* | We do not statistically infer AI authorship. We attest **claims** made by tools, plus the environment that collected them. Detection is unreliable and legally dangerous to assert. |
| A code review tool | We record that review happened and by whom. We do not judge code quality. |
| A compliance guarantee | We produce *evidence*. Compliance is determined by the auditor and the organisation. Marketing must say "compliance-enabling", never "compliant". |
| A build-provenance (SLSA) replacement | attest covers authoring. SLSA covers building. They compose; they do not compete. |
| A secrets or prompt archive | Raw prompt text is **never** stored by default. Only digests. See `SEC-001`. |

### 2.3 Core claim model (critical concept)

attest attests **chain of custody**, not **forensic truth**.

- We assert: *"At time T, in trusted CI environment E, the following authorship claims were
  present in the repository, bound to diff digest D, alongside review record R, and this
  assertion is signed by identity I."*
- We do **not** assert: *"An AI definitively wrote line 42."*

Every document, schema field, error message, and marketing sentence must respect this
distinction. It is the product's intellectual honesty and its legal safety.

---

## 3. Scope (NORMATIVE)

### 3.1 In scope — v1.0

| ID | Capability |
|---|---|
| `SCOPE-01` | Deterministic ChangeSet digest computation from git object IDs |
| `SCOPE-02` | Collection of authorship claims from trailers, sidecar claim files, and Git Notes |
| `SCOPE-03` | Collection of review records from GitHub (PR reviews, check runs) |
| `SCOPE-04` | Construction of in-toto Statements using predicate `SPEC-001` |
| `SCOPE-05` | Keyless signing via Sigstore (Fulcio + Rekor), DSSE envelope, bundle output |
| `SCOPE-06` | Storage in a git ref namespace, and optionally an OCI registry |
| `SCOPE-07` | Full verification: signature, certificate identity, transparency log inclusion, schema, subject binding |
| `SCOPE-08` | Declarative policy engine and blocking CI gate |
| `SCOPE-09` | CLI with deterministic exit codes |
| `SCOPE-10` | GitHub Action packaging |
| `SCOPE-11` | Evidence export mapped to control identifiers |

### 3.2 Out of scope — v1.0 (deferred, not rejected)

| ID | Capability | Target |
|---|---|---|
| `OOS-01` | Hosted multi-tenant evidence store | v1.1 |
| `OOS-02` | GitLab and Bitbucket collectors | v1.1 |
| `OOS-03` | Web dashboard | v1.2 |
| `OOS-04` | Solidity/EVM provenance plug-in | v1.2 |
| `OOS-05` | Statistical AI-code detection | **Never** (see §2.2) |
| `OOS-06` | Raw prompt storage | **Never by default**; opt-in encrypted only, v1.2 |
| `OOS-07` | Agent runtime authorization | **Never** (different product) |

Any work item that does not map to a `SCOPE-xx` identifier is out of scope for v1.0 and must be
rejected or converted into a change request against this document.

---

## 4. Users and buyers

| Persona | Role | Pain | What they do with attest |
|---|---|---|---|
| **Dana — Platform / DevSecOps engineer** | Primary user | Owns CI. Asked by security to "prove AI code is reviewed." Has no mechanism. | Installs the Action, writes the policy, owns the gate. |
| **Raj — Engineering lead** | Influencer | Drowning in unreviewed AI PRs. Wants enforcement without becoming the bottleneck. | Sets review requirements in policy; reads violation reports. |
| **Priya — Compliance / GRC lead** | Economic buyer | Auditor asks "show me change-management evidence for AI-generated code." Currently screenshots Jira. | Runs `attest export`, hands the bundle to the auditor. |
| **Sam — External auditor** | Validator | Needs evidence they can independently verify without trusting the vendor. | Runs `attest verify` on the bundle offline. |

**Buying trigger:** an audit finding, a customer security questionnaire, or an EU AI Act
readiness programme. Not developer delight. This shapes GTM: land with the free CLI via Dana,
monetise via Priya.

---

## 5. Solution overview

### 5.1 Lifecycle

```
 ┌──────────┐   ┌─────────┐   ┌────────┐   ┌────────┐   ┌────────┐   ┌────────┐
 │ COLLECT  │──▶│  BUILD  │──▶│  SIGN  │──▶│ STORE  │──▶│ VERIFY │──▶│  GATE  │
 └──────────┘   └─────────┘   └────────┘   └────────┘   └────────┘   └────────┘
   git diff      in-toto        DSSE +       git ref /     sig +        policy
   trailers      Statement      Fulcio       OCI           identity +   decision
   claims        (SPEC-001)     + Rekor                    Rekor        exit code
   reviews
                                                                          │
                                                                          ▼
                                                                    ┌──────────┐
                                                                    │  EXPORT  │
                                                                    └──────────┘
                                                                     control-mapped
                                                                     evidence bundle
```

### 5.2 The two irreducible technical ideas

Everything else is plumbing. These two are the product.

**(a) A deterministic ChangeSet digest that any implementation can reproduce.**
We digest *git object identities*, never rendered diff text. Diff text varies by algorithm,
context width, whitespace flags, and renderer. Blob OIDs do not. This makes the digest
reproducible across machines, languages, and years. Specified in `SPEC-001 §5`.

**(b) Identity-bound verification, not merely signature verification.**
A valid signature proves *someone* signed. It proves nothing about *who*. Verification must
assert that the signing certificate's identity matches an expected CI workflow identity and
issuer. Without this control the product is security theatre. Specified in `SPEC-001 §8` and
enforced by `F-08` / `F-09`.

---

## 6. Architecture summary

Full detail in `ARCH-001`. Summary only here.

| Package | Responsibility | Depends on |
|---|---|---|
| `attest-core` | Domain models, predicate schema, canonicalisation, digests | — |
| `attest-collect` | Git, trailer, sidecar, and forge collectors | core |
| `attest-sign` | Sigstore signing and verification, DSSE, bundles | core |
| `attest-store` | Git-ref and OCI storage backends | core |
| `attest-policy` | Policy model, evaluation, decisions | core |
| `attest-export` | Control mapping, evidence bundles | core, store, sign |
| `attest-cli` | Command surface, config, output, exit codes | all |

Dependency rule (enforced in CI): dependencies point **inward toward `attest-core`**. Peer adapters
do not import each other; `attest-export` is the bounded application layer above store and sign;
`attest-cli` is the top-level root (`ADR-022`). No cycles.

---

## 7. Technology

Implementation language: **Python 3.12+**, decided and final for v1.x (`ADR-012`). Rationale, full
library list, and version pinning policy in `TECH-001`. The language question is closed; it is not
reopened by any document, contributor, or agent except via the single bounded trigger in `ADR-011`.

Short justification: this product's centre of gravity is Sigstore, in-toto, DSSE, and TUF.
Those ecosystems are Python-first — `sigstore-python` is maintained by the Sigstore project
itself, and the in-toto reference implementation is Python. Choosing Python means consuming
first-party, actively maintained cryptographic tooling rather than second-tier bindings. For a
security product, that is the correct trade even at the cost of writing in a less familiar
language.

The known cost is documented honestly in `TECH-001 §9`: single-binary distribution and CI
cold-start are harder in Python than in Go or Node. Mitigations are specified there.

---

## 8. Feature map

| ID | Feature | BRD | Milestone |
|---|---|---|---|
| `F-01` | Core domain model and predicate schema | `BRD-F01` | M1 |
| `F-02` | Git ChangeSet collector | `BRD-F02` | M1 |
| `F-03` | Authorship claim collector | `BRD-F03` | M1 |
| `F-04` | Review record collector (GitHub) | `BRD-F04` | M2 |
| `F-05` | Attestation builder | `BRD-F05` | M1 |
| `F-06` | Sigstore signing | `BRD-F06` | M1 |
| `F-07` | Storage and retrieval | `BRD-F07` | M2 |
| `F-08` | Verification | `BRD-F08` | M1 |
| `F-09` | Policy engine and CI gate | `BRD-F09` | M2 |
| `F-10` | CLI | `BRD-F10` | M1 |
| `F-11` | GitHub Action packaging | `BRD-F11` | M2 |
| `F-12` | Evidence export and control mapping | `BRD-F12` | M3 |

Build order and dependencies are given in `BRD-INDEX`. Do not build features out of the
declared order — later features consume earlier contracts.

---

## 9. Milestones

| Milestone | Window | Exit criterion (binary, testable) |
|---|---|---|
| **M1 — Signed core** | Days 0–30 | `attest run` in a GitHub Actions workflow produces a signed attestation logged to Rekor; `attest verify` validates it on a clean machine with no local state. Predicate spec published publicly. |
| **M2 — Enforcement** | Days 31–60 | A policy violation blocks a PR merge via a required status check in a real repository. Three external design partners have it running in CI. |
| **M3 — Evidence** | Days 61–90 | `attest export --framework soc2` produces a bundle that a practising auditor confirms is usable as change-management evidence. One paid pilot agreed. |

Detail, weekly breakdown, and definition of done in `ROADMAP-001`.

---

## 10. Business model

- **Open core.** Apache-2.0 CLI, Action, and predicate specification. Free forever, self-hostable,
  no telemetry by default.
- **Paid tier (v1.1+).** Hosted evidence store with retention management, control mapping and
  auditor export packs, org-wide policy distribution, SSO/RBAC, and self-hosted enterprise
  deployment.
- **Pricing shape.** Per-active-committer per-month, plus a compliance module. Benchmarked
  against adjacent AI code-review tooling in the $12–20/seat range.
- **Wedge sequencing.** Standard first, tool second, SaaS third. Owning the predicate
  specification is the durable asset; the SaaS is the rent collector.

---

## 11. Success and kill criteria

Tracked in `RISK-001`. Headline criteria:

| Criterion | Threshold | Action if missed |
|---|---|---|
| Spec adoption | 1 external implementation or 1 standards-body engagement by day 120 | Reassess standard-ownership thesis |
| CI adoption | 25 repositories running the gate by day 90 | Re-examine onboarding friction |
| Willingness to pay | 1 paid pilot by day 90; 3 by day 180 | Pivot to the eval-gate runner-up idea |
| Platform displacement | GitHub ships cross-vendor **signed** authoring provenance | Reposition to policy/evidence layer above it |

---

## 12. Document authority (NORMATIVE)

To eliminate contradiction between documents — and to stop implementation agents inventing
behaviour — exactly one document is normative per concern. If two documents conflict, the
normative one governs and the other is a defect to be fixed.

| Concern | Normative document | Everything else is |
|---|---|---|
| Repository scaffold, file contents, tooling config | `BOOT-001` | commentary |
| Validation gates and empirical unknowns | `CHALLENGE-001` | commentary |
| Attestation format, digests, canonicalisation, verification rules | `SPEC-001` | commentary |
| Terminology, identifiers, naming | `GLOSS-001` | commentary |
| Component boundaries, data flow, package rules | `ARCH-001` | commentary |
| Libraries, versions, tooling | `TECH-001` | commentary |
| Feature behaviour and acceptance criteria | the relevant `BRD-Fxx` | commentary |
| Recorded decisions and their rationale | `ADR-LOG` | commentary |
| Threat model and security controls | `SEC-001` | commentary |
| Test obligations | `QA-001` | commentary |
| Agent implementation rules | `AGENTS.md` | commentary |
| Scope | this document, §3 | commentary |

**Change rule.** Any change to a normative document requires a new ADR in `ADR-LOG` recording
what changed and why. Silent edits to normative documents are forbidden. This rule exists
specifically so that a coding agent cannot quietly redefine the format mid-implementation.

---

## 13. Document set

| ID | File | Purpose |
|---|---|---|
| `MPD-001` | `00-MASTER-PROJECT-DOCUMENT.md` | This document |
| `GLOSS-001` | `01-GLOSSARY-AND-CONVENTIONS.md` | Canonical terms and ID scheme |
| `SPEC-001` | `02-SPEC-001-AI-AUTHORSHIP-PREDICATE.md` | The normative format specification |
| `ARCH-001` | `03-SYSTEM-ARCHITECTURE.md` | Components, flows, contracts |
| `TECH-001` | `04-TECH-STACK-PYTHON.md` | Python stack and rationale |
| `ADR-LOG` | `05-ADR-LOG.md` | Decision records |
| `BRD-INDEX` | `06-BRD-INDEX-AND-TRACEABILITY.md` | Feature index, build order, traceability matrix |
| `BRD-F01..F12` | `brd/BRD-F01.md` … `brd/BRD-F12.md` | Per-feature requirements |
| `QA-001` | `07-TESTING-AND-QUALITY-STRATEGY.md` | Test strategy and obligations |
| `DEV-001` | `08-REPO-SCAFFOLD-AND-DEV-WORKFLOW.md` | Repository layout and workflow |
| `AGENTS.md` | `09-AGENTS.md` | Rules for AI coding agents on this repo |
| `ROADMAP-001` | `10-ROADMAP-90-DAY.md` | Week-by-week plan and DoD |
| `RISK-001` | `11-RISK-REGISTER-AND-KILL-CRITERIA.md` | Risks, mitigations, kill criteria |
| `SEC-001` | `12-SECURITY-THREAT-MODEL.md` | Threat model and controls |
| `BOOT-001` | `13-BOOTSTRAP-AND-BOILERPLATE.md` | Complete, buildable scaffold specification |
| `CHALLENGE-001` | `14-OPEN-CHALLENGES-AND-VALIDATION.md` | What is genuinely unresolved, and how to resolve it |

---

## 14. Open questions — all closed

Every question that blocked a feature has been closed by a recorded decision. **No feature in
this document set is blocked on an undecided question.**

| ID | Question | Closed by | Decision |
|---|---|---|---|
| `OQ-01` | Predicate type URI and domain | `ADR-013` | Org-controlled URI; v0.x explicitly unstable; freezes at v1.0 |
| `OQ-02` | Git ref namespace vs. notes for storage | `ADR-014` | `refs/attestations/<digest>`; notes not used for storage |
| `OQ-03` | Offline-verifiable inclusion proof | `ADR-015` | Embedded at signing; verified offline; no online substitute |
| `OQ-04` | Control identifiers for export | `ADR-016` | Build now with `draft-unreviewed` mappings; publishing gated on practitioner review |
| `OQ-05` | Licence | `ADR-017` | Apache-2.0 for code, CC-BY-4.0 for the specification |
| `OQ-06` | Implementation language | `ADR-012` | Python 3.12+, final for v1.x |

**Nothing further may be added to this table without a corresponding ADR.** If an implementer or
agent encounters a genuine gap, it is reported as `SPEC-GAP` (`AGENTS.md §8`) and closed by a new
ADR — never by silent choice.

What remains unresolved is **not** a documentation question. It is empirical, and is tracked in
`CHALLENGE-001` — the validation work that must happen before and alongside the build.
