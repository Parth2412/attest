# BRD-F08 — Verification

| Field | Value |
|---|---|
| Document ID | `BRD-F08` |
| Feature | `F-08` |
| Milestone | M1 |
| Package | `attest-sign` |
| Depends on | `F-01`, `F-06` |
| Status | In progress · contract clarified by `ADR-038` |

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
class VerificationEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"

@dataclass(frozen=True)
class ServiceTrustRoot:
    environment: VerificationEnvironment
    offline: bool                # explicit: False permits a TUF refresh

@dataclass(frozen=True)
class SuppliedTrustRoot:
    client_trust_config_json: str

type TrustRootSource = ServiceTrustRoot | SuppliedTrustRoot

@dataclass(frozen=True)
class IdentityConstraint:
    identity_pattern: str        # exact or the bounded glob grammar below
    issuer: str                  # exact match

@dataclass(frozen=True)
class RepositoryConstraint:
    path: Path
    base_revision: str           # caller-selected diff base
    head_revision: str           # caller-selected diff head

@dataclass(frozen=True)
class CheckOutcome:
    name: Literal[
        "bundle-structure",
        "sigstore-dsse",
        "statement-payload",
        "structural-schema",
        "semantic-model",
        "changeset-recomputation",
    ]
    result: Literal["passed", "failed", "skipped"]
    code: str | None              # populated only when result == "failed"

@dataclass(frozen=True)
class VerificationResult:
    status: Literal["verified", "verified-untrusted-environment", "failed"]
    checks: list[CheckOutcome]     # one per SPEC-001 §8 step, in order
    statement: Statement | None
    failure_code: str | None

def verify(
    bundle: bytes,
    constraint: IdentityConstraint,
    trust_root: TrustRootSource,
    repository: RepositoryConstraint | None = None,
) -> VerificationResult: ...
```

`constraint` and `trust_root` are **required and positional**. Neither is optional and neither has
a default. An omitted identity constraint is rejected before verification as a usage/configuration
error; it is never a successful verification result (`ADR-004`, `ADR-038`).

Checks are appended in the table order above. A completed check records `passed`; the first failed
check records `failed` and its code, and later checks are absent. A successful call records all six
checks; `changeset-recomputation` is `skipped` when `repository` is `None`. Passed and skipped
checks have `code is None`.

An identity without `*` is exact. A bounded glob is permitted only for a GitHub Actions workflow
URI of the form `https://github.com/<owner>/<repository>/.github/workflows/<file>@refs/<ref>`.
Everything before `@refs/` is exact and contains no wildcard. In the ref only, `*` matches one or
more characters other than `/`; matching is case-sensitive and anchored to the whole identity.
`**`, `?`, bracket expressions, empty values, and every wildcard outside the ref are invalid and
raise `ERR-VERIFY-011` when `IdentityConstraint` is constructed. Exact non-GitHub identities remain
permitted. A glob match is resolved against the certificate's URI SAN and that one exact SAN plus
the exact issuer is supplied to Sigstore's public `Identity` policy. Zero or multiple matches fail
closed with `ERR-VERIFY-013`.

