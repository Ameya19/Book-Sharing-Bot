import os
import re
import json
import time
import base64
import threading
from html import escape
from datetime import datetime
from pathlib import Path
import tempfile

import requests
from flask import Flask, request, jsonify

# ============================================================
# Flask + Telegram Bot API version of Book-Sharing-Bot
# This version does NOT use Pyrogram polling.
# Telegram sends updates to /webhook.
# ============================================================

app = Flask(__name__)

BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("TG_BOT_TOKEN (or BOT_TOKEN) is required")

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "0"))
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

ADMINS = set()
for value in os.environ.get("ADMINS", "").split():
    try:
        ADMINS.add(int(value))
    except ValueError:
        pass
if OWNER_ID:
    ADMINS.add(OWNER_ID)

FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "0"))
JOIN_REQUEST_ENABLE = os.environ.get("JOIN_REQUEST_ENABLED", "").lower() == "true"

START_PIC = os.environ.get("START_PIC", "")
START_MSG = os.environ.get(
    "START_MESSAGE",
    "Hello {first}. I am book sharing bot which will help you get the books "
    "which are agreed to read by people in anime discussion 2.0."
)
FORCE_MSG = os.environ.get(
    "FORCE_SUB_MESSAGE",
    "Hello {first}\n\n<b>You need to join in my Channel/Group to use me\n\n"
    "Kindly Please join Channel</b>"
)
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION") or None
PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False").lower() == "true"
AUTO_DELETE_TIME = int(os.environ.get("AUTO_DELETE_TIME", "0"))
AUTO_DELETE_MSG = os.environ.get(
    "AUTO_DELETE_MSG",
    "This file will be automatically deleted in {time} seconds. "
    "Please ensure you have saved any necessary content before this time."
)
AUTO_DEL_SUCCESS_MSG = os.environ.get(
    "AUTO_DEL_SUCCESS_MSG",
    "Your file has been successfully deleted. Thank you for using our service. ✅"
)
DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", "False").lower() == "true"
USER_REPLY_TEXT = os.environ.get(
    "USER_REPLY_TEXT",
    "❌Don't send me messages directly I'm only File Share bot!"
)
BOT_STATS_TEXT = "<b>BOT UPTIME</b>\n{uptime}"

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")

STARTED_AT = time.time()
BOT_USERNAME = None
CHANNEL_USERNAME = None
BOT_ME = None

DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
USERS_FILE = DATA_DIR / "users.json"
USER_PROFILES_FILE = DATA_DIR / "user_profiles.json"
ADMINS_FILE = DATA_DIR / "admins.json"
FILES_FILE = DATA_DIR / "files_index.json"

state_lock = threading.RLock()
pending_actions = {}  # user_id -> {"type": "genlink"|"batch", "step": 1|2}

session = requests.Session()
API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ------------------------- persistence -------------------------

