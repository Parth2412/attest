# attest 0.1.4 / GitHub Action v1.0.4

This image-only correction reduces GitHub Action cold-start transfer cost while preserving the
released Python package graph and public Action interface.

## Changed artifacts

- GitHub Action `v1.0.4` pins the reviewed multi-platform image manifest
  `sha256:d25c6d00db13c34423b38e2c948bde8f41d2856a25bcf251bca2213872a15fbd`.
- Image `0.1.4` uses digest-pinned `python:3.12.14-alpine3.23`, exact Alpine package
  `git=2.52.0-r0`, removes unused runtime content, strips native extension symbols, and publishes
  both runtime manifests with OCI zstd-compressed layers.
- The candidate covers `linux/amd64` and `linux/arm64`, has zero vulnerability and secret
  findings, and retains SBOM, maximum SLSA provenance, closed-context evidence, and an
  identity-bound GitHub artifact attestation.
- Product/source tag and immutable GitHub Release `v0.1.4` retain the exact candidate,
  performance, promotion, asset-attestation, and production-dogfood evidence.

No Python distribution is rebuilt or uploaded. The public package versions remain
`attest-core==0.1.0`, `attest-collect==0.1.0`, `attest-sign==0.1.0`,
`attest-store==0.1.1`, `attest-policy==0.1.0`, and `attest-cli==0.1.3`.

## Upgrade

Use immutable Action tag `v1.0.4` or its full release commit SHA. The moving `v1` tag remains on
`v1.0.3` until the v1.0.4 public onboarding proof and all retained release evidence verify.

Every earlier Python file, image, source tag, Action tag, and GitHub Release remains immutable.
