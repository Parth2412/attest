# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Implemented the independent F-08 verification pipeline with mandatory identity and issuer
  constraints, explicit offline trust roots, Sigstore-native atomic verification, historical
  bundle support, hardened ChangeSet recomputation, stable fail-closed outcomes, real signed
  adversarial fixtures, 100% verifier coverage, and zero surviving verifier mutants.
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
