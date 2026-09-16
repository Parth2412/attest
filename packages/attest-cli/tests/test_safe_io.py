"""F-10 hostile file and atomic publication tests."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from attest_cli import safe_io
from attest_cli.errors import CliError
from attest_cli.safe_io import (
    MissingInputError,
    ensure_directory,
    read_json_object,
    read_regular_file,
    write_atomic,
)


@pytest.mark.ac("AC-F10-160")
def test_bounded_regular_read_rejects_symlink_directory_and_oversize(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"abcd")
    link = tmp_path / "link"
    link.symlink_to(source)

    assert read_regular_file(source, maximum_size=4, error_code="ERR-CONFIG-003") == b"abcd"
    for path in (link, tmp_path):
        with pytest.raises(CliError, match="ERR-CONFIG-003"):
            read_regular_file(path, maximum_size=4, error_code="ERR-CONFIG-003")
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        read_regular_file(source, maximum_size=3, error_code="ERR-CONFIG-003")


@pytest.mark.ac("AC-F10-160")
@pytest.mark.parametrize(
    "raw",
    [
        b'\xef\xbb\xbf{"key":1}',
        b'{"key":1,"key":2}',
        b'{"key":NaN}',
        b'{"key":Infinity}',
        b'{"key":1} trailing',
        b"[1,2,3]",
        b"\xff",
    ],
)
def test_strict_json_object_rejects_ambiguous_inputs(tmp_path: Path, raw: bytes) -> None:
    source = tmp_path / "input.json"
    source.write_bytes(raw)
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        read_json_object(source, maximum_size=1024)


@pytest.mark.ac("AC-F10-160")
def test_atomic_output_is_create_only_mode_0600_and_exact(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    write_atomic(target, b"first", overwrite=False)

    assert target.read_bytes() == b"first"
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert not list(tmp_path.glob(".artifact.json.attest-*"))
    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        write_atomic(target, b"second", overwrite=False)
    assert target.read_bytes() == b"first"


@pytest.mark.ac("AC-F10-160")
def test_atomic_overwrite_replaces_only_regular_file(tmp_path: Path) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"first")
    write_atomic(target, b"second", overwrite=True)
    assert target.read_bytes() == b"second"

    linked = tmp_path / "linked.json"
    linked.symlink_to(target)
    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        write_atomic(linked, b"third", overwrite=True)
    assert target.read_bytes() == b"second"


@pytest.mark.ac("AC-F10-160")
def test_input_identity_or_size_change_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source"
    source.write_bytes(b"before")
    original_fstat = os.fstat
    calls = 0

    def changed_fstat(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        result = original_fstat(descriptor)
        if calls >= 2:
            values = list(result)
            values[stat.ST_SIZE] = result.st_size + 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "fstat", changed_fstat)
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        read_regular_file(source, maximum_size=1024, error_code="ERR-CONFIG-003")


@pytest.mark.ac("AC-F10-160")
def test_missing_input_can_be_distinguished_without_exposing_a_path(tmp_path: Path) -> None:
    with pytest.raises(MissingInputError) as raised:
        read_regular_file(
            tmp_path / "missing",
            maximum_size=1,
            error_code="ERR-CONFIG-003",
            distinguish_missing=True,
        )

    assert str(raised.value) == ""


@pytest.mark.ac("AC-F10-160")
def test_directory_creation_is_private_and_rejects_symlink_components(tmp_path: Path) -> None:
    created = ensure_directory(tmp_path / "first" / "second")
    assert created == tmp_path / "first" / "second"
    assert created.is_dir()
    assert stat.S_IMODE(created.stat().st_mode) == 0o700

    link = tmp_path / "linked"
    link.symlink_to(tmp_path / "first", target_is_directory=True)
    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        ensure_directory(link / "forbidden")


@pytest.mark.ac("AC-F10-160")
def test_device_inputs_and_output_directories_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        read_regular_file("/dev/null", maximum_size=1024, error_code="ERR-CONFIG-003")
    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        write_atomic(tmp_path, b"content", overwrite=True)


@pytest.mark.ac("AC-F10-160")
def test_overwrite_target_race_is_rejected_and_temporary_is_cleaned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"
    target.write_bytes(b"original")
    actual_target_stat = safe_io._target_stat
    calls = 0

    def changed_target_stat(directory_fd: int, name: str) -> os.stat_result | None:
        nonlocal calls
        calls += 1
        result = actual_target_stat(directory_fd, name)
        if calls == 2 and result is not None:
            values = list(result)
            values[stat.ST_INO] = result.st_ino + 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(safe_io, "_target_stat", changed_target_stat)
    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        write_atomic(target, b"replacement", overwrite=True)

    assert target.read_bytes() == b"original"
    assert not list(tmp_path.glob(".artifact.json.attest-*"))


@pytest.mark.ac("AC-F10-160")
def test_failed_atomic_write_removes_private_temporary_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "artifact.json"

    def fail_write(_descriptor: int, _content: bytes) -> None:
        raise OSError

    monkeypatch.setattr(safe_io, "_write_all", fail_write)
    with pytest.raises(CliError, match="ERR-CONFIG-004"):
        write_atomic(target, b"content", overwrite=False)

    assert not target.exists()
    assert not list(tmp_path.glob(".artifact.json.attest-*"))


@pytest.mark.ac("AC-F10-160")
@pytest.mark.parametrize(
    ("maximum_size", "path"),
    [(True, "input"), (-1, "input"), (1, "bad\x00name")],
)
def test_invalid_read_contract_values_fail_closed(
    tmp_path: Path,
    maximum_size: int,
    path: str,
) -> None:
    (tmp_path / "input").write_bytes(b"x")
    with pytest.raises(CliError, match="ERR-CONFIG-003"):
        read_regular_file(
            tmp_path / path,
            maximum_size=maximum_size,
            error_code="ERR-CONFIG-003",
        )
