# BRD-F11 — GitHub Action Packaging

| Field | Value |
|---|---|
| Document ID | `BRD-F11` |
| Feature | `F-11` |
| Milestone | M2 |
| Package | `action/` |
| Depends on | `F-06`, `F-07`, `F-09`, `F-10` |
| Status | **In Progress** · `v1.0.4` complete; bounded `ADR-054`–`ADR-059` correction underway |

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

Only branch `pull_request` and branch `push` events are supported. `pull_request_target`, tag
pushes, branch creation/deletion, missing before/after objects, malformed or inconsistent payloads,
and every other event fail closed with `ERR-CONFIG-007`. Pull-request context uses the F-04 exact
resolver. Push context is derived only from the validated event repository, before/after commits,
and local git objects; an all-zero before or after object is invalid.

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
| `ERR-CONFIG-007` | Unsupported, malformed, inconsistent, or forbidden Action input/event | 2 | Use only the exact §3.1 inputs on a branch `pull_request` or branch `push` event. |
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

`ADR-053` therefore replaces the digest-pinned Debian-slim runtime with the validated,
digest-pinned `python:3.12.14-alpine3.23` base and exact `git=2.52.0-r0` package without changing
the Python package graph or Action interface. A fresh candidate must carry the truthful
`0.1.4-candidate` OCI label. The exact merged `main` Action and candidate digest must pass the
unchanged 20-job p95 gate before publication.

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

The exact reviewed candidate must pass real-container cryptographic contracts, both architecture
scans, SBOM/provenance validation, and identity-bound attestation. After its digest is pinned by a
reviewed `main` commit, the automatic push measurement and two ordered reviewed dispatches must
form three consecutive attempt-1 20-job measurements. Each run and the combined 60 samples must
have nearest-rank p95 below 15 seconds. Only then may the exact manifest be promoted without
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
| `REQ-F11-070` | The Action **MUST** support only branch `pull_request` and branch `push`, validate their exact immutable context, and reject `pull_request_target` and every unsupported event with `ERR-CONFIG-007`. |
| `REQ-F11-080` | Action versioning **MUST** use immutable `v1.0.0` plus a reviewed `v1` moving-major tag independently of product version `0.1.0`. |
| `REQ-F11-090` | The Action's own release **MUST** be attested with attest and publicly verified. |
| `REQ-F11-100` | Action-step cold start **MUST** be below 15 seconds p95 under the exact 20-run measurement in `ADR-046`. |
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
| `REQ-F11-210` | The repeatability correction **MUST** preserve every `0.1.4`/`v1.0.4` record; build locked cryptography from its hash-locked sdist using the exact removable toolchain and exact matching runtime OpenSSL in `ADR-054`; use only the fail-closed approved pinned system-library linkage as amended by `ADR-059`/`REQ-F11-240` and prove native execution on both architectures; enable in-process CLI execution only for the digest-matched bundled script under isolated Python; pass both-platform container, scan, SBOM, provenance, and identity-attestation gates; and publish only exact reviewed image `0.1.5`, source `v0.1.5`, and Action `v1.0.5` with no Python distribution after three consecutive attempt-1 20-job measurements and their combined 60 samples each meet p95 below 15 seconds. It **MUST NOT** move `v1` until the complete release, dogfood, public-proof, fork-denial, and performance evidence verifies independently. |
| `REQ-F11-220` | As the `ADR-055` amendment to `REQ-F11-210`, the correction **MUST** publish exactly `attest-sign==0.1.1` and `attest-cli==0.1.4` with the CLI exact-pinning that signer, through their separate protected Trusted Publisher environments; it **MUST** verify exact public bytes and clean installs on Python 3.12 and 3.13, retain validated OIDC evidence for a fresh or exact-resume path, and **MUST NOT** rebuild or upload any other Python distribution. The new unique image candidate and exact merged Action **MUST** repeat every supply-chain and three-run performance gate before any bounded release record is published. |
| `REQ-F11-230` | The Action image **MUST** contain only the closed `ADR-058` trust-seed inputs, verify their exact bytes and complete TUF chain from Sigstore's pinned embedded environment roots during the build, and seed each fresh isolated runtime `HOME` with only the exact approved root-history, snapshot, targets, and selected-target files after rechecking their hashes. Captured timestamp metadata **MUST NOT** enter runtime cache; every invocation **MUST** retain the live next-root probe, live timestamp download, authenticated stale-cache replacement, and refreshed-root final verification. The failed run `37796984054` **MUST NOT** be rerun or counted, and every existing candidate, three-run, combined-60-sample, release, and promotion gate remains unchanged. |
| `REQ-F11-240` | The Action image **MUST** build exact locked `cryptography==50.0.1`, `pydantic-core==2.46.5`, and `rfc3161-client==1.0.8` from their hash-locked source distributions with `ADR-059`'s exact removable toolchain, Rust flags, non-vendored dynamic pinned OpenSSL, and pinned system libgcc. Only the exact `rpds_py.libs` compatibility symlink to `/usr/lib/libgcc_s.so.1` may remain in the closed private-libgcc set; both architectures **MUST** prove direct system-library mapping and native execution. The failed run `37899003696` **MUST NOT** be rerun or counted, and a new unique candidate and exact merged Action **MUST** restart every existing candidate, three-run, combined-60-sample, release, and promotion gate. |

## 6. Acceptance criteria

