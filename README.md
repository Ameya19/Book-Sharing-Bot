# Annie's Bookshelf — Flask Webhook Bot

Telegram book-sharing bot using **Flask + Telegram Bot API webhooks**. It is designed to run as a Render Web Service (including the free tier).

## Commands

### User commands

| Command | Description |
|---|---|
| `/start` | Start the bot or open a book from a generated deep link |
| `/files` | List files currently present in the bot's file index |
| `/help` | Show available commands |
| `/ping` | Check bot response time |

### Admin commands

| Command | Description |
|---|---|
| `/users` | Show total bot users |
| `/broadcast` | Broadcast a replied message to users |
| `/batch` | Generate a deep link for a range of channel posts |
| `/genlink` | Generate a deep link for a channel post |
| `/addadmin` | Add an admin by ID, username, or reply |
| `/removeadmin` | Remove an admin by ID, username, or reply |
| `/listadmins` | List admins |
| `/stats` | Show bot uptime |
| `/rename` | Rename an indexed DB-channel document |

## Important `/files` behavior

Telegram's standard Bot API does **not** provide a method for reading arbitrary historical channel messages. Therefore `/files` is populated from:

1. New `channel_post` updates received after the webhook is active.
2. Files uploaded to the bot by an admin.
3. Existing channel documents that an admin forwards to the bot while using `/genlink` or `/batch`.

This means an old channel can be backfilled by forwarding its book posts to the bot. The file index is stored locally in `files_index.json`; Render's free filesystem is ephemeral, so the index can be lost after a restart/redeploy. Use a persistent database if you need the `/files` catalog to survive restarts.

## Important `/rename` behavior

Use `/rename` from a private admin chat:

1. Forward the document from the DB channel to the bot.
2. Reply to that forwarded document with `/rename New Book Name.pdf`.
3. The bot downloads the document, uploads it to the DB channel with the new filename, updates `/files`, adds a new deep link, and removes the old DB-channel post.

The public Telegram Bot API currently limits `getFile` downloads to **20 MB**, so this Flask implementation can rename documents up to 20 MB. Larger files require a different Telegram API setup (for example, a local Bot API server or an MTProto client).

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `TG_BOT_TOKEN` | Yes | Token from BotFather |
| `CHANNEL_ID` | Yes | DB channel ID, e.g. `-1001234567890` |
| `OWNER_ID` | Yes | Telegram user ID of the bot owner |
| `ADMINS` | No | Space-separated admin user IDs |
| `FORCE_SUB_CHANNEL` | No | Channel ID for force subscription; `0` disables it |
| `START_MESSAGE` | No | Custom start message |
| `START_PIC` | No | Reserved start image setting |
| `FORCE_SUB_MESSAGE` | No | Custom force-subscription message |
| `CUSTOM_CAPTION` | No | Caption template for delivered documents |
| `PROTECT_CONTENT` | No | `True` prevents forwarding/saving where supported |
| `AUTO_DELETE_TIME` | No | Auto-delete delay in seconds; `0` disables it |
| `DISABLE_CHANNEL_BUTTON` | No | `True` disables generated share buttons on channel posts |
| `USER_REPLY_TEXT` | No | Default reply to unsupported direct messages |
| `WEBHOOK_URL` | Yes on Render | Public service URL, e.g. `https://your-service.onrender.com` |
| `WEBHOOK_SECRET` | No | Secret token used to validate Telegram webhook requests |
| `DATA_DIR` | No | Directory for JSON state files; defaults to project directory |

`APP_ID` and `API_HASH` are **not required** by the Flask/Telegram Bot API version.

## Render deployment

Use a **Web Service** with:

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn --workers 1 app:app`

Set `WEBHOOK_URL` to the Render service URL, without a trailing `/`.

The app also exposes:

- `/health` — health check
- `/setwebhook` — registers the webhook
- `/getwebhook` — shows Telegram webhook status
- `/deletewebhook` — removes the webhook

After deployment, open `/setwebhook` once if the webhook was not automatically registered.

## Telegram channel setup

1. Create the DB channel.
2. Add the bot as an administrator.
3. Give it permission to post/edit messages and delete messages if you want `/rename` to replace old posts.
4. Set `CHANNEL_ID` to the channel ID.
5. Publish a new document to verify that `/files` receives the `channel_post` update.

## Local run

```bash
pip install -r requirements.txt
python main.py
```

## License

GNU GPLv3 — see `LICENSE`.
