# Trading Journal Telegram Bot

A Telegram bot for private trade record-keeping. Users can add trades, review recent entries, see basic performance statistics, and delete their own records.

## Features
- Add a trade with symbol, Buy/Long or Sell/Short, entry, optional exit, optional P/L and notes
- View the 10 most recent trades
- See totals, open/closed counts, wins, losses, recorded win rate and recorded P/L
- Delete a trade by its ID
- User records are separated by Telegram user ID
- Flask health endpoint for hosting platforms

This is a journaling tool only. It does not provide trading signals, financial advice, or profit guarantees.

## Setup
1. Create a bot with Telegram's @BotFather and copy its token.
2. Install Python 3.11 or newer.
3. Install dependencies: `pip install -r requirements.txt`
4. Set the environment variable `BOT_TOKEN` to your bot token.
5. Run: `python main.py`

Optional environment variables:
- `DATABASE_PATH`: SQLite database path (default: `trades.db`)
- `PORT`: health server port (default: `10000`)
- `LOG_LEVEL`: logging level (default: `INFO`)

## Render deployment
Create a Web Service from this repository. Use:
- Build command: `pip install -r requirements.txt`
- Start command: `python main.py`
- Environment variable: `BOT_TOKEN` = your BotFather token
- Health check path: `/health`

SQLite data on an ephemeral host filesystem may be lost when the service is replaced. Attach a persistent disk and set `DATABASE_PATH` to a file on that disk if you need durable journal records.

## Bot commands
- `/start` — open the menu
- `/add` — record a trade
- `/trades` — list recent trades
- `/stats` — show journal statistics
- `/delete ID` — delete one of your trades
- `/cancel` — cancel an entry in progress
- `/help` — show help
