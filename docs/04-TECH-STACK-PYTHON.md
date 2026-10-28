# attest — Technology Stack (Python)

| Field | Value |
|---|---|
| Document ID | `TECH-001` |
| Version | `1.7.13` |
| Status | **NORMATIVE** for libraries, versions, and tooling |
| Last updated | 2026-10-28 |

---

## 1. Language decision

**Python 3.12+ (target 3.12, test on 3.12 and 3.13). Decided and final for v1.x — `ADR-012`.**

### 1.1 Why Python is the right choice here — the honest case

You asked for Python; the earlier research recommended TypeScript because that is your strongest
stack. For **this specific product**, Python is genuinely the better choice, for reasons that are
about the domain rather than preference:

| Factor | Assessment |
|---|---|
| **Sigstore support** | `sigstore-python` is maintained by the Sigstore project itself. It is a first-party client, not a community port. For a product whose entire value is signature correctness, using a first-party implementation is worth a great deal. |
| **in-toto support** | The in-toto reference implementation is Python. The wire types remain close to the specification without requiring a second DSSE implementation. |
| **TUF** | The TUF reference implementation (`python-tuf`) is Python. Trust root handling comes from the source. |
| **Standards proximity** | Your strategic bet is owning a specification. Being in the same language as the reference implementations puts you closer to the standards communities you need to influence. |
| **Schema tooling** | Pydantic v2 generating JSON Schema directly from models eliminates structural schema drift; runtime validators enforce non-representable semantic invariants (`ADR-021`). |

### 1.2 What Python costs you — stated plainly

| Cost | Severity | Mitigation |
|---|---|---|
| No single static binary | **High** — this is the real cost | Ship a container image as the primary CI artifact; `uv tool install` for local; evaluate PyInstaller/Nuitka only if user demand justifies it |
| Cold start in CI | Medium | Pre-built slim container, layer caching, lazy imports of heavy modules |
| Distribution to non-Python teams | Medium | Container + GitHub Action wrapper means users never see Python |
| Your own velocity | Medium, temporary | Strict typing and a small pure core make the unfamiliar language safer, not riskier |
| Concurrency | Low | The workload is I/O-light and mostly sequential |

**Do not** try to erase the packaging cost with a heroic single-binary build in month one. Ship
the container. Revisit if adoption data says otherwise.

### 1.3 The single bounded revisit trigger

Recorded as `ADR-011`, and deliberately narrow so it cannot become an open-ended debate:

> **If, at the M2 exit gate, installation or runtime friction is the top-ranked complaint from a
> majority of design partners, the verifier — and only the verifier — is reimplemented as a static
> Go binary, recorded then as a new ADR.**

No other condition reopens the language question. Nobody may begin such a port speculatively, and
no agent or contributor may propose a language change outside this trigger. The TypeScript
alternative was considered in full and rejected in `ADR-012`; it is closed.

---

## 2. Runtime and project tooling

| Concern | Choice | Rationale |
|---|---|---|
| Python | 3.12+ | Modern typing syntax, performance, long support window |
| Package/project manager | **uv** | Fast, lockfile-based, workspace support for the monorepo, single tool for envs and tool installs |
| Build backend | **hatchling** | PEP 621 native, simple, no legacy setup.py |
| Layout | **src layout** | Prevents accidental imports of uninstalled code — a real source of "works locally, fails in CI" |
| Monorepo | **uv workspaces** | Multiple distributions, one lockfile, one resolution |
| Task runner | **just** (Justfile) | Simple, discoverable, not another Python dependency |

### 2.1 Workspace layout

```
pyproject.toml                 # workspace root, tool config
uv.lock                        # single lockfile for the workspace
Justfile
packages/
  attest-core/
    pyproject.toml
    src/attest_core/
    tests/
  attest-collect/
  attest-sign/
  attest-store/
  attest-policy/
  attest-export/
  attest-cli/
```

---

## 3. Core dependencies

> **Version discipline.** Versions below are *floors and intent*, not verified current releases.
> Before writing code against any library, run `uv add <pkg>` and read the installed version's
> API. **Never** write code from remembered API surfaces — see `AGENTS.md §4`. Every dependency
> is pinned in `uv.lock`; the lockfile is committed and is the source of truth.

