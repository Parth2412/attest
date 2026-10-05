# attest CLI 0.1.2 / GitHub Action v1.0.2

This corrective release makes the generated pull-request workflow verify the exact GitHub OIDC
identity that signs a `pull_request` run and preserves safe verification failures at the Action
boundary.

## Changed artifacts

- `attest-cli==0.1.2` generates a repository- and workflow-bound
  `refs/pull/*/merge` identity pattern for pull-request verification.
- GitHub Action `v1.0.2` preserves known `ERR-VERIFY-*` diagnostics from denied runs without
  publishing unverified outputs or summaries.
- The Action runtime is the reviewed `linux/amd64` and `linux/arm64` image at
  `sha256:50ff206da7d26341776c954bb190005f1e6d10369b29fbbbe68619ce8d7ad627`.
- Product/source tag and immutable GitHub Release `v0.1.2` retain the package, image, provenance,
  scan, publication, and dogfood evidence.

The five Python libraries remain at `0.1.0`, and CLI `0.1.2` pins each one exactly. The image is
promoted from candidate run `35886884855` without rebuilding; its closed build-context digest is
`sha256:1000bc7cc5402e442536ba6d94630da39433b41bdfcea01ebb9b1dc1b0882944`.

## Upgrade

Replace Action `v1.0.1` with immutable `v1.0.2` or the release commit SHA. Existing projects should
rerun `attest init` only in a clean integration fixture or update both configured signer identities
to the generated `refs/pull/*/merge` pattern. The moving `v1` tag remains unchanged until the
same-repository and fork pull-request proofs complete against this release.

Action `v1.0.1` and CLI `0.1.1` remain immutable. Their generated configuration expects a main-branch
workflow identity and therefore cannot verify a bundle signed by the generated pull-request
workflow.
