# attest-store

Filesystem, Git-ref, and OCI storage adapters for exact Sigstore Bundles produced by
[attest](https://github.com/Parth2412/attest).

Version `0.1.2` corrects process-concurrent filesystem lock acquisition while preserving the
storage API and on-disk format. This distribution is part of the version-locked attest package
family. See the
[project documentation](https://github.com/Parth2412/attest/tree/main/docs) for its public
contracts and security model.
