"""
scheduler.py — Task scheduler for Phantom Command Center.

Wraps APScheduler to run cron jobs defined in config/schedules.json.
Each job runs a Python script from the scripts/ directory.
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.config import ROOT_DIR, load_schedules

# File where Phantom saves his own dynamically added recurring jobs
_DYNAMIC_JOBS_FILE = ROOT_DIR / "memory" / "dynamic-schedules.json"

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def _run_script(script_path: str):
    """Run a Python script as a subprocess."""
    full_path = ROOT_DIR / script_path
    if not full_path.exists():
        logger.error(f"Script not found: {script_path}")
        return
    logger.info(f"Running scheduled script: {script_path}")
    try:
        result = subprocess.run(
            [sys.executable, str(full_path)],
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour max
        )
        if result.returncode != 0:
            logger.error(f"Script {script_path} failed:\n{result.stderr}")
        else:
            logger.info(f"Script {script_path} completed successfully")
    except subprocess.TimeoutExpired:
        logger.error(f"Script {script_path} timed out after 1 hour")
    except Exception as e:
        logger.error(f"Failed to run {script_path}: {e}")


def setup_jobs():
    """
    Load schedule definitions from config and register all enabled jobs
    with APScheduler.
    """
    schedules = load_schedules()
    for task in schedules.get("tasks", []):
        if not task.get("enabled", True):
            logger.info(f"Skipping disabled task: {task['name']}")
            continue

        cron_expr = task["cron"]
        script = task["script"]
        name = task["name"]

        # Parse cron: "min hour dom mon dow"
        parts = cron_expr.split()
        trigger = CronTrigger(
            minute=parts[0],
            hour=parts[1],
            day=parts[2],
            month=parts[3],
            day_of_week=parts[4]
        )

        scheduler.add_job(
            _run_script,
            trigger=trigger,
            args=[script],
            id=name,
            name=task.get("description", name),
            replace_existing=True
        )
        logger.info(f"Scheduled {name} ({cron_expr}): {task.get('description', '')}")


def _load_dynamic_jobs() -> list:
    """Load persisted dynamic jobs from disk."""
    try:
        if _DYNAMIC_JOBS_FILE.exists():
            return json.loads(_DYNAMIC_JOBS_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not load dynamic schedules: {e}")
    return []


def _save_dynamic_jobs(jobs: list):
    """Persist dynamic jobs to disk."""
    _DYNAMIC_JOBS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _DYNAMIC_JOBS_FILE.write_text(json.dumps(jobs, indent=2), encoding="utf-8")


def _setup_dynamic_jobs():
    """Register all persisted dynamic jobs with APScheduler."""
    for job in _load_dynamic_jobs():
        try:
            _register_dynamic_job(job)
            logger.info(f"Restored dynamic job: {job['name']} ({job['cron']})")
        except Exception as e:
            logger.warning(f"Could not restore dynamic job {job.get('name')}: {e}")


def _register_dynamic_job(job: dict):
    """Register a single dynamic job dict with APScheduler."""
    parts = job["cron"].split()
    trigger = CronTrigger(
        minute=parts[0], hour=parts[1],
        day=parts[2], month=parts[3], day_of_week=parts[4],
    )
    if job.get("type") == "dm":
        # DM-type jobs: send a message via the bot (handled in heartbeat)
        from src.agents.heartbeat import schedule_dm
        scheduler.add_job(
            schedule_dm,
            trigger=trigger,
            args=[job["payload"]],
            id=job["id"],
            name=job["name"],
            replace_existing=True,
        )
    else:
        scheduler.add_job(
            _run_script,
            trigger=trigger,
            args=[job.get("script", "scripts/morning_briefing.py")],
            id=job["id"],
            name=job["name"],
            replace_existing=True,
        )


def add_recurring_job(
    name: str,
    cron: str,
    job_type: str = "dm",
    payload: str = "",
    script: str = "",
) -> str:
    """
    Add a new recurring job dynamically (persisted across restarts).

    Args:
        name:     Human-readable name  (e.g. "gaming_debrief")
        cron:     Standard cron expression (e.g. "0 21 * * *" for 9PM daily)
        job_type: "dm" to DM Offline a message, "script" to run a script
        payload:  The message to send (for dm jobs)
        script:   Script path relative to ROOT_DIR (for script jobs)

    Returns:
        Confirmation string.
    """
    job_id = f"dynamic_{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    job = {
        "id": job_id,
        "name": name,
        "cron": cron,
        "type": job_type,
        "payload": payload,
        "script": script,
        "added": datetime.now().isoformat(),
    }

    # Persist first, then register
    jobs = _load_dynamic_jobs()
    # Remove old job with same name if it exists
    jobs = [j for j in jobs if j["name"] != name]
    jobs.append(job)
    _save_dynamic_jobs(jobs)

    try:
        _register_dynamic_job(job)
        logger.info(f"Dynamic job added: {name} ({cron})")
        return f"✅ Scheduled **{name}** — cron: `{cron}`"
    except Exception as e:
        logger.error(f"Failed to register dynamic job {name}: {e}")
        return f"❌ Job saved but failed to activate: {e}"


def remove_recurring_job(name: str) -> str:
    """Remove a dynamic recurring job by name."""
    jobs = _load_dynamic_jobs()
    matching = [j for j in jobs if j["name"] == name]
    if not matching:
        return f"No dynamic job named '{name}' found."

    for j in matching:
        try:
            scheduler.remove_job(j["id"])
        except Exception:
            pass

    jobs = [j for j in jobs if j["name"] != name]
    _save_dynamic_jobs(jobs)
    return f"✅ Removed scheduled job: **{name}**"


def start():
    """Start the APScheduler."""
    setup_jobs()
    _setup_dynamic_jobs()  # Load Phantom's own scheduled jobs
    scheduler.start()
    logger.info("Scheduler started with all jobs")


def stop():
    """Stop the APScheduler."""
    scheduler.shutdown()
    logger.info("Scheduler stopped")


def add_one_time_job(script: str, run_at, name: str = None):
    """Add a one-time job to run at a specific datetime."""
    from apscheduler.triggers.date import DateTrigger
    scheduler.add_job(
        _run_script,
        trigger=DateTrigger(run_date=run_at),
        args=[script],
        name=name or script
    )
    logger.info(f"One-time job scheduled: {script} at {run_at}")


def get_jobs_status() -> list:
    """Return status of all scheduled jobs for the dashboard."""
    jobs = []
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": next_run.isoformat() if next_run else None,
        })
    return jobs
