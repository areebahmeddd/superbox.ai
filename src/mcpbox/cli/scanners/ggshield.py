import os
import json
import subprocess
from typing import Any, Dict

from mcpbox.shared.config import Config


def run_scan(path_to_scan: str) -> Dict[str, Any]:
    """Run GitGuardian ggshield scan on repository"""
    print("[GGShield] Starting secret scan")
    cfg = Config()
    env = dict(os.environ)
    env["GITGUARDIAN_API_KEY"] = cfg.GITGUARDIAN_API_KEY

    cmd = ["ggshield", "secret", "scan", "path", path_to_scan, "--recursive", "--json"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=env)

        scan_data = None
        if result.stdout:
            try:
                scan_data = json.loads(result.stdout)
            except json.JSONDecodeError:
                pass

        secrets_found = []
        total_secrets = 0

        if scan_data and isinstance(scan_data, list):
            for item in scan_data:
                secrets = item.get("secrets", [])
                total_secrets += len(secrets)
                for secret in secrets:
                    secrets_found.append(
                        {
                            "type": secret.get("type"),
                            "validity": secret.get("validity"),
                            "file": item.get("filename"),
                            "line": secret.get("start_line"),
                        }
                    )

        result_dict = {
            "success": result.returncode == 0,
            "total_secrets": total_secrets,
            "secrets": secrets_found,
        }
        print("[GGShield] Scan complete")
        return result_dict

    except subprocess.TimeoutExpired:
        print("[GGShield] Scanner timeout")
        return {"success": False, "error": "Scanner timeout", "total_secrets": 0, "secrets": []}
    except FileNotFoundError:
        print("[GGShield] ggshield not installed")
        return {
            "success": False,
            "error": "ggshield not installed",
            "total_secrets": 0,
            "secrets": [],
        }
    except Exception as e:
        print(f"[GGShield] Error: {str(e)}")
        return {"success": False, "error": str(e), "total_secrets": 0, "secrets": []}
