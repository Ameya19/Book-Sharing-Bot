# Annie's Bookshelf — Telegram Book-Sharing Bot

A Telegram book-sharing bot built with **Flask + Telegram Bot API webhooks**. It is designed to run as a **Render Web Service**, including the free tier, and uses **MongoDB Atlas** for persistent bot data when `MONGODB_URI` is configured.

## Features

- 📚 PDF and EPUB book indexing and deep-link generation
- 🔎 Admin-only `/files` catalog with pagination
- 🔗 `/genlink` and `/batch` for generating book links
- ✏️ Rename indexed channel documents with `/rename`
- 🗑️ Remove stale catalog entries with `/removebook`
- 👥 Runtime admin management with `/addadmin`, `/removeadmin`, and `/listadmins`
- ⏱️ Configurable automatic deletion of delivered books
- 📢 Admin broadcast support
- 📊 Basic bot statistics and user management
- 💾 MongoDB persistence for files, admins, users, settings, and pending deletions
- 🌐 Flask webhook endpoint suitable for Render Web Services

## Commands

### 👤 User commands

These are the commands shown by `/help`:

| Command | Description |
|---|---|
| `/start` | Start the bot or open a book from a generated deep link |
| `/ping` | Check whether the bot is responding |
| `/help` | Show user commands |

> `/files` is **admin-only** and is intentionally not shown in the public `/help` message.

### 🛠️ Admin commands

Admins can use `/adminhelp` to see the admin command list.

| Command | Description |
|---|---|
| `/files` | View the indexed PDF/EPUB book catalog |
| `/rename` | Rename a channel document and update its index |
| `/removebook` | Remove a book from the `/files` index without deleting the channel post |
| `/genlink` | Generate a deep link for a channel post |
| `/batch` | Generate links for multiple channel posts |
| `/addadmin` | Add an admin by ID, username, or reply |
| `/removeadmin` | Remove an admin by ID, username, or reply |
| `/listadmins` | List configured admins |
| `/setautodelete` | Set automatic deletion duration |
| `/autodelete` | View the current automatic deletion setting |
| `/stats` | Show bot statistics/uptime |
| `/users` | View user information |
| `/broadcast` | Broadcast a replied message to users |
| `/adminhelp` | Show the admin command list |

Admin commands verify the user's Telegram ID before performing protected operations.

## Book file types

Only the following file extensions are supported:

- `.pdf`
- `.epub`

The extension check is case-insensitive. Unsupported files are rejected by book-link generation and are not displayed in `/files`.

## Book indexing

The bot builds its catalog from Telegram updates and supported admin workflows. Telegram's standard Bot API does **not** provide a general method for reading arbitrary historical channel posts, so an already-existing channel may need to be backfilled using the bot's supported link-generation workflows.

When MongoDB is configured, indexed files are persisted in the `files` collection, so the catalog does not need to be rebuilt after a normal Render restart or redeploy.

### Removing a book

`/removebook` removes a book from the bot's searchable catalog without deleting the original Telegram channel post:

```text
/removebook 1234
```

You can also provide a supported channel-post link.

This is useful when a channel post has been deleted and its old entry should no longer appear in `/files`.

## Rename a book

From a private admin chat:

1. Forward the document from the configured book channel to the bot.
2. Reply to the forwarded document with:

```text
/rename New Book Name.pdf
```

3. The bot downloads the source document, uploads the renamed document to the configured channel, updates the book index, creates the new link information, and removes the old channel post when possible.

> The public Telegram Bot API currently limits `getFile` downloads to **20 MB**. Larger files require a different Telegram API setup, such as a local Bot API server or an MTProto client.

## Automatic deletion

Books delivered through generated links can be automatically deleted from the user's chat. The original channel copy is not deleted.

Examples:

```text
/setautodelete 30s
/setautodelete 10m
/setautodelete 2h
/setautodelete 1d
/setautodelete 0
```

- `0` disables automatic deletion.
- `/autodelete` displays the current setting.
- Pending deletion jobs are persisted in MongoDB when MongoDB is configured.

> Render Free services can sleep. If the service is asleep when a deletion becomes due, cleanup can be delayed until the service wakes up and processes pending jobs. Exact deletion timing therefore cannot be guaranteed on a sleeping free service.

## MongoDB Atlas

MongoDB is optional for local development, but **recommended for Render deployment** when persistent state is required.

