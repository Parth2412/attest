---
name: verify-library-api
description: Use before writing any call into sigstore, pygit2, securesystemslib, rfc8785, pydantic, oras, or any other pinned dependency in the attest repository. Enforces AGENTS.md §4 - confirm the installed version, read the installed source, run a throwaway script, then implement. Never write a library call from memory.
---

# Verify the library API before writing code

`AGENTS.md §4` — the most important practical rule in this repository.

> **You do not know the API surface of the pinned libraries. Verify before you write.**

This matters more here than in ordinary projects for one reason: **cryptographic libraries that
appear to work while being used incorrectly are the worst possible outcome.** The failure is
invisible until an auditor cannot verify an attestation, which is years later and is exactly when
the evidence was supposed to be worth something.

## The loop

### 1. Confirm what is actually installed

```bash
uv pip show sigstore
uv pip show pygit2
uv run python -c "import sigstore; print(sigstore.__version__, sigstore.__file__)"
```

`uv.lock` is the source of truth for versions (`TECH-001 §3`). Never write a version number from
memory, and never `uv add` a version you "remember working".

### 2. Read the installed source, not the docs

```bash
# Where does it live
uv run python -c "import pygit2, pathlib; print(pathlib.Path(pygit2.__file__).parent)"

# What does the object actually expose
uv run python -c "import pygit2; help(pygit2.Repository.diff)"
uv run python -c "import inspect, pygit2; print(inspect.signature(pygit2.Repository.diff))"
```

Published documentation lags the installed version. The installed source does not.

### 3. Run a throwaway script that exercises the exact call

Put it in a scratch directory, **never in `packages/`**. It exists to answer one question.

```python
# scratch/check_pygit2_no_renames.py
# Question: does pygit2 give a tree diff with rename AND copy detection genuinely off?
# Governing requirement: REQ-F02-010, ADR-001
import pygit2
repo = pygit2.Repository(".")
diff = repo.diff("HEAD~1", "HEAD")   # inspect: are similarity flags off by default?
for d in diff.deltas:
    print(d.status_char(), d.old_file.path, d.new_file.path, d.old_file.id, d.new_file.id)
```

Run it. Read the output. Only then write the implementation.

### 4. Verify negatively where the property is a *rejection*

Some assumptions are only proven by something **failing**. The critical one:

> **`CH-02` assumption C** — verification can be constrained to an expected certificate identity
> *and* issuer. Prove it by signing as identity X, verifying constrained to identity Y, and
> confirming verification **fails**. A passing verification proves nothing here.

Same shape applies to: naive datetimes must be rejected (`REQ-F01-070`), abbreviated OIDs must be
rejected (`REQ-F01-080`), floats must be rejected by canonicalisation (`REQ-F01-040`), unknown
predicate types must be rejected (`REQ-F08-090`), unknown enum values must raise rather than
coerce (`BRD-F01 §4.2`).

### 5. Record what you verified

In the session report:

```
VERIFIED: sigstore 3.x — ambient GitHub Actions OIDC detected without manual token handling (REQ-F06-030)
UNVERIFIED: oras push to a private registry — no registry available in this environment (REQ-F07-060)
```

Anything you could not execute is `UNVERIFIED:` and must be reported. Never leave one unreported.

## Test signing targets staging. Always.

```
SIGSTORE_ENVIRONMENT=staging   # or the equivalent for the installed client — verify it
```

Writing test attestations to the **production** transparency log pollutes a public, append-only
log that cannot be cleaned. This is a hard rule (`TECH-001 §6`, `QA-001 §10`), and a guard test
fails the suite if a production endpoint is configured in test settings.

## The eight assumptions that must hold (`CHALLENGE-001 §4`)

Each is verified by executing code, one throwaway script per assumption:

| # | Assumption | Requirement |
|---|---|---|
| A | `sigstore-python` detects the GitHub Actions ambient OIDC credential without manual token handling | `REQ-F06-030` |
| B | The bundle embeds a Rekor inclusion proof verifiable **offline** | `REQ-F08-070`, `ADR-015` |
| C | Verification can be constrained to an expected identity **and** issuer | `REQ-F08-040` — **if this fails, the product has no security property** |
| D | A Sigstore staging environment is usable for tests | `QA-001 §10` |
| E | `securesystemslib` DSSE envelopes interoperate with the Sigstore bundle format | `REQ-F06-020` |
| F | `pygit2` exposes tree-diff with rename detection genuinely off | `REQ-F02-010` |
| G | `rfc8785` output matches a second independent JCS implementation | `REQ-F01-030` |
| H | Pydantic v2 JSON Schema generation covers every construct the models need | `REQ-F01-120` |

## If you cannot verify

Say so and stop. Guessing is never acceptable here. Report:

```
BLOCKED: cannot verify <assumption> — <what is missing: no network, no registry, no staging credential>
```

A blocked session that reports honestly costs an hour. Confident wrong code in a signing path
costs the product.