| Package | Purpose | Package assignment |
|---|---|---|
| `pydantic` (v2.x) | Models, validation, JSON Schema generation, camelCase aliasing | `attest-core`, `attest-policy`, `attest-cli` |
| `rfc8785` | RFC 8785 JCS canonicalisation | `attest-core` |
| `sigstore` | Keyless signing, native DSSE signing/verification, bundles, trust root | `attest-sign` |
| `pygit2` | Optional libgit2 backend; pinned in development/CI for conformance | `attest-collect[pygit2]`, `attest-store[pygit2]`, root `dev` group |
| `httpx` | HTTP client (forge APIs and explicit doctor probes) | `attest-collect`, `attest-cli` |
| `typer` | CLI framework | `attest-cli` |
| `rich` | Terminal output, tables, diagnostics | `attest-cli` |
| `structlog` | Structured logging and JSON output | `attest-cli` |
| `pyyaml` | Policy, export mapping, and config parsing | `attest-policy`, `attest-export`, `attest-cli` |
| `oras` | OCI registry storage backend | `attest-store` |
| `jsonschema` | Schema validation at verify time | `attest-core` |

`attest-policy` uses the same locked Pydantic v2 baseline for its strict immutable configuration
models and generates `spec/schemas/policy-v1.schema.json` from those models. PyYAML supplies only
bounded tokenisation/parsing under the restrictions in `BRD-F09 §5.1`; library glob defaults and
constructors are not part of the policy contract (`ADR-042`).

`attest-cli` is a direct Pydantic and HTTPX consumer under `ADR-045`: Pydantic owns the closed
configuration, Collection Artifact, and output models plus generated schemas; HTTPX is used only
for explicit credential-free `doctor --probe-network` requests. Depending on either only through a
sibling package would leave the CLI's runtime imports undeclared.

The executed pre-bootstrap baselines are `pygit2==1.20.0`, `rfc8785==0.1.4`,
`sigstore==4.5.0`, `pydantic==2.13.5`, and `jsonschema==4.26.0`. `BOOT-001 §4.1`
requires the first `uv.lock` to resolve these versions exactly. They may move only after the
corresponding `CH-01`/`CH-02` conformance is repeated.

`ADR-065` sets the reviewed security-replacement lock baseline to runtime
`certifi==2026.10.19`, development-only `virtualenv==21.14.12`, and its resolver-selected
`python-discovery==1.6.4`. The latter two packages **MUST NOT** enter the Action runtime. The
candidate gate proves the exact runtime certifi version in a real container and `pip-audit`
rejects any remaining affected locked dependency.

`ADR-066` adds Alpine's fixed `musl==1.2.5-r24` runtime and matching
`musl-dev==1.2.5-r24` native-build baseline. The immutable Python base remains digest-pinned, so
the runtime stage explicitly upgrades musl, proves the installed loader owner, and retains that
exact revision after removing Alpine's package database. Both release architectures enforce the
same record and reject affected `1.2.5-r23`.

`ADR-067` replaces only source-built curl `8.22.0`, rejected by protected candidate run
`39829765757` for fixable High `CVE-2026-92392`, with signed and SHA-512-locked curl `8.23.0`.
Git `2.52.0`, the pinned removable toolchain, HTTP/1.1-only feature set, sole Git-for-Windows VEX
statement, and every candidate/release threshold remain unchanged.

`ADR-069` advances the current source baseline to build-only `setuptools==84.1.0` and
development-only `virtualenv==21.14.13` after new upstream advisories affected the previously
reviewed pins. `python-discovery==1.6.4` remains unchanged. Setuptools is removed after the Action
build; virtualenv and python-discovery remain excluded from its runtime. Existing public artifacts
therefore remain immutable, while any future candidate must use and prove the patched baseline.

`ADR-071` advances the runtime baseline from affected `dnspython==2.8.0` to exact patched
`dnspython==2.9.0` and the development baseline from affected `msgpack==1.2.2` to exact patched
`msgpack==1.2.3`. The Action runtime must contain the former and exclude the latter. Because the
public `0.1.7` image contains affected dnspython, the corrected lock must enter one unique
two-platform `0.1.8-candidate` and the complete image-only release lifecycle; no Python
distribution is republished.

### 3.1 Notes on specific choices

**Sigstore-native DSSE (`ADR-020`).**
The reference implementation uses Sigstore's public `sign_dsse` and `verify_dsse` operations.
`securesystemslib` is not a direct dependency and **MUST NOT** be imported for envelope handling,
even when installed transitively. The exact canonical Statement bytes enter Sigstore once; PAE,
envelope, certificate, Rekor, and bundle operations remain under one upstream authority. The
validated baseline is `sigstore==4.5.0`; bootstrap **MUST** resolve that exact version into
`uv.lock` before `F-06` or `F-08` implementation. An upgrade requires repeating the `CH-02`
conformance checks first.

