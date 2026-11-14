"""
Executable package entrypoint for running:
    python -m scripts [command] [options]
"""
from scripts.cli import cli

if __name__ == "__main__":
    cli()
