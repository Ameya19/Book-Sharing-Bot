# Annie's Bookshelf

A Telegram bot to share and access books from Annie's Bookshelf.

## Features

- List all available books with download links
- Search books by name
- Generate shareable links for single or multiple books
- Admin management system (add/remove admins)
- Broadcast messages to all users
- Force subscription to channel
- Auto-delete files after configurable time
- Deployable on Vercel, Railway, Render, or VPS

## Commands

### User Commands

| Command | Description |
|---|---|
| `/start` | Start the bot or download a book via link |
| `/files` | List all available books |
| `/help` | Show help message |
| `/ping` | Check bot response time |

### Admin Commands

| Command | Description |
|---|---|
| `/users` | Show total number of bot users |
| `/broadcast` | Send a message to all users |
| `/batch` | Generate a link for multiple books |
| `/genlink` | Generate a link for a single book |
| `/addadmin` | Add a new admin |
| `/removeadmin` | Remove an admin |
| `/listadmins` | List all admins |

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TG_BOT_TOKEN` | Yes | Bot token from @BotFather |
| `APP_ID` | Yes | API ID from my.telegram.org |
| `API_HASH` | Yes | API Hash from my.telegram.org |
| `CHANNEL_ID` | Yes | Database channel ID (e.g., -100xxxxxxxxxx) |
| `OWNER_ID` | Yes | Your Telegram user ID |
| `ADMINS` | No | Space-separated list of admin user IDs |
| `FORCE_SUB_CHANNEL` | No | Channel ID for force subscription (0 to disable) |
| `START_MESSAGE` | No | Custom start message |
| `START_PIC` | No | URL of image for start message |
| `FORCE_SUB_MESSAGE` | No | Custom force sub message |
| `CUSTOM_CAPTION` | No | Custom caption for files |
| `PROTECT_CONTENT` | No | Set to `True` to prevent forwarding |
| `AUTO_DELETE_TIME` | No | Auto-delete time in seconds (0 to disable) |
| `DISABLE_CHANNEL_BUTTON` | No | Set to `True` to disable channel button |
| `WEBHOOK_URL` | No | Your Vercel app URL (for Vercel deployment) |

## Deployment

### Local / VPS

```bash
git clone <your-repo-url>
cd Book-Sharing-Bot
pip install -r requirements.txt

# Set environment variables or create .env file
python main.py
```

### Vercel

1. Push code to GitHub
2. Import repo on [vercel.com](https://vercel.com)
3. Set environment variables in Vercel dashboard
4. Deploy
5. Visit `https://your-app.vercel.app/setwebhook` to register webhook

### Railway

1. Push code to GitHub
2. Create new project on [railway.app](https://railway.app)
3. Link your GitHub repo
4. Set environment variables
5. Deploy

### Render

1. Push code to GitHub
2. Create new Web Service on [render.com](https://render.com)
3. Link your GitHub repo
4. Set environment variables
5. Deploy

## Setup

1. Create a Telegram channel
2. Add the bot as admin with `Post Messages` permission
3. Get the channel ID from @RawDataBot
4. Set `CHANNEL_ID` environment variable
5. (Optional) Create a force sub channel and set `FORCE_SUB_CHANNEL`

## License

[GNU GPLv3](LICENSE)
