import sys
import json
from pathlib import Path
from urllib.parse import quote

import click

from mcpbox.cli.utils import config_path
from mcpbox.shared.config import Config, load_env


def get_repo(repo_url: str) -> str:
    """Extract repository name from URL"""
    repo_url = repo_url.strip().rstrip("/")

    if repo_url.startswith("git@github.com:"):
        repo_url = repo_url.replace("git@github.com:", "")
    elif "github.com/" in repo_url:
        repo_url = repo_url.split("github.com/")[-1]

    repo_url = repo_url.replace(".git", "")
    parts = repo_url.split("/")

    if len(parts) >= 2:
        return parts[-1]
    return parts[-1] if parts else "unknown"


@click.command()
@click.option("--url", required=True, help="Repository URL of the MCP server")
@click.option(
    "--client",
    required=True,
    type=click.Choice(["vscode", "cursor", "windsurf", "claude", "chatgpt"], case_sensitive=False),
    help="Target client to write config for",
)
@click.option("--entrypoint", default="main.py", help="Entrypoint file (default: main.py)")
@click.option("--lang", default="python", help="Language (default: python)")
def test(url: str, client: str, entrypoint: str, lang: str) -> None:
    """Test MCP server directly from repository URL without S3 registration or security checks"""
    try:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            click.echo("Error: .env file not found in current directory")
            sys.exit(1)

        load_env(env_path)
        cfg = Config()
        lambda_base_url = cfg.LAMBDA_BASE_URL

        repo_name = get_repo(url)

        click.echo("\n" + "=" * 70)
        click.echo("⚠️  TEST MODE - No Security Checks")
        click.echo("=" * 70)
        click.echo("\nThis server is being tested directly and has NOT gone through:")
        click.echo("  • Security scanning (SonarQube, Bandit, GitGuardian)")
        click.echo("  • Quality checks")
        click.echo("  • Registry validation")
        click.echo("\n⚠️  This server will NOT be available on the platform.")
        click.echo("=" * 70 + "\n")

        encoded_url = quote(url, safe="")
        test_url = f"{lambda_base_url.rstrip('/')}/{repo_name}?repo_url={encoded_url}&entrypoint={entrypoint}&lang={lang}&test_mode=true"

        target = client.lower()
        path = config_path(target)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            with open(path, "r") as f:
                client_config = json.load(f)
        else:
            client_config = {"mcpServers": {}}

        display_target = {
            "vscode": "VS Code",
            "cursor": "Cursor",
            "windsurf": "Windsurf",
            "claude": "Claude",
            "chatgpt": "ChatGPT",
        }.get(target, target)

        if repo_name in client_config.get("mcpServers", {}):
            click.echo(
                f"Warning: Server '{repo_name}' already exists in {display_target} configuration"
            )
            if not click.confirm("Do you want to overwrite it?"):
                click.echo("Aborted")
                sys.exit(0)

        entry = {
            "command": "curl",
            "args": ["-X", "GET", test_url],
            "metadata": {
                "repository": {"type": "git", "url": url},
                "description": f"Test mode: {repo_name} (not registered in platform)",
                "tools": [],
                "test_mode": True,
            },
        }
        client_config.setdefault("mcpServers", {})
        client_config["mcpServers"][repo_name] = entry

        if target == "vscode":
            client_config.setdefault("servers", {})
            client_config["servers"][repo_name] = {
                "type": "http",
                "url": test_url,
                "gallery": False,
            }

        with open(path, "w") as f:
            json.dump(client_config, f, indent=2)

        click.echo("\n" + "=" * 70)
        click.echo("Success!")
        click.echo("=" * 70)
        click.echo(f"\nServer '{repo_name}' added to {display_target} MCP config")
        click.echo(f"Repository: {url}")
        click.echo(f"Test URL: {test_url}")
        click.echo(f"\nLocation: {path}")

    except Exception as e:
        click.echo(f"\nError: {str(e)}")
        sys.exit(1)
