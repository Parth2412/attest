"""Convert attest Statements at the Sigstore-native DSSE boundary."""

from __future__ import annotations

from typing import cast

from sigstore.dsse import Statement as SigstoreStatement

from attest_core.canonical import JsonValue, canonicalize
from attest_core.models.statement import Statement


def to_sigstore_statement(statement: Statement) -> SigstoreStatement:
    """Pass exact RFC 8785 Statement bytes to Sigstore (REQ-F06-010/020)."""
    wire = cast(JsonValue, statement.model_dump(mode="json", by_alias=True))
    return SigstoreStatement(canonicalize(wire))
