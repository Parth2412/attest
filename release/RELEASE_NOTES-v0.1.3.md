# attest 0.1.3 / GitHub Action v1.0.3

This corrective release makes durable-store publication deterministic across fresh repositories
that publish attestations for the same ChangeSet Digest.

## Changed artifacts

- `attest-store==0.1.1` discovers, validates, and imports the bounded remote digest namespace before
  allocating a new immutable reference. It fails closed on unstable, malformed, oversized, or
  conflicting remote state and never overwrites a local reference.
- `attest-cli==0.1.3` uses remote discovery before publication and preserves the exact newly created
  bundle in the configured fallback directory when remote import or publication fails.
- GitHub Action `v1.0.3` uses the reviewed `linux/amd64` and `linux/arm64` image at
  `sha256:d5a370bff96f3dbe8eca341701060b73b915d9bade981e24a835f62362d2e2e1`.
- Product/source tag and immutable GitHub Release `v0.1.3` retain package, image, provenance, scan,
  publication, and dogfood evidence.

The core, collect, sign, and policy libraries remain at `0.1.0`. CLI `0.1.3` pins those libraries
and store `0.1.1` exactly. The image is promoted from candidate run `35963124568` without rebuilding;
its closed build-context digest is
`sha256:947ecc3ee98a9cea0eda2eb0c8ddeb6da6606a2af65fa23308720670f4e835f5`.

## Upgrade

Install `attest-cli==0.1.3` and use immutable Action tag `v1.0.3` or the release commit SHA. The
moving `v1` tag remains at the first release until the replacement public proof completes against
this release.

Releases `v0.1.0`, `v0.1.1`, and `v0.1.2`, and Action tags `v1.0.0`, `v1.0.1`, and `v1.0.2`, remain
immutable.
