# Telegram Bot

Telegram user-account manager with a desktop GUI. Reply workflows use Google Gemini (primary) and OpenAI GPT-4o-mini (fallback), with a built-in conversion funnel, human-like delays, and per-account credential management.

This repository is **source code only** (run with Python). For **Windows installers**, PyInstaller/Inno Setup, bundled **Visual C++ redistributable** (for PyTorch / ML classifiers / NSFW on clean PCs), and optional **baked Cloudflare Worker URL** for end users, use **[tgbot-for-client](https://github.com/adrrnnn/tgbot-for-client)**.

---

## ⚠️ Legal Notice

This app operates in **user-account mode** via Pyrogram, not the official Bot API. Automating a personal Telegram account technically violates Telegram's ToS. Use it at your own risk and be aware that people you're messaging will not know they're talking to automation.

---

## Requirements

- Python 3.10+
- Windows (tested), macOS/Linux should work
- A Cloudflare Worker serving your API keys (see setup below)
- Telegram API credentials from [my.telegram.org/apps](https://my.telegram.org/apps)

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure the app

Copy `config/config.example.json` to `config/config.json` and fill in:

```json
{
  "cloudflare": {
    "worker_url": "https://your-worker.workers.dev",
    "auth_token": "your-secret-token"
  },
  "bot": {
    "of_link": "https://onlyfans.com/yourprofile"
  }
}
```

API keys (OpenAI, Gemini) are fetched at runtime from your Cloudflare Worker and never stored locally.

### 3. Run the app

```bash
python main.py
```

### 4. Add a Telegram account

In the **Accounts** tab, click **Add Account** and fill in:
- Account name
- Phone number (with country code)
- API ID and API Hash (get these from [my.telegram.org/apps](https://my.telegram.org/apps))

The app sends a login code first. If your account has **two-step verification**, you are prompted for the cloud password after the code (you can skip and finish login later via **Re-login**).

### 5. Create a profile

In the **Profiles** tab, create a persona with a name, age, location, and any custom instructions. Set it as active.

### 6. Start the bot

Go to the **Start Bot** tab and click **Start**. Use **Pause** to temporarily stop replies without disconnecting.

---

## Project Structure

```
Telegram Bot/
├── main.py                          # Entry point
├── requirements.txt
├── config/
│   ├── config.json                  # Your config (gitignored)
│   └── config.example.json          # Template
├── src/
│   ├── bot_server.py                # Pyrogram client + reconnect logic
│   ├── config.py                    # Config manager
│   ├── database.py                  # SQLite schema + query helpers
│   ├── llm.py                       # Gemini + OpenAI integration
│   ├── classifier.py                # Conversation state classifier
│   ├── interceptor.py               # Keyword + intent funnel
│   ├── nsfw_detector.py             # Local DistilBERT NSFW detection
│   ├── handlers/
│   │   └── ai_reply_handler.py      # Core message handler
│   └── ui/
│       ├── main_gui.py              # Main window
│       └── tabs/
│           ├── accounts_tab.py
│           ├── profiles_tab.py
│           ├── start_bot_tab.py
│           ├── link_tab.py
│           ├── reset_tab.py
│           └── settings_tab.py
├── pyrogram_sessions/               # Session files (gitignored)
├── telegrambot.db                   # SQLite database (gitignored)
└── logs/
    └── bot.log                      # App logs (gitignored)
```

---

## Cloudflare Worker Setup

The bot fetches API keys (Gemini, OpenAI) from a Cloudflare Worker at startup. Keys live encrypted in Cloudflare's environment, never on your machine.

### 1. Create the worker

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com)
2. Click **Workers & Pages** → **Create application** → **Create Worker**
3. Name it anything (e.g. `telegram-bot-keys`) and click **Deploy**
4. Open the worker editor, replace all code with the contents of `cloudflare_worker.js` (included in this repo), then save and deploy

### 2. Set environment variables

In the worker's **Settings → Environment variables**, add:

| Variable | Value |
|----------|-------|
| `BOT_AUTH_TOKEN` | Any random secret string you make up |
| `GEMINI_API_KEY` | From [ai.google.dev](https://ai.google.dev/) |
| `OPENAI_API_KEY` | From [platform.openai.com/api-keys](https://platform.openai.com/api-keys) (optional) |

Mark each one as **Encrypted**, then deploy again.

### 3. Add to config.json

```json
{
  "cloudflare": {
    "enabled": true,
    "worker_url": "https://your-worker.your-name.workers.dev",
    "auth_token": "the-same-token-you-set-in-cloudflare",
    "fallback_to_local": false
  }
}
```

`fallback_to_local: false` means the bot will refuse to start if Cloudflare is unreachable. That way keys are never accidentally missing.

### Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| 401 Unauthorized | `auth_token` doesn't match `BOT_AUTH_TOKEN` | Copy the exact token from Cloudflare env vars |
| 404 Not Found | Wrong worker URL | Go to Cloudflare dashboard and copy the URL from the worker's page |
| Cloudflare unreachable | Network issue or worker offline | Check your internet; verify worker is deployed at dash.cloudflare.com |
| Keys loaded but no replies | API quota exhausted | Replace the key in Cloudflare env vars (no bot restart needed) |

### Rotating keys (no restart needed)

Update the environment variable in the Cloudflare dashboard. Every new request the bot makes will pick up the new key automatically.

---

## How It Works

**Message flow:**
1. Incoming private message → batched over a 10-second window (handles double/triple texting)
2. Keyword interceptor checks for funnel triggers (photo requests, social handle requests, OF refusals)
3. If interceptor fires, a scripted reply goes out and `_of_link_pending` is set
4. NSFW detector (local DistilBERT) scans for subtle intent that bypassed keywords
5. Conversation state classifier labels the user's engagement level (warm / cold / skeptical / hostile)
6. LLM generates a reply using the active profile's system prompt + conversation history
7. Human-like reading delay + typing indicator → message sent
8. Rate limit enforced (minimum 8 seconds between replies per chat)

**Conversion funnel:**
- Interceptor deflects photo/contact requests with a scripted line
- On the user's next message, the bot naturally drops the OF link through the LLM
- After the link is sent, one final reply is allowed, then the bot goes silent on that chat
- Users who explicitly decline to subscribe are marked done immediately

**API keys:**
Keys are fetched from a Cloudflare Worker at startup and never written to disk. The Cloudflare `auth_token` in `config.json` is the only credential that lives locally.

---

## Settings

| Setting | Location | What it does |
|---------|----------|-------------|
| Debug logging | Settings tab | When on, message content is written to `logs/bot.log`. Off by default. |
| Reset bot | Settings tab | Wipes conversation state so the bot treats all users as new |
| Pause | Start Bot tab | Suspends replies without disconnecting the Pyrogram session |

---

## Troubleshooting

**Bot doesn't reply**
- Check that a profile is set as active in the Profiles tab
- Check that the Cloudflare worker URL and auth token are correct. Without API keys the LLM can't generate replies.
- Turn on debug logging and check `logs/bot.log`

**Wrong or expired verification code**
- The app will tell you and immediately re-prompt. Just enter the correct code.

**Session expired / AuthKeyUnregistered**
- Delete the session file in `pyrogram_sessions/` and restart. You'll go through phone auth again.

**NSFW detector fails to load**
- The DistilBERT model requires `transformers` and `torch`. Check your install with `pip show transformers torch`
- The bot falls back gracefully if the model can't load, it just won't do local NSFW scoring

---

## Security

- `config.json`, `telegrambot.db`, `pyrogram_sessions/`, and `logs/` are all gitignored
- API keys (OpenAI, Gemini) are never stored on disk, they're fetched from Cloudflare at runtime
- Message content is only written to log files when debug mode is explicitly turned on
- Session files are unencrypted on disk, so keep your machine and that folder private
