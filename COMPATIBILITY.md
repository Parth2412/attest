# attest — Version Compatibility Matrix

| Field | Value |
|---|---|
| Document ID | `COMPAT-001` |
| Version | `1.19.0` |
| Status | Descriptive — **commentary**. Version *policy* is normative in `GLOSS-001 §5` |
| Last updated | 2026-10-26 |

> **What this file is for.** attest publishes several independently-versioned contracts: a
> distribution set, a wire format, a digest algorithm, an exit-code table, and a policy schema.
> They do not move together. This matrix is where their relationship is stated once, so that
> "which version of what verifies which" is never inferred from code.
>
> **Backwards-compatibility rule (NORMATIVE — `GLOSS-001 §5`):** attest **MUST** be able to verify
> every attestation format it has ever emitted, indefinitely. Verification code for old versions is
> never deleted, only marked legacy. Audit evidence that stops verifying is worthless.

---

## 1. Component versions

`Status` values: `planned` (specified, no code), `scaffold` (stub exists, no logic),
`active` (implemented), `deprecated`.

| Component | Distribution | Import name | Version | Runtime | Owning feature(s) | Status |
|---|---|---|---|---|---|---|
| Workspace root | `attest-workspace` | — | 0.0.0 (not published) | Python 3.12+ | — | active |
| Core | `attest-core` | `attest_core` | 0.1.0 | Python 3.12+ | `F-01`, `F-05` | active |
| Collectors | `attest-collect` | `attest_collect` | 0.1.0 | Python 3.12+ | `F-02`, `F-03`, `F-04`, `F-05` | active |
| Signing & verification | `attest-sign` | `attest_sign` | 0.1.1 | Python 3.12+ | `F-06`, `F-08` | active |
| Storage | `attest-store` | `attest_store` | 0.1.2 | Python 3.12+ | `F-07` | active |
| Policy | `attest-policy` | `attest_policy` | 0.1.0 | Python 3.12+ | `F-09` | active |
| Export | `attest-export` | `attest_export` | 0.1.0 | Python 3.12+ | `F-12` | scaffold |
| CLI | `attest-cli` | `attest_cli` | 0.1.5 | Python 3.12+ | `F-10` | active |
| GitHub Action | `Parth2412/attest/action` | — | v1.0.7 / v1 | Container | `F-11` | active |
| Container image | `ghcr.io/parth2412/attest` | — | 0.1.7 | multi-platform Alpine manifest | `F-11` | active |
| Specification | `SPEC-001` | — | 0.1.5 (document) | — | `F-01`, `F-07`, `F-08` | baselined, unpublished |
| Test vectors | `spec/testvectors/` | — | tracks `SPEC-001 §12` | — | `F-01`, `F-02` | active |

F-01 and F-05 are active in `attest-core`; F-02, F-03, F-04, and the F-05 environment adapter are
active in `attest-collect`; F-06 signing and F-08 verification are active in `attest-sign`; F-07
storage is active in `attest-store`; and F-09 policy evaluation is active in `attest-policy`.
F-04 is complete, including the `REQ-F04-150` fail-closed context resolver. F-08 verification and
its `REQ-F08-170` explicitly non-cryptographic inspection operation are complete. F-10's CLI and
F-11's published Action/image are active and F-11 is Done. `ADR-068` completed public store
`0.1.2`, CLI `0.1.5`, image `0.1.7`, immutable Action `v1.0.7`, and reviewed moving `v1`; every
earlier release remains immutable historical evidence. F-12 is Planned and `attest-export`
remains a development scaffold pending `CH-04`.
See `PROJECT_SPECS.md §Current Project Status`.

The GitHub owner is resolved to `parth2412` in the predicate URI (`ADR-013`, `BOOT-001 §16`). The
URI appears in exactly one place in code — `attest_core.constants.PREDICATE_TYPE_V0_1` — and never
as a literal at a call site (`REQ-F05-040`).

---

## 2. Wire-format and contract versions

These version **independently of the distributions above**, and are the versions that matter to
anyone verifying an attestation years from now.

