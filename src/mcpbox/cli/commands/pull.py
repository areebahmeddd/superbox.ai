"""Pull MCP server from registry"""

import json
from pathlib import Path
import sys

import click

from mcpbox.cli.utils import vscode_path
from mcpbox.shared import s3
from mcpbox.shared.config import Config, load_env


@click.command()
@click.option("--name", "-n", required=True, help="MCP server name to pull")
def pull(name: str) -> None:
    """Pull and configure MCP server from registry"""
    try:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            click.echo("Error: .env file not found in current directory")
            sys.exit(1)

        load_env(env_path)
        cfg = Config()
        lambda_base_url = cfg.LAMBDA_BASE_URL
        if not lambda_base_url:
            click.echo("Error: LAMBDA_BASE_URL not found in .env file")
            click.echo("Add to .env: LAMBDA_BASE_URL=https://your-lambda-url.amazonaws.com")
            sys.exit(1)

        bucket = cfg.S3_BUCKET_NAME

        click.echo(f"\nFetching server '{name}' from S3 bucket '{bucket}'...")

        if not bucket:
            click.echo("Error: S3_BUCKET_NAME not found in .env file or --bucket option")
            sys.exit(1)

        mcp_data = s3.get_registry(bucket)
        servers = mcp_data.get("mcpServers", {})

        if name not in servers:
            click.echo(f"Error: Server '{name}' not found in registry")
            click.echo("\nAvailable servers:")
            for server_name in servers.keys():
                click.echo(f"   - {server_name}")
            sys.exit(1)

        server_data = servers[name]

        vscode_mcp_path = vscode_path()
        vscode_mcp_path.parent.mkdir(parents=True, exist_ok=True)

        if vscode_mcp_path.exists():
            with open(vscode_mcp_path, "r") as f:
                vscode_config = json.load(f)
        else:
            vscode_config = {"mcpServers": {}}

        server_url = f"{lambda_base_url}?mcp_name={name}&s3_bucket={bucket}"

        if name in vscode_config.get("mcpServers", {}):
            click.echo(f"Warning: Server '{name}' already exists in VS Code configuration")
            if not click.confirm("Do you want to overwrite it?"):
                click.echo("Aborted")
                sys.exit(0)

        vscode_config["mcpServers"][name] = {
            "command": "curl",
            "args": ["-X", "GET", server_url],
            "metadata": {
                "repository": server_data.get("repository", {}),
                "description": server_data.get("description", ""),
                "tools": server_data.get("tools", []),
            },
        }

        with open(vscode_mcp_path, "w") as f:
            json.dump(vscode_config, f, indent=2)

        click.echo("\n" + "=" * 70)
        click.echo("Success!")
        click.echo("=" * 70)
        click.echo(f"\nServer '{name}' added to VS Code mcp.json")
        click.echo(f"URL: {server_url}")
        click.echo(f"\nLocation: {vscode_mcp_path}")
        click.echo("\nNote: Restart VS Code to load the new server")

    except Exception as e:
        click.echo(f"\nError: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
