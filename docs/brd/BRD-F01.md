# BRD-F01 — Core Domain Model and Predicate Schema

| Field | Value |
|---|---|
| Document ID | `BRD-F01` |
| Feature | `F-01` |
| Milestone | M1 |
| Package | `attest-core` |
| Depends on | — |
| Status | Ready — `CH-01` and `CH-02` closed (`CHALLENGE-001 §12`) |

---

## 1. Purpose

Establish the typed, validated, canonicalisable representation of everything attest signs. This
package is the shared vocabulary of the entire system: every other feature either produces or
consumes these types. It contains **no I/O whatsoever** — no git, no network, no filesystem — so
that the digest and canonicalisation logic is exhaustively testable against fixed vectors.

Get this feature wrong and every downstream feature inherits the error. Build it first, and
over-test it.

## 2. Scope trace

`SCOPE-01`, `SCOPE-04`. Implements `SPEC-001` §3, §4, §5 (algorithm), §6 (wire structures;
downstream features populate them), §11, §12.

## 3. Dependencies

No feature dependencies — this is the root of the dependency graph.

**Challenge gate:** `CH-01` (does `CSD-1` survive real repositories) and `CH-02` (do the pinned
libraries behave as assumed) **MUST** be closed before starting. `CSD-1` is a wire format; a flaw
found after publication invalidates every attestation ever produced.

## 4. Data contracts

### 4.1 Types to define

| Type | Corresponds to |
|---|---|
| `Statement` | `SPEC-001 §3.2` |
| `Subject` | `SPEC-001 §3.2` |
| `DigestSet` | `SPEC-001 §3.2` |
| `Predicate` | `SPEC-001 §6.1` |
| `ChangeSetInfo`, `ChangeSetStats` | `SPEC-001 §6.2` |
| `Authorship`, `AuthorshipClaim`, `AgentRef`, `ModelRef`, `ClaimSource`, `ClaimScope` | `SPEC-001 §6.3` |
| `Review`, `Reviewer`, `ReviewEvidence`, `AutomatedReview` | `SPEC-001 §6.4` |
| `Check` | `SPEC-001 §6.5` |
| `Collection`, `CollectorRef`, `EnvironmentRef` | `SPEC-001 §6.6` |
| `ChangeSetRecord`, `ChangeSetEntry` | `SPEC-001 §5.3` |

### 4.2 Enumerations

| Enum | Values |
|---|---|
| `AuthorshipMode` | `human-authored`, `ai-assisted`, `ai-authored`, `unknown` |
| `ChangeType` | `added`, `modified`, `deleted`, `typechange` |
| `ClaimSourceKind` | `trailer`, `sidecar`, `git-note`, `forge-api`, `manual` |
| `ReviewState` | `approved`, `changes-requested`, `commented`, `none`, `unknown` |
| `ReviewVerdict` | `approved`, `changes-requested`, `commented`, `dismissed` |
| `CheckConclusion` | `success`, `failure`, `neutral`, `cancelled`, `skipped`, `timed_out` |
| `EnvironmentKind` | `github-actions`, `gitlab-ci`, `local`, `other` |

Enums are closed. Unknown values from external sources **MUST** raise a coded error, not be
silently coerced.

### 4.3 Key function signatures

```python
def canonicalize(value: JsonValue) -> bytes: ...
def compute_changeset_digest(record: ChangeSetRecord) -> str: ...
def build_changeset_record(
    entries: Sequence[ChangeSetEntry]
) -> ChangeSetRecord: ...
def generate_json_schema(predicate_version: str) -> dict[str, object]: ...
```

`compute_changeset_digest` takes an already-built record. It never reads a repository. Entry
extraction is `F-02`'s job.

