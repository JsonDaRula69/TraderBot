"""Allow ``python -m traderbot`` as an alias for the CLI entry point."""

from traderbot.cli import app


def main() -> None:
    app()


if __name__ == "__main__":
    main()
