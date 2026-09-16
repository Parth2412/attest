# BRD-F11 — GitHub Action Packaging

| Field | Value |
|---|---|
| Document ID | `BRD-F11` |
| Feature | `F-11` |
| Milestone | M2 |
| Package | `action/` |
| Depends on | `F-06`, `F-07`, `F-09`, `F-10` |
| Status | **In progress** · delivery contract governed by `ADR-046` |

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
permission. `verify` and `gate` never request an OIDC token. The automatic `${{ github.token }}` is
provided to the container by Action metadata as `GITHUB_TOKEN`; there is no public token input or
output, and no credential is printed.

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

### 4.2 Two-phase supply chain

1. After implementation lands on protected `dev`, a candidate workflow builds from an explicitly
   enumerated context, lock file, and digest-pinned base image, runs the complete gate, scans the
   image, and emits the context/manifest digests, SBOM, provenance, and GitHub artifact attestation.
2. A second reviewed PR pins that exact digest in `action.yml`; `action.yml` is outside the image
   build context, so the pin does not change the candidate bytes.
3. After the reviewed tree reaches protected `main`, a manually dispatched protected release job
   verifies final context equality and promotes the exact candidate manifest to `0.1.0`; it does
   not substitute a rebuild with a different digest.
4. A build job creates distributions once. A separate publish job uses PyPI Trusted Publishing
   bound to the protected `pypi` environment; no API token is stored.
5. The workflow publishes the public image and six distributions, creates immutable product
   Release/tag `v0.1.0` and immutable Action tag `v1.0.0`, advances reviewed `v1`, creates attest's
   own release ChangeSet evidence, and verifies that evidence publicly.

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
| `REQ-F11-060` | The Action **MUST NOT** require a repository secret for the core loop; keyless signing uses the workflow identity and publication uses the automatic token. |
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

## 7. Evidence retention

F-11 retains the candidate and release run URLs and IDs; repository, fork, pull-request, commit,
tag, release, image, package, SBOM, provenance, and Bundle identifiers; status-check App identity and
branch-protection response; exact generated files; success, blocked, fork-failure, malicious-fixture,
and missing-permission logs; outputs; and all 20 performance measurements. Evidence is indexed from
the immutable GitHub Release and contains no credential.

## 8. Out of scope

GitLab and Bitbucket templates (v1.1), marketplace listing optimisation, self-hosted runner
specialisation, publishing `attest-export` before F-12, and granting fork pull requests signing or
write authority.

## 9. Definition of Done

- [ ] All `REQ-F11-*` implemented, all `AC-F11-*` green and traced
- [ ] The exact F-10-generated and copy-pasteable README workflows run unmodified on a fresh repository
- [ ] The six packages and multi-platform image are publicly installable by immutable version/digest
- [ ] Dogfood release evidence verifies publicly
- [ ] A real repository demonstrates blocked and successful merge states through the required,
  expected-App-pinned gate check
- [ ] The `zettacore-labs` fork proof fails safely before repository reads
- [ ] The retained 20-run measurement meets p95 below 15 seconds
- [ ] Cross-cutting obligations satisfied
