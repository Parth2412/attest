# BRD-F07 — Storage and Retrieval

| Field | Value |
|---|---|
| Document ID | `BRD-F07` |
| Feature | `F-07` |
| Milestone | M2 |
| Package | `attest-store` |
| Depends on | `F-01`, `F-06` |
| Status | Ready when F-01, F-06 are Done · governed by `ADR-043` |

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
@dataclass(frozen=True, slots=True)
class StoreRef:
    backend: Literal["git-ref", "filesystem", "oci"]
    digest: str
    bundle_digest: str
    location: str
    stored_at: datetime

class AttestationStore(Protocol):
    def put(self, digest: str, bundle: bytes) -> StoreRef: ...
    def get(self, digest: str) -> list[bytes]: ...
    def list(self, since: datetime | None = None) -> Iterator[StoreRef]: ...
```

Backends: `GitRefStore` (default), `FilesystemStore`, `OciStore`.

`digest` and `StoreRef.digest` are exact 64-character lowercase hexadecimal ChangeSet Digests.
`bundle_digest` is the exact 64-character lowercase SHA-256 of the stored Bundle bytes. `location`
is an opaque backend locator and **MUST NOT** contain credentials. `stored_at` is an injected-clock
storage timestamp, persisted as RFC 3339 UTC with `Z`, second precision; it is not evidence time.
The closed store-metadata object is RFC 8785 canonical JSON with exactly `version` (integer `1`),
`changeSetDigest`, `bundleDigest`, `size`, and `storedAt`. Filesystem companion metadata is named
`<bundle-filename>.store.json`; a Git tag message is the same canonical bytes followed by LF.

`get` returns exact Bundle bytes ordered by their SHA-256 digest. It raises `ERR-STORE-403` when no
entry exists. `list` is deterministic by `(stored_at, digest, bundle_digest, location)`. `since`
is inclusive, **MUST** be timezone-aware, and is normalised to UTC. Invalid digest, bundle,
timestamp, backend, repository, ref, subject, or timeout inputs raise `ERR-STORE-405` before I/O.
Retrieval validates storage metadata and content hashes but does not parse or verify a Bundle.

The application composes a primary backend with an explicit `FilesystemStore` through
`put_with_fallback(primary, fallback, digest, bundle)`. A primary `StoreError` remains the public
failure, but after a successful fallback write it carries the exact local `fallback_path`. The
storage package never prints. The CLI output layer later renders that path. If the fallback write
also fails, `ERR-STORE-406` is raised with the primary error chained privately.

`GitRefStore.push(reference, remote, fallback)` is the only network operation on the Git-ref
backend. It pushes exactly `reference.location` to the same remote ref without force. On failure,
it preserves the referenced Bundle through the supplied fallback before raising the classified
push error with `fallback_path`.

`pygit2` is an optional package extra. `GitRefStore` **MUST** remain fully operational through the
Git CLI when the extra is absent, and both native and subprocess implementations **MUST** satisfy
the same externally observable storage contract (`ADR-034`). Backend selection is `auto`,
`pygit2`, or `subprocess`; `auto` prefers pygit2 and falls back only when it is unavailable, never
after an operational failure. Git subprocesses have a hard caller-configurable deadline.

`OciStore` is configured with one registry repository and one immutable OCI subject descriptor:
media type, `sha256:<64-lowercase-hex>` manifest digest, and non-negative byte size. The descriptor
is supplied explicitly; a tag is never resolved implicitly. Registry authentication comes only
from an explicitly selected Docker-compatible config path or an injected ORAS client. TLS
verification is the default; plaintext transport is explicit. Every OCI operation has a hard
caller-configurable deadline enforced outside ORAS's unbounded request surface.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F07-010` | The store **MUST** support multiple exact Bundle byte strings per ChangeSet Digest; `get` returns all once each in deterministic Bundle-digest order and raises `ERR-STORE-403` only when none exist. |
| `REQ-F07-020` | `put` **MUST** be content-idempotent: identical Bundle bytes under one ChangeSet Digest yield the same logical entry and exactly one value from `get` and `list`, including after concurrent calls. |
| `REQ-F07-030` | `GitRefStore` **MUST** write one ref per Bundle under `refs/attestations/<digest>`. The first uses that exact ref. Additional refs use `/<log-index>` when a unique non-negative Rekor `logIndex` can be read without verification, `/<log-index>-<bundle-digest>` when that index collides, and `/sha256-<bundle-digest>` when no usable index exists. Refs point to attest metadata tag objects whose targets are exact Bundle blobs. No branch, tag ref, notes ref, index, or working-tree state may change. |
| `REQ-F07-040` | `GitRefStore.put` **MUST** perform no network operation. Pushing one returned attestation ref is an explicit, separately invoked, non-force operation. |
| `REQ-F07-050` | A push rejected for authentication, authorisation, or ref policy **MUST** raise `ERR-STORE-401` with remediation naming `contents: write` for `refs/attestations/*`; reachability and deadline failures raise `ERR-STORE-402`. Diagnostics **MUST NOT** expose credentials or raw remote output. |
| `REQ-F07-060` | `FilesystemStore` **MUST** write exact Bundle bytes as `<digest>.sigstore.json`, then `<digest>.1.sigstore.json`, `<digest>.2.sigstore.json`, and so on after content comparison. Each Bundle file has closed, hash-bound `<bundle-filename>.store.json` metadata in the same configured directory. Publication is atomic to cooperating operations and never overwrites an existing entry. |
| `REQ-F07-070` | Retrieval **MUST NOT** parse or verify Bundle semantics, signatures, identities, or transparency evidence. It validates only store metadata, descriptor hashes, sizes, and readability; an invalid but uncorrupted Bundle is returned unchanged for F-08 to reject. |
| `REQ-F07-080` | Production storage composition **MUST** use an explicitly configured local `FilesystemStore` fallback. When a primary write or Git push fails and fallback succeeds, the original coded failure **MUST** report the exact fallback path. If fallback also fails, `ERR-STORE-406` **MUST** report that no durable copy was made. |
| `REQ-F07-090` | `OciStore` **MUST** attach an OCI image manifest to its configured immutable artifact descriptor through the OCI 1.1 subject/referrers mechanism. The manifest artifact type and sole Bundle layer media type are `application/vnd.dev.sigstore.bundle.v0.3+json`; annotations carry the ChangeSet Digest, Bundle digest, and storage timestamp. Discovery uses the Referrers API, filters all three identifiers, and validates the layer descriptor before returning exact bytes. |
| `REQ-F07-100` | Concurrent `put` operations **MUST** use create-only publication and content comparison. They may leave unreachable Git objects or OCI manifests, but `get` and `list` **MUST** expose every distinct readable Bundle exactly once and **MUST NOT** expose partial content. |
| `REQ-F07-110` | Filesystem and temporary writes **MUST** remain under explicitly configured directories; Git writes **MUST** remain in the configured repository object database and `refs/attestations/`; OCI writes **MUST** remain in the configured registry repository. Symlinks, irregular files, traversal, malformed refs, and descriptor mismatches fail closed without writing outside those locations. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F07-010` | Every backend returns two distinct Bundle byte strings for one digest exactly once and in Bundle-digest order; an absent digest raises `ERR-STORE-403`. |
| `AC-F07-020` | Sequential and concurrent duplicate writes yield one logical `StoreRef`, one listed entry, and one returned Bundle. |
| `AC-F07-030` | Both Git implementations create the exact base and collision refs with hash-bound metadata and Bundle blobs while branch, tag, notes, index, HEAD, and working tree snapshots remain unchanged. |
| `AC-F07-040` | A socket-denial guard proves both Git `put` implementations perform no egress; only an explicit `push` contacts the configured remote. |
| `AC-F07-050` | A fixture remote rejection raises sanitised `ERR-STORE-401`, names `contents: write` and `refs/attestations/*`, and reports the preserved fallback path; unreachable and expired pushes raise `ERR-STORE-402`. |
| `AC-F07-060` | Distinct bytes produce the exact base and `.1` Bundle filenames plus valid metadata; duplicate bytes do not create `.2`; no existing file is overwritten. |
| `AC-F07-070` | Every backend returns deliberately invalid Bundle bytes unchanged, while corrupted metadata, content digest, size, symlink, or unreadable storage raises `ERR-STORE-404`. |
| `AC-F07-080` | A simulated primary failure preserves exact bytes in the configured fallback and exposes its path on the original `StoreError`; a simulated double failure raises `ERR-STORE-406`. |
| `AC-F07-090` | A local OCI 1.1 fixture registry lists the stored manifest from `/referrers/<subject-digest>`, and retrieved subject, media types, annotations, blob digest, size, and bytes match exactly. |
| `AC-F07-100` | Ten process-concurrent puts for identical and distinct bytes leave no partial entry; all distinct Bundles remain readable once through `get` and `list`. |
| `AC-F07-110` | Snapshot and adversarial path tests prove no backend or ORAS staging operation writes outside its configured repository, registry repository, filesystem directory, or staging directory. |

## 7. Error codes

| Code | Condition | Remediation |
|---|---|---|
| `ERR-STORE-401` | Attestation ref push rejected | Grant `contents: write` for `refs/attestations/*` and retry the explicit push |
| `ERR-STORE-402` | Registry or Git remote unreachable or deadline exceeded | Check registry, remote, authentication, proxy, and deadline configuration |
| `ERR-STORE-403` | ChangeSet Digest not found | Confirm the Bundle was stored or fetch the attestation ref namespace |
| `ERR-STORE-404` | Store metadata, content, or configured location corrupted or unreadable | Restore from the reported fallback path or another valid copy |
| `ERR-STORE-405` | Store input or configuration is invalid | Supply a valid digest, UTC time, backend, location, subject, and deadline |
| `ERR-STORE-406` | Primary and local fallback writes both failed | Restore write access to the configured fallback and retry with the retained Bundle bytes |

## 8. Out of scope

Hosted store (`OOS-01`, v1.1), retention policy enforcement, cross-repository search.

## 9. Definition of Done

- [ ] All `REQ-F07-*` implemented, all `AC-F07-*` green
- [ ] All three backends pass the identical store conformance suite
- [ ] Coverage ≥ 90%
- [ ] Cross-cutting obligations satisfied
