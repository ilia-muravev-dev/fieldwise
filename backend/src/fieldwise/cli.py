"""Command-line interface: ingestion, extraction, evals and reports."""

import typer
from rich.console import Console

from fieldwise import __version__

app = typer.Typer(help="fieldwise — document extraction workbench.", no_args_is_help=True)
console = Console()


@app.callback()
def main() -> None:
    """fieldwise — document extraction workbench."""


@app.command()
def version() -> None:
    """Print the installed version."""
    console.print(f"fieldwise {__version__}")


if __name__ == "__main__":
    app()