In `sigstore` 4.5.0, one signing run uses one signer context with its default in-memory ephemeral
key retention. Setting `cache=False` is forbidden because repeated private-key access within the
flow produces different ephemeral keys; no private key may be written to disk.

The v0.1 adapter is keyless-only and requires the caller to select production or staging
explicitly. The locked library sets timeouts for ambient GitHub OIDC and timestamp-authority
requests but not for Fulcio or Rekor, and it exposes no supported HTTP-timeout injection point.
Signing therefore runs in an isolated child process with a default 120-second parent-enforced
deadline. The parent terminates an expired worker, retries at most once before Rekor begins, and
never retries after Rekor submission begins. Do not mutate Sigstore's private HTTP sessions or
wrap an unbounded call in a worker thread (`ADR-037`).

The public CLI, direct library API, non-Linux runtimes, non-main threads, and processes with any
other live Python thread continue to use `spawn`. Only the digest-matched, sanitized Action
in-process `run` adapter may mint a fresh private capability and authorize `fork` for that single
invocation. A caller-supplied marker or any failed precondition falls back to `spawn`; both start
methods retain the same isolated child, one-way pipe, deadline, retry ceiling, termination, and
secret-safe error boundary (`REQ-F06-170`, `ADR-061`).

Verification also requires its trust source explicitly (`ADR-038`). `ServiceTrustRoot` selects
production or staging and requires an `offline` boolean; `offline=False` is the caller's explicit
permission for a TUF refresh. The locked TUF client applies a 30-second socket timeout to every
fetch. `SuppliedTrustRoot` parses complete client-trust-configuration JSON through the public
`ClientTrustConfig.from_json` API and performs no network operation. Verification calls only the
public `Bundle.from_json`, `Verifier.verify_dsse`, and `Identity` surfaces; it never imports or
invokes Sigstore's private verification helpers.

Sigstore 4.5.0's `Identity` policy is exact-only. The adapter therefore validates bounded GitHub
workflow glob syntax itself, resolves exactly one matching URI SAN through the public certificate
surface, and passes that resolved exact identity and the exact issuer to `Identity`. Issuer globs,
ambiguous SAN matches, and root fallback are not supported. Its constructor conditionally creates
the issuer sub-policy only when the issuer string is truthy, so F-08 rejects an empty or non-string
issuer before constructing `Identity` (`ADR-039`).

**`pygit2` over `GitPython` or subprocess.**
`GitPython` shells out for many operations and is slow and fragile. Subprocess parsing of
`git diff-tree` output is a correctness hazard for exotic paths. `pygit2` gives direct access to
tree diffs with explicit control over rename detection — which `CSD-1` requires to be *disabled*,
a setting that is awkward to guarantee via porcelain commands.

*Risk:* `pygit2` requires compiled libgit2, complicating wheels on some platforms. **Mitigation:**
define a narrow `GitBackend` protocol in `attest-collect` with a `pygit2` implementation and a
`subprocess` fallback implementation, both passing the same test vectors. `pygit2` is an optional
package extra and is imported lazily; the base installation therefore remains usable through the
Git CLI when a compatible wheel is unavailable. The exact `pygit2` baseline remains mandatory in
the root development group so CI exercises both backends. `attest-store` follows the same optional
native-backend rule and keeps its Git-ref backend usable through the Git CLI. Recorded as
`ADR-007` and `ADR-034`.

**ORAS registry boundary.**
The committed lock resolves `oras==0.2.43`. Its public push surface accepts an OCI subject, but it
does not expose a high-level Referrers API and its underlying Requests calls expose no supported
request-timeout argument. `OciStore` therefore keeps ORAS as the registry and authentication
implementation, uses the OCI 1.1 Referrers endpoint through the authenticated client surface, and
runs each complete operation in a terminable worker under a hard caller-configurable deadline.
The adapter **MUST NOT** mutate ORAS private sessions, implement a second unauthenticated registry
client, resolve mutable subject tags implicitly, or write staging material outside its explicit
directory (`ADR-043`). Any ORAS upgrade requires the subject, referrers, authentication, digest,
and deadline probes to be repeated against the installed source before implementation changes.

