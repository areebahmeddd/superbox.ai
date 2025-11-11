from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from mcpbox.shared.config import Config
from mcpbox.shared.models import CreateServerRequest, UpdateServerRequest
from mcpbox.shared.s3 import (
    list_servers as s3_list_servers,
    get_server as s3_get_server,
    upsert_server,
    delete_server as s3_delete_server,
)

router = APIRouter()

_cfg = Config()
S3_BUCKET = _cfg.S3_BUCKET_NAME


@router.get("/{server_name}")
async def get_server(server_name: str) -> JSONResponse:
    """Get detailed information about a specific MCP server"""
    try:
        server = s3_get_server(S3_BUCKET, server_name)

        if not server:
            raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

        return JSONResponse(content={"status": "success", "server": server})

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching server info: {str(e)}")


@router.get("")
async def list_servers() -> JSONResponse:
    """List all MCP servers from S3 bucket"""
    try:
        server_map = s3_list_servers(S3_BUCKET)

        if not server_map:
            return JSONResponse(content={"status": "success", "total": 0, "servers": []})

        server_list = []
        for server in server_map.values():
            server_info = {
                "name": server.get("name"),
                "version": server.get("version"),
                "description": server.get("description"),
                "author": server.get("author"),
                "lang": server.get("lang"),
                "license": server.get("license"),
                "entrypoint": server.get("entrypoint"),
                "repository": server.get("repository"),
            }

            if "tools" in server and server["tools"]:
                server_info["tools"] = server["tools"]

            if "pricing" in server and server["pricing"]:
                server_info["pricing"] = server["pricing"]
            else:
                server_info["pricing"] = {"currency": "", "amount": 0}

            if "security_report" in server and server["security_report"]:
                server_info["security_report"] = server["security_report"]

            server_list.append(server_info)

        return JSONResponse(
            content={"status": "success", "total": len(server_list), "servers": server_list}
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching servers: {str(e)}")


@router.post("")
async def create_server(server: CreateServerRequest) -> JSONResponse:
    """Create a new MCP server and add it to S3"""
    try:
        existing = s3_get_server(S3_BUCKET, server.name)
        if existing:
            raise HTTPException(status_code=400, detail=f"Server '{server.name}' already exists")

        new_server = {
            "name": server.name,
            "version": server.version,
            "description": server.description,
            "author": server.author,
            "lang": server.lang,
            "license": server.license,
            "entrypoint": server.entrypoint,
            "repository": {"type": server.repository.type, "url": server.repository.url},
            "meta": {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        new_server["pricing"] = {
            "currency": server.pricing.currency,
            "amount": server.pricing.amount,
        }

        if server.tools:
            new_server["tools"] = server.tools

        upsert_server(S3_BUCKET, server.name, new_server)

        return JSONResponse(
            content={"status": "success", "message": "Server created", "server": new_server},
            status_code=201,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating server: {str(e)}")


@router.put("/{server_name}")
async def update_server(server_name: str, updates: UpdateServerRequest) -> JSONResponse:
    """Update an existing MCP server with partial updates"""
    try:
        existing = s3_get_server(S3_BUCKET, server_name)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

        updated_data = dict(existing)

        new_name = updates.name if updates.name else server_name
        if updates.name and updates.name != server_name:
            if s3_get_server(S3_BUCKET, updates.name):
                raise HTTPException(
                    status_code=400, detail=f"Server '{updates.name}' already exists"
                )
            updated_data["name"] = updates.name

        if updates.version is not None:
            updated_data["version"] = updates.version
        if updates.description is not None:
            updated_data["description"] = updates.description
        if updates.author is not None:
            updated_data["author"] = updates.author
        if updates.lang is not None:
            updated_data["lang"] = updates.lang
        if updates.license is not None:
            updated_data["license"] = updates.license
        if updates.entrypoint is not None:
            updated_data["entrypoint"] = updates.entrypoint
        if updates.repository is not None:
            updated_data["repository"] = {
                "type": updates.repository.type,
                "url": updates.repository.url,
            }
        if updates.pricing is not None:
            updated_data["pricing"] = {
                "currency": updates.pricing.currency,
                "amount": updates.pricing.amount,
            }
        if updates.tools is not None:
            updated_data["tools"] = updates.tools
        if updates.security_report is not None:
            updated_data["security_report"] = updates.security_report

        if "meta" in updated_data and "created_at" in updated_data["meta"]:
            del updated_data["meta"]["created_at"]

        if new_name != server_name:
            s3_delete_server(S3_BUCKET, server_name)

        upsert_server(S3_BUCKET, new_name, updated_data)

        return JSONResponse(
            content={
                "status": "success",
                "message": f"Server '{server_name}' updated successfully",
                "server": updated_data,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error updating server: {str(e)}")


@router.delete("/{server_name}")
async def delete_server(server_name: str) -> JSONResponse:
    """Delete an MCP server from the registry"""
    try:
        existing = s3_get_server(S3_BUCKET, server_name)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Server '{server_name}' not found")

        success = s3_delete_server(S3_BUCKET, server_name)
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to delete server '{server_name}'")

        return JSONResponse(
            content={
                "status": "success",
                "message": f"Server '{server_name}' deleted successfully",
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting server: {str(e)}")
