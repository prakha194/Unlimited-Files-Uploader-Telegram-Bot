import os
import logging
import asyncio
import threading
import secrets
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

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
DATABASE_URL = os.getenv("DATABASE_URL")

storage_channel_raw = os.getenv("STORAGE_CHANNEL_ID")
if storage_channel_raw and storage_channel_raw.startswith("@"):
    STORAGE_CHANNEL = storage_channel_raw
else:
    try:
        STORAGE_CHANNEL = int(storage_channel_raw) if storage_channel_raw else None
    except (ValueError, TypeError):
        STORAGE_CHANNEL = None

app = Flask(__name__)
BOT_LOOP = None
BOT_USERNAME = None

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
                    total_size BIGINT DEFAULT 0,
                    first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    welcome_sent BOOLEAN DEFAULT FALSE
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
                    token TEXT UNIQUE,
                    link TEXT,
                    uploaded_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Add missing columns if needed
            try:
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS welcome_sent BOOLEAN DEFAULT FALSE")
            except:
                pass
            conn.commit()
    logger.info("Database initialized")

def add_user(user_id, username=None, first_name=None):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (user_id, username, first_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username,
                    first_name = EXCLUDED.first_name
            """, (user_id, username, first_name))
            conn.commit()

def set_welcome_sent(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET welcome_sent = TRUE WHERE user_id = %s", (user_id,))
            conn.commit()

def welcome_sent(user_id):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT welcome_sent FROM users WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return row and row[0]

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

def save_file(user_id, file_id, file_name, file_size, message_id, token):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            link = f"https://t.me/{BOT_USERNAME}?start={token}" if BOT_USERNAME else ""
            cur.execute("""
                INSERT INTO files (user_id, file_id, file_name, file_size, message_id, token, link)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (user_id, file_id, file_name, file_size, message_id, token, link))
            conn.commit()
            return link

def get_file_by_token(token):
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM files WHERE token = %s", (token,))
            return cur.fetchone()

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
            return cur.fetchone()

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

def get_all_users():
    with get_db_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT user_id, username, first_name, joined_date, total_files, total_size FROM users ORDER BY joined_date DESC")
            return cur.fetchall()

def format_size(bytes_size):
    if bytes_size < 1024:
        return f"{bytes_size} B"
    if bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.2f} KB"
    if bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.2f} MB"
    return f"{bytes_size / (1024 * 1024 * 1024):.2f} GB"

def extract_message_meta(msg):
    if msg.document:
        return (
            msg.document.file_id,
            msg.document.file_name or "document",
            msg.document.file_size or 0
        )
    if msg.photo:
        return (
            msg.photo[-1].file_id,
            f"photo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg",
            msg.photo[-1].file_size or 0
        )
    if msg.video:
        return (
            msg.video.file_id,
            msg.video.file_name or f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4",
            msg.video.file_size or 0
        )
    if msg.audio:
        return (
            msg.audio.file_id,
            msg.audio.file_name or f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3",
            msg.audio.file_size or 0
        )
    if msg.voice:
        return (
            msg.voice.file_id,
            f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg",
            msg.voice.file_size or 0
        )
    if msg.text:
        text_bytes = len(msg.text.encode("utf-8"))
        return (
            None,
            f"text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            text_bytes
        )
    return (
        None,
        f"message_{datetime.now().strftime('%Y%m%d_%H%M%S')}.dat",
        0
    )

# -------------------- Application --------------------
application = Application.builder().token(BOT_TOKEN).updater(None).build()