**`rfc8785` for canonicalisation.**
Do not hand-roll canonicalisation with `json.dumps(sort_keys=True)`. It is *not* RFC 8785: it
differs on number formatting, key ordering (code point vs. UTF-16 code unit), and escaping. This
is a classic silent interoperability bug that appears only when a second implementation exists —
i.e. exactly when it hurts most.

**`typer` over `click` or `argparse`.**
Type-hint driven, so the CLI signature and the domain types stay aligned. Built on click, so
testing via `CliRunner` is well-trodden.

**No ORM in v1.0.** There is no database in v1.0. When the hosted store arrives in v1.1, use
SQLAlchemy 2.x + Alembic on PostgreSQL. Do not add it early "so it's ready" — that is exactly how
a decentralised tool accidentally becomes a service.

---

## 4. Quality tooling

| Concern | Tool | Configuration |
|---|---|---|
| Lint + format | **ruff** | Replaces black, isort, flake8, pyupgrade. Single tool, single config. |
| Type checking | **mypy** in `strict` mode | Non-negotiable. See §4.1. |
| Import boundaries | **import-linter** | Enforces `ARCH-001 §2.1` |
| Testing | **pytest** | With `pytest-cov`, `pytest-randomly` |
| Property testing | **hypothesis** | For canonicalisation and digest invariants |
| HTTP mocking | **respx** or `pytest-httpx` | Match to the installed `httpx` version |
| Security scanning | **bandit**, **pip-audit** | In CI |
| Pre-commit | **pre-commit** | ruff, mypy, schema-drift check |
| Docs | **mkdocs-material** | Spec and CLI docs |

### 4.1 Typing policy (NORMATIVE)

- `mypy --strict` across all packages. No exceptions committed to `main`.
- `# type: ignore` requires a specific error code and an inline justification comment.
- `Any` is banned in `attest-core` public signatures.
- All wire-format models are Pydantic; no untyped `dict` crosses a package boundary.

Rationale beyond general hygiene: strict typing is the strongest available guardrail against an
AI implementation agent inventing plausible-but-wrong structures. A hallucinated field fails type
checking immediately rather than surviving to produce a malformed attestation.

---

## 5. Ruff configuration baseline

```toml
[tool.ruff]
target-version = "py312"
line-length = 100
src = ["packages/*/src"]
extend-exclude = ["*.md"]

[tool.ruff.lint]
select = [
  "E", "F", "W",      # pycodestyle, pyflakes
  "I",                 # isort
  "N",                 # pep8-naming
  "UP",                # pyupgrade
  "B",                 # bugbear
  "A",                 # builtins shadowing
  "C4",                # comprehensions
  "DTZ",               # naive datetime — critical for this project
  "S",                 # bandit rules
  "PT",                # pytest style
  "RET", "SIM", "ARG",
  "PTH",               # pathlib over os.path
  "ERA",               # commented-out code
  "TRY",               # exception antipatterns
  "RUF",
]

[tool.ruff.lint.per-file-ignores]
"**/tests/**" = ["S", "ARG"]
```

`DTZ` is deliberately enabled: naive datetimes in a project that signs timestamps are a defect
class, not a style preference.

Ruff does not format Markdown because normative code examples are specification artifacts, not
implementation source. Pytest uses importlib mode and test directories are not Python packages,
preventing seven workspace distributions from colliding on a top-level `tests` package. Strict
mypy runs once per workspace package through `scripts/run_mypy.py`; Bandit scans production
package code and excludes test directories, where assertions are expected (`ADR-026`).

---

## 6. Testing stack

Detail in `QA-001`. Stack summary:

| Layer | Tool |
|---|---|
| Unit | pytest |
| Property | hypothesis |
| Vector conformance | pytest parametrised over `spec/testvectors/` |
| Integration (git) | pytest fixtures building real repositories in `tmp_path` |
| Integration (sigstore) | Sigstore **staging** instance in CI; never production for tests |
| CLI | `typer.testing.CliRunner` |
| Contract (forge) | Recorded HTTP fixtures; live smoke test in a nightly job only |
| Mutation (core only) | `mutmut` on `attest-core` |

> **Sigstore staging.** Test signing **MUST** target the Sigstore staging environment. Writing
> test attestations to the production transparency log pollutes a public append-only log that
> cannot be cleaned. This is a hard rule.

---

## 7. CI/CD

**GitHub Actions.** Jobs:

