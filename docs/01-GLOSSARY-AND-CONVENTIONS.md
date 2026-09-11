# attest — Glossary and Conventions

| Field | Value |
|---|---|
| Document ID | `GLOSS-001` |
| Version | `1.0.4` |
| Status | **NORMATIVE** for terminology and identifiers |
| Last updated | 2026-09-10 |

> **Why this document exists.** Ambiguous vocabulary is the single largest source of drift in
> AI-assisted implementation. If "attestation", "claim", and "record" are used loosely, an
> implementation agent will invent three incompatible models. Every term below has exactly one
> meaning. Forbidden synonyms are listed so they can be caught in review.

---

## 1. Requirement language

This project uses RFC 2119 / RFC 8174 keywords. In all documents:

| Keyword | Meaning |
|---|---|
| **MUST** / **MUST NOT** | Absolute requirement. A violation is a defect. |
| **SHOULD** / **SHOULD NOT** | Strong recommendation. Deviation requires a recorded ADR. |
| **MAY** | Optional. |

Keywords are normative only when in **bold uppercase**. Lowercase "must" in prose is
commentary.

---

## 2. Canonical terms

Each entry gives the **only** correct term, its definition, and terms that **MUST NOT** be used
for it.

### 2.1 Domain terms

| Term | Definition | Do NOT call it |
|---|---|---|
| **ChangeSet** | The set of file-level changes between a base commit and a head commit, expressed as git object identities. The unit attest attests. | diff, patch, changeset (lowercase), delta, PR contents |
| **ChangeSet Digest** | The SHA-256 hex digest produced by algorithm `CSD-1` over the canonicalised ChangeSet record. | diff hash, content hash, patch digest |
| **Authorship Claim** | A self-reported assertion by a tool or human that a given agent/model contributed to a ChangeSet. **Unverified by nature.** | attribution, detection, authorship record, AI usage |
| **Review Record** | Forge-verified evidence that a human approved (or rejected) the ChangeSet, including approver identity and timestamp. | approval, sign-off, human check |
| **Statement** | An in-toto Statement: subject + predicateType + predicate. | payload, document, claim |
| **Predicate** | The `predicate` object inside a Statement, conforming to `SPEC-001`. | body, data, metadata |
| **Envelope** | A DSSE envelope wrapping a serialised Statement plus signatures. | wrapper, container |
| **Bundle** | A Sigstore bundle: envelope + verification material (certificate, transparency log entry). The unit that is stored and distributed. | artifact, blob, package |
| **Attestation** | Informal umbrella term for a signed Bundle. Acceptable in prose and marketing. **MUST NOT** be used as a type or variable name — use `Bundle`, `Envelope`, or `Statement` precisely. | — |
| **Collector** | A component that gathers one class of input signal. | scanner, parser (as a component name), detector |
| **Signing Identity** | The workflow identity encoded in the Fulcio certificate SAN, plus its OIDC issuer. | signer, key, author |
| **Policy** | A declarative document stating what MUST be true for a ChangeSet to be allowed. | rules, config, gate config |
| **Decision** | The output of policy evaluation: `allow`, `warn`, or `deny`, plus reasons. | result, verdict (reserved — see below), outcome |
| **Verdict** | Reserved exclusively for a human or automated **reviewer's** conclusion inside a Review Record. Never for policy output. | — |
| **Evidence Bundle** | An export artifact mapping one or more Bundles to control identifiers, for audit. | report, export, audit pack |
| **Control** | An identified requirement from a compliance framework (e.g. SOC 2 CC8.1). | requirement (reserved for our own REQs), rule |

### 2.2 Explicitly banned language

These phrases **MUST NOT** appear in code, documentation, error messages, or marketing. They
over-claim and create legal exposure. See `MPD-001 §2.2`.

<!-- # banned-language-allowlist:start -->
| Banned | Use instead |
|---|---|
| "detects AI-generated code" | "records authorship claims" |
| "proves an AI wrote this" | "attests that a claim was present and signed" |
| "makes you compliant" / "compliance guaranteed" | "produces audit evidence" / "compliance-enabling" |
| "tamper-proof" | "tamper-evident" |
| "verified authorship" | "verified signature over a claimed authorship record" |
| "AI percentage of your codebase" | "share of ChangeSets carrying AI authorship claims" |
<!-- # banned-language-allowlist:end -->

The string check for these phrases is a CI job (`QA-001 §7`).

---

## 3. Identifier scheme

All identifiers are stable and **MUST NOT** be renumbered once published. Retired identifiers
are marked `DEPRECATED`, never reused.

| Prefix | Applies to | Format | Example |
|---|---|---|---|
| `F-` | Feature | `F-NN` | `F-06` |
| `REQ-` | Requirement inside a BRD | `REQ-FNN-NNN` | `REQ-F06-010` |
| `AC-` | Acceptance criterion | `AC-FNN-NNN` | `AC-F06-010` |
| `ADR-` | Architecture decision record | `ADR-NNN` | `ADR-004` |
| `SCOPE-` | In-scope capability | `SCOPE-NN` | `SCOPE-05` |
| `OOS-` | Out-of-scope item | `OOS-NN` | `OOS-05` |
| `T-` | Threat | `T-NN` | `T-03` |
| `C-` | Security control | `C-NN` | `C-07` |
| `RISK-` | Business/technical risk | `RISK-NN` | `RISK-02` |
| `OQ-` | Open question | `OQ-NN` | `OQ-02` |
| `ERR-` | Error code | `ERR-DOMAIN-NNN` | `ERR-VERIFY-013` |
| `CSD-` | Digest algorithm version | `CSD-N` | `CSD-1` |

