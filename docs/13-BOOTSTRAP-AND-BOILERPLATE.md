# attest — Bootstrap and Boilerplate Specification

| Field | Value |
|---|---|
| Document ID | `BOOT-001` |
| Version | `1.8.0` |
| Status | **NORMATIVE** for repository scaffold, file contents, and tooling configuration |
| Last updated | 2026-09-15 |

> **Purpose.** This document is complete enough to generate the entire starting repository with
> **zero invention**. Every file that must exist is listed. Every configuration file's content is
> given. Where content is given, it is `NORMATIVE` — reproduce it, do not improve it.
>
> **The scaffold contains no business logic.** Stub modules are created empty with docstrings
> naming their governing BRD. Logic arrives feature by feature, starting at `BRD-F01`.

---

## 1. Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.12 or 3.13 | system or `uv python install 3.12` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| just | latest | `cargo install just` or package manager |
| git | 2.40+ | system |
| libgit2 | optional via the `pygit2` package extras | resolved by uv when selected |

---

## 2. Complete file tree

Every path below **MUST** exist after bootstrap. Paths marked `(empty stub)` contain only a module
docstring naming their BRD. Paths marked `(generated)` are produced by a command, never hand-written.

```
attest/
├── .github/
│   └── workflows/
│       └── ci.yml
├── .attest/
│   ├── config.yaml
│   ├── policy.yaml
│   └── claims.d/.gitkeep
├── .importlinter
├── .pre-commit-config.yaml
├── .gitignore
├── AGENTS.md
├── CHANGELOG.md
├── CONTRIBUTING.md
├── LICENSE                       # Apache-2.0 (ADR-017)
├── LICENSE.spec                  # CC-BY-4.0 (ADR-017)
├── README.md
├── SECURITY.md
├── Justfile
├── pyproject.toml
├── uv.lock                       # (generated) committed
├── docs/                         # this entire document set, copied in
│   ├── 00-MASTER-PROJECT-DOCUMENT.md
│   ├── 01-GLOSSARY-AND-CONVENTIONS.md
│   ├── 02-SPEC-001-AI-AUTHORSHIP-PREDICATE.md
│   ├── 03-SYSTEM-ARCHITECTURE.md
│   ├── 04-TECH-STACK-PYTHON.md
│   ├── 05-ADR-LOG.md
│   ├── 06-BRD-INDEX-AND-TRACEABILITY.md
│   ├── 07-TESTING-AND-QUALITY-STRATEGY.md
│   ├── 08-REPO-SCAFFOLD-AND-DEV-WORKFLOW.md
│   ├── 09-AGENTS.md
│   ├── 10-ROADMAP-90-DAY.md
│   ├── 11-RISK-REGISTER-AND-KILL-CRITERIA.md
│   ├── 12-SECURITY-THREAT-MODEL.md
│   ├── 13-BOOTSTRAP-AND-BOILERPLATE.md
│   ├── 14-OPEN-CHALLENGES-AND-VALIDATION.md
│   └── brd/BRD-F01.md … BRD-F12.md
├── scripts/
│   ├── check_traceability.py
│   ├── check_banned_language.py
│   ├── run_test_group.py
│   ├── run_mypy.py
│   └── new_adr.py
├── spec/
│   ├── SPEC-001.md               # published copy of docs/02-*
│   ├── schemas/
│   │   └── .gitkeep              # generated schemas arrive in BRD-F01
│   └── testvectors/
│       ├── README.md
│       ├── jcs-canonical/.gitkeep
│       ├── csd1-empty/.gitkeep
│       ├── csd1-single-add/.gitkeep
│       ├── csd1-modify-delete/.gitkeep
│       ├── csd1-rename/.gitkeep
│       ├── csd1-mode-change/.gitkeep
│       ├── csd1-unicode-paths/.gitkeep
│       ├── csd1-submodule/.gitkeep
│       ├── csd1-symlink/.gitkeep
│       ├── csd1-path-ordering/.gitkeep
│       ├── statement-valid/.gitkeep
│       └── (statement-invalid-schema-* and statement-invalid-semantic-* arrive in BRD-F01)
├── examples/
│   ├── hooks/
│   │   ├── claude-code/
│   │   ├── cursor/
│   │   └── generic/
│   └── workflows/
│       └── quickstart.yml
├── action/
│   ├── action.yml
│   └── Dockerfile
└── packages/
    ├── attest-core/
    │   ├── pyproject.toml
    │   ├── src/attest_core/
    │   │   ├── __init__.py
    │   │   ├── py.typed
    │   │   ├── constants.py
    │   │   ├── errors.py
    │   │   ├── canonical.py          (empty stub — BRD-F01)
    │   │   ├── digest.py             (empty stub — BRD-F01)
    │   │   ├── builder.py            (empty stub — BRD-F05)
    │   │   ├── schema.py             (empty stub — BRD-F01)
    │   │   └── models/
    │   │       ├── __init__.py
    │   │       ├── enums.py          (empty stub — BRD-F01)
    │   │       ├── changeset.py      (empty stub — BRD-F01)
    │   │       ├── predicate.py      (empty stub — BRD-F01)
    │   │       └── statement.py      (empty stub — BRD-F01)
    │   └── tests/
    │       ├── conftest.py
    │       └── test_bootstrap.py       (workspace import smoke test — BOOT-001 only)
    ├── attest-collect/
    │   ├── pyproject.toml
    │   ├── src/attest_collect/
    │   │   ├── __init__.py
    │   │   ├── py.typed
    │   │   ├── protocols.py          (empty stub — BRD-F02)
    │   │   ├── git_pygit2.py         (empty stub — BRD-F02)
    │   │   ├── git_subprocess.py     (empty stub — BRD-F02)
    │   │   ├── changeset.py          (empty stub — BRD-F02)
    │   │   ├── trailers.py           (empty stub — BRD-F03)
    │   │   ├── sidecar.py            (empty stub — BRD-F03)
    │   │   ├── gitnotes.py           (empty stub — BRD-F03)
    │   │   ├── authorship.py         (empty stub — BRD-F03)
    │   │   ├── github.py             (empty stub — BRD-F04)
    │   │   └── environment.py        (empty stub — BRD-F05)
    │   └── tests/conftest.py
    ├── attest-sign/
    │   ├── pyproject.toml
    │   ├── src/attest_sign/
    │   │   ├── __init__.py
    │   │   ├── py.typed
    │   │   ├── protocols.py          (empty stub — BRD-F06)
    │   │   ├── dsse.py               (Sigstore DSSE adapter stub — BRD-F06; no PAE logic)
    │   │   ├── sigstore_signer.py    (empty stub — BRD-F06)
    │   │   ├── trustroot.py          (empty stub — BRD-F08)
    │   │   └── verifier.py           (empty stub — BRD-F08)
    │   └── tests/conftest.py
    ├── attest-store/
    │   ├── pyproject.toml
    │   ├── src/attest_store/
    │   │   ├── __init__.py
    │   │   ├── py.typed
    │   │   ├── protocols.py          (empty stub — BRD-F07)
    │   │   ├── gitref.py             (empty stub — BRD-F07)
    │   │   ├── filesystem.py         (empty stub — BRD-F07)
    │   │   └── oci.py                (empty stub — BRD-F07)
    │   └── tests/conftest.py
    ├── attest-policy/
    │   ├── pyproject.toml
    │   ├── src/attest_policy/
    │   │   ├── __init__.py
    │   │   ├── py.typed
    │   │   ├── models.py             (empty stub — BRD-F09)
    │   │   ├── loader.py             (empty stub — BRD-F09)
    │   │   └── evaluate.py           (empty stub — BRD-F09)
    │   └── tests/conftest.py
    ├── attest-export/
    │   ├── pyproject.toml
    │   ├── src/attest_export/
    │   │   ├── __init__.py
    │   │   ├── py.typed
    │   │   ├── bundle.py             (empty stub — BRD-F12)
    │   │   ├── mappings.py           (empty stub — BRD-F12)
    │   │   └── frameworks/           (mapping data files — BRD-F12)
    │   └── tests/conftest.py
    └── attest-cli/
        ├── pyproject.toml
        ├── src/attest_cli/
        │   ├── __init__.py
        │   ├── py.typed
        │   ├── __main__.py
        │   ├── app.py                (empty stub — BRD-F10)
        │   ├── config.py             (empty stub — BRD-F10)
        │   ├── output.py             (empty stub — BRD-F10)
        │   ├── exit_codes.py
        │   └── commands/
        │       ├── __init__.py
        │       └── (one module per command — BRD-F10 §3)
        └── tests/conftest.py
```

