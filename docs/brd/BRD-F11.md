# BRD-F11 — GitHub Action Packaging

| Field | Value |
|---|---|
| Document ID | `BRD-F11` |
| Feature | `F-11` |
| Milestone | M2 |
| Package | `action/` |
| Depends on | `F-06`, `F-07`, `F-09`, `F-10` |
| Status | **In progress** · `ADR-071` requires an image-only `0.1.8` / Action `v1.0.8` security replacement before F-11 returns to Done |

---

## 1. Purpose

Make attest usable in under five minutes by someone who has never written Python. The Action is
the primary distribution channel; PyPI is the direct CLI/library channel.

## 2. Scope trace

`SCOPE-10`.

## 3. Action interface

### 3.1 Exact public manifest

`NORMATIVE EXAMPLE`

```yaml
- uses: Parth2412/attest/action@<40-character-commit-sha>
  env:
    GITHUB_TOKEN: ${{ github.token }}
  with:
    mode: run
    policy: .attest/policy.yaml
    push-attestation: 'true'
    fail-on-violation: 'true'
```

`bundle` is omitted in `run` mode and required in `verify` and `gate` modes. The public input set
is closed:

| Input | Default | Contract |
|---|---|---|
| `mode` | `run` | Exact enum `run`, `verify`, or `gate`. |
| `policy` | `.attest/policy.yaml` in `run`/`gate` | Repository-relative bounded regular YAML file; forbidden for `verify`. |
| `bundle` | — | Repository-relative bounded regular JSON file; forbidden for `run`, required for `verify` and `gate`. |
| `push-attestation` | `'true'` in `run` | Exact Boolean string; forbidden for `verify`/`gate`. `false` uses an ephemeral filesystem store. |
| `fail-on-violation` | `'true'` in `run`/`gate` | Exact Boolean string; forbidden for `verify`; see §3.5. |

The manifest declares only these inputs, and the wrapper rejects unexpected runner-provided Action
inputs. Empty required values, absolute paths, `..` escape, symbolic links, special files,
oversized files, invalid UTF-8, and invalid Boolean spellings are rejected before orchestration.
Only `mode` has a metadata default. The wrapper applies the other defaults after validating the
mode, preserving the distinction between an omitted value and an explicitly invalid combination.

### 3.2 Mode semantics

| Mode | Operation | OIDC | Policy | Storage |
|---|---|---:|---:|---|
| `run` | Resolve the event, collect, build, sign, self-verify, store, verify, and gate through the F-10 composition. | Required | Required | Configured durable store when `push-attestation=true`; isolated temporary filesystem store otherwise. |
| `verify` | Identity-bound verification of the supplied Bundle and repository subject. | Forbidden | None | No write. |
| `gate` | Identity-bound verification of the supplied Bundle, then policy evaluation. | Forbidden | Required | No write. |

No mode imports or executes code, scripts, hooks, build files, or executables from the repository.
The image invokes the wrapper through an exec-form entry point with a sanitized runtime environment;
user-site Python imports and implicit current-directory imports are disabled.

### 3.3 Events and repository state

Only branch `pull_request`, branch `push`, and exact branch `workflow_dispatch` events are
supported. `pull_request_target`, tags, branch creation/deletion, missing before/after objects,
malformed or inconsistent payloads, and every other event fail closed with `ERR-CONFIG-007`.
Pull-request context uses the F-04 exact resolver. Push context is derived only from the validated
event repository, before/after commits, and local git objects; an all-zero before or after object
is invalid. Dispatch context binds its exact five-field payload, repository, full branch ref,
branch name/type, selected SHA, workflow path, and `GITHUB_WORKFLOW_REF`, then derives the selected
commit's first parent from complete local history after OIDC succeeds.

Every mode requires complete repository history for its subject. A shallow repository, missing
object, or unavailable comparison fails with `ERR-CONFIG-008` and a message that names
`fetch-depth: 0`. The Action does not fetch or deepen history itself.

### 3.4 Authentication and permissions

`run` checks OIDC availability before it reads repository-controlled configuration, claims,
policy, or Bundle data. Absence fails with `ERR-SIGN-301` and names the exact `id-token: write`
permission. `verify` and `gate` never request an OIDC token. The caller workflow passes the
automatic `${{ github.token }}` to the Action step as `GITHUB_TOKEN`; Action metadata does not
reference the `github` context. There is no public token input or output, and no credential is
printed.

For the generated production `run` workflow with publication enabled:

```yaml
permissions:
  contents: write
  id-token: write
  pull-requests: read
  checks: read
```

`contents: write` is unnecessary when publication is disabled. `verify` and `gate` require only
the read permissions needed by their exact repository and policy inputs. Fork pull requests do not
receive signing or write authority and must fail before repository reads. A
`pull_request_target` workaround is prohibited.

### 3.5 Outputs, summary, and exits

The public outputs are:

| Output | Meaning |
|---|---|
| `changeset-digest` | Lowercase SHA-256 ChangeSet Digest, set after a structurally and semantically valid Statement is available. |
| `attestation-ref` | Durable store location for published `run`; validated Bundle path for `verify`/`gate`; empty for non-publishing `run` or before either exists. |
| `decision` | `allow`, `warn`, or `deny` for verified `run`/`gate`; `verified` for successful `verify`; empty before verification completes. |
| `log-index` | Rekor log index from a successfully verified Bundle when present; otherwise empty. |

Outputs already earned are written before an expected policy exit, including a deny. With
`fail-on-violation=false`, only policy exit `3`, or decision-backed verification-policy exit `5`,
is converted to Action success. Configuration, input, verification, signing, storage, network, and
internal failures remain fatal. The job summary escapes all untrusted data and renders the
decision, authorship mode, and review record without HTML execution.

### 3.6 Action-boundary diagnostics

| Code | Condition | Exit | Remediation |
|---|---|---:|---|
| `ERR-CONFIG-007` | Unsupported, malformed, inconsistent, or forbidden Action input/event | 2 | Use only the exact §3.1 inputs on a branch `pull_request`, branch `push`, or exact branch `workflow_dispatch` event. |
| `ERR-CONFIG-008` | Shallow history, missing comparison object, or incomplete repository state | 2 | Configure checkout with `fetch-depth: 0` and ensure both comparison objects exist. |
| `ERR-SIGN-301` | `run` has no ambient GitHub OIDC signing identity | 2 | Add `permissions: id-token: write`; do not add a token input. |

All other domain errors retain F-10's semantic exit mapping. The wrapper emits exactly one safe
code, message, and remediation and does not relabel an unknown exception except as
`ERR-INTERNAL-001`/exit `1`.

## 4. Distribution and release

### 4.1 Version and artifact set

The first product release is `0.1.0`. PyPI receives exactly `attest-core`, `attest-collect`,
`attest-sign`, `attest-store`, `attest-policy`, and `attest-cli`. Published internal dependencies
are exactly pinned to `0.1.0`; every package has complete project URLs, README metadata, licence
metadata, and licence content. `attest-export` is not published and is not an `attest-cli`
dependency until F-12 is Done. The six names were available when checked on 2026-09-16, but the
release must recheck ownership/availability before Trusted Publisher registration and stop for a
new ADR rather than rename any distribution implicitly.

The Action version is independent: immutable `v1.0.0` plus moving-major `v1`, both initially
pointing to the product `v0.1.0` release commit. Immutable version tags are protected from update
and deletion by a tag ruleset, GitHub immutable releases protect `v0.1.0`, and only the reviewed
release procedure may move `v1`. The multi-platform
`linux/amd64` and `linux/arm64` image is versioned `0.1.0`, published publicly to GHCR, and consumed
by `action.yml` only through its immutable manifest digest.

### 4.1.1 Bounded token-boundary correction

The public `v1.0.0` Action remains immutable but is documented as defective: GitHub rejects its
metadata before execution because the metadata references `github.token` outside a supported
evaluation boundary. The correction removes that reference from `action.yml` and places the
automatic token in the exact caller step environment. It introduces no token input or secret.

The corrected generator is published only as `attest-cli==0.1.1`; its five internal dependencies
remain exactly pinned to `0.1.0`. The corrected Action is published as immutable `v1.0.1`, and the
reviewed moving-major `v1` advances to that commit. The existing `0.1.0` container manifest digest
remains pinned because the Action runtime and image bytes are unchanged. A product/source tag
`v0.1.1` records the bounded CLI correction; no unchanged Python distribution or image tag is
republished.

Public verification uses PyPI's version-specific JSON endpoint and compares the exact downloaded
wheel and source archive with the reviewed build. If those exact immutable files already exist,
recovery must validate and retain the original successful Trusted Publishing run and skip the
publisher job. The public verification, production dogfood, and immutable-release jobs must use
explicit success-result conditions so that GitHub does not propagate that intentional skip; any
failed, cancelled, or otherwise skipped required gate remains fail-closed. Recovery must never
overwrite, silently skip, delete, or yank a release file.

### 4.1.2 Pull-request identity and runtime diagnostic correction

The public `v1.0.1` Action reaches its container, but the CLI `0.1.1` generator binds the
pull-request-only workflow to `refs/heads/<default-branch>`. GitHub instead issues the workflow
certificate at `refs/pull/<number>/merge`, so verification correctly fails closed. The initializer
therefore generates the bounded `refs/pull/*/merge` workflow identity defined by `ADR-051`.

The Action wrapper also preserves a closed `ERR-VERIFY-*` diagnostic from a structurally valid
denied run or gate report before deriving facts. Unknown or inconsistent reports remain internal
errors, and failed verification emits no output or job-summary fact.

The correction publishes only `attest-cli==0.1.2` on PyPI and retains its exact five `0.1.0`
library pins. Because the wrapper bytes change, a new reviewed multi-platform candidate is promoted
without rebuilding to `ghcr.io/parth2412/attest:0.1.2`, pinned by manifest digest from immutable
Action `v1.0.2`; `v0.1.2` records the source and evidence. Every earlier PyPI file, image manifest,
source tag, Action tag, and immutable Release remains unchanged. Moving `v1` is forbidden until
the `0.1.2` replacement public proof completes every required state.

