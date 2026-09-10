# BRD-F08 — Verification

| Field | Value |
|---|---|
| Document ID | `BRD-F08` |
| Feature | `F-08` |
| Milestone | M1 |
| Package | `attest-sign` |
| Depends on | `F-01`, `F-06` |
| Status | Ready to build once F-06 Done |

---

## 1. Purpose

Determine whether an attestation is trustworthy. This is the feature the entire product's
credibility rests on. An auditor running `attest verify` on a bundle is the moment of truth; if
verification is weak or bypassable, nothing else matters.

**The single most important requirement in this document is `REQ-F08-040`.**

## 2. Scope trace

`SCOPE-07`. Implements `SPEC-001 §8`, §8.1, §8.2.

## 3. Dependencies

`F-01`, `F-06`. `OQ-03` is **closed** by `ADR-015`: the inclusion proof is embedded at signing
time and verified offline from bundle contents alone. `CH-02` is closed; `ADR-020` requires the
Sigstore-native atomic cryptographic verification boundary.

## 4. Data contract

```python
@dataclass(frozen=True)
class IdentityConstraint:
    identity_pattern: str     # exact or bounded glob
    issuer: str               # exact match

@dataclass(frozen=True)
class VerificationResult:
    status: Literal["verified", "verified-untrusted-environment", "failed"]
    checks: list[CheckOutcome]     # one per SPEC-001 §8 step, in order
    statement: Statement | None
    failure_code: str | None

def verify(
    bundle: bytes,
    constraint: IdentityConstraint,
    repo: Path | None = None,
) -> VerificationResult: ...
```

Note the signature: `constraint` is **required and positional**. It is not optional and has no
default. The type system enforces `ADR-004`.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F08-010` | Verification **MUST** execute the six checks of `SPEC-001 §8` in the specified order and **MUST** abort at the first failure. Sigstore-native `verify_dsse` **MUST** perform the atomic cryptographic check; private Sigstore methods and exception-text classification are forbidden. |
| `REQ-F08-020` | Each check **MUST** produce a `CheckOutcome` recording its name, result, and code, so the sequence is inspectable in output. |
| `REQ-F08-030` | Sigstore-native verification **MUST** establish certificate validity using verified bundle time evidence, not the current wall clock. |
| `REQ-F08-040` | **An identity constraint MUST be supplied to the Sigstore `Identity` policy. There MUST NOT be a default that accepts any identity, and there MUST NOT be any flag, environment variable, or configuration key that skips the policy while returning `status == "verified"`.** |
| `REQ-F08-050` | Identity patterns **MUST** be anchored. Unbounded wildcards that match any identity **MUST** be rejected at configuration parse time with `ERR-VERIFY-011`. |
| `REQ-F08-060` | Issuer **MUST** be matched exactly; no pattern matching on issuer. |
| `REQ-F08-070` | Transparency log inclusion **MUST** be verified by `verify_dsse` from the inclusion proof embedded in the bundle, without contacting the log. Querying the log **MUST NOT** be offered as a substitute, and no option may make verification depend on log reachability. A bundle without an embedded proof **MUST** fail `ERR-VERIFY-013`. |
| `REQ-F08-080` | Verification **MUST** be possible offline given a bundle and a cached trust root; network availability **MUST NOT** be required. |
| `REQ-F08-090` | Unknown `predicateType` **MUST** fail with `ERR-VERIFY-007`; best-effort parsing is forbidden. |
| `REQ-F08-100` | Structural schema validation **MUST** use the schema for the predicate version in the Statement, not the newest known schema. It **MUST** run before Pydantic semantic model construction (`ADR-021`). |
| `REQ-F08-110` | When a repository is supplied, `CSD-1` **MUST** be recomputed and compared; mismatch is `ERR-VERIFY-010`. |
| `REQ-F08-120` | `collection.environment.trusted == false` **MUST** yield `verified-untrusted-environment`, never plain `verified`. |
| `REQ-F08-130` | Verification code **MUST NOT** share a code path with signing beyond `attest-core` pure functions. |
| `REQ-F08-140` | Failure output **MUST** name the failing check and its code, and **MUST NOT** reveal internal cryptographic material. |
| `REQ-F08-150` | attest **MUST** verify every predicate version it has ever emitted; verification code for old versions **MUST NOT** be removed. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F08-010` | A bundle failing atomic cryptographic step 2 never reaches payload step 3, asserted by the `checks` list length. |
| `AC-F08-020` | Output lists all attempted checks with individual outcomes. |
| `AC-F08-030` | A bundle signed with a since-expired certificate still verifies when the log timestamp falls in the validity window. |
| `AC-F08-040` | **Static analysis test:** a test greps the entire codebase and CLI surface for any bypass of the identity check and fails if one exists. Additionally, a bundle signed by a different identity fails closed with `ERR-VERIFY-013` under every configuration permutation exercised. |
| `AC-F08-050` | `identity_pattern = "*"` is rejected at parse time with `ERR-VERIFY-011`. |
| `AC-F08-060` | A near-miss issuer string fails. |
| `AC-F08-070` | A tampered inclusion proof fails with `ERR-VERIFY-013`; a bundle with the proof removed also fails; both fail with all network access blocked. |
| `AC-F08-080` | Verification succeeds with all network access blocked, given a cached trust root. |
| `AC-F08-090` | A bundle with `predicateType` `…/v9.9` fails with `ERR-VERIFY-007`. |
| `AC-F08-100` | A v0.1 Statement uses the v0.1 structural schema even when v0.2 exists; a subject/predicate digest-mismatch vector passes that schema, then fails semantic step 5 with `ERR-VERIFY-009`. |
| `AC-F08-110` | Modifying one file in the repo after signing causes `ERR-VERIFY-010`. |
| `AC-F08-120` | A locally-produced bundle yields `verified-untrusted-environment`. |
| `AC-F08-130` | Import analysis shows no shared non-core module between signer and verifier. |
| `AC-F08-140` | Failure messages contain a code and no key material. |
| `AC-F08-150` | A stored historical bundle from the earliest supported version still verifies. |

