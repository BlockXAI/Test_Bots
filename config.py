import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

SCHEDULE_HOURS = [int(h.strip()) for h in os.getenv("SCHEDULE_HOURS", "6,18").split(",")]
TIMEZONE = os.getenv("TIMEZONE", "Asia/Kolkata")

NOTIFY_ON_SUCCESS = os.getenv("NOTIFY_ON_SUCCESS", "true").lower() == "true"

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
REPORTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
DATABASE_URL = os.getenv("DATABASE_URL", "")

WEB_PORT = int(os.getenv("PORT", os.getenv("WEB_PORT", "8080")))
BASE_URL = os.getenv("BASE_URL", f"http://localhost:{WEB_PORT}")
