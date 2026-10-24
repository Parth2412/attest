# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

- Accepted ADR-068 and reopened F-11 for the bounded filesystem-lock correction. Workspace store
  `0.1.2` uses atomic exclusive lock creation with a safe existing-lock fallback, and CLI `0.1.5`
  exact-pins that store. A new `0.1.7-candidate` must repeat every two-platform supply-chain,
  performance, release, public-proof, and reviewed-promotion gate before these versions are called
  public. Cancelled old-label run `40086747745` remains incomplete non-promotable evidence; its
  60-minute build ceiling becomes 90 minutes without changing inputs, privileges, or gates.
- Completed the `ADR-065`–`ADR-067` security replacement on exact release commit
  `e693e6b60afdf9c667a913faa4f9652bfd6dc050` and multi-platform manifest
  `sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe`. Three
  attempt-1 performance runs and their combined 60 samples passed the unchanged release SLO;
  protected release run `39988130356` published immutable product `v0.1.6`, image `0.1.6`, and
  Action `v1.0.6` without publishing a Python distribution. Same-repository proof PR #11,
  fork-denial PR #12, and protected promotion run `39994508140` completed before reviewed `v1`
  moved to the exact release commit, returning F-11 to Done.
- Protected candidate run `39906806331` passed every `ADR-065`–`ADR-067` two-platform source,
  runtime, scan, SBOM, provenance, and identity gate for the unique `0.1.6-candidate`; the Action,
  performance, and release workflows now pin its reviewed manifest for the image-only `v1.0.6`
  lifecycle while explicitly publishing no Python distribution.
- Accepted ADR-067 after protected candidate run `39829765757` rejected source-built curl 8.22.0
  for fixable High `CVE-2026-92392`. The Action now pins the signed upstream curl 8.23.0 archive
  and exact component identity without changing transport features, VEX policy, release versions,
  or the no-PyPI boundary; the failed source artifact and scan remain immutable negative evidence.
- Accepted ADR-066 and extended the unreleased Action security replacement with exact Alpine
  `musl 1.2.5-r24` build/runtime pins plus retained installed-version evidence for
  `CVE-2026-107891`; ADR-065's versions, no-PyPI boundary, and complete release gates are unchanged.
- Accepted ADR-065 and reopened F-11 for an image-only security replacement: the workspace now
  locks corrected `certifi 2026.10.19`, development-only `virtualenv 21.14.12`, and
  `python-discovery 1.6.4`; a unique two-platform `0.1.6-candidate` must repeat every supply-chain,
  performance, release, dogfood, public-proof, and reviewed-promotion gate without publishing a
  Python distribution or mutating an earlier record.
- Completed F-11 under ADR-064 on exact product release `v0.1.5` and Action `v1.0.5`: the three
  attempt-1 performance runs and combined 60 samples passed the strict release SLO, signer `0.1.1`
  and CLI `0.1.4` verified publicly, the reviewed image was promoted without rebuilding, dogfood
  and same-repository/fork proofs completed, and protected reviewed promotion moved `v1` to the
  immutable release commit.
- Accepted and implemented ADR-062's source-verified minimal Git/HTTPS Action runtime after
  ADR-061 run `38257587284` retained 20 successful samples but failed closed at p95 17 seconds.
  The Action now builds hash-locked Git 2.52.0 and curl 8.22.0 with their minimal verified
  transport closure, publishes identity-attested corresponding source before the binary, scans
  exact CPE component evidence with immutable Grype and one exact Windows-only OpenVEX
  not-affected statement, and retains both-platform layer/binary/loader and release evidence.
  Candidate run `38529646263` passed the complete source, component, platform, scan, SBOM,
  provenance, and attestation gates for image
  `sha256:6e1656ab5da1d5abc43c0ec36e6f3010f1f52c2528ff0e868eb2f62b5754906a`; the complete
  three-run performance sequence remains required.
