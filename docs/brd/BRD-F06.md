# BRD-F06 — Sigstore Signing

| Field | Value |
|---|---|
| Document ID | `BRD-F06` |
| Feature | `F-06` |
| Milestone | M1 |
| Package | `attest-sign` |
| Depends on | `F-01`, `F-05` |
| Status | Ready when F-01 and F-05 are Done · `CH-02` closed |

---

## 1. Purpose

Wrap a Statement in a DSSE envelope, sign it keylessly using an ambient CI workload identity via
Fulcio, record it in the Rekor transparency log, and emit a Sigstore bundle.

> **Library discipline.** Do **not** write code against remembered `sigstore-python` APIs. Install
> the pinned version, read its actual surface, and wrap it behind the internal `Signer` protocol
> so that upstream changes have a one-module blast radius. See `AGENTS.md §4`.

## 2. Scope trace

`SCOPE-05`. Implements `SPEC-001 §7`.

## 3. Dependencies

`F-01`, `F-05`. `CH-02` is closed by executed conformance evidence and `ADR-020`/`ADR-021`.
Implementation **MUST** retain the validated Sigstore-native boundary and exact locked version.

## 4. Data contract

```python
class SigningEnvironment(StrEnum):
    PRODUCTION = "production"
    STAGING = "staging"


class Signer(Protocol):
    def sign(self, statement: Statement) -> Bundle: ...


class SigstoreSigner:
    def __init__(
        self,
        *,
        environment: SigningEnvironment,
        attempt_timeout: timedelta = timedelta(seconds=120),
    ) -> None: ...


@dataclass(frozen=True)
class Bundle:
    raw: bytes                    # serialised Sigstore bundle
    environment: SigningEnvironment
    certificate_identity: str
    certificate_issuer: str       # effective workload OIDC issuer, not the Fulcio CA DN
    log_index: int
    log_integrated_time: datetime | None
```