### 3.1 Requirement numbering rules

- Requirements within a BRD are numbered in tens: `010`, `020`, `030`. This leaves room to
  insert without renumbering.
- Each `REQ-FNN-NNN` has exactly one matching `AC-FNN-NNN` with the same number.
- Every requirement **MUST** be traceable to a `SCOPE-xx` item. Untraceable requirements are
  scope creep and **MUST** be rejected.

---

## 4. Naming conventions in code

| Element | Convention | Example |
|---|---|---|
| Package | `attest-<role>` (distribution), `attest_<role>` (import) | `attest-core` / `attest_core` |
| Module | `snake_case`, singular noun | `changeset.py`, `digest.py` |
| Class | `PascalCase`, matching a canonical term exactly | `ChangeSet`, `AuthorshipClaim`, `ReviewRecord` |
| Pydantic model for wire format | Canonical term + no suffix | `Predicate`, `Statement` |
| Internal DTO not on the wire | Canonical term + `Input` / `Result` | `CollectResult` |
| Function | `snake_case`, verb-first | `compute_changeset_digest()` |
| Constant | `UPPER_SNAKE_CASE` | `PREDICATE_TYPE_V0_1` |
| Error class | `<Domain>Error` | `VerificationError`, `PolicyError` |
| CLI command | lowercase verb, no abbreviations | `attest verify`, not `attest vfy` |
| JSON field | `camelCase` (in-toto/Sigstore ecosystem convention) | `changeSetDigest` |
| Python field | `snake_case`, aliased to camelCase for serialisation | `change_set_digest` |

> **Wire format rule.** JSON on the wire is `camelCase` because the in-toto and Sigstore
> ecosystems use it. Python code is `snake_case`. Pydantic aliases bridge the two. Never
> hand-write the conversion. The protocol-defined in-toto `_type` property and digest-map
> `sha256` key are the only v0.1 exceptions (`ADR-029`).

---

## 5. Versioning

| Artefact | Scheme | Rule |
|---|---|---|
| `attest` CLI | SemVer | Breaking CLI or exit-code change = major |
| Predicate (`SPEC-001`) | `vMAJOR.MINOR` in the type URI | Any field removal or semantic change = major, new URI |
| Digest algorithm | `CSD-N` | Any change to the algorithm = new N. Old N remains verifiable forever. |
| Policy schema | `version:` integer field | Increment on breaking change; old versions still evaluated |

**Backwards compatibility rule (NORMATIVE):** attest **MUST** be able to verify every
attestation format it has ever emitted, indefinitely. Audit evidence that stops verifying is
worthless. Verification code for old versions is never deleted, only marked legacy.

---

## 6. Error code taxonomy

Errors are identified, not just messaged, so policies and tests can assert on them.

| Domain | Range | Meaning |
|---|---|---|
| `ERR-CONFIG-*` | 001–099 | Configuration or invocation problems |
| `ERR-COLLECT-*` | 100–199 | Signal collection failures |
| `ERR-BUILD-*` | 200–299 | Statement construction failures |
| `ERR-SIGN-*` | 300–399 | Signing failures |
| `ERR-STORE-*` | 400–499 | Storage failures |
| `ERR-VERIFY-*` | 500–599 | Verification failures |
| `ERR-POLICY-*` | 600–699 | Policy evaluation failures and violations |
| `ERR-EXPORT-*` | 700–799 | Export failures |

Every raised error **MUST** carry a code, a human message, and a remediation hint. Specified
per feature in the BRDs.

---

## 7. CLI exit codes (NORMATIVE)

CI depends on these. They **MUST NOT** change without a major version bump.

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Unexpected internal error |
| `2` | Usage error (bad arguments, bad config) |
| `3` | Policy violation — the gate denied the change |
| `4` | Verification failure — signature, identity, or log check failed |
| `5` | Attestation not found where one was required |
| `6` | Transient/network failure (safe to retry) |

Note the deliberate separation of `3`, `4`, and `5`. "Policy says no", "the signature is bad",
and "there is nothing here" require different human responses and different CI handling.

---

## 8. Timestamps, encodings, and formats

| Concern | Rule |
|---|---|
| Timestamps | RFC 3339, UTC, with `Z` suffix, second precision. Never local time. |
| Digests | Lowercase hex, no prefix, in the field. Algorithm named by the key (`sha256`). |
| Git object IDs | Full 40-character lowercase hex. Abbreviated OIDs **MUST NOT** appear in any signed field. |
| Canonical JSON | RFC 8785 (JCS) for anything that is digested or signed. |
| Text encoding | UTF-8 everywhere. Git paths are byte strings represented canonically as percent-encoded ASCII per `ADR-018`; do not Unicode-normalise them. |
| Line endings in digests | Irrelevant — we digest blob OIDs, not content. This is deliberate. |

---

## 9. Document conventions

- Every document has an ID, version, status, and last-updated date in a header table.
- Status is one of: `Draft`, `Baselined`, `Superseded`.
- Normative documents say **NORMATIVE** in their status line and list what they are normative for.
- Code examples in documents are **illustrative unless marked `NORMATIVE EXAMPLE`**. Illustrative
  examples **MUST NOT** be copied verbatim into the implementation without verification against
  the pinned library version.
- Cross-references use the document or requirement ID, never a page or section number alone.
