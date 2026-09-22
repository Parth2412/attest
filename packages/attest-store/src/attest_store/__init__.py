"""Attestation storage and retrieval adapters."""

from attest_store.errors import StoreError, StoreErrorCode
from attest_store.fallback import put_with_fallback
from attest_store.filesystem import FilesystemStore
from attest_store.gitref import GitBackend, GitRefStore
from attest_store.oci import OciClientFactory, OciStore, OciSubject
from attest_store.protocols import AttestationStore, StoreBackend, StoreRef

__all__ = [
    "AttestationStore",
    "FilesystemStore",
    "GitBackend",
    "GitRefStore",
    "OciClientFactory",
    "OciStore",
    "OciSubject",
    "StoreBackend",
    "StoreError",
    "StoreErrorCode",
    "StoreRef",
    "put_with_fallback",
]