---

## 3. Root `pyproject.toml` — NORMATIVE

```toml
[project]
name = "attest-workspace"
version = "0.0.0"
description = "Workspace root. Not published."
requires-python = ">=3.12"

[tool.uv]
package = false

[tool.uv.workspace]
members = ["packages/*"]

[tool.uv.sources]
attest-core   = { workspace = true }
attest-collect = { workspace = true }
attest-sign   = { workspace = true }
attest-store  = { workspace = true }
attest-policy = { workspace = true }
attest-export = { workspace = true }
attest-cli    = { workspace = true }

[dependency-groups]
dev = [
  "pytest",
  "pytest-cov",
  "pytest-randomly",
  "hypothesis",
  "mypy",
  "ruff",
  "import-linter",
  "pre-commit",
  "bandit",
  "pip-audit",
  "mutmut",
  "respx",
  "pygit2==1.20.0",
]

[tool.ruff]
target-version = "py312"
line-length = 100
extend-exclude = ["*.md"]
src = ["packages/attest-core/src", "packages/attest-collect/src", "packages/attest-sign/src",
       "packages/attest-store/src", "packages/attest-policy/src", "packages/attest-export/src",
       "packages/attest-cli/src"]

[tool.ruff.lint]
select = ["E","F","W","I","N","UP","B","A","C4","DTZ","S","PT","RET","SIM","ARG","PTH","ERA","TRY","RUF"]

[tool.ruff.lint.per-file-ignores]
"**/tests/**" = ["S101","S","ARG"]

[tool.mypy]
python_version = "3.12"
strict = true
warn_unreachable = true
disallow_any_explicit = false
enable_error_code = ["ignore-without-code","redundant-expr","truthy-bool"]

[tool.pytest.ini_options]
testpaths = ["packages"]
addopts = "-q --strict-markers --strict-config --import-mode=importlib"
markers = [
  "ac(id): the acceptance criterion this test satisfies, e.g. AC-F01-050",
  "vectors: normative test-vector conformance",
  "adversarial: forgery, tampering, and replay tests",
  "slow: excluded from the default run",
]

[tool.coverage.run]
branch = true
source = ["packages"]

[tool.coverage.report]
show_missing = true
```