# -------------------- Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    # If there is a token argument, serve the file
    if context.args:
        token = context.args[0]
        file_record = get_file_by_token(token)
        if file_record:
            # Add user if not admin (or always add, but we already do)
            add_user(user_id, user.username, user.first_name)
            # Send welcome message if this is the first time for this user (and not admin)
            if user_id != ADMIN_ID and not welcome_sent(user_id):
                await update.message.reply_text(
                    "👋 Welcome to the File Storage Bot!\n\n"
                    "You are receiving this file via a shared link.\n"
                    "Only the admin can upload files, but you can download any shared files using these links.\n\n"
                    "🔗 Use the link you received to access files."
                )
                set_welcome_sent(user_id)
            # Send the file
            try:
                await context.bot.copy_message(
                    chat_id=update.effective_chat.id,
                    from_chat_id=STORAGE_CHANNEL,
                    message_id=file_record["message_id"]
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Error retrieving file: {e}")
            return
        else:
            await update.message.reply_text("❌ Invalid or expired link.")
            return

    # Normal start command (no token)
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ This bot is private and only the admin can use it.")
        return

    add_user(user.id, user.username, user.first_name)
    stats = get_user_stats(user.id)

    if stats:
        total_files, total_size, joined_date = stats
        await update.message.reply_text(
            f"✅ Admin Panel\n\n"
            f"Welcome, {user.first_name}!\n\n"
            f"📊 Your Stats:\n"
            f"• Files uploaded: {total_files}\n"
            f"• Storage used: {format_size(total_size)}\n"
            f"• Member since: {joined_date.strftime('%Y-%m-%d')}\n\n"
            f"📤 Send me any text, file, photo, video, audio, or voice message.\n"
            f"🔒 It will be copied to storage without forward signature.\n"
            f"🔗 You'll receive a private link (token) that anyone can use.\n\n"
            f"**Admin Commands:**\n"
            f"/stats - Bot statistics\n"
            f"/users - List all users\n"
            f"/broadcast - Send a message to all users (reply to a message)\n"
            f"/mylinks - Your recent files\n"
            f"/mystats - Your personal stats\n"
            f"/test - Test channel connection",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text(
            f"✅ Admin Panel\n\n"
            f"Welcome, {user.first_name}!\n\n"
            f"Send me a message or file to get started.\n\n"
            f"**Admin Commands:**\n"
            f"/stats - Bot statistics\n"
            f"/users - List all users\n"
            f"/broadcast - Send a message to all users (reply to a message)\n"
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
        f"📊 Bot Statistics\n\n"
        f"📁 Total files: {total_files}\n"
        f"💾 Total storage: {format_size(total_storage)}",
        disable_web_page_preview=True
    )

async def users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    all_users = get_all_users()
    if not all_users:
        await update.message.reply_text("No users found.")
        return

    message = "👥 **User List**\n\n"
    for u in all_users:
        user_id = u["user_id"]
        username = u["username"] or "N/A"
        first_name = u["first_name"] or "N/A"
        joined = u["joined_date"].strftime("%Y-%m-%d")
        files = u["total_files"]
        storage = format_size(u["total_size"])
        message += f"**ID:** {user_id}\n"
        message += f"**Name:** {first_name} (@{username})\n"
        message += f"**Joined:** {joined} | **Files:** {files} | **Storage:** {storage}\n\n"

    await update.message.reply_text(message, disable_web_page_preview=True)

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    # Must be a reply to a message
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Please reply to a message with /broadcast to send it to all users.")
        return

    broadcast_msg = update.message.reply_to_message
    all_users = get_all_users()
    if not all_users:
        await update.message.reply_text("No users to broadcast to.")
        return

    status_msg = await update.message.reply_text(f"📤 Broadcasting to {len(all_users)} users...")

    success = 0
    fail = 0
    for u in all_users:
        uid = u["user_id"]
        try:
            # Copy the exact message (with forward metadata if any)
            await broadcast_msg.copy(
                chat_id=uid,
                caption=broadcast_msg.caption,
                reply_markup=broadcast_msg.reply_markup
            )
            success += 1
        except Exception as e:
            logger.error(f"Failed to broadcast to {uid}: {e}")
            fail += 1
        await asyncio.sleep(0.05)  # rate limit

    await status_msg.edit_text(f"✅ Broadcast completed!\n\n📤 Sent to: {success}\n❌ Failed: {fail}")

async def mylinks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    files = get_user_files(user_id, limit=10)
    if not files:
        await update.message.reply_text("📭 No files found. Send me a file to get started!")
        return

    message = "📁 Your Recent Files (Last 10):\n\n"
    for i, file in enumerate(files, 1):
        file_name = file["file_name"] or "unknown"
        file_size = file["file_size"] or 0
        link = file["link"]
        uploaded_date = file["uploaded_date"]
        message += f"{i}. 📄 {file_name[:30]}\n"
        message += f"   💾 Size: {format_size(file_size)}\n"
        message += f"   🔗 {link}\n"
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
            f"📊 Your Statistics\n\n"
            f"📁 Total files: {total_files}\n"
            f"💾 Storage used: {format_size(total_size)}\n"
            f"📅 Member since: {joined_date.strftime('%Y-%m-%d')}",
            disable_web_page_preview=True
        )
    else:
        await update.message.reply_text("No statistics found. Upload a file to get started!")

async def test_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Unauthorized.")
        return

    if not STORAGE_CHANNEL:
        await update.message.reply_text("❌ STORAGE_CHANNEL_ID is not configured!")
        return

    try:
        result = await context.bot.send_message(
            chat_id=STORAGE_CHANNEL,
            text=f"✅ Test message from bot at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await update.message.reply_text(
            f"✅ Test successful!\n\n"
            f"Channel: {STORAGE_CHANNEL}\n"
            f"Message ID: {result.message_id}\n\n"
            f"Bot can post to the channel."
        )
    except Exception as e:
        logger.exception("Test failed")
        await update.message.reply_text(f"❌ Test failed!\n\nError: {str(e)[:200]}")

async def handle_incoming(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    msg = update.effective_message

    if not user or not msg:
        return

    # Only admin can upload files
    if user.id != ADMIN_ID:
        await msg.reply_text("⛔ Unauthorized.")
        return

    add_user(user.id, user.username, user.first_name)

    if not STORAGE_CHANNEL:
        await msg.reply_text("❌ STORAGE_CHANNEL_ID is not configured!")
        return

    processing_msg = await msg.reply_text("📤 Uploading to storage...")

    try:
        # Copy to storage channel
        copied = await context.bot.copy_message(
            chat_id=STORAGE_CHANNEL,
            from_chat_id=msg.chat_id,
            message_id=msg.message_id
        )

        stored_msg_id = copied.message_id
        file_id, file_name, file_size = extract_message_meta(msg)

        # Generate a unique token for this file
        token = secrets.token_urlsafe(8)
        link = save_file(user.id, file_id, file_name, file_size, stored_msg_id, token)

        update_user_stats(user.id, file_size)

        await processing_msg.edit_text(
            f"✅ File stored successfully!\n\n"
            f"📄 Name: {file_name}\n"
            f"💾 Size: {format_size(file_size)}\n"
            f"🔗 Link: {link}\n\n"
            f"🔒 Anyone with this link can download it.",
            disable_web_page_preview=True
        )

        logger.info("Stored message %s with token %s", stored_msg_id, token)

    except Exception as e:
        logger.exception("Error handling incoming message")
        await processing_msg.edit_text(f"❌ Error: {str(e)[:200]}")

# -------------------- Register Handlers --------------------
application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("stats", stats))
application.add_handler(CommandHandler("users", users))
application.add_handler(CommandHandler("broadcast", broadcast))
application.add_handler(CommandHandler("mylinks", mylinks))
application.add_handler(CommandHandler("mystats", mystats))
application.add_handler(CommandHandler("test", test_channel))

application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_incoming))

