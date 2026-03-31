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
import sqlite3
from contextlib import closing

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

# Flask app
app = Flask(__name__)

# Database setup
DB_PATH = "users.db"

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                joined BOOLEAN DEFAULT 0
            )
        """)
        conn.commit()

def add_user(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,)
        )
        conn.commit()

def set_user_joined(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute(
            "UPDATE users SET joined = 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()

def is_user_joined(user_id):
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute(
            "SELECT joined FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        return row is not None and row[0] == 1

def get_all_users():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        cursor = conn.execute("SELECT user_id FROM users")
        return [row[0] for row in cursor.fetchall()]

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

# -------------------- Handlers --------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)

    if is_user_joined(user_id):
        await update.message.reply_text(
            "✅ **You are already verified!**\n\n"
            "📤 **Send me any file** (up to 2GB) and I'll give you a permanent download link.\n\n"
            "🔗 Links never expire and have no forward signatures."
        )
        return

    keyboard = [
        [InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{REQUIRED_CHANNEL.lstrip('@')}")],
        [InlineKeyboardButton("✅ I've Joined", callback_data="verify")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"🎬 **Welcome to File Storage Bot!**\n\n"
        f"To use this bot, you must first join our channel:\n"
        f"👉 @{REQUIRED_CHANNEL.lstrip('@')}\n\n"
        f"After joining, click the button below.",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )

async def verify_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = update.effective_user.id

    if await is_member(user_id):
        set_user_joined(user_id)
        await query.edit_message_text(
            "✅ **Verification successful!**\n\n"
            "Now you can send me any file (up to 2GB) and I'll give you a permanent download link.\n\n"
            "📎 Just send a photo, video, document, or any file.\n"
            "🔗 The link will be your direct access — no forward signatures."
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

async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_user_joined(user_id):
        if await is_member(user_id):
            set_user_joined(user_id)
        else:
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

            await processing_msg.delete()
            await update.message.reply_text(
                f"✅ **File stored successfully!**\n\n"
                f"🔗 **Your link:**\n{link}\n\n"
                f"💾 **Permanent** | 🔒 **No forward signature** | 📁 **Up to 2GB**",
                disable_web_page_preview=True
            )
            logger.info(f"User {user_id} stored file -> {link}")
    except Exception as e:
        logger.error(f"Error storing file: {e}")
        await processing_msg.edit_text("❌ Failed to store file. Please try again later.")

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

    await update.message.reply_text(f"✅ Broadcast sent to {success} users. Failed: {fail}")

# Register handlers
application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(verify_callback, pattern="verify"))
application.add_handler(MessageHandler(filters.ATTACHMENT, handle_file))
application.add_handler(CommandHandler("broadcast", broadcast))

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
    # Set webhook (asynchronously)
    render_url = os.getenv("RENDER_EXTERNAL_URL")
    if render_url:
        webhook_url = f"{render_url}/webhook"
        # Run the async set_webhook function
        asyncio.run(application.bot.set_webhook(url=webhook_url))
        logger.info(f"Webhook set to: {webhook_url}")
    else:
        logger.warning("RENDER_EXTERNAL_URL not found, webhook not set")

    # Start Flask server
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)