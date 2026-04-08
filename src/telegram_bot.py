import asyncio
import logging
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCHEDULE_HOURS
from src.reporter import build_single_script_message, build_summary_message
from src.runner import discover_scripts, run_all_scripts, run_script_by_name
from src.storage import list_reports

logger = logging.getLogger(__name__)


async def send_report(app, message):
    if not TELEGRAM_CHAT_ID:
        logger.warning("No TELEGRAM_CHAT_ID configured, skipping send")
        return

    max_len = 4000
    chunks = [message[i:i + max_len] for i in range(0, len(message), max_len)]
    for chunk in chunks:
        try:
            await app.bot.send_message(
                chat_id=TELEGRAM_CHAT_ID,
                text=chunk,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            try:
                await app.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=chunk,
                    disable_web_page_preview=True,
                )
            except Exception as e2:
                logger.error(f"Fallback send also failed: {e2}")


def _available_script_names():
    return [os.path.splitext(os.path.basename(s))[0] for s in discover_scripts()]


def _services_message():
    names = _available_script_names()
    msg = f"🧰 *Tracked services* ({len(names)})\n"
    for name in names:
        msg += f"- `{name}`\n"
    msg += "\nTry `/test <service>` or mention me with `@botname run <service>`."
    return msg


async def _run_all_and_reply(message):
    await message.reply_text("🤖 Chinku is warming up the full product patrol. Give me a moment...")
    loop = asyncio.get_event_loop()
    run_summary = await loop.run_in_executor(None, run_all_scripts)
    msg = build_summary_message(run_summary)
    await message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def _run_single_and_reply(message, name):
    await message.reply_text(f"🧪 Chinku is checking `{name}` right now...", parse_mode=ParseMode.MARKDOWN)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_script_by_name, name)
    if result is None:
        await message.reply_text(f"❌ I couldn't find `{name}` in `scripts/`.", parse_mode=ParseMode.MARKDOWN)
        return
    msg = build_single_script_message(result)
    await message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def cmd_run_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _run_all_and_reply(update.message)


async def cmd_run_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text(_services_message(), parse_mode=ParseMode.MARKDOWN)
        return
    await _run_single_and_reply(update.message, context.args[0])


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = _available_script_names()
    first_run_text = "The first automatic health run happens about 60 seconds after each fresh server start."
    msg = f"📡 *Chinku status*\n\n- Watching *{len(names)}* service(s)\n- {first_run_text}\n- Scheduled UTC slots: `{', '.join(str(x) for x in context.bot_data.get('schedule_hours', []))}`\n"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(_services_message(), parse_mode=ParseMode.MARKDOWN)


async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reports = list_reports(1)
    if not reports:
        await update.message.reply_text("🗂️ No stored reports yet. Let me run one first.")
        return
    latest = reports[0]
    data = latest["data"]
    report_id = latest["id"]
    total = data.get("total_scripts", 0)
    passed = data.get("passed_scripts", 0)
    failed = data.get("failed_scripts", 0)
    msg = f"🗂️ *Latest saved run*\n- Report: `{report_id}`\n- Scripts: *{passed}/{total}* passing\n- Failed scripts: *{failed}*"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = context.bot.username or "your_bot"
    msg = (
        "🤖 *Chinku command desk*\n\n"
        "/run — run every tracked service\n"
        "/test <name> — run one service\n"
        "/services — list all services\n"
        "/status — bot + schedule status\n"
        "/latest — show latest stored run\n"
        "/help — show this guide\n\n"
        f"In the group you can also tag me like `@{username} run all` or `@{username} run joyo_cc`."
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def handle_group_mentions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not message.text:
        return

    username = context.bot.username
    if not username:
        return

    lowered = message.text.lower()
    mention = f"@{username.lower()}"
    if mention not in lowered:
        return

    cleaned = lowered.replace(mention, " ").strip()
    if cleaned in {"", "help"}:
        await cmd_help(update, context)
        return
    if cleaned in {"services", "list services", "show services"}:
        await update.message.reply_text(_services_message(), parse_mode=ParseMode.MARKDOWN)
        return
    if cleaned in {"run", "run all", "check all", "test all"}:
        await _run_all_and_reply(message)
        return
    if cleaned.startswith("run ") or cleaned.startswith("test "):
        service_name = cleaned.split(" ", 1)[1].strip()
        await _run_single_and_reply(message, service_name)
        return
    await message.reply_text("👋 Tag me with `run all`, `run <service>`, or `services` and I'll take it from there.", parse_mode=ParseMode.MARKDOWN)


def build_application():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.bot_data["schedule_hours"] = SCHEDULE_HOURS

    app.add_handler(CommandHandler("run", cmd_run_all))
    app.add_handler(CommandHandler("test", cmd_run_single))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("services", cmd_services))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_group_mentions))

    return app
