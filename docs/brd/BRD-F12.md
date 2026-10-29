# BRD-F12 — Evidence Export and Control Mapping

| Field | Value |
|---|---|
| Document ID | `BRD-F12` |
| Feature | `F-12` |
| Milestone | M3 |
| Package | `attest-export` |
| Depends on | `F-07`, `F-08` |
| Status | Validation in progress; production implementation blocked on `CH-04` (`ADR-064`, `ADR-070`) |

---

## 1. Purpose

Turn a set of verified attestations into an artifact an auditor can consume and independently
verify. This is the feature the economic buyer pays for; everything before it is the free tier.

> **Hard constraint on language.** Export output **MUST** describe itself as evidence, never as
> proof of compliance. See `GLOSS-001 §2.2`. A compliance claim in an audit artifact is both
> dishonest and commercially dangerous.

## 2. Scope trace

`SCOPE-11`.

## 3. Dependencies

`F-07`, `F-08`. `OQ-04` is **closed** by `ADR-016`, which originally separated **building** from
**publishing**:

- At the time of `ADR-016`, implementation was unblocked because the bundle structure,
  verification-during-export, `verify.sh`, and exceptions reporting are independent of which
  control IDs are cited. `ADR-064` later changed the implementation timing as stated below.
- Mapping files ship with mandatory metadata `status: draft-unreviewed`, `reviewedBy: null`,
  `reviewedAt: null`.
- Exports generated from a draft mapping carry a prominent, non-suppressible banner.
- A mapping becomes `status: reviewed` only with a named practitioner and date.
- `F-12` does not pass Definition of Done until at least one framework mapping is `reviewed`.

**Do not guess control mappings and mark them reviewed.** Drafting candidate mappings for a
practitioner to correct is expected and encouraged.

`ADR-064` later restored the empirical challenge gate: production F-12 implementation does not
begin until `CH-04` closes with its required practising-auditor evidence. `ADR-070` authorizes only
the normative exception-lifecycle design and synthetic validation artifacts while that gate is
open. It does not authorize package, CLI, Action, schema, or publication work.

## 4. Data contract

```python
def export_evidence(
    bundles: Sequence[bytes],
    constraint: IdentityConstraint,
    framework: str,
    period: tuple[datetime, datetime],
) -> EvidenceBundle: ...
```

Output directory structure:

```
evidence-<framework>-<period>/
├── manifest.json          # index, digests, generation metadata
├── summary.md             # human-readable narrative
├── controls/
│   └── <control-id>.md    # per-control evidence narrative + references
├── attestations/
│   └── <digest>.sigstore.json
└── verify.sh              # reproduces verification independently
```

### 4.1 Policy-exception validation contract

`ADR-070` adds a second class of evidence for validation: a signed **Policy Exception Record**
representing either emergency authorization or later retrospective review. It is separate from
missing or unverifiable attestation exceptions and does not mutate the original Statement or
Policy Decision.