The concrete Sigstore adapter requires `environment` at construction and has no environment
default. `attempt_timeout` must be positive. The protocol intentionally exposes neither
configuration nor credential inputs: the implementation obtains credentials through ambient
detection.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F06-010` | The payload supplied to `sigstore.dsse.Statement` **MUST** be the exact RFC 8785 canonicalised Statement bytes; DSSE `payloadType` **MUST** be `application/vnd.in-toto+json`. |
| `REQ-F06-020` | Signing **MUST** use Sigstore's public `sign_dsse` operation, which owns PAE, envelope construction, signing, Rekor submission, and bundle construction. PAE **MUST NOT** be hand-constructed, and `securesystemslib` **MUST NOT** be imported directly (`ADR-020`). |
| `REQ-F06-030` | Keyless signing via ambient OIDC **MUST** be the default; ambient credential detection **MUST** be used rather than manual token handling. |
| `REQ-F06-040` | If no ambient identity is available, the tool **MUST** raise `ERR-SIGN-301` naming the missing CI permission (`id-token: write`), and **MUST NOT** fall back to interactive browser flow in a non-interactive environment. |
| `REQ-F06-050` | The bundle **MUST** include the DSSE envelope, leaf signing certificate, transparency-log entry with inclusion proof, and any timestamp verification material emitted by Sigstore. The configured trusted root supplies the certificate chain; an embedded chain **MUST NOT** be required. |
| `REQ-F06-060` | If Rekor submission fails, signing **MUST** fail with `ERR-SIGN-303`. A bundle without a log entry **MUST NOT** be emitted as successful in the default configuration. |
| `REQ-F06-070` | The signing environment (production vs. staging) **MUST** be explicitly configured and reported. Tests **MUST** target staging. |
| `REQ-F06-080` | Private key material **MUST** be ephemeral and **MUST NOT** be written to disk. One signing run **MUST** use one Sigstore signer context with default in-memory key retention; `cache=False` **MUST NOT** be used with `sigstore` 4.5.0. |
| `REQ-F06-090` | v0.1 **MUST** support keyless ambient-OIDC signing only. It **MUST NOT** expose a long-lived key, key-path, or manual-token input. Long-lived key support requires a future ADR and feature contract. |
| `REQ-F06-100` | Before returning, the signer **MUST** reparse the serialized bundle through Sigstore and validate that it is a DSSE bundle with the material required by `REQ-F06-050`; failure raises `ERR-SIGN-305`. Full independent F-08 self-verification remains mandatory at the `attest run` composition root before overall success (`ADR-005`, `ADR-037`). |
| `REQ-F06-110` | The identity and effective OIDC issuer obtained from ambient detection **MUST** be validated against the actual leaf certificate with Sigstore's public identity policy and reported in the `Bundle` result so the user can configure verification constraints. The X.509 CA issuer distinguished name is not this value. |
| `REQ-F06-120` | Every signing attempt **MUST** execute in an isolated child process with a positive hard deadline, defaulting to 120 seconds. The parent **MUST** terminate an expired worker. A pre-Rekor timeout permits at most one fresh attempt; once Rekor submission begins, the operation **MUST NOT** be retried. Deadline exhaustion raises `ERR-SIGN-304` (`ADR-037`). |
| `REQ-F06-130` | No secret, token, or key material **MUST** appear in logs, diagnostics, or error messages. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F06-010` | Sigstore-native `verify_dsse` returns payload bytes identical to `canonicalize(statement)` and payload type `application/vnd.in-toto+json`. |
| `AC-F06-020` | Signing exercises public `sign_dsse`; no hand-written PAE, manual DSSE envelope assembly, or direct `securesystemslib` import exists in the codebase. |
| `AC-F06-030` | In a simulated CI environment with an OIDC token, signing succeeds without interactive input. |
| `AC-F06-040` | Without an ambient identity in a non-TTY environment, `ERR-SIGN-301` is raised and its remediation names `id-token: write`. |
| `AC-F06-050` | The emitted bundle parses and contains a DSSE envelope, leaf signing certificate, transparency-log entry, complete inclusion proof, and available timestamp material; offline verification succeeds with the configured cached trust root. |
| `AC-F06-060` | A simulated Rekor failure yields `ERR-SIGN-303` and no bundle file written. |
| `AC-F06-070` | The test suite signs only against staging; a guard test fails if a production endpoint is configured in tests. |
| `AC-F06-080` | One signer context completes a staging signing run, and filesystem-write monitoring in a temporary home proves no private key material is persisted. |
| `AC-F06-090` | The public adapter and protocol expose no long-lived key, key-path, or manual-token input, and no long-lived-key implementation path exists. |
| `AC-F06-100` | A malformed serialized result or a result missing the DSSE envelope, leaf certificate, log entry, complete inclusion proof, or both supported signed-time sources fails with `ERR-SIGN-305` rather than returning a `Bundle`. |
| `AC-F06-110` | The reported identity string is suitable for pasting into a verification constraint. |
| `AC-F06-120` | A hanging worker is terminated and yields `ERR-SIGN-304`; a pre-Rekor timeout is attempted no more than twice, and a Rekor-stage timeout is attempted exactly once. |
| `AC-F06-130` | A full-suite scan of captured output contains no token-like strings. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-SIGN-301` | No ambient signing identity | Add `permissions: id-token: write` to the workflow |
| `ERR-SIGN-302` | Fulcio certificate request failed | Check network and OIDC audience configuration |
| `ERR-SIGN-303` | Transparency log submission failed | Retry; do not disable log submission |
| `ERR-SIGN-304` | Signing attempt exceeded its hard deadline | Check egress and proxy configuration |
| `ERR-SIGN-305` | Produced bundle failed required-material validation | Report as a bug; do not use the produced bundle |
| `ERR-SIGN-306` | Sigstore trust root or signing configuration could not be initialized | Check the selected environment, trusted metadata cache, and network access |

## 8. Out of scope

Storage of the bundle (F-07), the independent verification pipeline (F-08), policy decisions
(F-09), CLI composition of post-sign verification (F-10), and all long-lived-key support.

## 9. Definition of Done

- [x] All `REQ-F06-*` implemented, all `AC-F06-*` green
- [x] End-to-end signing against Sigstore **staging** in CI, then verified with Sigstore's native
      DSSE verifier; the full attest verification pipeline is completed by F-08/F-10
- [x] `Signer` protocol isolates the library; swapping the implementation touches one module
- [x] No direct `securesystemslib` import or hand-written PAE/envelope assembly exists
- [x] Guard test prevents production-endpoint use in tests
- [x] Coverage ≥ 90% (`attest-sign`: 95%)
- [x] Cross-cutting obligations satisfied
