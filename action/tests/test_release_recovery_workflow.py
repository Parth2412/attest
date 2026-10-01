"""F-11 release-recovery retirement contract."""

from __future__ import annotations

from pathlib import Path
from typing import Final

import pytest

REPOSITORY_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
RECOVERY_WORKFLOW: Final[Path] = REPOSITORY_ROOT / ".github/workflows/recover-release-v0.1.4.yml"


@pytest.mark.ac("AC-F11-200")
def test_completed_v014_recovery_workflow_is_retired() -> None:
    """REQ-F11-200: the bounded recovery path is absent after publication completes."""
    assert not RECOVERY_WORKFLOW.exists()
