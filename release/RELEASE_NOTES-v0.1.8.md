# attest 0.1.8 / GitHub Action v1.0.8

This is a bounded Action-image security release. It replaces two dependency versions affected by
newly published advisories while preserving the public CLI and every existing Python distribution.

## Security correction

- The locked runtime dependency `dnspython` is upgraded from 2.8.0 to dnspython `2.9.0`, the
  first version containing the upstream fix for CVE-2026-114605 / GHSA-45c3-73f7-pv4m.
- The development-only audit dependency `msgpack` is upgraded from 1.2.2 to msgpack `1.2.3`,
  the first version containing the upstream fix for CVE-2026-114613 / GHSA-j586-36cw-2gc2.
- The released container includes `dnspython==2.9.0`. It excludes msgpack,
  virtualenv `21.14.13`, and python-discovery `1.6.4` because those packages are not runtime
  dependencies.
- The existing certificate floor remains enforced at certifi `2026.10.19`.

No Python distribution is built or uploaded by this release. The release contract records
`"pythonDistributionsPublished": []` and verifies the unchanged public set on Python 3.12 and
3.13, including `attest-sign==0.1.1` and `attest-cli==0.1.5`.

## Reviewed candidate

- Candidate workflow run: `40674146751` (attempt 1)
- Candidate source commit: `905c30679d291bce13ad3140703162cf3405e55b`
- Enumerated context digest:
  `sha256:8b863e6dc4733bb7050b27f34863b3db87db7ff069562ce348a98db0642c17bd`
- Multi-platform image digest:
  `sha256:1b40c02bfacaae958a2adf9bfc25485fe0c22794db50c19aa401db530ea36c61`
- Corresponding-source artifact digest:
  `sha256:7a346ff30f6886f5ab06045b0dfd2be645fd2a9df9a6fdabc1f280562e2ae1af`

The candidate passed the complete candidate gate, source publication and attestation, component
scan, amd64 and arm64 image scans, real-container tests on both platforms, SBOM and provenance
validation, and identity-bound GitHub artifact attestation. The runtime continues to use
Git `2.52.0`, curl `8.23.0`, and musl `1.2.5-r24`.

## Release gates

Before publication, the exact merged commit must pass three consecutive attempt-1 hosted
performance runs. The release workflow recomputes every result and the combined 60-sample
cold-start gate against the reviewed image digest. It then promotes that manifest without
rebuilding, dogfoods the public CLI, attests every release asset, and publishes immutable
`v0.1.8` and `v1.0.8` records.

The moving major tag `v1` remains on the independently reviewed prior release `v1.0.7` until
same-repository execution proof, fork-denial proof, and a separate protected promotion review
complete.