def load_json(path, default):
    try:
        if path.exists():
            with path.open("r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as exc:
        print(f"Could not read {path}: {exc}")
    return default


def save_json(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


users = set(int(x) for x in load_json(USERS_FILE, []) if str(x).lstrip("-").isdigit())
# Maps normalized Telegram usernames to user IDs for users who have interacted with the bot.
user_profiles = load_json(USER_PROFILES_FILE, {})
stored_admins = set(int(x) for x in load_json(ADMINS_FILE, []) if str(x).lstrip("-").isdigit())
ADMINS.update(stored_admins)

# File index contains channel messages seen since this Flask webhook was installed.
# Telegram Bot API does not provide a "read channel history" method.
file_index = load_json(FILES_FILE, [])


def add_user(user_id, user=None):
    with state_lock:
        if user_id not in users:
            users.add(user_id)
            save_json(USERS_FILE, sorted(users))

        if user:
            username = (user.get("username") or "").strip().lstrip("@").lower()
            if username:
                user_profiles[username] = {
                    "id": user_id,
                    "username": user.get("username"),
                    "first_name": user.get("first_name", ""),
                    "last_name": user.get("last_name", "")
                }
                save_json(USER_PROFILES_FILE, user_profiles)


def resolve_user_id(identifier, message=None):
    """Resolve a numeric Telegram ID or a username to a user ID.

    Telegram Bot API cannot resolve an arbitrary person's @username to an ID.
    Username lookup therefore works for users who have previously interacted
    with this bot (their username is stored from incoming updates). A reply to
    a user's message is also supported and is the most reliable method.
    """
    if not identifier:
        return None, "Please provide a user ID or @username."

    value = identifier.strip()

    if value.lstrip("-").isdigit():
        return int(value), None

    username = value.lstrip("@").lower()

    if message:
        reply = message.get("reply_to_message") or {}
        replied_user = reply.get("from") or {}
        replied_username = (replied_user.get("username") or "").lower()
        if replied_user.get("id") and (not username or replied_username == username):
            return int(replied_user["id"]), None

    profile = user_profiles.get(username)
    if profile and profile.get("id"):
        return int(profile["id"]), None

    return None, (
        f"I couldn't find @{username}. The user must first start or interact with "
        "this bot so Telegram provides their user ID. Alternatively, reply to "
        "one of their messages with the admin command."
    )


def remove_user(user_id):
    with state_lock:
        users.discard(user_id)
        save_json(USERS_FILE, sorted(users))


def persist_admins():
    save_json(ADMINS_FILE, sorted(x for x in ADMINS if x != OWNER_ID))


# ------------------------- Telegram API -------------------------

def tg(method, payload=None, timeout=30):
    response = session.post(
        f"{API}/{method}",
        json=payload or {},
        timeout=timeout
    )
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data["result"]


def tg_get(method, params=None, timeout=30):
    response = session.get(
        f"{API}/{method}",
        params=params or {},
        timeout=timeout
    )
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method} failed: {data}")
    return data["result"]


def send_message(chat_id, text, reply_markup=None, reply_to=None, disable_preview=False):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": disable_preview,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    if reply_to is not None:
        payload["reply_parameters"] = {"message_id": reply_to}
    return tg("sendMessage", payload)


def edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return tg("editMessageText", payload)


def delete_message(chat_id, message_id):
    try:
        return tg("deleteMessage", {
            "chat_id": chat_id,
            "message_id": message_id
        })
    except Exception as exc:
        print(f"deleteMessage failed: {exc}")
        return False


def answer_callback(callback_id, text=None):
    payload = {"callback_query_id": callback_id}
    if text:
        payload["text"] = text
    try:
        return tg("answerCallbackQuery", payload)
    except Exception as exc:
        print(f"answerCallbackQuery failed: {exc}")


def copy_message(from_chat_id, message_id, to_chat_id, caption=None, reply_markup=None):
    payload = {
        "chat_id": to_chat_id,
        "from_chat_id": from_chat_id,
        "message_id": message_id,
        "protect_content": PROTECT_CONTENT,
    }
    if caption is not None:
        payload["caption"] = caption
        payload["parse_mode"] = "HTML"
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup
    return tg("copyMessage", payload)


def edit_reply_markup(chat_id, message_id, reply_markup):
    return tg("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": reply_markup
    })


# ------------------------- helpers -------------------------

def encode(value):
    return base64.urlsafe_b64encode(value.encode("ascii")).decode("ascii").rstrip("=")


def decode(value):
    value = value.strip("=")
    raw = (value + "=" * (-len(value) % 4)).encode("ascii")
    return base64.urlsafe_b64decode(raw).decode("ascii")


def user_fields(user):
    first = escape(user.get("first_name") or "")
    last = escape(user.get("last_name") or "")
    username = user.get("username")
    username_display = "@" + escape(username) if username else ""
    uid = user.get("id")
    mention = f'<a href="tg://user?id={uid}">{first}</a>'
    return {
        "first": first,
        "last": last,
        "username": username_display,
        "mention": mention,
        "id": uid,
    }


def is_admin(user_id):
    return user_id in ADMINS


def is_private(message):
    return message.get("chat", {}).get("type") == "private"


def command_parts(message):
    text = message.get("text", "")
    if not text.startswith("/"):
        return None, []
    parts = text.split()
    command = parts[0].split("@", 1)[0].lower()
    return command, parts[1:]


def user_message(message):
    return message.get("from") or {}


def user_id(message):
    return int(user_message(message).get("id", 0))


def make_start_text(user):
    return START_MSG.format(**user_fields(user))


def make_force_text(user):
    return FORCE_MSG.format(**user_fields(user))


def bot_link(payload=""):
    username = BOT_USERNAME or ""
    return f"https://t.me/{username}" + (f"?start={payload}" if payload else "")


def share_button(url):
    return {
        "inline_keyboard": [[
            {
                "text": "🔁 Share URL",
                "url": f"https://telegram.me/share/url?url={url}"
            }
        ]]
    }


def close_button():
    return {"inline_keyboard": [[{"text": "🔒 Close", "callback_data": "close"}]]}


