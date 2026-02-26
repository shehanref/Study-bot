import logging
import sqlite3
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

TOKEN = 'YOUR_BOT_TOKEN_HERE'

# ডাটাবেজ সেটআপ
def init_db():
    conn = sqlite3.connect('study_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
                 (user_id INTEGER PRIMARY KEY, name TEXT, points INTEGER)''')
    conn.commit()
    conn.close()

# পয়েন্ট আপডেট ফাংশন
def update_score(user_id, name, points):
    conn = sqlite3.connect('study_data.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO scores (user_id, name, points) VALUES (?, ?, 0)", (user_id, name))
    c.execute("UPDATE scores SET points = points + ?, name = ? WHERE user_id = ?", (points, name, user_id))
    conn.commit()
    c.execute("SELECT points FROM scores WHERE user_id = ?", (user_id,))
    total = c.fetchone()[0]
    conn.close()
    return total

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("বট সক্রিয়! গ্রুপে /task লিখুন।")

async def send_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✅ সম্পন্ন", callback_data='done'),
                 InlineKeyboardButton("❌ বাকি", callback_data='not_done')]]
    await update.message.reply_text("📖 আজকের টাস্ক শেষ করে থাকলে নিচের বাটনে চাপ দিন:", 
                                  reply_markup=InlineKeyboardMarkup(keyboard))

async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if query.data == 'done':
        total = update_score(user.id, user.first_name, 10)
        await query.edit_message_text(f"সাবাস {user.first_name}! ১০ পয়েন্ট পেয়েছেন। মোট: {total}")
    else:
        await query.edit_message_text(f"চেষ্টা করুন {user.first_name}!")

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('study_data.db')
    c = conn.cursor()
    c.execute("SELECT name, points FROM scores ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    
    msg = "🏆 লিডারবোর্ড 🏆\n\n"
    for i, row in enumerate(rows, 1):
        msg += f"{i}. {row[0]} — {row[1]} pt\n"
    await update.message.reply_text(msg, parse_mode='Markdown')

if name == 'main':
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("task", send_task))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CallbackQueryHandler(button_click))
    app.run_polling()