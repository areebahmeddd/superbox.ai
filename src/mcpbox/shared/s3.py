import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

import boto3

from mcpbox.shared.config import Config


def s3_client() -> Any:
    """Create and return S3 client using shared Config values"""
    cfg = Config()
    return boto3.client(
        "s3",
        region_name=cfg.AWS_REGION,
        aws_access_key_id=cfg.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=cfg.AWS_SECRET_ACCESS_KEY,
    )


def _server_key(server_name: str) -> str:
    return f"{server_name}.json"


def get_server(bucket_name: str, server_name: str) -> Optional[Dict[str, Any]]:
    """Fetch a single MCP server JSON: <name>.json"""
    s3 = s3_client()
    key = _server_key(server_name)
    try:
        response = s3.get_object(Bucket=bucket_name, Key=key)
        content = response["Body"].read().decode("utf-8")
        return json.loads(content)
    except Exception:
        return None


def save_server(bucket_name: str, server_name: str, data: Dict[str, Any]) -> bool:
    """Write a single MCP server JSON: <name>.json"""
    s3 = s3_client()
    key = _server_key(server_name)
    payload = dict(data)
    if "name" not in payload:
        payload["name"] = server_name
    s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=json.dumps(payload, indent=2),
        ContentType="application/json",
    )
    return True


def list_servers(bucket_name: str) -> Dict[str, Dict[str, Any]]:
    """List all MCP servers by enumerating *.json objects in the bucket.

    Returns a mapping {name: data}.
    """
    s3 = s3_client()
    servers: Dict[str, Dict[str, Any]] = {}
    continuation_token: Optional[str] = None
    while True:
        kwargs: Dict[str, Any] = {"Bucket": bucket_name}
        if continuation_token:
            kwargs["ContinuationToken"] = continuation_token
        resp = s3.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            key = obj.get("Key", "")
            if not key.lower().endswith(".json"):
                continue
            name = key[:-5]  # strip .json
            try:
                data = get_server(bucket_name, name)
                if data is not None:
                    servers[name] = data
            except Exception:
                # Skip unreadable entries
                pass
        if resp.get("IsTruncated"):
            continuation_token = resp.get("NextContinuationToken")
        else:
            break
    return servers


def check_server(bucket_name: str, server_name: str) -> Tuple[bool, Dict[str, Any]]:
    """Check if a per-file server exists; returns (exists, currentDataOrEmpty)."""
    data = get_server(bucket_name, server_name)
    return (data is not None, data or {})


def find_server(bucket_name: str, server_name: str) -> Optional[Dict[str, Any]]:
    """Find a server by name using per-file storage."""
    return get_server(bucket_name, server_name)


def upsert_server(bucket_name: str, server_name: str, server_data: Dict[str, Any]) -> bool:
    """Create or update a single MCP server file <name>.json, preserving created_at if present."""
    existing = get_server(bucket_name, server_name)
    server_data = dict(server_data)

    if "meta" not in server_data:
        server_data["meta"] = {}

    if existing:
        if existing.get("meta") and existing["meta"].get("created_at"):
            server_data["meta"]["created_at"] = existing["meta"]["created_at"]
    else:
        if "created_at" not in server_data["meta"]:
            server_data["meta"]["created_at"] = datetime.now(timezone.utc).isoformat()

    server_data["meta"]["updated_at"] = datetime.now(timezone.utc).isoformat()
    return save_server(bucket_name, server_name, server_data)


def delete_server(bucket_name: str, server_name: str) -> bool:
    """Delete a single MCP server JSON file: <name>.json"""
    s3 = s3_client()
    key = _server_key(server_name)
    try:
        s3.delete_object(Bucket=bucket_name, Key=key)
        return True
    except Exception:
        return False
