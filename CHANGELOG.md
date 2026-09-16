# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Implemented the hardened F-11 container Action runtime with closed inputs, fail-closed GitHub
  event and repository validation, OIDC-before-read enforcement, sanitized CLI execution,
  injection-safe outputs and summaries, and real-container contract coverage.
- Prepared the exact six-package `0.1.0` release set with complete PyPI metadata, exact internal
  pins, embedded licence content, archive/hash validation, and clean Python 3.12/3.13 wheel smoke
  tests; `attest-export` remains unpublished and outside the CLI dependency graph.
- Accepted ADR-046 and started F-11 with the exact container Action interface, six-package
  product 0.1.0 scope, independent Action v1.0.0/v1 lifecycle, two-phase digest-reviewed release,
  Trusted Publishing, and public repository, fork-safety, dogfood, and performance evidence gates.
- Implemented F-10's production CLI with the exact import-light command surface,
  provenance-aware strict configuration, bounded safe I/O, canonical stage artifacts, generated
  schemas, deterministic reports and exits, secure initialization, and full pipeline orchestration.
- Completed F-08's parse-only Bundle inspection with explicit `unverified-identity` results,
  ordered structure/payload/schema/model checks, and a boundary that cannot produce verified
  identity or policy evidence.
- Completed F-04's fail-closed GitHub ChangeSet context resolver with strict pull-request event
  parsing, PR-field fencing, exhaustive Compare pagination, forge merge-base selection, and
  immutable author/committer account IDs.
- Accepted ADR-045's complete F-10 CLI/configuration/artifact/output/security contract, added
  exact GitHub ChangeSet-context and labelled parse-only inspection prerequisites, reserved
  `attest export` for F-12, and assigned publication/live workflow proof to F-11.
- Implemented F-07 exact-byte storage through filesystem, Git CLI, optional pygit2, and OCI 1.1
  Referrers backends with deterministic multi-attestation retrieval, create-only concurrency,
  integrity validation, explicit fallback, bounded egress, and containment-safe staging.
- Defined the complete F-07 Git-ref, filesystem, OCI Referrers, concurrency, integrity,
  deadline, and local-fallback storage contract in ADR-043.
- Corrected additional F-07 Git locators to sibling refs so the base and multiple attestations can
  coexist without Git file/directory conflicts in ADR-044.
- Cleared parsed Statements from failed F-08 verification results so repository recomputation
  failures remain valid fail-closed policy inputs.
- Implemented F-09 strict bounded policy loading, generated policy schema, raw-byte glob matching,
  pure deterministic evaluation, complete predicate reporting, and fail-closed decision precedence.
- Implemented F-04 GitHub review evidence collection with immutable reviewer identities,
  exhaustive same-origin pagination, combined ruleset and classic-protection requirements,
  complete check-suite/run collection, bounded rate-limit handling, secret-safe authentication,
  deterministic evidence digests, and component-wise fail-open diagnostics.
- Implemented the independent F-08 verification pipeline with mandatory identity and issuer
  constraints, explicit offline trust roots, Sigstore-native atomic verification, historical
  bundle support, hardened ChangeSet recomputation, stable fail-closed outcomes, real signed
  adversarial fixtures, 100% verifier coverage, and zero surviving verifier mutants. F-08
  completed under the documented ADR-040 owner-only review exception.
- Required non-empty verification issuers so Sigstore cannot interpret an empty value as omission
  of the issuer policy.
- Defined the explicit F-08 verification boundary: required trust-source selection, bounded
  identity patterns resolved through Sigstore's exact policy, stable ordered check outcomes, and
  caller-selected repository ChangeSet recomputation.
- Implemented F-06 ambient-OIDC Sigstore signing with exact canonical DSSE payloads, explicit
  staging or production trust roots, fail-closed bundle postconditions, secret-safe diagnostics,
  hard process deadlines, retry suppression after Rekor begins, and live staging verification.
- Implemented F-05 pure deterministic Statement assembly, structural and semantic validation,
  total array ordering, golden-byte conformance, runtime collector metadata, and conservative
  GitHub Actions workload-identity context without retaining OIDC request credentials.
- Implemented F-03 deterministic authorship-claim collection across sidecars, commit trailers,
  Git AI `authorship/3.0.0` notes, and manual declarations, with exact source digests, graceful
  degradation, secure filesystem handling, and experimental Claude Code and Codex hook examples.
- Implemented F-02 deterministic Git ChangeSet collection with conformant pygit2 and Git CLI
  backends, stable diagnostics, raw-byte paths, hardened subprocess isolation, and monorepo-scale
  validation.
- Implemented F-01 core domain contracts, canonical JSON, CSD-1 digests, schemas, and vectors.
- Bootstrapped the zero-logic Python workspace defined by BOOT-001.
