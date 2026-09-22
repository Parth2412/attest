"""Deterministic human and JSON report rendering."""

from __future__ import annotations

import json
from typing import TextIO

from rich.console import Console

from attest_cli.models import CliReport, report_wire


def emit_report(
    report: CliReport,
    *,
    json_output: bool,
    no_color: bool,
    stdout: TextIO,
    stderr: TextIO,
    is_tty: bool,
    no_color_environment: bool,
) -> None:
    """Emit exactly one report through the selected presentation channel."""
    wire = report_wire(report)
    if json_output:
        stdout.write(json.dumps(wire, ensure_ascii=False, separators=(",", ":")) + "\n")
        stdout.flush()
        return

    colour = is_tty and not no_color and not no_color_environment
    console = Console(
        file=stderr,
        force_terminal=colour,
        color_system="standard" if colour else None,
        no_color=not colour,
        highlight=False,
        markup=colour,
    )
    if report.outcome == "unverified-identity":
        heading = (
            "[bold yellow]UNVERIFIED IDENTITY[/bold yellow]" if colour else "UNVERIFIED IDENTITY"
        )
        console.print(heading)
    rendered = json.dumps(wire, ensure_ascii=False, indent=2)
    if colour:
        console.print_json(rendered)
    else:
        stderr.write(rendered + "\n")
        stderr.flush()
