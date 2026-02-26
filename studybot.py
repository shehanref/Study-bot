import os
import sqlite3
import logging
import threading
from datetime import datetime, time
import pytz
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- FLASK WEB SERVER (For Render Free Tier) ---
server = Flask('')

@server.route('/')
def home():
    return "Study Bot is Online!"

def run_flask():
    # Render সাধারণত ৮০০০ বা ১০০০০ পোর্টে চলে, তাই ০.০.০.০ ইন্টারফেস ব্যবহার করা হয়েছে
    port = int(os.environ.get('PORT', 8080))
    server.run(host='0.0.0.0', port=port)

# --- BOT LOGIC ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
TZ = pytz.timezone('Asia/Dhaka')

def init_db():
    conn = sqlite3.connect('study_bot.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
                 (chat_id TEXT, user_id INTEGER, name TEXT, points INTEGER, 
                 PRIMARY KEY (chat_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks 
                 (chat_id TEXT PRIMARY KEY, task_list TEXT, set_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress 
                 (chat_id TEXT, user_id INTEGER, task_index INTEGER, 
                 PRIMARY KEY (chat_id, user_id, task_index))''')
    c.execute('''CREATE TABLE IF NOT EXISTS votes 
                 (chat_id TEXT, user_id TEXT, PRIMARY KEY (chat_id, user_id))''')
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect('study_bot.db')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Advanced Study Tracker Bot (Free Tier)**\n\n"
        "• `/settask t1, t2...` : টাস্ক সেট করুন\n"
        "• `/task` : টাস্ক লিস্ট ও বাটন\n"
        "• `/changetask` : রিসেট ভোট (২ জন)\n"
        "• `/leaderboard` : র‍্যাঙ্কিং\n"
        "• `/amolnama` : আজকের রিপোর্ট",
        parse_mode='Markdown'
    )

async def set_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("ব্যবহার: `/settask পড়া১, পড়া২`")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT set_at FROM tasks WHERE chat_id = ?", (chat_id,))
    if c.fetchone():
        await update.message.reply_text("❌ টাস্ক অলরেডি সেট। বদলাতে `/changetask` দিন।")
        conn.close()
        return

    task_text = ' '.join(context.args)
    c.execute("INSERT OR REPLACE INTO tasks (chat_id, task_list, set_at) VALUES (?, ?, ?)", 
              (chat_id, task_text, datetime.now(TZ).isoformat()))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ টাস্ক সেট হয়েছে!\n📋 {task_text}")

async def show_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT task_list FROM tasks WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    
    if not row:
        await update.message.reply_text("আজকের কোনো টাস্ক নেই!")
        return

    tasks = [t.strip() for t in row[0].split(',')]
    keyboard = []
    for i, t in enumerate(tasks):
        c.execute("SELECT 1 FROM user_progress WHERE chat_id=? AND user_id=? AND task_index=?", (chat_id, user_id, i))
        status = "✅" if c.fetchone() else "⬜"
        keyboard.append([InlineKeyboardButton(f"{status} {t}", callback_data=f"done_{i}")])
    
    await update.message.reply_text("📖 আপনার করা টাস্কগুলো সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))
    conn.close()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = query.from_user
    data = query.data

    conn = get_db()
    c = conn.cursor()
    if data.startswith("done_"):
        idx = int(data.split("_")[1])
        try:
            c.execute("INSERT INTO user_progress (chat_id, user_id, task_index) VALUES (?, ?, ?)", (chat_id, user.id, idx))
            c.execute("INSERT OR IGNORE INTO scores (chat_id, user_id, name, points) VALUES (?, ?, ?, 0)", (chat_id, user.id, user.first_name))
            c.execute("UPDATE scores SET points = points + 2 WHERE chat_id=? AND user_id=?", (chat_id, user.id))
            await query.answer(f"সাবাস {user.first_name}! +২ পয়েন্ট।")
        except sqlite3.IntegrityError:
            await query.answer("আপনি এটি আগেই শেষ করেছেন!", show_alert=True)
    conn.commit()
    conn.close()

async def amolnama(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT task_list FROM tasks WHERE chat_id = ?", (chat_id,))
    task_row = c.fetchone()
    if not task_row:
        await update.message.reply_text("আজ কোনো টাস্ক নেই।")
        return
    
    tasks = [t.strip() for t in task_row[0].split(',')]
    c.execute("SELECT user_id, name FROM scores WHERE chat_id = ?", (chat_id,))
    users = c.fetchall()
    
    report = "📝 **আজকের আমলনামা**\n\n"
    for uid, name in users:
        c.execute("SELECT task_index FROM user_progress WHERE chat_id=? AND user_id=?", (chat_id, uid))
        done_indices = [r[0] for r in c.fetchall()]
        done_tasks = [tasks[i] for i in done_indices]
        pending = len(tasks) - len(done_tasks)
        report += f"👤 {name}: ✅ {len(done_tasks)} শেষ, ⏳ {pending} বাকি\n"
    
    await update.message.reply_text(report, parse_mode='Markdown')
    conn.close()

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT name, points FROM scores WHERE chat_id = ? ORDER BY points DESC", (chat_id,))
    rows = c.fetchall()
    msg = "🏆 **Leaderboard**\n\n"
    for i, r in enumerate(rows, 1): msg += f"{i}. {r[0]} — {r[1]} pt\n"
    await update.message.reply_text(msg or "পয়েন্ট টেবিল খালি।", parse_mode='Markdown')
    conn.close()

async def change_task_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_id = str(update.effective_user.id)
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO votes (chat_id, user_id) VALUES (?, ?)", (chat_id, user_id))
    c.execute("SELECT COUNT(*) FROM votes WHERE chat_id = ?", (chat_id,))
    count = c.fetchone()[0]
    
    if count >= 2:
        c.execute("DELETE FROM tasks WHERE chat_id = ?", (chat_id,))
        c.execute("DELETE FROM votes WHERE chat_id = ?", (chat_id,))
        c.execute("DELETE FROM user_progress WHERE chat_id = ?", (chat_id,))
        await update.message.reply_text("🗳 ভোট সম্পন্ন! টাস্ক রিসেট হয়েছে। নতুন টাস্ক দিন।")
    else:
        await update.message.reply_text(f"🗳 ভোট রেকর্ড হয়েছে ({count}/2)।")
    conn.commit()
    conn.close()

async def daily_refresh(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE scores SET points = points - 1")
    c.execute("DELETE FROM tasks")
    c.execute("DELETE FROM user_progress")
    c.execute("DELETE FROM votes")
    conn.commit()
    conn.close()
    print("Daily Refresh Success")

if __name__ == '__main__':
    init_db()
    
    # আলাদা থ্রেডে ফ্ল্যাক্স সার্ভার চালু করা যাতে রেন্ডার পোর্ট পায়
    threading.Thread(target=run_flask, daemon=True).start()
    
    app = Application.builder().token(TOKEN).build()
    
    if app.job_queue:
        app.job_queue.run_daily(daily_refresh, time=time(hour=6, minute=0, second=0, tzinfo=TZ))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settask", set_task))
    app.add_handler(CommandHandler("task", show_task))
    app.add_handler(CommandHandler("changetask", change_task_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("amolnama", amolnama))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is starting...")
    app.run_polling()
