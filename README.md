# E2E Test Bot

Automated monitoring bot that runs your product e2e test scripts on a schedule and reports results via Telegram.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env
```

### Get your Telegram credentials

1. Message [@BotFather](https://t.me/BotFather) on Telegram, send `/newbot`, follow prompts to get your **bot token**
2. Start a chat with your bot, then visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` — your **chat_id** is in the response
3. For group chats, add the bot to the group and check the same URL

## Usage

```bash
python main.py
```

The bot will:
- Start listening for Telegram commands
- Run all scripts in `scripts/` at the configured schedule (default: 06:00 and 18:00 UTC)
- Send reports to your Telegram chat

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/run` | Run all test scripts now |
| `/test <name>` | Run a specific script (without `.py`) |
| `/status` | List all available scripts |
| `/help` | Show commands |

## Adding a new product test

1. Create a `.py` file in `scripts/` (e.g. `scripts/my_product.py`)
2. It must have a `main()` function that returns `0` on success, `1` on failure
3. For detailed Telegram reports, write a `*_results.json` in the script's directory with this shape:

```json
{
  "server": "https://your-api.com",
  "total_tests": 10,
  "passed": 9,
  "failed": 1,
  "pass_rate": "90.0%",
  "total_time_ms": 5000,
  "results": [
    {
      "status": true,
      "endpoint": "/health",
      "method": "GET",
      "detail": "status=200",
      "elapsed_ms": 120
    }
  ]
}
```

The bot auto-discovers and picks up the JSON report for per-endpoint failure details.

## Configuration (.env)

| Variable | Default | Description |
|----------|---------|-------------|
| `TELEGRAM_BOT_TOKEN` | required | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | required | Chat ID to send reports to |
| `SCHEDULE_HOURS` | `6,18` | Comma-separated UTC hours |
| `TIMEZONE` | `Asia/Kolkata` | Display timezone in reports |
| `NOTIFY_ON_SUCCESS` | `true` | Send reports even when all pass |

## Project Structure

```
Test_Bots/
├── scripts/            # Drop e2e test scripts here
│   └── joyo_cc.py      # Example script
├── src/
│   ├── runner.py       # Script discovery and execution
│   ├── reporter.py     # Builds Telegram report messages
│   ├── telegram_bot.py # Telegram bot handlers
│   └── scheduler.py    # APScheduler cron jobs
├── reports/            # Auto-generated run reports (gitignored)
├── config.py           # Central configuration
├── main.py             # Entrypoint
└── requirements.txt
```

## Deployment

Run on any always-on machine (VPS, Railway, etc.):

```bash
python main.py
```

Or with Docker — create a simple `Dockerfile`:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```
