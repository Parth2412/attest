# attest — Testing and Quality Strategy

| Field | Value |
|---|---|
| Document ID | `QA-001` |
| Version | `1.5.7` |
| Status | **NORMATIVE** for test obligations |
| Last updated | 2026-10-24 |

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
| `attest-store` | 90% | Persistent evidence must remain complete and retrievable |
| `action/` Python wrapper | 90% | Privileged public orchestration boundary |
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

1. Regenerate the Statement and policy structural JSON Schemas from their Pydantic models.
2. Compare against `spec/schemas/ai-authorship-v0.1.schema.json` and
   `spec/schemas/policy-v1.schema.json` once each owning feature is `Done`.
3. Fail on any difference.

Because the schema is the published structural contract, an unnoticed representable model change
is a breaking change to the specification. Cross-field and other non-representable invariants are
covered separately by runtime and semantic-vector tests (`ADR-021`). Policy loader safety, YAML
resource bounds, duplicate-key rejection, and policy cross-field invariants remain runtime tests
because generated schema alone cannot prove them (`ADR-042`).

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

The CI schema-drift job activates each schema independently: the Statement schema once F-01 is
`Done`, and the policy schema once F-09 is `Done`. A not-yet-Done owner is reported as not
applicable without disabling an already-active schema comparison. The local release gate remains
stricter and generates every implemented schema before release.

F-10 adds three independently generated contracts: CLI config v1, Collection Artifact v0.1, and
CLI output v0.1. Their drift comparisons activate as soon as each generator/model lands and all
three are mandatory before F-10 may be `Done`. Hand-authored expected schemas or one generator
silently updating another schema are forbidden (`ADR-045`).

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
| Storage conformance runs against filesystem, OCI fixture, Git CLI, and pygit2 implementations; OCI fixture traffic remains local |
| Storage concurrency uses processes, not only threads, and asserts exact-byte completeness plus containment |
| GitHub context fixtures prove exact event/PR/Compare endpoints, PR-field binding, forge merge base, complete pagination/counts, and every numeric author/committer association; no live call in default CI |
| CLI integration uses deterministic injected adapters to compare standalone stages with `run`, while installed-wheel tests exercise the real console entry point |
| CLI file-I/O tests race and replace inputs/outputs, exercise symlinks/devices/limits, and assert create-only or explicit atomic overwrite behavior |
| CLI egress tests deny sockets by default and allow only the operation and explicit option under test; doctor probes never send credentials or sign |
| Action contract tests run the real container entry point with table-driven inputs/events and hostile paths, environment, summaries, output files, workflow commands, and repository executables |
| Action signer tests prove a caller marker cannot authorize `fork`, every unsafe platform/thread/fallback path uses `spawn`, the guarded real container creates an actual `fork` child, authorization resets after one invocation, and both start methods retain the same supervised process boundary |
| Action tests prove OIDC preflight precedes repository reads in `run`, while `verify` and `gate` never request OIDC |
| Action policy-advisory tests neutralize only verified decision-backed exits `3`/`5`; every configuration, verification, signing, storage, network, and internal failure remains fatal |
| Candidate/release tests inspect final build-context equality, exact manifest promotion, both image architectures, base and Action digest pins, lock equality, SBOM, provenance, GitHub artifact attestation, and clean package/image installation |
| Production Sigstore is used only for the public release/dogfood proof; ordinary integration signing remains on staging |
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