| Job | Trigger | Purpose |
|---|---|---|
| `lint` | every push | ruff, mypy, import-linter |
| `test` | every push | pytest matrix, Python 3.12/3.13, Linux + macOS |
| `vectors` | every push | Conformance against `spec/testvectors/` |
| `schema-drift` | every push | Regenerate JSON Schema; fail if it differs from committed |
| `banned-language` | every push | Grep for banned phrases (`GLOSS-001 §2.2`) |
| `security` | every push | bandit, pip-audit |
| `e2e-sign` | main + nightly | Real signing against Sigstore staging, then verify |
| `action-candidate` | protected `dev` after implementation | Build/test/scan the enumerated-context multi-platform image; emit context/manifest digests, SBOM, provenance, and GitHub attestation |
| `action-performance` | protected `main` push plus reviewed soak dispatches | Measure the exact merged Action in independent hosted jobs, retain runner/timing identity, and enforce the single-run and combined cold-start gates |
| `release` | manual dispatch on protected `main` | Verify final context and promote the exact reviewed candidate; publish packages, immutable release records, and verified dogfood evidence |

**Dogfooding requirement (NORMATIVE):** attest **MUST** attest its own releases from the first
release. If the tool cannot be used on itself, it is not ready to be used by anyone else — and it
is by far the most persuasive demo you will have.

---

## 8. Distribution

| Channel | Artifact | Audience |
|---|---|---|
| PyPI | Current core/collect/policy `0.1.0`, sign `0.1.1`, store `0.1.2`, and CLI `0.1.5`; `attest-export` is unpublished | Python-native teams; CLI exact-pins sign `0.1.1`, store `0.1.2`, and the other three libraries at `0.1.0`; no export package until F-12 |
| GHCR | Current public `ghcr.io/parth2412/attest:0.1.7` at manifest `sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356`; every earlier manifest remains immutable | **Primary** CI channel |
| GitHub Action | `Parth2412/attest/action@<full-sha>`, current immutable `v1.0.7`, and reviewed moving `v1`, all at release commit `c42e52d038f5ecdcc498679cb7648e5b0957d489`; earlier patch tags remain immutable historical records | Most users — hides Python entirely; generated workflows pin a commit |
| Homebrew | Formula (post-v1.0; not F-11) | Local developer use |

`ADR-068` published store `0.1.2`, CLI `0.1.5`, image `0.1.7`, and Action `v1.0.7`. The CLI
exact-pins the corrected store; every other internal package version is unchanged. Public guidance
uses the full release commit above, immutable `v1.0.7`, or the independently reviewed moving `v1`.

