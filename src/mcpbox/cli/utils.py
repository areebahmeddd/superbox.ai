import os
import platform
from pathlib import Path
from datetime import datetime
from typing import Any, Dict

import click


def build_report(
    repo_name: str,
    repo_url: str,
    sonarqube_data: Dict[str, Any],
    ggshield_result: Dict[str, Any],
    bandit_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Create a unified security report combining all scanner results"""
    unified_report = {
        "metadata": {
            "repository": repo_name,
            "repo_url": repo_url,
            "scan_date": datetime.now().isoformat(),
            "scanners_used": ["SonarQube", "GitGuardian ggshield", "Bandit"],
        },
        "summary": {
            "total_issues_all_scanners": (
                sonarqube_data.get("issue_counts", {}).get("total", 0)
                + ggshield_result.get("total_secrets", 0)
                + bandit_result.get("total_issues", 0)
            ),
            "critical_issues": 0,
            "sonarcloud_url": sonarqube_data.get("metadata", {}).get("sonarcloud_url", ""),
            "scan_passed": (
                sonarqube_data.get("issue_counts", {}).get("total", 0) == 0
                and ggshield_result.get("total_secrets", 0) == 0
                and bandit_result.get("total_issues", 0) == 0
            ),
        },
        "sonarqube": {
            "total_issues": sonarqube_data.get("issue_counts", {}).get("total", 0),
            "bugs": sonarqube_data.get("issue_counts", {}).get("bugs", 0),
            "vulnerabilities": sonarqube_data.get("issue_counts", {}).get("vulnerabilities", 0),
            "code_smells": sonarqube_data.get("issue_counts", {}).get("code_smells", 0),
            "security_hotspots": sonarqube_data.get("issue_counts", {}).get("security_hotspots", 0),
            "quality_gate": sonarqube_data.get("quality_gate", {}).get("status", "N/A"),
            "reliability_rating": sonarqube_data.get("quality_ratings", {}).get(
                "reliability", "N/A"
            ),
            "security_rating": sonarqube_data.get("quality_ratings", {}).get("security", "N/A"),
            "maintainability_rating": sonarqube_data.get("quality_ratings", {}).get(
                "maintainability", "N/A"
            ),
            "coverage": sonarqube_data.get("metrics", {}).get("coverage", 0),
            "duplications": sonarqube_data.get("metrics", {}).get("duplicated_lines_density", 0),
            "lines_of_code": sonarqube_data.get("metrics", {}).get("ncloc", 0),
        },
        "gitguardian": {
            "scan_passed": ggshield_result.get("success", False),
            "total_secrets": ggshield_result.get("total_secrets", 0),
            "secrets": ggshield_result.get("secrets", []),
            "error": ggshield_result.get("error"),
        },
        "bandit": {
            "scan_passed": bandit_result.get("success", False),
            "total_issues": bandit_result.get("total_issues", 0),
            "severity_counts": bandit_result.get("severity_counts", {}),
            "total_lines_scanned": bandit_result.get("total_lines_scanned", 0),
            "issues": bandit_result.get("issues", []),
            "error": bandit_result.get("error"),
        },
        "recommendations": [],
    }

    sonar_issues = sonarqube_data.get("issue_counts", {}).get("total", 0)
    secrets = ggshield_result.get("total_secrets", 0)
    bandit_issues = bandit_result.get("total_issues", 0)
    high_severity = bandit_result.get("severity_counts", {}).get("high", 0)
    coverage = sonarqube_data.get("metrics", {}).get("coverage", 0)

    try:
        coverage = float(coverage) if coverage else 0
    except (ValueError, TypeError):
        coverage = 0

    if sonar_issues > 5 or secrets > 0 or high_severity > 0:
        unified_report["recommendations"].append(
            "Critical security issues found - immediate action required"
        )
    if secrets > 0:
        unified_report["recommendations"].append(
            "Secrets detected - rotate credentials immediately"
        )
    if bandit_issues > 0:
        unified_report["recommendations"].append("Security vulnerabilities found - review and fix")
    if high_severity > 0:
        unified_report["recommendations"].append("High-severity issues detected - prioritize fixes")
    if coverage < 80:
        unified_report["recommendations"].append("Code coverage below 80% - add more tests")
    if len(unified_report["recommendations"]) == 0:
        unified_report["recommendations"].append("All security scans passed")

    return unified_report


def show_summary(security_report: Dict[str, Any]) -> None:
    """Print a summary of the security report."""
    total_issues = security_report["summary"]["total_issues_all_scanners"]
    if total_issues == 0:
        click.echo("Scans passed: no issues found")
        return
    click.echo(f"Scans found {total_issues} issue(s)")
    # Only print critical counts if present
    sonar_total = security_report["sonarqube"].get("total_issues", 0)
    secrets = security_report["gitguardian"].get("total_secrets", 0)
    bandit_total = security_report["bandit"].get("total_issues", 0)
    parts = []
    if sonar_total:
        parts.append(f"sonar={sonar_total}")
    if secrets:
        parts.append(f"secrets={secrets}")
    if bandit_total:
        parts.append(f"bandit={bandit_total}")
    if parts:
        click.echo("Details: " + ", ".join(parts))


def config_path(app: str) -> Path:
    app = app.lower()
    system = platform.system()
    if app == "vscode":
        if system == "Windows":
            return Path(os.getenv("APPDATA")) / "Code" / "User" / "mcp.json"
        if system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "Code" / "User" / "mcp.json"
        if system == "Linux":
            return Path.home() / ".config" / "Code" / "User" / "mcp.json"
    if app == "cursor":
        if system == "Windows":
            return Path(os.getenv("USERPROFILE")) / ".cursor" / "mcp.json"
        if system == "Darwin" or system == "Linux":
            return Path.home() / ".cursor" / "mcp.json"
    if app == "windsurf":
        if system == "Windows":
            return Path(os.getenv("APPDATA")) / "Windsurf" / "User" / "mcp.json"
        if system == "Darwin":
            return (
                Path.home() / "Library" / "Application Support" / "Windsurf" / "User" / "mcp.json"
            )
        if system == "Linux":
            return Path.home() / ".config" / "Windsurf" / "User" / "mcp.json"
    if app == "claude":
        if system == "Windows":
            return Path(os.getenv("APPDATA")) / "Claude" / "claude_desktop_config.json"
        if system == "Darwin":
            return (
                Path.home()
                / "Library"
                / "Application Support"
                / "Claude"
                / "claude_desktop_config.json"
            )
        if system == "Linux":
            return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"
    if app == "chatgpt":
        if system == "Windows":
            return Path(os.getenv("APPDATA")) / "ChatGPT" / "mcp.json"
        if system == "Darwin":
            return Path.home() / "Library" / "Application Support" / "ChatGPT" / "mcp.json"
        if system == "Linux":
            return Path.home() / ".config" / "ChatGPT" / "mcp.json"
    raise RuntimeError(f"Unsupported app '{app}' or OS '{system}'")
