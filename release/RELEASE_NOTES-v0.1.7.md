# attest 0.1.7 / GitHub Action v1.0.7

This is a bounded storage-correctness release. It fixes filesystem lock acquisition under
cross-process contention while preserving the storage API, on-disk format, error catalogue,
attestation predicates, policy semantics, and every earlier immutable public record.

## Python patch boundary

Only these two Python distributions are built once and published through their separate protected
PyPI Trusted Publishers:

- `attest-store==0.1.2` replaces the lock-file check-then-create race with atomic exclusive
  creation and a safe existing-lock fallback while retaining no-follow, regular-descriptor, and
  advisory-lock validation.
- `attest-cli==0.1.5` exact-pins `attest-store==0.1.2` and otherwise preserves its command and
  dependency contract.

The remaining public internal graph is unchanged: `attest-core==0.1.0`,
`attest-collect==0.1.0`, `attest-sign==0.1.1`, and `attest-policy==0.1.0` are neither rebuilt nor
uploaded. `attest-export` remains unpublished. The machine-readable release contract records
`"pythonDistributionsPublished"` as exactly `attest-store==0.1.2` and `attest-cli==0.1.5`.

Clean Python 3.12 and 3.13 environments must byte-match both public artifacts, install the exact
six-package graph, execute the CLI, require certifi `2026.10.19` or later, and reject the
development-only virtualenv `21.14.12` and python-discovery `1.6.4` packages from the runtime.

## Retained Action security baseline

The new Action image carries the corrected store and CLI bytes without weakening the reviewed
runtime boundary. It retains source-built Git `2.52.0` and curl `8.23.0`, exact musl `1.2.5-r24`,
the locked certifi `2026.10.19` CA bundle, matching OpenSSL runtime libraries, the minimal
HTTP/1.1-only Git transport, four zstd image layers, and the digest-guarded isolated Python path.

## Reviewed candidate

Protected `dev` candidate run `40114789855`, attempt 1, completed every repository, corresponding
source, component, two-platform container, image-scan, SBOM, provenance, and identity-attestation
gate for source commit `62b72c2537176c84bc232f727f223a9ea21ae80b`.

- Multi-platform image:
  `sha256:14e47087c9e6346c8115ba29eb00a922fcc3da630411058f8f35fee7684bf356`
- Enumerated 115-file build context:
  `sha256:580c0b7881882817ae7ca65dfe1bbdcd06c5bea77556c8b77ff5b04e11cacc73`
- Public identity-attested corresponding-source artifact:
  `sha256:7472c920350b428c850a6f18f2e17693431b0e89761ef52498b009b0ea447805`
- Linux/amd64 manifest:
  `sha256:0b14b2da68d2abce405cf87bf7abf56497cd13707bde1b2da634b83bfe31608f`
- Linux/arm64 manifest:
  `sha256:40ad43b5cc948eeedb09373e241d0e42448cd04e93e2f33e7365a46c0c136de8`

Both architectures passed all 23 real-container contracts. Both image scans reported zero
vulnerabilities. The component scan retained only the existing Git-for-Windows-only
`CVE-2026-62960` match covered by the exact approved not-affected OpenVEX statement; curl 8.23.0
was clean. Independent verification reproduced the context digest and validated the exact image,
source, manifests, labels, component policy, and GitHub-hosted workflow identities.

Cancelled run `40086747745` remains immutable incomplete evidence. It passed the pre-build gates
but reached the former 60-minute build ceiling before emitting a binary, so it is not a candidate
and is never reused. Run `40114789855` used the approved 90-minute ceiling without changing an
input, runner class, privilege, or verification gate.

## Release gate and compatibility

The exact merged `main` commit and reviewed image must complete three consecutive attempt-1
20-job performance runs. Each run and the recomputed 60-sample nearest-rank p95 must remain
strictly below the 18-second release SLO; the strict 15-second engineering target is reported
independently.

Only after that evidence passes may the protected release publish the two Python patches, promote
the reviewed manifest without rebuilding to image `0.1.7`, create immutable source `v0.1.7` and
Action `v1.0.7`, and complete production dogfood. Moving major tag `v1` is a separate reviewed
promotion. It remains on immutable `v1.0.6` until the release, same-repository proof, safe fork
denial, public verification, and independent promotion checks all pass.
