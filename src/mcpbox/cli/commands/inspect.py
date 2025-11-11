import sys
import webbrowser
from pathlib import Path

import click

from mcpbox.shared import s3
from mcpbox.shared.config import Config, load_env


@click.command()
@click.option("--name", required=True, help="MCP server name to inspect")
def inspect(name: str) -> None:
    """Open the repository URL for a server stored in S3."""
    try:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            click.echo("Error: .env file not found in current directory")
            sys.exit(1)

        load_env(env_path)
        cfg = Config()

        bucket = cfg.S3_BUCKET_NAME

        click.echo(f"Fetching server '{name}' from S3 bucket '{bucket}'...")

        server = s3.get_server(bucket, name)
        if not server:
            click.echo(f"Error: Server '{name}' not found in registry")
            sys.exit(1)

        repo_url = None
        if isinstance(server.get("repository"), dict):
            repo_url = server.get("repository", {}).get("url")
        if not repo_url and server.get("repo_url"):
            repo_url = server.get("repo_url")

        if not repo_url:
            click.echo("Error: Repository URL not found in server data")
            sys.exit(1)

        click.echo(f"Opening repository: {repo_url}")
        opened = webbrowser.open(repo_url)
        if not opened:
            click.echo("Warning: Could not open browser. Here is the URL:")
            click.echo(repo_url)
        else:
            click.echo("Done.")

    except Exception as e:
        click.echo(f"\nError: {str(e)}")
        sys.exit(1)
