import asyncio
import logging, os, sqlite3
from datetime import datetime, timezone
from threading import Thread
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ConversationHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = os.getenv("DATABASE_PATH", "trades.db")
PORT = int(os.getenv("PORT", "10000"))
SYMBOL, SIDE, ENTRY, EXIT, PNL, NOTES = range(6)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("trading-journal")
web = Flask(__name__)

@web.get("/")
@web.get("/health")
def health():
    return jsonify(status="ok", service="Trading Journal Telegram Bot")

def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

def init_db():
    with db() as con:
        con.execute("""CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL, side TEXT NOT NULL, entry REAL NOT NULL,
            exit REAL, pnl REAL, notes TEXT DEFAULT '', status TEXT NOT NULL,
            created_at TEXT NOT NULL)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id,id DESC)")

def keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add trade", callback_data="add"),
         InlineKeyboardButton("📒 My trades", callback_data="trades")],
        [InlineKeyboardButton("📊 Statistics", callback_data="stats"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help")]
    ])

def fmt(value):
    return "—" if value is None else f"{value:,.2f}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = ("📊 *Welcome to Trading Journal!*\n\n"
            "Record your trades, review results and keep your trading history organized.\n\n"
            "Choose an option below to get started. Your journal is private to your Telegram account.")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard())
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard())

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "*How to use*\n• Add trade — record a position\n• My trades — see your latest records\n"
        "• Statistics — review your recorded results\n• /delete ID — remove one of your trades\n"
        "• /cancel — stop entering a trade\n\nThis bot records information you enter. It does not provide trading signals or investment advice.",
        parse_mode="Markdown", reply_markup=keyboard())

async def begin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["trade"] = {}
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.reply_text("Enter the market or symbol (e.g. EURUSD, XAUUSD or BTCUSDT):")
    else:
        await update.effective_message.reply_text("➕ *New trade*\n\nEnter the market or symbol (e.g. EURUSD, XAUUSD or BTCUSDT):", parse_mode="Markdown")
    return SYMBOL

async def symbol_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    value = update.message.text.strip().upper()
    if not value or len(value) > 24:
        await update.message.reply_text("Enter a valid symbol (up to 24 characters).")
        return SYMBOL
    context.user_data["trade"]["symbol"] = value
    await update.message.reply_text("Choose direction:", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("🟢 Buy / Long", callback_data="side:BUY"),
        InlineKeyboardButton("🔴 Sell / Short", callback_data="side:SELL")]]))
    return SIDE

async def side_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    context.user_data["trade"]["side"] = q.data.split(":")[1]
    await q.edit_message_text("Enter entry price (positive number, e.g. 1.08450):")
    return ENTRY

async def entry_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        n = float(update.message.text.strip().replace(",", ""))
        if n <= 0: raise ValueError
    except ValueError:
        await update.message.reply_text("Please enter a positive number.")
        return ENTRY
    context.user_data["trade"]["entry"] = n
    await update.message.reply_text("Enter exit price, or type open if the trade is still open:")
    return EXIT

async def exit_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lower()
    if raw == "open":
        context.user_data["trade"].update(exit=None, status="OPEN")
    else:
        try:
            n = float(raw.replace(",", ""))
            if n <= 0: raise ValueError
        except ValueError:
            await update.message.reply_text("Enter a positive exit price, or type open.")
            return EXIT
        context.user_data["trade"].update(exit=n, status="CLOSED")
    await update.message.reply_text("Enter profit/loss amount (e.g. 25.50 or -10), or type skip:")
    return PNL

async def pnl_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().lower().replace(",", "")
    if raw == "skip":
        context.user_data["trade"]["pnl"] = None
    else:
        try: context.user_data["trade"]["pnl"] = float(raw)
        except ValueError:
            await update.message.reply_text("Enter a number or type skip.")
            return PNL
    await update.message.reply_text("Add an optional note, or type skip:")
    return NOTES

async def notes_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = context.user_data.pop("trade", {})
    note = update.message.text.strip()
    if note.lower() == "skip": note = ""
    with db() as con:
        cur = con.execute("""INSERT INTO trades
            (user_id,symbol,side,entry,exit,pnl,notes,status,created_at)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (update.effective_user.id,t["symbol"],t["side"],t["entry"],t.get("exit"),
             t.get("pnl"),note[:1000],t["status"],datetime.now(timezone.utc).isoformat()))
        trade_id = cur.lastrowid
    await update.message.reply_text(
        f"✅ *Trade saved!*\nID: #{trade_id}\nSymbol: *{t['symbol']}*\nDirection: *{t['side']}*"
        f"\nEntry: {fmt(t['entry'])}\nExit: {fmt(t.get('exit')) if t.get('exit') is not None else 'Open'}"
        f"\nP/L: {fmt(t.get('pnl'))}\nStatus: *{t['status']}*",
        parse_mode="Markdown", reply_markup=keyboard())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("trade", None)
    await update.effective_message.reply_text("Trade entry cancelled.")
    return ConversationHandler.END

