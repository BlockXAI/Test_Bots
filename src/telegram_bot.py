import asyncio
import logging
import os

from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.constants import ParseMode

from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, SCRIPTS_DIR
from src.runner import run_all_scripts, run_script_by_name, discover_scripts
from src.reporter import build_summary_message, build_single_script_message

logger = logging.getLogger(__name__)


async def send_report(app, message):
    """Send a message to the configured chat. Splits if too long."""
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
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            try:
                await app.bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=chunk,
                )
            except Exception as e2:
                logger.error(f"Fallback send also failed: {e2}")


async def cmd_run_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /run command — runs all scripts."""
    await update.message.reply_text("\u23f3 Running all e2e test scripts...")

    loop = asyncio.get_event_loop()
    run_summary = await loop.run_in_executor(None, run_all_scripts)
    msg = build_summary_message(run_summary)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_run_single(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /test <script_name> — runs one script."""
    if not context.args:
        scripts = discover_scripts()
        names = [os.path.splitext(os.path.basename(s))[0] for s in scripts]
        await update.message.reply_text(
            f"Usage: /test <script_name>\n\nAvailable scripts:\n" + "\n".join(f"  \u2022 `{n}`" for n in names),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    name = context.args[0]
    await update.message.reply_text(f"\u23f3 Running `{name}`...", parse_mode=ParseMode.MARKDOWN)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, run_script_by_name, name)
    if result is None:
        await update.message.reply_text(f"\u274c Script `{name}` not found in scripts/", parse_mode=ParseMode.MARKDOWN)
        return

    msg = build_single_script_message(result)
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /status — lists available scripts."""
    scripts = discover_scripts()
    names = [os.path.splitext(os.path.basename(s))[0] for s in scripts]
    msg = f"\U0001f4cb *Available test scripts* ({len(names)}):\n"
    for n in names:
        msg += f"  \u2022 `{n}`\n"
    msg += f"\nUse /run to run all or /test <name> to run one."
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handler for /help command."""
    msg = (
        "\U0001f916 *E2E Test Bot Commands*\n\n"
        "/run — Run all test scripts\n"
        "/test <name> — Run a specific script\n"
        "/status — List available scripts\n"
        "/help — Show this message\n"
    )
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


def build_application():
    """Build and return the Telegram Application (not started)."""
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in environment")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("run", cmd_run_all))
    app.add_handler(CommandHandler("test", cmd_run_single))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("start", cmd_help))

    return app
