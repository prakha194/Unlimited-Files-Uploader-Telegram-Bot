import os
import logging
import asyncio
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    CallbackQueryHandler,
    ContextTypes
)
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime, timedelta
import json

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
STORAGE_CHANNEL = int(os.getenv("STORAGE_CHANNEL_ID"))
REQUIRED_CHANNEL = os.getenv("REQUIRED_CHANNEL")
DATABASE_URL = os.getenv("DATABASE_URL")

# Flask app
app = Flask(__name__)

# -------------------- Database Setup --------------------
def get_db_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            # Users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_files INTEGER DEFAULT 0,
                    total_size BIGINT DEFAULT 0
                )
            """)
            # Files table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    file_id TEXT,
                    file_name TEXT,
                    file_size BIGINT,
                    message_id INTEGER,
                    link TEXT,
                    uploaded_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            conn.commit()
    logger.info("Database initialized")

def add_user(user_id, username=None, first_name=None):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, username, first_name) 
                VALUES (%s, %s, %s) 
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id, username, first_name))
            conn.commit()

def update_user_stats(user_id, file_size):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET total_files = total_files + 1,
                    total_size = total_size + %s
                WHERE user_id = %s
            """, (file_size, user_id))
            conn.commit()

def save_file(user_id, file_id, file_name, file_size, message_id, link):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO files (user_id, file_id, file_name, file_size, message_id, link)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (user_id, file_id, file_name, file_size, message_id, link))
            conn.commit()

def get_user_files(user_id, limit=10):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT file_name, file_size, link, uploaded_date
                FROM files 
                WHERE user_id = %s 
                ORDER BY uploaded_date DESC 
                LIMIT %s
            """, (user_id, limit))
            return cur.fetchall()

def get_user_stats(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT total_files, total_size, joined_date
                FROM users 
                WHERE user_id = %s
            """, (user_id,))
            return cur.fetchone()

def get_all_users_count():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            return cur.fetchone()[0]

def get_total_files():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM files")
            return cur.fetchone()[0]

def get_total_storage():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(file_size), 0) FROM files")
            return cur.fetchone()[0]

def get_today_stats():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*), COALESCE(SUM(file_size), 0)
                FROM files 
                WHERE uploaded_date >= CURRENT_DATE
            """)
            return cur.fetchone()

def get_all_users_detailed():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT user_id, username, first_name, total_files, total_size, joined_date
                FROM users 
                ORDER BY joined_date DESC
            """)
            return cur.fetchall()

def format_size(bytes_size):
    """Convert bytes to human readable format"""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"

# Initialize database
init_db()

# Create Application WITHOUT an Updater (for webhooks)
application = Application.builder().token(BOT_TOKEN).updater(None).build()

# -------------------- Helper Functions --------------------
async def is_member(user_id):
    try:
        chat = await application.bot.get_chat(REQUIRED_CHANNEL)
        member = await application.bot.get_chat_member(chat.id, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logger.error(f"Error checking membership for {user_id}: {e}")
        return False

# -------------------- User Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    # Add user to database
    add_user(user_id, user.username, user.first_name)

    if await is_member(user_id):
        stats = get_user_stats(user_id)
        if stats:
            total_files, total_size, joined_date = stats
            await update.message.reply_text(
                f"✅ **Welcome back, {user.first_name}!**\n\n"
                f"📊 **Your Stats:**\n"
                f"• Files uploaded: {total_files}\n"
                f"• Storage used: {format_size(total_size)}\n"
                f"• Member since: {joined_date.strftime('%Y-%m-%d')}\n\n"
                f"📤 **Send me any file** (up to 2GB) and I'll give you a permanent download link.\n\n"
                f"🔗 Links never expire and have no forward signatures.\n\n"
                f"Use /mylinks to see your uploaded files.",
                disable_web_page_preview=True
            )
        return

    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("✅ I've Joined", callback_data="verify")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎬 **Welcome to File Storage Bot, {user.first_name}!**\n\n"
        f"To use this bot, you must first join our channel:\n"
        f"👉 @{REQUIRED_CHANNEL.lstrip('@')}\n\n"
        f"After joining, click the button below.",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    user_id = user.id

    if await is_member(user_id):
        await query.edit_message_text(
            "✅ **Verification successful!**\n\n"
            "Now you can send me any file (up to 2GB) and I'll give you a permanent download link.\n\n"
            "📎 Just send a photo, video, document, or any file.\n"
            "🔗 The link will be your direct access — no forward signatures.\n\n"
            "Use /mylinks to see all your uploaded files."
        )
    else:
        await query.edit_message_text(
            "❌ **You haven't joined the channel yet.**\n\n"
            f"Please join @{REQUIRED_CHANNEL.lstrip('@')} first, then click 'I've Joined' again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")],
                [InlineKeyboardButton("✅ I've Joined", callback_data="verify")]
            ])
        )

