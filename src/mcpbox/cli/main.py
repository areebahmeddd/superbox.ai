"""MCP Box CLI - Main Entry Point"""

import click

from mcpbox.cli.commands.init import init
from mcpbox.cli.commands.push import push
from mcpbox.cli.commands.pull import pull
from mcpbox.cli.commands.run import run
from mcpbox.cli.commands.search import search
from mcpbox.cli.commands.inspect import inspect


@click.group()
@click.version_option(version="1.0.0", prog_name="mcpbox")
def cli():
    """MCP Box CLI"""
    pass


# Register commands
cli.add_command(init)
cli.add_command(push)
cli.add_command(pull)
cli.add_command(run)
cli.add_command(search)
cli.add_command(inspect)


def main():
    """Entry point for CLI"""
    cli()


if __name__ == "__main__":
    main()
