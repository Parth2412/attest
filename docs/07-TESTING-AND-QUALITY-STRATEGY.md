# attest — Testing and Quality Strategy

| Field | Value |
|---|---|
| Document ID | `QA-001` |
| Version | `1.0.4` |
| Status | **NORMATIVE** for test obligations |
| Last updated | 2026-09-10 |

---

## 1. Testing philosophy

This is a security and evidence product. The failure mode that matters is not a crash — it is a
**silently wrong attestation that verifies today and fails, or misleads, at audit time**.

Testing priorities, in order:

1. **Correctness of the digest and canonicalisation.** Wrong here, and every attestation ever
   produced is worthless.
2. **Strength of verification.** A verifier that accepts a forgery is worse than no verifier.
3. **Determinism.** Anything signed must be reproducible.
4. **Honest degradation.** Missing signals must produce `unknown`, never a confident default.
5. Everything else.

---

## 2. Test pyramid

| Layer | Share | Scope |
|---|---|---|
| Unit (pure) | ~55% | `attest-core`, `attest-policy` — no I/O, exhaustive |
| Vector conformance | ~10% | `spec/testvectors/` — the definition of correctness |
| Property-based | ~5% | Digest and canonicalisation invariants |
| Integration | ~20% | Real git repositories, recorded HTTP, Sigstore staging |
| Adversarial | ~5% | Forgery, tampering, replay — `BRD-F08 §7` |
| End-to-end | ~5% | Full workflow in CI on a real repository |

---

### 2.1 Monorepo test and tool boundaries

Each `packages/*/tests/` directory is a non-package test root: it **MUST NOT** contain
`__init__.py`. Pytest uses importlib mode so equal test filenames remain isolated by filesystem
path. Strict mypy runs separately over each workspace package. Ruff excludes Markdown from
formatting, and Bandit excludes test directories while continuing to scan every production module
under `packages/*/src/` (`ADR-026`).

---

## 3. Coverage requirements

| Package | Minimum | Rationale |
|---|---|---|
| `attest-core` | 95% | Everything depends on it |
| `attest-sign` (verifier module) | 95% | Security-critical |
| `attest-policy` | 95% | Pure, no excuse |
| All other packages | 90% | — |

Coverage is a floor, not a goal. 100% coverage with weak assertions is worse than 90% with
adversarial ones. Review assertions, not just the number.

---

## 4. Test vector conformance (NORMATIVE)

`spec/testvectors/` is the normative definition of correctness per `SPEC-001 §12`.

Rules:

- Vectors **MUST** be plain files with no dependency on attest's own code to interpret.
- A vector's expected output **MUST NOT** be regenerated from the implementation when a test
  fails. If implementation and vector disagree, one of them is wrong and a human decides which —
  **never** the failing party.
- Adding or changing a vector requires an ADR when it changes normative behaviour.
- Both git backends run the full vector suite (`ADR-007`).
- `statement-invalid-schema-*` vectors fail both the generated structural schema and Pydantic
  runtime validation. `statement-invalid-semantic-*` vectors may pass the structural schema but
  must fail runtime and verifier semantic validation (`ADR-021`).

> **This rule exists specifically to stop an AI agent "fixing" a failing test by regenerating the
> expected value.** That single behaviour would silently destroy the specification. It is called
> out again in `AGENTS.md §5`.

---

## 5. Schema drift check

CI job `schema-drift`:

1. Regenerate the structural JSON Schema from Pydantic models.
2. Compare against `spec/schemas/ai-authorship-v0.1.schema.json`.
3. Fail on any difference.

Because the schema is the published structural contract, an unnoticed representable model change
is a breaking change to the specification. Cross-field and other non-representable invariants are
covered separately by runtime and semantic-vector tests (`ADR-021`).

---

## 6. Import boundary enforcement

`import-linter` contracts, run in CI:

| Contract | Rule |
|---|---|
| `core-is-independent` | `attest_core` may not import any `attest_*` sibling |
| `core-is-pure` | `attest_core` may not import `httpx`, `pygit2`, `sigstore`, `subprocess`, `socket` |
| `peer-adapters-independent` | `attest_collect`, `attest_sign`, `attest_store`, and `attest_policy` may not import each other |
| `export-dependencies-bounded` | `attest_export` may import only `attest_core`, `attest_store`, and `attest_sign` internally |
| `cli-is-top-level-root` | Only `attest_cli` may import every internal package |
| `verifier-isolation` | The verifier module may not import the signer module |

---

## 7. Banned-language check

CI job greps source, docs, help text, and generated output for the banned phrases in
`GLOSS-001 §2.2`. Any match fails the build.

Rationale: over-claiming is a legal and credibility risk, and it is exactly the kind of phrasing
that creeps in during a marketing push or from a generative tool with an enthusiastic tone.

---

## 8. Requirement traceability enforcement

CI job:

1. Parse all `REQ-Fxx-NNN` identifiers from the BRDs.
2. Parse all `AC-Fxx-NNN` referenced in test names, docstrings, or markers.
3. Fail if any requirement for a feature marked Done has no referencing test.

Tests reference their criterion explicitly:

```python
@pytest.mark.ac("AC-F01-050")
def test_csd1_vectors_match_expected_digest(vector: Vector) -> None: ...
```

This is the mechanism that makes "no gaps" checkable rather than aspirational.

### 8.1 Pre-feature gate lifecycle

`BRD-INDEX §7.1` is the single machine-readable completion registry. A marker-specific pytest
gate may translate pytest's exit status `5` (no selected tests) to success only while none of that
gate's owning features is `Done`; it must report the gate as not applicable. Any other non-zero
status propagates unchanged. Vector tests are owned by F-01 and F-02; adversarial tests are owned
by F-08. Once any owner is `Done`, an empty selected suite is a failure.

The CI schema-drift job reports not applicable while F-01 is not `Done`. Once F-01 is `Done`, it
must generate and compare the schema on every run. The local release gate remains stricter before
F-01 and stops cleanly at `schema-check`.

---

## 9. Property-based testing

Required properties (minimum):

| Property | Applies to |
|---|---|
| Canonicalisation is idempotent | `canonicalize` |
| Digest is invariant under entry permutation | `CSD-1` |
| Digest changes under any single-field mutation | `CSD-1` |
| Model round-trip is lossless | all wire models |
| Policy evaluation is deterministic | `evaluate` |
| Verification never returns `verified` for a mutated payload | verifier |

The last one is the most valuable test in the codebase. Generate arbitrary valid bundles, mutate
one byte anywhere, assert verification never succeeds.

---

## 10. Integration testing rules

| Rule |
|---|
| Git fixtures are built programmatically in `tmp_path`; no committed binary repositories |
| Forge tests use recorded HTTP fixtures by default; live calls only in a nightly job |
| Sigstore tests target **staging only** — never write test data to the production transparency log |
| A guard test fails the suite if a production Sigstore endpoint is configured in test settings |
| No test may depend on the current wall clock; clocks are injected |
| No test may depend on network availability except the explicitly-marked nightly jobs |

---

## 11. Mutation testing

`mutmut` on `attest-core` (`digest.py`, `canonical.py`) and on the verifier module, run weekly
rather than per-commit. Surviving mutants are triaged: killed with a new test, or documented with
a written justification. An untriaged surviving mutant in the verifier blocks a release.

---

## 12. Release gates

A release **MUST NOT** ship unless:

- [ ] All CI jobs green on the release commit
- [ ] All test vectors pass on both git backends
- [ ] Adversarial suite green
- [ ] Schema drift check green
- [ ] Banned-language check green
- [ ] Traceability check green
- [ ] No untriaged surviving mutant in the verifier
- [ ] `pip-audit` reports no unmitigated high-severity advisory
- [ ] The release itself is attested by attest, and that attestation verifies publicly
- [ ] CHANGELOG updated
- [ ] Backwards compatibility confirmed: attestations from every prior version still verify

---

## 13. What is deliberately not tested

Stated so nobody spends effort here:

- Whether authorship claims are true (`ADR-003` — unknowable by design)
- Whether reviewers understood the code (unknowable)
- Third-party library internals (pin and trust; audit separately)
- Sigstore infrastructure availability (their SLO, not ours)
