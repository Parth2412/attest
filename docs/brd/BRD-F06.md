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
class Signer(Protocol):
    def sign(self, statement: Statement) -> Bundle: ...

@dataclass(frozen=True)
class Bundle:
    raw: bytes                    # serialised Sigstore bundle
    certificate_identity: str
    certificate_issuer: str
    log_index: int | None
    log_integrated_time: datetime | None
```

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
| `REQ-F06-090` | Long-lived key signing **MAY** be supported for air-gapped use but **MUST** be off by default and **MUST** be flagged in verification output. |
| `REQ-F06-100` | After signing, the full `F-08` verification pipeline **MUST** be run against the produced bundle before reporting success (`ADR-005`). |
| `REQ-F06-110` | The certificate identity and issuer actually obtained **MUST** be reported in output so the user can configure verification constraints. |
| `REQ-F06-120` | Network operations **MUST** have explicit timeouts and bounded retries; exhaustion raises `ERR-SIGN-304`. |
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
| `AC-F06-090` | Long-lived key mode requires an explicit flag and sets a flag visible in verification output. |
| `AC-F06-100` | Corrupting the bundle post-signing but pre-verification causes the run to fail rather than report success. |
| `AC-F06-110` | The reported identity string is suitable for pasting into a verification constraint. |
| `AC-F06-120` | A hanging endpoint fixture triggers timeout and `ERR-SIGN-304`. |
| `AC-F06-130` | A full-suite scan of captured output contains no token-like strings. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-SIGN-301` | No ambient signing identity | Add `permissions: id-token: write` to the workflow |
| `ERR-SIGN-302` | Fulcio certificate request failed | Check network and OIDC audience configuration |
| `ERR-SIGN-303` | Transparency log submission failed | Retry; do not disable log submission |
| `ERR-SIGN-304` | Network timeout after retries | Check egress and proxy configuration |
| `ERR-SIGN-305` | Self-verification after signing failed | Report as a bug; do not use the produced bundle |

## 8. Out of scope

Storage of the bundle (F-07), policy decisions (F-09), key management for long-lived keys beyond
basic file loading.

## 9. Definition of Done

- [ ] All `REQ-F06-*` implemented, all `AC-F06-*` green
- [ ] End-to-end signing against Sigstore **staging** in CI, then verified
- [ ] `Signer` protocol isolates the library; swapping the implementation touches one module
- [ ] No direct `securesystemslib` import or hand-written PAE/envelope assembly exists
- [ ] Guard test prevents production-endpoint use in tests
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