`ServiceTrustRoot.offline` is deliberately required. `True` uses only the selected environment's
packaged or cached TUF material; `False` explicitly permits Sigstore's bounded TUF refresh.
`SuppliedTrustRoot` uses Sigstore's public client-trust-configuration JSON parser and performs no
network operation. A verifier never tries production and staging roots in sequence.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F08-010` | Verification **MUST** execute the six checks of `SPEC-001 §8` in the specified order and **MUST** abort at the first failure. Sigstore-native `verify_dsse` **MUST** perform the atomic cryptographic check; private Sigstore methods and exception-text classification are forbidden. Trust-root initialization is part of check 2: unavailable trust material fails that check with `ERR-VERIFY-012` before `verify_dsse`; every `VerificationError` from `verify_dsse` maps to `ERR-VERIFY-013`. |
| `REQ-F08-020` | Each check **MUST** produce a `CheckOutcome` recording its name, result, and code, so the sequence is inspectable in output. |
| `REQ-F08-030` | Sigstore-native verification **MUST** establish certificate validity using verified bundle time evidence, not the current wall clock. |
| `REQ-F08-040` | **An identity constraint MUST be supplied to the Sigstore `Identity` policy. There MUST NOT be a default that accepts any identity, and there MUST NOT be any flag, environment variable, or configuration key that skips the policy while returning `status == "verified"`.** |
| `REQ-F08-050` | Identity patterns **MUST** use the exact or bounded, case-sensitive, whole-string grammar in §4. Invalid or unbounded patterns **MUST** be rejected when `IdentityConstraint` is constructed with `ERR-VERIFY-011`. |
| `REQ-F08-060` | Issuer **MUST** be matched exactly; no pattern matching on issuer. |
| `REQ-F08-070` | Transparency log inclusion **MUST** be verified by `verify_dsse` from the inclusion proof embedded in the bundle, without contacting the log. Querying the log **MUST NOT** be offered as a substitute, and no option may make verification depend on log reachability. A bundle without an embedded proof **MUST** fail `ERR-VERIFY-013`. |
| `REQ-F08-080` | Verification **MUST** be possible offline given a bundle and packaged, cached, or explicitly supplied trust material. Environment and offline/refresh behaviour **MUST** be explicit; network availability **MUST NOT** be required, and roots from different environments **MUST NOT** be tried automatically. |
| `REQ-F08-090` | Unknown `predicateType` **MUST** fail with `ERR-VERIFY-007`; best-effort parsing is forbidden. |
| `REQ-F08-100` | Structural schema validation **MUST** use the schema for the predicate version in the Statement, not the newest known schema. It **MUST** run before Pydantic semantic model construction (`ADR-021`). |
| `REQ-F08-110` | When a `RepositoryConstraint` is supplied, an independent read-only Git CLI path **MUST** resolve its caller-selected base and head revisions, recompute `CSD-1`, and compare it with the attested digest. It **MUST** ignore the working tree, disable replacement objects, hooks, external diff/text conversion, and rename/copy detection, and bound every subprocess call. An unavailable repository, unresolved revision, failed recomputation, or mismatch is `ERR-VERIFY-010`. |
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
| `AC-F08-050` | `identity_pattern = "*"`, a wildcard before `@refs/`, `**`, `?`, and bracket expressions are rejected at construction with `ERR-VERIFY-011`; an exact identity and a ref-segment glob are anchored and accepted. |
| `AC-F08-060` | A near-miss issuer string fails. |
| `AC-F08-070` | A tampered inclusion proof fails with `ERR-VERIFY-013`; a bundle with the proof removed also fails; both fail with all network access blocked. |
| `AC-F08-080` | Verification succeeds with all network access blocked using both selected packaged/cached trust material and a supplied client trust configuration; a staging bundle fails under the production root. |
| `AC-F08-090` | A bundle with `predicateType` `…/v9.9` fails with `ERR-VERIFY-007`. |
| `AC-F08-100` | A v0.1 Statement selects the v0.1 schema by exact predicate URI while the test registry also contains an incompatible test-only v0.2 sentinel; a subject/predicate digest-mismatch fixture passes the v0.1 schema, then fails semantic step 5 with `ERR-VERIFY-009`. |
| `AC-F08-110` | After signing, committing a one-file change and verifying against the original base plus the caller-selected new head revision causes `ERR-VERIFY-010`; an uncommitted working-tree edit is ignored. |
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
| Valid bundle checked against a different caller-selected ChangeSet | `ERR-VERIFY-010` |
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
| `ERR-VERIFY-011` | Invalid or unbounded identity pattern | Use an exact identity or anchor a single-segment glob to a GitHub workflow ref |
| `ERR-VERIFY-012` | Selected trust material is unavailable or invalid | Explicitly refresh the selected environment or supply a valid client trust configuration |
| `ERR-VERIFY-013` | Sigstore-native cryptographic verification failed | Reject the bundle; inspect the sanitised diagnostic and signer/trust configuration |

## 9. Out of scope

Policy decisions (F-09). Verification answers "is this attestation genuine"; policy answers
"is what it says acceptable". Keeping these separate is deliberate and **MUST NOT** be merged.

## 10. Definition of Done

- [ ] All `REQ-F08-*` implemented, all `AC-F08-*` green
- [ ] Full adversarial suite (§7) implemented and green
- [ ] Offline verification demonstrated in CI with network disabled
- [ ] Independent human review of the verification order by someone other than the author
- [ ] Coverage ≥ 95% on the verifier module specifically
- [ ] Cross-cutting obligations satisfied