The current image records and pins the verified `python:3.12.14-alpine3.23` base digest and, under
`ADR-062` as amended by `ADR-067`, builds unmodified Git `2.52.0` and curl `8.23.0` from their
exact hash-locked upstream sources rather than retaining Alpine's broad Git/curl transport
closure. Release builds from the committed lock with
user-site/current-directory imports disabled. Multi-arch is
`linux/amd64` and `linux/arm64`. Every published image has an SBOM, provenance, and a GitHub
artifact attestation. PyPI publication uses per-package Trusted Publishing environments with build
and publish jobs separated and no long-lived package token. Because PyPI permits only three pending
publishers per account, the first release publishes two strictly ordered three-package waves with
public hash verification and a protected registration checkpoint between them. The first-release
procedure is governed by `ADR-046`, `ADR-047`, and `ADR-048`. The token-boundary correction and
its unchanged image digest are governed by `ADR-049`; the pull-request identity/runtime
correction, new reviewed image, and independent patch versions are governed by `ADR-051`; remote
attestation discovery and its bounded store/CLI/Action patch set are governed by `ADR-052`.
The image-only cold-start correction, pre-publication 20-job gate, container `0.1.4`, and Action
`v1.0.4` are governed by `ADR-053`; no Python distribution changes in that patch.
`ADR-054` authorizes a subsequent `0.1.5`/Action `v1.0.5` reliability correction. Its
candidate builds locked `cryptography==50.0.1` from the hash-locked sdist with build-only
`maturin==1.15.0`, `setuptools==84.0.0`, and exact Alpine Rust/C/OpenSSL packages, then removes the
build toolchain. Runtime OpenSSL is exact `libcrypto3=3.5.9-r0` plus `libssl3=3.5.9-r0`. The
isolated Action interpreter may invoke the bundled CLI in-process only when its console script
matches a build-generated SHA-256 marker; marker failure retains the subprocess path. Publication
requires three consecutive 20-job attempt-1 measurements whose individual and combined
nearest-rank p95 values meet the `ADR-063` release SLO below 18 seconds; the engineering target
below 15 seconds remains separately recorded and does not gate release. `ADR-055` amends the package boundary: mandatory
online trust refresh and refreshed-root verification change signer bytes, so the release publishes
only `attest-sign==0.1.1` and `attest-cli==0.1.4`, with the latter exact-pinning the former.
`ADR-056` retains those versions while allowing one refresh-gated fresh-process recovery from a
stale pre-Rekor trust bootstrap. `ADR-057` starts ambient OIDC and mandatory online trust
acquisition concurrently, permits one pre-Fulcio OIDC retry and one retry inside the online-trust
future, and preserves one signer context and Rekor submission per attempt. Each package uses its
separate protected Trusted Publisher. The same ADR requires the Action build to replace exactly
the three approved wheel-private libgcc copies with platform-specific links to pinned system
`/usr/lib/libgcc_s.so.1`, fail on path-set drift, and execute all affected native modules on both
architectures. `ADR-058` adds a build-verified, hash-locked non-timestamp TUF cache seed while
retaining live root and timestamp refresh and refreshed-root final verification on every Action
invocation. `ADR-059` supersedes the three-link runtime layout: exact locked cryptography,
pydantic-core, and rfc3161-client now build from source with the approved size flags and direct
pinned system OpenSSL/libgcc linkage; only the `rpds-py` compatibility name remains as a
fail-closed symlink to system libgcc. `ADR-060` encodes the closed deterministic pure-Python
runtime archive with standard-library DEFLATE level 9 while retaining sorted members, fixed
metadata, checked-hash bytecode, and in-place imports. `ADR-061` starts the archive-build
interpreter with `PYTHONNODEBUGRANGES=1`, removing only code-object end-line and column tables from
both deterministic archives while retaining optimisation level zero, assertions, docstrings,
source line numbers, and every existing archive contract; the final runtime does not set that
environment variable. Public files must byte-match the single build, and Python 3.12/3.13 clean
installs must pass; core, collect, store, policy, and export are not rebuilt or uploaded.
`ADR-062` pins the removable C toolchain, OpenSSL, and zlib; retains only Git's complete builtin
binary plus receive/upload-pack and HTTP(S) helper links; and compiles libcurl for verified
HTTP/HTTPS smart transport, IPv6, threaded DNS, CA bundle/path, HTTPS proxy, and zlib. Both
architectures must prove the rediscovered loader closure and the absence of PCRE2, c-ares, HTTP/2,
IDN, PSL, zstd, Brotli, and libunistring. A public digest-bound, GitHub-attested source artifact
containing both archives, licences, hashes, SPDX component evidence, exact OpenVEX, and the exact
recipe must exist before the candidate binary; the binary labels that source digest, and the immutable release
re-fetches and retains the same materials. Exact Git/curl component evidence receives the same
critical and fixable-high scan policy as the image through immutable CPE-aware Grype. The sole
not-affected statement covers Git-for-Windows `CVE-2026-62960`; its exact product, status,
justification, and the raw scanner/database evidence are retained and fail closed on drift.
`ADR-063` retains the exact `ADR-062` image, timing boundary, 20-job sample size, nearest-rank
calculation, attempt-1 rule, and automatic-plus-two-reviewed-dispatch sequence. Evidence schema 2
records both the strict 15-second engineering target and the strict 18-second release SLO for each
run and for the combined 60 samples; only the SLO gates publication, and schema-1 summaries fail
closed rather than being reinterpreted.
`ADR-064` accepts the completed schema-2 sequence, immutable `0.1.5`/`v0.1.5`/`v1.0.5` release,
public proof, fork denial, dogfood, and independently reviewed movement of `v1`. The three p95
values were 15, 14, and 16 seconds and the combined 60-sample p95 was 16 seconds: all four passed
the strict release SLO, while the retained evidence continues to expose engineering-target misses.
`ADR-065` preserves those records but requires an image-only `0.1.6`/`v1.0.6` replacement for
affected runtime `certifi==2026.7.22`. It publishes no Python distribution, repeats every candidate
and schema-2 performance gate, and forbids moving `v1` until the immutable release, dogfood,
same-repository proof, fork denial, and independent protected promotion verify.
`ADR-066` folds Alpine's `CVE-2026-107891` fix into that still-unreleased replacement by pinning
matching `musl-dev==1.2.5-r24` build stages and `musl==1.2.5-r24` runtime bytes, retaining exact
installed-version evidence, and changing no ADR-065 release or publication boundary.
`ADR-067` further replaces only the rejected curl `8.22.0` archive with signed, hash-locked curl
`8.23.0`. Failed run `39829765757`, its raw component scan, and its source artifact remain
negative evidence. Candidate run `39906806331` produced the reviewed manifest above. Exact release
commit `e693e6b60afdf9c667a913faa4f9652bfd6dc050` then passed three attempt-1 performance runs at
p95 16, 14, and 13 seconds plus a combined 60-sample p95 of 16 seconds, all below the strict
18-second release SLO. Release run `39988130356` promoted that manifest without rebuilding,
published no Python distribution, completed dogfood and immutable `v0.1.6`/`v1.0.6` records, and
verified the public package set. Same-repository and fork-denial proofs completed before protected
promotion run `39994508140` moved reviewed `v1` to the exact release commit.
`ADR-068` reopened F-11 for the filesystem lock correction. Candidate run `40086747745` passed the
repository, corresponding-source, and component gates but reached the former 60-minute build job
ceiling before emitting a binary. The new `0.1.7-candidate` receives only a 90-minute ceiling and
must otherwise repeat the unchanged two-platform build, scan, runtime, SBOM, provenance,
attestation, performance, release, proof, and promotion controls. Replacement run `40114789855`,
attempt 1, passed the complete candidate gate for source
`62b72c2537176c84bc232f727f223a9ea21ae80b`, context
`sha256:580c0b7881882817ae7ca65dfe1bbdcd06c5bea77556c8b77ff5b04e11cacc73`, corresponding source
`sha256:7472c920350b428c850a6f18f2e17693431b0e89761ef52498b009b0ea447805`, and multi-platform image
`sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356`; both architecture scans
were clean and both 23-test container suites passed. Exact release commit
`c42e52d038f5ecdcc498679cb7648e5b0957d489` then passed all three performance runs and the combined
60-sample gate. Release run `40215131129` published the bounded artifact set and completed dogfood;
proof PRs #13/#14 and protected promotion run `40287925165` verified before reviewed `v1` moved,
returning F-11 to Done.