### 4.1.3 Remote attestation discovery correction

The `v1.0.2` proof publishes its valid no-review denial Bundle, then an approved rerun signs a
different Bundle for the same ChangeSet. A fresh checkout does not contain custom remote refs, so
without `ADR-052` it attempts the occupied base ref and fails closed with `ERR-STORE-401` before
policy evaluation.

The corrected Git-ref path imports one stable, exact-digest remote namespace through source-only
object fetches before local allocation. It validates every object, never updates a destination ref
or `FETCH_HEAD`, creates only absent refs, and then applies the existing deterministic sibling
algorithm. Import happens at the push stage after OIDC preflight, preserving fork failure before
repository reads. An import failure preserves the new signed Bundle in filesystem fallback.

The correction publishes `attest-store==0.1.1` and `attest-cli==0.1.3`; core, collect, sign, and
policy remain exactly `0.1.0`, and export remains unpublished. A reviewed candidate is promoted
without rebuilding to image `0.1.3`, immutable Action `v1.0.3`, and source record `v0.1.3`.
Earlier package files, images, tags, Releases, and attestation refs remain immutable. The moving
`v1` tag remains unchanged until a new proof completes every required state and demonstrates the
denied and approved sibling Bundles.

### 4.1.4 Measured slim-runtime correction

The released `v1.0.3` Action fails the exact cold-start acceptance gate: run `36033851434`,
attempt 1, retained 20 successful hosted-runner samples with p50 16 s and nearest-rank p95 20 s.
Its image pull alone reached 13 s p95. The release remains functionally correct and immutable, but
F-11 cannot be Done while `REQ-F11-100` fails.

`ADR-053` therefore replaced the digest-pinned Debian-slim runtime with the validated,
digest-pinned `python:3.12.14-alpine3.23` base and exact `git=2.52.0-r0` package without changing
the Python package graph or Action interface. A fresh candidate must carry the truthful
`0.1.4-candidate` OCI label. The exact merged `main` Action and candidate digest must pass the
then-unchanged 20-job p95 gate before publication.

On success, the exact reviewed manifest is promoted without rebuilding as image `0.1.4`, with
source record `v0.1.4` and immutable Action `v1.0.4`. No Python distribution is rebuilt or
republished. Moving `v1` remains on `v1.0.3` until the new image and attestation, immutable release,
production dogfood, fresh public proof, and retained performance evidence all verify independently.
Every earlier package, image, source tag, Action tag, Release, and attestation record remains
immutable.

### 4.1.5 Repeatable cold-start reliability correction

The exact `v1.0.4` release gate passed, but post-release monitoring did not retain its cold-start
headroom. Run `36872334911` measured p95 16 s, and run `36905961561` measured p50 13 s and p95
17 s against the same reviewed image. The immutable `0.1.4`/`v1.0.4` release remains valid and is
not rewritten, but `ADR-054` requires a bounded image-only correction before the Action is treated
as repeatedly meeting `REQ-F11-100`.

The `0.1.5-candidate` runtime builds locked `cryptography==50.0.1` from its hash-locked sdist with
an exact build-only Rust/C/OpenSSL toolchain, removes every build tool, uses exact matching runtime
OpenSSL libraries, and balances the remaining content across three zstd layers. The wrapper retains
the isolated interpreter and sanitized state but avoids a second interpreter only when the bundled
console script matches a build-generated SHA-256 marker; any mismatch uses the existing subprocess
boundary.

Under the original `ADR-054` contract, the exact reviewed candidate had to pass real-container cryptographic contracts, both architecture
scans, SBOM/provenance validation, and identity-bound attestation. After its digest is pinned by a
reviewed `main` commit, the automatic push measurement and two ordered reviewed dispatches must
form three consecutive attempt-1 20-job measurements. Each run and the combined 60 samples must
have nearest-rank p95 below 15 seconds. `ADR-063` and `REQ-F11-280` supersede only that
performance threshold for the pending release; all other controls in this section remain. Only
after the amended gate passes may the exact manifest be promoted without
rebuilding to image `0.1.5`, source record `v0.1.5`, and immutable Action `v1.0.5`. No Python
distribution changes. Moving `v1` from `v1.0.4` remains forbidden until immutable release,
dogfood, public onboarding, fork-denial, performance, and independent review evidence all verify.

### 4.1.6 Mandatory trust-refresh release amendment

`ADR-055` amends the image-only part of §4.1.5 after the first exact performance proof exposed
serialized Sigstore trust initialization as a material signing cost. The corrected signer overlaps
a same-environment offline bootstrap with mandatory online trust initialization, withholds success
until refreshed-root identity-bound DSSE verification returns the exact canonical payload, and
retains the same hard deadline and fail-closed error boundary. `ADR-056` adds only one bounded
fresh-process recovery for a stale pre-Rekor certificate/SCT bootstrap, after the already-running
online refresh succeeds; every other failure and the global two-attempt ceiling remain unchanged.

Because those production bytes change, the release publishes exactly `attest-sign==0.1.1` and
compatibility package `attest-cli==0.1.4`, whose internal dependency is exactly
`attest-sign==0.1.1`. Core, collect, policy, and store remain at their existing public versions and
must not be rebuilt or uploaded. Each new distribution is built once, published through its own
protected PyPI Trusted Publisher environment, matched byte-for-byte against the public files, and
clean-installed on Python 3.12 and 3.13. Exact recovery from an already successful publication
requires the earlier successful workflow run and validated OIDC publication evidence; it never
uses `skip-existing` or treats an unknown public file as acceptable.

The failed performance candidate remains immutable negative evidence. A new unique candidate must
repeat the entire two-platform, container, scan, SBOM, provenance, identity-attestation, and three
consecutive attempt-1 performance sequence before the bounded Python packages, exact reviewed image
`0.1.5`, source `v0.1.5`, and Action `v1.0.5` may be published. The independent `v1` promotion
rules remain unchanged.

### 4.1.7 Concurrent acquisition and native-runtime deduplication amendment

`ADR-057` amends §4.1.5–§4.1.6 after the first new candidate performance run failed closed
with one ambient-identity acquisition failure and one online-trust initialization failure, while
the successful subset still exceeded the required p95. Ambient identity and mandatory online
trust acquisition now begin concurrently under the unchanged signing deadline and bounded retry
rules in `BRD-F06`.

Before `ADR-059`, the candidate runtime replaced exactly one wheel-private `libgcc_s-*.so.1`
file in each of `pydantic_core.libs`, `rfc3161_client.libs`, and `rpds_py.libs` with a symbolic
link to the exact `libgcc=15.2.0-r2` runtime file `/usr/lib/libgcc_s.so.1`. The build fails if any
directory lacks its one expected file or if another wheel-private copy appears. The platform-specific wheel
filename is discovered from the locked installation rather than copied from another architecture.
Both amd64 and arm64 real-container jobs must prove the three links, dynamic system-library
mapping, native module execution, and offline Sigstore trust initialization.

The failed candidate and performance run remain immutable negative evidence. A new uniquely
referenced candidate must repeat every existing container, scan, SBOM, provenance,
identity-attestation, and performance gate. No version, public artifact set, acceptance threshold,
or promotion rule changes.

### 4.1.8 Verified non-timestamp TUF cache amendment

The exact post-`ADR-057` performance run `37796984054`, attempt 1, retained 20 successful samples
but correctly failed the strict gate at p50 12 seconds and nearest-rank p95 16 seconds. It remains
immutable negative evidence. `ADR-058` addresses the measured post-pull tail without changing the
signer, dependencies, acceptance threshold, or mandatory online trust boundary.

The candidate checks in a closed, hash-locked, lossless representation of captured production and
staging TUF metadata and target bytes. During the image build, the exact pinned Sigstore and TUF
libraries must verify the complete captured chain from Sigstore's embedded environment root at the
recorded capture instant, including target length and hash validation. Any file-set, path, byte,
signature, version, expiry-at-capture, or target mismatch fails the build.

Each Action invocation seeds its fresh isolated `HOME` only with staging root-history version 15,
both environments' snapshot and targets metadata, and both selected target files. Captured
timestamps are build-validation inputs only and must never be copied into runtime cache. Sigstore
must therefore still perform a live next-root probe and live timestamp download on every
invocation; authenticated metadata drift triggers the normal live download path, and the final
refreshed-root verification remains unchanged.

The new unique candidate and exact merged Action must repeat every existing candidate and three-
run performance gate. No version, public artifact set, promotion rule, or earlier immutable record
changes.

### 4.1.9 Locked native source-build amendment

The exact post-`ADR-058` run `37899003696`, attempt 1, retained 20 successful samples but failed
closed at p50 11 seconds and nearest-rank p95 17 seconds. Its measured p95 tails were about 7.87
seconds for image pull/extraction and 9.60 seconds after pull. It remains immutable negative
evidence. `ADR-059` reduces both the transferred image and the native runtime without changing a
dependency version, trust rule, signer behavior, public interface, or threshold.

The image builds exact locked `cryptography==50.0.1`, `pydantic-core==2.46.5`, and
`rfc3161-client==1.0.8` from their hash-locked source distributions with the approved removable
toolchain. Rust uses the exact size/strip/panic flags in `ADR-059`; vendored and static OpenSSL are
disabled so native extensions consume pinned Alpine OpenSSL. Pydantic and RFC 3161 consume the
pinned system libgcc directly. Only `rpds_py.libs` may contain one private libgcc name, which is
replaced by a symlink to `/usr/lib/libgcc_s.so.1`; any private-lib set drift fails the build.

The reduced Pydantic package moves to the second primary pull layer to keep the three concurrent
zstd downloads balanced. Both target architectures must execute every affected native module,
load exact system libraries, and initialize offline Sigstore trust before the candidate is
accepted. A new unique candidate and exact merged Action restart every existing supply-chain and
three-run performance gate.

### 4.1.10 Deterministic runtime-archive compression amendment

