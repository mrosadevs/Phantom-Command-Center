"""
server.py — FastAPI dashboard backend for Phantom Command Center.

Serves the web dashboard at http://localhost:3000
Provides REST API endpoints for the frontend to consume.

Run with: python src/dashboard/server.py
"""

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.core import memory, router
from src.core.config import CONFIG, ROOT_DIR, SURPRISES_DIR, MEMORY_DIR
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("phantom.dashboard")

app = FastAPI(title="Phantom Command Center", version="1.0.0")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

# Mount static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(exist_ok=True)
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ─────────────────────────────────────────────
# HTML Dashboard (served at /)
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the main dashboard HTML."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        return HTMLResponse(template_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Dashboard template not found</h1>")


# ─────────────────────────────────────────────
# API Endpoints
# ─────────────────────────────────────────────

@app.get("/api/overview")
async def get_overview():
    """System overview stats."""
    from src.utils import lm_studio_client

    lm_online = await lm_studio_client.is_available()
    lm_models = await lm_studio_client.list_models() if lm_online else []

    # Count surprises
    surprises_count = len([d for d in SURPRISES_DIR.iterdir() if d.is_dir()]) if SURPRISES_DIR.exists() else 0

    # Count research reports
    research_dir = MEMORY_DIR / "research"
    research_count = len(list(research_dir.glob("*.md"))) if research_dir.exists() else 0

    # Routing stats
    routing_stats = router.get_recent_routing_stats()

    # Memory items (rough count of lines in about-manuel.md)
    about_content = memory.read_memory("about-manuel.md")
    memory_items = len([l for l in about_content.splitlines() if l.strip().startswith("-")])

    return {
        "services": {
            "lm_studio": {"online": lm_online, "models": lm_models},
            "claude_code": {"online": True, "model": CONFIG["models"]["heavy"]["model"]},
            "groq": {"online": True},
            "discord_bot": {"online": True}
        },
        "stats": {
            "surprises_built": surprises_count,
            "research_reports": research_count,
            "memory_items": memory_items,
        },
        "routing": routing_stats,
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/surprises")
async def get_surprises():
    """List all overnight surprises."""
    surprises = []
    if not SURPRISES_DIR.exists():
        return {"surprises": []}

    for d in sorted(SURPRISES_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        readme = d / "README.md"
        description = ""
        if readme.exists():
            content = readme.read_text(encoding="utf-8")
            # Extract first paragraph
            lines = [l for l in content.splitlines() if l.strip() and not l.startswith("#")]
            description = lines[0][:200] if lines else ""

        surprises.append({
            "name": d.name,
            "path": str(d.relative_to(ROOT_DIR)),
            "description": description,
            "created": datetime.fromtimestamp(d.stat().st_ctime).isoformat(),
            "files": [f.name for f in d.iterdir() if f.is_file()][:10]
        })

    return {"surprises": surprises}


def _next_run_from_cron(cron_expr: str) -> Optional[str]:
    """Compute the next fire time from a cron string without a running scheduler."""
    try:
        parts = cron_expr.strip().split()
        trigger = CronTrigger(
            minute=parts[0], hour=parts[1],
            day=parts[2], month=parts[3], day_of_week=parts[4],
        )
        next_dt = trigger.get_next_fire_time(None, datetime.now())
        if next_dt:
            return next_dt.strftime("%b %d %I:%M %p")
    except Exception:
        pass
    return None


@app.get("/api/schedule")
async def get_schedule():
    """Get scheduled tasks and their next run times (computed from cron expressions)."""
    from src.core.config import load_schedules
    schedules_config = load_schedules()
    tasks = schedules_config.get("tasks", [])

    # Compute next_run from cron for each task — works without a live scheduler
    jobs = []
    for t in tasks:
        jobs.append({
            "id":       t.get("name", ""),
            "name":     t.get("description", t.get("name", "")),
            "next_run": _next_run_from_cron(t["cron"]) if t.get("enabled") and t.get("cron") else None,
            "enabled":  t.get("enabled", True),
        })

    return {
        "jobs": jobs,
        "definitions": tasks,
    }


@app.get("/api/heartbeat")
async def get_heartbeat():
    """Return the last heartbeat state written by the bot."""
    from src.agents.heartbeat import read_heartbeat_state
    state = read_heartbeat_state()
    if not state:
        return {"online": False, "last_heartbeat": None, "uptime": None}

    last = datetime.fromisoformat(state["last_heartbeat"])
    start = datetime.fromisoformat(state["start_time"])
    age_seconds = (datetime.now() - last).total_seconds()
    uptime_seconds = (datetime.now() - start).total_seconds()

    # Bot writes state every 2 minutes — consider dead if nothing in 5 minutes
    is_online = age_seconds < 300

    uptime_hours = int(uptime_seconds // 3600)
    uptime_mins = int((uptime_seconds % 3600) // 60)

    return {
        "online": is_online,
        "last_heartbeat": state["last_heartbeat"],
        "last_heartbeat_ago": f"{int(age_seconds // 60)}m ago" if age_seconds < 3600 else f"{int(age_seconds // 3600)}h ago",
        "uptime": f"{uptime_hours}h {uptime_mins}m",
        "lm_studio_online": state.get("lm_studio_online", False),
        "lm_models": state.get("lm_models", [])
    }


@app.get("/api/research")
async def get_research():
    """Get recent research entries."""
    content = memory.read_memory("research-log.md")
    sections = content.split("##")
    entries = []

    for section in sections[1:]:  # Skip header
        lines = section.strip().splitlines()
        if not lines:
            continue
        title_line = lines[0].strip()
        body = "\n".join(lines[1:]).strip()
        entries.append({
            "title": title_line,
            "summary": body[:400],
            "full": body
        })

    return {"entries": list(reversed(entries))}


@app.get("/api/memory")
async def get_memory():
    """Get all memory files as a structured dict."""
    files = {
        "about_manuel": memory.read_memory("about-manuel.md"),
        "projects": memory.read_memory("projects.md"),
        "skills": memory.read_memory("skills-learned.md"),
        "mcps": memory.read_memory("mcps-installed.md"),
        "research_log": memory.read_memory("research-log.md"),
        "surprises_log": memory.read_memory("surprises-log.md"),
    }
    return files


class MemoryUpdate(BaseModel):
    file: str
    content: str


@app.post("/api/memory")
async def update_memory(update: MemoryUpdate):
    """Update a memory file from the dashboard."""
    allowed_files = {
        "about_manuel": "about-manuel.md",
        "projects": "projects.md",
        "skills": "skills-learned.md",
    }
    if update.file not in allowed_files:
        raise HTTPException(status_code=400, detail="Unknown memory file")
    memory.write_memory(allowed_files[update.file], update.content)
    return {"status": "saved"}


class ChatMessage(BaseModel):
    message: str


@app.post("/api/chat")
async def dashboard_chat(msg: ChatMessage):
    """Handle a chat message from the web dashboard."""
    from src.agents.orchestrator import process_request
    result = await process_request(msg.message, source="dashboard")
    return result


@app.get("/api/config")
async def get_config():
    """Return the current config (without secrets)."""
    safe_config = {k: v for k, v in CONFIG.items() if k != "discord"}
    return safe_config


@app.get("/api/routing-log")
async def get_routing_log(limit: int = 20):
    """Return recent routing decisions."""
    log_file = ROOT_DIR / "memory" / "routing-log.jsonl"
    entries = []
    if log_file.exists():
        lines = log_file.read_text().strip().split("\n")
        for line in lines[-limit:]:
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
    return {"entries": list(reversed(entries))}


if __name__ == "__main__":
    host = CONFIG.get("dashboard", {}).get("host", "0.0.0.0")
    port = CONFIG.get("dashboard", {}).get("port", 3000)
    logger.info(f"Starting Phantom dashboard at http://localhost:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
