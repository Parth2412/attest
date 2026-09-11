# attest — Technology Stack (Python)

| Field | Value |
|---|---|
| Document ID | `TECH-001` |
| Version | `1.0.4` |
| Status | **NORMATIVE** for libraries, versions, and tooling |
| Last updated | 2026-09-11 |

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
| `pydantic` (v2.x) | Models, validation, JSON Schema generation, camelCase aliasing | `attest-core` |
| `rfc8785` | RFC 8785 JCS canonicalisation | `attest-core` |
| `sigstore` | Keyless signing, native DSSE signing/verification, bundles, trust root | `attest-sign` |
| `pygit2` | Optional libgit2 backend; pinned in development/CI for conformance | `attest-collect[pygit2]`, `attest-store[pygit2]`, root `dev` group |
| `httpx` | HTTP client (forge APIs) | `attest-collect` |
| `typer` | CLI framework | `attest-cli` |
| `rich` | Terminal output, tables, diagnostics | `attest-cli` |
| `structlog` | Structured logging and JSON output | `attest-cli` |
| `pyyaml` | Policy, export mapping, and config parsing | `attest-policy`, `attest-export`, `attest-cli` |
| `oras` | OCI registry storage backend | `attest-store` |
| `jsonschema` | Schema validation at verify time | `attest-core` |

The executed pre-bootstrap baselines are `pygit2==1.20.0`, `rfc8785==0.1.4`,
`sigstore==4.5.0`, `pydantic==2.13.5`, and `jsonschema==4.26.0`. `BOOT-001 §4.1`
requires the first `uv.lock` to resolve these versions exactly. They may move only after the
corresponding `CH-01`/`CH-02` conformance is repeated.

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
| `release` | tag | Build wheels + container, sign own artifacts with attest, publish |

**Dogfooding requirement (NORMATIVE):** attest **MUST** attest its own releases from the first
release. If the tool cannot be used on itself, it is not ready to be used by anyone else — and it
is by far the most persuasive demo you will have.

---

## 8. Distribution

| Channel | Artifact | Audience |
|---|---|---|
| PyPI | `attest-cli` wheel | Python-native teams |
| GHCR | `ghcr.io/<org>/attest:<version>` slim container | **Primary** CI channel |
| GitHub Action | `<org>/attest-action@v1` | Most users — hides Python entirely |
| Homebrew | Formula | Local developer use |

Container base: `python:3.12-slim` initially. Move to distroless once the `pygit2`/libgit2 native
dependency is settled. Multi-arch: `linux/amd64` and `linux/arm64`.

---

## 9. Known technical risks in this stack

| Risk | Impact | Mitigation |
|---|---|---|
| `pygit2` wheel availability across platforms | Install failures | Dual `GitBackend` implementations (`ADR-007`) |
| `sigstore-python` API changes between minor versions | Breakage | Pin exactly; wrap behind an internal `Signer` protocol so the blast radius is one module |
| Container cold start | Slower CI | Slim base, lazy imports, layer caching |
| Python startup for a CLI | Perceived sluggishness | Defer heavy imports until the subcommand needs them; keep `attest --help` import-light |
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