def about_markup():
    return {"inline_keyboard": [[{"text": "Close", "callback_data": "close"}]]}


def force_sub_markup(start_arg=None):
    buttons = []
    try:
        if JOIN_REQUEST_ENABLE:
            invite = tg("createChatInviteLink", {
                "chat_id": FORCE_SUB_CHANNEL,
                "creates_join_request": True
            })
            url = invite["invite_link"]
        else:
            chat = tg("getChat", {"chat_id": FORCE_SUB_CHANNEL})
            url = chat.get("invite_link")
            if not url:
                invite = tg("createChatInviteLink", {"chat_id": FORCE_SUB_CHANNEL})
                url = invite["invite_link"]
        buttons.append([{"text": "Join Channel", "url": url}])
    except Exception as exc:
        print(f"Could not create force-sub link: {exc}")

    if start_arg:
        buttons.append([{
            "text": "Try Again",
            "url": bot_link(start_arg)
        }])
    return {"inline_keyboard": buttons}


def subscribed(user_id_value):
    if not FORCE_SUB_CHANNEL or is_admin(user_id_value):
        return True
    try:
        member = tg("getChatMember", {
            "chat_id": FORCE_SUB_CHANNEL,
            "user_id": user_id_value
        })
        status = member.get("status")
        return status in ("creator", "administrator", "member")
    except Exception as exc:
        print(f"getChatMember failed: {exc}")
        return False


def file_info_from_message(message):
    for kind in ("document", "video", "audio", "photo"):
        if kind not in message:
            continue
        value = message[kind]
        if kind == "photo":
            value = value[-1] if isinstance(value, list) else value
            name = "Photo"
            size = value.get("file_size")
            file_id = value.get("file_id")
        else:
            name = value.get("file_name") or kind.title()
            size = value.get("file_size")
            file_id = value.get("file_id")
        return {
            "message_id": message.get("message_id"),
            "type": kind,
            "file_name": name,
            "file_size": size,
            "chat_id": message.get("chat", {}).get("id"),
            "caption": message.get("caption") or "",
            "file_id": file_id,
        }
    return None


def format_size(size_bytes):
    if size_bytes is None:
        return "Unknown size"
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def add_file_index(message):
    info = file_info_from_message(message)
    if not info or not info.get("message_id"):
        return
    with state_lock:
        existing = [x for x in file_index if x.get("message_id") != info["message_id"]]
        existing.append(info)
        file_index[:] = existing[-5000:]
        save_json(FILES_FILE, file_index)


def message_id_from_link_or_forward(message):
    # New Bot API format: forward_origin.type == "channel"
    origin = message.get("forward_origin")
    if origin and origin.get("type") == "channel":
        chat = origin.get("chat", {})
        if int(chat.get("id", 0)) == CHANNEL_ID:
            return int(origin.get("message_id", 0))

    # Legacy-compatible fields, if present
    fchat = message.get("forward_from_chat")
    if fchat and int(fchat.get("id", 0)) == CHANNEL_ID:
        return int(message.get("forward_from_message_id", 0))

    text = message.get("text") or ""
    pattern = r"^https?://t\.me/(?:c/)?([^/\s]+)/(\d+)"
    match = re.match(pattern, text)
    if not match:
        return 0

    channel_part, msg_id = match.groups()
    msg_id = int(msg_id)
    if channel_part.isdigit():
        if f"-100{channel_part}" == str(CHANNEL_ID):
            return msg_id
    else:
        if CHANNEL_USERNAME and channel_part.lower() == CHANNEL_USERNAME.lower():
            return msg_id
    return 0


def lookup_file_info(message_id):
    for item in file_index:
        if int(item.get("message_id", 0)) == int(message_id):
            return item
    return None


def get_start_ids(argument):
    decoded = decode(argument)
    pieces = decoded.split("-")
    if pieces[0] != "get":
        return []

    if len(pieces) == 2:
        try:
            return [int(int(pieces[1]) / abs(CHANNEL_ID))]
        except Exception:
            return []

    if len(pieces) == 3:
        try:
            start = int(int(pieces[1]) / abs(CHANNEL_ID))
            end = int(int(pieces[2]) / abs(CHANNEL_ID))
        except Exception:
            return []
        if start <= end:
            return list(range(start, end + 1))
        return list(range(start, end - 1, -1))
    return []


# ------------------------- command handlers -------------------------

