# CLI logic lives in insarscript.cli.main.
# This module re-exports the entry point for backward compatibility.
from insarscript.cli.main import create_parser, main  # noqa: F401

if __name__ == "__main__":
    main()
