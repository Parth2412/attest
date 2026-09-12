# attest

attest is an open specification and toolchain for producing cryptographically signed provenance
attestations for code changes. It records declared AI-authorship claims and forge-sourced review
records, binds them to a deterministic ChangeSet digest, and signs the resulting in-toto
Statement with a CI workload identity.

> **Development status:** pre-alpha. The deterministic core, Git ChangeSet collector, and
> four-source authorship-claim collector are implemented; no CLI or production release exists yet.

## What attest establishes

Given an attestation, a verifier will be able to establish that a stated set of claims and review
records was signed by an expected workload identity for a specific deterministic code change.
The normative wire contract is [SPEC-001](spec/SPEC-001.md); the implementation plan and current
status are recorded in [PROJECT_SPECS.md](PROJECT_SPECS.md).

## Current limitations

- AI use that is not declared is invisible to the claim model.
- Claude Code and Codex hook examples are experimental and cover only documented edit events;
  the real-world claim-emission validation gate remains open.
- A policy gate has no effect unless a repository administrator configures it as a required check.
- A public transparency log can expose repository and workflow metadata; organisations with
  stricter disclosure requirements will need a private deployment.
- A review record establishes that an approval occurred, not that the reviewer understood every
  change.
- A compromised CI environment can sign malicious content with a genuine workload identity.
- Predicate identifiers remain unstable throughout the `v0.x` series.

## Development setup

Prerequisites: Python 3.12 or 3.13, [uv](https://docs.astral.sh/uv/), Git 2.40+, and
[just](https://just.systems/).

```bash
uv sync --all-packages
uv run pre-commit install
just check
```

Read [CONTRIBUTING.md](CONTRIBUTING.md) before making changes. Security reports must follow
[SECURITY.md](SECURITY.md).

Experimental claim-emission integrations and their exact limitations are documented under
[examples/hooks](examples/hooks/README.md).

## Licensing

Code is licensed under Apache-2.0. SPEC-001 and the normative test vectors are licensed under
CC-BY-4.0. See [LICENSE](LICENSE) and [LICENSE.spec](LICENSE.spec).