---

## 4. Per-package `pyproject.toml` — NORMATIVE pattern

Every package follows this shape. Only `name`, `description`, `dependencies`, and the wheel path
change.

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "attest-core"
version = "0.1.0"
description = "attest core domain model, canonicalisation, and CSD-1 digest"
requires-python = ">=3.12"
license = "Apache-2.0"
dependencies = [
  "pydantic>=2.7",
  "rfc8785",
  "jsonschema",
]

[tool.hatch.build.targets.wheel]
packages = ["src/attest_core"]
```

### 4.1 Dependency assignment per package — NORMATIVE

| Package | `dependencies` |
|---|---|
| `attest-core` | `pydantic`, `rfc8785`, `jsonschema` |
| `attest-collect` | `attest-core`, `httpx`; optional `pygit2` extra |
| `attest-sign` | `attest-core`, `sigstore` |
| `attest-store` | `attest-core`, `oras`; optional `pygit2` extra |
| `attest-policy` | `attest-core`, `pydantic`, `pyyaml` |
| `attest-export` | `attest-core`, `attest-store`, `attest-sign`, `pyyaml` |
| `attest-cli` | all six above, `pydantic`, `httpx`, `typer`, `rich`, `structlog`, `pyyaml` |

**Version constraints are not given here on purpose except for the executed `CH-01`/`CH-02`
baselines below.** Run `uv add` and let the resolver pin into `uv.lock`. `uv.lock` is the source of
truth (`TECH-001 §3`). Do not hand-write version numbers from memory.

The first bootstrap lock **MUST** resolve these empirically validated versions exactly. The root
development group owns the `pygit2` pin so both Git implementations remain mandatory in CI while
base package installation remains independent of a native wheel (`ADR-034`):

| Dependency | Required bootstrap version | Evidence |
|---|---|---|
| `pygit2` | `1.20.0` | `CH-01`, validation PR #1 |
| `rfc8785` | `0.1.4` | `CH-01`/`CH-02` |
| `sigstore` | `4.5.0` | `CH-02`, validation PRs #2–#3 |
| `pydantic` | `2.13.5` | `CH-02`, validation PR #3 structural/semantic boundary proof |
| `jsonschema` | `4.26.0` | `CH-02`, validation PR #3 structural/semantic boundary proof |

These are validated bootstrap pins, not remembered version guesses. Upgrading one requires the
relevant conformance experiment before changing `uv.lock` (`ADR-020`, `ADR-021`).

`attest-core` **MUST NOT** gain any dependency with I/O capability. Adding one requires an ADR.

---

## 5. `.importlinter` — NORMATIVE

```ini
[importlinter]
root_packages =
    attest_core
    attest_collect
    attest_sign
    attest_store
    attest_policy
    attest_export
    attest_cli