# -------------------- Flask Webhook --------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    update = Update.de_json(data, application.bot)

    future = asyncio.run_coroutine_threadsafe(
        application.process_update(update),
        BOT_LOOP
    )

    try:
        future.result(timeout=30)
    except Exception:
        logger.exception("Webhook processing failed")

    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

# -------------------- Main Entry --------------------
if __name__ == "__main__":
    init_db()

    BOT_LOOP = asyncio.new_event_loop()
    asyncio.set_event_loop(BOT_LOOP)

    async def setup():
        global BOT_USERNAME
        await application.initialize()
        await application.start()
        me = await application.bot.get_me()
        BOT_USERNAME = me.username
        logger.info("Bot username: @%s", BOT_USERNAME)

        render_url = os.getenv("RENDER_EXTERNAL_URL")
        if render_url:
            webhook_url = f"{render_url}/webhook"
            await application.bot.set_webhook(url=webhook_url)
            logger.info("Webhook set to: %s", webhook_url)
        else:
            logger.warning("RENDER_EXTERNAL_URL not found, webhook not set")

    BOT_LOOP.run_until_complete(setup())

    def run_flask():
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    try:
        BOT_LOOP.run_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        BOT_LOOP.run_until_complete(application.shutdown())
        BOT_LOOP.close()