async def trades(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as con:
        rows = con.execute("SELECT * FROM trades WHERE user_id=? ORDER BY id DESC LIMIT 10",
                           (update.effective_user.id,)).fetchall()
    if not rows:
        text = "📒 *Your journal is empty.*\nTap Add trade to record your first trade."
    else:
        lines = ["📒 *Your 10 most recent trades*"]
        for r in rows:
            exit_value = fmt(r["exit"]) if r["exit"] is not None else "Open"
            lines.append(f"\n*#{r['id']} {r['symbol']} — {r['side']}*\nEntry: {fmt(r['entry'])} | Exit: {exit_value}\nStatus: {r['status']} | P/L: {fmt(r['pnl'])}")
        lines.append("\nUse /delete ID to remove a record.")
        text = "\n".join(lines)
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard())
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard())

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    with db() as con:
        r = con.execute("""SELECT COUNT(*) total,
          SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) opened,
          SUM(CASE WHEN status='CLOSED' THEN 1 ELSE 0 END) closed,
          SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) wins,
          SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END) losses,
          SUM(COALESCE(pnl,0)) total_pnl FROM trades WHERE user_id=?""",
          (update.effective_user.id,)).fetchone()
    wins, losses = r["wins"] or 0, r["losses"] or 0
    decided = wins + losses
    rate = wins / decided * 100 if decided else 0
    text = ("📊 *Your trading statistics*\n\n"
      f"Total records: *{r['total'] or 0}*\nOpen trades: *{r['opened'] or 0}*\n"
      f"Closed trades: *{r['closed'] or 0}*\nRecorded wins: *{wins}*\n"
      f"Recorded losses: *{losses}*\nWin rate (trades with positive/negative P/L): *{rate:.1f}%*\n"
      f"Recorded total P/L: *{fmt(r['total_pnl'] or 0)}*\n\n"
      "_Based only on the P/L values you enter. This is a record-keeping tool, not a forecast._")
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard())
    else:
        await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard())

async def delete_trade(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1 or not context.args[0].isdigit():
        await update.message.reply_text("Usage: /delete ID")
        return
    with db() as con:
        cur = con.execute("DELETE FROM trades WHERE id=? AND user_id=?",
                          (int(context.args[0]), update.effective_user.id))
    await update.message.reply_text("🗑 Trade deleted." if cur.rowcount else "Trade not found in your journal.")

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.data == "trades": await trades(update, context)
    elif q.data == "stats": await stats(update, context)
    elif q.data == "help":
        await q.answer()
        await q.edit_message_text("Add trades, review your journal and check your recorded statistics. Use /cancel during entry or /delete ID to remove a trade.", reply_markup=keyboard())

def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN is missing. Add your Telegram bot token as an environment variable.")
    init_db()
    app = Application.builder().token(TOKEN).build()
    conversation = ConversationHandler(
        entry_points=[CommandHandler("add", begin_add), CallbackQueryHandler(begin_add, pattern="^add$")],
        states={
            SYMBOL: [MessageHandler(filters.TEXT & ~filters.COMMAND, symbol_step)],
            SIDE: [CallbackQueryHandler(side_step, pattern="^side:(BUY|SELL)$")],
            ENTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, entry_step)],
            EXIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, exit_step)],
            PNL: [MessageHandler(filters.TEXT & ~filters.COMMAND, pnl_step)],
            NOTES: [MessageHandler(filters.TEXT & ~filters.COMMAND, notes_step)]
        },
        fallbacks=[CommandHandler("cancel", cancel)], allow_reentry=True)
    app.add_handler(conversation)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("trades", trades))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("delete", delete_trade))
    app.add_handler(CallbackQueryHandler(button_router, pattern="^(trades|stats|help)$"))
    Thread(target=lambda: web.run(host="0.0.0.0", port=PORT, use_reloader=False), daemon=True).start()
    log.info("Trading Journal bot is running")
    # Python 3.14 no longer creates the main-thread event loop implicitly.
    # Create and install one before python-telegram-bot's run_polling().
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        if not loop.is_closed():
            loop.close()

if __name__ == "__main__":
    main()
