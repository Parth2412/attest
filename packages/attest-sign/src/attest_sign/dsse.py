"""Convert attest Statements at the Sigstore-native DSSE boundary."""

from __future__ import annotations

from typing import cast

from sigstore.dsse import Statement as SigstoreStatement

from attest_core.canonical import JsonValue, canonicalize
from attest_core.models.statement import Statement


def canonical_statement_bytes(statement: Statement) -> bytes:
    """Return the exact RFC 8785 Statement bytes used at every signing boundary."""
    wire = cast(JsonValue, statement.model_dump(mode="json", by_alias=True))
    return canonicalize(wire)


def to_sigstore_statement(statement: Statement) -> SigstoreStatement:
    """Pass exact RFC 8785 Statement bytes to Sigstore (REQ-F06-010/020)."""
    return SigstoreStatement(canonical_statement_bytes(statement))