The exact post-`ADR-059` run `37946041636`, attempt 1, retained 20 successful samples but failed
closed at p50 12 seconds and nearest-rank p95 16 seconds. Its measured p95 tails were 7.397 seconds
for image pull/extraction and 10.952 seconds after pull. It remains immutable negative evidence.
`ADR-060` reduces the runtime layer's applied filesystem bytes without changing a dependency,
trust rule, signer behavior, public interface, version, sample, or threshold.

The build encodes exactly the closed 1,066-member pure-Python `attest-runtime.zip` with Python's
standard `ZIP_DEFLATED` method at compression level 9. It retains sorted membership, checked-hash
bytecode, fixed 1980 timestamps, Unix regular-file modes, the closed root set, and the existing
in-place `.pth` import path. The already-deflated standard-library archive remains unchanged, and
no runtime extraction path is introduced.

Both target architectures must prove the exact compression method, deterministic metadata,
complete archived imports, native execution, and existing trust and security contracts. A new
unique candidate and exact merged Action restart every existing supply-chain and three-run
performance gate.

### 4.1.11 Action runtime-headroom and reviewed-dispatch amendment

Automatic performance run `38056326479`, attempt 1, retained 20 successful samples but failed
closed at p50 11 seconds and nearest-rank p95 15 seconds. Exact timestamps measured p95 image
pull/extraction at 7.444 seconds and post-pull execution at 9.751 seconds. It remains immutable
negative evidence and did not start the required three-run sequence.

`ADR-061` removes only fine-grained traceback end-line and column tables from both deterministic
Python archives while retaining optimisation level zero, assertions, docstrings, source line
numbers, checked-hash bytecode, and every existing archive contract. It also authorizes only the
guarded Action-internal Linux `fork` boundary in `REQ-F06-170`; general CLI and library callers
remain on `spawn`.

The event adapter accepts exact branch `workflow_dispatch` alongside branch push and pull request.
It validates the closed dispatch payload, repository, full ref, branch coordinates, selected SHA,
workflow path, and workflow-ref binding before deriving the selected commit's first parent after
the OIDC-before-repository-read boundary. Tags, root commits, incomplete history, and inconsistent
or additional event data fail closed. A new unique candidate and exact merged Action restart every
existing supply-chain and three-run performance gate.

Pre-candidate automatic runs `38225190032` and `38249545348`, both attempt 1 against the
superseded `ADR-060` manifest, retained 20 successful samples at p50 12 seconds and p95 16
seconds. They remain immutable negative evidence and do not start the required sequence.
Candidate run `38250635610`, attempt 1, passed every `ADR-061` two-platform, 20-test
real-container, scan, SBOM, provenance, and identity-attestation gate for source
`b1d5475da39b2e9522482894dc675c73ecb118a1`, context
`sha256:f6206c3597e520322a4acfc7b40037a7b5fdd5621220eb9015c2595ef1d8ea7b`, and manifest
`sha256:10dade4e41415b68735f784f32a5667496ee4c36d60dba1b805660af092da584`.

### 4.1.12 Source-verified minimal Git HTTPS runtime amendment

Automatic performance run `38257587284`, attempt 1, retained 20 successful samples but failed
closed at p50 10 seconds and nearest-rank p95 17 seconds. It remains immutable negative evidence
and cannot be rerun or counted. `ADR-062` replaces only the Action image's oversized Alpine
Git/curl transport closure; Python packages, Sigstore behavior, trust, public interfaces, errors,
measurements, thresholds, and promotion rules remain unchanged.

The image builds unmodified Git `2.52.0` and curl `8.22.0` from the exact upstream archives and
digests accepted in `ADR-062`, using the exact pinned removable Alpine toolchain and pinned
OpenSSL/zlib. Git retains the complete builtin command set but only its required executables and
HTTP(S) helper. Curl retains HTTP/HTTPS smart transport, certificate verification, zlib, IPv6,
threaded DNS, CA bundle/path, and HTTPS proxy support while excluding every accepted unused
protocol and library.

Both architectures must rediscover and retain the complete loader mapping, prove the excluded
PCRE2/c-ares/HTTP2/IDN/PSL/zstd/Brotli/libunistring closure is absent, and exercise local and
certificate-verified public HTTPS Git operations. Before any candidate binary is published, the
workflow must publish and identity-attest a public digest-bound corresponding-source artifact
containing the exact archives, licences, hashes, component SPDX/OpenVEX evidence, and build recipe.
The binary must link that source digest, and the release must re-fetch, verify, retain, and attest the
same materials. Immutable CPE-aware Grype scans exact Git/curl evidence under the same critical
and fixable-high vulnerability gate as the runtime image; only the exact retained not-affected
OpenVEX statement for Git-for-Windows `CVE-2026-62960` applies. A unique candidate and the exact
merged Action restart the entire
candidate and three-run performance sequence.

Candidate run `38529646263`, attempt 1, passed this complete boundary for exact source
`49139761393b1f18f28f6bc06dfc1ff37166aa1b`, context
`sha256:25e8aec09b88f9182e10e096cb4336ef0cc9fbd0ea6f5498ab6dcf61a2c6c78b`, image
`sha256:6e1656ab5da1d5abc43c0ec36e6f3010f1f52c2528ff0e868eb2f62b5754906a`, and public
corresponding-source artifact
`sha256:0855c9c357f8764b18f288c6b13dd5a0859424f12264fa3140e08680637d0457`. Both platforms passed
all 22 real-container contracts, exact loader and four-layer evidence, image scans, component
scan, SBOM, provenance, and identity-bound attestations. This success authorizes candidate
pinning and a fresh performance sequence; it does not authorize release.

### 4.1.13 Evidence-calibrated hosted-runner SLO amendment

Automatic performance run `38570478871`, attempt 1, measured the exact merged commit
`f22f5be015a020b520d5abcb736ba236af7198cc` and the unchanged `ADR-062` manifest
`sha256:6e1656ab5da1d5abc43c0ec36e6f3010f1f52c2528ff0e868eb2f62b5754906a`. All 20 jobs
succeeded at p50 11 seconds and nearest-rank p95 17 seconds. Exact timestamps measured total p50
11.533 seconds and p95 16.861 seconds, image pull/extraction p50 6.110 seconds and p95 9.182
seconds, and post-pull execution p50 6.294 seconds and p95 8.711 seconds. The run failed the prior
strict 15-second gate and remains immutable negative evidence; it is not rerun, reclassified, or
counted in the new sequence.

`ADR-063` preserves the exact image, Action timing boundary, 20-job sample size, nearest-rank
calculation, attempt-1 rule, and automatic-plus-two-reviewed-dispatch sequence. It distinguishes a
strict engineering target below 15 seconds from a strict release SLO below 18 seconds. Both values
and both pass/fail results must appear in every single-run and combined summary, but only the SLO
authorizes publication. Evidence schema 2 binds `REQ-F11-280`/`AC-F11-280`; schema-1 evidence and
any earlier run fail closed instead of being silently reinterpreted.

Only a fresh sequence for the exact merged `ADR-063` commit may qualify: the automatic push run
followed by two ordered reviewed dispatches, each attempt 1 with 20 successful jobs, and the
combined 60 samples must all have nearest-rank p95 strictly below 18 seconds. The existing
`ADR-062` candidate is reused without rebuilding because this amendment changes only the evidence
contract. The 15-second engineering result remains a separately visible reliability signal.

### 4.1.14 Critical CA-bundle security replacement

`ADR-065` reopens F-11 after critical certifi advisory `GHSA-6q48-6c7w-9gw2` established that the
immutable `v1.0.5` Action image vendors affected `certifi==2026.7.22`. The corrected lock uses
exact `certifi==2026.10.19`. It also removes seven reviewed development-environment advisories by
upgrading development-only `virtualenv==21.14.1` to `21.14.12` and its resolver-selected
`python-discovery` dependency to `1.6.4`; neither development package may enter the Action image.

Every `0.1.5`, `v0.1.5`, `v1.0.5`, Python distribution, and evidence record remains immutable.
The replacement is image-only: fresh public package installations already resolve the corrected
certifi release, so no Python distribution is rebuilt or uploaded. A unique `0.1.6-candidate`
must repeat the complete two-platform real-container, scan, source-correspondence, SBOM,
provenance, identity-attestation, and exact-context gates. After reviewed digest pinning reaches
protected `main`, the exact Action and image must repeat the unchanged schema-2 automatic-plus-two-
reviewed-dispatch performance sequence and combined 60-sample release SLO.

Only the exact candidate may then be promoted without rebuilding to image `0.1.6`, immutable
source `v0.1.6`, and immutable Action `v1.0.6`. Release dogfood, the same-repository proof, fork
denial, and independent protected promotion must all verify before `v1` moves from `v1.0.5`.

### 4.1.15 Alpine musl security rebuild

`ADR-066` amends the still-unreleased replacement after Alpine published `musl==1.2.5-r24` for
`CVE-2026-107891`. The immutable Alpine base and public `v1.0.5` image contain affected
`musl==1.2.5-r23`. Both removable native-build stages must therefore use exact
`musl-dev==1.2.5-r24`, and the final runtime must explicitly upgrade to exact
`musl==1.2.5-r24`; correcting build tools without correcting the final libc is forbidden.

Before Alpine package metadata is removed, the build must prove the installed owner of its musl
loader and retain the exact installed revision in `/usr/share/attest/runtime-package-versions.txt`.
Both target architectures must prove that record contains only `musl-1.2.5-r24`, rejects `r23`,
and preserves every existing minimized-runtime and native-execution contract. This correction
shares ADR-065's unique candidate, performance, release, proof, and promotion lifecycle and does
not authorize another package, base-image, API, threshold, or publication change.

### 4.1.16 Fixed curl source replacement

`ADR-067` amends the still-unreleased replacement after protected candidate run `39829765757`
passed the complete release gate, published identity-attested corresponding source, and then
failed closed on fixable High `CVE-2026-92392` in curl `8.22.0`. The component gate stopped the
run before a binary candidate, performance sequence, release, or moving tag existed.

