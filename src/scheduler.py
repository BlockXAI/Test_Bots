import asyncio
import logging
from datetime import datetime, timedelta
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from config import SCHEDULE_HOURS, NOTIFY_ON_SUCCESS
from src.runner import run_all_scripts
from src.reporter import build_summary_message
from src.telegram_bot import send_report

logger = logging.getLogger(__name__)
_RUN_LOCK = Lock()


def setup_scheduler(app):
    scheduler = BackgroundScheduler(job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 300})

    def scheduled_run():
        if not _RUN_LOCK.acquire(blocking=False):
            logger.warning("Skipping scheduled test run because another run is still in progress")
            return

        logger.info("Scheduled test run starting...")
        try:
            run_summary = run_all_scripts()

            should_notify = not run_summary["all_passed"] or NOTIFY_ON_SUCCESS
            if should_notify:
                msg = build_summary_message(run_summary)
                try:
                    asyncio.run(send_report(app, msg))
                except Exception:
                    logger.exception("Failed to send scheduled Telegram report")

            status = "PASS" if run_summary["all_passed"] else "FAIL"
            logger.info(f"Scheduled run complete: {status}")
        except Exception:
            logger.exception("Scheduled run crashed before completing")
        finally:
            _RUN_LOCK.release()

    first_run_at = datetime.now() + timedelta(seconds=60)
    scheduler.add_job(
        scheduled_run,
        DateTrigger(run_date=first_run_at),
        id="e2e_startup_run",
        replace_existing=True,
    )
    logger.info(f"Initial test run scheduled at {first_run_at.strftime('%H:%M:%S')} (60s from now)")

    for hour in SCHEDULE_HOURS:
        trigger = CronTrigger(hour=hour, minute=0, timezone="UTC")
        scheduler.add_job(scheduled_run, trigger, id=f"e2e_run_{hour}", replace_existing=True)
        logger.info(f"Scheduled e2e run at {hour:02d}:00 UTC")

    return scheduler
