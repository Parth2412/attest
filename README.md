# attest

attest is an open specification and toolchain for producing cryptographically signed provenance
attestations for code changes. It records declared AI-authorship claims and forge-sourced review
records, binds them to a deterministic ChangeSet digest, and signs the resulting in-toto
Statement with a CI workload identity.

> **Development status:** public pre-alpha. F-01 through F-10 and the initial F-11 release are
> implemented and evidence-backed. Six Python distributions, the multi-platform `0.1.4` image,
> immutable Action `v1.0.4`, and the reviewed moving `v1` tag are public. F-11 is temporarily in
> progress for the bounded `ADR-054`–`ADR-057` cold-start and signing-trust correction. Evidence
> export (F-12) and the external M2/M3 adoption and auditor gates remain pending, so this is not
> yet the complete product/v1 launch.

## Public release

The current immutable release is
[`v0.1.4`](https://github.com/Parth2412/attest/releases/tag/v0.1.4), and the current immutable
Action is `Parth2412/attest/action@v1.0.4`. The reviewed moving-major alias
`Parth2412/attest/action@v1` resolves to the same release commit. The Action pins the reviewed
multi-platform image by manifest digest; no mutable image tag is used at runtime.

The public Python package set remains `attest-core==0.1.0`, `attest-collect==0.1.0`,
`attest-sign==0.1.0`, `attest-store==0.1.1`, `attest-policy==0.1.0`, and
`attest-cli==0.1.3`. `attest-export` is intentionally unpublished until F-12 is complete.

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
- The exact v1.0.4 release gate passed 20 hosted measurements at p95 14 seconds, but later
  fail-closed monitoring has reproduced p95 above the 15-second target; performance reliability
  remains active launch work.

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
