# attest 0.1.5 / GitHub Action v1.0.5

This bounded patch restores the public signer's verified trust-material refresh path, publishes a
CLI that consumes that signer exactly, and restores repeatable GitHub-hosted cold-start headroom.
Verification rules, outputs, and failure semantics remain fail closed.

## Release contents

- GitHub Action `v1.0.5` pins the reviewed multi-platform image manifest
  `sha256:06581569a1382003b8537e016ce15b159066c275e186fbc27f8810da0105d5ab`.
- Image `0.1.5` retains digest-pinned `python:3.12.14-alpine3.23`, exact
  `git=2.52.0-r0` and `libgcc=15.2.0-r2`, and uses exact dynamic
  `libcrypto3=3.5.9-r0` and `libssl3=3.5.9-r0`.
- Locked `cryptography==50.0.1`, `pydantic-core==2.46.5`, and
  `rfc3161-client==1.0.8` are built from their hash-locked source distributions with removable
  `maturin==1.15.0`, `setuptools==84.0.0`, exact Alpine build packages, and the approved size
  flags. Native modules use pinned dynamic system OpenSSL/libgcc; only `rpds-py` retains a private
  libgcc name, replaced fail closed by a link to the pinned system file. Build tools are absent
  from the runtime image.
- Ambient identity and mandatory online trust acquisition begin concurrently with one bounded
  transient retry each, while the signer context and Rekor submission remain single-path.
- The image build verifies the closed production and staging TUF seed from Sigstore's embedded
  roots. Runtime homes receive only the nine hash-checked non-timestamp cache files and retain
  mandatory live root and timestamp refresh.
- The closed pure-Python runtime bytecode archive uses deterministic DEFLATE level 9 with sorted
  members, fixed timestamps and modes, and in-place imports; it introduces no runtime extraction
  path and leaves the already-deflated standard-library archive unchanged.
- The isolated wrapper may invoke the bundled CLI in-process only when the installed console
  script matches its build-generated SHA-256 marker. Any missing, malformed, symlinked, or changed
  script uses the existing sanitized subprocess boundary.
- Both `linux/amd64` and `linux/arm64` execute the complete 17-test real-container contract suite,
  including offline historical signature verification, before release.
- The retained candidate includes clean per-platform scans, SBOM, maximum provenance,
  source/context/manifest digests, and a GitHub-hosted identity-bound attestation. Attempt-1 run
  `38038325243` binds source `57ab2e08c297a2bf2131d2ea942d9e439d9c8faf` and context
  `sha256:58acc9a031c2d193f7160cffb16cd709ef7d1ce1dae6bb4cc92196b18a77b6bf`.
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
