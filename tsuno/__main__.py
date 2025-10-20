"""
Entry point for running tsuno as a module.

This allows users to run:
    python -m tsuno app:application [OPTIONS]
"""

from tsuno.cli.main import main

if __name__ == "__main__":
    main()
