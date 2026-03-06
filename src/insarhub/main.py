# CLI logic lives in insarhub.cli.main.
# This module re-exports the entry point for backward compatibility.
from insarhub.cli.main import create_parser, main  # noqa: F401

if __name__ == "__main__":
    main()
