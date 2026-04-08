import asyncio
import logging
import sys

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCHEDULE_HOURS
from src.telegram_bot import build_application
from src.scheduler import setup_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("e2e_bot")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill in your values.")
        sys.exit(1)

    if not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_CHAT_ID is not set. Bot will run but scheduled reports won't be sent.")

    logger.info(f"Starting E2E Test Bot")
    logger.info(f"Scheduled runs at UTC hours: {SCHEDULE_HOURS}")

    app = build_application()
    scheduler = setup_scheduler(app)
    scheduler.start()

    logger.info("Bot is live. Listening for commands and running on schedule.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