When `MONGODB_URI` is configured, the bot uses the database specified by `MONGODB_DB_NAME` and persists data including:

- `files` — indexed book/channel documents
- `admins` — runtime admins
- `settings` — persistent bot settings such as auto-delete configuration
- `pending_deletions` — scheduled/overdue deletion jobs
- `users` — known bot users
- `user_profiles` — stored user profile information

Recommended environment variables:

```text
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>/<database>
MONGODB_DB_NAME=book_sharing_bot
```

See [`MONGODB_RENDER_SETUP.md`](MONGODB_RENDER_SETUP.md) for the Render + MongoDB setup.

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `TG_BOT_TOKEN` | Yes | Token generated by BotFather |
| `CHANNEL_ID` | Yes | ID of the configured book/database channel, e.g. `-1001234567890` |
| `OWNER_ID` | Yes | Telegram user ID of the bot owner |
| `DEFAULT_ADMINS` | No | Permanent admin IDs separated by commas or spaces |
| `ADMINS` | No | Additional admin IDs separated by commas or spaces |
| `MONGODB_URI` | Recommended on Render | MongoDB Atlas connection string |
| `MONGODB_DB_NAME` | No | MongoDB database name; defaults to `book_sharing_bot` |
| `FORCE_SUB_CHANNEL` | No | Channel ID used for force subscription; `0` disables it |
| `START_MESSAGE` | No | Custom `/start` message |
| `START_PIC` | No | Optional/reserved start image setting |
| `FORCE_SUB_MESSAGE` | No | Custom force-subscription message |
| `CUSTOM_CAPTION` | No | Caption template for delivered documents |
| `PROTECT_CONTENT` | No | `True` enables Telegram content protection where supported |
| `AUTO_DELETE_TIME` | No | Initial auto-delete delay in seconds; `0` disables it |
| `DISABLE_CHANNEL_BUTTON` | No | `True` disables generated channel share buttons |
| `USER_REPLY_TEXT` | No | Default response to unsupported direct messages |
| `WEBHOOK_URL` | Yes on Render | Public Render service URL without a trailing `/` |
| `WEBHOOK_SECRET` | No | Secret token used to validate Telegram webhook requests |
| `DATA_DIR` | No | Directory for local fallback JSON state |

`APP_ID` and `API_HASH` are not required by this Flask/Telegram Bot API implementation.

## Admin persistence

`OWNER_ID` and `DEFAULT_ADMINS` are useful for permanent access because they are loaded on every startup.

Example:

```text
DEFAULT_ADMINS=123456789,987654321
```

Spaces are also supported:

```text
DEFAULT_ADMINS=123456789 987654321
```

`/removeadmin` cannot remove the owner or a user configured through `DEFAULT_ADMINS`. Remove the ID from the Render environment variable if that permanent access should be revoked.

When MongoDB is configured, runtime admins added with `/addadmin` are persisted in the `admins` collection and survive Render redeploys.

## Render deployment

Create a **Web Service** on Render.

### Build command

```bash
pip install -r requirements.txt
```

### Start command

```bash
gunicorn --workers 1 app:app
```

Set `WEBHOOK_URL` to your Render service URL, for example:

```text
https://your-service.onrender.com
```

The application exposes these useful endpoints:

| Endpoint | Purpose |
|---|---|
| `/health` | Health check |
| `/setwebhook` | Register the Telegram webhook |
| `/getwebhook` | View Telegram webhook status |
| `/deletewebhook` | Remove the Telegram webhook |
| `/webhook` | Telegram update endpoint |

After deployment, open `/setwebhook` once if the webhook has not been registered automatically.

## Telegram channel setup

1. Create the book/database channel.
2. Add the bot as an administrator.
3. Give the bot permission to post/edit messages and delete messages if `/rename` should replace old posts.
4. Set `CHANNEL_ID` to the channel ID.
5. Publish a PDF or EPUB document and verify that the bot receives the channel update.

## Local development

```bash
pip install -r requirements.txt
python main.py
```

For persistent local testing, configure `MONGODB_URI` and `MONGODB_DB_NAME` in your environment.

## Project structure

```text
Book-Sharing-Bot/
├── app.py
├── bot.py
├── config.py
├── main.py
├── helper_func.py
├── database/
├── plugins/
├── requirements.txt
├── Procfile
├── Dockerfile
├── MONGODB_RENDER_SETUP.md
└── README.md
```

## License

GNU GPLv3 — see [`LICENSE`](LICENSE).
