# E2E Test Bot
 
Automated monitoring bot that runs Python e2e scripts on a schedule, posts summaries to Telegram, and hosts full HTML reports for debugging.
 
## Purpose
 
This project is used as an internal reliability layer for live products.
 
It does three jobs:
 
- **Execute e2e test scripts** from the `scripts/` directory (sequentially, one-by-one)
- **Require structured JSON reports** from every script (no fallback generation)
- **Send clean summaries to Telegram** for the internal team
- **Host full detailed reports** on the web dashboard with complete request/response payloads
- **Log all script output** to server logs for real-time debugging
 
This is intended for post-deploy monitoring, scheduled health checks, and quick triage when production services degrade.
 
## High-Level Flow
 
1. A script in `scripts/` runs against a live product
2. The script **must** emit a valid structured JSON report
3. `runner.py` validates the JSON report (fails the script if missing/invalid)
4. Results are stored in `reports/` and optionally in PostgreSQL
5. `reporter.py` formats a Telegram-friendly summary
6. `web.py` exposes the full report at `/report/<report_id>`
7. The bot posts a summary + report link to the Telegram group
 
## Project Structure
 
```
Test_Bots/
├── scripts/               # Product-specific e2e test scripts (executed)
│   ├── growstreams.py     # Example: API e2e with full lifecycle tests
│   ├── nist_rmf.py        # Example: Multi-service RMF compliance suite
│   └── *_impl.py          # Helper modules (NOT executed directly)
├── src/
│   ├── runner.py          # Discovers scripts, runs them, logs output, validates JSON
│   ├── reporter.py        # Builds Telegram summary/debug messages
│   ├── telegram_bot.py    # Telegram command handlers
│   ├── scheduler.py       # Scheduled execution (startup + cron, non-overlapping)
│   └── web.py             # FastAPI dashboard with request/response payloads
├── reports/               # Saved JSON run reports
├── config.py              # Central env/config loading
├── main.py                # Starts dashboard + bot + scheduler
├── railway.json           # Railway deployment config
├── Dockerfile             # Container build for Railway
├── requirements.txt
├── .env.example
└── README.md
```
 
## Environment Variables
 
Copy the example file first:
 
```bash
cp .env.example .env
```
 
Then fill in the required values.
 
| Variable | Required | Example | Purpose |
|----------|----------|---------|---------|
| `TELEGRAM_BOT_TOKEN` | Yes | `123456:ABC...` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Yes | `-5296600103` | Numeric Telegram group or DM chat ID |
| `SCHEDULE_HOURS` | No | `6,18` | UTC hours when scheduled runs should happen |
| `TIMEZONE` | No | `Asia/Kolkata` | Display timezone in reports |
| `NOTIFY_ON_SUCCESS` | No | `true` | Whether success reports should also be sent |
| `WEB_PORT` | No | `8080` | Local web dashboard port |
| `BASE_URL` | Yes in production | `https://chinku-production.up.railway.app` | Public base URL used in Telegram report links |
| `DATABASE_URL` | Recommended in production | `postgresql://...` | PostgreSQL storage for durable test reports across redeploys |
 
## Getting Telegram Credentials
 
### Bot Token
 