| Contract | Identifier | Current | Scheme | Change rule |
|---|---|---|---|---|
| Predicate type | `https://parth2412.github.io/attest/ai-authorship/v0.1` | v0.1 | `vMAJOR.MINOR` in the URI | **v0.x is explicitly unstable and may change without a MAJOR bump.** Freezes permanently at v1.0; after that any change needs a new MAJOR URI plus permanent verification support for the old one. `ADR-013`, `SPEC-001 §3.1` |
| Digest algorithm | `CSD-1` | `CSD-1` | `CSD-N` | Any change to the algorithm is a new `N`. Old `N` remains verifiable forever. `GLOSS-001 §5` |
| Claim sidecar schema | `schemaVersion` field | `0.1.0` | SemVer | `ARCH-001 §7`, `BRD-F03` |
| Statement type | `https://in-toto.io/Statement/v1` | v1 | upstream | External — in-toto |
| DSSE payload type | `application/vnd.in-toto+json` | — | upstream | External — DSSE |
| Attestation ref namespace | `refs/attestations/<changeset-digest>` | — | — | Multiple Bundles use sibling `-<log-index>` and Bundle-digest collision locators; `ADR-014`, `ADR-044` |
| Store metadata | Canonical JSON version `1` | 1 | integer | Exact ChangeSet Digest, Bundle digest, size, and storage-time binding; `ADR-043` |
| CLI exit codes | `GLOSS-001 §7` | frozen | table | **Effectively frozen from first release.** Any change is a major version bump of the CLI. `REQ-F10-010` |
| CLI config | `spec/schemas/cli-config-v1.schema.json` | 1 | integer | Closed safe-YAML model; generated and drift-checked. `REQ-F10-050`, `REQ-F10-200` |
| CLI Collection Artifact | `spec/schemas/cli-collection-v0.1.schema.json` | 0.1.0 | SemVer | Closed staged-pipeline input; generated and drift-checked. `REQ-F10-110`, `REQ-F10-200` |
| CLI `--json` output | `spec/schemas/cli-output-v0.1.schema.json` | 0.1.0 | SemVer | Closed command-discriminated union; generated and drift-checked. `REQ-F10-020`, `REQ-F10-200` |
| Policy schema | `version:` integer field | `1` | integer | Increment on breaking change; old versions still evaluated. `GLOSS-001 §5` |
| Generated structural JSON Schema | `spec/schemas/ai-authorship-v0.1.schema.json` | tracks predicate | generated | **Generated only — never hand-authored or hand-edited.** CI fails on drift; non-representable semantic invariants remain mandatory runtime checks. `ADR-010`, `ADR-021` |

### 2.1 Exit-code table (frozen contract — `GLOSS-001 §7`)

CI pipelines depend on these. They **MUST NOT** change without a major version bump.

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Unexpected internal error |
| `2` | Usage error (bad arguments, bad config) |
| `3` | Policy violation — the gate denied the change |
| `4` | Verification failure — signature, identity, or log check failed |
| `5` | Attestation not found where one was required |
| `6` | Transient/network failure (safe to retry) |

The separation of `3`, `4`, and `5` is deliberate: "policy says no", "the signature is bad", and
"there is nothing here" need different human responses and different CI handling. Do not collapse
them.

---

## 3. Runtime requirements

| Runtime | Minimum | Used in dev | Notes |
|---|---|---|---|
| Python | 3.12.0 | 3.12.13 and 3.13.12 | Test matrix covers both (`BOOT-001 §12`). 3.12 is the target |
| uv | latest | 0.11.2 | Package/project manager; `uv.lock` is the source of truth for versions |
| just | latest | 1.58.0 | Task runner; not a Python dependency |
| git | 2.40 | 2.34.1 host; 2.47.3 validation | F-02 release validation ran on 2.47.3 because the host is below the supported floor |
| libgit2 | optional via `pygit2` extras | 1.9.6 via pygit2 1.20.0 | Base installation uses the Git CLI when a compatible wheel is unavailable (`ADR-034`) |
| Docker | 24.0 | 29.6.1 | Only for building/running the container distribution |
| GitHub Actions runner | `ubuntu-latest` | — | Needs `id-token: write`, `contents: read`/`write`, `pull-requests: read` |

