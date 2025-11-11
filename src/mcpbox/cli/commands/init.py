import sys
import json
import click
from pathlib import Path

from mcpbox.cli.scanners import sonarqube


@click.command()
def init() -> None:
    """Initialize mcpbox.json configuration file"""
    config_file = Path.cwd() / "mcpbox.json"

    if config_file.exists():
        click.echo("mcpbox.json already exists")
        if not click.confirm("Do you want to overwrite it?"):
            click.echo("Aborted")
            sys.exit(0)

    click.echo("\nInitialize MCP Box Configuration")
    click.echo("=" * 50)

    repo_url = click.prompt("\nRepository URL (GitHub)", default="")
    if repo_url:
        owner, repo = sonarqube.extract_repository(repo_url)
        default_name = repo if repo else ""
    else:
        default_name = Path.cwd().name

    name = click.prompt("Server name", default=default_name)
    version = click.prompt("Version", default="1.0.0")
    description = click.prompt("Description", default=f"MCP server for {name}")
    author = click.prompt("Author", default="")
    lang = click.prompt("Language", default="Python")
    license_type = click.prompt("License", default="MIT")
    entrypoint = click.prompt("Entrypoint file", default="main.py")

    if not repo_url:
        repo_url = click.prompt("Repository URL", default="")

    add_pricing = click.confirm("\nAdd pricing information?", default=False)

    config = {
        "name": name,
        "version": version,
        "description": description,
        "author": author,
        "lang": lang,
        "license": license_type,
        "entrypoint": entrypoint,
        "repository": {"type": "git", "url": repo_url},
    }

    if add_pricing:
        currency = click.prompt("Currency", default="USD")
        amount = click.prompt("Amount", type=float, default=0.0)
        config["pricing"] = {"currency": currency, "amount": amount}

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    click.echo("\n" + "=" * 50)
    click.echo("Configuration saved!")
    click.echo("=" * 50)
    click.echo(f"\nCreated: {config_file}")
    click.echo("\nNext steps:")
    click.echo(f"   1. mcpbox push --name {name}")
    click.echo(f"   2. mcpbox pull --name {name}")
