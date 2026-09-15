"""CLI process entry point."""

from attest_cli.app import app


def main() -> None:
    """Run the attest command-line application."""
    app()


if __name__ == "__main__":
    main()