## 7. Adversarial test suite (required)

`F-08` **MUST** ship a dedicated negative suite. Each case **MUST** fail verification:

| Case | Expected |
|---|---|
| Payload modified after signing | `ERR-VERIFY-013` |
| Signature copied from a different bundle | `ERR-VERIFY-013` |
| Valid signature, attacker-controlled identity | `ERR-VERIFY-013` |
| Valid bundle replayed against a different ChangeSet | `ERR-VERIFY-009` or `ERR-VERIFY-010` |
| Subject digest edited to match a different change | `ERR-VERIFY-013` (cryptographic verification fails) |
| Leaf certificate chaining to an untrusted root | `ERR-VERIFY-013` |
| Inclusion proof removed | `ERR-VERIFY-013` |
| Predicate field added beyond the schema | `ERR-VERIFY-008` |
| Truncated bundle | `ERR-VERIFY-001` |
| Bundle with valid signature but `trusted: false` | `verified-untrusted-environment` |

## 8. Error codes

Per `SPEC-001 §8`, plus:

| Code | Condition | Remediation |
|---|---|---|
| `ERR-VERIFY-011` | Unbounded identity pattern | Anchor the pattern to your workflow ref |
| `ERR-VERIFY-012` | Trust root unavailable and no cache | Run once online, or supply an offline trust bundle |
| `ERR-VERIFY-013` | Sigstore-native cryptographic verification failed | Reject the bundle; inspect the sanitised diagnostic and signer/trust configuration |

## 9. Out of scope

Policy decisions (F-09). Verification answers "is this attestation genuine"; policy answers
"is what it says acceptable". Keeping these separate is deliberate and **MUST NOT** be merged.

## 10. Definition of Done

- [ ] All `REQ-F08-*` implemented, all `AC-F08-*` green
- [ ] Full adversarial suite (§7) implemented and green
- [ ] Offline verification demonstrated in CI with network disabled
- [ ] External review of the verification order by someone other than the author
- [ ] Coverage ≥ 95% on the verifier module specifically
- [ ] Cross-cutting obligations satisfied
