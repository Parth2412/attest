# attest 0.1.6 / GitHub Action v1.0.6

This is an image-only security release. It replaces vulnerable runtime bytes in the GitHub
Action while preserving every Python package version, public API, input/output contract,
predicate, policy, storage format, and verification rule from `v1.0.5`.

## Security corrections

- The Action now vendors certifi `2026.10.19`, which replaces the CA bundle affected by
  `GHSA-6q48-6c7w-9gw2`.
- The final Alpine runtime contains musl `1.2.5-r24`, replacing `1.2.5-r23` affected by
  `CVE-2026-107891`. Both native build stages use the matching musl development revision.
- The minimal HTTPS transport uses Git `2.52.0` with curl `8.23.0`, OpenSSL `3.5.9`, and zlib
  `1.3.2`. curl 8.23.0 replaces 8.22.0 affected by `CVE-2026-92392` without enabling HTTP/2,
  HTTP/3, WebSockets, cookies, or another optional transport dependency.
- Development-only virtualenv `21.14.12` and python-discovery `1.6.4` are corrected in the
  repository lock and are absent from the Action runtime and clean public-package installations.

No Python distribution was rebuilt or published. Clean Python 3.12 and 3.13 environments verify
the unchanged public set exactly:

- `attest-core==0.1.0`
- `attest-collect==0.1.0`
- `attest-sign==0.1.1`
- `attest-store==0.1.1`
- `attest-policy==0.1.0`
- `attest-cli==0.1.4`

Those probes require certifi `2026.10.19` or later and reject development-only virtualenv and
python-discovery. The machine-readable release contract and evidence index record
`"pythonDistributionsPublished": []`.

## Reviewed candidate

Protected `dev` candidate run `39906806331`, attempt 1, completed every source, component,
two-platform container, image-scan, SBOM, provenance, and identity-attestation gate for source
commit `ae456176d0faefb732b9d8d8a4526365ad559278`.

- Multi-platform image:
  `sha256:f389b16257feab193532de0ea0b9339bb69255f9ff130f7b594f87ac4a0d10fe`
- Enumerated build context:
  `sha256:646ac89af1aa583ce3780c8542d980559a6782b171131df017daf35293440df1`
- Public identity-attested corresponding-source artifact:
  `sha256:535fb5f393bc57d28383cd8f453eac87e196531d44d28e835e54efefcbb22e0a`
- Retained curl 8.23.0 archive SHA-256:
  `8dadd7d2536a314f982ad05a651b713f426bf7d02cc2c76cffb9796f2218e6c5`
- Linux/amd64 manifest:
  `sha256:1770f3f63a11bb930c5ced53eebb7a58a158cfde08ed3d49b00d67800e131ed8`
- Linux/arm64 manifest:
  `sha256:52fe2e0ad06962a1b38db624673d5e2549468a4848bb673e3e25af4bb5128160`

Both architectures passed all 23 real-container contracts. Both image scans reported zero
vulnerabilities. The immutable component scan found only the existing Git-for-Windows-only
`CVE-2026-62960` match covered by the exact approved not-affected OpenVEX statement; curl 8.23.0
was clean.

Failed run `39829765757` remains immutable negative evidence. Its component gate rejected curl
8.22.0 and retained only the identity-attested source artifact
`sha256:5aef5c06c1989411d86c636c38dec652eec7747dccab739decc648ab560c23c4`;
it produced no binary candidate and is not reused or rerun.

## Release gate and compatibility

The exact merged `main` commit and reviewed image must complete three consecutive attempt-1
20-job performance runs—one automatic run and two reviewed dispatches—and their recomputed
60-sample nearest-rank p95 must remain strictly below the 18-second release SLO. The strict
15-second engineering target is reported independently.

The release workflow then promotes the reviewed manifest to image `0.1.6` without rebuilding,
creates immutable product/source tag `v0.1.6` and immutable Action tag `v1.0.6`, dogfoods the
unchanged public CLI, and retains complete attestation and release evidence. Moving major tag
`v1` is a separate reviewed promotion; it remains on immutable `v1.0.5` until release, public
same-repository proof, fork denial, and promotion checks all pass.