def handle_start(message, argument=None):
    uid = user_id(message)
    add_user(uid)

    if not subscribed(uid):
        send_message(
            message["chat"]["id"],
            make_force_text(user_message(message)),
            reply_markup=force_sub_markup(argument),
            reply_to=message.get("message_id"),
            disable_preview=True
        )
        return

    if argument:
        try:
            ids = get_start_ids(argument)
        except Exception:
            ids = []

        if not ids:
            send_message(message["chat"]["id"], "Something went wrong..!")
            return

        temp = send_message(message["chat"]["id"], "Please wait...")
        copied = []

        for msg_id in ids:
            info = lookup_file_info(msg_id)
            caption = None
            if info and CUSTOM_CAPTION and info.get("type") == "document":
                try:
                    caption = CUSTOM_CAPTION.format(
                        previouscaption=info.get("caption") or "",
                        filename=info.get("file_name") or ""
                    )
                except Exception:
                    caption = None

            try:
                result = copy_message(
                    CHANNEL_ID,
                    msg_id,
                    message["chat"]["id"],
                    caption=caption
                )
                copied.append(result.get("message_id"))
            except Exception as exc:
                print(f"copyMessage {msg_id} failed: {exc}")

        delete_message(message["chat"]["id"], temp["message_id"])

        if AUTO_DELETE_TIME > 0 and copied:
            notice = send_message(
                message["chat"]["id"],
                AUTO_DELETE_MSG.format(time=AUTO_DELETE_TIME)
            )

            def delete_later(chat_id, ids_to_delete, notice_id):
                time.sleep(AUTO_DELETE_TIME)
                for mid in ids_to_delete:
                    delete_message(chat_id, mid)
                edit_message(
                    chat_id,
                    notice_id,
                    AUTO_DEL_SUCCESS_MSG
                )

            threading.Thread(
                target=delete_later,
                args=(message["chat"]["id"], copied, notice["message_id"]),
                daemon=True
            ).start()
        return

    markup = {
        "inline_keyboard": [[
            {"text": "😊 About Me", "callback_data": "about"},
            {"text": "🔒 Close", "callback_data": "close"}
        ]]
    }

    if START_PIC:
        tg("sendPhoto", {
            "chat_id": message["chat"]["id"],
            "photo": START_PIC,
            "caption": make_start_text(user_message(message)),
            "parse_mode": "HTML",
            "reply_markup": markup,
            "reply_parameters": {"message_id": message["message_id"]}
        })
    else:
        send_message(
            message["chat"]["id"],
            make_start_text(user_message(message)),
            reply_markup=markup,
            reply_to=message["message_id"],
            disable_preview=True
        )


def handle_help(message):
    text = """<b>Book Sharing Bot - Help</b>

<b>What is this bot?</b>
This bot helps you access books that are agreed to read by people in Anime Discussion 2.0.

<b>How to use?</b>
1. Click on <b>/files</b> to see all available books
2. Click on any book name to download it
3. You can also use shared links to get books directly

<b>Commands:</b>
/start - Start the bot
/files - List all available books
/ping - Check bot response time
/help - Show this help message

<b>Need help?</b>
Contact the bot owner for support."""

    send_message(message["chat"]["id"], text, reply_to=message.get("message_id"), disable_preview=True)


def handle_ping(message):
    start = time.perf_counter()
    sent = send_message(message["chat"]["id"], "Pinging...")
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    edit_message(
        message["chat"]["id"],
        sent["message_id"],
        f"Pong!\nResponse time: <code>{elapsed}ms</code>"
    )


