import sys
import json
import shutil
import tempfile
from pathlib import Path

import click

from mcpbox.cli.scanners import bandit, ggshield, sonarqube
from mcpbox.cli.scanners import discovery as tool_discovery
from mcpbox.cli.utils import build_report, show_summary
from mcpbox.shared import s3
from mcpbox.shared.config import Config, load_env


@click.command()
@click.option("--name", help="MCP server name (reads from mcpbox.json if not provided)")
@click.option("--force", is_flag=True, help="Force overwrite if server exists")
def push(
    name: str | None,
    force: bool,
) -> None:
    """Push MCP server to registry with security scanning"""
    try:
        config = {}
        config_file = Path.cwd() / "mcpbox.json"
        if config_file.exists():
            with open(config_file, "r") as f:
                config = json.load(f)

        if not name:
            name = config.get("name")
            if name:
                click.echo(f"Using name from config: {name}")

        if not name:
            click.echo("Error: --name required (or create mcpbox.json with 'mcpbox init')")
            sys.exit(1)

        env_path = Path.cwd() / ".env"
        if not env_path.exists():
            click.echo("Error: .env file not found in current directory")
            sys.exit(1)

        load_env(env_path)
        cfg = Config()

        bucket = cfg.S3_BUCKET_NAME

        try:
            exists, _ = s3.check_server(bucket, name)
            server_exists = exists
            if server_exists:
                click.echo(f"Warning: Server '{name}' already exists in mcp.json")
                if not force and not click.confirm("Do you want to overwrite it?"):
                    click.echo("Aborted")
                    sys.exit(0)
                if force:
                    click.echo("Force flag set, will overwrite existing server")

        except Exception as e:
            click.echo(f"Warning: Could not check S3 bucket: {str(e)}")
            if not click.confirm("Continue anyway?"):
                sys.exit(1)

        repo_url = None
        if isinstance(config.get("repository"), dict):
            repo_url = config.get("repository", {}).get("url")
        if not repo_url and config.get("repo_url"):
            repo_url = config.get("repo_url")
        if not repo_url:
            click.echo("Error: repository URL not found in mcpbox.json under 'repository.url'")
            sys.exit(1)

        click.echo(f"Pushing server: {name}")
        click.echo("Running SonarCloud analysis...")

        try:
            result = sonarqube.run_analysis(repo_url, env_path)

            if not result["success"]:
                click.echo("Analysis failed")
                sys.exit(1)

            _ = result["report_data"]

            temp_dir = tempfile.mkdtemp(prefix="mcpbox_scan_")
            try:
                repo_clone_path = tool_discovery.clone_repo(repo_url, temp_dir)
                if repo_clone_path:
                    tool_info = tool_discovery.discover_tools(repo_clone_path)

                    owner, repo = sonarqube.extract_repository(repo_url)
                    repo_name = f"{owner}_{repo}" if owner and repo else name

                    click.echo("Running additional scanners...")

                    click.echo("\nRunning GitGuardian Secret Scan...")
                    ggshield_result = ggshield.run_scan(repo_clone_path)
                    if ggshield_result.get("success"):
                        click.echo("   GitGuardian: No secrets detected")
                    elif "error" in ggshield_result:
                        click.echo(f"   GitGuardian: {ggshield_result['error']}")
                    else:
                        click.echo(
                            f"   GitGuardian: {ggshield_result.get('total_secrets', 0)} secret(s) detected"
                        )

                    click.echo("\nRunning Bandit Python Security Scan...")
                    bandit_result = bandit.run_scan(repo_clone_path)

                    click.echo("Generating security report...")
                    security_report = build_report(
                        repo_name, repo_url, result["report_data"], ggshield_result, bandit_result
                    )

                    show_summary(security_report)
                else:
                    tool_info = {"tool_count": 0, "tool_names": []}
                    security_report = None
                    click.echo("   Could not discover tools (clone failed)")
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

            server_data = {
                "name": name,
                "repository": {"type": "git", "url": repo_url},
                "description": config.get("description", ""),
                "tools": tool_info.get("tool_names", []),
                "tool_count": tool_info.get("tool_count", 0),
                "security_report": security_report,
            }

            meta = config.get("meta", {})
            if meta:
                meta = {k: v for k, v in meta.items() if k not in ("created_at", "updated_at")}
                if meta:
                    server_data["meta"] = meta

            click.echo("Uploading to S3...")

            s3.upsert_server(bucket, name, server_data)

            click.echo("Push complete")

        except Exception as e:
            click.echo(f"\nError: {e}")
            sys.exit(1)

    except Exception as e:
        click.echo(f"\nError: {str(e)}")
        sys.exit(1)
