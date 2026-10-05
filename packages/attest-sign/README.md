# attest-sign

Keyless Sigstore signing, identity-bound verification, and Bundle inspection adapters for
[attest](https://github.com/Parth2412/attest).

Version `0.1.1` adds mandatory refreshed-trust verification and bounded recovery when packaged
Sigstore trust is stale before Rekor submission. It retains exact `attest-core==0.1.0`. See the
[project documentation](https://github.com/Parth2412/attest/tree/main/docs) for its public
contracts and security model.