include_external_packages = True

[importlinter:contract:layers]
name = Package layering: cli, export, peer adapters, core
type = layers
layers =
    attest_cli
    attest_export
    attest_policy | attest_store | attest_sign | attest_collect
    attest_core

[importlinter:contract:core-is-pure]
name = attest_core performs no I/O
type = forbidden
source_modules =
    attest_core
forbidden_modules =
    httpx
    pygit2
    sigstore
    securesystemslib
    subprocess
    socket
    urllib
    requests

[importlinter:contract:policy-is-pure]
name = attest_policy performs no I/O beyond reading its own file via the CLI
type = forbidden
source_modules =
    attest_policy.evaluate
forbidden_modules =
    httpx
    pygit2
    subprocess
    socket

[importlinter:contract:verifier-isolation]
name = The verifier does not share code paths with the signer
type = forbidden
source_modules =
    attest_sign.verifier
forbidden_modules =
    attest_sign.sigstore_signer
```

---

## 6. `Justfile` — NORMATIVE

```make
default: check

# Full local gate — run before every commit
check: lint types imports test

lint:
    uv run ruff check .
    uv run ruff format --check .

fmt:
    uv run ruff check --fix .
    uv run ruff format .

types:
    uv run python scripts/run_mypy.py

imports:
    uv run lint-imports

test:
    uv run pytest

test-cov:
    uv run pytest --cov --cov-report=term-missing

vectors:
    uv run python scripts/run_test_group.py vectors F-01 F-02

adversarial:
    uv run python scripts/run_test_group.py adversarial F-08

schema:
    @echo "not yet implemented — schema generation belongs to BRD-F01" >&2
    @exit 2

schema-check: schema
    git diff --exit-code spec/schemas/

banned:
    uv run python scripts/check_banned_language.py

trace:
    uv run python scripts/check_traceability.py

security:
    uv run bandit -r packages --exclude "*/tests/*" -c pyproject.toml
    uv run pip-audit