| ID | Criterion |
|---|---|
| `AC-F11-010` | A manifest contract test proves the container image is an immutable manifest digest and the runtime is exec-form. |
| `AC-F11-020` | A workflow missing `id-token: write` fails before a repository-read marker with `ERR-SIGN-301` and a message containing that exact permission. |
| `AC-F11-030` | A default-depth checkout produces `ERR-CONFIG-008` and the `fetch-depth: 0` remediation in all modes. |
| `AC-F11-040` | Outputs are populated as specified in success and violation runs and remain empty before their prerequisite stage. |
| `AC-F11-050` | The real-run summary contains the decision and authorship/review facts, and adversarial text cannot create markup or workflow commands. |
| `AC-F11-060` | An end-to-end `run` workflow with zero repository secrets completes successfully without credential output. |
| `AC-F11-070` | Branch PR and push fixtures succeed; tag, create/delete, malformed, inconsistent, unsupported, and `pull_request_target` fixtures fail with `ERR-CONFIG-007`. |
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
| `AC-F11-210` | Tests and retained candidate evidence prove the locked source build, absence of build tools, exact dynamic OpenSSL, the `ADR-059`-amended approved system-library linkage with native-module execution, three balanced zstd layers, digest-guarded/fallback CLI boundaries, both target platforms, clean scans, SBOM, provenance, and identity-bound attestation; the exact merged Action and candidate digest then pass three consecutive fresh attempt-1 20-job hosted measurements individually and as a combined 60-sample set below 15 s p95 before the bounded `0.1.5`/Action `v1.0.5` release and independently reviewed `v1` promotion complete without an unapproved PyPI file or mutation of an earlier record. |
| `AC-F11-220` | Package and workflow contracts prove the exact signer/CLI versions and dependency, unchanged-distribution exclusion, separate protected OIDC publishers, no `skip-existing`, exact public-byte comparison, Python 3.12/3.13 clean installs, and validated prior-run recovery evidence; the new candidate, three-run performance proof, immutable `0.1.5`/`v0.1.5`/`v1.0.5` records, dogfood, public proof, fork denial, and independent `v1` promotion then complete without mutating an earlier artifact. |
| `AC-F11-230` | Build and unit tests verify both captured TUF chains from the pinned embedded roots at the recorded instant, exact source hashes and target length/hashes, closed source/runtime path sets, tamper failure, and timestamp exclusion; both platform images contain the validated inputs, every isolated Action home receives exactly nine re-hashed non-timestamp files, and the new candidate plus exact merged Action repeat every existing supply-chain and performance gate before publication. |
| `AC-F11-240` | Dockerfile and both-platform real-container tests prove all three exact native packages build from locked source with the approved compiler/OpenSSL settings, only the `rpds-py` private libgcc name remains and resolves to pinned system libgcc, every affected module maps approved system libraries and executes successfully with offline trust initialization, the primary compressed layers remain balanced, and the new candidate and exact merged Action restart and pass every supply-chain and performance gate before publication. |

## 7. Evidence retention

F-11 retains the candidate and release run URLs and IDs; repository, fork, pull-request, commit,
tag, release, image, package, SBOM, provenance, and Bundle identifiers; status-check App identity and
branch-protection response; exact generated files; success, blocked, fork-failure, malicious-fixture,
and missing-permission logs; outputs; the historical 20-job release measurement; and all three
ADR-054–ADR-059 20-job measurements plus the combined 60-sample result. Evidence is indexed from the
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

## 8. Out of scope

GitLab and Bitbucket templates (v1.1), marketplace listing optimisation, self-hosted runner
specialisation, publishing `attest-export` before F-12, and granting fork pull requests signing or
write authority.

## 9. Definition of Done

- [ ] All `REQ-F11-*` implemented, all `AC-F11-*` green and traced
- [x] The exact F-10-generated and copy-pasteable README workflows run unmodified on a fresh repository
- [x] The six packages and multi-platform image are publicly installable by immutable version/digest
- [x] Dogfood release evidence verifies publicly
- [x] A real repository demonstrates blocked and successful merge states through the required,
  expected-App-pinned gate check
- [x] The `zettacore-labs` fork proof fails safely before repository reads
- [x] The retained 20-run measurement meets p95 below 15 seconds
- [x] The image-only `0.1.4` / Action `v1.0.4` correction satisfies `ADR-053` without republishing Python packages
- [ ] Cross-cutting obligations satisfied for the bounded correction
- [ ] The new `0.1.5-candidate` satisfies the locked three-package source build, closed pinned system-library linkage, verified non-timestamp TUF seed, native runtime, two-platform, security, and supply-chain boundary in `ADR-054`–`ADR-059`
- [ ] Three consecutive attempt-1 20-job runs and their combined 60-sample result each remain below 15 seconds nearest-rank p95
- [ ] Exact signer `0.1.1`, CLI `0.1.4`, image `0.1.5`, source `v0.1.5`, immutable Action `v1.0.5`, dogfood, public proof, fork denial, and reviewed `v1` promotion complete without another Python publication

Completion evidence: release performance run `36761068084` attempt 1 measured p50 11 s and
nearest-rank p95 14 s on release commit `4e73dcaf888f15967da66826d48cca5ac6684fcb`; recovery run
`36849857414` completed the immutable release; public proof PR #6 and fork-denial PR #7 established
the required merge states; protected promotion run `36872903768` moved `v1` to immutable
`v1.0.4` after review. Post-release monitoring remains fail-closed: run `36872334911` measured p95
16 s and run `36905961561` measured p95 17 s. Run `37796984054` measured p50 12 s and p95 16 s
after the `ADR-057` candidate. Run `37899003696` measured p50 11 s and p95 17 s after the
`ADR-058` candidate. Accepted `ADR-054`–`ADR-059` track the bounded
repeatability correction without altering the retained `v1.0.4` release gate or any immutable
public record.
