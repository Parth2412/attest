"""Acceptance tests for the CSD-1 digest algorithm."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from attest_core.digest import build_changeset_record, compute_changeset_digest
from attest_core.models import ChangeSetEntry

_MISSING_VECTOR_ROOT = "spec/testvectors directory is unavailable"


def _vector_root() -> Path:
    for root in (Path.cwd(), *Path.cwd().parents):
        candidate = root / "spec" / "testvectors"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(_MISSING_VECTOR_ROOT)


VECTOR_ROOT = _vector_root()


def _csd_vectors() -> list[Path]:
    return sorted(path for path in VECTOR_ROOT.glob("csd1-*") if (path / "input.json").is_file())


@pytest.mark.ac("AC-F01-050")
@pytest.mark.vectors
@pytest.mark.parametrize("vector_path", _csd_vectors(), ids=lambda path: path.name)
def test_csd1_vectors_produce_exact_expected_digests(vector_path: Path) -> None:
    """REQ-F01-050: every normative CSD-1 fixture has one exact digest."""
    payload: dict[str, Any] = json.loads((vector_path / "input.json").read_text(encoding="utf-8"))
    entries = [ChangeSetEntry.model_validate(item) for item in payload["entries"]]
    record = build_changeset_record(entries)

    assert set(record.model_dump()) == {"algorithm", "entries"}
    assert (
        compute_changeset_digest(record)
        == (vector_path / "expected.sha256").read_text(encoding="ascii").strip()
    )


@pytest.mark.ac("AC-F01-050")
@pytest.mark.vectors
@pytest.mark.parametrize("name", ["csd1-rebase-stability", "csd1-squash-stability"])
def test_commit_context_never_changes_the_digest(name: str) -> None:
    """REQ-F01-050: commit identities are vector metadata, never record fields."""
    vector_path = VECTOR_ROOT / name
    payload: dict[str, Any] = json.loads((vector_path / "input.json").read_text(encoding="utf-8"))
    assert payload["contexts"][0] != payload["contexts"][1]
    entries = [ChangeSetEntry.model_validate(item) for item in payload["entries"]]
    expected = (vector_path / "expected.sha256").read_text(encoding="ascii").strip()
    assert compute_changeset_digest(build_changeset_record(entries)) == expected


@pytest.mark.ac("AC-F01-060")
@pytest.mark.vectors
@pytest.mark.parametrize("locale_name", ["C", "tr_TR.UTF-8"])
def test_path_ordering_is_independent_of_process_locale(
    locale_name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """REQ-F01-060: locale variables cannot affect raw-byte sorting."""
    monkeypatch.setenv("LC_ALL", locale_name)
    vector_path = VECTOR_ROOT / "csd1-path-ordering"
    payload: dict[str, Any] = json.loads((vector_path / "input.json").read_text(encoding="utf-8"))
    entries = [ChangeSetEntry.model_validate(item) for item in payload["entries"]]
    record = build_changeset_record(entries)

    assert [entry.path for entry in record.entries] == ["A.txt", "z.txt", "%C3%A9.txt", "%FF.txt"]
    assert (
        compute_changeset_digest(record)
        == (vector_path / "expected.sha256").read_text(encoding="ascii").strip()
    )


@pytest.mark.ac("AC-F01-050")
@pytest.mark.parametrize(
    "entry",
    [
        {
            "path": "added.txt",
            "changeType": "added",
            "oldMode": "100644",
            "newMode": "100644",
            "oldBlob": None,
            "newBlob": "1" * 40,
        },
        {
            "path": "deleted.txt",
            "changeType": "deleted",
            "oldMode": "100644",
            "newMode": None,
            "oldBlob": "1" * 40,
            "newBlob": "2" * 40,
        },
        {
            "path": "modified.txt",
            "changeType": "modified",
            "oldMode": "100644",
            "newMode": "100644",
            "oldBlob": None,
            "newBlob": "2" * 40,
        },
        {
            "path": "typechange.txt",
            "changeType": "typechange",
            "oldMode": "100644",
            "newMode": None,
            "oldBlob": "1" * 40,
            "newBlob": "2" * 40,
        },
    ],
)
def test_changeset_entry_transition_nullability_is_enforced(entry: dict[str, Any]) -> None:
    """REQ-F01-050: transition types enforce the exact old/new nullability matrix."""
    with pytest.raises(ValidationError):
        ChangeSetEntry.model_validate(entry)


@pytest.mark.ac("AC-F01-050")
def test_digest_revalidates_an_existing_record() -> None:
    """REQ-F01-050: unvalidated model copies cannot alter or bypass the CSD-1 record shape."""
    entry = ChangeSetEntry.model_validate(
        {
            "path": "src/a.py",
            "changeType": "added",
            "oldMode": None,
            "newMode": "100644",
            "oldBlob": None,
            "newBlob": "1" * 40,
        }
    )
    record = build_changeset_record([entry])
    invalid_record = record.model_copy(update={"algorithm": "CSD-2"})
    with pytest.raises(ValidationError):
        compute_changeset_digest(invalid_record)