`predicate_version` is the exact string `0.1`. Other values raise `ERR-BUILD-205`. The generated
schema describes a complete `Statement`, not the predicate object in isolation (`ADR-029`).

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F01-010` | All wire-format types **MUST** be Pydantic v2 models with `model_config` setting `extra="forbid"`, `frozen=True`, and `populate_by_name=True`. |
| `REQ-F01-020` | Python fields **MUST** be `snake_case`; serialisation aliases **MUST** be `camelCase` per `GLOSS-001 §4`, except for the protocol-defined `_type` and `sha256` keys. Serialisation **MUST** use aliases by default and omit optional null fields. |
| `REQ-F01-030` | `canonicalize()` **MUST** implement RFC 8785 via the `rfc8785` library. Hand-rolled canonicalisation **MUST NOT** be used. |
| `REQ-F01-040` | `canonicalize()` **MUST** raise `ERR-BUILD-201` if the input contains a float, a NaN, an infinity, or a non-UTF-8-representable string. |
| `REQ-F01-050` | `compute_changeset_digest()` **MUST** implement `CSD-1` exactly: validate canonical path encoding, sort entries by decoded raw Git path bytes ascending, build a record containing exactly `algorithm` and `entries` per `SPEC-001 §5.3` step 5, canonicalise, SHA-256, lowercase hex. Commit and repository context **MUST NOT** enter the digest. |
| `REQ-F01-060` | Entry sorting **MUST NOT** apply locale collation or Unicode normalisation. |
| `REQ-F01-070` | All timestamp fields **MUST** be timezone-aware `datetime` serialised as RFC 3339 UTC with `Z`, second precision. Naive datetimes **MUST** be rejected at validation. |
| `REQ-F01-080` | Commit OID fields **MUST** validate as exactly 40 lowercase hex characters. Abbreviated OIDs **MUST** be rejected with `ERR-BUILD-202`. |
| `REQ-F01-090` | SHA-256 value fields **MUST** validate as exactly 64 lowercase hex characters with no algorithm prefix. |
| `REQ-F01-100` | `Predicate.change_set.digest` **MUST** be validated to equal `Statement.subject[0].digest["sha256"]` at model level; mismatch raises `ERR-BUILD-203`. |
| `REQ-F01-110` | `Statement.subject` **MUST** contain exactly one entry with `name == "changeset"`. |
| `REQ-F01-120` | `generate_json_schema()` **MUST** produce the complete Statement structural schema from the models for the exact predicate version `0.1`; unsupported versions **MUST** raise `ERR-BUILD-205`. The schema **MUST NOT** be hand-authored or hand-edited. Cross-field invariants that generated JSON Schema cannot express **MUST** remain enforced by runtime model validators (`ADR-021`). |
| `REQ-F01-130` | The generated schema **MUST** be written to `spec/schemas/ai-authorship-v0.1.schema.json` by a `just schema` task, and CI **MUST** fail if the committed file differs. |
| `REQ-F01-140` | `attest-core` **MUST NOT** import `httpx`, `pygit2`, `sigstore`, `os.path` I/O helpers, or any sibling `attest-*` package. Enforced by import-linter. |
| `REQ-F01-150` | Every attest-defined error type **MUST** carry `code`, `message`, and `remediation` attributes. Direct Pydantic structural diagnostics remain `ValidationError`; F-01-assigned semantic codes **MUST** be retained in its error context (`ADR-030`). |
| `REQ-F01-160` | Test vectors listed in `SPEC-001 §12` **MUST** exist under `spec/testvectors/` and be exercised by a parametrised test. |
| `REQ-F01-170` | `AuthorshipMode` **MUST NOT** default to `human-authored`. Absence of authorship evidence maps to an explicitly supplied `unknown`; the required wire field **MUST NOT** have a model default. |
| `REQ-F01-180` | Git path strings **MUST** use the canonical percent-encoded representation from `SPEC-001 §4.1`, round-trip byte-identically, and reject non-canonical spellings. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F01-010` | Constructing any wire model with an unknown field raises `ValidationError`. Mutating a constructed model raises. |
| `AC-F01-020` | `Statement.model_dump()` emits camelCase keys by default, omits optional null fields, and preserves only the protocol-defined `_type` and `sha256` exceptions; round-trip through `model_validate` is lossless. |
| `AC-F01-030` | `canonicalize()` output matches every fixture in `spec/testvectors/jcs-canonical/` byte-for-byte. |
| `AC-F01-040` | `canonicalize({"a": 1.5})` raises `ERR-BUILD-201`. |
| `AC-F01-050` | Every `spec/testvectors/csd1-*` vector produces the expected digest exactly; identical entry transitions with different base/head commit identities produce the same digest across the squash and rebase vectors. |
| `AC-F01-060` | Vector `csd1-path-ordering` (paths where byte order differs from locale order) passes under `LC_ALL=tr_TR.UTF-8` and `LC_ALL=C`. |
| `AC-F01-070` | A naive datetime raises `ValidationError`; serialised output matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`. |
| `AC-F01-080` | A 7-character OID raises `ERR-BUILD-202`. |
| `AC-F01-090` | An uppercase-hex digest raises `ValidationError`. |
| `AC-F01-100` | A Statement whose subject digest differs from `predicate.changeSet.digest` raises `ERR-BUILD-203`. |
| `AC-F01-110` | Two subjects, zero subjects, or `name != "changeset"` each raise `ValidationError`. |
| `AC-F01-120` | `generate_json_schema("0.1")` output validates `statement-valid` and rejects every `statement-invalid-schema-*`; runtime model validation rejects both every schema-invalid vector and every `statement-invalid-semantic-*` vector. The subject/predicate digest-mismatch semantic vector is accepted by JSON Schema and rejected with `ERR-BUILD-203` at runtime. Any unsupported version raises `ERR-BUILD-205`. |
| `AC-F01-130` | `just schema` produces no diff on a clean tree; a manual schema edit makes CI fail. |
| `AC-F01-140` | import-linter reports zero violations for the `attest-core` contract. |
| `AC-F01-150` | Every attest-defined error class exposes non-empty `code`, `message`, `remediation`; coded model-validation failures retain the underlying `BuildError` in the Pydantic error context. |
| `AC-F01-160` | Every vector directory in `SPEC-001 §12` is collected and passes. |
| `AC-F01-170` | `Authorship(mode="unknown", claims=[], claims_present=False)` preserves `mode == "unknown"`; omitting `mode` raises `ValidationError`, and no construction path defaults it to `human-authored`. |
| `AC-F01-180` | Raw path bytes containing valid multibyte UTF-8, `%`, and `0xFF` round-trip through canonical path encoding, model validation, and RFC 8785 canonicalisation; malformed or non-canonical encodings are rejected. |

## 7. Property-based tests (required)

| Property | Statement |
|---|---|
| Canonicalisation determinism | For any valid JSON value, `canonicalize(v) == canonicalize(json.loads(canonicalize(v)))` |
| Digest stability under entry permutation | Shuffling the input entry list **MUST NOT** change the digest |
| Digest sensitivity | Changing any single field of any entry **MUST** change the digest |
| Alias round-trip | For any generated model instance, `validate(dump(m)) == m` |

## 8. Error codes

| Code | Condition | Remediation hint |
|---|---|---|
| `ERR-BUILD-201` | Non-canonicalisable value (float, NaN, infinity) | Use integers; report as a bug if from a collector |
| `ERR-BUILD-202` | Malformed git OID | Supply full 40-character OIDs |
| `ERR-BUILD-203` | Subject/predicate digest mismatch | Rebuild the Statement from a single ChangeSetRecord |
| `ERR-BUILD-204` | Unknown enum value from external input | Upgrade attest or file an issue for the new value |
| `ERR-BUILD-205` | Unsupported predicate schema version | Use predicate version `0.1` or upgrade attest |

## 9. Out of scope

- Reading any repository (F-02)
- Reading claim files (F-03)
- Any network call (F-04, F-06)
- Signing or verification (F-06, F-08)

## 10. Definition of Done

- [ ] All `REQ-F01-*` implemented, all `AC-F01-*` green
- [ ] All four properties in §7 implemented in Hypothesis
- [ ] All `SPEC-001 §12` vectors present and passing
- [ ] Coverage ≥ 95% on `attest-core`
- [ ] Cross-cutting obligations `X-01`…`X-10` satisfied
- [ ] Generated schema committed and drift check green
- [ ] `mutmut` run on `digest.py` and `canonical.py`; surviving mutants reviewed and either killed or justified in writing
