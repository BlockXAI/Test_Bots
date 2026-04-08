import asyncio
import logging
import sys
import threading

import uvicorn

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCHEDULE_HOURS, WEB_PORT, BASE_URL
from src.telegram_bot import build_application
from src.scheduler import setup_scheduler
from src.storage import init_db
from src.web import app as web_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("e2e_bot")


def run_web_server():
    uvicorn.run(web_app, host="0.0.0.0", port=WEB_PORT, log_level="warning")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID is not set. Bot will run but scheduled reports won't be sent.")

    logger.info(f"Starting E2E Test Bot")
    logger.info(f"Dashboard: {BASE_URL}")
    logger.info(f"Scheduled runs at UTC hours: {SCHEDULE_HOURS}")
    init_db()

    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()
    logger.info(f"Web dashboard running on port {WEB_PORT}")

    tg_app = build_application()
    scheduler = setup_scheduler(tg_app)
    scheduler.start()

    logger.info("Bot is live. Listening for commands and running on schedule.")
    tg_app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
