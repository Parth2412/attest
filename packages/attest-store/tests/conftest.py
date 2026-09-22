"""Shared attest-store test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest


@pytest.fixture
def stored_at() -> datetime:
    """Return one stable, second-precision storage timestamp."""
    return datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)