async def mylinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not await is_member(user_id):
        await update.message.reply_text(
            "⚠️ **Access Denied**\n\n"
            f"You must join @{REQUIRED_CHANNEL.lstrip('@')} first.\n"
            "Use /start to verify."
        )
        return
    
    files = get_user_files(user_id, limit=10)
    
    if not files:
        await update.message.reply_text(
            "📭 **No files found**\n\n"
            "You haven't uploaded any files yet. Send me a file to get started!"
        )
        return
    
    message = "📁 **Your Recent Files (Last 10):**\n\n"
    for i, (file_name, file_size, link, uploaded_date) in enumerate(files, 1):
        message += f"{i}. 📄 {file_name[:30]}\n"
        message += f"   💾 Size: {format_size(file_size)}\n"
        message += f"   🔗 [Download Link]({link})\n"
        message += f"   📅 {uploaded_date.strftime('%Y-%m-%d %H:%M')}\n\n"
    
    await update.message.reply_text(message, disable_web_page_preview=True)

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not await is_member(user_id):
        await update.message.reply_text(
            "⚠️ **Access Denied**\n\n"
            f"You must join @{REQUIRED_CHANNEL.lstrip('@')} first."
        )
        return
    
    stats = get_user_stats(user_id)
    if stats:
        total_files, total_size, joined_date = stats
        await update.message.reply_text(
            f"📊 **Your Statistics**\n\n"
            f"📁 **Total files:** {total_files}\n"
            f"💾 **Storage used:** {format_size(total_size)}\n"
            f"📅 **Member since:** {joined_date.strftime('%Y-%m-%d')}\n"
            f"🎯 **Daily limit:** Unlimited (up to 2GB per file)\n\n"
            f"Use /mylinks to see all your files.",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text("No statistics found. Start by uploading a file!")

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    if not await is_member(user_id):
        await update.message.reply_text(
            "⚠️ **Access Denied**\n\n"
            f"You must join @{REQUIRED_CHANNEL.lstrip('@')} first.\n"
            "Use /start to verify."
        )
        return

    if not update.message.effective_attachment:
        await update.message.reply_text(
            "Please send a **file** (photo, video, document, audio, etc.)\n"
            "Maximum size: **2GB**"
        )
        return

    processing_msg = await update.message.reply_text("📤 Uploading to storage...")

    try:
        # Get file info
        if update.message.document:
            file_name = update.message.document.file_name
            file_size = update.message.document.file_size
            file_id = update.message.document.file_id
        elif update.message.photo:
            file_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            file_size = update.message.photo[-1].file_size
            file_id = update.message.photo[-1].file_id
        elif update.message.video:
            file_name = update.message.video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            file_size = update.message.video.file_size
            file_id = update.message.video.file_id
        else:
            file_name = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            file_size = 0
            file_id = None

        # Forward to storage channel without signature
        forwarded = await context.bot.forward_messages(
            chat_id=STORAGE_CHANNEL,
            from_chat_id=update.message.chat_id,
            message_ids=update.message.message_id,
            drop_author=True
        )

        if forwarded:
            if isinstance(forwarded, list):
                stored_msg_id = forwarded[0].message_id
            else:
                stored_msg_id = forwarded.message_id

            channel_positive = abs(STORAGE_CHANNEL)
            link = f"https://t.me/c/{channel_positive}/{stored_msg_id}"

            # Save to database
            update_user_stats(user_id, file_size)
            save_file(user_id, file_id, file_name, file_size, stored_msg_id, link)

            await processing_msg.delete()
            await update.message.reply_text(
                f"✅ **File stored successfully!**\n\n"
                f"📄 **Name:** {file_name}\n"
                f"💾 **Size:** {format_size(file_size)}\n"
                f"🔗 **Your link:**\n{link}\n\n"
                f"💾 **Permanent** | 🔒 **No forward signature** | 📁 **Up to 2GB**\n\n"
                f"Use /mylinks to see all your files.",
                disable_web_page_preview=True
            )
            logger.info(f"User {user_id} stored {file_name} -> {link}")
    except Exception as e:
        logger.error(f"Error storing file: {e}")
        await processing_msg.edit_text("❌ Failed to store file. Please try again later.")

# -------------------- Admin Handlers --------------------
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    total_users = get_all_users_count()
    total_files = get_total_files()
    total_storage = get_total_storage()
    today_files, today_size = get_today_stats()
    
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 **Total Users:** {total_users}\n"
        f"📁 **Total Files:** {total_files}\n"
        f"💾 **Total Storage:** {format_size(total_storage)}\n\n"
        f"📅 **Today's Activity:**\n"
        f"• Files uploaded: {today_files}\n"
        f"• Storage added: {format_size(today_size)}\n\n"
        f"📈 **Average per user:**\n"
        f"• Files: {total_files/total_users if total_users > 0 else 0:.1f}\n"
        f"• Storage: {format_size(total_storage/total_users if total_users > 0 else 0)}",
        disable_web_page_preview=True
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    users = get_all_users_detailed()
    
    if not users:
        await update.message.reply_text("No users in database.")
        return

    message = "👥 **User List**\n\n"
    for user_id, username, first_name, total_files, total_size, joined_date in users[:20]:  # Limit to 20
        message += f"**ID:** {user_id}\n"
        message += f"**Name:** {first_name or 'N/A'} (@{username or 'N/A'})\n"
        message += f"**Files:** {total_files} | **Storage:** {format_size(total_size)}\n"
        message += f"**Joined:** {joined_date.strftime('%Y-%m-%d')}\n\n"
    
    if len(users) > 20:
        message += f"\n*Showing first 20 of {len(users)} users*"
    
    await update.message.reply_text(message, disable_web_page_preview=True)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to use this command.")
        return

    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Please reply to a message with /broadcast to send it to all users.")
        return

    broadcast_msg = update.message.reply_to_message
    users = get_all_users()
    
    if not users:
        await update.message.reply_text("No users in database.")
        return

    status_msg = await update.message.reply_text(f"📤 Broadcasting to {len(users)} users...")
    
    success = 0
    fail = 0
    
    for uid in users:
        try:
            if broadcast_msg.text:
                await context.bot.send_message(chat_id=uid, text=broadcast_msg.text)
            elif broadcast_msg.photo:
                await context.bot.send_photo(
                    chat_id=uid,
                    photo=broadcast_msg.photo[-1].file_id,
                    caption=broadcast_msg.caption
                )
            elif broadcast_msg.video:
                await context.bot.send_video(
                    chat_id=uid,
                    video=broadcast_msg.video.file_id,
                    caption=broadcast_msg.caption
                )
            elif broadcast_msg.document:
                await context.bot.send_document(
                    chat_id=uid,
                    document=broadcast_msg.document.file_id,
                    caption=broadcast_msg.caption
                )
            else:
                await context.bot.send_message(
                    chat_id=uid,
                    text="[Admin broadcast - unsupported media type]"
                )
            success += 1
        except Exception as e:
            logger.error(f"Failed to send to {uid}: {e}")
            fail += 1
        
        # Small delay to avoid rate limits
        await asyncio.sleep(0.05)
    
    await status_msg.edit_text(f"✅ Broadcast completed!\n\n📤 Sent to: {success}\n❌ Failed: {fail}")

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("mylinks", mylinks))
application.add_handler(CommandHandler("mystats", mystats))
application.add_handler(CommandHandler("stats", admin_stats))  # Admin only
application.add_handler(CommandHandler("users", admin_users))  # Admin only
application.add_handler(CommandHandler("broadcast", broadcast))  # Admin only
application.add_handler(CallbackQueryHandler(verify_callback, pattern="verify"))
application.add_handler(MessageHandler(filters.ATTACHMENT, handle_file))

# -------------------- Flask Webhook --------------------
@app.route("/webhook", methods=["POST"])
async def webhook():
    update = Update.de_json(request.get_json(force=True), application.bot)
    await application.process_update(update)
    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

if __name__ == "__main__":
    # Set webhook
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        # Run async webhook setting
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(application.bot.set_webhook(url=webhook_url))
        logger.info(f"Webhook set to: {webhook_url}")
    else:
        logger.warning("RENDER_EXTERNAL_URL not found, webhook not set")

    # Start Flask server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)