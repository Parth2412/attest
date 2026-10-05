# attest 0.1.5 / GitHub Action v1.0.5

This image-only patch restores repeatable GitHub-hosted cold-start headroom while preserving the
public CLI, verification rules, outputs, and failure semantics.

## Release contents

- GitHub Action `v1.0.5` pins the reviewed multi-platform image manifest
  `sha256:6d0deb74d178d37971f36c226bde2e45072fa4f1bcf24b68e91401a2518964c7`.
- Image `0.1.5` retains digest-pinned `python:3.12.14-alpine3.23`, exact
  `git=2.52.0-r0` and `libgcc=15.2.0-r2`, and uses exact dynamic
  `libcrypto3=3.5.9-r0` and `libssl3=3.5.9-r0`.
- Locked `cryptography==50.0.1` is built from its hash-locked source distribution with removable
  `maturin==1.15.0`, `setuptools==84.0.0`, and exact Alpine build packages. Build tools are absent
  from the runtime image.
- The isolated wrapper may invoke the bundled CLI in-process only when the installed console
  script matches its build-generated SHA-256 marker. Any missing, malformed, symlinked, or changed
  script uses the existing sanitized subprocess boundary.
- Both `linux/amd64` and `linux/arm64` execute the complete 14-test real-container contract suite,
  including offline historical signature verification, before release.
- The retained candidate includes clean per-platform scans, SBOM, maximum provenance,
  source/context/manifest digests, and a GitHub-hosted identity-bound attestation.
- The exact merged Action and candidate digest must pass three consecutive fresh attempt-1 hosted
  measurements of 20 jobs each. Every individual p95 and the combined 60-sample p95 must remain
  below 15 seconds.
- No Python distribution is rebuilt or uploaded. Public Python packages remain at their existing
  released versions, including `attest-cli==0.1.3`.

## Immutability and promotion

Product/source tag `v0.1.5` and immutable Action tag `v1.0.5` resolve to the reviewed release
commit. Existing `0.1.4`, `v0.1.4`, and `v1.0.4` records remain unchanged. The moving `v1` tag
stays on `v1.0.4` until the separate protected promotion revalidates the immutable release,
production dogfood, public same-repository proof, malicious-content non-execution, safe fork
denial, and all retained performance evidence.

Use immutable Action tag `v1.0.5` or its full release commit SHA until that independent promotion
completes.