Only curl changes: the official signed, SHA-512-locked `8.23.0` archive replaces `8.22.0`. Git
`2.52.0`, the pinned toolchain, HTTP/1.1-only feature set, loader restrictions, exact
Git-for-Windows VEX statement, scan thresholds, release versions, and every ADR-065 lifecycle
gate remain unchanged. Run `39829765757`, its raw component scan, and source artifact
`sha256:5aef5c06c1989411d86c636c38dec652eec7747dccab739decc648ab560c23c4`
remain immutable negative evidence and cannot be rerun or promoted. A new protected `dev` commit
must publish new corresponding source and create a new unique two-platform candidate.

### 4.1.17 Reviewed 0.1.6 candidate evidence

Protected `dev` candidate run `39906806331`, attempt 1, completed successfully for exact source
`ae456176d0faefb732b9d8d8a4526365ad559278`, context
`sha256:646ac89af1aa583ce3780c8542d980559a6782b171131df017daf35293440df1`,
identity-attested corresponding-source artifact
`sha256:535fb5f393bc57d28383cd8f453eac87e196531d44d28e835e54efefcbb22e0a`, and
multi-platform image
`sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe`.
Its linux/amd64 and linux/arm64 images passed all 23 container contracts and zero-vulnerability
image scans. The immutable component scan found curl `8.23.0` clean and retained only the exact
approved Git-for-Windows not-affected result. Candidate success completes the digest-review
prerequisite.

### 4.1.18 Completed 0.1.6 release and promotion evidence

Exact release commit `e693e6b60afdf9c667a913faa4f9652bfd6dc050` and unchanged candidate
manifest `sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe`
completed attempt-1 performance runs `39987447085`, `39987667038`, and `39987819708` with
nearest-rank p95 values of 16, 14, and 13 seconds. Their recomputed 60-sample p95 was 16 seconds.
Every individual and combined result passed the strict release SLO below 18 seconds; the first and
combined results truthfully record that the separate strict engineering target below 15 seconds
was not met.

Protected release run `39988130356`, attempt 1, promoted the reviewed image without rebuilding,
published no Python distribution, verified the unchanged six-package public set on Python 3.12
and 3.13, completed production dogfood, and created immutable product `v0.1.6` and Action
`v1.0.6` at that exact release commit. Its immutable Release retains corresponding source, both
platform manifests, scans, SBOM, provenance, performance evidence, public-package probes, release
attestations, and dogfood verification.

Same-repository proof PR `Parth2412/attest-action-proof#11` retained its blocked-before-check and
no-review denial states, received the project owner's approval for exact head
`65d56307b056a6ec9789d1984758cde9a0a29218`, passed on run `39989199325` attempt 3, and merged as
`a13dbf8d29cd54ea6de59b1fdd56bf7f57496147`. Fork proof PR #12 failed safely on run
`39989723943`, attempt 1, with `ERR-SIGN-301` before repository-controlled content could execute,
and closed unmerged. Protected promotion run `39994508140`, attempt 1, independently revalidated
the release and both proofs, received the required `action-major` environment review, and moved
only `v1` from `203d2deb7dff946dc82c6efc6506bc34adbcd209` to the exact `v1.0.6` release commit.
The preflight and final promotion evidence are retained as separate run artifacts.

### 4.1.19 Filesystem-lock public correction

`ADR-068` amends the completed lifecycle after repeated macOS Python 3.12 process contention
reproduced a lock-acquisition race in public `attest-store==0.1.1`. The corrected source uses an
atomic exclusive create-or-existing-open sequence while retaining no-follow, regular-descriptor,
and advisory-lock validation. The storage API, format, errors, and retrieval semantics do not
change.

The release publishes only `attest-store==0.1.2` and compatibility CLI `0.1.5`, which exact-pins
the corrected store. A new `0.1.7-candidate` must repeat the complete two-platform supply-chain
and runtime gate. Candidate run `40086747745` is retained incomplete evidence: validation,
corresponding source, and component scan passed, but the old-label build reached the 60-minute job
ceiling before emitting a binary. The replacement candidate uses a bounded 90-minute build ceiling
without another runner, cache, privilege, mutable input, or relaxed gate.

Replacement run `40114789855`, attempt 1, passed the complete candidate boundary for source
`62b72c2537176c84bc232f727f223a9ea21ae80b`, context
`sha256:580c0b7881882817ae7ca65dfe1bbdcd06c5bea77556c8b77ff5b04e11cacc73`, identity-attested
corresponding source `sha256:7472c920350b428c850a6f18f2e17693431b0e89761ef52498b009b0ea447805`, and image
`sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356`. Both 23-test architecture
suites and both image scans passed before reviewed digest pinning.

After reviewed digest pinning, the exact protected-main commit and image must pass three fresh
ordered attempt-1 20-job measurements and the combined 60-sample release SLO. Protected release
publishes both Python distributions through their separate Trusted Publishers, verifies exact
public bytes and Python 3.12/3.13 clean installs, promotes without rebuilding to image `0.1.7`,
and creates immutable `v0.1.7`/`v1.0.7` records. Production dogfood, same-repository proof, safe
fork denial, and independent promotion review must complete before `v1` moves from `v1.0.6`.

### 4.1.20 Completed 0.1.7 release and promotion evidence

Exact release commit `c42e52d038f5ecdcc498679cb7648e5b0957d489` and unchanged candidate
manifest `sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356`
completed attempt-1 performance runs `40214718176`, `40214802805`, and `40214887540` with
nearest-rank p95 values of 12, 14, and 14 seconds. Their recomputed 60-sample summary retained p50
11 seconds and p95 14 seconds. Every individual and combined result passed both the engineering
target below 15 seconds and release SLO below 18 seconds.

Protected release run `40215131129`, attempt 1, published only store `0.1.2` and exact-pinned CLI
`0.1.5`, verified exact public bytes and clean Python 3.12/3.13 installations, promoted the
reviewed image without rebuilding, completed production dogfood, and created immutable product
`v0.1.7` and Action `v1.0.7` at the exact release commit. The immutable Release retains the
corresponding source, both platform manifests, scans, SBOM, provenance, performance evidence,
public-package probes, release attestations, and dogfood verification.

Same-repository proof PR `Parth2412/attest-action-proof#13` retained its no-review denial and
passed only after independent review before merge. Fork proof PR #14 failed safely before
repository-controlled execution and closed unmerged. Protected promotion run `40287925165`,
attempt 1, independently revalidated the release and both proofs, received the required
`action-major` environment review, and moved only `v1` from the exact `v1.0.6` release commit to
the exact `v1.0.7` release commit. Its separate preflight and promotion artifacts retain the
review decision, tag response, and evidence digests. This evidence completes `REQ-F11-320`,
`AC-F11-320`, and F-11.

### 4.1.21 Runtime DNS parser security replacement

`ADR-071` reopens F-11 after `GHSA-45c3-73f7-pv4m` / `CVE-2026-114605` established that
`dnspython<2.9.0` can consume excessive CPU while following attacker-controlled DNS compression
pointers. Exact inspection proves the immutable public `0.1.7` Action image contains affected
`dnspython==2.8.0`. The corrected source lock must use exact `dnspython==2.9.0`.

The same audit reports `GHSA-j586-36cw-2gc2` / `CVE-2026-114613` against `msgpack<1.2.3`.
Msgpack enters only through development-only `pip-audit` and is absent from the public runtime; the
corrected lock must nevertheless use exact `msgpack==1.2.3`. Source and real-container contracts
must prove both exact versions and runtime exclusion before a candidate is promotable.

Every existing package, image, tag, Release, Bundle, and evidence record remains immutable. Fresh
Python installations already resolve a corrected dnspython and never install msgpack through an
attest product dependency, so this is an image-only replacement. A unique `0.1.8-candidate` must
repeat the complete two-platform source-correspondence, real-container, scan, SBOM, provenance,
identity-attestation, reviewed digest-pinning, three-run performance, release, dogfood,
same-repository proof, fork-denial, and independent moving-major promotion boundary. No Python
distribution may be built or published for this correction.

Reviewed source PR #172 merged to protected `dev` at
`905c30679d291bce13ad3140703162cf3405e55b`. Automatic candidate run `40674146751`, attempt 1,
then passed validation, public corresponding-source publication and attestation, exact component
scan, the 88-minute multi-platform build, clean amd64/arm64 image scans, both real-container
contracts, SBOM/provenance validation, and identity-bound attestation. It produced context
`sha256:8b863e6dc4733bb7050b27f34863b3db87db7ff069562ce348a98db0642c17bd`, corresponding source
`sha256:7a346ff30f6886f5ab06045b0dfd2be645fd2a9df9a6fdabc1f280562e2ae1af`, and reviewed image
`sha256:1b40c02bfacaae958a2adf9bfc25485fe0c22794db50c19aa401db530ea36c61`.

### 4.2 Two-phase supply chain

1. After implementation lands on protected `dev`, a candidate workflow builds from an explicitly
   enumerated context, lock file, and digest-pinned base image, runs the complete gate, scans the
   image, and emits the context/manifest digests, SBOM, provenance, and GitHub artifact attestation.
2. A second reviewed PR pins that exact digest in `action.yml`; `action.yml` is outside the image
   build context, so the pin does not change the candidate bytes.
3. After the reviewed tree reaches protected `main`, a manually dispatched protected release job
   verifies final context equality and promotes the exact candidate manifest to `0.1.0`; it does
   not substitute a rebuild with a different digest.
4. A build job creates all distributions once. Separate per-package jobs use PyPI Trusted
   Publishing bound to six protected environments; no API token is stored. The first release
   publishes three packages, verifies their public bytes, and then exposes the protected checkpoint
   for registering and approving the remaining three publishers.
5. Only after both PyPI waves succeed, the workflow publishes the public image, creates immutable
   product Release/tag `v0.1.0` and immutable Action tag `v1.0.0`, advances reviewed `v1`, creates
   attest's own release ChangeSet evidence, and verifies that evidence publicly.

