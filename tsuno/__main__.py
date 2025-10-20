"""
Entry point for running z as a module.

This allows users to run:
    python -m z app:application [OPTIONS]
"""

from z.cli.main import main

if __name__ == "__main__":
    main()