---

## 9. Known technical risks in this stack

| Risk | Impact | Mitigation |
|---|---|---|
| `pygit2` wheel availability across platforms | Install failures | Dual `GitBackend` implementations (`ADR-007`) |
| `sigstore-python` API changes between minor versions | Breakage | Pin exactly; wrap behind an internal `Signer` protocol so the blast radius is one module |
| Container cold start | Slower CI | Slim base, balanced zstd layers, one locked dynamic OpenSSL, deterministic DEFLATE level-9 pure-Python archive, and retained hosted-runner soak evidence |
| Python startup for a CLI | Perceived sluggishness | Defer heavy imports; for the Action only, use the digest-guarded in-process CLI under isolated Python |
| Transitive dependency surface in a security tool | Supply-chain criticism | Keep the dependency tree small and auditable; `pip-audit` in CI; publish an SBOM for each release |

---

## 10. Explicitly rejected technologies

Recorded so they are not relitigated by a future contributor or agent.

| Rejected | Reason |
|---|---|
| `json.dumps(sort_keys=True)` as canonicalisation | Not RFC 8785; silent interoperability failure |
| Shelling out to `git` for diffs | Non-deterministic across versions; rename-detection defaults are wrong for `CSD-1` |
| Storing raw prompts | Secrets and personal data exposure (`SEC-001 C-06`) |
| A database in v1.0 | Turns a decentralised tool into a service prematurely |
| An embedded scripting language for policy | Arbitrary code execution in a job that holds signing permissions |
| Hand-written JSON Schema | Guarantees drift from the implementation |
| Blockchain anchoring of attestations | Rekor already provides an append-only transparency log with inclusion proofs. Adding a chain adds cost and operational burden with no additional security property. Do not do this. |

The last row deserves emphasis given your background: your blockchain expertise is a genuine
asset for this project, but the asset is your comfort with cryptographic verification, Merkle
proofs, and transparency logs — not an excuse to put a chain in the architecture. Rekor *is* the
Merkle log. Adding another would be a credibility cost with the security audience you are
selling to.