**Operating systems.** CI tests Linux and macOS (`TECH-001 §7`). Windows is untested and
unsupported in v1.0; nothing in the design prevents it, but nothing verifies it either — do not
claim support that no job proves.

---

## 4. Dependency assignment (NORMATIVE — `BOOT-001 §4.1`)

Routine version constraints are deliberately **not** listed here. The initial lock must use the
executed baseline versions recorded in `BOOT-001 §4.1`; after that, use `uv add` or `uv lock` and
let the resolver update `uv.lock`, which remains the source of truth (`TECH-001 §3`). Never
hand-write a version from memory.

| Package | Dependencies |
|---|---|
| `attest-core` | `pydantic`, `rfc8785`, `jsonschema` |
| `attest-collect` | `attest-core`, `httpx`; optional `pygit2` extra |
| `attest-sign` | `attest-core`, `sigstore` |
| `attest-store` | `attest-core`, `oras`; optional `pygit2` extra |
| `attest-policy` | `attest-core`, `pyyaml` |
| `attest-export` | `attest-core`, `attest-store`, `attest-sign`, `pyyaml` |
| `attest-cli` | `attest-core`, `attest-collect`, `attest-sign`, `attest-store`, `attest-policy`, `pydantic`, `httpx`, `typer`, `rich`, `structlog`, `pyyaml`; `attest-export` only after F-12 |

Current published CLI `0.1.4` metadata exact-pins core, collect, and policy to `0.1.0` and sign and
store to `0.1.1`. Pending workspace CLI `0.1.5` preserves those pins except for corrected store
`0.1.2`; these source versions remain local until `ADR-068` completes. `attest-export` is excluded
from the published set and from the published CLI dependency graph until F-12 is Done (`ADR-046`,
`ADR-064`).

**`attest-core` MUST NOT gain any dependency with I/O capability.** Adding one requires an ADR
(`BOOT-001 §4.1`, `REQ-F01-140`). Enforced by the `core-is-pure` import-linter contract, not by
convention.

Project-owned Pydantic models implement the in-toto Statement wire contract; there is no direct
`in-toto-attestation` dependency (`ADR-022`). Direct `securesystemslib` imports are forbidden;
Sigstore owns DSSE and bundle operations
end-to-end (`ADR-020`). The first `uv.lock` must use the exact executed baselines listed in
`BOOT-001 §4.1`.

---

## 5. Internal interoperability

Dependencies point **inward toward `attest-core`**. The four peer adapters never import each other;
`attest-export` is the bounded application layer over store and sign, and `attest-cli` is the
top-level composition root (`ADR-022`, `ARCH-001 §2.1`).

```
                         attest-cli
                    /        |        \
                   /    attest-export  \
                  /        /     \      \
     attest-collect  attest-sign  attest-store  attest-policy
                  \        |       /           /
                   \       |      /           /
                         attest-core
```

| Consumer | Depends on | Min version | Enforced by |
|---|---|---|---|
| `attest-collect` | `attest-core` | 0.1.0 | import-linter `layers` |
| `attest-sign` | `attest-core` | exactly 0.1.0 in published `0.1.1` metadata | import-linter `layers` |
| `attest-store` | `attest-core` | exactly 0.1.0 in published `0.1.2` metadata | import-linter `layers` |
| `attest-policy` | `attest-core` | 0.1.0 | import-linter `layers` |
| `attest-export` | `attest-core`, `attest-store`, `attest-sign` | 0.1.0 | import-linter `layers` |
| `attest-cli` | core, collect, sign, store, policy; export activates with F-12 | published `0.1.5`: exact core/collect/policy 0.1.0, sign 0.1.1, store 0.1.2 | import-linter `layers` |
| `attest_sign.verifier` | **must not** import `attest_sign.sigstore_signer` | — | import-linter `verifier-isolation` (`ARCH-001 §1` P3) |
| GitHub Action | multi-platform container image, pinned **by manifest digest, not tag** | public image 0.1.7; Action v1.0.7/v1 | `REQ-F11-010`, `REQ-F11-290`, `REQ-F11-300`, `REQ-F11-310`, `REQ-F11-320`, `C-09`, `ADR-046`, `ADR-064`, `ADR-065`–`ADR-068` |

