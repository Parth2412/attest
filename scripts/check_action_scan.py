#!/usr/bin/env python3
"""Fail closed on actionable findings in one retained Trivy JSON report."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_MAX_REPORT_SIZE = 64 * 1024 * 1024
_INVALID_REPORT = "invalid Trivy report"


def _invalid() -> None:
    raise ValueError(_INVALID_REPORT)


def _findings(result: dict[str, object], name: str) -> list[object]:
    value = result.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        _invalid()
    return value


def _load(path: Path) -> list[object]:
    if not path.is_file() or path.stat().st_size > _MAX_REPORT_SIZE:
        _invalid()
    decoded = json.loads(path.read_bytes().decode("utf-8", errors="strict"))
    if not isinstance(decoded, dict) or decoded.get("SchemaVersion") != 2:
        _invalid()
    results = decoded.get("Results")
    if not isinstance(results, list):
        _invalid()
    return results


def _evaluate(results: list[object]) -> tuple[int, int, int, int]:
    critical = 0
    fixable_high = 0
    unfixed_high = 0
    secrets = 0
    for raw_result in results:
        if not isinstance(raw_result, dict):
            _invalid()
        result: dict[str, object] = raw_result
        for raw_vulnerability in _findings(result, "Vulnerabilities"):
            if not isinstance(raw_vulnerability, dict):
                _invalid()
            severity = raw_vulnerability.get("Severity")
            fixed_version = raw_vulnerability.get("FixedVersion", "")
            if not isinstance(severity, str) or not isinstance(fixed_version, str):
                _invalid()
            if severity == "CRITICAL":
                critical += 1
            elif severity == "HIGH":
                if fixed_version.strip():
                    fixable_high += 1
                else:
                    unfixed_high += 1
        for raw_secret in _findings(result, "Secrets"):
            if not isinstance(raw_secret, dict):
                _invalid()
            secrets += 1
    return critical, fixable_high, unfixed_high, secrets


def main() -> int:
    if len(sys.argv) != 2:
        print(_INVALID_REPORT, file=sys.stderr)
        return 2
    try:
        critical, fixable_high, unfixed_high, secrets = _evaluate(_load(Path(sys.argv[1])))
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
        print(_INVALID_REPORT, file=sys.stderr)
        return 2

    summary = (
        f"critical={critical}, fixable high={fixable_high}, "
        f"unfixed high={unfixed_high}, secrets={secrets}"
    )
    if critical or fixable_high or secrets:
        print(f"candidate security gate failed: {summary}", file=sys.stderr)
        return 1
    print(f"candidate security gate passed: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
