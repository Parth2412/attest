# BRD-F12 — Evidence Export and Control Mapping

| Field | Value |
|---|---|
| Document ID | `BRD-F12` |
| Feature | `F-12` |
| Milestone | M3 |
| Package | `attest-export` |
| Depends on | `F-07`, `F-08` |
| Status | Ready to build; **publishing** gated on auditor review (`ADR-016`) |

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

`F-07`, `F-08`. `OQ-04` is **closed** by `ADR-016`, which separates **building** from
**publishing**:

- Implementation is unblocked now. The bundle structure, verification-during-export, `verify.sh`,
  and exceptions reporting are independent of which control IDs are cited.
- Mapping files ship with mandatory metadata `status: draft-unreviewed`, `reviewedBy: null`,
  `reviewedAt: null`.
- Exports generated from a draft mapping carry a prominent, non-suppressible banner.
- A mapping becomes `status: reviewed` only with a named practitioner and date.
- `F-12` does not pass Definition of Done until at least one framework mapping is `reviewed`.

**Do not guess control mappings and mark them reviewed.** Drafting candidate mappings for a
practitioner to correct is expected and encouraged.

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

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-EXPORT-701` | No attestations in period | Widen the period or confirm the gate is running |
| `ERR-EXPORT-702` | Unknown framework | Use a supported framework identifier |
| `ERR-EXPORT-703` | Mapping file invalid | Validate against the mapping schema |
| `ERR-EXPORT-704` | Mapping marked reviewed without a named reviewer and date | Supply `reviewedBy` and `reviewedAt`, or leave it `draft-unreviewed` |

## 8. Out of scope

Automated control testing, GRC platform integrations, continuous monitoring dashboards. All v1.2+.

## 9. Definition of Done

- [ ] At least one framework mapping is `status: reviewed` with a named practitioner (`ADR-016`)
- [ ] All `REQ-F12-*` implemented, all `AC-F12-*` green
- [ ] One real auditor has reviewed a generated bundle and confirmed in writing it is usable as change-management evidence
- [ ] `verify.sh` validated in a clean container
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
