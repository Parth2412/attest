# attest 0.1.5 / GitHub Action v1.0.5

This bounded patch restores the public signer's verified trust-material refresh path, publishes a
CLI that consumes that signer exactly, and restores repeatable GitHub-hosted cold-start headroom.
Verification rules, outputs, and failure semantics remain fail closed.

## Release contents

- GitHub Action `v1.0.5` pins the reviewed multi-platform image manifest
  `sha256:850942c64d29ecabb9560e128d38b148a0084012bd014804bdda992e5425dce7`.
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
- `attest-sign==0.1.1` is rebuilt from the reviewed source and published through its protected
  PyPI Trusted Publisher environment.
- `attest-cli==0.1.4` exact-pins `attest-sign==0.1.1`; both public distributions are byte-matched
  against locally built wheels and source archives, then clean-installed on Python 3.12 and 3.13.
- No other Python distribution is rebuilt or uploaded. Public versions remain
  `attest-core==0.1.0`, `attest-collect==0.1.0`, `attest-store==0.1.1`, and
  `attest-policy==0.1.0`.

## Immutability and promotion

Product/source tag `v0.1.5` and immutable Action tag `v1.0.5` resolve to the reviewed release
commit. Existing `0.1.4`, `v0.1.4`, and `v1.0.4` image and GitHub records remain unchanged; the
new Python patch versions are additive and immutable. The moving `v1` tag stays on `v1.0.4` until
the separate protected promotion revalidates the immutable release, production dogfood, public
same-repository proof, malicious-content non-execution, safe fork denial, and all retained
performance evidence.

Use immutable Action tag `v1.0.5` or its full release commit SHA until that independent promotion
completes.
