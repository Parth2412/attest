# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

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
