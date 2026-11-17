"""
Executable package entrypoint for running:
    python -m deepsift [command] [options]
"""
from deepsift.cli import cli

if __name__ == "__main__":
    cli()