---

## 6. External service and standard compatibility

| Dependency | Used for | Version/instance | Notes |
|---|---|---|---|
| Sigstore Fulcio | Keyless certificate issuance | public good instance | Production for real runs |
| Sigstore Rekor | Transparency log | public good instance | **Public by default.** Anything in an attestation is effectively published (`SEC-001 T-06`). Private Rekor is the documented mitigation |
| Sigstore staging | All test signing | staging instance | **Hard rule** — never write test data to the production log (`TECH-001 §6`, `QA-001 §10`). A guard test fails the suite if a production endpoint is configured in test settings |
| GitHub REST/GraphQL | PR record/Compare context, review records, check runs | v3 / v4 | F-04 rejects PR-field drift and incomplete/capped Compare identity context; GitLab/Bitbucket are `OOS-02`, v1.1 |
| Git AI note format | Cross-tool authorship claims | `authorship/3.0.0` at upstream commit `0670e7ef` | Exact read-only profile; a different schema version requires an ADR (`ADR-035`) |
| Agent hook examples | Experimental sidecar emission | Claude Code and Codex `PostToolUse`, checked 2026-09-12 | Covers only documented file-edit/apply-patch events; `CH-03` remains open |
| OCI registry | Optional attestation storage | OCI distribution spec | `F-07` via `oras` |
| RFC 8785 (JCS) | Canonicalisation | — | Via `rfc8785`. `json.dumps(sort_keys=True)` is **not** equivalent and is explicitly rejected (`TECH-001 §10`) |
| RFC 3339 | Timestamps | UTC, `Z` suffix, second precision | Naive datetimes are rejected at model validation (`REQ-F01-070`) |

---

## 7. Distribution channels

| Channel | Artifact | Audience | Feature |
|---|---|---|---|
| GHCR | public `ghcr.io/parth2412/attest:0.1.7` for amd64/arm64 at immutable manifest `sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356` | **Primary** CI channel | `F-11` |
| GitHub Action | `Parth2412/attest/action@<full-sha>`; immutable `v1.0.7` and reviewed moving `v1` at release commit `c42e52d038f5ecdcc498679cb7648e5b0957d489` | Most users — generated workflows pin a commit | `F-11` |
| PyPI | core, collect, policy `0.1.0`; sign `0.1.1`; store `0.1.2`; CLI `0.1.5`; no export distribution | Python-native teams | `F-11` publication of implemented F-01–F-10 artifacts |
| Homebrew | formula | Local developer use | post-v1.0 |

Multi-arch: `linux/amd64` and `linux/arm64`. The Action builds from the reviewed
`python:3.12.14-alpine3.23` base, carries source-built Git 2.52.0 and curl 8.23.0, and pins the
released runtime by the immutable manifest above (`ADR-062`, `ADR-064`, `ADR-067`). Failed run
`39829765757` and its 8.22.0 source artifact remain immutable negative evidence and are not a
binary candidate.

**There is no single static binary and none is planned.** `ADR-011` records the one bounded
trigger that could reopen it — M2 exit gate, installation friction ranked top complaint by a
majority of design partners, verifier only. Nobody may begin such a port speculatively.

---

## 8. Licensing

| Artifact | Licence | Recorded in |
|---|---|---|
| All code (`packages/`, `action/`, `scripts/`) | Apache-2.0 | `LICENSE`, `ADR-017` |
| `SPEC-001` and `spec/testvectors/` | CC-BY-4.0 | `LICENSE.spec`, `ADR-017` |

