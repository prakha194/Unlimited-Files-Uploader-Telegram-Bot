import os
import logging
import asyncio
import threading
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import psycopg
from psycopg.rows import dict_row
from datetime import datetime

# -------------------- Configuration --------------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Get environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DATABASE_URL = os.getenv("DATABASE_URL")

# Handle STORAGE_CHANNEL_ID - supports both numeric IDs and usernames
storage_channel_raw = os.getenv("STORAGE_CHANNEL_ID")
if storage_channel_raw and storage_channel_raw.startswith('@'):
    STORAGE_CHANNEL = storage_channel_raw  # Public channel username
    logger.info(f"Storage channel set as username: {STORAGE_CHANNEL}")
else:
    try:
        STORAGE_CHANNEL = int(storage_channel_raw) if storage_channel_raw else None
        logger.info(f"Storage channel set as numeric ID: {STORAGE_CHANNEL}")
    except (ValueError, TypeError):
        STORAGE_CHANNEL = None
        logger.error(f"Invalid STORAGE_CHANNEL_ID: {storage_channel_raw}")

# Flask app
app = Flask(__name__)

# -------------------- Database Functions --------------------
def get_db_connection():
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
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
            cur.execute("""
                CREATE TABLE IF NOT EXISTS files (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    file_id TEXT,
                    file_name TEXT,
                    file_size BIGINT,
                    message_id INTEGER,
                    link TEXT,
                    uploaded_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        with conn.cursor(row_factory=dict_row) as cur:
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
            row = cur.fetchone()
            return row if row else None

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

def format_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.2f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"

# -------------------- Application --------------------
application = Application.builder().token(BOT_TOKEN).updater(None).build()

# -------------------- Handlers (Admin Only) --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ You are not authorized to use this bot.")
        return

    add_user(user.id, user.username, user.first_name)
    stats = get_user_stats(user.id)

    if stats:
        total_files, total_size, joined_date = stats
        await update.message.reply_text(
            f"✅ **Admin Panel**\n\n"
            f"Welcome, {user.first_name}!\n\n"
            f"📊 **Your Stats:**\n"
            f"• Files uploaded: {total_files}\n"
            f"• Storage used: {format_size(total_size)}\n"
            f"• Member since: {joined_date.strftime('%Y-%m-%d')}\n\n"
            f"📤 **Send or forward me any file** (up to 2GB) and I'll store it.\n"
            f"🔗 Links never expire and have no forward signatures.\n\n"
            f"**Commands:**\n"
            f"/stats - Bot statistics\n"
            f"/mylinks - Your recent files\n"
            f"/mystats - Your personal stats\n"
            f"/test - Test channel connection",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            f"✅ **Admin Panel**\n\n"
            f"Welcome, {user.first_name}!\n\n"
            f"Send or forward me a file to get started.\n\n"
            f"**Commands:**\n"
            f"/stats - Bot statistics\n"
            f"/mylinks - Your recent files\n"
            f"/mystats - Your personal stats\n"
            f"/test - Test channel connection"
        )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    total_files = get_total_files()
    total_storage = get_total_storage()
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"📁 **Total files:** {total_files}\n"
        f"💾 **Total storage:** {format_size(total_storage)}",
        disable_web_page_preview=True
    )

async def mylinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    files = get_user_files(user_id, limit=10)

    if not files:
        await update.message.reply_text("📭 No files found. Send me a file to get started!")
        return

    message = "📁 **Your Recent Files (Last 10):**\n\n"
    for i, file in enumerate(files, 1):
        file_name = file['file_name']
        file_size = file['file_size']
        link = file['link']
        uploaded_date = file['uploaded_date']
        message += f"{i}. 📄 {file_name[:30]}\n"
        message += f"   💾 Size: {format_size(file_size)}\n"
        message += f"   🔗 [Download Link]({link})\n"
        message += f"   📅 {uploaded_date.strftime('%Y-%m-%d %H:%M')}\n\n"

    await update.message.reply_text(message, disable_web_page_preview=True)

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    stats = get_user_stats(user_id)
    if stats:
        total_files, total_size, joined_date = stats
        await update.message.reply_text(
            f"📊 **Your Statistics**\n\n"
            f"📁 **Total files:** {total_files}\n"
            f"💾 **Storage used:** {format_size(total_size)}\n"
            f"📅 **Member since:** {joined_date.strftime('%Y-%m-%d')}",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text("No statistics found. Upload a file to get started!")

async def test_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test if bot can post to the storage channel"""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not STORAGE_CHANNEL:
        await update.message.reply_text("❌ STORAGE_CHANNEL_ID is not configured!")
        return

    try:
        await update.message.reply_text(f"📡 Testing channel: {STORAGE_CHANNEL}")
        
        # Try to send a test message
        result = await context.bot.send_message(
            chat_id=STORAGE_CHANNEL,
            text=f"✅ Test message from bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        
        await update.message.reply_text(
            f"✅ **Test successful!**\n\n"
            f"Channel: {STORAGE_CHANNEL}\n"
            f"Message ID: {result.message_id}\n\n"
            f"Bot can post to the channel."
        )
        logger.info(f"Test message sent to channel {STORAGE_CHANNEL}")
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Test failed: {error_msg}")
        await update.message.reply_text(
            f"❌ **Test failed!**\n\n"
            f"Error: {error_msg[:200]}\n\n"
            f"Make sure:\n"
            f"1. Bot is admin in the channel\n"
            f"2. Channel ID is correct\n"
            f"3. Bot has 'Post Messages' permission"
        )

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    # Ensure user in DB
    add_user(user.id, user.username, user.first_name)

    # Check if there's a file (either directly sent or forwarded)
    message = update.message
    
    # Get the actual file message (if forwarded, use the original)
    file_message = message
    if message.forward_origin:
        # This is a forwarded message, we need to get the original
        # For forwarded messages, the media is still in message
        logger.info("Processing forwarded message")
    
    if not file_message.effective_attachment:
        await update.message.reply_text("Please send or forward a file (photo, video, document, etc.)")
        return

    processing_msg = await update.message.reply_text("📤 Uploading to storage...")

    try:
        # Debug logging
        logger.info(f"=== Processing file from admin {user.id} ===")
        logger.info(f"STORAGE_CHANNEL value: {STORAGE_CHANNEL}")
        logger.info(f"Message has attachment: {bool(file_message.effective_attachment)}")

        # Extract file info
        if file_message.document:
            file_name = file_message.document.file_name
            file_size = file_message.document.file_size
            file_id = file_message.document.file_id
            logger.info(f"Document: {file_name} ({file_size} bytes)")
        elif file_message.photo:
            file_name = f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
            file_size = file_message.photo[-1].file_size
            file_id = file_message.photo[-1].file_id
            logger.info(f"Photo: {file_name} ({file_size} bytes)")
        elif file_message.video:
            file_name = file_message.video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
            file_size = file_message.video.file_size
            file_id = file_message.video.file_id
            logger.info(f"Video: {file_name} ({file_size} bytes)")
        elif file_message.audio:
            file_name = file_message.audio.file_name or f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
            file_size = file_message.audio.file_size
            file_id = file_message.audio.file_id
            logger.info(f"Audio: {file_name} ({file_size} bytes)")
        else:
            file_name = f"file_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            file_size = 0
            file_id = None
            logger.info(f"Unknown file type")

        # Forward to storage channel WITHOUT signature
        # Use copy_message instead of forward to completely remove signature
        logger.info(f"Attempting to copy to: {STORAGE_CHANNEL}")
        
        # Use copy_message which doesn't show "Forwarded from" at all
        copied = await context.bot.copy_message(
            chat_id=STORAGE_CHANNEL,
            from_chat_id=file_message.chat_id,
            message_id=file_message.message_id
        )
        
        logger.info(f"Copy result: {copied}")

        if copied:
            stored_msg_id = copied.message_id
            logger.info(f"Stored message ID in channel: {stored_msg_id}")

            # Generate link
            if isinstance(STORAGE_CHANNEL, str) and STORAGE_CHANNEL.startswith('@'):
                link = f"https://t.me/{STORAGE_CHANNEL.lstrip('@')}/{stored_msg_id}"
                logger.info(f"Generated username link: {link}")
            else:
                channel_positive = abs(int(STORAGE_CHANNEL))
                link = f"https://t.me/c/{channel_positive}/{stored_msg_id}"
                logger.info(f"Generated numeric link: {link}")

            # Save to database
            update_user_stats(user.id, file_size)
            save_file(user.id, file_id, file_name, file_size, stored_msg_id, link)

            await processing_msg.edit_text(
                f"✅ **File stored successfully!**\n\n"
                f"📄 **Name:** {file_name}\n"
                f"💾 **Size:** {format_size(file_size)}\n"
                f"🔗 **Link:** {link}\n\n"
                f"🔒 No forward signature | 📁 Permanent",
                disable_web_page_preview=True
            )
            logger.info(f"Successfully stored {file_name} -> {link}")
        else:
            logger.error("Copy returned None")
            await processing_msg.edit_text("❌ Failed to store file. No response from Telegram.")
            
    except Exception as e:
        logger.error(f"Error handling file: {e}", exc_info=True)
        error_msg = str(e)
        await processing_msg.edit_text(f"❌ Error: {error_msg[:200]}\n\nCheck logs for details.")

# -------------------- Register Handlers --------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("stats", stats))
application.add_handler(CommandHandler("mylinks", mylinks))
application.add_handler(CommandHandler("mystats", mystats))
application.add_handler(CommandHandler("test", test_channel))
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

# -------------------- Main Entry --------------------
if __name__ == "__main__":
    # Initialize database
    init_db()

    # Set up asyncio loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Initialize application and set webhook
    async def setup():
        await application.initialize()
        await application.start()
        render_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_url:
            webhook_url = f"{render_url}/webhook"
            await application.bot.set_webhook(url=webhook_url)
            logger.info(f"Webhook set to: {webhook_url}")
        else:
            logger.warning("RENDER_EXTERNAL_URL not found, webhook not set")

    loop.run_until_complete(setup())

    # Run Flask in a separate thread
    def run_flask():
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, threaded=True)

    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    logger.info("Flask server started on port 5000")

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        loop.run_until_complete(application.shutdown())
        loop.close()
        flask_thread.join()