The exact Policy Exception Record predicate, function parameter, and output paths are deliberately
not baselined while `CH-04` is open. The validation kit uses synthetic unsigned records labelled as
such. A follow-up ADR, informed by practitioner responses, must finalize the public wire and API
contract before production implementation.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F12-010` | Every attestation included **MUST** be verified during export; unverifiable ones **MUST** be excluded and listed separately as exceptions. |
| `REQ-F12-020` | The bundle **MUST** include the raw attestations, so the auditor can verify independently of attest's summary. |
| `REQ-F12-030` | `verify.sh` **MUST** reproduce verification using only the bundle contents and a published trust root. |
| `REQ-F12-040` | `manifest.json` **MUST** record generation time, tool version, identity constraint used, period, and a digest of every included file. |
| `REQ-F12-050` | Control mapping files **MUST** be declarative data, not code, and **MUST** cite the control text they map to. |
| `REQ-F12-060` | Output **MUST NOT** contain any language prohibited by `GLOSS-001 §2.2` or a semantically equivalent over-claim. Enforced by the banned-language CI check. |
| `REQ-F12-070` | Exceptions — changes in the period with no attestation, or with verification failures — **MUST** be reported prominently, not hidden. |
| `REQ-F12-080` | The export **MUST** state its own limitations explicitly, including that authorship claims are self-reported. |
| `REQ-F12-090` | No customer source code **MUST** be included; only paths, digests, and metadata. |
| `REQ-F12-100` | Export **MUST** be deterministic given the same inputs and a fixed generation timestamp. |
| `REQ-F12-110` | Supported frameworks in v1.0: SOC 2 change management, ISO/IEC 42001, EU AI Act record-keeping. Each mapping **MUST** carry `status`, `reviewedBy`, `reviewedAt`. |
| `REQ-F12-120` | An export using any `draft-unreviewed` mapping **MUST** emit a banner in `summary.md` and a `draftMappings` array in `manifest.json`. The banner **MUST NOT** be suppressible by flag, config, or environment variable. |
| `REQ-F12-130` | A mapping **MUST NOT** be settable to `status: reviewed` without a non-null `reviewedBy` and `reviewedAt`; validation **MUST** reject it with `ERR-EXPORT-704`. |
| `REQ-F12-140` | The Evidence Bundle **MUST** represent evidence failures (unattested changes or verification failures) separately from Policy Exception Records. Neither collection **MUST** relabel, suppress, or imply resolution of the other. |
| `REQ-F12-150` | An authorization Policy Exception Record **MUST** bind the exact ChangeSet Digest, denied Decision and policy source digests, failed predicate identifiers, deployment target and workflow run, stable requester and Decision Owner identities, reason, authorization time, retrospective-review deadline, and digest of the forge source. Production exports **MUST** treat it as verified only after signature and expected-identity verification succeeds. |
| `REQ-F12-160` | Independent approval is the default. The export **MUST** state whether the Decision Owner is distinct from the requester and change author and **MUST NOT** describe self-authorization as independent approval. |
| `REQ-F12-170` | Given the fixed generation timestamp required for deterministic export, each policy exception **MUST** be classified as `open`, `overdue`, or `closed`. Deployment success **MUST NOT** close an exception, and absence of a valid closure after the deadline **MUST** produce `overdue`. |
| `REQ-F12-180` | Retrospective review **MUST** be an append-only signed event linked to the authorization record and the same ChangeSet. A valid closure **MUST** record stable reviewer identity, completion time, disposition, and review or remediation evidence; it **MUST NOT** replace or alter the authorization event. |
| `REQ-F12-190` | Unverified, incomplete, open, and overdue Policy Exception Records **MUST** appear prominently in `summary.md` and as machine-readable manifest data. No flag, config, or environment variable may suppress them, and unverified synthetic or manual input **MUST NOT** be presented as signed evidence. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F12-010` | A tampered bundle in the input set appears in exceptions, not in evidence. |
| `AC-F12-020` | Raw attestations are present and byte-identical to the stored originals. |
| `AC-F12-030` | `verify.sh` succeeds in a clean container with no attest installation beyond the documented prerequisite. |
| `AC-F12-040` | Manifest digests match the files on disk. |
| `AC-F12-050` | Mapping files are YAML/JSON with no executable content and include control citations. |
| `AC-F12-060` | The banned-language check passes over generated output. |
| `AC-F12-070` | An unattested change in the period appears in the exceptions section. |
| `AC-F12-080` | `summary.md` contains an explicit limitations section including the self-reporting caveat. |
| `AC-F12-090` | No file in the bundle contains source code content. |
| `AC-F12-100` | Two exports with a pinned timestamp are byte-identical. |
| `AC-F12-110` | Each mapping file carries `status`, `reviewedBy`, `reviewedAt`; schema validation rejects a file missing any of them. |
| `AC-F12-120` | An export from a draft mapping contains the banner in `summary.md` and `draftMappings` in `manifest.json`; no flag or environment variable removes it, asserted across the full option matrix. |
| `AC-F12-130` | Setting `status: reviewed` with `reviewedBy: null` raises `ERR-EXPORT-704`. |
| `AC-F12-140` | One unattested change and one authorized emergency release appear in different manifest collections and retain different labels in `summary.md`. |
| `AC-F12-150` | Removing or changing any required authorization binding prevents the record from being reported as verified; wrong Signing Identity and wrong ChangeSet fixtures remain unverified. |
| `AC-F12-160` | Distinct and identical requester, change-author, and Decision Owner fixtures produce explicit separation-of-duties facts without relabelling self-authorization as independent. |
| `AC-F12-170` | With an injected generation timestamp, boundary fixtures immediately before, at, and after the review deadline deterministically produce `open`, `overdue`, and `closed`; a successful deployment without closure remains open or overdue. |
| `AC-F12-180` | A closure with the wrong exception identifier, authorization digest, or ChangeSet cannot close the lifecycle; a correctly linked verified review event closes it without changing the authorization bytes. |
| `AC-F12-190` | Every unverified, incomplete, open, and overdue fixture appears in the human and machine outputs across the full option matrix; no suppression surface exists. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-EXPORT-701` | No attestations in period | Widen the period or confirm the gate is running |
| `ERR-EXPORT-702` | Unknown framework | Use a supported framework identifier |
| `ERR-EXPORT-703` | Mapping file invalid | Validate against the mapping schema |
| `ERR-EXPORT-704` | Mapping marked reviewed without a named reviewer and date | Supply `reviewedBy` and `reviewedAt`, or leave it `draft-unreviewed` |
| `ERR-EXPORT-705` | Policy Exception Record or lifecycle binding is invalid | Supply complete, correctly linked records bound to the same ChangeSet and authorization event |

## 8. Out of scope

Automated control testing, GRC platform integrations, continuous monitoring dashboards. All v1.2+.

## 9. Definition of Done

- [ ] At least one framework mapping is `status: reviewed` with a named practitioner (`ADR-016`)
- [ ] All `REQ-F12-*` implemented, all `AC-F12-*` green
- [ ] One real auditor has reviewed a generated bundle and confirmed in writing it is usable as change-management evidence
- [ ] `CH-04` reviewers have accepted or corrected the Policy Exception Record lifecycle shape and overdue-state presentation
- [ ] Final signed authorization and retrospective-review records verify in a clean container after their follow-up ADR baselines the format
- [ ] `verify.sh` validated in a clean container
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
