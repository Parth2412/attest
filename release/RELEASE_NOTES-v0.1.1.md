# attest CLI 0.1.1 / GitHub Action v1.0.1

This corrective release fixes the GitHub Action token evaluation boundary discovered by the first
fresh-repository proof.

## Changed artifacts

- `attest-cli==0.1.1` generates the automatic `GITHUB_TOKEN` handoff in the caller step environment.
- Immutable Action tag `v1.0.1` points to this reviewed source commit.
- Product/source tag and immutable GitHub Release `v0.1.1` record the correction and evidence.

The five Python libraries remain at `0.1.0`, and CLI `0.1.1` pins each one exactly. The Action still
uses the reviewed public `0.1.0` multi-platform image at
`sha256:0e5073cb4f2a9cc484f15aded43b7f0b8ac432a0a8b31fc401b7e361cd0509f3`; no image is rebuilt or
republished.

## Upgrade

Replace Action `v1.0.0` with `v1.0.1` or the corrected full commit SHA. The moving `v1` tag remains
on the first release until the corrected public same-repository and fork proofs complete.

Action `v1.0.0` remains immutable and is known to fail during job setup because its metadata
references the `github` context outside a supported evaluation boundary.