- Added ADR-060's deterministic DEFLATE level-9 pure-Python runtime archive, reducing the Action's
  applied filesystem footprint while retaining the closed bytecode set, fixed metadata, in-place
  imports, and every existing candidate and performance gate.
- Added ADR-059's exact locked source builds for cryptography, pydantic-core, and rfc3161-client,
  reducing the Action image by about 14% while retaining pinned dynamic system OpenSSL/libgcc,
  one fail-closed `rpds-py` compatibility link, and both-platform native execution contracts.
- Added the ADR-057 bounded acquisition correction: ambient OIDC and mandatory online trust now
  start concurrently, each transient network boundary receives at most one retry before success,
  and no retry can duplicate the signer context or Rekor submission.
- Implemented the ADR-055/ADR-056 signing correction with mandatory concurrent online trust
  refresh, refreshed-root exact-payload verification, and bounded stale-bootstrap recovery; prepared
  only `attest-sign 0.1.1` and exact-pinned `attest-cli 0.1.4` for protected Trusted Publishing,
  public byte verification, and clean Python 3.12/3.13 installation.
- Accepted ADR-054 and began the originally image-only `0.1.5` / Action `v1.0.5` reliability
  correction with locked source-built cryptography, exact runtime OpenSSL, balanced zstd layers, a
  digest-guarded single-interpreter Action path, both-platform container contracts, and three
  consecutive 20-job release measurements; ADR-055 subsequently amended its package boundary.
- Completed the image-only `0.1.4` / Action `v1.0.4` release, public same-repository and fork
  proofs, exact p95 14-second release gate, production dogfood verification, and protected reviewed
  promotion of moving `v1`; retired the bounded one-time recovery workflow after publication.
- Replaced the Action runtime with a digest-pinned Alpine image, removed unused system `pip`,
  added exact 20-job merged-commit cold-start enforcement, and prepared the image-only `0.1.4` /
  Action `v1.0.4` release without rebuilding or publishing any Python distribution.
- Added bounded, create-only Git attestation-ref discovery before local sibling allocation so
  fresh CI reruns retain denied and approved Bundles for one ChangeSet without overwriting evidence;
  remote discovery failures preserve the new exact Bundle in the configured filesystem fallback.
- Corrected generated pull-request workflow identities to the bounded
  `refs/pull/*/merge` certificate ref, preserved known verification failures at the Action
  boundary without emitting unverified facts, and prepared the `attest-cli 0.1.2` / Action
  `v1.0.2` candidate with a newly reviewed runtime image.
- Hardened patch publication recovery with version-specific PyPI metadata, full metadata/hash/byte
  retries, deterministic exact-publication detection, validated retention of the original OIDC
  publishing evidence without duplicate uploads, and explicit fail-closed continuation across the
  intentionally skipped publisher job.
- Corrected the Docker Action token evaluation boundary, added exact caller-step token handoff,
  and prepared the bounded `attest-cli 0.1.1` / Action `v1.0.1` release without rebuilding the
  five `0.1.0` libraries or the reviewed multi-platform image.
- Added a two-wave, approval-gated PyPI bootstrap that respects the three-pending-publisher limit,
  verifies the first public wave byte-for-byte, and blocks final image and release publication
  until all six OIDC-only package jobs succeed.
- Isolated first-release PyPI Trusted Publishing by distribution so all six projects can be
  bootstrapped without long-lived credentials while preserving build-once release artifacts.
- Added the protected F-11 release workflow for exact candidate promotion, six-package Trusted
  Publishing, clean public verification, production self-attestation, immutable release evidence,
  and independent product and Action tags.
- Added the closed public F-11 Docker Action manifest with the reviewed immutable multi-platform
  image digest, exact five-input/four-output interface, and automatic GitHub token injection.
- Added the F-11 candidate supply chain with a Git-tracked deterministic build context,
  multi-platform GHCR image build, per-platform scanning, BuildKit SBOM/provenance, GitHub artifact
  attestation, identity-bound verification, retained digest evidence, and a fail-closed security
  gate for secrets, critical vulnerabilities, and fixable high vulnerabilities.
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
