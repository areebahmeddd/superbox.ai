import sys
import json
from pathlib import Path

import click
import requests

from mcpbox.shared.config import Config, load_env


@click.command()
@click.option("--name", required=True, help="MCP server name to run")
def run(name: str) -> None:
    """Start an interactive session posting prompts to the MCP executor."""
    try:
        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            click.echo("Error: .env file not found in current directory")
            sys.exit(1)

        load_env(env_path)
        cfg = Config()

        lambda_base_url = cfg.LAMBDA_BASE_URL

        url = f"{lambda_base_url.rstrip('/')}/{name}"
        click.echo(f"Connecting to MCP executor: {url}")
        click.echo("Type 'exit' or 'quit' to end. Press Enter on empty line to continue.")

        while True:
            try:
                prompt = input("> ")
            except (EOFError, KeyboardInterrupt):
                click.echo("\nExiting.")
                break

            if prompt is None:
                continue
            prompt = prompt.strip()
            if prompt.lower() in {"exit", "quit"}:
                click.echo("Bye.")
                break
            if prompt == "":
                continue

            try:
                resp = requests.post(url, data=prompt, timeout=60)
            except requests.RequestException as e:
                click.echo(f"Request error: {str(e)}")
                continue

            if resp.status_code != 200:
                click.echo(f"Error [{resp.status_code}]: {resp.text[:300]}")
                continue

            body_text = resp.text or ""
            try:
                parsed = json.loads(body_text)
                click.echo(json.dumps(parsed, indent=2))
            except Exception:
                click.echo(body_text)
    except Exception as e:
        click.echo(f"\nError: {str(e)}")
        sys.exit(1)
