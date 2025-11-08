"""Pull MCP server from registry"""

import json
from pathlib import Path
import sys

import click

from mcpbox.cli.utils import config_path
from mcpbox.shared import s3
from mcpbox.shared.config import Config, load_env


@click.command()
@click.option("--name", required=True, help="MCP server name to pull")
@click.option(
    "--client",
    required=True,
    type=click.Choice(["vscode", "cursor", "windsurf", "claude", "chatgpt"], case_sensitive=False),
    help="Target client to write config for",
)
def pull(name: str, client: str) -> None:
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
            sys.exit(1)

        bucket = cfg.S3_BUCKET_NAME

        click.echo(f"\nFetching server '{name}' from S3 bucket '{bucket}'...")

        servers = s3.list_servers(bucket)

        if name not in servers:
            click.echo(f"Error: Server '{name}' not found in registry")
            click.echo("\nAvailable servers:")
            for server_name in servers.keys():
                click.echo(f"   - {server_name}")
            sys.exit(1)

        server_data = servers[name]

        target = client.lower()

        path = config_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            with open(path, "r") as f:
                vscode_config = json.load(f)
        else:
            vscode_config = {"mcpServers": {}}

        server_url = f"{lambda_base_url}?mcp_name={name}&s3_bucket={bucket}"

        display_target = {
            "vscode": "VS Code",
            "cursor": "Cursor",
            "windsurf": "Windsurf",
            "claude": "Claude",
            "chatgpt": "ChatGPT",
        }.get(target, target)

        if name in vscode_config.get("mcpServers", {}):
            click.echo(f"Warning: Server '{name}' already exists in {display_target} configuration")
            if not click.confirm("Do you want to overwrite it?"):
                click.echo("Aborted")
                sys.exit(0)

        entry = {
            "command": "curl",
            "args": ["-X", "GET", server_url],
            "metadata": {
                "repository": server_data.get("repository", {}),
                "description": server_data.get("description", ""),
                "tools": server_data.get("tools", []),
            },
        }
        vscode_config.setdefault("mcpServers", {})
        vscode_config["mcpServers"][name] = entry

        if target == "vscode":
            vscode_config.setdefault("servers", {})
            vscode_config["servers"][name] = {
                "type": "http",
                "url": server_url,
                "gallery": False,
            }

        with open(path, "w") as f:
            json.dump(vscode_config, f, indent=2)

        click.echo("\n" + "=" * 70)
        click.echo("Success!")
        click.echo("=" * 70)
        click.echo(f"\nServer '{name}' added to {display_target} MCP config")
        click.echo(f"URL: {server_url}")
        click.echo(f"\nLocation: {path}")

    except Exception as e:
        click.echo(f"\nError: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
