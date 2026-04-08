#!/usr/bin/env python3
"""
FastAPI Backend for Visualization System.
- Serves structure.json to the dashboard
- Provides WebSocket for real-time interaction tracking
- Triggers re-scan of repositories
- Env-based config, rate limiting, error handling
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

# ───────────────────────── Config from environment ─────────────────────────

# Load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env")
    load_dotenv(Path(__file__).parent / ".env")  # backend-local override
except ImportError:
    pass

PORT = int(os.getenv("PORT", "8000"))
HOST = os.getenv("HOST", "0.0.0.0")
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://localhost:3001"
).split(",")
DEFAULT_REPO_PATH = os.getenv("DEFAULT_REPO_PATH", "")
MAX_INTERACTION_LOG = int(os.getenv("MAX_INTERACTION_LOG", "500"))
SCAN_RATE_LIMIT_SECONDS = int(os.getenv("SCAN_RATE_LIMIT_SECONDS", "5"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("viz-backend")

# Add analyzer to path
sys.path.insert(0, str(Path(__file__).parent.parent / "analyzer"))
from scanner import scan_repository

app = FastAPI(title="Visualization Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ───────────────────────── State ─────────────────────────

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# Current structure data (in-memory cache)
current_structure: Optional[dict] = None

# Active WebSocket connections for the dashboard
dashboard_connections: list[WebSocket] = []

# Active interaction events log
interaction_log: list[dict] = []

# Active node highlights (node_id -> timestamp)
active_nodes: dict[str, str] = {}

# Rate limiting state for scan endpoint
_last_scan_time: float = 0.0
_scan_in_progress = False

# Component visit counts for heatmap analytics
_component_visit_counts: dict[str, int] = {}


# ───────────────────────── Models ─────────────────────────

class InteractionEvent(BaseModel):
    eventType: str
    componentName: str
    filePath: Optional[str] = None
    route: Optional[str] = None
    timestamp: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator("eventType")
    @classmethod
    def validate_event_type(cls, v: str) -> str:
        allowed = {"mount", "unmount", "click", "navigate", "api_call", "error", "render"}
        if v not in allowed:
            raise ValueError(f"eventType must be one of {allowed}")
        return v

    @field_validator("componentName")
    @classmethod
    def validate_component_name(cls, v: str) -> str:
        if not v or len(v) > 200:
            raise ValueError("componentName must be 1-200 chars")
        return v


class ScanRequest(BaseModel):
    repoPath: str

    @field_validator("repoPath")
    @classmethod
    def validate_repo_path(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("repoPath is required")
        # Block path traversal attempts
        normalized = os.path.normpath(v)
        if ".." in normalized.split(os.sep):
            raise ValueError("Path traversal not allowed")
        return v


# ───────────────────────── WebSocket Manager ─────────────────────────


async def broadcast_to_dashboards(message: dict):
    """Send a message to all connected dashboard clients."""
    dead = []
    for ws in dashboard_connections:
        try:
            await ws.send_json(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in dashboard_connections:
            dashboard_connections.remove(ws)


# ───────────────────────── REST Endpoints ─────────────────────────


@app.get("/api/structure")
async def get_structure():
    """Return the current analyzed structure."""
    global current_structure
    if current_structure is None:
        # Try loading from disk
        cache_file = DATA_DIR / "structure.json"
        if cache_file.exists():
            try:
                raw = cache_file.read_text(encoding="utf-8")
                current_structure = json.loads(raw)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to read cache file: %s", e)
                return JSONResponse(
                    status_code=500,
                    content={"error": "Cached data is corrupted. Trigger a new scan."},
                )
        else:
            return JSONResponse(
                status_code=404,
                content={"error": "No structure data. Trigger a scan first."},
            )
    return current_structure


@app.post("/api/scan")
async def trigger_scan(req: ScanRequest):
    """Trigger a re-scan of the repository."""
    global current_structure, _last_scan_time, _scan_in_progress

    # Rate limiting
    now = time.monotonic()
    if now - _last_scan_time < SCAN_RATE_LIMIT_SECONDS:
        wait = int(SCAN_RATE_LIMIT_SECONDS - (now - _last_scan_time)) + 1
        return JSONResponse(
            status_code=429,
            content={"error": f"Rate limited. Try again in {wait}s."},
        )

    if _scan_in_progress:
        return JSONResponse(
            status_code=409,
            content={"error": "A scan is already in progress."},
        )

    repo_path = req.repoPath
    resolved = Path(repo_path).resolve()

    if not resolved.is_dir():
        return JSONResponse(
            status_code=400,
            content={"error": f"'{repo_path}' is not a directory"},
        )

    # Basic safety: must contain package.json or src/
    if not (resolved / "package.json").exists() and not (resolved / "src").is_dir():
        return JSONResponse(
            status_code=400,
            content={"error": f"'{repo_path}' does not appear to be a JavaScript/TypeScript project (no package.json or src/)"},
        )

    _scan_in_progress = True
    _last_scan_time = now
    logger.info("Scanning repository: %s", resolved)

    try:
        structure = scan_repository(str(resolved))
        current_structure = structure

        # Persist to disk
        cache_file = DATA_DIR / "structure.json"
        try:
            cache_file.write_text(json.dumps(structure, indent=2), encoding="utf-8")
        except OSError as e:
            logger.error("Failed to write cache: %s", e)

        # Notify dashboards
        await broadcast_to_dashboards({
            "type": "structure_update",
            "data": structure,
        })

        logger.info(
            "Scan complete: %d files, %d nodes, %d edges",
            structure["metadata"]["analyzedFiles"],
            len(structure["nodes"]),
            structure["metadata"]["totalEdges"],
        )

        return {
            "status": "ok",
            "metadata": structure["metadata"],
        }
    except ValueError as e:
        return JSONResponse(status_code=400, content={"error": str(e)})
    except Exception as e:
        logger.exception("Scan failed")
        return JSONResponse(status_code=500, content={"error": f"Scan failed: {str(e)}"})
    finally:
        _scan_in_progress = False


@app.post("/api/interaction")
async def post_interaction(event: InteractionEvent):
    """Receive an interaction event from the demo app and broadcast to dashboards."""
    ts = event.timestamp or datetime.now(timezone.utc).isoformat()

    entry = {
        "eventType": event.eventType,
        "componentName": event.componentName,
        "filePath": event.filePath,
        "route": event.route,
        "timestamp": ts,
        "metadata": event.metadata or {},
    }

    interaction_log.append(entry)
    # Keep bounded
    while len(interaction_log) > MAX_INTERACTION_LOG:
        interaction_log.pop(0)

    # Track active nodes
    if event.eventType in ("mount", "navigate", "click"):
        active_nodes[event.componentName] = ts
        _component_visit_counts[event.componentName] = _component_visit_counts.get(event.componentName, 0) + 1
    elif event.eventType == "unmount":
        active_nodes.pop(event.componentName, None)

    # Broadcast to dashboards
    await broadcast_to_dashboards({
        "type": "interaction",
        "data": entry,
        "activeNodes": list(active_nodes.keys()),
    })

    return {"status": "ok"}


@app.get("/api/interactions")
async def get_interactions(limit: int = Query(default=50, le=500, ge=1)):
    """Return recent interaction events."""
    return {
        "events": interaction_log[-limit:],
        "activeNodes": list(active_nodes.keys()),
    }


@app.delete("/api/interactions")
async def clear_interactions():
    """Clear the interaction log and active nodes."""
    interaction_log.clear()
    active_nodes.clear()
    _component_visit_counts.clear()
    await broadcast_to_dashboards({
        "type": "clear",
        "activeNodes": [],
    })
    logger.info("Interaction log cleared")
    return {"status": "ok"}


# ───────────────────────── Analytics Endpoints ─────────────────────────


@app.get("/api/analytics")
async def get_analytics():
    """Return analytics data: heatmap, circular deps, dead files, dependents."""
    analytics: dict = {"heatmap": dict(_component_visit_counts)}
    if current_structure:
        sa = current_structure.get("analytics", {})
        analytics["circularDeps"] = sa.get("circularDeps", [])
        analytics["deadFiles"] = sa.get("deadFiles", [])
        analytics["dependents"] = sa.get("dependents", {})
    else:
        analytics["circularDeps"] = []
        analytics["deadFiles"] = []
        analytics["dependents"] = {}
    return analytics


@app.get("/api/analytics/impact")
async def get_change_impact(nodeId: str = Query(..., min_length=1)):
    """Compute transitive dependents (who is impacted if this file changes)."""
    if not current_structure:
        return {"nodeId": nodeId, "impacted": []}
    dependents = current_structure.get("analytics", {}).get("dependents", {})
    visited: set[str] = set()
    queue = [nodeId]
    while queue:
        n = queue.pop(0)
        if n in visited:
            continue
        visited.add(n)
        for parent in dependents.get(n, []):
            if parent not in visited:
                queue.append(parent)
    visited.discard(nodeId)
    return {"nodeId": nodeId, "impacted": list(visited)}


# ───────────────────────── WebSocket Endpoints ─────────────────────────


@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    """WebSocket for dashboard clients to receive real-time updates."""
    await websocket.accept()
    dashboard_connections.append(websocket)
    logger.info("Dashboard connected (%d total)", len(dashboard_connections))

    try:
        await websocket.send_json({
            "type": "connected",
            "activeNodes": list(active_nodes.keys()),
        })

        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=60)
            if data == "ping":
                await websocket.send_text("pong")
    except asyncio.TimeoutError:
        # No data in 60s — send a server ping to check liveness
        try:
            await websocket.send_text("ping")
        except Exception:
            pass
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("Dashboard WS error: %s", e)
    finally:
        if websocket in dashboard_connections:
            dashboard_connections.remove(websocket)
        logger.info("Dashboard disconnected (%d remaining)", len(dashboard_connections))


@app.websocket("/ws/tracker")
async def tracker_ws(websocket: WebSocket):
    """WebSocket for the demo app tracker to send interaction events."""
    await websocket.accept()
    logger.info("Tracker connected")

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                event_data = json.loads(raw)
                event = InteractionEvent(**event_data)
                await post_interaction(event)
                await websocket.send_json({"status": "ok"})
            except (json.JSONDecodeError, ValueError) as e:
                await websocket.send_json({"status": "error", "message": str(e)})
    except WebSocketDisconnect:
        logger.info("Tracker disconnected")
    except Exception as e:
        logger.debug("Tracker WS error: %s", e)


# ───────────────────────── Health Check ─────────────────────────


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "dashboardClients": len(dashboard_connections),
        "interactionLogSize": len(interaction_log),
        "activeNodes": len(active_nodes),
        "hasCachedStructure": current_structure is not None,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
