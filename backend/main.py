import asyncio
from contextlib import asynccontextmanager
import os
import platform
from pathlib import Path
from typing import Set
import psutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from routers import system, packages, storage, services, commands
from services.metrics import collect_live_metrics, get_lite_vitals, refresh_network_indicators
from services.policy_guard import policy_guard


@asynccontextmanager
async def lifespan(app: FastAPI):
    policy_guard.start()
    try:
        yield
    finally:
        await policy_guard.stop()


app = FastAPI(
    title="Cockpit — Ubuntu 8GB System Assistant & Developer Control Center",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(system.router)
app.include_router(packages.router)
app.include_router(storage.router)
app.include_router(services.router)
app.include_router(commands.router)

# Prime psutil CPU counters once on startup
psutil.cpu_percent(interval=None, percpu=True)

# Track active WebSocket connections — ZERO background polling when empty
_active_ws_clients: Set[WebSocket] = set()


@app.get("/api/health")
async def health_check():
    proc = psutil.Process(os.getpid())
    rss_mb = round(proc.memory_info().rss / (1024 * 1024), 2)
    return {
        "status": "ok",
        "hostname": platform.node(),
        "kernel": platform.release(),
        "distro": "Ubuntu Linux",
        "backend_pid": os.getpid(),
        "backend_rss_mb": rss_mb,
        "active_ws_clients": len(_active_ws_clients),
        "policy_guard_active": policy_guard._running,
    }


@app.get("/api/vitals/lite")
async def vitals_lite():
    """Ultra-lightweight vitals endpoint for the Ubuntu Top Bar AppIndicator (polled every 4s)."""
    return get_lite_vitals()


@app.websocket("/ws/metrics")
async def websocket_metrics_endpoint(websocket: WebSocket):
    """
    Streams live CPU, per-core load, temperature, battery wattage, Disk/Net I/O,
    and detailed RAM/ZRAM/Swap telemetry every 1.5 seconds ONLY while connected.
    Zero background loops or timers run when no client is connected.
    """
    await websocket.accept()
    _active_ws_clients.add(websocket)
    try:
        while True:
            await refresh_network_indicators()
            payload = collect_live_metrics()
            await websocket.send_json(payload)
            await asyncio.sleep(1.5)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        _active_ws_clients.discard(websocket)


# Serve compiled Vue 3 static bundle from ../frontend/dist when built
FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(FRONTEND_DIST / "assets")),
        name="static_assets",
    )


@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    if full_path.startswith("api/") or full_path.startswith("ws/"):
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    target_file = FRONTEND_DIST / full_path
    if full_path and target_file.exists() and target_file.is_file():
        return FileResponse(str(target_file))

    index_html = FRONTEND_DIST / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))

    return JSONResponse(
        {
            "message": "Cockpit Backend API is online. Build the frontend via ./install.sh to serve the UI."
        }
    )