- [x] All CI jobs green on the release commit
- [x] All test vectors pass on both git backends
- [x] All storage conformance tests pass on filesystem, OCI fixture, Git CLI, and pygit2 backends
- [x] Adversarial suite green
- [x] Schema drift check green
- [x] CLI config, Collection Artifact, and output schema drift checks green once F-10 is implemented
- [x] Banned-language check green
- [x] Traceability check green
- [x] No untriaged surviving mutant in the verifier
- [x] `pip-audit` reports no unmitigated high-severity advisory
- [x] Candidate and protected release workflows prove final build-context equality, exact candidate manifest promotion, both target architectures, a pinned base, SBOM, provenance, and GitHub artifact attestations
- [x] Build and publish authority are separated; PyPI Trusted Publishing uses the six protected per-package environments and no long-lived package token exists
- [x] The first-release PyPI bootstrap verifies wave one publicly before exposing the protected second-wave registration checkpoint; image promotion and final release remain blocked until all six publications succeed
- [x] Clean environments install and smoke-test exactly the six approved `0.1.0` distributions; `attest-export` is neither published nor a CLI dependency
- [x] The `0.1.1` correction builds and publishes only `attest-cli`, proves its five exact `0.1.0` library pins in clean Python 3.12/3.13 environments, and verifies both public files byte-for-byte through version-specific PyPI metadata; an exact recovery imports the prior OIDC evidence, never re-uploads, and crosses the intentionally skipped publisher only when every required direct gate reports success
- [x] The `0.1.1` correction proves the public `0.1.0` image digest and immutable `v1.0.0` record are unchanged, creates protected immutable `v0.1.1`/`v1.0.1` records, and does not move `v1` before the replacement public proof succeeds
- [x] The `0.1.2` correction builds and publishes only `attest-cli`, retains the five exact `0.1.0` library pins, builds/scans/attests a new two-platform candidate image, proves final context equality, and promotes that exact manifest to `0.1.2` without rebuilding
- [x] The `0.1.2` release creates protected immutable `v0.1.2`/`v1.0.2` records without changing any earlier PyPI file, image, tag, or Release; `v1` moves only after the replacement public proof establishes the required blocked, denied, approved, malicious-content, and fork states
- [x] The `0.1.3` correction publishes only store `0.1.1` and CLI `0.1.3`, imports a stable exact-digest attestation-ref snapshot without overwriting local refs or `FETCH_HEAD`, promotes the exact reviewed `0.1.3` image candidate, and creates protected immutable `v0.1.3`/`v1.0.3` records without changing earlier public artifacts
- [x] The `0.1.3` replacement proof retains the public v1.0.2 denied Bundle, publishes an approved sibling Bundle for the same ChangeSet, and completes blocked, denied, approved, malicious-content, and fork states before `v1` moves
- [x] The `0.1.4-candidate` image uses the ADR-053 digest-pinned Alpine base and exact package set, passes both architecture scans, and retains SBOM, provenance, context/manifest digests, and identity-bound GitHub attestation
- [x] The exact merged Action and candidate digest pass 20 fresh attempt-1 hosted measurements below 15 s nearest-rank p95 before image `0.1.4`, source `v0.1.4`, or Action `v1.0.4` is published; no Python distribution is rebuilt or uploaded
- [x] The `v1.0.4` public proof, release evidence, and performance evidence verify before the reviewed procedure moves `v1` from `v1.0.3`
- [x] Candidate run `38250635610` proves the `0.1.5-candidate` image uses ADR-059's exact locked source builds for cryptography, pydantic-core, and rfc3161-client, the exact build-only toolchain and size flags, pinned dynamic system OpenSSL/libgcc with only the closed `rpds-py` compatibility link, ADR-058's build-verified non-timestamp TUF seed, ADR-060's deterministic DEFLATE level-9 pure-Python runtime archive, and ADR-061's debug-range, guarded process-boundary, and exact branch-dispatch controls; both architectures pass all 20 real-container cryptographic/native-module/trust-seed/archive/event tests, scans, SBOM/provenance checks, and identity-bound attestation
- [x] The exact merged Action and `0.1.5-candidate` digest complete three consecutive fresh attempt-1 20-job measurements; every run and the combined 60 samples remain strictly below the 18 s nearest-rank p95 release SLO, while the strict 15 s engineering target is reported independently, before image `0.1.5`, source `v0.1.5`, or Action `v1.0.5` is published
- [x] The signer contracts prove concurrent ambient OIDC and mandatory online trust acquisition, refreshed-root identity-bound verification of the exact DSSE payload, the ADR-056 one-retry pre-Rekor ceiling, ADR-057's two-call transient acquisition ceilings, and one signer/Rekor path per attempt without any offline-only success
- [x] The Action-only signer process boundary permits `fork` solely through the digest-matched adapter's fresh scoped capability on Linux's sole main thread, rejects caller markers, and preserves identical isolation, deadline, retry, termination, and secret-safety behavior under `spawn` and `fork`
- [x] Local build and real-container contracts prove both deterministic archives omit only fine-grained debug ranges and that exact branch dispatches derive the checked-out head's first parent while malformed, tag, root, incomplete, and inconsistent dispatches fail closed
- [x] Candidate run `38529646263` proves ADR-062's exact hash-locked Git/curl source builds, licences, component SPDX, immutable CPE-aware Grype output, the single exact OpenVEX not-affected statement, and unchanged vulnerability gate; both-platform local and verified-HTTPS transport, forbidden-library absence, loader mappings, binary hashes/sizes, and four-layer/three-primary-zstd layout; public identity-attested source artifact `sha256:0855c9c357f8764b18f288c6b13dd5a0859424f12264fa3140e08680637d0457` preceded and is linked from image `sha256:6e1656ab5da1d5abc43c0ec36e6f3010f1f52c2528ff0e868eb2f62b5754906a`
- [x] The bounded release builds only `attest-sign==0.1.1` and `attest-cli==0.1.4`, proves the exact internal pin, uses their separate protected Trusted Publishers without `skip-existing`, matches both public artifacts byte-for-byte, and clean-installs them on Python 3.12 and 3.13 without rebuilding another distribution
- [x] The `v1.0.5` release, dogfood, onboarding proof, fork denial, three-run performance evidence, and immutable records verify before the reviewed procedure moves `v1` from `v1.0.4`
- [x] The bounded `dev` integration uses `[skip ci]` only after all required pull-request checks pass, proves the squash tree equals the checked head, and starts no Action candidate run; the exact `main` release commit contains no skip directive and passes the complete CI suite
- [x] The release itself is attested by attest, and that attestation verifies publicly
- [x] CHANGELOG updated
- [x] Backwards compatibility confirmed: attestations from every prior version still verify
- [x] F-11 fresh-repository test proves the generated F-10 workflow runs unmodified with the published full-SHA Action and immutable image digest
- [x] F-11 real-repository evidence proves required expected-App-pinned blocking/success states, safe fork failure before repository reads, and no untrusted repository execution
- [x] F-11 retains the historical 20-job release gate; immutable failed runs `37796984054`, `37899003696`, `37946041636`, `38056326479`, `38257587284`, and `38570478871`; and, for ADR-063, three fresh consecutive attempt-1 20-job Action-step measurements plus the combined 60-sample result; every result includes image pull, reports the strict 15-second engineering target, and passes the strict release SLO below 18 seconds
- [x] The `ADR-065` lock contains exact `certifi==2026.10.19`, `virtualenv==21.14.12`, and `python-discovery==1.6.4`; dependency audit is clean; and both real-container platforms prove the corrected certifi runtime and virtualenv exclusion
- [x] The `ADR-066` image builds against exact `musl-dev==1.2.5-r24`, runs exact `musl==1.2.5-r24`, retains its single-line installed-version record after package metadata removal, and rejects affected `r23` on both architectures
- [x] The `ADR-067` source, Dockerfile, component, and release contracts require signed, SHA-512-locked curl `8.23.0`, reject `8.22.0`, preserve the HTTP/1.1-only transport and sole Git VEX statement, and retain failed run `39829765757` as negative evidence
- [x] Candidate run `39906806331`, attempt 1, proves exact source `ae456176d0faefb732b9d8d8a4526365ad559278`, context `sha256:646ac89af1aa583ce3780c8542d980559a6782b171131df017daf35293440df1`, corresponding source `sha256:535fb5f393bc57d28383cd8f453eac87e196531d44d28e835e54efefcbb22e0a`, and multi-platform candidate `sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe` pass every existing source-correspondence, 23-test real-container, two-platform scan, component-scan, SBOM, provenance, and identity-attestation gate before reviewed digest pinning
- [x] Performance runs `39987447085`, `39987667038`, and `39987819708`, all attempt 1, record p95 values of 16, 14, and 13 seconds and a recomputed 60-sample p95 of 16 seconds; every result passes the unchanged schema-2 release SLO before exact image `0.1.6`, source `v0.1.6`, and immutable Action `v1.0.6` publish without a Python distribution
- [x] Release run `39988130356`, same-repository proof PR #11, fork-denial PR #12/run `39989723943`, public-package non-publication checks, and protected promotion run `39994508140` verify before `v1` moves from `v1.0.5` to exact release commit `e693e6b60afdf9c667a913faa4f9652bfd6dc050`
- [x] ADR-068 unit and macOS evidence proves atomic exclusive filesystem-lock creation, safe existing-lock fallback, symlink denial, and ten fresh process-contention rounds; the exact failure was reproduced over 100 rounds before correction
- [x] Candidate workflow contracts require store `0.1.2`, exact-pinned CLI `0.1.5`, the unique `0.1.7-candidate` label, and the bounded 90-minute build ceiling while retaining every existing gate
- [ ] A new attempt-1 candidate passes both architectures after cancelled old-label run `40086747745`, whose successful pre-build evidence and missing binary remain retained
- [ ] Three fresh ordered attempt-1 20-job measurements and their recomputed 60 samples pass the unchanged schema-2 release SLO for the exact merged commit and candidate
- [ ] Protected release publishes only store `0.1.2` and CLI `0.1.5`, verifies exact public bytes and clean Python 3.12/3.13 installs, promotes immutable `0.1.7`/`v0.1.7`/`v1.0.7`, and completes dogfood and both public proofs before independently reviewed `v1` movement

---

## 13. What is deliberately not tested

Stated so nobody spends effort here:

- Whether authorship claims are true (`ADR-003` — unknowable by design)
- Whether reviewers understood the code (unknowable)
- Third-party library internals (pin and trust; audit separately)
- Sigstore infrastructure availability (their SLO, not ours)
