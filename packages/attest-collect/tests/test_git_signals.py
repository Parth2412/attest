"""Failure-boundary tests for hardened, read-only F-03 Git signal plumbing."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from attest_collect._git_signals import (
    GitSignalError,
    GitSignalReader,
    GitSignalRevisionError,
    GitSignalUnavailableError,
    _git_environment,
)
from attest_collect._strict_json import decode_json


def _result(returncode: int = 0, stdout: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    return subprocess.CompletedProcess([], returncode, stdout, b"")


def _reader(single_add_repo: Any) -> GitSignalReader:
    return GitSignalReader(single_add_repo.path)


def _responses(
    *values: subprocess.CompletedProcess[bytes],
) -> Callable[..., subprocess.CompletedProcess[bytes]]:
    iterator = iter(values)

    def run(*_arguments: str, **_keywords: object) -> subprocess.CompletedProcess[bytes]:
        return next(iterator)

    return run


def test_git_environment_removes_repository_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_DIR", "/private/repository")
    monkeypatch.setenv("ATTEST_TEST_VALUE", "retained")

    environment = _git_environment()

    assert "GIT_DIR" not in environment
    assert environment["ATTEST_TEST_VALUE"] == "retained"
    assert environment["GIT_NO_REPLACE_OBJECTS"] == "1"
    assert environment["GIT_OPTIONAL_LOCKS"] == "0"
    assert environment["LC_ALL"] == "C"


def test_reader_reports_missing_or_unstartable_git(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("attest_collect._git_signals.shutil.which", lambda _name: None)
    with pytest.raises(GitSignalUnavailableError):
        GitSignalReader(tmp_path)

    monkeypatch.setattr("attest_collect._git_signals.shutil.which", lambda _name: "/usr/bin/git")

    def fail_to_start(*_arguments: object, **_keywords: object) -> object:
        raise OSError

    monkeypatch.setattr(GitSignalReader, "_run", fail_to_start)
    with pytest.raises(GitSignalUnavailableError):
        GitSignalReader(tmp_path)


@pytest.mark.parametrize("oid", ["not-a-full-oid", "é" * 40])
def test_commit_validation_rejects_noncanonical_oids(single_add_repo: Any, oid: str) -> None:
    with pytest.raises(GitSignalRevisionError):
        _reader(single_add_repo).validate_commit(oid)


def test_commit_validation_rejects_unreadable_object(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(single_add_repo)
    monkeypatch.setattr(reader, "_run", _responses(_result(1)))

    with pytest.raises(GitSignalRevisionError):
        reader.validate_commit("a" * 40)


def test_commit_range_rejects_failed_and_malformed_git_output(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(single_add_repo)
    monkeypatch.setattr(reader, "_run", _responses(_result(1), _result(stdout=b"invalid\n")))

    with pytest.raises(GitSignalError):
        reader.commit_oids("a" * 40, "b" * 40)
    with pytest.raises(GitSignalError):
        reader.commit_oids("a" * 40, "b" * 40)


def test_raw_commit_message_rejects_failed_and_headerless_output(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(single_add_repo)
    monkeypatch.setattr(reader, "_run", _responses(_result(1), _result(stdout=b"no-divider")))

    with pytest.raises(GitSignalError):
        reader.raw_commit_message("a" * 40)
    with pytest.raises(GitSignalError):
        reader.raw_commit_message("a" * 40)


def test_trailer_parser_rejects_failed_and_malformed_output(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(single_add_repo)
    monkeypatch.setattr(reader, "_run", _responses(_result(1), _result(stdout=b"missing token")))

    with pytest.raises(GitSignalError):
        reader.parsed_trailers(b"message")
    with pytest.raises(GitSignalError):
        reader.parsed_trailers(b"message")


def test_notes_ref_validation_covers_absent_and_failed_refs(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(single_add_repo)
    with pytest.raises(GitSignalError):
        reader.notes_ref_exists("refs/heads/main")

    monkeypatch.setattr(reader, "_run", _responses(_result(1)))
    with pytest.raises(GitSignalError):
        reader.notes_ref_exists("refs/notes/bad")

    monkeypatch.setattr(reader, "_run", _responses(_result(), _result(1)))
    assert reader.notes_ref_exists("refs/notes/absent") is False

    monkeypatch.setattr(reader, "_run", _responses(_result(), _result(2)))
    with pytest.raises(GitSignalError):
        reader.notes_ref_exists("refs/notes/failure")


def test_note_blob_rejects_failed_or_malformed_object_resolution(
    single_add_repo: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    reader = _reader(single_add_repo)
    monkeypatch.setattr(reader, "_run", _responses(_result(2)))
    with pytest.raises(GitSignalError):
        reader.note_blob("refs/notes/ai", "a" * 40)

    monkeypatch.setattr(reader, "_run", _responses(_result(1)))
    assert reader.note_blob("refs/notes/ai", "a" * 40) is None

    monkeypatch.setattr(reader, "_run", _responses(_result()))
    assert reader.note_blob("refs/notes/ai", "a" * 40) is None

    monkeypatch.setattr(reader, "_run", _responses(_result(stdout=b"bad-object\n")))
    with pytest.raises(GitSignalError):
        reader.note_blob("refs/notes/ai", "a" * 40)

    monkeypatch.setattr(reader, "_run", _responses(_result(stdout=b"a" * 40), _result(1)))
    with pytest.raises(GitSignalError):
        reader.note_blob("refs/notes/ai", "a" * 40)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"claimId":"a","claimId":"b"}', "duplicate property"),
        ('{"value":NaN}', "non-standard numeric value"),
    ],
)
def test_strict_json_rejects_ambiguous_or_nonstandard_values(text: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        decode_json(text)
