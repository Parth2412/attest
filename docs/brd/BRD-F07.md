# BRD-F07 — Storage and Retrieval

| Field | Value |
|---|---|
| Document ID | `BRD-F07` |
| Feature | `F-07` |
| Milestone | M2 |
| Package | `attest-store` |
| Depends on | `F-01`, `F-06` |
| Status | Ready when F-01, F-06 are Done · no open question |

---

## 1. Purpose

Persist bundles so they can be found later by ChangeSet Digest, without requiring a server. The
default backend keeps evidence inside the repository itself, which is what makes v1.0 fully
decentralised.

## 2. Scope trace

`SCOPE-06`. Implements `SPEC-001 §9`.

## 3. Dependencies

`F-01`, `F-06`. `OQ-02` is **closed** by `ADR-014`: storage uses a dedicated git ref namespace,
one ref per attestation. Git notes are not used for storage.

## 4. Data contract

```python
class AttestationStore(Protocol):
    def put(self, digest: str, bundle: bytes) -> StoreRef: ...
    def get(self, digest: str) -> list[bytes]: ...
    def list(self, since: datetime | None = None) -> Iterator[StoreRef]: ...
```

Backends: `GitRefStore` (default), `FilesystemStore`, `OciStore`.

`pygit2` is an optional package extra. `GitRefStore` **MUST** remain fully operational through the
Git CLI when the extra is absent, and both native and subprocess implementations **MUST** satisfy
the same externally observable storage contract (`ADR-034`).

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F07-010` | The store **MUST** support multiple bundles per digest; `get` returns all. |
| `REQ-F07-020` | `put` **MUST** be idempotent for identical bundle bytes: storing twice yields one entry. |
| `REQ-F07-030` | `GitRefStore` **MUST** write one ref per attestation under `refs/attestations/<digest>`, suffixed `/<log-index>` when a digest has more than one, and **MUST NOT** modify branches, tags, notes, or working tree state. |
| `REQ-F07-040` | Pushing attestation refs **MUST** be an explicit operation, never implicit in `put`. |
| `REQ-F07-050` | A push rejected by the remote **MUST** raise `ERR-STORE-401` with remediation naming the required ref permission. |
| `REQ-F07-060` | `FilesystemStore` **MUST** name files `<digest>.sigstore.json`, with a numeric suffix on collision after content comparison. |
| `REQ-F07-070` | Retrieval **MUST NOT** verify; verification is `F-08`'s responsibility and **MUST** remain separately invocable. |
| `REQ-F07-080` | Storage failure **MUST NOT** discard the bundle: it **MUST** be written to a local fallback path and the path reported. |
| `REQ-F07-090` | `OciStore` **MUST** use the referrers mechanism with the artifact digest as subject. |
| `REQ-F07-100` | Concurrent `put` for the same digest from parallel CI jobs **MUST NOT** corrupt the store; last-writer-wins is acceptable, corruption is not. |
| `REQ-F07-110` | No backend **MUST** require write access to anything outside its configured location. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F07-010` | Two distinct bundles for one digest both return from `get`. |
| `AC-F07-020` | Identical bytes stored twice yield one entry. |
| `AC-F07-030` | After `put`, `git status` is clean, no branch or tag moved, no notes ref written, and the ref exists at `refs/attestations/<digest>`. |
| `AC-F07-040` | `put` alone performs no network operation, asserted by a no-egress test. |
| `AC-F07-050` | A rejected push raises `ERR-STORE-401` naming the ref permission. |
| `AC-F07-060` | Two different bundles for one digest produce two files without overwriting. |
| `AC-F07-070` | `get` returns an invalid bundle without error; verification is what rejects it. |
| `AC-F07-080` | Simulated store failure still writes the bundle locally and prints the path. |
| `AC-F07-090` | An OCI fixture registry shows the attestation as a referrer of the subject digest. |
| `AC-F07-100` | Ten concurrent puts leave a readable, uncorrupted store. |
| `AC-F07-110` | No writes occur outside the configured directory or ref namespace during the suite. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-STORE-401` | Ref push rejected | Grant `contents: write` for the attestation ref namespace |
| `ERR-STORE-402` | Backend unreachable | Check registry or remote configuration |
| `ERR-STORE-403` | Digest not found | Confirm the attestation was pushed |
| `ERR-STORE-404` | Store corrupted or unreadable | Use the local fallback path reported at write time |

## 8. Out of scope

Hosted store (`OOS-01`, v1.1), retention policy enforcement, cross-repository search.

## 9. Definition of Done

- [ ] All `REQ-F07-*` implemented, all `AC-F07-*` green
- [ ] All three backends pass the identical store conformance suite
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
