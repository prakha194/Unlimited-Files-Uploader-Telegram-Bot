# README.md

<div align="center">
  
# 📦 Telegram File Storage Bot

### Your Personal Unlimited Cloud Storage on Telegram

[![Deploy on Render](https://img.shields.io/badge/Deploy%20on-Render-blue?style=for-the-badge&logo=render)](https://render.com)
[![Python](https://img.shields.io/badge/Python-3.9+-blue?style=for-the-badge&logo=python)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.3.3-black?style=for-the-badge&logo=flask)](https://flask.palletsprojects.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue?style=for-the-badge&logo=postgresql)](https://postgresql.org)
[![Telegram Bot API](https://img.shields.io/badge/Telegram%20Bot%20API-6.9-blue?style=for-the-badge&logo=telegram)](https://core.telegram.org/bots)

**Free • Unlimited Storage • No Forward Signatures • Permanent Links**

</div>

---

## 🛠️ Tech Stack

<div align="center">
  
| Category | Technology | Badge |
|----------|------------|-------|
| **Language** | Python 3.9+ | ![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white) |
| **Framework** | Flask 2.3.3 | ![Flask](https://img.shields.io/badge/Flask-2.3.3-000000?logo=flask&logoColor=white) |
| **Bot Library** | python-telegram-bot 20.7 | ![Telegram](https://img.shields.io/badge/Telegram%20Bot-20.7-26A5E4?logo=telegram&logoColor=white) |
| **Database** | PostgreSQL 15 | ![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1?logo=postgresql&logoColor=white) |
| **Hosting** | Render | ![Render](https://img.shields.io/badge/Render-Deployed-46E3B7?logo=render&logoColor=white) |
| **Web Server** | Gunicorn | ![Gunicorn](https://img.shields.io/badge/Gunicorn-20.1-499848?logo=gunicorn&logoColor=white) |

</div>

---

## ✨ Features

| Feature | Description | Status |
|---------|-------------|--------|
| 📤 **Unlimited Storage** | Store files up to 2GB each on Telegram's free servers | ✅ |
| 🔗 **Permanent Links** | Get instant, never-expiring download links | ✅ |
| 🚫 **No Forward Signatures** | Files appear as directly uploaded by the bot | ✅ |
| 👥 **Channel Verification** | Users must join your channel before using | ✅ |
| 📊 **User Statistics** | Track files, storage usage per user | ✅ |
| 👑 **Admin Controls** | Broadcast messages, view all users, total stats | ✅ |
| 💾 **Persistent Database** | PostgreSQL storage that survives redeploys | ✅ |
| ⚡ **Fast Webhook** | Instant response with Flask webhook | ✅ |
| 📈 **Real-time Analytics** | Daily uploads, storage trends, user activity | ✅ |

---

## 🎯 Bot Commands

### 👤 User Commands

| Command | Description |
|---------|-------------|
| `/start` | Verify channel membership and view your stats |
| `/mylinks` | Show your last 10 uploaded files with links |
| `/mystats` | View your personal storage statistics |

### 👑 Admin Commands

| Command | Description |
|---------|-------------|
| `/stats` | View overall bot statistics (users, files, storage) |
| `/users` | List all users with their file counts and storage |
| `/broadcast` | Send messages to all users (reply to any message) |

---

## 🚀 Quick Deploy (Render)

### Step 1: Prerequisites
- Bot Token from [@BotFather](https://t.me/botfather)
- Your Telegram User ID from [@userinfobot](https://t.me/userinfobot)
- Private Channel ID from [@get_id_bot](https://t.me/get_id_bot)
- Required Channel Username (with @)

### Step 2: Create PostgreSQL Database on Render
1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click **New +** → **PostgreSQL**
3. Select **Free** tier
4. Name: `telegram-bot-db`
5. Click **Create Database**
6. Copy the **Internal Database URL**

### Step 3: Deploy Bot on Render
1. Push code to GitHub
2. On Render: **New +** → **Web Service**
3. Connect your GitHub repository
4. Configure:
   - Name: `telegram-storage-bot`
   - Environment: `Python 3`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `python bot.py`
5. Add Environment Variables:
   - `BOT_TOKEN` = your_bot_token_here
   - `ADMIN_ID` = 123456789
   - `STORAGE_CHANNEL_ID` = -1001234567890
   - `REQUIRED_CHANNEL` = @yourchannel
   - `DATABASE_URL` = postgresql://... (from step 2)
6. Click **Deploy Web Service**

### Step 4: Set Bot Commands
Message [@BotFather](https://t.me/botfather):

/setcommands
Select your bot and paste:

start - Start the bot and verify channel membership
mylinks - View your uploaded files and links
mystats - View your personal storage statistics
stats - View bot statistics (Admin only)
users - View all users list (Admin only)
broadcast - Send message to all users (Admin only)

---

## 📁 Project Structure
telegram-storage-bot/
├── bot.py              # Main bot code (Flask + Telegram)
├── requirements.txt    # Python dependencies
├── README.md          # Documentation
└── .env               # Environment variables (not committed)

env.example-
```env
BOT_TOKEN=your_bot_token_here
ADMIN_ID=123456789
STORAGE_CHANNEL_ID=-1001234567890
REQUIRED_CHANNEL=@yourchannel
DATABASE_URL=postgresql://user:pass@host:port/dbname
```