def build_files_page(page):
    per_page = 10
    snapshot = list(file_index)
    total_pages = max(1, (len(snapshot) + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    selected = snapshot[(page - 1) * per_page:page * per_page]

    text = f"<b>Available Files (Page {page}/{total_pages})</b>\n\n"
    buttons = []

    for number, item in enumerate(selected, start=(page - 1) * per_page + 1):
        msg_id = item["message_id"]
        converted = msg_id * abs(CHANNEL_ID)
        payload = encode(f"get-{converted}")
        link = bot_link(payload)
        name = item.get("file_name") or "Unnamed file"
        size = format_size(item.get("file_size"))
        text += f"<b>{number}.</b> <code>{escape(name)}</code> ({size})\n"
        buttons.append([{"text": f"{number}. {name}", "url": link}])

    nav = []
    if page > 1:
        nav.append({"text": "Previous", "callback_data": f"files_page_{page - 1}"})
    if page < total_pages:
        nav.append({"text": "Next", "callback_data": f"files_page_{page + 1}"})
    if nav:
        buttons.append(nav)
    buttons.append([{"text": "Close", "callback_data": "close"}])

    return text, {"inline_keyboard": buttons}


def handle_files(message):
    if not file_index:
        send_message(
            message["chat"]["id"],
            "No files are indexed yet.\n\n"
            "New channel posts will appear here after the webhook is active. "
            "You can still use /genlink with an existing channel post."
        )
        return

    text, markup = build_files_page(1)
    send_message(
        message["chat"]["id"],
        text,
        reply_markup=markup,
        disable_preview=True
    )


def handle_users(message):
    if not is_admin(user_id(message)):
        return
    send_message(
        message["chat"]["id"],
        f"{len(users)} users are using this bot"
    )


def handle_broadcast(message):
    if not is_admin(user_id(message)):
        return

    reply = message.get("reply_to_message")
    if not reply:
        send_message(
            message["chat"]["id"],
            '<code>Use this command as a reply to any telegram message without any spaces.</code>'
        )
        return

    source_chat = reply.get("chat", {}).get("id")
    source_message = reply.get("message_id")
    if source_chat is None or source_message is None:
        send_message(message["chat"]["id"], "Could not determine the message to broadcast.")
        return

    wait = send_message(
        message["chat"]["id"],
        "<i>Broadcasting Message.. This will Take Some Time</i>"
    )

    def broadcast_worker():
        total = successful = blocked = deleted = unsuccessful = 0

        for chat_id in list(users):
            total += 1
            try:
                copy_message(source_chat, source_message, chat_id)
                successful += 1
            except Exception as exc:
                text = str(exc).lower()
                if "blocked" in text or "chat not found" in text:
                    remove_user(chat_id)
                    blocked += 1
                elif "deactivated" in text:
                    remove_user(chat_id)
                    deleted += 1
                else:
                    unsuccessful += 1
            time.sleep(0.04)

        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        try:
            edit_message(message["chat"]["id"], wait["message_id"], status)
        except Exception as exc:
            print(exc)

    threading.Thread(target=broadcast_worker, daemon=True).start()


def parse_id_message(message):
    msg_id = message_id_from_link_or_forward(message)
    return msg_id


def handle_genlink(message):
    if not is_admin(user_id(message)):
        return
    pending_actions[user_id(message)] = {"type": "genlink", "step": 1}
    send_message(
        message["chat"]["id"],
        "Forward Message from the DB Channel (with Quotes)..\n"
        "or Send the DB Channel Post link"
    )


def handle_batch(message):
    if not is_admin(user_id(message)):
        return
    pending_actions[user_id(message)] = {"type": "batch", "step": 1}
    send_message(
        message["chat"]["id"],
        "Forward the First Message from DB Channel (with Quotes)..\n\n"
        "or Send the DB Channel Post Link"
    )


def process_pending(message):
    uid = user_id(message)
    action = pending_actions.get(uid)
    if not action:
        return False

    msg_id = parse_id_message(message)
    if not msg_id:
        send_message(
            message["chat"]["id"],
            "❌ Error\n\nThis message/link is not from my DB Channel."
        )
        return True

    if action["type"] == "genlink":
        pending_actions.pop(uid, None)
        payload = encode(f"get-{msg_id * abs(CHANNEL_ID)}")
        link = bot_link(payload)
        send_message(
            message["chat"]["id"],
            f"<b>Here is your link</b>\n\n{link}",
            reply_markup=share_button(link),
            disable_preview=True
        )
        return True

    if action["step"] == 1:
        action["first_id"] = msg_id
        action["step"] = 2
        send_message(
            message["chat"]["id"],
            "Forward the Last Message from DB Channel (with Quotes)..\n"
            "or Send the DB Channel Post link"
        )
        return True

    first_id = action["first_id"]
    pending_actions.pop(uid, None)

    payload = encode(
        f"get-{first_id * abs(CHANNEL_ID)}-{msg_id * abs(CHANNEL_ID)}"
    )
    link = bot_link(payload)

    send_message(
        message["chat"]["id"],
        f"<b>Here is your link</b>\n\n{link}",
        reply_markup=share_button(link),
        disable_preview=True
    )
    return True


def handle_addadmin(message, args):
    if not is_admin(user_id(message)):
        return

    # /addadmin @username, /addadmin 123456789, or reply to a user's message
    identifier = args[0] if args else None
    if not identifier and message.get("reply_to_message"):
        replied_user = (message["reply_to_message"].get("from") or {})
        identifier = replied_user.get("username") or str(replied_user.get("id") or "")

    if not identifier:
        send_message(
            message["chat"]["id"],
            "Usage: /addadmin @username or /addadmin <user_id>\n"
            "You can also reply to the user's message with /addadmin."
        )
        return

    new_id, error = resolve_user_id(identifier, message)
    if new_id is None:
        send_message(message["chat"]["id"], error)
        return
    if new_id == OWNER_ID:
        send_message(message["chat"]["id"], "You are already the owner.")
        return
    if new_id in ADMINS:
        send_message(message["chat"]["id"], "This user is already an admin.")
        return

    ADMINS.add(new_id)
    persist_admins()
    username = identifier if str(identifier).startswith("@") else ""
    label = f"{username} (<code>{new_id}</code>)" if username else f"<code>{new_id}</code>"
    send_message(message["chat"]["id"], f"User {label} has been added as admin.")


def handle_removeadmin(message, args):
    if not is_admin(user_id(message)):
        return

    # /removeadmin @username, /removeadmin 123456789, or reply to a user's message
    identifier = args[0] if args else None
    if not identifier and message.get("reply_to_message"):
        replied_user = (message["reply_to_message"].get("from") or {})
        identifier = replied_user.get("username") or str(replied_user.get("id") or "")

    if not identifier:
        send_message(
            message["chat"]["id"],
            "Usage: /removeadmin @username or /removeadmin <user_id>\n"
            "You can also reply to the user's message with /removeadmin."
        )
        return

    remove_id, error = resolve_user_id(identifier, message)
    if remove_id is None:
        send_message(message["chat"]["id"], error)
        return
    if remove_id == OWNER_ID:
        send_message(message["chat"]["id"], "You cannot remove the owner.")
        return
    if remove_id not in ADMINS:
        send_message(message["chat"]["id"], "This user is not an admin.")
        return

    ADMINS.discard(remove_id)
    persist_admins()
    username = identifier if str(identifier).startswith("@") else ""
    label = f"{username} (<code>{remove_id}</code>)" if username else f"<code>{remove_id}</code>"
    send_message(message["chat"]["id"], f"User {label} has been removed from admins.")


def handle_listadmins(message):
    if not is_admin(user_id(message)):
        return
    admin_ids = sorted(ADMINS)
    if not admin_ids:
        send_message(message["chat"]["id"], "No admins found.")
        return
    text = "<b>Admin List:</b>\n\n" + "\n".join(
        f"<code>{x}</code>" for x in admin_ids
    )
    send_message(message["chat"]["id"], text)


def handle_stats(message):
    if not is_admin(user_id(message)):
        return
    seconds = int(time.time() - STARTED_AT)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    uptime = f"{days}d {hours}h {minutes}m {secs}s" if days else f"{hours}h {minutes}m {secs}s"
    send_message(message["chat"]["id"], BOT_STATS_TEXT.format(uptime=uptime))


# ------------------------- callbacks -------------------------

def handle_callback(query):
    data = query.get("data", "")
    answer_callback(query.get("id"))

    msg = query.get("message") or {}
    chat_id = msg.get("chat", {}).get("id")
    message_id = msg.get("message_id")

    if data == "about":
        edit_message(
            chat_id,
            message_id,
            "<b>Book Sharing Bot\n\n"
            "A bot to share and access books from Anime Discussion 2.0.\n\n"
            "Language : <code>Python3</code>\n"
            "Library : <code>Flask + Telegram Bot API</code></b>",
            reply_markup=about_markup()
        )
    elif data == "close":
        delete_message(chat_id, message_id)
    elif data.startswith("files_page_"):
        try:
            page = int(data.rsplit("_", 1)[1])
        except ValueError:
            return
        text, markup = build_files_page(page)
        edit_message(chat_id, message_id, text, reply_markup=markup)


# ------------------------- admin uploads / channel posts -------------------------

def process_private_media(message):
    uid = user_id(message)
    if not is_admin(uid):
        if USER_REPLY_TEXT:
            send_message(message["chat"]["id"], USER_REPLY_TEXT)
        return

    # Admin sent a media message directly to the bot. Copy it into DB channel.
    info = file_info_from_message(message)
    if not info:
        return False

    wait = send_message(message["chat"]["id"], "Please Wait...!")

    try:
        copied = copy_message(
            message["chat"]["id"],
            message["message_id"],
            CHANNEL_ID
        )
        channel_message_id = copied["message_id"]

        # The original incoming message contains enough metadata for indexing.
        indexed = dict(info)
        indexed["message_id"] = channel_message_id
        indexed["chat_id"] = CHANNEL_ID
        add_file_index({
            **message,
            "message_id": channel_message_id,
            "chat": {"id": CHANNEL_ID},
        })

        payload = encode(f"get-{channel_message_id * abs(CHANNEL_ID)}")
        link = bot_link(payload)
        markup = share_button(link)

        edit_reply_markup(CHANNEL_ID, channel_message_id, markup)
        edit_message(
            message["chat"]["id"],
            wait["message_id"],
            f"<b>Here is your link</b>\n\n{link}",
            reply_markup=markup
        )
    except Exception as exc:
        print(f"Admin media upload failed: {exc}")
        edit_message(
            message["chat"]["id"],
            wait["message_id"],
            "Something went Wrong..!"
        )
    return True


def process_channel_post(message):
    if int(message.get("chat", {}).get("id", 0)) != CHANNEL_ID:
        return

    # Always index the post. DISABLE_CHANNEL_BUTTON only controls the
    # share button, not whether the file appears in /files.
    info = file_info_from_message(message)
    if info:
        add_file_index(message)

    if DISABLE_CHANNEL_BUTTON:
        return

    if info:
        msg_id = message["message_id"]
        payload = encode(f"get-{msg_id * abs(CHANNEL_ID)}")
        link = bot_link(payload)
        markup = share_button(link)
        try:
            edit_reply_markup(CHANNEL_ID, msg_id, markup)
        except Exception as exc:
            print(f"Channel markup update failed: {exc}")

def download_telegram_file(file_id):
    """Download a Telegram file and return its local path."""

    # Get Telegram file information
    response = telegram_request(
        "getFile",
        {"file_id": file_id}
    )

    if not response.get("ok"):
        return None

    file_path = response["result"]["file_path"]

    # Download the actual file
    url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"

    response = requests.get(url, stream=True)

    if not response.ok:
        return None

    extension = os.path.splitext(file_path)[1]

    temp_file = tempfile.NamedTemporaryFile(
        delete=False,
        suffix=extension
    )

    with temp_file as f:
        for chunk in response.iter_content(chunk_size=8192):
            if chunk:
                f.write(chunk)

    return temp_file.name

def handle_rename(message, args):

    chat_id = message["chat"]["id"]
    reply = message.get("reply_to_message")

    # Must reply to a message
    if not reply:
        send_message(
            chat_id,
            "❌ Reply to a document with:\n\n"
            "/rename New File Name.pdf"
        )
        return

    # Check if replied message contains a document
    document = reply.get("document")

    if not document:
        send_message(
            chat_id,
            "❌ The replied message does not contain a document."
        )
        return

    # Get new filename
    new_name = " ".join(args).strip()

    if not new_name:
        send_message(
            chat_id,
            "❌ Please provide a new filename.\n\n"
            "Example:\n"
            "/rename My New Book.pdf"
        )
        return

    # Prevent invalid filename
    invalid_chars = '<>:"/\\|?*'

    if any(char in new_name for char in invalid_chars):
        send_message(
            chat_id,
            "❌ Invalid filename.\n"
            "Please remove characters like: < > : \" / \\ | ? *"
        )
        return

    file_id = document["file_id"]

    send_message(
        chat_id,
        "⏳ Downloading and renaming the file..."
    )

    temp_path = None

    try:
        temp_path = download_telegram_file(file_id)

        if not temp_path:
            send_message(
                chat_id,
                "❌ Failed to download the file from Telegram."
            )
            return

        # Upload with new filename
        with open(temp_path, "rb") as file:

            response = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
                data={
                    "chat_id": chat_id,
                    "caption": reply.get("caption", "")
                },
                files={
                    "document": (
                        new_name,
                        file
                    )
                }
            )

        result = response.json()

        if not result.get("ok"):
            send_message(
                chat_id,
                f"❌ Failed to upload renamed file.\n\n"
                f"{result.get('description', 'Unknown error')}"
            )
            return

        send_message(
            chat_id,
            f"✅ File renamed successfully!\n\n"
            f"New name: `{new_name}`"
        )

    except Exception as e:

        print("Rename error:", e)

        send_message(
            chat_id,
            f"❌ Error while renaming file:\n`{str(e)}`"
        )

    finally:

        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ------------------------- update dispatcher -------------------------

def process_message(message):
    uid = user_id(message)
    if uid:
        add_user(uid, message.get("from"))

    # Batch/genlink follow-up messages must be handled BEFORE admin-media
    # handling, because a forwarded document is a valid batch/genlink input.
    if is_private(message) and not (message.get("text") or "").startswith("/"):
        if process_pending(message):
            return

    # Admin's media upload to bot
    if is_private(message) and file_info_from_message(message):
        # If it is a reply used for broadcast, do not treat as upload.
        if command_parts(message)[0] != "/broadcast":
            if process_private_media(message):
                return

    command, args = command_parts(message)

    if command == "/start" and is_private(message):
        argument = args[0] if args else None
        handle_start(message, argument)
    elif command == "/help" and is_private(message):
        if subscribed(uid):
            handle_help(message)
    elif command == "/ping" and is_private(message):
        handle_ping(message)
    elif command == "/files" and is_private(message):
        if subscribed(uid):
            handle_files(message)
    elif command == "/users" and is_private(message):
        handle_users(message)
    elif command == "/broadcast" and is_private(message):
        handle_broadcast(message)
    elif command == "/batch" and is_private(message):
        handle_batch(message)
    elif command == "/genlink" and is_private(message):
        handle_genlink(message)
    elif command == "/addadmin" and is_private(message):
        handle_addadmin(message, args)
    elif command == "/removeadmin" and is_private(message):
        handle_removeadmin(message, args)
    elif command == "/listadmins" and is_private(message):
        handle_listadmins(message)
    elif command == "/stats" and is_private(message):
        handle_stats(message)
    elif command == "/rename":
        return handle_rename(message, args)
    elif is_private(message) and process_pending(message):
        pass
    elif is_private(message) and not command and USER_REPLY_TEXT:
        # Do not answer admin media messages twice.
        if not file_info_from_message(message):
            send_message(message["chat"]["id"], USER_REPLY_TEXT)


def initialize():
    global BOT_ME, BOT_USERNAME, CHANNEL_USERNAME

    BOT_ME = tg_get("getMe")
    BOT_USERNAME = BOT_ME.get("username")

    if CHANNEL_ID:
        try:
            channel = tg_get("getChat", {"chat_id": CHANNEL_ID})
            CHANNEL_USERNAME = channel.get("username")
        except Exception as exc:
            print(f"Could not get DB channel: {exc}")

    if WEBHOOK_URL:
        try:
            payload = {"url": f"{WEBHOOK_URL}/webhook"}
            if WEBHOOK_SECRET:
                payload["secret_token"] = WEBHOOK_SECRET
            result = tg("setWebhook", payload)
            print("Webhook configured:", result)
        except Exception as exc:
            print("Webhook configuration failed:", exc)

    print(f"Bot @{BOT_USERNAME} initialized")
    print(f"Indexed files: {len(file_index)}")
    print(f"Users: {len(users)}")
    print(f"Admins: {len(ADMINS)}")


@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "status": "Book Sharing Bot is running",
        "bot": BOT_USERNAME,
        "webhook": bool(WEBHOOK_URL),
        "indexed_files": len(file_index),
        "users": len(users)
    })


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != WEBHOOK_SECRET:
            return jsonify({"ok": False, "error": "invalid secret"}), 403

    try:
        update = request.get_json(silent=True) or {}

        if "callback_query" in update:
            handle_callback(update["callback_query"])

        elif "channel_post" in update:
            process_channel_post(update["channel_post"])

        elif "message" in update:
            process_message(update["message"])

        elif "edited_channel_post" in update:
            process_channel_post(update["edited_channel_post"])

        return jsonify({"ok": True})
    except Exception as exc:
        print(f"Webhook error: {exc}")
        # Telegram should normally receive 200 so it doesn't hammer the
        # endpoint with the same update repeatedly. Log the real exception.
        return jsonify({"ok": False}), 200


@app.route("/setwebhook", methods=["GET"])
def set_webhook():
    public_url = WEBHOOK_URL or request.url_root.rstrip("/")
    payload = {"url": f"{public_url}/webhook"}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    try:
        return jsonify(tg("setWebhook", payload))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/deletewebhook", methods=["GET"])
def delete_webhook():
    try:
        return jsonify(tg("deleteWebhook", {}))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/getwebhook", methods=["GET"])
def get_webhook():
    try:
        return jsonify(tg_get("getWebhookInfo"))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500

# Initialize once when the Gunicorn worker imports this module.
try:
    initialize()
except Exception as exc:
    # Keep Flask alive so Render logs expose the actual error.
    print(f"Initialization error: {exc}")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)
