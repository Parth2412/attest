# attest 0.1.0

The first public alpha release of attest provides deterministic ChangeSet Digests, evidence
collection, AI-authorship Statements, keyless Sigstore signing, independent verification, storage
adapters, policy enforcement, a closed CLI, and a digest-pinned multi-platform GitHub Action.

This release publishes exactly six Python distributions: `attest-core`, `attest-collect`,
`attest-sign`, `attest-store`, `attest-policy`, and `attest-cli`. The unfinished `attest-export`
package is not published. The Action is available through immutable `v1.0.0`, reviewed moving
major `v1`, and full commit SHA references; its runtime image remains pinned by manifest digest.

Release assets include exact source and distribution hashes, GitHub artifact attestations, and the
publicly verified attest Bundle produced by the release workflow itself.