Apache-2.0 carries the explicit patent grant enterprise legal review expects from security
tooling. CC-BY-4.0 signals that reimplementation of the specification is invited — which is the
entire adoption strategy (`CH-07`).

---

## 9. Deprecated and transitional

| Item | Status | Replacement / note |
|---|---|---|
| Git Notes as attestation **storage** | never used | `refs/attestations/<digest>` (`ADR-014`). Notes concentrate writes on one ref and conflict under concurrent CI |
| Git Notes as a **claim source** | supported | Unaffected by the above — read-only, for Git AI interoperability (`BRD-F03`) |
| Predicate `v0.x` URIs | unstable by design | Early adopters **must** be told v0.x identifiers can change; stated in the README and in verification output (`ADR-013`) |
| Control mappings without a named reviewer | `status: draft-unreviewed` | Exports built from them carry a non-suppressible banner; `F-12` cannot reach DoD until one framework mapping is `reviewed` (`ADR-016`) |

---

## 10. Changelog

- **2026-10-26**: Completed `ADR-068` and returned F-11 to Done. Public store `0.1.2`, CLI
  `0.1.5`, image `0.1.7`, product `v0.1.7`, and immutable Action `v1.0.7` resolve to exact release
  commit `c42e52d038f5ecdcc498679cb7648e5b0957d489`; independently approved promotion run
  `40287925165` moved reviewed `v1` only after the release, same-repository proof, and safe fork
  denial verified.
- **2026-10-24**: Accepted `ADR-068` and reopened F-11. Source store `0.1.2` corrects Darwin
  process-lock acquisition and source CLI `0.1.5` exact-pins it. Public versions remain store
  `0.1.1`, CLI `0.1.4`, image `0.1.6`, and Action `v1.0.6`/`v1` until a unique
  `0.1.7-candidate`, full performance/release lifecycle, public proofs, and reviewed promotion
  complete. Cancelled run `40086747745` remains incomplete evidence and is not promotable.
  Replacement run `40114789855`, attempt 1, passed every source, component, both-platform runtime,
  image-scan, SBOM, provenance, and identity gate for multi-platform candidate
  `sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356`; performance and public
  release gates remain pending.
- **2026-10-23**: Completed the `ADR-065`–`ADR-067` replacement on image `0.1.6`, immutable
  product `v0.1.6`, immutable Action `v1.0.6`, and reviewed moving `v1`, all at release commit
  `e693e6b60afdf9c667a913faa4f9652bfd6dc050` and manifest
  `sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe`. No Python
  distribution changed; candidate, performance, release, dogfood, public proof, fork denial, and
  protected promotion evidence all completed.
- **2026-10-23**: Accepted `ADR-067` and replaced only the rejected curl `8.22.0` source with
  signed, hash-locked `8.23.0` inside the existing unreleased `0.1.6` lifecycle. Failed run
  `39829765757` remains negative evidence; a new unique candidate must pass every existing gate.
- **2026-10-22**: Accepted `ADR-066` and added exact Alpine `musl==1.2.5-r24` runtime and matching
  build-stage remediation to the existing `0.1.6` lifecycle without changing its versions,
  publication boundary, evidence sequence, or immutable history.
- **2026-10-22**: Accepted `ADR-065`, reopened F-11, and recorded the bounded image-only
  `0.1.6`/Action `v1.0.6` security replacement. Existing Python versions and every immutable
  `0.1.5` record remain unchanged while the complete candidate, performance, release, proof, and
  independent promotion sequence is repeated.
- **2026-10-15**: Accepted `ADR-064` and completed F-11 on immutable product/image `0.1.5`, source
  `v0.1.5`, Action `v1.0.5`, reviewed moving `v1`, signer `0.1.1`, and CLI `0.1.4` evidence. The
  schema-2 performance sequence, release dogfood, same-repository proof, safe fork denial, and
  protected promotion all completed; F-12 remains Planned and unpublished pending `CH-04`.
- **2026-09-16**: Accepted F-11's closed Action and two-phase release contract in `ADR-046`;
  recorded product 0.1.0's exact six-package set, independent Action v1.0.0/v1 versions,
  multi-platform immutable image, Trusted Publishing, and required public/fork/performance proofs.
