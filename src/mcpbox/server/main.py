from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from mcpbox.server.routes import servers_router, payment_router
from mcpbox.shared.config import Config
from mcpbox.shared.config import ServerConfig, load_env
from mcpbox.shared.s3 import s3_client

load_env()

_server_cfg = ServerConfig()
settings = _server_cfg.app_params()
app = FastAPI(**settings)

cors = _server_cfg.cors_params()
app.add_middleware(CORSMiddleware, **cors)

app.include_router(servers_router, prefix="/api/v1/servers")
app.include_router(payment_router, prefix="/api/v1/payment")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Root HTML landing page"""
    tpl_path = Path(__file__).parent / "templates" / "index.html"
    content = tpl_path.read_text(encoding="utf-8")
    return HTMLResponse(content=content)


@app.get("/health")
async def health():
    """Health check reporting config status and S3 readiness"""
    # Config presence
    try:
        cfg = Config()
        cfg_ok = True
    except Exception:
        cfg_ok = False
        cfg = None

    # S3 readiness
    s3_ok = False
    registry_ok = False
    if cfg_ok:
        try:
            s3 = s3_client()
            try:
                s3.list_objects_v2(Bucket=cfg.S3_BUCKET_NAME, MaxKeys=1)
                registry_ok = True
            except Exception:
                registry_ok = False
            s3_ok = True
        except Exception:
            s3_ok = False

    return JSONResponse(
        content={
            "status": "healthy" if (cfg_ok and s3_ok) else "degraded",
            "version": settings.get("version"),
            "config_ok": cfg_ok,
            "s3_client_ok": s3_ok,
            "registry_ok": registry_ok,
        }
    )


def run_server():
    """Run server from CLI"""
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    run_server()
