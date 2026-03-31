# Telegram File Storage Bot

[![Deploy on Render](https://img.shields.io/badge/Deploy%20on-Render-blue?style=for-the-badge&logo=render)](https://render.com)
[![Python](https://img.shields.io/badge/Python-3.9+-blue?logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Unlimited Telegram storage • No forward signatures • Permanent links**

## Features
- Store any file (up to 2GB) – documents, photos, videos, audio, text
- Forwarded files lose all sender signatures
- Permanent download links (never expire)
- Admin-only access
- PostgreSQL database (persistent across redeploys)
- Built-in stats: total files, storage used, recent links

## Commands
| Command | Description |
|---------|-------------|
| `/start` | Welcome & your stats |
| `/stats` | Bot totals (files, storage) |
| `/mylinks` | Last 10 files with links |
| `/mystats` | Your personal usage |
| `/test` | Check channel connectivity |

Any non-command message (file or text) is saved automatically.

## Deploy on Render

### 1. Prerequisites
- Bot token from [@BotFather](https://t.me/botfather)
- Your Telegram user ID (from [@userinfobot](https://t.me/userinfobot))
- A Telegram channel (public or private) – bot must be **admin**
  - Public: use `@channelusername`
  - Private: numeric ID (e.g., `-1001234567890`)

### 2. Create PostgreSQL database on Render
- New → PostgreSQL → Free tier → copy **Internal Database URL**

### 3. Deploy web service
- New → Web Service → connect GitHub repo
- Build: `pip install -r requirements.txt`
- Start: `python bot.py`
- Add environment variables:
  - `BOT_TOKEN`
  - `ADMIN_ID`
  - `STORAGE_CHANNEL_ID`
  - `DATABASE_URL`

## Environment Variables
```env
BOT_TOKEN=your_bot_token
ADMIN_ID=your_telegram_id
STORAGE_CHANNEL_ID=@channel_or_numeric_id
DATABASE_URL=postgresql://...