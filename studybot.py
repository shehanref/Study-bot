import os
import sqlite3
import logging
import threading
from datetime import datetime, time, timedelta
import pytz
from flask import Flask
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- FLASK SERVER FOR RENDER ---
server = Flask('')
@server.route('/')
def home(): return "Study Bot Pro is Live!"

def run_flask():
    port = int(os.environ.get('PORT', 8080))
    server.run(host='0.0.0.0', port=port)

# --- CONFIG ---
TOKEN = os.getenv('BOT_TOKEN')
TZ = pytz.timezone('Asia/Dhaka')

# --- DB SETUP ---
def init_db():
    conn = sqlite3.connect('study_ultra.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS logs 
                 (chat_id TEXT, user_id INTEGER, name TEXT, points INTEGER, timestamp DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS stats 
                 (chat_id TEXT, user_id INTEGER, name TEXT, streak INTEGER, 
                 weekly_record TEXT, PRIMARY KEY (chat_id, user_id))''')
    c.execute('''CREATE TABLE IF NOT EXISTS tasks 
                 (chat_id TEXT PRIMARY KEY, task_list TEXT, set_at DATETIME)''')
    c.execute('''CREATE TABLE IF NOT EXISTS progress 
                 (chat_id TEXT, user_id INTEGER, task_index INTEGER, 
                 PRIMARY KEY (chat_id, user_id, task_index))''')
    conn.commit()
    conn.close()

def get_db(): return sqlite3.connect('study_ultra.db')

# --- HELPERS ---
def get_progress_bar(percent):
    done = int(percent / 10)
    return "🟢" * done + "⚪" * (10 - done)

# --- COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = (
        "👑 **STUDY TRACKER PRO V4** 👑\n\n"
        "📝 `/settask t1, t2...` - টাস্ক সেট\n"
        "🎯 `/task` - আজকের মিশন (টিক লিস্ট)\n"
        "📊 `/today`, `/yesterday`, `/week`, `/month` - লিডারবোর্ড\n"
        "👤 `/me` - পার্সোনাল স্ট্রিক ও গ্রিড\n"
        "📜 `/amolnama` - ভিজ্যুয়াল প্রগ্রেস বার"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')

async def set_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    if not context.args:
        await update.message.reply_text("❌ ব্যবহার: `/settask পড়া১, পড়া২`")
        return

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT set_at FROM tasks WHERE chat_id=?", (chat_id,))
    if c.fetchone():
        await update.message.reply_text("⚠️ টাস্ক অলরেডি আছে! বদলাতে হলে ১২টা পর্যন্ত অপেক্ষা করুন।")
        return

    task_str = ' '.join(context.args)
    c.execute("INSERT INTO tasks VALUES (?, ?, ?)", (chat_id, task_str, datetime.now(TZ)))
    conn.commit()
    conn.close()
    await update.message.reply_text(f"✅ **Mission Locked!** রাত ১২টায় রিসেট হবে।\n📋 {task_str}")

async def task_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT task_list FROM tasks WHERE chat_id=?", (chat_id,))
    row = c.fetchone()
    if not row:
        await update.message.reply_text("🚫 কোনো টাস্ক সেট করা হয়নি!")
        return

    tasks = [t.strip() for t in row[0].split(',')]
    keyboard = []
    for i, t in enumerate(tasks):
        c.execute("SELECT 1 FROM progress WHERE chat_id=? AND user_id=? AND task_index=?", (chat_id, user_id, i))
        icon = "✅" if c.fetchone() else "⬜"
        keyboard.append([InlineKeyboardButton(f"{icon} {t}", callback_data=f"p_{i}")])
    
    await update.message.reply_text("📖 আপনার মিশন লিস্ট:", reply_markup=InlineKeyboardMarkup(keyboard))
    conn.close()

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    chat_id = str(query.message.chat_id)
    user = query.from_user
    if query.data.startswith("p_"):
        idx = int(query.data.split("_")[1])
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO progress VALUES (?, ?, ?)", (chat_id, user.id, idx))
            c.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)", (chat_id, user.id, user.first_name, 2, datetime.now(TZ)))
            conn.commit()
            await query.answer("+২ পয়েন্ট যোগ হয়েছে!")
            await query.message.delete()
            await task_menu(update, context)
        except sqlite3.IntegrityError:
            await query.answer("এটি আগেই শেষ করেছেন!", show_alert=True)
        conn.close()

async def me_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    user_id = update.effective_user.id
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT streak, weekly_record FROM stats WHERE chat_id=? AND user_id=?", (chat_id, user_id))
    row = c.fetchone()
    
    streak = row[0] if row else 0
    grid = row[1] if row else "⬜⬜⬜⬜⬜⬜⬜"
    
    crowns = "👑 " * (streak // 7)
    msg = (
        f"👤 **User:** {update.effective_user.first_name}\n"
        f"🔥 **Current Streak:** {streak} days\n"
        f"🏆 **Badges:** {crowns if crowns else 'Beginner'}\n"
        f"📅 **Weekly Grid:** {grid}"
    )
    await update.message.reply_text(msg, parse_mode='Markdown')
    conn.close()

# --- AUTOMATION LOGIC ---

async def midnight_handler(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT chat_id, task_list FROM tasks")
    all_groups = c.fetchall()

    for chat_id, task_list in all_groups:
        tasks = [t.strip() for t in task_list.split(',')]
        total_t = len(tasks)
        
        c.execute("SELECT DISTINCT user_id, name FROM logs WHERE chat_id=?", (chat_id,))
        users = c.fetchall()
        
        for uid, name in users:
            c.execute("SELECT COUNT(*) FROM progress WHERE chat_id=? AND user_id=?", (chat_id, uid))
            done = c.fetchone()[0]
            
            # Penalty Logic
            penalty = 0
            if done == 0:
                penalty = -5
            elif done < total_t:
                penalty = -(total_t - done)
            
            if penalty != 0:
                c.execute("INSERT INTO logs VALUES (?, ?, ?, ?, ?)", (chat_id, uid, name, penalty, datetime.now(TZ)))
            
            # Streak Logic
            c.execute("SELECT streak, weekly_record FROM stats WHERE chat_id=? AND user_id=?", (chat_id, uid))
            s_row = c.fetchone()
            curr_streak = s_row[0] if s_row else 0
            curr_grid = s_row[1] if s_row else ""
            
            if done == total_t:
                new_streak = curr_streak + 1
                new_grid = (curr_grid + "✅")[-7:]
            else:
                new_streak = 0
                new_grid = (curr_grid + "❌")[-7:]
            
            c.execute("INSERT OR REPLACE INTO stats VALUES (?, ?, ?, ?, ?)", (chat_id, uid, name, new_streak, new_grid))
        
        await context.bot.send_message(chat_id=chat_id, text="🕛 **রাত ১২টা বেজেছে!**\nসব টাস্ক রিসেট হয়েছে এবং পেনাল্টি দেওয়া হয়েছে।\nএখন নতুন দিনের টাস্ক সেট করুন: `/settask`")
    
    c.execute("DELETE FROM tasks")
    c.execute("DELETE FROM progress")
    conn.commit()
    conn.close()

async def alert_handler(context: ContextTypes.DEFAULT_TYPE):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT chat_id FROM tasks")
    chats_with_tasks = [r[0] for r in c.fetchall()]
    
    # Logic for reminder (Checking job context to see if it's 1hr or 6hr)
    # Simple approach: Broad message
    for chat in chats_with_tasks:
        await context.bot.send_message(chat_id=chat, text="⏰ **রিমাইন্ডার:** টাস্ক শেষ করতে ভুলবেন না! ১২টার আগে শেষ করুন।")
    conn.close()

if __name__ == '__main__':
    init_db()
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    
    jq = app.job_queue
    # Midnight Reset
    jq.run_daily(midnight_handler, time=time(hour=0, minute=0, tzinfo=TZ))
    # 6 Hour Reminder (If task exists)
    jq.run_repeating(alert_handler, interval=21600, first=3600) 

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settask", set_task))
    app.add_handler(CommandHandler("task", task_menu))
    app.add_handler(CommandHandler("me", me_status))
    app.add_handler(CallbackQueryHandler(button_handler))

    app.run_polling()
