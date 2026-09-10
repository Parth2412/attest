# Contributing to attest

attest treats its wire format, deterministic digest, and verification rules as public contracts.
Before contributing, read [AGENTS.md](AGENTS.md) and the authority order in
[MPD-001](docs/00-MASTER-PROJECT-DOCUMENT.md). Work on one BRD at a time and do not change a
normative document without an accepted ADR.

## Set up the workspace

```bash
uv sync --all-packages
uv run pre-commit install
just check
just banned
just trace
```

Feature changes must begin with tests that reference their acceptance criterion through an
`@pytest.mark.ac("AC-Fxx-NNN")` marker. Before opening a pull request, run every gate required by
the feature's Definition of Done.

Report suspected vulnerabilities privately according to [SECURITY.md](SECURITY.md); do not open
a public issue containing exploit details.
