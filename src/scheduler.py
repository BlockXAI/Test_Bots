import asyncio
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

from config import SCHEDULE_HOURS, NOTIFY_ON_SUCCESS
from src.runner import run_all_scripts
from src.reporter import build_summary_message
from src.telegram_bot import send_report

logger = logging.getLogger(__name__)


def setup_scheduler(app):
    scheduler = BackgroundScheduler()

    def scheduled_run():
        logger.info("Scheduled test run starting...")
        run_summary = run_all_scripts()

        should_notify = not run_summary["all_passed"] or NOTIFY_ON_SUCCESS
        if should_notify:
            msg = build_summary_message(run_summary)
            asyncio.run(send_report(app, msg))

        status = "PASS" if run_summary["all_passed"] else "FAIL"
        logger.info(f"Scheduled run complete: {status}")

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
