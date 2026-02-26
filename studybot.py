import os
import sqlite3
import logging
from datetime import datetime, time
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Logging setup
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN = os.getenv('BOT_TOKEN')
TZ = pytz.timezone('Asia/Dhaka')

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('study_bot.db')
    c = conn.cursor()
    # স্কোর টেবিল
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
                 (chat_id TEXT, user_id INTEGER, name TEXT, points INTEGER, 
                 PRIMARY KEY (chat_id, user_id))''')
    # টাস্ক টেবিল
    c.execute('''CREATE TABLE IF NOT EXISTS tasks 
                 (chat_id TEXT PRIMARY KEY, task_list TEXT, set_at TEXT)''')
    # ইউজার প্রগ্রেস (কে কোন টাস্ক করল)
    c.execute('''CREATE TABLE IF NOT EXISTS user_progress 
                 (chat_id TEXT, user_id INTEGER, task_index INTEGER, 
                 PRIMARY KEY (chat_id, user_id, task_index))''')
    # ভোটের হিসাব
    c.execute('''CREATE TABLE IF NOT EXISTS votes 
                 (chat_id TEXT, user_id TEXT, PRIMARY KEY (chat_id, user_id))''')
    conn.commit()
    conn.close()

def get_db():
    return sqlite3.connect('study_bot.db')

# --- COMMANDS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🚀 **Advanced Study Tracker Bot**\n\n"
        "• `/settask t1, t2...` : নতুন টাস্ক (কমা দিয়ে)\n"
        "• `/task` : টাস্ক লিস্ট ও কমপ্লিশন বাটন\n"
        "• `/changetask` : টাস্ক বদলাতে ভোট দিন\n"
        "• `/leaderboard` : গ্রুপের র‍্যাঙ্কিং\n"
        "• `/amolnama` : আজকের রিপোর্ট",
        parse_mode='Markdown'
    )

# টাস্ক সেট করা (২৪ ঘণ্টায় একবার)
async def set_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("ব্যবহার: `/settask পড়া১, পড়া২`")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT set_at FROM tasks WHERE chat_id = ?", (chat_id,))
    row = c.fetchone()
    
    # সকাল ৬টার পর চেক (সিম্পল লজিক)
    if row:
        await update.message.reply_text("❌ আজকের টাস্ক অলরেডি সেট। বদলাতে `/changetask` লিখুন।")
        return

    task_text = ' '.join(context.args)
    c.execute("INSERT OR REPLACE INTO tasks (chat_id, task_list, set_at) VALUES (?, ?, ?)", 
              (chat_id, task_text, datetime.now(TZ).isoformat()))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ টাস্ক সেট হয়েছে!\n📋 {task_text}")

# টাস্ক দেখানো ও বাটন (Dynamic)
async def show_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
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
        # চেক করা ইউজার এটা কি আগেই করেছে?
        c.execute("SELECT 1 FROM user_progress WHERE chat_id=? AND user_id=? AND task_index=?", 
                  (chat_id, update.effective_user.id, i))
        status = "✅" if c.fetchone() else "⬜"
        keyboard.append([InlineKeyboardButton(f"{status} {t}", callback_data=f"done_{i}")])
    
    await update.message.reply_text("📖 আপনার করা টাস্কগুলো সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard))
    conn.close()

# ভোট সিস্টেম
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
        await update.message.reply_text("🗳 ভোট সম্পন্ন! আজকের টাস্ক রিসেট হয়েছে। এখন নতুন টাস্ক দিন।")
    else:
        await update.message.reply_text(f"🗳 ভোট রেকর্ড হয়েছে ({count}/2)। টাস্ক বদলাতে আরও ১ জনের ভোট লাগবে।")
    conn.commit()
    conn.close()

# বাটন হ্যান্ডলার (পয়েন্ট সিস্টেম)
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
            await query.answer("সাবাস! +২ পয়েন্ট।")
            # বাটন রিফ্রেশ (Optional)
        except sqlite3.IntegrityError:
            await query.answer("এটি আগেই শেষ করেছেন!", show_alert=True)
    
    conn.commit()
    conn.close()

# আমলনামা ও লিডারবোর্ড
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
        pending_count = len(tasks) - len(done_tasks)
        report += f"👤 {name}:\n✅ {', '.join(done_tasks) if done_tasks else 'কিছুই না'}\n⏳ বাকি: {pending_count}\n\n"
    
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
    await update.message.reply_text(msg or "এখনো কেউ পয়েন্ট পায়নি।", parse_mode='Markdown')
    conn.close()

# সকাল ৬টার রিফ্রেশ
async def daily_refresh(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    # যারা টাস্ক করেনি তাদের -১ লজিক (সিম্পল ভার্সন)
    c.execute("UPDATE scores SET points = points - 1") # এটি সব গ্রুপে প্রযোজ্য হবে
    c.execute("DELETE FROM tasks")
    c.execute("DELETE FROM user_progress")
    c.execute("DELETE FROM votes")
    conn.commit()
    conn.close()
    print("Refresh Done at 6 AM")

if __name__ == '__main__':
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    # Job Queue for 6 AM refresh
    app.job_queue.run_daily(daily_refresh, time=time(hour=6, minute=0, tzinfo=TZ))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settask", set_task))
    app.add_handler(CommandHandler("task", show_task))
    app.add_handler(CommandHandler("changetask", change_task_cmd))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CommandHandler("amolnama", amolnama))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()
