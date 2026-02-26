import os
import sqlite3
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Token setup from Render Environment Variable
TOKEN = os.getenv('BOT_TOKEN')

# ডাটাবেজ সেটআপ (পয়েন্ট এবং বর্তমান টাস্ক সেভ রাখার জন্য)
def init_db():
    conn = sqlite3.connect('study_data.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scores 
                 (user_id INTEGER PRIMARY KEY, name TEXT, points INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS current_task 
                 (id INTEGER PRIMARY KEY, task_text TEXT)''')
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

# স্টার্ট কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 **স্টাডি ট্র্যাকার বটে স্বাগতম!**\n\n"
        "কিভাবে ব্যবহার করবেন:\n"
        "১. টাস্ক সেট করতে লিখুন: `/settask আজকের পড়ার তালিকা`\n"
        "২. টাস্ক দেখতে ও পূরণ করতে লিখুন: `/task`\n"
        "৩. পয়েন্ট দেখতে লিখুন: `/leaderboard`",
        parse_mode='Markdown'
    )

# নতুন টাস্ক সেট করার কমান্ড (যে কেউ পারবে)
async def set_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("দয়া করে কমান্ডের সাথে টাস্কটি লিখুন। উদাহরণ:\n`/settask ২ ঘণ্টা ফিজিক্স পড়া`", parse_mode='Markdown')
        return
    
    task_description = ' '.join(context.args)
    conn = sqlite3.connect('study_data.db')
    c = conn.cursor()
    c.execute("DELETE FROM current_task") # আগের টাস্ক মুছে ফেলা
    c.execute("INSERT INTO current_task (id, task_text) VALUES (1, ?)", (task_description,))
    conn.commit()
    conn.close()
    
    await update.message.reply_text(f"✅ **আজকের টাস্ক সেট করা হয়েছে:**\n{task_description}", parse_mode='Markdown')

# সেভ করা টাস্ক দেখানোর কমান্ড
async def show_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('study_data.db')
    c = conn.cursor()
    c.execute("SELECT task_text FROM current_task WHERE id = 1")
    row = c.fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("এখনো কোনো টাস্ক সেট করা হয়নি! `/settask` দিয়ে টাস্ক অ্যাড করুন।")
        return

    task_text = row[0]
    keyboard = [[InlineKeyboardButton("✅ Done (পয়েন্ট নিন)", callback_data='done'),
                 InlineKeyboardButton("❌ বাকি আছে", callback_data='not_done')]]
    
    await update.message.reply_text(
        f"📖 **আজকের নির্ধারিত টাস্ক:**\n\n{task_text}\n\nশেষ হলে নিচের বাটনে ক্লিক করুন:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# বাটন ক্লিক হ্যান্ডলার
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    await query.answer()

    if query.data == 'done':
        total = update_score(user.id, user.first_name, 10)
        await query.edit_message_text(f"সাবাস {user.first_name}! ১০ পয়েন্ট পেয়েছেন।\nআপনার মোট পয়েন্ট: {total}")
    else:
        await query.edit_message_text(f"হাল ছাড়বেন না {user.first_name}! দ্রুত শেষ করার চেষ্টা করুন।")

# লিডারবোর্ড
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('study_data.db')
    c = conn.cursor()
    c.execute("SELECT name, points FROM scores ORDER BY points DESC LIMIT 10")
    rows = c.fetchall()
    conn.close()
    
    msg = "🏆 **লিডারবোর্ড (সেরা ১০ জন)** 🏆\n\n"
    if not rows:
        msg += "এখনো কেউ পয়েন্ট পায়নি।"
    for i, row in enumerate(rows, 1):
        msg += f"{i}. {row[0]} — {row[1]} pt\n"
    
    await update.message.reply_text(msg, parse_mode='Markdown')

if __name__ == '__main__':
    init_db()
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settask", set_task))
    app.add_handler(CommandHandler("task", show_task))
    app.add_handler(CommandHandler("leaderboard", leaderboard))
    app.add_handler(CallbackQueryHandler(button_click))
    
    print("Bot is running...")
    app.run_polling()
