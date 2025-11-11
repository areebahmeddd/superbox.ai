import re
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional


def scan_repo(repo_path: str) -> Dict[str, Any]:
    """
    Discover MCP tools from a repository by analyzing Python files.
    Returns dict with tool_count and tool_names list.
    """
    tools = []

    python_files = list(Path(repo_path).rglob("*.py"))

    for py_file in python_files:
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()

            file_tools = extract_tools(content)
            tools.extend(file_tools)
        except Exception:
            continue

    unique_tools = list(set(tools))

    return {"tool_count": len(unique_tools), "tool_names": sorted(unique_tools)}


def extract_tools(content: str) -> List[str]:
    """
    Extract MCP tool names from Python code.
    Looks for @server.call_tool, @mcp.tool, and similar patterns.
    """
    tools = []

    tool_patterns = [
        r'@server\.call_tool\(["\']([^"\']+)["\']\)',
        r'@mcp\.tool\(["\']([^"\']+)["\']\)',
        r'@server\.tool\(["\']([^"\']+)["\']\)',
        r'Tool\(name=["\']([^"\']+)["\']\)',
        r'name=["\']([^"\']+)["\'].*type=["\']tool["\']',
        r"def\s+(\w+).*@.*tool",
    ]

    for pattern in tool_patterns:
        matches = re.findall(pattern, content, re.MULTILINE)
        tools.extend(matches)

    if '"tools"' in content or "'tools'" in content:
        try:
            tools_section = re.search(r'["\']tools["\']\s*:\s*\[(.*?)\]', content, re.DOTALL)
            if tools_section:
                tool_names = re.findall(
                    r'["\']name["\']\s*:\s*["\']([^"\']+)["\']', tools_section.group(1)
                )
                tools.extend(tool_names)
        except Exception:
            pass

    tools = [t for t in tools if t and not t.startswith("_") and len(t) > 1]

    return tools


def scan_package(repo_path: str) -> Dict[str, Any]:
    """
    Check if there's a package.json with MCP tool definitions (for Node.js servers)
    """
    package_json = Path(repo_path) / "package.json"

    if not package_json.exists():
        return {"tool_count": 0, "tool_names": []}

    try:
        with open(package_json, "r") as f:
            data = json.load(f)

        tools = []

        if "mcp" in data and "tools" in data["mcp"]:
            tools = [tool.get("name") for tool in data["mcp"]["tools"] if "name" in tool]

        return {"tool_count": len(tools), "tool_names": sorted(tools)}

    except Exception:
        return {"tool_count": 0, "tool_names": []}


def clone_repo(repo_url: str, target_dir: str) -> Optional[str]:
    """Clone a repository to target_dir and return the clone path, or None on failure"""
    try:
        repo_path = Path(target_dir) / "repo"
        result = subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(repo_path)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            return None
        return str(repo_path)

    except Exception:
        return None


def discover_tools(repo_path: str) -> Dict[str, Any]:
    """Discover tools by scanning code and package.json, merged and deduplicated"""
    from_repo = scan_repo(repo_path)
    from_pkg = scan_package(repo_path)
    names = sorted(list(set(from_repo.get("tool_names", []) + from_pkg.get("tool_names", []))))
    return {"tool_count": len(names), "tool_names": names}