- **2026-09-16**: Activated F-10 in `attest-cli`; the exact command surface, config and artifact
  schemas, installed entrypoints, deterministic reports and exits, secure I/O, and full pipeline
  orchestration pass the enforced 90% CLI coverage gate.
- **2026-09-15**: Completed F-08 parse-only Bundle inspection with ordered structural checks,
  explicit `unverified-identity` success, and no verified-identity or policy-evidence surface.
- **2026-09-15**: Completed F-04 exact GitHub event/PR/Compare context resolution with immutable
  numeric author and committer associations and fail-closed drift/cap handling.
- **2026-09-15**: Accepted the F-10 v0.1 CLI/config/artifact/output contracts in `ADR-045`, with
  F-04 exact GitHub Compare context and F-08 labelled parse-only inspection as prerequisites.
- **2026-09-14**: Activated F-07 in `attest-store`; filesystem, Git CLI, optional pygit2, and OCI
  Referrers storage pass exact-byte, create-only concurrency, corruption, containment, fallback,
  pagination, and hard-deadline conformance above the 90% package coverage gate.
- **2026-09-12**: Activated F-05 across `attest-core` and `attest-collect`; deterministic
  Statement assembly, two-layer validation, golden canonical bytes, and conservative GitHub
  Actions environment trust metadata are covered at 99% core and 100% environment-module branch
  coverage.
- **2026-09-12**: Activated F-03 in `attest-collect`; sidecar, trailer, pinned Git AI note, and
  manual sources pass deterministic, raw-digest, malformed-input, prompt-isolation, and secure
  filesystem tests at 91% package branch coverage. Claude Code and Codex examples are
  experimental, and `CH-03` remains open.
- **2026-09-11**: Activated F-02 in `attest-collect`; both optional pygit2 and base-install Git
  CLI paths pass identical real-repository and normative-vector conformance. Supported-Git
  benchmarks closed `CH-08` without changing the 500 ms target.
- **2026-09-11**: Made `pygit2` an optional collector/storage backend extra while retaining its
  exact development/CI pin and requiring Git CLI operation from the base installation
  (`ADR-034`).
- **2026-09-11**: Removed inactive workflow placeholders; `e2e-sign.yml` and `release.yml` now
  arrive only with their owning features (`ADR-028`).
- **2026-09-11**: Activated the F-01 core domain contracts and their normative test vectors.
- **2026-09-11**: Pinned the bootstrap CI action/toolchain inputs, locked CI installation, and
  expanded the required Python matrix to Linux and macOS (`ADR-027`).
- **2026-09-10**: Bootstrapped all seven distributions at 0.1.0, resolved the GitHub owner in the
  predicate URI, and recorded each implementation component as `scaffold`. Quality tooling is
  aligned to the workspace layout by `ADR-026`.
- **2026-09-10**: Removed direct `securesystemslib` assignment, recorded Sigstore-native DSSE, and
  clarified that generated JSON Schema is structural while semantic invariants remain runtime
  obligations (`ADR-020`, `ADR-021`). `CH-01` and `CH-02` are closed.
- **2026-09-10**: Formalised `attest-export` as a bounded application layer and corrected direct
  dependency ownership (`ADR-022`).
- **2026-09-10**: Clarified the pre-F-01 schema lifecycle and added the bootstrap import smoke
  test (`ADR-023`).
- **2026-08-01**: Initial matrix. All components `planned` — repository is pre-bootstrap, Week 0
  validation (`CH-01`, `CH-02`) not yet closed. Wire contracts recorded from `SPEC-001`,
  `GLOSS-001 §5`, `GLOSS-001 §7`, and `ADR-013`/`ADR-014`/`ADR-017`.

> **Update obligation.** This file changes in the same commit as any version bump, runtime-floor
> change, dependency reassignment, or wire-contract change. A stale compatibility matrix in a
> product whose whole promise is long-term verifiability is not a documentation problem — it is a
> correctness problem.