adr TITLE:
    uv run python scripts/new_adr.py "{{TITLE}}"

# The full release gate from QA-001 §12
release-gate: check vectors adversarial schema-check banned trace security
```

---

## 7. `.pre-commit-config.yaml` — NORMATIVE

```yaml
repos:
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --fix
        language: system
        types: [python]
      - id: ruff-format
        name: ruff format
        entry: uv run ruff format
        language: system
        types: [python]
      - id: mypy
        name: mypy strict
        entry: uv run python scripts/run_mypy.py
        language: system
        pass_filenames: false
        types: [python]
      - id: import-linter
        name: import boundaries
        entry: uv run lint-imports
        language: system
        pass_filenames: false
      - id: banned-language
        name: banned language check
        entry: uv run python scripts/check_banned_language.py
        language: system
        pass_filenames: false
```

---

## 8. `.gitignore` — NORMATIVE additions

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/

# Claim sidecars are local, per-developer, and never committed
.attest/claims.d/*.json

# Local attestation output
*.sigstore.json
attest-out/
```

---

## 9. `scripts/check_banned_language.py` — behaviour contract

Implements `QA-001 §7`. Behaviour, not code:

- Reads the banned-phrase list from a single constant table that mirrors `GLOSS-001 §2.2`.
- Scans: `packages/**/*.py`, `docs/**/*.md`, `spec/**/*.md`, `README.md`, `action/**`, and any
  generated export fixtures under `tests/`.
- Matching is case-insensitive, whitespace-normalised.
- Exits `1` listing every file, line number, and matched phrase.
- **Exempts exactly two bounded regions:** the canonical table in `GLOSS-001 §2.2` and this
  script's own constant table. Each region uses paired
  `# banned-language-allowlist:start`/`:end` markers. No other file or region is exempt.
- The script's constant values **MUST** mirror the canonical `Banned` column in
  `GLOSS-001 §2.2` byte-for-byte; this document does not duplicate those literals.

## 10. `scripts/check_traceability.py` — behaviour contract

Implements `QA-001 §8`:

- Parses every `REQ-Fxx-NNN` from `docs/brd/BRD-F*.md`.
- Parses every `AC-Fxx-NNN` from the same files.
- Parses every `@pytest.mark.ac("AC-Fxx-NNN")` from `packages/**/tests/**`.
- Fails if: any `REQ-` has no same-numbered `AC-`; any `AC-` has no same-numbered `REQ-`; or any
  `AC-` belonging to a feature listed as Done in `BRD-INDEX §7` has no referencing test.
- Prints a coverage table per feature.
- Exits `0` at bootstrap, when no features are Done yet.

### 10.1 `scripts/run_test_group.py` — behaviour contract

- Accepts one registered pytest marker followed by one or more owning feature IDs.
- Runs pytest for that marker and propagates every exit status except `5` unchanged.
- Reads feature status only from `BRD-INDEX §7.1`.
- Translates exit status `5` to `0`, with an explicit not-applicable message, only when none of
  the owning features is `Done`.
- Leaves exit status `5` unchanged once any owning feature is `Done`.

### 10.2 `scripts/run_mypy.py` — behaviour contract

- Discovers every direct child of `packages/` containing `pyproject.toml`.
- Runs mypy in strict project configuration once per workspace package, including that package's
  source and tests.
- Prints each package result and exits non-zero if any invocation fails.
- Fails when no workspace package is discovered.

## 11. `scripts/new_adr.py` — behaviour contract

Appends a new ADR to `docs/05-ADR-LOG.md` using the template at the end of that file, assigning
the next sequential number and today's UTC date. Never edits an existing ADR.

---

## 12. `.github/workflows/ci.yml` — NORMATIVE structure

