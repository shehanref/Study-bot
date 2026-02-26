import os
import sqlite3
import logging
import threading
from datetime import datetime, time, timedelta
import pytz
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- FLASK SERVER (For Render) ---
server = Flask('')
@server.route('/')
def home(): return "Study Bot Pro V4 is Active!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    server.run(host='0.0.0.0', port=port)

# --- CONFIG ---
TOKEN = os.getenv('BOT_TOKEN')
TZ = pytz.timezone('Asia/Dhaka')
DB_NAME = 'study_ultra.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (chat_id TEXT, user_id INTEGER, name TEXT, points INTEGER, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stats 
                 (chat_id TEXT, user_id INTEGER, name TEXT, username TEXT, streak INTEGER, 
                 weekly_record TEXT, PRIMARY KEY (chat_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks 
                 (chat_id TEXT PRIMARY KEY, task_list TEXT, set_at DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS progress 
                 (chat_id TEXT, user_id INTEGER, task_index INTEGER, 
                 PRIMARY KEY (chat_id, user_id, task_index))''')
    conn.commit()
    conn.close()

def get_db(): return sqlite3.connect(DB_NAME)

# --- HELPERS ---
def get_progress_bar(percent):
    done = int(percent / 10)
    return "🟢" * done + "⚪" * (10 - done)

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👑 **STUDY TRACKER PRO V4** 👑\n\n"
        "📝 `/settask` - Task set kora\n"
        "🎯 `/task` - Mission check-list\n"
        "📊 `/today`, `/yesterday`, `/week`, `/month` - Leaderboards\n"
        "👤 `/me` - Nijer status\n"
        "🔍 `/info @username` - Onner status check\n"
        "📜 `/amolnama` - Group progress bar\n"
        "💾 `/backup` - DB Backup"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("❌ Use: `/settask task1, task2`")
        return
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT set_at FROM tasks WHERE chat_id=?", (chat_id,))
    if c.fetchone():
        await update.message.reply_text("⚠️ Task already set! Reset hobe rat 12-tay.")
    else:
        task_str = ' '.join(context.args)
        c.execute("INSERT INTO tasks VALUES (?, ?, ?)", (chat_id, task_str, datetime.now(TZ)))
        conn.commit()
        await update.message.reply_text(f"✅ **Mission Locked!**\n📋 {task_str}")
    conn.close()

async def task_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id); user_id = update.effective_user.id
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT task_list FROM tasks WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("🚫 No tasks set for today!"); return
    tasks = [t.strip() for t in row[0].split(',')]
    keyboard = []
    for i, t in enumerate(tasks):
        c.execute("SELECT 1 FROM progress WHERE chat_id=? AND user_id=? AND task_index=?", (chat_id, user_id, i))
        icon = "✅" if c.fetchone() else "⬜"
        keyboard.append([InlineKeyboardButton(f"{icon} {t}", callback_data=f"p_{i}")])
    await update.message.reply_text(f"👋 {update.effective_user.first_name}, ajker mission:", reply_markup=InlineKeyboardMarkup(keyboard))
    conn.close()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; chat_id = str(query.message.chat_id); user = query.from_user
    if query.data.startswith("p_"):
        idx = int(query.data.split("_")[1])
        conn = get_db(); c = conn.cursor()
        try:
            c.execute("INSERT INTO progress VALUES (?, ?, ?)", (chat_id, user.id, idx))
            c.execute("INSERT OR REPLACE INTO stats (chat_id, user_id, name, username, streak, weekly_record) VALUES (?, ?, ?, ?, COALESCE((SELECT streak FROM stats WHERE user_id=?), 0), COALESCE((SELECT weekly_record FROM stats WHERE user_id=?), '⬜⬜⬜⬜⬜⬜⬜'))", 
                      (chat_id, user.id, user.first_name, user.username, user.id, user.id))
            c.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)", (chat_id, user.id, user.first_name, 2, datetime.now(TZ)))
            conn.commit()
            await query.answer("+2 Points!")
            await query.message.delete()
            await task_menu(update, context)
        except sqlite3.IntegrityError:
            await query.answer("Already done!", show_alert=True)
        conn.close()

async def get_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    cmd = update.message.text.split('@')[0].lower()
    conn = get_db(); c = conn.cursor(); now = datetime.now(TZ)
    
    if "today" in cmd: start_date = now.replace(hour=0, minute=0, second=0, microsecond=0); title = "☀️ Today"
    elif "yesterday" in cmd:
        start_date = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        title = "⏳ Yesterday"
    elif "week" in cmd: start_date = now - timedelta(days=7); title = "📅 Weekly"
    elif "month" in cmd: start_date = now - timedelta(days=30); title = "🗓 Monthly"
    else: start_date = datetime(2024, 1, 1); title = "🏆 All-Time"

    if "yesterday" in cmd:
        c.execute("SELECT name, SUM(points) as s FROM logs WHERE chat_id=? AND timestamp BETWEEN ? AND ? GROUP BY user_id ORDER BY s DESC", (chat_id, start_date, end_date))
    else:
        c.execute("SELECT name, SUM(points) as s FROM logs WHERE chat_id=? AND timestamp >= ? GROUP BY user_id ORDER BY s DESC", (chat_id, start_date))
    
    rows = c.fetchall(); conn.close()
    msg = f"📊 **{title} Leaderboard**\n\n"
    if not rows: msg += "No data found."
    else:
        for i, r in enumerate(rows, 1):
            medal = "🥇" if i==1 else "🥈" if i==2 else "🥉" if i==3 else "🔹"
            msg += f"{medal} {r[0]} — `{r[1]} pts`\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

async def info_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    target_user = None
    
    if context.args: # /info @username case
        username = context.args[0].replace('@', '')
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT user_id, name, streak, weekly_record FROM stats WHERE chat_id=? AND username=?", (chat_id, username))
        target_user = c.fetchone()
        conn.close()
    else: # /me case
        user_id = update.effective_user.id
        conn = get_db(); c = conn.cursor()
        c.execute("SELECT user_id, name, streak, weekly_record FROM stats WHERE chat_id=? AND user_id=?", (chat_id, user_id))
        target_user = c.fetchone()
        conn.close()

    if not target_user:
        await update.message.reply_text("❌ User khunje paoa jayni! Bot-e active thaka proyojon.")
        return

    uid, name, streak, grid = target_user
    crowns = "👑" * (streak // 7)
    msg = (f"👤 **User:** {name}\n"
           f"🔥 **Current Streak:** {streak} days\n"
           f"🏆 **Badges:** {crowns or 'Beginner'}\n"
           f"📅 **Weekly Grid:** {grid}")
    await update.message.reply_text(msg, parse_mode='Markdown')

async def amolnama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id); conn = get_db(); c = conn.cursor()
    c.execute("SELECT task_list FROM tasks WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    if not row: await update.message.reply_text("No tasks today."); return
    tasks = [t.strip() for t in row[0].split(',')]
    c.execute("SELECT DISTINCT user_id, name FROM logs WHERE chat_id=? AND timestamp >= ?", (chat_id, datetime.now(TZ).replace(hour=0, minute=0, second=0)))
    users = c.fetchall()
    msg = "📜 **Today's Progress**\n\n"
    for uid, name in users:
        c.execute("SELECT COUNT(*) FROM progress WHERE chat_id=? AND user_id=?", (chat_id, uid))
        done = c.fetchone()[0]; percent = (done/len(tasks))*100
        msg += f"👤 {name}\n{get_progress_bar(percent)} {int(percent)}%\n"
    await update.message.reply_text(msg, parse_mode='Markdown'); conn.close()

async def backup_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(DB_NAME):
        await update.message.reply_document(document=open(DB_NAME, 'rb'), caption="📂 DB Backup")
    else: await update.message.reply_text("DB not found.")

async def midnight_handler(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT chat_id, task_list FROM tasks")
    for chat_id, task_list in c.fetchall():
        tasks = [t.strip() for t in task_list.split(',')]
        c.execute("SELECT DISTINCT user_id, name FROM stats WHERE chat_id=?", (chat_id,))
        for uid, name in c.fetchall():
            c.execute("SELECT COUNT(*) FROM progress WHERE chat_id=? AND user_id=?", (chat_id, uid))
            done = c.fetchone()[0]
            # Penalty
            pen = -5 if done == 0 else -(len(tasks)-done) if done < len(tasks) else 0
            if pen: c.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)", (chat_id, uid, name, pen, datetime.now(TZ)))
            # Streak
            c.execute("SELECT streak, weekly_record FROM stats WHERE chat_id=? AND user_id=?", (chat_id, uid))
            s_row = c.fetchone(); curr_s = s_row[0]; curr_g = s_row[1]
            if done == len(tasks): new_s = curr_s + 1; new_g = (curr_g + "✅")[-7:]
            else: new_s = 0; new_g = (curr_g + "❌")[-7:]
            c.execute("UPDATE stats SET streak=?, weekly_record=? WHERE chat_id=? AND user_id=?", (new_s, new_g, chat_id, uid))
        await context.bot.send_message(chat_id=chat_id, text="🕛 **Midnight Reset!** Set new tasks: `/settask`")
    c.execute("DELETE FROM tasks"); c.execute("DELETE FROM progress"); conn.commit(); conn.close()

async def reminder_handler(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db(); c = conn.cursor(); c.execute("SELECT chat_id FROM tasks")
    task_chats = [r[0] for r in c.fetchall()]
    if not task_chats:
        pass # Handle group list if needed
    else:
        for chat in task_chats:
            await context.bot.send_message(chat_id=chat, text="🔔 6-Hour Reminder! Finish your tasks.")
    conn.close()

if __name__ == '__main__':
    init_db(); threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    jq = app.job_queue
    jq.run_daily(midnight_handler, time=time(hour=0, minute=0, tzinfo=TZ))
    jq.run_repeating(reminder_handler, interval=21600, first=3600)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settask", set_task))
    app.add_handler(CommandHandler("task", task_menu))
    app.add_handler(CommandHandler(["today", "yesterday", "week", "month", "leaderboard"], get_stats))
    app.add_handler(CommandHandler("me", info_status))
    app.add_handler(CommandHandler("info", info_status))
    app.add_handler(CommandHandler("amolnama", amolnama))
    app.add_handler(CommandHandler("backup", backup_db))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()
