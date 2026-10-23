"""REQ-F11-270/REQ-F11-310 upstream component vulnerability-gate contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPOSITORY_ROOT / "scripts/check_action_component_scan.py"
VEX = REPOSITORY_ROOT / "action/runtime-components.openvex.json"


def _sbom(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "spdxVersion": "SPDX-2.3",
                "packages": [
                    {
                        "name": "curl",
                        "versionInfo": "8.23.0",
                        "externalRefs": [
                            {
                                "referenceType": "purl",
                                "referenceLocator": "pkg:generic/curl@8.23.0",
                            },
                            {
                                "referenceType": "cpe23Type",
                                "referenceLocator": ("cpe:2.3:a:haxx:curl:8.23.0:*:*:*:*:*:*:*"),
                            },
                        ],
                    },
                    {
                        "name": "git",
                        "versionInfo": "2.52.0",
                        "externalRefs": [
                            {
                                "referenceType": "purl",
                                "referenceLocator": "pkg:generic/git@2.52.0",
                            },
                            {
                                "referenceType": "cpe23Type",
                                "referenceLocator": ("cpe:2.3:a:git-scm:git:2.52.0:*:*:*:*:*:*:*"),
                            },
                        ],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )


def _match(
    vulnerability: str,
    severity: str,
    package: str,
    purl: str,
    *,
    fix_state: str,
    fix_versions: list[str],
) -> dict[str, Any]:
    return {
        "vulnerability": {
            "id": vulnerability,
            "severity": severity,
            "fix": {"state": fix_state, "versions": fix_versions},
        },
        "artifact": {"name": package, "purl": purl},
    }


def _report(path: Path, matches: list[dict[str, Any]]) -> None:
    path.write_text(
        json.dumps(
            {
                "matches": matches,
                "source": {
                    "type": "sbom-file",
                    "target": "/source/runtime-components.spdx.json",
                },
                "descriptor": {
                    "name": "grype",
                    "version": "0.107.0",
                    "configuration": {"match": {"stock": {"using-cpes": True}}},
                    "db": {
                        "status": {
                            "valid": True,
                            "built": "2026-10-13T06:35:20Z",
                            "from": "https://grype.anchore.io/databases/example",
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _run(report: Path, sbom: Path, vex: Path = VEX) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CHECKER),
            str(report),
            "--sbom",
            str(sbom),
            "--vex",
            str(vex),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.ac("AC-F11-270")
@pytest.mark.ac("AC-F11-310")
def test_component_gate_applies_exact_vex_and_allows_unfixed_high(tmp_path: Path) -> None:
    sbom = tmp_path / "components.spdx.json"
    report = tmp_path / "grype.json"
    _sbom(sbom)
    _report(
        report,
        [
            _match(
                "CVE-2026-62960",
                "High",
                "git",
                "pkg:generic/git@2.52.0",
                fix_state="fixed",
                fix_versions=["2.55.0.windows.4"],
            ),
            _match(
                "CVE-UNFIXED-HIGH",
                "High",
                "curl",
                "pkg:generic/curl@8.23.0",
                fix_state="not-fixed",
                fix_versions=[],
            ),
        ],
    )

    completed = _run(report, sbom)

    assert completed.returncode == 0, completed.stderr
    assert "ignored by VEX=1" in completed.stdout
    assert "unfixed high=1" in completed.stdout


@pytest.mark.ac("AC-F11-310")
def test_component_gate_rejects_affected_curl_identity(tmp_path: Path) -> None:
    sbom = tmp_path / "components.spdx.json"
    report = tmp_path / "grype.json"
    _sbom(sbom)
    document = json.loads(sbom.read_text(encoding="utf-8"))
    curl = document["packages"][0]
    curl["versionInfo"] = "8.22.0"
    curl["externalRefs"][0]["referenceLocator"] = "pkg:generic/curl@8.22.0"
    curl["externalRefs"][1]["referenceLocator"] = "cpe:2.3:a:haxx:curl:8.22.0:*:*:*:*:*:*:*"
    sbom.write_text(json.dumps(document), encoding="utf-8")
    _report(report, [])

    completed = _run(report, sbom)

    assert completed.returncode == 2
    assert "invalid component SBOM" in completed.stderr


@pytest.mark.ac("AC-F11-270")
@pytest.mark.ac("AC-F11-310")
@pytest.mark.parametrize(
    ("severity", "fix_state", "fix_versions", "message"),
    [
        ("Critical", "not-fixed", [], "critical=1"),
        ("High", "fixed", ["8.23.1"], "fixable high=1"),
    ],
)
def test_component_gate_rejects_actionable_findings(
    tmp_path: Path,
    severity: str,
    fix_state: str,
    fix_versions: list[str],
    message: str,
) -> None:
    sbom = tmp_path / "components.spdx.json"
    report = tmp_path / "grype.json"
    _sbom(sbom)
    _report(
        report,
        [
            _match(
                "CVE-ACTIONABLE",
                severity,
                "curl",
                "pkg:generic/curl@8.23.0",
                fix_state=fix_state,
                fix_versions=fix_versions,
            )
        ],
    )

    completed = _run(report, sbom)

    assert completed.returncode == 1
    assert message in completed.stderr


@pytest.mark.ac("AC-F11-270")
def test_component_gate_rejects_vex_or_scanner_contract_drift(tmp_path: Path) -> None:
    sbom = tmp_path / "components.spdx.json"
    report = tmp_path / "grype.json"
    vex = tmp_path / "vex.json"
    _sbom(sbom)
    _report(report, [])
    vex.write_text(VEX.read_text(encoding="utf-8").replace("not_affected", "under_investigation"))

    invalid_vex = _run(report, sbom, vex)
    document = json.loads(report.read_text(encoding="utf-8"))
    document["descriptor"]["configuration"]["match"]["stock"]["using-cpes"] = False
    report.write_text(json.dumps(document), encoding="utf-8")
    invalid_scanner = _run(report, sbom)

    assert invalid_vex.returncode == 2
    assert "invalid component VEX" in invalid_vex.stderr
    assert invalid_scanner.returncode == 2
    assert "invalid Grype component report" in invalid_scanner.stderr