1. Open [@BotFather](https://t.me/BotFather)
2. Create a bot using `/newbot`
3. Copy the token into `.env`
 
### Chat ID
 
1. Add the bot to the Telegram group
2. Send at least one message in the group
3. Call:
 
```bash
curl "https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates"
```
 
4. Use the numeric `chat.id`
 
Notes:
 
- **Private chats** usually have a positive numeric ID
- **Groups** usually have a negative numeric ID
- **Do not use usernames** as `TELEGRAM_CHAT_ID`
 
## Local Development
 
Install dependencies:
 
```bash
pip install -r requirements.txt
```
 
Start the app:
 
```bash
python main.py
```
 
Once started:
 
- **Bot polling** is active for Telegram commands
- **Dashboard** is available locally at `http://localhost:8080`
- **Initial run** is scheduled for 60 seconds after startup
- **Recurring runs** happen based on `SCHEDULE_HOURS`
- **Report storage** is written to PostgreSQL when `DATABASE_URL` is configured
 
## Telegram Commands
 
| Command | Description |
|---------|-------------|
| `/run` | Run all scripts immediately |
| `/test <name>` | Run a specific script from `scripts/` |
| `/services` | List all tracked services/scripts |
| `/status` | Show discovered scripts |
| `/latest` | Show the latest stored report snapshot |
| `/help` | Show usage help |
 
In groups, users can also trigger runs by tagging the bot:
 
```
@Chinkiai_bot run all
@Chinkiai_bot run joyo_cc
@Chinkiai_bot services
```
 
## How to Add a New Product Test
 
Add a new Python file inside `scripts/`.
 
Example:
 
```
scripts/my_product.py
```
 
Requirements for every script:
 
- **Must be executable with Python directly**
- **Must return exit code `0` on success**
- **Must return non-zero on failure**
- **Must write a valid JSON report file** (`<script_name>_results.json`) — the runner will fail the script if this is missing or malformed
- **Should include request/response payloads** for full debugging in the dashboard
 
Recommended structure:
 
```python
scripts/
├── my_product.py              # Entrypoint (thin wrapper)
└── my_product_v3_impl.py       # Implementation (helper, not executed)
```

**Entrypoint pattern** (keeps `scripts/` clean):
```python
#!/usr/bin/env python3
from my_product_v3_impl import main as run_impl
import sys
if __name__ == "__main__":
    sys.exit(run_impl())
```

**Implementation structure**:
- **[config]** base URL, constants, feature flags
- **[helpers]** request wrapper that captures request/response/headers/timing
- **[tests]** endpoint-level test functions
- **[report builder]** produces bot-native JSON with all required fields
- **[main]** orchestrates execution, writes JSON report, returns exit code

**Note**: Files ending in `_impl.py` are automatically excluded from script discovery.
 
## JSON Report Contract (Required)

Every script **must** emit a valid JSON report. The runner will reject scripts that don't produce one.

**Required report file**: `<script_name>_results.json` in the same directory as the script.

**Required output shape**:
 
```json
{
  "server": "https://your-api.com",
  "timestamp": "2026-04-09T03:40:00",
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
      "detail": "status=200 body={...}",
      "elapsed_ms": 120
    },
    {
      "status": false,
      "endpoint": "/login",
      "method": "POST",
      "detail": "status=500 internal error",
      "elapsed_ms": 310
    }
  ]
}
```
 
Optional but recommended keys:

- **`request`** — full request payload {url, headers, body}
- **`response`** — full response body (JSON or string)
- **`response_headers`** — response headers dict
- **`traces`** — array of all API calls made during a multi-step test
- **`is_known_bug`** — boolean flag for server-side issues (won't count as failure)
- **`section`** — logical grouping (e.g., "Health", "Tokens", "Streams")
- **`tx_hash`** — for blockchain/NFT flows
- **`test_user`** — when scripts create temporary users
- **service-specific IDs** — that help debugging after a failure
 
## Report Storage and Debugging
 
Every run is persisted in `reports/` as a JSON file:
 
```
reports/run_YYYYMMDD_HHMMSS.json
```
 
These files are used by the web dashboard.
 
If `DATABASE_URL` is configured, the same run summary is also stored in PostgreSQL so reports survive Railway restarts and fresh deploys.
 
Useful URLs:
 
- **Dashboard home**: `/`
- **Healthcheck**: `/health`
- **Single report**: `/report/<report_id>`
 
In production, these become:
 
- `https://your-app.up.railway.app/`
- `https://your-app.up.railway.app/health`
- `https://your-app.up.railway.app/report/run_20260409_034400`
 
## Railway Deployment Guide
 
This project is set up to deploy on Railway using:
 
- `Dockerfile`
- `railway.json`
 
### First-time setup
 
Link the project:
 
```bash
railway link
```
 
Create a domain:
 
```bash
railway domain
```
 
### Required Railway variables
 
Add these in Railway project settings:
 
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `SCHEDULE_HOURS`
- `TIMEZONE`
- `NOTIFY_ON_SUCCESS`
- `BASE_URL`
- `DATABASE_URL`
 
Recommended `BASE_URL` value:
 
```
https://chinku-production.up.railway.app
```
 
Railway automatically injects `PORT`, which the app already supports.
 
### Deploy
 
```bash
railway up
```
 
### Post-deploy checks
 
Check these immediately after deploy:
 
- **[health]** `https://your-domain/health`
- **[dashboard]** `https://your-domain/`
- **[telegram]** bot responds to `/status`
- **[run trigger]** first automatic run should happen about 60 seconds after startup
 
## Maintenance Guide
 
When the team updates this repo, use this checklist.
 
### Safe changes
 
- Adding new scripts in `scripts/`
- Improving Telegram message formatting
- Improving HTML dashboard UI
- Adding extra fields to the JSON report
- Adjusting schedule hours
 
### High-risk changes
 
- Changing `main.py` startup flow
- Changing scheduler implementation
- Modifying how scripts are discovered or executed
- Changing the JSON contract expected by `reporter.py` or `web.py`
- Changing process model for Railway
 
### Before merging changes
 
- **[run local]** start `python main.py`
- **[test dashboard]** verify `/` and `/health`
- **[test telegram]** use `/status` and `/test <script>`
- **[check report]** verify report link opens and renders correctly
- **[check failure formatting]** ensure failed endpoints remain readable in Telegram
 
## Common Failure Modes
 
### Bot starts but no Telegram messages arrive
 
Check:
 
- `TELEGRAM_BOT_TOKEN` is valid
- `TELEGRAM_CHAT_ID` is numeric and correct
- the bot has been added to the group
- the group has sent at least one message to generate updates
 
### Railway deploy succeeds but healthcheck fails
 
Check:
 
- app is binding to `PORT`
- `main.py` is starting successfully
- `/health` returns HTTP 200
- no startup crash in Railway logs
 
### Reports show little detail
 
Cause:
 
- script is returning exit code only, without writing structured JSON
 
Fix:
 
- ensure script writes a report file with `results[]` entries
 
### Telegram shows endpoint failures but no report page data
 
Check:
 
- `BASE_URL` is set correctly in production
- report files are being saved in `reports/`
- report links match the live deployed domain
 
### Script works locally but fails on Railway
 
Check:
 
- environment-specific URLs
- missing env vars
- network timeouts
- dependency versions
- file path assumptions
- generated temp files

Also check **server logs** — the runner now streams script output:
```
2026-04-09 05:01:12 [INFO] e2e_bot.runner: Starting script: growstreams
2026-04-09 05:01:13 [INFO] e2e_bot.runner: [growstreams][stdout] ✅ [PASS] GET /health
2026-04-09 05:01:14 [WARNING] e2e_bot.runner: [growstreams][stderr] rate limit hit
```
 
## Recommendations for New Scripts
 
To keep reports consistent across all products:
 
- **[name scripts clearly]** use product-style names like `growstreams.py`, `nist_rmf.py`
- **[use the helper module pattern]** put implementation in `*_impl.py`, keep entrypoint thin
- **[track timing]** include `elapsed_ms` for every endpoint
- **[capture full payloads]** include request/response/headers for dashboard debugging
- **[log enough detail]** include status code, key response fields, and useful IDs
- **[avoid secrets]** never dump tokens or credentials in details or logs
- **[clean test data]** if a script creates entities, use time-based IDs
- **[be deterministic]** avoid flaky behavior where possible
- **[emit valid JSON]** the runner will reject your script if the report is missing
 
## Recommended Next Improvements
 
These have been implemented:

- ✅ **[structured reports required]** scripts must emit valid JSON
- ✅ **[full payload visibility]** request/response/headers shown in dashboard
- ✅ **[server-side logging]** all script output piped to application logs
- ✅ **[non-overlapping runs]** scheduler prevents concurrent execution
- ✅ **[known bug tracking]** `is_known_bug` flag for server-side issues

Good future upgrades:

- **[trend comparison]** compare against previous run
- **[latency alerts]** mark endpoints that are slow even if they pass
- **[deployment metadata]** attach commit SHA, deploy time, and environment
- **[ownership mapping]** map scripts to product owners
- **[severity routing]** send major failures to the group, minor ones to admin-only channels
 
## Quick Commands Reference
 
```bash
pip install -r requirements.txt
cp .env.example .env
python main.py
railway link
railway domain
railway up
```
 
## Maintainer Notes
 
- The bot is intended to feel human-readable and operationally useful
- Keep Telegram messages concise, but make the report pages rich
- Prefer structured JSON outputs from scripts over plain console logs
- If you change the report shape, update both `reporter.py` and `web.py`
