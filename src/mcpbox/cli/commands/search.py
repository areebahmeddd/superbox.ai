"""Search for MCP server in registry"""

from pathlib import Path
import sys

import click

from mcpbox.shared import s3
from mcpbox.shared.config import Config, load_env


@click.command()
def search() -> None:
    """Search for available MCP servers"""
    try:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            click.echo("Error: .env file not found in current directory")
            sys.exit(1)

        load_env(env_path)
        cfg = Config()

        bucket = cfg.S3_BUCKET_NAME

        if not bucket:
            click.echo("Error: S3_BUCKET_NAME not found in .env file or --bucket option")
            sys.exit(1)

        mcp_data = s3.get_registry(bucket)
        servers = mcp_data.get("mcpServers", {})

        if not servers:
            click.echo("No MCP servers found in registry")
            return

        click.echo("\n" + "=" * 70)
        click.echo(f"Available MCP Servers ({len(servers)} found)")
        click.echo("=" * 70)

        for name, data in servers.items():
            repo_url = data.get("repository", {}).get("url", "N/A")
            tools_count = data.get("tool_count", 0)
            description = data.get("description", "No description")

            click.echo(f"\n[{name}]")
            click.echo(f"   Repository: {repo_url}")
            click.echo(f"   Tools: {tools_count}")
            click.echo(f"   Description: {description}")

            if "security_report" in data and data["security_report"]:
                security = data["security_report"]["summary"]
                total_issues = security.get("total_issues_all_scanners", 0)
                if total_issues == 0:
                    click.echo("   Security: All scans passed")
                else:
                    click.echo(f"   Security: {total_issues} issues found")

        click.echo("\n" + "=" * 70 + "\n")

    except Exception as e:
        click.echo(f"\nError: {str(e)}")
        sys.exit(1)