Every third-party Action is pinned to a full commit SHA. Release smoke tests install each package
and the CLI into clean supported Python environments and execute the published Action by full SHA.
PyPI's publication attestations complement, but do not replace, the product's self-attestation.

## 5. Requirements

| ID | Requirement |
|---|---|
| `REQ-F11-010` | The Action **MUST** be container-based using the published image, pinned by immutable multi-platform manifest digest, not by tag. |
| `REQ-F11-020` | `run` **MUST** test OIDC before reading repository-controlled data and fail with `ERR-SIGN-301` and a message naming `id-token: write` when absent. |
| `REQ-F11-030` | Every mode **MUST** detect and report shallow or incomplete history with `ERR-CONFIG-008`, naming `fetch-depth: 0`. |
| `REQ-F11-040` | The Action **MUST** expose the §3.5 outputs when each value is earned, including before a policy-violation exit. |
| `REQ-F11-050` | The Action **MUST** post an injection-safe job summary rendering the decision, authorship mode, and review record. |
| `REQ-F11-060` | The Action **MUST NOT** require a repository secret for the core loop; keyless signing uses the workflow identity and publication uses the automatic token passed only through the caller step environment. |
| `REQ-F11-070` | The Action **MUST** support only branch `pull_request`, branch `push`, and exact branch `workflow_dispatch`, validate their immutable context, and reject `pull_request_target`, tags, malformed or inconsistent dispatches, and every unsupported event with `ERR-CONFIG-007`. A dispatch **MUST** bind its closed payload, repository, full ref, branch name/type, selected head SHA, workflow path, and exact `GITHUB_WORKFLOW_REF`; after OIDC succeeds, complete history **MUST** prove the head and its first parent. |
| `REQ-F11-080` | Action versioning **MUST** use immutable `v1.0.0` plus a reviewed `v1` moving-major tag independently of product version `0.1.0`. |
| `REQ-F11-090` | The Action's own release **MUST** be attested with attest and publicly verified. |
| `REQ-F11-100` | The `v1.0.4` Action-step cold-start release gate **MUST** be below 15 seconds p95 under the exact 20-run measurement in `ADR-046`; the pending `v1.0.5` reliability release is amended only by `REQ-F11-280`. |
| `REQ-F11-110` | A real-repository release test **MUST** publish the gate as a required GitHub status check, pin it to the re-observed GitHub Actions App (currently App ID `15368`), and prove a blocking absence or violation prevents merge. Documentation **MUST** state that a non-required gate is advisory. |
| `REQ-F11-120` | The published full-SHA Action and immutable image digest **MUST** make the exact workflow generated by F-10 run unmodified in a fresh repository. The test **MUST** prove exact `GITHUB_WORKFLOW_REF` identity verification, least privileges, no execution of repository content by the privileged Action, and safe failure for a fork without write/OIDC authority. |
| `REQ-F11-130` | The Action **MUST** implement only the closed inputs, mode semantics, path rules, outputs, and policy-exit treatment in §3. |
| `REQ-F11-140` | Release `0.1.0` **MUST** publish exactly the six implemented distributions with exact internal pins, complete metadata, clean-install smoke tests, and PyPI Trusted Publishing; it **MUST NOT** publish or depend on `attest-export`. |
| `REQ-F11-150` | Release **MUST** use the two-phase digest-review process, locked and digest-pinned inputs, separated build/publish jobs, multi-platform image, SBOM, provenance, GitHub artifact attestations, immutable release records, and full-SHA third-party Actions in §4. |
| `REQ-F11-160` | The wrapper **MUST** sanitize its environment, execute no repository content, leak no credentials, and preserve fatal failures when policy violations are configured advisory. |
| `REQ-F11-170` | The correction **MUST** publish only CLI `0.1.1`, immutable Action `v1.0.1`, moving `v1`, and source record `v0.1.1`; it **MUST** retain exact CLI pins to the five `0.1.0` libraries, the immutable `0.1.0` image digest, and the defective immutable `v1.0.0` record. Version-specific public verification and any exact resume **MUST** prove accepted bytes and prior OIDC evidence without re-uploading. |
| `REQ-F11-180` | The pull-request identity correction **MUST** publish only CLI `0.1.2`, immutable Action `v1.0.2`, source record `v0.1.2`, and the exact reviewed image candidate promoted as `0.1.2`; it **MUST** preserve known failed-verification diagnostics without emitting unverified facts, retain the five exact `0.1.0` library pins and every earlier immutable public record, and move `v1` only after the complete replacement proof succeeds. |
| `REQ-F11-190` | The remote-discovery correction **MUST** publish only store `0.1.1`, CLI `0.1.3`, immutable Action `v1.0.3`, source record `v0.1.3`, and the exact reviewed image candidate promoted as `0.1.3`; it **MUST** retain every earlier public artifact and attestation ref, import remote sibling refs without overwrite or `FETCH_HEAD`, preserve import failures locally, and move `v1` only after the complete corrected proof succeeds. |
| `REQ-F11-200` | The cold-start correction **MUST** use the digest-pinned Alpine runtime and exact package set in `ADR-053`, publish no Python distribution, promote only an exact reviewed `0.1.4-candidate` manifest as image `0.1.4`, and create source `v0.1.4` plus immutable Action `v1.0.4` only after the unchanged 20-job p95 gate passes; it **MUST NOT** move `v1` until the complete release, dogfood, public-proof, and performance evidence verifies. |
| `REQ-F11-210` | The repeatability correction **MUST** preserve every `0.1.4`/`v1.0.4` record; build locked cryptography from its hash-locked sdist using the exact removable toolchain and exact matching runtime OpenSSL in `ADR-054`; use only the fail-closed approved pinned system-library linkage as amended by `ADR-059`/`REQ-F11-240` and prove native execution on both architectures; enable in-process CLI execution only for the digest-matched bundled script under isolated Python; pass both-platform container, scan, SBOM, provenance, and identity-attestation gates; and publish only exact reviewed image `0.1.5`, source `v0.1.5`, and Action `v1.0.5` with no Python distribution after the three-run and combined-60-sample performance contract, as amended by `REQ-F11-280`, passes. It **MUST NOT** move `v1` until the complete release, dogfood, public-proof, fork-denial, and performance evidence verifies independently. |
| `REQ-F11-220` | As the `ADR-055` amendment to `REQ-F11-210`, the correction **MUST** publish exactly `attest-sign==0.1.1` and `attest-cli==0.1.4` with the CLI exact-pinning that signer, through their separate protected Trusted Publisher environments; it **MUST** verify exact public bytes and clean installs on Python 3.12 and 3.13, retain validated OIDC evidence for a fresh or exact-resume path, and **MUST NOT** rebuild or upload any other Python distribution. The new unique image candidate and exact merged Action **MUST** repeat every supply-chain and three-run performance gate before any bounded release record is published. |
| `REQ-F11-230` | The Action image **MUST** contain only the closed `ADR-058` trust-seed inputs, verify their exact bytes and complete TUF chain from Sigstore's pinned embedded environment roots during the build, and seed each fresh isolated runtime `HOME` with only the exact approved root-history, snapshot, targets, and selected-target files after rechecking their hashes. Captured timestamp metadata **MUST NOT** enter runtime cache; every invocation **MUST** retain the live next-root probe, live timestamp download, authenticated stale-cache replacement, and refreshed-root final verification. The failed run `37796984054` **MUST NOT** be rerun or counted, and every existing candidate, three-run, combined-60-sample, release, and promotion gate remains unchanged. |
| `REQ-F11-240` | The Action image **MUST** build exact locked `cryptography==50.0.1`, `pydantic-core==2.46.5`, and `rfc3161-client==1.0.8` from their hash-locked source distributions with `ADR-059`'s exact removable toolchain, Rust flags, non-vendored dynamic pinned OpenSSL, and pinned system libgcc. Only the exact `rpds_py.libs` compatibility symlink to `/usr/lib/libgcc_s.so.1` may remain in the closed private-libgcc set; both architectures **MUST** prove direct system-library mapping and native execution. The failed run `37899003696` **MUST NOT** be rerun or counted, and a new unique candidate and exact merged Action **MUST** restart every existing candidate, three-run, combined-60-sample, release, and promotion gate. |
| `REQ-F11-250` | The Action image **MUST** encode exactly its closed pure-Python `attest-runtime.zip` with standard `ZIP_DEFLATED` at compression level 9 while preserving sorted membership, checked-hash bytecode, fixed timestamps, regular-file modes, the closed root set, and in-place imports without runtime extraction. Both architectures **MUST** prove the exact archive and existing runtime contracts. The failed run `37946041636` **MUST NOT** be rerun or counted, and a new unique candidate and exact merged Action **MUST** restart every existing candidate, three-run, combined-60-sample, release, and promotion gate. |
| `REQ-F11-260` | Both deterministic Python archives **MUST** be compiled at optimisation level zero without fine-grained traceback end-line and column tables while retaining assertions, docstrings, source line numbers, checked-hash invalidation, closed sorted membership, fixed timestamps, regular-file modes, DEFLATE level 9, and in-place imports. Both architectures **MUST** pass every existing runtime and supply-chain contract. Failed run `38056326479` **MUST NOT** be rerun or counted; only a new unique candidate and exact merged Action may start a fresh automatic-plus-two-reviewed-dispatch sequence of three consecutive attempt-1 20-job measurements and the combined 60-sample gate. |
| `REQ-F11-270` | The Action **MUST** build unmodified Git `2.52.0` and curl `8.22.0` from `ADR-062`'s exact hash-locked upstream archives using its exact pinned removable toolchain, retain only the bounded Git HTTP(S) transport and its rediscovered loader closure, licences, and component evidence, and preserve certificate verification and every existing Git security control. Both architectures **MUST** prove exact versions, local and verified-HTTPS behavior, forbidden-library absence, four runtime layers with exactly three primary zstd layers, binary hashes/sizes, and loader mapping. Before the binary candidate, CI **MUST** publish and attest a public digest-bound corresponding-source artifact containing the exact archives, licences, hashes, SPDX component evidence, exact OpenVEX, and recipe; the binary **MUST** link it. Immutable CPE-aware Grype **MUST** scan the exact components under the unchanged critical/fixable-high gate; only the exact retained not-affected statement for Git-for-Windows `CVE-2026-62960` may suppress a match, and scanner/database/VEX drift **MUST** fail closed. The immutable release **MUST** re-fetch, verify, retain, and attest the same materials. Failed run `38257587284` **MUST NOT** be rerun or counted; only a new unique candidate and exact merged Action may restart every existing supply-chain and three-run performance gate. |
| `REQ-F11-280` | The hosted-runner evidence contract **MUST** preserve the exact `ADR-062` candidate image, Action-step timing boundary, 20-job sample size, nearest-rank calculation, first-attempt-only rule, and automatic-push-plus-two-reviewed-dispatch order. Every individual run and the combined 60-sample result **MUST** record a strict engineering target below 15 seconds and independently enforce a strict release SLO below 18 seconds. Publication **MUST** require all four SLO results to pass. Evidence **MUST** use schema 2 bound to `REQ-F11-280`/`AC-F11-280` and fail closed on schema 1, mismatched thresholds, incomplete samples, overlapping jobs, or altered identity. Failed run `38570478871` and every earlier performance run **MUST NOT** be rerun, reinterpreted, or counted; only a fresh exact-commit three-run sequence may qualify. |
| `REQ-F11-290` | The security replacement **MUST** preserve every earlier immutable record; lock exactly `certifi==2026.10.19`, `virtualenv==21.14.12`, and resolver-selected `python-discovery==1.6.4`; prove the Action runtime contains the corrected certifi and excludes virtualenv; build and review one unique two-platform `0.1.6-candidate`; repeat every existing candidate, schema-2 performance, release, dogfood, same-repository, and fork-denial gate; publish only image `0.1.6`, source `v0.1.6`, and immutable Action `v1.0.6` with no Python distribution; and move `v1` only after independent protected review. |
| `REQ-F11-300` | The same security replacement **MUST** build against exact `musl-dev==1.2.5-r24`, upgrade the final Action runtime to exact `musl==1.2.5-r24`, retain deterministic installed-version evidence after Alpine package metadata is removed, and reject affected `r23` on both architectures; it **MUST NOT** change ADR-065's candidate identity, release versions, publication boundary, performance thresholds, evidence sequence, immutable history, or independent promotion requirement. |
| `REQ-F11-310` | The same security replacement **MUST** replace only source-built curl `8.22.0` with the official signed, SHA-512-locked curl `8.23.0` archive; preserve Git `2.52.0`, the HTTP/1.1-only feature set, exact toolchain and loader closure, sole Git-for-Windows VEX statement, scan thresholds, release versions, and no-Python-publication boundary; reject `8.22.0` from source, component, runtime, candidate, and release evidence; retain failed run `39829765757`, its raw scan, and attested source artifact as immutable negative evidence; and require a new unique corresponding-source artifact and two-platform candidate before the unchanged ADR-065 lifecycle continues. |
| `REQ-F11-320` | The filesystem-lock correction **MUST** preserve every earlier immutable record; publish exactly `attest-store==0.1.2` and `attest-cli==0.1.5` with the CLI exact-pinning that store and every other internal version unchanged; build one unique two-platform `0.1.7-candidate` under a 90-minute build ceiling and every existing supply-chain/runtime gate; retain cancelled run `40086747745` as incomplete non-promotable evidence; pass the unchanged schema-2 three-run performance contract; publish through the two separate protected Trusted Publishers without `skip-existing`; verify exact public bytes and clean Python 3.12/3.13 installs; promote without rebuilding to image `0.1.7` and immutable `v0.1.7`/`v1.0.7`; and move `v1` only after dogfood, same-repository proof, fork denial, and independent protected review. |
| `REQ-F11-330` | The post-release source baseline **MUST** replace affected build-only `setuptools==84.0.0` with exact patched `84.1.0` and affected development-only `virtualenv==21.14.12` with exact patched `21.14.13`; retain resolver-selected `python-discovery==1.6.4`; prove setuptools, virtualenv, and python-discovery remain absent from the published Action runtime; pass the complete repository and real-container contracts; and close both alerts through a reviewed protected-source merge. It **MUST NOT** mutate or republish any existing package, image, Release, immutable tag, or evidence record. |
| `REQ-F11-340` | The runtime security replacement **MUST** preserve every earlier immutable record; lock exact patched `dnspython==2.9.0` and development-only `msgpack==1.2.3`; prove the Action runtime contains exact dnspython and excludes msgpack; pass a clean dependency audit; build and review one unique two-platform `0.1.8-candidate`; repeat every existing source-correspondence, real-container, scan, SBOM, provenance, identity, schema-2 performance, release, dogfood, same-repository, fork-denial, and independent-promotion gate; publish only image `0.1.8`, product `v0.1.8`, and immutable Action `v1.0.8` with no Python distribution; and move `v1` only after independent protected review. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F11-010` | A manifest contract test proves the container image is an immutable manifest digest and the runtime is exec-form. |
| `AC-F11-020` | A workflow missing `id-token: write` fails before a repository-read marker with `ERR-SIGN-301` and a message containing that exact permission. |
| `AC-F11-030` | A default-depth checkout produces `ERR-CONFIG-008` and the `fetch-depth: 0` remediation in all modes. |
| `AC-F11-040` | Outputs are populated as specified in success and violation runs and remain empty before their prerequisite stage. |
| `AC-F11-050` | The real-run summary contains the decision and authorship/review facts, and adversarial text cannot create markup or workflow commands. |
| `AC-F11-060` | An end-to-end `run` workflow with zero repository secrets completes successfully without credential output. |
| `AC-F11-070` | Branch PR, push, and exact branch-dispatch fixtures succeed and a dispatch produces the same ChangeSet coordinates as the matching push; tag, root-commit, incomplete-history, extra/missing-field, path-traversal, repository/ref/SHA/workflow mismatch, create/delete, malformed, unsupported, and `pull_request_target` fixtures fail with `ERR-CONFIG-007` or `ERR-CONFIG-008` as specified. |
| `AC-F11-080` | Product `v0.1.0`, Action `v1.0.0`, and moving `v1` resolve to the same released commit; immutable releases and a tag ruleset prevent update/deletion of immutable records, while only the reviewed release procedure may move `v1`. |
| `AC-F11-090` | The release workflow produces attest evidence for the released source and artifacts, and its public identity-bound verification succeeds. |
| `AC-F11-100` | Twenty retained hosted-runner measurements include image pull and meet the documented nearest-rank p95 target. |
| `AC-F11-110` | In public `Parth2412/attest-action-proof`, a `github-actions[bot]` (numeric ID `41898282`) pull request is unmergeable both before the required check appears and on its initial no-review exit `3`, then becomes mergeable only after the project owner's independent approval and a successful rerun of the re-observed App-pinned check. |
| `AC-F11-120` | A release-gated test in `Parth2412/attest-action-proof` runs `attest init` with the published Action SHA and reviewed checkout SHA, commits its three files unchanged, proves a same-repository PR succeeds with the exact workflow identity, proves a malicious repository fixture is never executed, and proves the `zettacore-labs/attest-action-proof` fork PR fails before repository reads without credential exposure or elevated event use. |
| `AC-F11-130` | Table-driven container tests cover every valid mode/input combination, every invalid combination and path, both policy settings, every output boundary, and fatal-error preservation. |
| `AC-F11-140` | PyPI and clean-environment probes find exactly the six `0.1.0` distributions, matching metadata and hashes, with no export dependency; Trusted Publisher evidence is retained. |
| `AC-F11-150` | Candidate and release workflows prove final build-context equality and exact manifest promotion, both architectures, locked inputs, SBOM, provenance, GitHub attestations, separated authority, immutable records, and full-SHA Action pins. |
| `AC-F11-160` | Adversarial fixtures prove no repository executable or import path runs, no workflow command is injected, no token is emitted, and non-policy failures cannot be neutralized. |
| `AC-F11-170` | Contract tests prove Action metadata has no `github` context reference and the exact generated workflow supplies `GITHUB_TOKEN` through step `env`; public records and a fresh proof repository verify the bounded versions, unchanged digest, blocked-before-check state, denial state, approval transition, malicious fixture, and safe fork failure. |
| `AC-F11-180` | Contract and container tests prove the generated identity matches only the intended PR workflow ref, known failed verification retains its stable code with empty outputs, the CLI/image candidate has the bounded `0.1.2` artifact set and supply-chain evidence, and public records plus a fresh proof establish blocked-before-check, no-review denial, independent approval, success, malicious-content non-execution, and safe fork failure before `v1` moves. |
| `AC-F11-190` | Two fresh CI-like repositories publish distinct denied and approved Bundles for one ChangeSet under immutable base and sibling refs; the store/CLI/Image/Action `0.1.1`/`0.1.3` release set verifies publicly, and a new bot-authored proof completes blocked-before-check, no-review denial, independent approval, successful rerun, malicious-content non-execution, and safe fork failure before `v1` moves. |
| `AC-F11-200` | The retained candidate proves the exact Alpine base and package, both target platforms, clean scans, SBOM, provenance, and identity-bound attestation; the exact merged Action then passes 20 fresh attempt-1 hosted measurements below 15 s p95 before the image-only `0.1.4`/Action `v1.0.4` release and reviewed `v1` promotion complete without any new PyPI file. |
| `AC-F11-210` | Tests and retained candidate evidence prove the locked source build, absence of build tools, exact dynamic OpenSSL, the `ADR-059`-amended approved system-library linkage with native-module execution, three balanced zstd layers, digest-guarded/fallback CLI boundaries, both target platforms, clean scans, SBOM, provenance, and identity-bound attestation; the exact merged Action and candidate digest then satisfy `AC-F11-280` before the bounded `0.1.5`/Action `v1.0.5` release and independently reviewed `v1` promotion complete without an unapproved PyPI file or mutation of an earlier record. |
| `AC-F11-220` | Package and workflow contracts prove the exact signer/CLI versions and dependency, unchanged-distribution exclusion, separate protected OIDC publishers, no `skip-existing`, exact public-byte comparison, Python 3.12/3.13 clean installs, and validated prior-run recovery evidence; the new candidate, three-run performance proof, immutable `0.1.5`/`v0.1.5`/`v1.0.5` records, dogfood, public proof, fork denial, and independent `v1` promotion then complete without mutating an earlier artifact. |
| `AC-F11-230` | Build and unit tests verify both captured TUF chains from the pinned embedded roots at the recorded instant, exact source hashes and target length/hashes, closed source/runtime path sets, tamper failure, and timestamp exclusion; both platform images contain the validated inputs, every isolated Action home receives exactly nine re-hashed non-timestamp files, and the new candidate plus exact merged Action repeat every existing supply-chain and performance gate before publication. |
| `AC-F11-240` | Dockerfile and both-platform real-container tests prove all three exact native packages build from locked source with the approved compiler/OpenSSL settings, only the `rpds-py` private libgcc name remains and resolves to pinned system libgcc, every affected module maps approved system libraries and executes successfully with offline trust initialization, the primary compressed layers remain balanced, and the new candidate and exact merged Action restart and pass every supply-chain and performance gate before publication. |
| `AC-F11-250` | Dockerfile and both-platform real-container tests prove the runtime archive uses DEFLATE level 9, contains exactly the closed deterministic bytecode members and metadata, imports every representative archived package in place, introduces no extraction path, and preserves native, trust, and security behavior; retained candidate evidence records exact archive/image/layer sizes, and the new candidate plus exact merged Action restart and pass every supply-chain and performance gate before publication. |
| `AC-F11-260` | Build, archive, and both-platform real-container tests prove both archives omit only fine-grained debug ranges while retaining optimisation level zero, active assertions, docstrings, line numbers, deterministic metadata, exact members, imports, native execution, trust, and security behavior; retained evidence records exact archive/image/layer sizes, and the new candidate plus exact merged Action pass every supply-chain gate before a fresh compliant three-run sequence may begin. |
| `AC-F11-270` | Unit, Dockerfile, both-platform real-container, candidate, and release tests prove upstream archive hashes before extraction; exact Git/curl versions, licences, component identities, build options, local and certificate-verified HTTPS transport; the rediscovered loader closure and forbidden-library absence; three primary zstd layers plus the entrypoint layer; retained per-platform image, layer, binary, and loader evidence; public source-before-binary publication, digest linkage, identity attestation, source correspondence, immutable CPE-aware Grype output, the single exact OpenVEX statement, scanner/VEX drift rejection, and immutable release retention. The unique candidate and exact merged Action must then pass every unchanged supply-chain gate before a fresh compliant three-run sequence begins. |
| `AC-F11-280` | Workflow and evidence-parser tests prove schema 2 records both exact thresholds and independently derived booleans, accepts p95 at or above 15 seconds only while it remains strictly below 18 seconds, rejects p95 at or above 18 seconds, rejects old or altered evidence, and requires three ordered, non-overlapping, attempt-1 20-job results plus the recomputed combined 60-sample SLO before release. Retained evidence proves the fresh sequence uses one exact merged commit and the unchanged reviewed image. |
| `AC-F11-290` | Lock and container contracts prove the three exact reviewed dependency versions, corrected certifi runtime, and virtualenv exclusion; retained candidate evidence proves both architectures, complete real-container behavior, clean runtime and component scans, source correspondence, SBOM, provenance, identity attestation, and exact reviewed digest pinning; three fresh attempt-1 performance runs and the combined 60 samples pass the unchanged release SLO; immutable `0.1.6`/`v0.1.6`/`v1.0.6`, dogfood, public proof, and fork-denial evidence verify before reviewed `v1` promotion; and public-package probes prove no new Python file was published. |
| `AC-F11-300` | Dockerfile and both-platform real-container contracts prove the two exact `musl-dev==1.2.5-r24` build pins, exact final `musl==1.2.5-r24` installation, retained single-line `musl-1.2.5-r24` version record, absence of affected `r23`, and unchanged minimized-runtime/native behavior; the candidate's clean scans, SBOM, provenance, and identity evidence then feed the complete unchanged ADR-065 lifecycle. |
| `AC-F11-310` | Source-preparation, Dockerfile, component-gate, candidate/release-validator, workflow, and both-platform real-container contracts prove curl `8.23.0`'s exact archive hash, source root, purl, CPE, licence, compiled version, unchanged protocols/features, loader closure, and clean fixable-High component result while rejecting `8.22.0`; retained evidence proves run `39829765757` stopped before a binary and a new protected-`dev` commit created distinct corresponding-source and candidate identities before any performance or release step. |
| `AC-F11-320` | Package, lock, workflow, and container contracts prove the exact two-distribution graph, closed manifests, separate OIDC publishers, 90-minute candidate build ceiling, `0.1.7-candidate` identity, and absence of unrelated publication; retained evidence proves run `40086747745` emitted no candidate, the new attempt-1 candidate passes both-platform source/runtime/scan/SBOM/provenance/attestation gates, three fresh performance runs plus all 60 samples pass the release SLO, public store/CLI bytes and clean installs match, immutable `0.1.7`/`v0.1.7`/`v1.0.7` plus dogfood and both public proofs verify, and independent review precedes moving `v1`. |
| `AC-F11-330` | Workspace, lock, Dockerfile, and real-container contracts prove exact setuptools `84.1.0`, virtualenv `21.14.13`, retained python-discovery `1.6.4`, removal of build tooling, exclusion of development tooling from runtime, and no product-version or publication change; the complete pull-request gate and dependency audit pass before protected merge and both superseded dependency pull requests close. |
| `AC-F11-340` | Lock and real-container contracts prove exact dnspython `2.9.0`, exact development-only msgpack `1.2.3`, msgpack runtime exclusion, the updated deterministic runtime archive, and a clean dependency audit; retained candidate evidence proves both architectures, complete runtime behavior, clean image and component scans, source correspondence, SBOM, provenance, identity attestation, and reviewed digest pinning; three fresh attempt-1 runs and their combined 60 samples pass the unchanged release SLO; immutable `0.1.8`/`v0.1.8`/`v1.0.8`, dogfood, public-package non-publication, same-repository proof, and fork-denial evidence verify before independently reviewed `v1` promotion. |

## 7. Evidence retention

F-11 retains the candidate and release run URLs and IDs; repository, fork, pull-request, commit,
tag, release, image, package, SBOM, provenance, and Bundle identifiers; status-check App identity and
branch-protection response; exact generated files; success, blocked, fork-failure, malicious-fixture,
and missing-permission logs; outputs; the historical 20-job release measurement; every immutable
`ADR-054`–`ADR-063` performance run; and the qualifying three `ADR-063` 20-job measurements plus
their combined 60-sample result. Evidence is indexed from the
immutable GitHub Release and contains no credential. For the `ADR-055` amendment it also retains
the exact signer/CLI build hashes, PyPI public-byte verification, clean-install results, protected
Trusted Publisher context, and any validated prior publication run used for exact recovery.
For `ADR-057` it additionally retains both-platform private-library paths, exact link targets,
dynamic loader mappings, and successful native-module and offline-trust execution.
For `ADR-058` it additionally retains the closed seed manifest and hashes, captured metadata
versions, build-verification result, exact nine-file runtime mapping, failed run `37796984054`,
and evidence that live root and timestamp refresh remain mandatory.
For `ADR-059` it additionally retains exact source-build inputs and flags, native binary and layer
sizes, both-platform loader mappings and native execution, failed run `37899003696`, and the fresh
candidate and performance sequence.
For `ADR-060` it additionally retains exact runtime-archive method, level, membership, metadata,
archive/image/layer sizes, both-platform import and native-runtime execution, failed run
`37946041636`, and the fresh candidate and performance sequence.
For `ADR-061` it additionally retains archive debug-range and optimisation proofs, exact
archive/image/layer sizes, guarded process-context selection and fallback proofs, closed dispatch
payload and first-parent proofs, failed run `38056326479`, and the fresh candidate and performance
sequence.
For `ADR-062` it additionally retains exact Git/curl source archives, hashes, licences, build
recipe and toolchain, public source-artifact digest and identity attestation, component SPDX and
OpenVEX plus the raw Grype scan, both-platform versions/binary hashes/sizes/loader mappings, all four zstd layer descriptors,
failed run `38257587284`, and the fresh candidate and performance sequence.
For `ADR-063` it additionally retains failed run `38570478871`, evidence schema and requirement
identity, both exact thresholds and pass results, the three fresh run IDs, all 60 measurements,
and the recomputed combined summary.
For `ADR-065` it additionally retains advisory identity and affected/fixed versions, the exact
lock diff and dependency audit, both-platform corrected runtime version and development-tool
exclusion, the unique candidate and context/image/source digests, all repeated supply-chain and
performance evidence, public-package non-publication probes, release dogfood, same-repository and
fork proof, and the independently reviewed moving-major promotion.
For `ADR-066` it additionally retains Alpine's advisory/package identity, affected and fixed musl
revisions, exact Dockerfile pins, both-platform installed-version records, runtime and component
scan outputs, and the unchanged ADR-065 candidate-through-promotion evidence.
For `ADR-067` it additionally retains curl's advisory identity, affected/fixed versions, upstream
signature fingerprint and exact archive hash, failed run `39829765757`, its raw component scan and
source-artifact digest, evidence that no binary candidate was created, and the new source,
component, both-platform runtime, candidate, and unchanged ADR-065 lifecycle evidence.
For `ADR-068` it additionally retains the Darwin failure reproduction, exact locking fix and
tests, cancelled run `40086747745` and its successful pre-build evidence, exact store/CLI build
hashes and Trusted Publisher contexts, new source/context/image identities, both-platform gates,
three-run and combined performance evidence, public byte/installation verification, immutable
release and dogfood, same-repository and fork proofs, and independently reviewed `v1` promotion.
For `ADR-071` it additionally retains both advisory identities and fixed versions, exact public
`0.1.7` runtime inspection, the lock diff and clean audit, both-platform exact dnspython and msgpack
exclusion proofs, candidate source/context/image identities, scans, SBOM, provenance, attestation,
three-run and combined performance evidence, Python non-publication probes, immutable release and
dogfood, both public proofs, and independently reviewed `v1` promotion.

## 8. Out of scope

GitLab and Bitbucket templates (v1.1), marketplace listing optimisation, self-hosted runner
specialisation, publishing `attest-export` before F-12, and granting fork pull requests signing or
write authority.

## 9. Definition of Done

- [x] All `REQ-F11-*` implemented, all `AC-F11-*` green and traced
- [x] The exact F-10-generated and copy-pasteable README workflows run unmodified on a fresh repository
- [x] The six packages and multi-platform image are publicly installable by immutable version/digest
- [x] Dogfood release evidence verifies publicly
- [x] A real repository demonstrates blocked and successful merge states through the required,
  expected-App-pinned gate check
- [x] The `zettacore-labs` fork proof fails safely before repository reads
- [x] The retained 20-run measurement meets p95 below 15 seconds
- [x] The image-only `0.1.4` / Action `v1.0.4` correction satisfies `ADR-053` without republishing Python packages
- [x] Cross-cutting obligations satisfied for the bounded correction
- [x] Candidate run `38038325243` satisfies the locked three-package source build, closed pinned system-library linkage, verified non-timestamp TUF seed, deterministic compressed pure-Python runtime archive, native runtime, two-platform, security, and supply-chain boundary in `ADR-054`–`ADR-060`
- [x] Candidate run `38250635610` satisfies the `ADR-061` archive, guarded process-boundary, branch-dispatch, two-platform, security, and supply-chain contracts
- [x] Candidate run `38529646263` satisfies `ADR-062` source correspondence, minimal Git/HTTPS transport, component scan, both-platform loader/layer evidence, and every prior supply-chain contract
- [x] Candidate run `39906806331` satisfies `ADR-065`–`ADR-067` corrected certifi, musl, curl, source-correspondence, 23-test both-platform runtime, zero-vulnerability image-scan, component-scan, SBOM, provenance, and identity-attestation gates for the unique `0.1.6-candidate`
- [x] Three fresh consecutive attempt-1 20-job runs and their combined 60-sample result each remain strictly below the 18-second nearest-rank p95 release SLO, with the strict 15-second engineering target recorded independently
- [x] Exact signer `0.1.1`, CLI `0.1.4`, image `0.1.5`, source `v0.1.5`, immutable Action `v1.0.5`, dogfood, public proof, fork denial, and reviewed `v1` promotion complete without another Python publication
- [x] Exact corrected lock, image `0.1.6`, source `v0.1.6`, immutable Action `v1.0.6`, dogfood, public proof, fork denial, and independently reviewed `v1` promotion complete without a Python publication
- [x] Candidate run `40114789855` satisfies `ADR-068` source correspondence, exact context, 23-test both-platform runtime, zero-vulnerability image scans, component policy, SBOM, provenance, and identity-attestation gates for the unique `0.1.7-candidate`
- [x] Store `0.1.2`, exact-pinned CLI `0.1.5`, image `0.1.7`, immutable `v0.1.7`/`v1.0.7`, dogfood, public proof, fork denial, and independently reviewed `v1` promotion complete under `ADR-068`
- [x] Attempt-1 candidate run `40674146751` proves the exact ADR-071 source, context, corresponding-source, component, two-platform runtime/scan, SBOM, provenance, and identity-attestation boundaries before reviewed digest pinning
- [ ] Exact patched lock, image `0.1.8`, immutable `v0.1.8`/`v1.0.8`, dogfood, public-package non-publication, both public proofs, and independently reviewed `v1` promotion complete under `ADR-071`

Completion evidence: release performance run `36761068084` attempt 1 measured p50 11 s and
nearest-rank p95 14 s on release commit `4e73dcaf888f15967da66826d48cca5ac6684fcb`; recovery run
`36849857414` completed the immutable release; public proof PR #6 and fork-denial PR #7 established
the required merge states; protected promotion run `36872903768` moved `v1` to immutable
`v1.0.4` after review. Post-release monitoring remains fail-closed: run `36872334911` measured p95
16 s and run `36905961561` measured p95 17 s. Run `37796984054` measured p50 12 s and p95 16 s
after the `ADR-057` candidate. Run `37899003696` measured p50 11 s and p95 17 s after the
`ADR-058` candidate. Run `37946041636` measured p50 12 s and p95 16 s after the `ADR-059`
candidate. Run `38056326479` measured p50 11 s and p95 15 s after the `ADR-060` candidate and did
not start the required three-run sequence. Run `38257587284` measured p50 10 s and p95 17 s after
the `ADR-061` candidate and likewise remains excluded. Run `38570478871` measured p50 11 seconds
and p95 17 seconds for the exact `ADR-062` image and remains immutable negative evidence under the
then-current 15-second contract. Accepted `ADR-054`–`ADR-063` track the bounded repeatability
correction without altering the retained `v1.0.4` release gate or any immutable
public record. Candidate run `37904158120`, attempt 1, passed all supply-chain gates for exact
source `6ec6074185cfd25e7f66c8eac2e0666dfa194a6f`, context
`sha256:c2c6240d341ae0fa066f6121a8d0d1c5b56aff598dd8f5a37598b01970f42fdc`, and manifest
`sha256:ac199137b3a1dda9bf091bf5c7a7858c77ea6446f4f7f0d98463aa9594bf63a2`.
Candidate run `38038325243`, attempt 1, passed all `ADR-060` supply-chain gates for exact source
`57ab2e08c297a2bf2131d2ea942d9e439d9c8faf`, context
`sha256:58acc9a031c2d193f7160cffb16cd709ef7d1ce1dae6bb4cc92196b18a77b6bf`, and manifest
`sha256:06581569a1382003b8537e016ce15b159066c275e186fbc27f8810da0105d5ab`.
Pre-candidate automatic runs `38225190032` and `38249545348`, attempt 1, each measured p50 12 s
and p95 16 s against that superseded manifest and remain excluded. Candidate run `38250635610`,
attempt 1, passed all `ADR-061` supply-chain gates for exact source
`b1d5475da39b2e9522482894dc675c73ecb118a1`, context
`sha256:f6206c3597e520322a4acfc7b40037a7b5fdd5621220eb9015c2595ef1d8ea7b`, and manifest
`sha256:10dade4e41415b68735f784f32a5667496ee4c36d60dba1b805660af092da584`.
Candidate run `38529646263`, attempt 1, passed all `ADR-062` supply-chain gates for exact source
`49139761393b1f18f28f6bc06dfc1ff37166aa1b`, context
`sha256:25e8aec09b88f9182e10e096cb4336ef0cc9fbd0ea6f5498ab6dcf61a2c6c78b`, manifest
`sha256:6e1656ab5da1d5abc43c0ec36e6f3010f1f52c2528ff0e868eb2f62b5754906a`, and public source
artifact `sha256:0855c9c357f8764b18f288c6b13dd5a0859424f12264fa3140e08680637d0457`.

Candidate run `39906806331`, attempt 1, passed all `ADR-065`–`ADR-067` supply-chain gates for
exact source `ae456176d0faefb732b9d8d8a4526365ad559278`, context
`sha256:646ac89af1aa583ce3780c8542d980559a6782b171131df017daf35293440df1`, manifest
`sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe`, and public source
artifact `sha256:535fb5f393bc57d28383cd8f453eac87e196531d44d28e835e54efefcbb22e0a`.

The qualifying `ADR-063` sequence measured exact release commit
`203d2deb7dff946dc82c6efc6506bc34adbcd209` and the unchanged candidate manifest. Automatic run
`38709056956` and reviewed dispatches `38709259244` and `38709401770`, all attempt 1, retained 20
successful samples each at p95 15, 14, and 16 seconds. Their recomputed 60-sample summary retained
p50 10 seconds and p95 16 seconds. Every result passed the strict release SLO below 18 seconds;
the first, third, and combined summaries independently recorded that the strict engineering target
below 15 seconds was not met.

Release run `38709868210`, attempt 1, published only signer `0.1.1` and CLI `0.1.4`, promoted the
exact reviewed image as `0.1.5` without rebuilding, created immutable `v0.1.5` and `v1.0.5` records,
and completed clean Python 3.12/3.13 verification, dogfood, asset attestation, public verification,
and immutable evidence publication. Public proof PR `Parth2412/attest-action-proof#8` retained the
no-review denial, passed run `38711403197` attempt 3 only after independent approval, and merged as
`604dab14ac52489255e8f792c5907eeb109f91c7`; fork proof PR #9 retained failure run `38735753424`,
attempt 1, before repository-controlled execution. Protected promotion run `38738669979`, attempt
1, independently revalidated the release and proof, received the required environment approval,
and moved `v1` from `4e73dcaf888f15967da66826d48cca5ac6684fcb` to exact release commit
`203d2deb7dff946dc82c6efc6506bc34adbcd209`. `ADR-064` closes F-11 on this immutable evidence.

The `ADR-068` sequence measured exact release commit
`c42e52d038f5ecdcc498679cb7648e5b0957d489` and unchanged candidate manifest
`sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356`. Runs
`40214718176`, `40214802805`, and `40214887540`, all attempt 1, retained 20 samples each at p95
12, 14, and 14 seconds; their combined 60-sample summary retained p50 11 seconds and p95 14
seconds. Protected release run `40215131129`, attempt 1, published store `0.1.2`, CLI `0.1.5`,
image `0.1.7`, product `v0.1.7`, and Action `v1.0.7` at the exact release commit. Public proof PR
#13 passed only after review, fork proof PR #14 failed safely, and independently approved promotion
run `40287925165`, attempt 1, moved reviewed `v1` to the exact release commit. `ADR-068` closes
F-11 on this immutable evidence.