```yaml
name: ci
on:
  push: { branches: [dev, main] }
  pull_request:

permissions:
  contents: read

jobs:
  check:
    name: check (${{ matrix.os }}, Python ${{ matrix.python }})
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest]
        python: ["3.12", "3.13"]
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with:
          version: "0.11.2"
          python-version: ${{ matrix.python }}
          enable-cache: false
      - name: Verify Python selection
        run: >-
          uv run python -c "import platform; expected='${{ matrix.python }}';
          actual='.'.join(platform.python_version_tuple()[:2]);
          raise SystemExit(0 if actual == expected else f'expected Python {expected}, got {actual}')"
      - run: uv sync --locked --all-packages
      - run: uv run ruff check .
      - run: uv run ruff format --check .
      - run: uv run python scripts/run_mypy.py
      - run: uv run lint-imports
      - run: uv run pytest --cov --cov-report=term-missing

  vectors:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with: { version: "0.11.2", python-version: "3.12", enable-cache: false }
      - run: uv sync --locked --all-packages
      - run: uv run python scripts/run_test_group.py vectors F-01 F-02

  adversarial:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with: { fetch-depth: 0 }
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with: { version: "0.11.2", python-version: "3.12", enable-cache: false }
      - run: uv sync --locked --all-packages
      - run: uv run python scripts/run_test_group.py adversarial F-08

  schema-drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with: { version: "0.11.2", python-version: "3.12", enable-cache: false }
      - run: uv sync --locked --all-packages
      - name: Check schema drift when F-01 is complete
        run: |
          if grep -qF '| `F-01` | Done |' docs/06-BRD-INDEX-AND-TRACEABILITY.md; then
            uv run python -m attest_core.schema --write spec/schemas/
            git diff --exit-code spec/schemas/
          else
            echo "schema-drift: not applicable until F-01 is Done"
          fi

  banned-language:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with: { version: "0.11.2", python-version: "3.12", enable-cache: false }
      - run: uv sync --locked --all-packages
      - run: uv run python scripts/check_banned_language.py

  traceability:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with: { version: "0.11.2", python-version: "3.12", enable-cache: false }
      - run: uv sync --locked --all-packages
      - run: uv run python scripts/check_traceability.py

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: astral-sh/setup-uv@20cfd1bf945f4377ade1205e4dbc17946fc9a30d # v10.0.1
        with: { version: "0.11.2", python-version: "3.12", enable-cache: false }
      - run: uv sync --locked --all-packages
      - run: uv run bandit -r packages --exclude "*/tests/*" -c pyproject.toml
      - run: uv run pip-audit
```

`e2e-sign.yml` and `release.yml` **MUST NOT exist** at bootstrap. GitHub registers every recognized
workflow file and rejects comment-only placeholders. `BRD-F06` and `BRD-F11` create those exact
paths only when they deliver valid executable workflows (`ADR-028`).

---

## 13. `constants.py` and `exit_codes.py` — NORMATIVE content

These two files carry real content at bootstrap because everything else references them.

`packages/attest-core/src/attest_core/constants.py`:

```python
"""Project-wide constants. Governed by SPEC-001 and ADR-013."""

from typing import Final

# ADR-013: v0.x URIs are explicitly unstable. Replace <org> at bootstrap.
# This MUST remain the single definition; never inline this string (REQ-F05-040).
PREDICATE_TYPE_V0_1: Final[str] = "https://<org>.github.io/attest/ai-authorship/v0.1"

IN_TOTO_STATEMENT_TYPE: Final[str] = "https://in-toto.io/Statement/v1"
DSSE_PAYLOAD_TYPE: Final[str] = "application/vnd.in-toto+json"

SUBJECT_NAME: Final[str] = "changeset"
DIGEST_ALGORITHM: Final[str] = "CSD-1"
SCHEMA_VERSION: Final[str] = "0.1.0"

ATTESTATION_REF_PREFIX: Final[str] = "refs/attestations"  # ADR-014
```

`packages/attest-cli/src/attest_cli/exit_codes.py`:

```python
"""CLI exit codes. NORMATIVE — GLOSS-001 §7. Frozen; changing one is a major version bump."""

from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    INTERNAL_ERROR = 1
    USAGE_ERROR = 2
    POLICY_VIOLATION = 3
    VERIFICATION_FAILURE = 4
    ATTESTATION_NOT_FOUND = 5
    TRANSIENT_FAILURE = 6
```

---

## 14. Stub module convention — NORMATIVE

Every stub module contains exactly a docstring and nothing else:

```python
"""ChangeSet digest — algorithm CSD-1.

Governed by: SPEC-001 §5, BRD-F01 (REQ-F01-050, REQ-F01-060).
Not yet implemented. Do not add logic here outside a BRD-F01 work session.
"""
```

Stubs **MUST NOT** contain `pass`, `TODO`, placeholder functions, or example implementations. An
empty stub with a docstring cannot be mistaken for working code; a placeholder function can.

---

## 15. Bootstrap sequence — exact commands

```bash
# 1. Create the tree and all files per §2
# 2. Replace <org> in constants.py with the real GitHub org (ADR-013)
uv sync --all-packages
uv run pre-commit install

# 3. Verify the scaffold
just check          # must pass on an empty codebase
just banned         # must pass
just trace          # must pass (no features Done yet)
just imports        # must pass

# 4. Commit
git add -A
git commit -m "chore: bootstrap repository scaffold per BOOT-001"
```

---

## 16. Bootstrap acceptance checklist

The scaffold is correct when **all** of these are true. This is the agent's Definition of Done for
the boilerplate task.

- [ ] Every path in §2 exists
- [ ] `uv sync --all-packages` completes and `uv.lock` is committed
- [ ] `just check` passes with zero findings
- [ ] Strict mypy passes independently for all seven workspace packages
- [ ] `just imports` passes — all four contracts in §5 load and pass
- [ ] `just vectors` and `just adversarial` report not applicable and exit `0` while their owning
      features remain Planned
- [ ] `just banned` passes
- [ ] `just trace` passes and prints a table with zero Done features
- [ ] `just schema` fails cleanly with a "not yet implemented" error, **not** a traceback — schema
      generation belongs to `BRD-F01`
- [ ] `spec/schemas/` contains only `.gitkeep`; generated schema files do not exist before F-01
- [ ] The bootstrap import smoke test imports all seven workspace packages
- [ ] No stub module contains executable code
- [ ] `<org>` has been replaced in `constants.py`
- [ ] `AGENTS.md` is at the repository root, copied from `docs/09-AGENTS.md`
- [ ] `docs/` contains all 15 documents plus 12 BRDs
- [ ] `LICENSE` is Apache-2.0 and `LICENSE.spec` is CC-BY-4.0 (`ADR-017`)
- [ ] `.github/workflows/` contains only the valid `ci.yml`; inactive workflow placeholders do
      not exist (`ADR-028`)
- [ ] CI runs green on the bootstrap commit
- [ ] Zero business logic exists anywhere

**If the agent writes any logic during bootstrap, the bootstrap is wrong.** The scaffold's entire
job is to make `BRD-F01` startable, not to anticipate it.

---

## 17. What the agent must NOT do during bootstrap

| Forbidden | Why |
|---|---|
| Implement any function | Logic arrives per BRD, in order |
| Write the JSON Schema by hand | `ADR-010` — generated only |
| Create test vectors | They are normative; authored in `BRD-F01`/`BRD-F02` with human review |
| Pin dependency versions from memory | Use `uv add`; only the executed `CH-01`/`CH-02` baselines in §4.1 are pre-authorised, and `uv.lock` is truth (`AGENTS.md §4`) |
| Add a dependency not in §4.1 | Requires an ADR |
| Create `e2e-sign.yml` or `release.yml` | GitHub registers them immediately; owned by `BRD-F06` and `BRD-F11` (`ADR-028`) |
| Choose a different project layout | `ARCH-001 §2` is normative |
| "Improve" any configuration in this document | It is `NORMATIVE` |
