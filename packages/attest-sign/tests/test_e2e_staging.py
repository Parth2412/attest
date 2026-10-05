"""Live Sigstore staging acceptance test, enabled only by the dedicated workflow."""

from __future__ import annotations

import os
from pathlib import Path
from typing import cast

import pytest
from sigstore.models import Bundle as SigstoreBundle
from sigstore.models import ClientTrustConfig
from sigstore.verify import Verifier
from sigstore.verify.policy import Identity

from attest_core import JsonValue, Statement, canonicalize
from attest_core.constants import DSSE_PAYLOAD_TYPE
from attest_sign import SigningEnvironment, SigstoreSigner


@pytest.mark.slow
@pytest.mark.ac("AC-F06-010")
@pytest.mark.ac("AC-F06-030")
@pytest.mark.ac("AC-F06-050")
@pytest.mark.ac("AC-F06-080")
@pytest.mark.skipif(
    os.environ.get("ATTEST_SIGSTORE_E2E") != "1",
    reason="live staging signing runs only in the dedicated OIDC workflow",
)
def test_keyless_staging_bundle_verifies_offline_without_persisting_a_key(
    monkeypatch: pytest.MonkeyPatch,
    statement: Statement,
    tmp_path: Path,
) -> None:
    """REQ-F06-010/030/050/080: exercise the complete staging signing boundary."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))

    result = SigstoreSigner(environment=SigningEnvironment.STAGING).sign(statement)
    bundle = SigstoreBundle.from_json(result.raw)
    trust_config = ClientTrustConfig.staging(offline=True)
    payload_type, payload = Verifier(trusted_root=trust_config.trusted_root).verify_dsse(
        bundle,
        policy=Identity(
            identity=result.certificate_identity,
            issuer=result.certificate_issuer,
        ),
    )

    assert payload_type == DSSE_PAYLOAD_TYPE
    assert payload == canonicalize(cast(JsonValue, statement.model_dump()))
    assert result.environment is SigningEnvironment.STAGING
    assert result.log_index >= 0

    persisted = b"\n".join(path.read_bytes() for path in tmp_path.rglob("*") if path.is_file())
    assert b"PRIVATE KEY" not in persisted
