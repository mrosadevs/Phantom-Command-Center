"""
scheduler.py — Task scheduler for Phantom Command Center.

Wraps APScheduler to run cron jobs defined in config/schedules.json.
Each job runs a Python script from the scripts/ directory.
"""

import logging
import subprocess
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.config import ROOT_DIR, load_schedules

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


def start():
    """Start the APScheduler."""
    setup_jobs()
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
