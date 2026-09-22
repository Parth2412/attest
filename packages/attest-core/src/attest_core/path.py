"""Canonical raw Git path encoding governed by SPEC-001 §4.1."""

from __future__ import annotations

from typing import Final

_SAFE_BYTES: Final[frozenset[int]] = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~/"
)
_UPPER_HEX: Final[frozenset[str]] = frozenset("0123456789ABCDEF")
_NON_ASCII_PATH = "Git path must use canonical ASCII percent encoding"
_UNESCAPED_PATH_BYTE = "Git path contains a non-canonical unescaped byte"
_INCOMPLETE_ESCAPE = "Git path contains an incomplete percent escape"
_LOWERCASE_ESCAPE = "Git path percent escapes must use two uppercase hexadecimal digits"
_UNNECESSARY_ESCAPE = "Git path percent-encodes a byte that must remain unescaped"


def encode_git_path(raw_path: bytes) -> str:
    """Encode a raw Git path into its unique ASCII representation (REQ-F01-180)."""
    return "".join(chr(byte) if byte in _SAFE_BYTES else f"%{byte:02X}" for byte in raw_path)


def decode_git_path(encoded_path: str) -> bytes:
    """Decode and validate a canonical Git path representation (REQ-F01-180)."""
    try:
        encoded_path.encode("ascii")
    except UnicodeEncodeError as error:
        raise ValueError(_NON_ASCII_PATH) from error

    decoded = bytearray()
    index = 0
    while index < len(encoded_path):
        character = encoded_path[index]
        if character != "%":
            byte = ord(character)
            if byte not in _SAFE_BYTES:
                raise ValueError(_UNESCAPED_PATH_BYTE)
            decoded.append(byte)
            index += 1
            continue

        if index + 2 >= len(encoded_path):
            raise ValueError(_INCOMPLETE_ESCAPE)
        digits = encoded_path[index + 1 : index + 3]
        if any(digit not in _UPPER_HEX for digit in digits):
            raise ValueError(_LOWERCASE_ESCAPE)
        byte = int(digits, 16)
        if byte in _SAFE_BYTES:
            raise ValueError(_UNNECESSARY_ESCAPE)
        decoded.append(byte)
        index += 3

    return bytes(decoded)
