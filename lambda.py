import os
import sys
import json
import shutil
import zipfile
import tempfile
import subprocess
import urllib.parse
import urllib.request

import boto3

from typing import Any, Dict


def get_env(key: str) -> str:
    """Read required environment variable."""
    value = os.environ.get(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


# Configuration
AWS_REGION = get_env("AWS_REGION")
S3_BUCKET = get_env("S3_BUCKET_NAME")


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Lambda handler for MCP server requests."""
    try:
        mcp_name = extract_name(event)
        print(f"Request received: {mcp_name}")

        query_params = event.get("queryStringParameters") or {}
        is_test_mode = query_params.get("test_mode", "").lower() == "true"
        repo_url = query_params.get("repo_url")
        entrypoint = query_params.get("entrypoint", "main.py")
        lang = query_params.get("lang", "python")

        if is_test_mode and repo_url:
            repo_url = urllib.parse.unquote(repo_url)
            print(f"Test mode: Using direct repo URL {repo_url}")
            metadata = {
                "repository": {"url": repo_url},
                "entrypoint": entrypoint,
                "lang": lang,
            }
        else:
            metadata = fetch_meta(mcp_name)

        repo_dir = clone_repo(metadata["repository"]["url"], mcp_name)
        print(f"Repository ready: {repo_dir}")

        install_deps(repo_dir)

        mcp_response = run_server(
            repo_dir=repo_dir,
            entrypoint=metadata["entrypoint"],
            lang=metadata["lang"],
            request_body=event.get("body", ""),
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
            },
            "body": mcp_response,
        }
    except Exception as e:
        print(f"Error: {str(e)}")

        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*"},
            "body": json.dumps({"error": str(e), "type": type(e).__name__}),
        }


def extract_name(event: Dict[str, Any]) -> str:
    """Extract MCP server name from request path."""
    raw_path = event.get("rawPath", "")

    if not raw_path:
        raw_path = event.get("path", "")

    path_parts = raw_path.strip("/").split("/")
    mcp_name = path_parts[-1] if path_parts else ""

    if not mcp_name:
        raise ValueError("MCP server name not found in request path")

    return mcp_name


def fetch_meta(mcp_name: str) -> Dict[str, Any]:
    """Fetch MCP server metadata from S3 per-file storage (<name>.json)."""
    s3 = boto3.client("s3", region_name=AWS_REGION)

    key = f"{mcp_name}.json"
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=key)
        mcp = json.loads(response["Body"].read().decode("utf-8"))
        return mcp
    except s3.exceptions.NoSuchKey:
        raise FileNotFoundError(f"MCP definition not found in S3: {key}")
    except Exception as e:
        raise Exception(f"Failed to fetch MCP metadata: {str(e)}")


def clone_repo(repo_url: str, mcp_name: str) -> str:
    """Download the MCP server repository from GitHub as a ZIP file."""
    temp_dir = tempfile.mkdtemp(prefix=f"mcp_{mcp_name}_")
    repo_dir = os.path.join(temp_dir, "repo")

    try:
        if "github.com" in repo_url:
            repo_url = repo_url.rstrip("/").replace(".git", "")
            zip_url = f"{repo_url}/archive/refs/heads/main.zip"
        else:
            raise ValueError(f"Only GitHub repositories are supported. Got: {repo_url}")

        zip_path = os.path.join(temp_dir, "repo.zip")
        urllib.request.urlretrieve(zip_url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(temp_dir)

        extracted_folders = [
            f for f in os.listdir(temp_dir) if os.path.isdir(os.path.join(temp_dir, f))
        ]

        if not extracted_folders:
            raise Exception("No folder found in extracted ZIP")

        extracted_path = os.path.join(temp_dir, extracted_folders[0])
        os.rename(extracted_path, repo_dir)

        os.remove(zip_path)

        return repo_dir
    except Exception as e:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise Exception(f"Failed to download repository: {str(e)}")


def install_deps(repo_dir: str) -> None:
    """Install Python dependencies from requirements.txt in the repository."""
    requirements_file = os.path.join(repo_dir, "requirements.txt")

    if not os.path.exists(requirements_file):
        # No dependencies to install
        return

    pip_target = os.path.join("/tmp", "pip_modules")
    os.makedirs(pip_target, exist_ok=True)

    if pip_target not in sys.path:
        sys.path.insert(0, pip_target)

    try:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                requirements_file,
                "--target",
                pip_target,
                "--upgrade",
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )

        if result.returncode != 0:
            print("Warning: pip install returned non-zero status")
    except subprocess.TimeoutExpired:
        print("Warning: pip install timed out")
    except Exception as e:
        print(f"Warning: dependency installation error: {str(e)}")


def run_server(repo_dir: str, entrypoint: str, lang: str, request_body: str) -> str:
    """Execute the MCP server and return its response."""
    if lang.lower() != "python":
        raise ValueError(f"Unsupported language: {lang}. Only Python is supported currently.")

    entrypoint_path = os.path.join(repo_dir, entrypoint)

    if not os.path.exists(entrypoint_path):
        raise FileNotFoundError(f"Entrypoint not found: {entrypoint}")

    env = os.environ.copy()
    env["PYTHONPATH"] = f"{repo_dir}:{env.get('PYTHONPATH', '')}"

    pip_target = os.path.join("/tmp", "pip_modules")
    if os.path.exists(pip_target):
        env["PYTHONPATH"] = f"{pip_target}:{env['PYTHONPATH']}"

    try:
        process = subprocess.Popen(
            [sys.executable, entrypoint_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=repo_dir,
            env=env,
        )

        stdout, stderr = process.communicate(input=request_body.encode("utf-8"), timeout=30)

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8") if stderr else "Unknown error"
            raise Exception(f"MCP server exited with code {process.returncode}: {error_msg}")

        response = stdout.decode("utf-8")

        if stderr:
            print(f"MCP server stderr: {stderr.decode('utf-8')[:200]}")

        return response
    except subprocess.TimeoutExpired:
        process.kill()
        raise Exception("MCP server execution timed out after 30 seconds")
    except Exception as e:
        raise Exception(f"Failed to execute MCP server: {str(e)}")
