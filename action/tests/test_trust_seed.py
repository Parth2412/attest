"""Cryptographic validation contracts for the embedded TUF cache seed."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

ACTION_ROOT: Final[Path] = Path(__file__).parents[1]
VERIFIER: Final[Path] = ACTION_ROOT / "verify_trust_seed.py"
TRUST_ROOT: Final[Path] = ACTION_ROOT / "trust"


def _verify(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFIER), str(root)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.ac("AC-F11-230")
def test_checked_in_trust_seed_verifies_from_pinned_embedded_roots() -> None:
    """REQ-F11-230: checked-in metadata and targets form valid TUF chains."""
    result = _verify(TRUST_ROOT)

    assert result.returncode == 0, result.stderr
    assert result.stdout == "verified TUF cache seed for production, staging\n"


@pytest.mark.ac("AC-F11-230")
@pytest.mark.parametrize("mutation", ["target", "extra", "timestamp-runtime"])
def test_trust_seed_verification_fails_closed_on_contract_drift(
    tmp_path: Path, mutation: str
) -> None:
    """REQ-F11-230: bytes, file set, and timestamp exclusion are closed."""
    trust = tmp_path / "trust"
    shutil.copytree(TRUST_ROOT, trust)
    if mutation == "target":
        (trust / "production/trusted_root.json.b64").write_bytes(b"{}\n")
    elif mutation == "extra":
        (trust / "production/unreviewed.json").write_bytes(b"{}\n")
    else:
        manifest_path = trust / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        production = manifest["environments"]["production"]
        production["runtimeFiles"]["production/timestamp.json.b64"] = (
            ".local/share/sigstore-python/tuf/"
            "https%3A%2F%2Ftuf-repo-cdn.sigstore.dev/timestamp.json"
        )
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _verify(trust)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "invalid TUF cache seed\n"
