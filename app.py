import os
import re
import json
import time
import base64
import threading
from html import escape
from datetime import datetime, timedelta
from pathlib import Path
import tempfile

import requests
from pymongo import MongoClient, ASCENDING
from flask import Flask, request, jsonify

import requests

GENSHIN_CHARACTER_NAMES = {
    "10000002": "Kamisato Ayaka",
    "10000003": "Jean",
    "10000005": "Traveler",
    "10000006": "Lisa",
    "10000007": "Traveler",
    "10000014": "Barbara",
    "10000015": "Kaeya",
    "10000016": "Diluc",
    "10000020": "Razor",
    "10000021": "Amber",
    "10000022": "Venti",
    "10000023": "Xiangling",
    "10000024": "Beidou",
    "10000025": "Xingqiu",
    "10000026": "Xiao",
    "10000027": "Ningguang",
    "10000029": "Klee",
    "10000030": "Zhongli",
    "10000031": "Fischl",
    "10000032": "Bennett",
    "10000033": "Tartaglia",
    "10000034": "Noelle",
    "10000035": "Qiqi",
    "10000036": "Chongyun",
    "10000037": "Ganyu",
    "10000038": "Albedo",
    "10000039": "Diona",
    "10000041": "Mona",
    "10000042": "Keqing",
    "10000043": "Sucrose",
    "10000044": "Xinyan",
    "10000045": "Rosaria",
    "10000046": "Hu Tao",
    "10000047": "Kaedehara Kazuha",
    "10000048": "Yanfei",
    "10000049": "Yoimiya",
    "10000050": "Thoma",
    "10000051": "Eula",
    "10000052": "Raiden Shogun",
    "10000053": "Sayu",
    "10000054": "Sangonomiya Kokomi",
    "10000055": "Gorou",
    "10000056": "Kujou Sara",
    "10000057": "Arataki Itto",
    "10000058": "Yae Miko",
    "10000059": "Shikanoin Heizou",
    "10000060": "Yelan",
    "10000062": "Aloy",
    "10000063": "Shenhe",
    "10000064": "Yun Jin",
    "10000065": "Kuki Shinobu",
    "10000066": "Kamisato Ayato",
    "10000067": "Collei",
    "10000068": "Dori",
    "10000069": "Tighnari",
    "10000070": "Nilou",
    "10000071": "Cyno",
    "10000072": "Candace",
    "10000073": "Nahida",
    "10000074": "Layla",
    "10000075": "Faruzan",
    "10000076": "Wanderer",
    "10000077": "Yaoyao",
    "10000078": "Alhaitham",
    "10000079": "Dehya",
    "10000080": "Kaveh",
    "10000081": "Kirara",
    "10000082": "Lyney",
    "10000083": "Lynette",
    "10000084": "Freminet",
    "10000085": "Wriothesley",
    "10000086": "Neuvillette",
    "10000087": "Charlotte",
    "10000088": "Furina",
    "10000089": "Navia",
    "10000090": "Chevreuse",
    "10000091": "Gaming",
    "10000092": "Xianyun",
    "10000093": "Chiori",
    "10000094": "Arlecchino",
    "10000095": "Clorinde",
    "10000096": "Sethos",
    "10000097": "Sigewinne",
    "10000098": "Emilie",
    "10000099": "Kachina",
    "10000100": "Kinich",
    "10000101": "Mualani",
    "10000102": "Xilonen",
    "10000103": "Chasca",
    "10000104": "Ororon",
    "10000105": "Mavuika",
    "10000106": "Citlali",
    "10000107": "Lan Yan",
    "10000108": "Yumemizuki Mizuki",
    "10000109": "Varesa",
    "10000110": "Iansan",
    "10000111": "Skirk",
    "10000112": "Dahlia",
    "10000113": "Ineffa",
    "10000114": "Flins",
    "10000115": "Lauma",
    "10000116": "Aino",
    "10000117": "Jahoda",
}

def get_character_name(character_id, character_data=None):
    character_id = str(character_id)

    # First try the local mapping
    name = GENSHIN_CHARACTER_NAMES.get(character_id)

    if name:
        return name

    # Try Enka character data if a name is available
    if isinstance(character_data, dict):
        name = (
            character_data.get("name")
            or character_data.get("Name")
        )

        if name:
            return name

    return f"Unknown Character ({character_id})"

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

def parse_admin_ids(value):
    """Parse admin IDs from comma/space/newline separated environment values."""
    result = set()
    for item in re.split(r"[\s,]+", value or ""):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError:
            pass
    return result


# DEFAULT_ADMINS are always admins and are restored on every startup.
# They are intentionally kept separate from the runtime /addadmin list so
# a Render redeploy cannot remove them.
DEFAULT_ADMINS = parse_admin_ids(os.environ.get("DEFAULT_ADMINS", ""))
ADMINS = set(DEFAULT_ADMINS)
ADMINS.update(parse_admin_ids(os.environ.get("ADMINS", "")))
if OWNER_ID:
    ADMINS.add(OWNER_ID)

FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "0"))
JOIN_REQUEST_ENABLE = os.environ.get("JOIN_REQUEST_ENABLED", "").lower() == "true"

START_PIC = os.environ.get("START_PIC", "")
START_MSG = os.environ.get(
    "START_MESSAGE",
    "Hello {first}. I am Annie's Bookshelf which will help you get the books "
    "which are agreed to read by people."
)
FORCE_MSG = os.environ.get(
    "FORCE_SUB_MESSAGE",
    "Hello {first}\n\n<b>You need to join in my Channel/Group to use me\n\n"
    "Kindly Please join Channel</b>"
)
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION") or None
PROTECT_CONTENT = os.environ.get("PROTECT_CONTENT", "False").lower() == "true"
AUTO_DELETE_TIME_DEFAULT = int(os.environ.get("AUTO_DELETE_TIME", "0"))
AUTO_DELETE_MSG = os.environ.get(
    "AUTO_DELETE_MSG",
    "⏳ This file will be automatically deleted in <b>{time}</b>.\n"
    "Please save it before the timer expires."
)
AUTO_DEL_SUCCESS_MSG = os.environ.get(
    "AUTO_DEL_SUCCESS_MSG",
    "Your file has been successfully deleted. Thank you for using our service. ✅"
)
DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", "False").lower() == "true"
USER_REPLY_TEXT = os.environ.get(
    "USER_REPLY_TEXT",
    "❌Don't send me messages directly I'm only Annie's Bookshelf!"
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
SETTINGS_FILE = DATA_DIR / "bot_settings.json"
DELETIONS_FILE = DATA_DIR / "pending_deletions.json"
DOWNLOADS_FILE = DATA_DIR / "download_stats.json"
GENSHIN_PROFILES_FILE = DATA_DIR / "genshin_profiles.json"
GENSHIN_CACHE_FILE = DATA_DIR / "genshin_cache.json"

state_lock = threading.RLock()
MONGODB_URI = os.environ.get("MONGODB_URI", "").strip()
MONGODB_DB_NAME = os.environ.get("MONGODB_DB_NAME", "book_sharing_bot")
mongo_client = None
mongo_db = None
if MONGODB_URI:
    mongo_client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=10000, connectTimeoutMS=10000)
    mongo_client.admin.command("ping")
    mongo_db = mongo_client[MONGODB_DB_NAME]
    mongo_files = mongo_db["files"]
    mongo_admins = mongo_db["admins"]
    mongo_settings = mongo_db["settings"]
    mongo_deletions = mongo_db["pending_deletions"]
    mongo_users = mongo_db["users"]
    mongo_profiles = mongo_db["user_profiles"]
    mongo_downloads = mongo_db["downloads"]
    mongo_files.create_index([("message_id", ASCENDING)], unique=True)
    mongo_admins.create_index([("user_id", ASCENDING)], unique=True)
    mongo_deletions.create_index([("job_key", ASCENDING)], unique=True)
    mongo_downloads.create_index([("downloaded_at", ASCENDING)])
    mongo_downloads.create_index([("user_id", ASCENDING), ("downloaded_at", ASCENDING)])
    mongo_downloads.create_index([("message_id", ASCENDING), ("downloaded_at", ASCENDING)])
    mongo_genshin_profiles = mongo_db["genshin_profiles"]
    mongo_genshin_cache = mongo_db["genshin_cache"]
    mongo_genshin_profiles.create_index([("telegram_user_id", ASCENDING)], unique=True)
    mongo_genshin_cache.create_index([("uid", ASCENDING)], unique=True)
else:
    mongo_files = mongo_admins = mongo_settings = mongo_deletions = mongo_users = mongo_profiles = mongo_downloads = None
    mongo_genshin_profiles = mongo_genshin_cache = None
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
if mongo_db is not None:
    users.update(int(x["user_id"]) for x in mongo_users.find({}, {"user_id": 1}) if x.get("user_id") is not None)
# Maps normalized Telegram usernames to user IDs for users who have interacted with the bot.
user_profiles = load_json(USER_PROFILES_FILE, {})
if mongo_db is not None:
    user_profiles.update({x["username"]: x["profile"] for x in mongo_profiles.find({}) if x.get("username") and x.get("profile")})
stored_admins = set(int(x) for x in load_json(ADMINS_FILE, []) if str(x).lstrip("-").isdigit())
ADMINS.update(stored_admins)
if mongo_db is not None:
    ADMINS.update(int(x["user_id"]) for x in mongo_admins.find({}) if x.get("user_id") is not None)

# File index contains channel messages seen since this Flask webhook was installed.
# Telegram Bot API does not provide a "read channel history" method.
file_index = load_json(FILES_FILE, [])
if mongo_db is not None:
    file_index = list(mongo_files.find({}, {"_id": 0}).sort("message_id", ASCENDING))

# Runtime-configurable settings. These are kept in the bot's local data directory so /setautodelete can change the value
# without requiring a redeploy. Render's filesystem is ephemeral, so an optional
# AUTO_DELETE_TIME environment variable remains the startup/default value.
_settings = load_json(SETTINGS_FILE, {})
try:
    auto_delete_time = int(_settings.get("auto_delete_time", AUTO_DELETE_TIME_DEFAULT))
except (TypeError, ValueError):
    auto_delete_time = AUTO_DELETE_TIME_DEFAULT
if mongo_db is not None:
    persisted_setting = mongo_settings.find_one({"_id": "bot_config"}) or {}
    try:
        auto_delete_time = max(0, int(persisted_setting.get("auto_delete_time", auto_delete_time)))
    except (TypeError, ValueError):
        pass

pending_deletions = load_json(DELETIONS_FILE, [])
if mongo_db is not None:
    pending_deletions = [{k: v for k, v in x.items() if k not in {"_id", "job_key"}} for x in mongo_deletions.find({})]

# Download analytics. MongoDB is the durable store; the local JSON file is a
# fallback for development or deployments where MongoDB is not configured.
download_stats = load_json(DOWNLOADS_FILE, [])
delete_worker_started = False



def add_user(user_id, user=None):
    with state_lock:
        if user_id not in users:
            users.add(user_id)
            save_json(USERS_FILE, sorted(users))
            if mongo_db is not None:
                mongo_users.update_one(
                    {"user_id": int(user_id)},
                    {"$set": {"user_id": int(user_id)}, "$setOnInsert": {"first_seen": datetime.utcnow()}},
                    upsert=True
                )
        elif mongo_db is not None:
            # Older users may already exist in MongoDB without a first_seen field.
            mongo_users.update_one(
                {"user_id": int(user_id)},
                {"$set": {"user_id": int(user_id)}},
                upsert=True
            )

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
                if mongo_db is not None:
                    mongo_profiles.update_one({"username": username}, {"$set": {"profile": user_profiles[username]}}, upsert=True)


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
        if mongo_db is not None:
            mongo_users.delete_one({"user_id": int(user_id)})


def persist_admins():
    save_json(ADMINS_FILE, sorted(x for x in ADMINS if x != OWNER_ID and x not in DEFAULT_ADMINS))
    if mongo_db is not None:
        mongo_admins.delete_many({})
        runtime_ids = [x for x in ADMINS if x != OWNER_ID and x not in DEFAULT_ADMINS]
        if runtime_ids:
            mongo_admins.insert_many([{"user_id": int(x)} for x in runtime_ids])


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


SUPPORTED_BOOK_EXTENSIONS = {".pdf", ".epub"}

def is_supported_book_name(file_name):
    """Return True only for PDF and EPUB files."""
    name = (file_name or "").strip().lower()
    return Path(name).suffix in SUPPORTED_BOOK_EXTENSIONS

def is_supported_book_info(info):
    return bool(info and is_supported_book_name(info.get("file_name")))

def unsupported_book_message():
    return "❌ Only <b>PDF</b> and <b>EPUB</b> files are supported for book links."

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
            "file_unique_id": value.get("file_unique_id"),
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
        if mongo_db is not None:
            mongo_files.replace_one({"message_id": int(info["message_id"])}, info, upsert=True)
            mongo_files.delete_many({"message_id": {"$nin": [int(x["message_id"]) for x in file_index]}})


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


def lookup_file_by_identity(document):
    """Find an indexed channel file from a Telegram document identity."""
    unique_id = document.get("file_unique_id")
    file_id = document.get("file_id")
    for item in file_index:
        if unique_id and item.get("file_unique_id") == unique_id:
            return item
        if file_id and item.get("file_id") == file_id:
            return item
    return None


def remove_file_index(message_id):
    with state_lock:
        file_index[:] = [
            item for item in file_index
            if int(item.get("message_id", 0)) != int(message_id)
        ]
        save_json(FILES_FILE, file_index)
        if mongo_db is not None:
            mongo_files.delete_one({"message_id": int(message_id)})


def replace_file_index(old_message_id, new_message):
    """Atomically replace a renamed channel post in local and Mongo indexes."""
    info = file_info_from_message(new_message)
    if not info or not info.get("message_id") or not is_supported_book_info(info):
        raise ValueError("The renamed channel post is not a supported PDF or EPUB document.")

    old_id = int(old_message_id)
    new_id = int(info["message_id"])
    with state_lock:
        updated = [
            item for item in file_index
            if int(item.get("message_id", 0)) not in {old_id, new_id}
        ]
        updated.append(info)
        updated = updated[-5000:]

        # Persist the new canonical entry before publishing the in-memory state.
        if mongo_db is not None:
            mongo_files.replace_one({"message_id": new_id}, info, upsert=True)
            if old_id != new_id:
                mongo_files.delete_one({"message_id": old_id})
        save_json(FILES_FILE, updated)
        file_index[:] = updated


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


# ------------------------- auto-delete -------------------------

def get_auto_delete_time():
    with state_lock:
        return max(0, int(auto_delete_time))


def save_auto_delete_time(seconds):
    global auto_delete_time
    with state_lock:
        auto_delete_time = max(0, int(seconds))
        settings = load_json(SETTINGS_FILE, {})
        settings["auto_delete_time"] = auto_delete_time
        save_json(SETTINGS_FILE, settings)
        if mongo_db is not None:
            mongo_settings.update_one({"_id": "bot_config"}, {"$set": {"auto_delete_time": auto_delete_time}}, upsert=True)


def format_duration(seconds):
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{hours} hour{'s' if hours != 1 else ''}"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    return f"{seconds} seconds"


def parse_duration(value):
    """Parse 30s, 10m, 2h, 1d or a plain number of seconds."""
    value = str(value or "").strip().lower()
    if value in {"0", "off", "disable", "disabled"}:
        return 0
    match = re.fullmatch(r"(\d+)\s*([smhd]?)", value)
    if not match:
        raise ValueError("Use formats like 30s, 10m, 2h, 1d, or 0 to disable.")
    amount = int(match.group(1))
    unit = match.group(2) or "s"
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    seconds = amount * multiplier
    if seconds > 30 * 86400:
        raise ValueError("The maximum auto-delete time is 30 days.")
    return seconds


def save_pending_deletions():
    with state_lock:
        save_json(DELETIONS_FILE, pending_deletions)


def _timer_delete_messages(chat_id, message_ids, delete_at):
    """Delete a delivered file/notice at the requested time.

    The persistent pending-deletions queue remains the recovery mechanism if the
    process restarts or Telegram is temporarily unavailable.
    """
    try:
        # If the process was delayed, delete immediately; otherwise this runs at
        # the exact timer deadline (subject to normal OS/thread scheduling).
        for message_id in message_ids:
            success = delete_message(chat_id, message_id)
            if success:
                with state_lock:
                    for item in list(pending_deletions):
                        if (int(item.get("chat_id", 0)) == int(chat_id) and
                                int(item.get("message_id", 0)) == int(message_id) and
                                abs(float(item.get("delete_at", 0)) - float(delete_at)) < 1):
                            try:
                                pending_deletions.remove(item)
                            except ValueError:
                                pass
        save_pending_deletions()
    except Exception as exc:
        print(f"Auto-delete timer error: {exc}")


def schedule_auto_deletion(chat_id, message_ids, delay):
    """Persist deletion jobs and start an in-process timer for immediate cleanup."""
    delay = max(0, int(delay))
    now = time.time()
    delete_at = now + delay
    chat_id = int(chat_id)
    message_ids = [int(mid) for mid in message_ids if mid]

    with state_lock:
        for message_id in message_ids:
            pending_deletions.append({
                "chat_id": chat_id,
                "message_id": message_id,
                "delete_at": delete_at,
            })
        save_pending_deletions()

    # Do not rely on the background polling worker for normal deletion. A
    # per-download timer is what makes a 5s/10s/etc. setting actually fire
    # without requiring another webhook request.
    if message_ids:
        timer = threading.Timer(
            delay,
            _timer_delete_messages,
            args=(chat_id, message_ids, delete_at)
        )
        timer.daemon = True
        timer.start()


def process_pending_deletions():
    """Delete due messages and keep failed deletions queued for retry."""
    now = time.time()
    due = []

    with state_lock:
        for item in list(pending_deletions):
            try:
                if float(item.get("delete_at", 0)) <= now:
                    due.append(dict(item))
            except (TypeError, ValueError):
                # Remove malformed entries so one bad record cannot block cleanup.
                pending_deletions.remove(item)

    for item in due:
        chat_id = int(item["chat_id"])
        message_id = int(item["message_id"])
        success = delete_message(chat_id, message_id)

        with state_lock:
            # Remove only after Telegram confirms success. This prevents a transient
            # network/API error from permanently losing the deletion task.
            if success:
                try:
                    pending_deletions.remove(item)
                except ValueError:
                    pass
            else:
                # Retry soon if Telegram was temporarily unavailable.
                item["delete_at"] = time.time() + 15

    save_pending_deletions()


def auto_delete_worker():
    while True:
        try:
            process_pending_deletions()
        except Exception as exc:
            print(f"Auto-delete worker error: {exc}")
        time.sleep(2)


def start_auto_delete_worker():
    global delete_worker_started
    with state_lock:
        if delete_worker_started:
            return
        delete_worker_started = True
    threading.Thread(target=auto_delete_worker, name="auto-delete-worker", daemon=True).start()


def handle_auto_delete(message, args):
    if not is_admin(user_id(message)):
        send_message(message["chat"]["id"], "❌ Only admins can configure auto-delete.")
        return

    chat_id = message["chat"]["id"]
    if not args:
        current = get_auto_delete_time()
        status = "disabled" if current == 0 else f"{format_duration(current)}"
        send_message(
            chat_id,
            "<b>Auto-delete setting</b>\n\n"
            f"Current: <code>{escape(status)}</code>\n\n"
            "Set it with:\n"
            "<code>/setautodelete 30s</code>\n"
            "<code>/setautodelete 10m</code>\n"
            "<code>/setautodelete 2h</code>\n"
            "<code>/setautodelete 1d</code>\n\n"
            "Use <code>/setautodelete 0</code> to disable it."
        )
        return

    try:
        seconds = parse_duration(args[0])
        save_auto_delete_time(seconds)
    except ValueError as exc:
        send_message(chat_id, f"❌ {escape(str(exc))}")
        return

    if seconds == 0:
        send_message(chat_id, "✅ Auto-delete has been disabled.")
    else:
        send_message(
            chat_id,
            f"✅ Auto-delete is now set to <b>{escape(format_duration(seconds))}</b>.\n\n"
            "Files delivered through book links will be deleted automatically after this time."
        )


# ------------------------- statistics -------------------------

def record_download(user_id_value, message_id, info=None):
    """Record one successful book delivery for persistent admin analytics."""
    if not user_id_value or not message_id:
        return
    info = info or lookup_file_info(message_id) or {}
    now = datetime.utcnow()
    event = {
        "user_id": int(user_id_value),
        "message_id": int(message_id),
        "book_name": info.get("file_name") or "Unknown book",
        "file_type": Path(str(info.get("file_name") or "")).suffix.lower().lstrip("."),
        "downloaded_at": now,
    }
    with state_lock:
        if mongo_db is not None:
            mongo_downloads.insert_one(event)
        else:
            serializable = dict(event)
            serializable["downloaded_at"] = now.isoformat()
            download_stats.append(serializable)
            # Keep the fallback bounded so a local deployment cannot grow forever.
            download_stats[:] = download_stats[-20000:]
            save_json(DOWNLOADS_FILE, download_stats)


def _stats_since(days):
    return datetime.utcnow() - timedelta(days=days)


def _stats_total_downloads():
    if mongo_db is not None:
        return mongo_downloads.count_documents({})
    return len(download_stats)


def _stats_downloads_since(days):
    cutoff = _stats_since(days)
    if mongo_db is not None:
        return mongo_downloads.count_documents({"downloaded_at": {"$gte": cutoff}})
    total = 0
    for item in download_stats:
        try:
            when = datetime.fromisoformat(str(item.get("downloaded_at", "")))
            if when >= cutoff:
                total += 1
        except (TypeError, ValueError):
            continue
    return total


def _stats_top_books(limit=10):
    if mongo_db is not None:
        return list(mongo_downloads.aggregate([
            {"$group": {"_id": "$message_id", "name": {"$first": "$book_name"}, "downloads": {"$sum": 1}}},
            {"$sort": {"downloads": -1}},
            {"$limit": int(limit)},
        ]))
    counts = {}
    for item in download_stats:
        key = item.get("message_id")
        if key is None:
            continue
        row = counts.setdefault(key, {"_id": key, "name": item.get("book_name") or "Unknown book", "downloads": 0})
        row["downloads"] += 1
    return sorted(counts.values(), key=lambda x: x["downloads"], reverse=True)[:limit]


def _stats_top_users(limit=10):
    if mongo_db is not None:
        return list(mongo_downloads.aggregate([
            {"$group": {"_id": "$user_id", "downloads": {"$sum": 1}}},
            {"$sort": {"downloads": -1}},
            {"$limit": int(limit)},
        ]))
    counts = {}
    for item in download_stats:
        uid = item.get("user_id")
        if uid is not None:
            counts[uid] = counts.get(uid, 0) + 1
    return [{"_id": uid, "downloads": count} for uid, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:limit]]


def _stats_active_users(days=30):
    cutoff = _stats_since(days)
    if mongo_db is not None:
        return mongo_downloads.count_documents({"downloaded_at": {"$gte": cutoff}}) and len(
            mongo_downloads.distinct("user_id", {"downloaded_at": {"$gte": cutoff}})
        )
    ids = set()
    for item in download_stats:
        try:
            when = datetime.fromisoformat(str(item.get("downloaded_at", "")))
            if when >= cutoff:
                ids.add(int(item.get("user_id")))
        except (TypeError, ValueError):
            continue
    return len(ids)


def _stats_new_users(days=7):
    if mongo_db is not None:
        cutoff = _stats_since(days)
        # Only users created after this feature was installed have first_seen.
        return mongo_users.count_documents({"first_seen": {"$gte": cutoff}})
    return 0


def handle_stats(message):
    if not is_admin(user_id(message)):
        send_message(message["chat"]["id"], "❌ This command is available to admins only.")
        return

    total_books = sum(1 for item in file_index if is_supported_book_name(item.get("file_name")))
    pdf_count = sum(1 for item in file_index if str(item.get("file_name") or "").lower().endswith(".pdf"))
    epub_count = sum(1 for item in file_index if str(item.get("file_name") or "").lower().endswith(".epub"))
    total_downloads = _stats_total_downloads()
    today = _stats_downloads_since(1)
    week = _stats_downloads_since(7)
    month = _stats_downloads_since(30)
    active = _stats_active_users(30)
    top = _stats_top_books(1)
    most_downloaded = escape(str(top[0].get("name") or "None")) if top else "None"

    seconds = int(time.time() - STARTED_AT)
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, secs = divmod(rem, 60)
    uptime = f"{days}d {hours}h {minutes}m {secs}s" if days else f"{hours}h {minutes}m {secs}s"
    db_status = "🟢 Connected" if mongo_db is not None else "🟡 Local fallback"

    text = f"""<b>📊 Annie's Bookshelf — Statistics</b>

<b>📚 Library</b>
━━━━━━━━━━━━━━━━
Total Books: <code>{total_books}</code>
PDF: <code>{pdf_count}</code>
EPUB: <code>{epub_count}</code>

<b>👥 Users</b>
━━━━━━━━━━━━━━━━
Total Users: <code>{len(users)}</code>
Active (30d): <code>{active}</code>
New Users (7d): <code>{_stats_new_users(7)}</code>

<b>⬇️ Downloads</b>
━━━━━━━━━━━━━━━━
Total Downloads: <code>{total_downloads}</code>
Last 24h: <code>{today}</code>
Last 7d: <code>{week}</code>
Last 30d: <code>{month}</code>

<b>🏆 Most Downloaded</b>
{most_downloaded}

<b>⚙️ Bot</b>
━━━━━━━━━━━━━━━━
Admins: <code>{len(ADMINS)}</code>
Auto-delete: <code>{escape(format_duration(get_auto_delete_time())) if get_auto_delete_time() else 'Disabled'}</code>
Database: {db_status}
Uptime: <code>{uptime}</code>"""
    send_message(message["chat"]["id"], text, disable_preview=True)


def handle_topbooks(message):
    if not is_admin(user_id(message)):
        send_message(message["chat"]["id"], "❌ This command is available to admins only.")
        return
    rows = _stats_top_books(10)
    if not rows:
        send_message(message["chat"]["id"], "📚 No download data has been recorded yet.")
        return
    lines = ["<b>🏆 Top 10 Most Downloaded Books</b>", ""]
    for i, row in enumerate(rows, 1):
        name = escape(str(row.get("name") or "Unknown book"))
        lines.append(f"<b>{i}.</b> {name} — <code>{row.get('downloads', 0)}</code> downloads")
    send_message(message["chat"]["id"], "\n".join(lines), disable_preview=True)


def handle_topusers(message):
    if not is_admin(user_id(message)):
        send_message(message["chat"]["id"], "❌ This command is available to admins only.")
        return
    rows = _stats_top_users(10)
    if not rows:
        send_message(message["chat"]["id"], "👥 No download data has been recorded yet.")
        return
    lines = ["<b>👥 Top 10 Most Active Downloaders</b>", ""]
    for i, row in enumerate(rows, 1):
        uid = int(row.get("_id", 0))
        profile = next((p for p in user_profiles.values() if int(p.get("id", 0)) == uid), {})
        name = " ".join(x for x in [profile.get("first_name", ""), profile.get("last_name", "")] if x).strip()
        label = escape(name or (f"@{profile.get('username')}" if profile.get("username") else f"User {uid}"))
        lines.append(f"<b>{i}.</b> {label} — <code>{row.get('downloads', 0)}</code> downloads")
    send_message(message["chat"]["id"], "\n".join(lines), disable_preview=True)


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
            if not is_supported_book_info(info):
                print(f"Skipping unsupported/non-indexed book message {msg_id}")
                continue
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
                copied_message_id = result.get("message_id")
                copied.append(copied_message_id)
                record_download(uid, msg_id, info)
            except Exception as exc:
                print(f"copyMessage {msg_id} failed: {exc}")

        delete_message(message["chat"]["id"], temp["message_id"])

        if get_auto_delete_time() > 0 and copied:
            delay = get_auto_delete_time()
            user_chat_id = message["chat"]["id"]

            # Tell the user exactly what will happen. The notification is also
            # scheduled for deletion, so no leftover auto-delete message remains.
            notice = send_message(
                user_chat_id,
                AUTO_DELETE_MSG.format(time=format_duration(delay))
            )

            messages_to_delete = list(copied)
            if notice and notice.get("message_id"):
                messages_to_delete.append(notice["message_id"])

            schedule_auto_deletion(
                user_chat_id,
                messages_to_delete,
                delay
            )
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
    text = """<b>Annie's Bookshelf - Help</b>

<b>What is this bot?</b>
This bot helps you access books that are agreed to read by people in Annie's Bookshelf.

<b>How to use?</b>
1. Start the bot with <b>/start</b>
2. Open a book using a shared book link
3. Use <b>/ping</b> to check whether the bot is responding

<b>User Commands:</b>
/start - Start the bot or open a shared book link
/ping - Check bot response time
/help - Show this help message
/genshin - Genshin Impact profile and showcase commands
/gi [UID] - View a Genshin profile
/gisave UID - Save your Genshin UID
/gicharacters [UID] - View showcase characters
/gibuilds [UID] - View character stats, weapons and artifacts

<b>Need help?</b>
Contact the bot owner for support."""

    send_message(message["chat"]["id"], text, reply_to=message.get("message_id"), disable_preview=True)



def handle_admin_help(message):
    uid = user_id(message)
    if not is_admin(uid):
        send_message(
            message["chat"]["id"],
            "❌ This command is available to admins only.",
            reply_to=message.get("message_id"),
        )
        return

    text = """<b>🛠 Admin Help</b>

<b>📚 Book Management</b>
/files - View the indexed book catalog
/rename - Rename a book and update its index
/removebook - Remove a book from the index

<b>👥 Admin Management</b>
/addadmin - Add an admin
/removeadmin - Remove an admin
/listadmins - List all admins

<b>⚙️ Bot Settings</b>
/setautodelete - Set automatic file deletion duration
/autodelete - View the current auto-delete setting

<b>📊 Statistics & Utilities</b>
/stats - View bot statistics
/topbooks - Show most downloaded books
/topusers - Show most active downloaders
/batch - Generate links for multiple files
/genlink - Generate a link for a file
/users - View user information
/broadcast - Broadcast a message
/ping - Check bot response time

<b>🎮 Genshin Impact</b>
/genshin - Show Genshin commands
/gi [UID] - View a player profile
/gisave UID - Save your Genshin UID
/gicharacters [UID] - View showcase characters
/gibuilds [UID] - View character builds, weapons and artifacts
/genshinfeature on|off|status - Enable or disable Genshin for everyone

<b>ℹ️ Help</b>
/help - Show user commands
/adminhelp - Show this admin help

<i>All commands above are restricted to authorized admins where applicable.</i>"""

    send_message(
        message["chat"]["id"],
        text,
        reply_to=message.get("message_id"),
        disable_preview=True,
    )


def handle_ping(message):
    start = time.perf_counter()
    sent = send_message(message["chat"]["id"], "Pinging...")
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    edit_message(
        message["chat"]["id"],
        sent["message_id"],
        f"Pong!\nResponse time: <code>{elapsed}ms</code>"
    )


def _display_book_title(filename):
    """Create a readable display title without changing the stored filename."""
    name = Path(str(filename or "Unnamed book")).name
    stem = Path(name).stem
    # Telegram-uploaded filenames often contain underscore separators and
    # repeated metadata fragments. Normalize whitespace for a cleaner catalog.
    stem = re.sub(r"[_\s]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .-_")
    return stem or "Untitled book"


def _short_button_title(title, limit=42):
    title = re.sub(r"\s+", " ", title).strip()
    return title if len(title) <= limit else title[:limit - 1].rstrip() + "…"


def build_files_page(page):
    per_page = 8
    snapshot = [item for item in file_index if is_supported_book_name(item.get("file_name"))]
    total_files = len(snapshot)
    total_pages = max(1, (total_files + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    selected = snapshot[(page - 1) * per_page:page * per_page]

    first_item = (page - 1) * per_page + 1 if total_files else 0
    last_item = min(page * per_page, total_files)
    text = (
        f"<b>📚 Available Books</b>\n"
        f"<i>{first_item}–{last_item} of {total_files} • Page {page}/{total_pages}</i>\n\n"
    )
    buttons = []

    for number, item in enumerate(selected, start=first_item):
        msg_id = item["message_id"]
        converted = msg_id * abs(CHANNEL_ID)
        payload = encode(f"get-{converted}")
        link = bot_link(payload)
        filename = item.get("file_name") or "Unnamed book"
        title = _display_book_title(filename)
        extension = Path(filename).suffix.lower().lstrip(".").upper() or "BOOK"
        size = format_size(item.get("file_size"))
        text += (
            f"<b>{number}. {escape(title)}</b>\n"
            f"<i>📄 {extension}  •  {escape(str(size))}</i>\n\n"
        )
        buttons.append([{"text": f"⬇️ {number}. {_short_button_title(title)}", "url": link}])

    nav = []
    if page > 1:
        nav.append({"text": "‹ Previous", "callback_data": f"files_page_{page - 1}"})
    if page < total_pages:
        nav.append({"text": "Next ›", "callback_data": f"files_page_{page + 1}"})
    if nav:
        buttons.append(nav)
    buttons.append([{"text": "✕ Close", "callback_data": "close"}])

    return text.rstrip(), {"inline_keyboard": buttons}


def parse_channel_message_id(value):
    """Accept a bare channel post ID or a Telegram channel post URL."""
    value = (value or "").strip()
    if value.isdigit():
        return int(value)

    match = re.fullmatch(r"https?://t\.me/(?:c/)?([^/]+)/([0-9]+)(?:\?.*)?", value)
    if not match:
        return None

    channel_part, message_part = match.groups()
    if channel_part.isdigit():
        # Private channel links use /c/<internal-id>/<message-id>.
        if str(CHANNEL_ID) != f"-100{channel_part}":
            return None
    elif CHANNEL_USERNAME and channel_part.lower() != CHANNEL_USERNAME.lower():
        return None
    return int(message_part)


def handle_removebook(message, args):
    """Delete a book channel post and remove its catalog entry.

    Supports:
      1. Reply to the book message with /removebook.
      2. /removebook <message_id>.
      3. /removebook <channel_post_link>.

    A command sent directly in the configured channel is also accepted when
    it is a reply to a channel post. Only channel admins can normally post
    there, so this is useful when an admin wants to remove a book without
    leaving the channel.
    """
    private_admin = is_admin(user_id(message))
    in_configured_channel = int(message.get("chat", {}).get("id", 0)) == CHANNEL_ID
    if not private_admin and not in_configured_channel:
        return

    chat_id = message["chat"]["id"]
    msg_id = None

    # Preferred shortcut: reply to a forwarded/channel book message.
    # message_id_from_link_or_forward() handles Telegram's current
    # forward_origin format as well as legacy forwarded-message fields.
    replied = message.get("reply_to_message")
    if replied:
        msg_id = message_id_from_link_or_forward(replied) or None

        # A reply can also point directly at a channel message when Telegram
        # includes the original chat/message metadata.
        if not msg_id:
            replied_chat = replied.get("chat") or {}
            if int(replied_chat.get("id", 0)) == CHANNEL_ID and replied.get("message_id"):
                msg_id = int(replied["message_id"])

    # Explicit ID/link still works and takes precedence when supplied.
    if args:
        msg_id = parse_channel_message_id(args[0])

    if not msg_id:
        send_message(
            chat_id,
            "Usage:\n"
            "• Reply to a forwarded book message with <code>/removebook</code>\n"
            "• Or use <code>/removebook &lt;message_id&gt;</code>\n"
            "• Or use <code>/removebook &lt;channel_post_link&gt;</code>\n\n"
            "The command deletes the original channel post and removes its /files index entry."
        )
        return

    existed = lookup_file_info(msg_id) is not None

    # Delete the source book from the configured Telegram channel first.
    # Only remove the catalog entry after Telegram confirms the deletion, so
    # a permissions/API failure does not leave a downloadable stale entry.
    try:
        tg("deleteMessage", {
            "chat_id": CHANNEL_ID,
            "message_id": int(msg_id),
        })
    except Exception as exc:
        print(f"removebook channel deletion failed for {msg_id}: {exc}")
        send_message(
            chat_id,
            f"❌ Could not delete channel post <code>{msg_id}</code>.\n\n"
            "The book was kept in the /files index. Make sure the bot is an admin "
            "in the channel with permission to delete messages."
        )
        return

    remove_file_index(msg_id)
    if existed:
        send_message(
            chat_id,
            f"✅ Book <code>{msg_id}</code> was deleted from the channel and removed from the /files index."
        )
    else:
        send_message(
            chat_id,
            f"✅ Channel post <code>{msg_id}</code> was deleted.\n"
            "It was not present in the /files index."
        )


def handle_files(message):
    if not is_admin(user_id(message)):
        send_message(
            message["chat"]["id"],
            "❌ The /files command is available to admins only."
        )
        return

    supported_files = [item for item in file_index if is_supported_book_name(item.get("file_name"))]
    if not supported_files:
        send_message(
            message["chat"]["id"],
            "No PDF or EPUB files are indexed yet.\n\n"
            "Only PDF and EPUB books can generate download links."
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

    # Link generation is restricted to PDF and EPUB books. Prefer the
    # forwarded message metadata, otherwise use the persistent file index.
    incoming_info = file_info_from_message(message)
    indexed_info = lookup_file_info(msg_id)
    book_info = incoming_info if incoming_info else indexed_info
    if not is_supported_book_info(book_info):
        send_message(message["chat"]["id"], unsupported_book_message())
        if action["type"] == "genlink" or action.get("step") == 1:
            pending_actions.pop(uid, None)
        return True

    # A forwarded channel post may contain the document metadata. Keep the
    # file index populated even when the post was published before this
    # webhook was installed. This is the supported way to backfill /files
    # because Telegram Bot API cannot read arbitrary channel history.
    if file_info_from_message(message):
        add_file_index({
            **message,
            "message_id": msg_id,
            "chat": {"id": CHANNEL_ID},
        })

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

    if remove_id in DEFAULT_ADMINS:
        send_message(
            message["chat"]["id"],
            "This is a default admin configured in <code>DEFAULT_ADMINS</code> and cannot be removed with /removeadmin. "
            "Remove the ID from the Render environment variable if you want to revoke access."
        )
        return

    ADMINS.discard(remove_id)
    persist_admins()
    username = identifier if str(identifier).startswith("@") else ""
    label = f"{username} (<code>{remove_id}</code>)" if username else f"<code>{remove_id}</code>"
    send_message(message["chat"]["id"], f"User {label} has been removed from admins.")


def handle_listadmins(message):
    """Show admins with display names, role/source, and Telegram IDs."""
    if not is_admin(user_id(message)):
        return

    admin_ids = sorted(ADMINS, key=lambda value: (value != OWNER_ID, value))
    if not admin_ids:
        send_message(message["chat"]["id"], "<b>Admin Management</b>\n\nNo admins are configured.")
        return

    # Start with profiles previously observed when users interacted with the bot.
    profiles_by_id = {}
    for profile in user_profiles.values():
        try:
            profile_id = int(profile.get("id"))
        except (TypeError, ValueError, AttributeError):
            continue
        profiles_by_id[profile_id] = profile

    # Ask Telegram for each account profile by numeric ID. This works when the
    # Bot API can resolve that private chat; otherwise retain a clear ID-based fallback.
    for admin_id in admin_ids:
        try:
            chat = tg_get("getChat", {"chat_id": admin_id})
            if chat and chat.get("type") == "private":
                profiles_by_id[admin_id] = {
                    "id": admin_id,
                    "first_name": chat.get("first_name", ""),
                    "last_name": chat.get("last_name", ""),
                    "username": chat.get("username", ""),
                }
        except Exception:
            pass

    lines = [
        "<b>👥 Admin Management</b>",
        f"<b>Total admins:</b> {len(admin_ids)}",
        "",
    ]

    for number, admin_id in enumerate(admin_ids, start=1):
        profile = profiles_by_id.get(admin_id, {})
        full_name = " ".join(
            part for part in (profile.get("first_name", ""), profile.get("last_name", "")) if part
        ).strip()
        username = profile.get("username")
        display_name = full_name or (f"@{username}" if username else f"Account ID {admin_id} (name unavailable)")
        if username and full_name:
            display_name += f" (@{username})"

        if admin_id == OWNER_ID and OWNER_ID:
            role = "👑 Owner"
        elif admin_id in DEFAULT_ADMINS:
            role = "🛡 Default admin"
        else:
            role = "✅ Admin"

        lines.extend([
            f"<b>{number}. {escape(display_name)}</b>",
            f"   {role}",
            f"   ID: <code>{admin_id}</code>",
            "",
        ])

    lines.append("<i>Use /addadmin and /removeadmin to manage access.</i>")
    send_message(message["chat"]["id"], "\n".join(lines), disable_preview=True)


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
            "<b>Annie's Bookshelf\n\n"
            "A bot to share and access books from Annie's Bookshelf.\n\n"
            "Language : <code>Python3</code>\n"
            "Library : <code>Flask + Telegram Bot API</code></b>",
            reply_markup=about_markup()
        )
    elif data == "close":
        delete_message(chat_id, message_id)
    elif data.startswith("files_page_"):
        callback_user_id = int((query.get("from") or {}).get("id", 0))
        if not is_admin(callback_user_id):
            answer_callback(query.get("id"), "The book catalog is available to admins only.")
            return
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
    if not is_supported_book_info(info):
        send_message(message["chat"]["id"], unsupported_book_message())
        return True

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

    # Admin channel commands are delivered as channel_post updates rather
    # than normal message updates. Handle /removebook here so an admin can
    # reply directly to a book post in the channel.
    command, args = command_parts(message)
    if command == "/removebook":
        handle_removebook(message, args)
        return

    # Always index the post. DISABLE_CHANNEL_BUTTON only controls the
    # share button, not whether the file appears in /files.
    info = file_info_from_message(message)
    if info and is_supported_book_info(info):
        add_file_index(message)
    else:
        info = None

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
    """Download a Telegram file using the public Bot API.

    Telegram's public Bot API currently limits getFile downloads to 20 MB.
    The caller checks the size and reports a useful error for larger files.
    """
    file_data = tg("getFile", {"file_id": file_id})
    file_path = file_data.get("file_path")
    if not file_path:
        raise RuntimeError("Telegram did not return a file path.")

    response = session.get(
        f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}",
        stream=True,
        timeout=120,
    )
    response.raise_for_status()

    suffix = Path(file_path).suffix
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        with temp_file as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
        return temp_file.name
    except Exception:
        try:
            os.remove(temp_file.name)
        except OSError:
            pass
        raise


def _rename_target_channel_message(reply):
    """Return the original DB-channel message id for a replied document."""
    forwarded_id = message_id_from_link_or_forward(reply)
    if forwarded_id:
        return forwarded_id

    document = reply.get("document") or {}
    indexed = lookup_file_by_identity(document)
    if indexed:
        return int(indexed.get("message_id", 0)) or 0
    return 0


def handle_rename(message, args):
    chat_id = message["chat"]["id"]

    if not is_private(message):
        return
    if not is_admin(user_id(message)):
        send_message(chat_id, "❌ Only admins can use /rename.")
        return

    reply = message.get("reply_to_message")
    if not reply:
        send_message(
            chat_id,
            "❌ Reply to the DB channel document (forward it to the bot) and use:\n\n"
            "/rename New File Name.pdf"
        )
        return

    document = reply.get("document")
    if not document:
        send_message(chat_id, "❌ The replied message does not contain a document.")
        return

    new_name = " ".join(args).strip()
    if not new_name:
        send_message(
            chat_id,
            "❌ Please provide a new filename.\n\n"
            "Example:\n/rename My New Book.pdf"
        )
        return

    old_name = (document.get("file_name") or "").strip()
    if not Path(new_name).suffix and Path(old_name).suffix:
        new_name += Path(old_name).suffix
    if not is_supported_book_name(new_name):
        send_message(chat_id, "❌ The new filename must end with .pdf or .epub.")
        return

    invalid_chars = '<>:"/\\|?*'
    if any(char in new_name for char in invalid_chars) or new_name in (".", ".."):
        send_message(
            chat_id,
            "❌ Invalid filename.\nPlease remove characters like: < > : \" / \\ | ? *"
        )
        return

    # Telegram's public Bot API cannot download files larger than 20 MB.
    file_size = document.get("file_size")
    if file_size and int(file_size) > 20 * 1024 * 1024:
        send_message(
            chat_id,
            "❌ This file is larger than 20 MB. Telegram's public Bot API "
            "does not allow the bot to download files this large for renaming.\n\n"
            "Files up to 20 MB can be renamed with this Flask + Bot API version."
        )
        return

    old_channel_id = _rename_target_channel_message(reply)
    if not old_channel_id:
        send_message(
            chat_id,
            "❌ I couldn't identify the original DB channel post.\n\n"
            "Forward the document directly from the DB channel to this bot, "
            "then reply to that forwarded document with /rename ..."
        )
        return

    wait = send_message(chat_id, "⏳ Downloading and uploading the renamed file...")
    temp_path = None

    try:
        temp_path = download_telegram_file(document["file_id"])
        caption = reply.get("caption") or ""
        caption_entities = reply.get("caption_entities")
        upload_data = {
            "chat_id": CHANNEL_ID,
            "caption": caption,
            "protect_content": str(PROTECT_CONTENT).lower(),
        }
        if caption_entities:
            upload_data["caption_entities"] = json.dumps(caption_entities)

        with open(temp_path, "rb") as file_handle:
            response = session.post(
                f"{API}/sendDocument",
                data=upload_data,
                files={"document": (new_name, file_handle)},
                timeout=180,
            )

        result = response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description", "Telegram upload failed."))

        new_channel_message = result["result"]
        new_channel_id = int(new_channel_message["message_id"])

        # Replace the old index entry with the renamed channel post in both
        # MongoDB and the local cache. The new Telegram message ID and filename
        # become the canonical catalog entry.
        replace_file_index(old_channel_id, new_channel_message)

        payload = encode(f"get-{new_channel_id * abs(CHANNEL_ID)}")
        link = bot_link(payload)
        markup = share_button(link)
        try:
            edit_reply_markup(CHANNEL_ID, new_channel_id, markup)
        except Exception as exc:
            print(f"Could not add rename share button: {exc}")

        # The renamed file is now the canonical DB-channel copy.
        delete_message(CHANNEL_ID, old_channel_id)

        edit_message(
            chat_id,
            wait["message_id"],
            f"<b>✅ File renamed successfully.</b>\n\n"
            f"New name: <code>{escape(new_name)}</code>\n\n"
            f"<b>New link:</b>\n{link}",
            reply_markup=markup,
        )

    except Exception as exc:
        print(f"Rename error: {exc}")
        edit_message(
            chat_id,
            wait["message_id"],
            f"❌ Rename failed.\n\n<code>{escape(str(exc))}</code>"
        )
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


# ------------------------- Genshin Impact module -------------------------

_ENKA_API = "https://enka.network/api/uid/{uid}/"
_ENKA_HEADERS = {"User-Agent": "AnniesBookshelfBot/1.0 (Telegram bot; Enka.Network API client)"}
_gi_profiles_local = load_json(GENSHIN_PROFILES_FILE, {})
_gi_cache_local = load_json(GENSHIN_CACHE_FILE, {})


def genshin_enabled():
    """Read the shared feature flag from MongoDB, with JSON fallback."""
    if mongo_settings is not None:
        try:
            doc = mongo_settings.find_one({"_id": "genshin_feature"}) or {}
            return bool(doc.get("enabled", True))
        except Exception as exc:
            print(f"Could not read Genshin feature setting: {exc}")
    settings = load_json(SETTINGS_FILE, {})
    return bool(settings.get("genshin_enabled", True))


def set_genshin_enabled(enabled):
    if mongo_settings is not None:
        mongo_settings.update_one(
            {"_id": "genshin_feature"},
            {"$set": {"enabled": bool(enabled), "updated_at": datetime.utcnow()}},
            upsert=True,
        )
    settings = load_json(SETTINGS_FILE, {})
    settings["genshin_enabled"] = bool(enabled)
    save_json(SETTINGS_FILE, settings)


def _uid_region(uid):
    # Genshin UID first digit identifies the server region.
    return {"6": "America", "7": "Europe", "8": "Asia", "9": "TW/HK/MO"}.get(uid[0], "Unknown")


def _get_saved_genshin_uid(telegram_user_id):
    key = str(int(telegram_user_id))
    if mongo_genshin_profiles is not None:
        doc = mongo_genshin_profiles.find_one({"telegram_user_id": int(telegram_user_id)}) or {}
        return doc.get("genshin_uid")
    return (_gi_profiles_local.get(key) or {}).get("genshin_uid")


def _save_genshin_uid(telegram_user_id, uid):
    record = {
        "telegram_user_id": int(telegram_user_id),
        "genshin_uid": uid,
        "region": _uid_region(uid),
        "updated_at": datetime.utcnow().isoformat(),
    }
    if mongo_genshin_profiles is not None:
        mongo_genshin_profiles.update_one(
            {"telegram_user_id": int(telegram_user_id)},
            {"$set": record},
            upsert=True,
        )
    else:
        _gi_profiles_local[str(int(telegram_user_id))] = record
        save_json(GENSHIN_PROFILES_FILE, _gi_profiles_local)


def _get_genshin_data(uid):
    now = datetime.utcnow()
    if mongo_genshin_cache is not None:
        cached = mongo_genshin_cache.find_one({"uid": uid})
        if cached and cached.get("expires_at") and cached["expires_at"] > now:
            return cached.get("data") or {}
    else:
        cached = _gi_cache_local.get(uid)
        if cached and float(cached.get("expires_at", 0)) > time.time():
            return cached.get("data") or {}

    response = session.get(
        _ENKA_API.format(uid=uid),
        headers=_ENKA_HEADERS,
        timeout=20,
    )
    if response.status_code == 400:
        raise ValueError("That UID format is invalid. Please check the 9-digit UID.")
    if response.status_code == 404:
        raise ValueError("Player not found. Please check the UID.")
    if response.status_code == 429:
        raise ValueError("Enka.Network is rate-limiting requests. Please try again later.")
    if response.status_code == 424:
        raise ValueError("Genshin data is temporarily unavailable during a game update.")
    if response.status_code >= 500:
        raise ValueError("Enka.Network is temporarily unavailable. Please try again later.")
    response.raise_for_status()
    data = response.json()
    ttl = max(60, min(int(data.get("ttl", 300) or 300), 86400))
    expires_at = now + timedelta(seconds=ttl)
    if mongo_genshin_cache is not None:
        mongo_genshin_cache.update_one(
            {"uid": uid},
            {"$set": {"uid": uid, "data": data, "expires_at": expires_at, "cached_at": now}},
            upsert=True,
        )
    else:
        _gi_cache_local[uid] = {"data": data, "expires_at": time.time() + ttl}
        save_json(GENSHIN_CACHE_FILE, _gi_cache_local)
    return data


def _gi_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# Enka's fightPropMap uses numeric property IDs. Convert them into labels
# before displaying anything to Telegram users.
_GI_FIGHT_PROPS = {
    "2000": ("Max HP", "number"),
    "2001": ("ATK", "number"),
    "2002": ("DEF", "number"),
    "2003": ("Elemental Mastery", "number"),
    "2004": ("CRIT DMG", "percent_ratio"),
    "2005": ("CRIT Rate", "percent_ratio"),
    "2006": ("Energy Recharge", "percent_ratio"),
    "2010": ("Healing Bonus", "percent_ratio"),
    "2011": ("Incoming Healing Bonus", "percent_ratio"),
    "2012": ("Physical DMG Bonus", "percent_ratio"),
    "2032": ("Pyro DMG Bonus", "percent_ratio"),
    "2033": ("Electro DMG Bonus", "percent_ratio"),
    "2034": ("Hydro DMG Bonus", "percent_ratio"),
    "2035": ("Dendro DMG Bonus", "percent_ratio"),
    "2036": ("Anemo DMG Bonus", "percent_ratio"),
    "2037": ("Geo DMG Bonus", "percent_ratio"),
    "2038": ("Cryo DMG Bonus", "percent_ratio"),
}
_GI_STAT_NAMES = {
    "FIGHT_PROP_HP": "HP", "FIGHT_PROP_HP_PERCENT": "HP%",
    "FIGHT_PROP_ATTACK": "ATK", "FIGHT_PROP_ATTACK_PERCENT": "ATK%",
    "FIGHT_PROP_DEFENSE": "DEF", "FIGHT_PROP_DEFENSE_PERCENT": "DEF%",
    "FIGHT_PROP_CRITICAL": "CRIT Rate", "FIGHT_PROP_CRITICAL_HURT": "CRIT DMG",
    "FIGHT_PROP_CHARGE效率": "Energy Recharge", "FIGHT_PROP_CHARGE_EFFICIENCY": "Energy Recharge",
    "FIGHT_PROP_ELEMENT_MASTERY": "Elemental Mastery",
    "FIGHT_PROP_HEAL加成": "Healing Bonus", "FIGHT_PROP_HEAL加成": "Healing Bonus",
    "FIGHT_PROP_PHYSICAL_ADD_HURT": "Physical DMG Bonus",
    "FIGHT_PROP_FIRE_ADD_HURT": "Pyro DMG Bonus", "FIGHT_PROP_ELEC_ADD_HURT": "Electro DMG Bonus",
    "FIGHT_PROP_WATER_ADD_HURT": "Hydro DMG Bonus", "FIGHT_PROP_GRASS_ADD_HURT": "Dendro DMG Bonus",
    "FIGHT_PROP_WIND_ADD_HURT": "Anemo DMG Bonus", "FIGHT_PROP_ROCK_ADD_HURT": "Geo DMG Bonus",
    "FIGHT_PROP_ICE_ADD_HURT": "Cryo DMG Bonus",
}


def _gi_percent(value, already_percent=False):
    number = _gi_number(value)
    if not already_percent and abs(number) <= 3:
        number *= 100
    return f"{number:.1f}%"


def _gi_prop_name(prop_id):
    value = str(prop_id or "")
    if value in _GI_STAT_NAMES:
        return _GI_STAT_NAMES[value]
    # Enka may return a numeric property identifier for artifact stats.
    numeric_names = {
        "FIGHT_PROP_HP": "HP", "FIGHT_PROP_ATTACK": "ATK",
        "FIGHT_PROP_DEFENSE": "DEF", "FIGHT_PROP_CRITICAL": "CRIT Rate",
        "FIGHT_PROP_CRITICAL_HURT": "CRIT DMG", "FIGHT_PROP_ELEMENT_MASTERY": "Elemental Mastery",
        "FIGHT_PROP_CHARGE_EFFICIENCY": "Energy Recharge",
    }
    return numeric_names.get(value, value.replace("FIGHT_PROP_", "").replace("_", " ").title() or "Stat")


def _gi_stat_value(prop_id, value):
    name = _gi_prop_name(prop_id)
    if "%" in name or name in ("CRIT Rate", "CRIT DMG", "Energy Recharge", "Healing Bonus", "Physical DMG Bonus", "Pyro DMG Bonus", "Electro DMG Bonus", "Hydro DMG Bonus", "Dendro DMG Bonus", "Anemo DMG Bonus", "Geo DMG Bonus", "Cryo DMG Bonus"):
        return _gi_percent(value)
    number = _gi_number(value)
    return f"{number:,.0f}" if number.is_integer() else f"{number:,.1f}"


def _gi_character_name(avatar):
    avatar_id = str(avatar.get("avatarId", ""))

    return GENSHIN_CHARACTER_NAMES.get(
        avatar_id,
        f"Character #{avatar_id}" if avatar_id else "Unknown Character"
    )


def _gi_character_level(avatar):
    for prop in (avatar.get("propMap") or {}).values():
        if str(prop.get("type", "")) == "4001":
            return str(prop.get("val", "?"))
    return "?"


def _gi_character_lines(data):
    avatars = data.get("avatarInfoList") or []
    if not avatars:
        return "No showcase characters were found. Ask the player to enable <b>Show Character Details</b> in their in-game profile."
    lines = ["<b>🌟 Public Character Showcase</b>"]
    for avatar in avatars[:8]:
        name = escape(_gi_character_name(avatar))
        level = escape(_gi_character_level(avatar))
        constellations = len(avatar.get("talentIdList") or [])
        skills = list((avatar.get("skillLevelMap") or {}).values())[:3]
        talents = " / ".join(str(v) for v in skills) if skills else "Not provided"
        lines.append(
            f"\n<b>{name}</b>\n"
            f"Level <b>{level}</b> · Constellation <b>C{constellations}</b>\n"
            f"Talents: {escape(talents)}"
        )
    if len(avatars) > 8:
        lines.append(f"\n<i>Showing 8 of {len(avatars)} showcase characters.</i>")
    return "\n".join(lines)


def _gi_equipment(avatar):
    weapon = None
    artifacts = []
    for item in avatar.get("equipList") or []:
        flat = item.get("flat") or {}
        item_type = str(flat.get("itemType", ""))
        if "WEAPON" in item_type or item.get("weapon"):
            weapon = item
        elif "RELIQUARY" in item_type or item.get("reliquary"):
            artifacts.append(item)
    return weapon, artifacts


def _gi_build_lines(data):
    avatars = data.get("avatarInfoList") or []
    if not avatars:
        return "No public character build data was found. Ask the player to enable <b>Show Character Details</b> in-game."

    sections = ["<b>🛠️ Character Builds</b>"]
    for avatar in avatars[:8]:
        name = escape(_gi_character_name(avatar))
        level = escape(_gi_character_level(avatar))
        fight = avatar.get("fightPropMap") or {}
        stats = []
        for prop_id, (label, kind) in _GI_FIGHT_PROPS.items():
            if prop_id not in fight:
                continue
            value = _gi_number(fight[prop_id])
            if kind == "percent_ratio":
                display = _gi_percent(value)
            else:
                display = f"{value:,.0f}"
            stats.append(f"{label}: <b>{display}</b>")
        # Keep the key combat stats easy to scan, even if some are absent.
        if not stats:
            stats.append("Combat stats were not included in the public response.")

        weapon, artifacts = _gi_equipment(avatar)
        section = [f"\n<b>✨ {name}</b> · Lv. {level}", "\n".join(stats)]
        if weapon:
            flat = weapon.get("flat") or {}
            weapon_name = flat.get("name") or flat.get("weaponName") or "Equipped weapon"
            weapon_data = weapon.get("weapon") or {}
            weapon_level = weapon_data.get("level")
            refinement = None
            affixes = weapon_data.get("affixMap") or {}
            if affixes:
                try:
                    refinement = max(int(v) for v in affixes.values()) + 1
                except (TypeError, ValueError):
                    refinement = None
            weapon_detail = f" · Lv. {weapon_level}" if weapon_level is not None else ""
            if refinement:
                weapon_detail += f" · R{refinement}"
            section.append(f"⚔️ <b>Weapon:</b> {escape(str(weapon_name))}{weapon_detail}")
        else:
            section.append("⚔️ <b>Weapon:</b> Not shown")

        if artifacts:
            section.append(f"🧿 <b>Artifacts:</b> {len(artifacts)} equipped")
            for artifact in artifacts[:5]:
                flat = artifact.get("flat") or {}
                artifact_name = flat.get("name") or "Artifact"
                reliquary = artifact.get("reliquary") or {}
                artifact_level = reliquary.get("level")
                main = flat.get("reliquaryMainstat") or {}
                main_id = main.get("mainPropId") or main.get("appendPropId")
                main_value = main.get("statValue")
                main_text = "Main stat unavailable"
                if main_id:
                    main_text = f"{_gi_prop_name(main_id)}: {_gi_stat_value(main_id, main_value)}"
                substats = []
                for sub in (flat.get("reliquarySubstats") or [])[:4]:
                    prop_id = sub.get("appendPropId") or sub.get("propId")
                    if prop_id:
                        substats.append(f"{_gi_prop_name(prop_id)} +{_gi_stat_value(prop_id, sub.get('statValue'))}")
                try:
                    level_text = f" +{max(0, int(artifact_level) - 1)}" if artifact_level is not None else ""
                except (TypeError, ValueError):
                    level_text = ""
                section.append(
                    f"  • <b>{escape(str(artifact_name))}{level_text}</b>\n"
                    f"    Main: {escape(main_text)}\n"
                    f"    Substats: {escape(' · '.join(substats) if substats else 'Not provided')}"
                )
        else:
            section.append("🧿 <b>Artifacts:</b> No artifact details in showcase response")
        sections.append("\n".join(section))
    if len(avatars) > 8:
        sections.append(f"<i>Showing 8 of {len(avatars)} showcase characters.</i>")
    return "\n\n".join(sections)


def _gi_profile_text(uid, data):
    player = data.get("playerInfo") or {}
    nickname = escape(str(player.get("nickname") or "Unknown player"))
    signature = escape(str(player.get("signature") or "Not set"))
    achievements = player.get("finishAchievementNum", "N/A")
    abyss_floor = player.get("towerFloorIndex")
    abyss_chamber = player.get("towerLevelIndex")
    abyss = f"Floor {abyss_floor}, Chamber {abyss_chamber}" if abyss_floor and abyss_chamber else "Not available"
    showcase_count = len(data.get("avatarInfoList") or [])
    return "\n".join([
        "<b>🎮 GENSHIN IMPACT PLAYER PROFILE</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"👤 <b>{nickname}</b>",
        f"🆔 UID: <code>{uid}</code>",
        f"🌏 Server: <b>{_uid_region(uid)}</b>",
        "",
        "<b>PLAYER PROGRESS</b>",
        f"🏅 Adventure Rank: <b>{escape(str(player.get('level', 'N/A')))}</b>",
        f"🌐 World Level: <b>{escape(str(player.get('worldLevel', 'N/A')))}</b>",
        f"🏆 Achievements: <b>{escape(str(achievements))}</b>",
        f"🌀 Spiral Abyss: <b>{escape(abyss)}</b>",
        f"🌟 Showcase Characters: <b>{showcase_count}</b>",
        "",
        "<b>PLAYER SIGNATURE</b>",
        signature,
        "",
        "<i>Information is limited to the player's public in-game showcase.</i>",
        "Use /gicharacters for the character list or /gibuilds for equipment and stats.",
    ])

def _genshin_uid_for(message, args):
    if args:
        uid = args[0].strip()
    else:
        uid = _get_saved_genshin_uid(user_id(message))
    if not uid:
        return None, "No UID supplied or saved. Use <code>/gi 800000000</code> or <code>/gisave 800000000</code>."
    if not re.fullmatch(r"[6789]\d{8}", str(uid)):
        return None, "Please provide a valid 9-digit Genshin UID beginning with 6, 7, 8 or 9."
    return str(uid), None


def _genshin_guard(message):
    if not genshin_enabled():
        send_message(message["chat"]["id"], "🎮 The Genshin Impact feature is currently disabled by an admin.", reply_to=message.get("message_id"))
        return False
    return True


def handle_genshin_feature(message, args):
    chat_id = message["chat"]["id"]
    if not is_admin(user_id(message)):
        send_message(chat_id, "❌ Only admins can change the Genshin feature setting.")
        return
    action = (args[0].lower() if args else "status")
    if action == "on":
        set_genshin_enabled(True)
        text = "✅ Genshin Impact commands are now enabled for everyone."
    elif action == "off":
        set_genshin_enabled(False)
        text = "🔒 Genshin Impact commands are now disabled for everyone."
    elif action == "status":
        text = f"🎮 Genshin Impact feature: <b>{'ENABLED' if genshin_enabled() else 'DISABLED'}</b>"
    else:
        text = "Usage: <code>/genshinfeature on</code>, <code>/genshinfeature off</code> or <code>/genshinfeature status</code>"
    send_message(chat_id, text, reply_to=message.get("message_id"))


def handle_genshin_command(message, command, args):
    chat_id = message["chat"]["id"]
    if not _genshin_guard(message):
        return
    if command == "/genshin":
        send_message(chat_id,
            "<b>🎮 Genshin Impact Commands</b>\n\n"
            "/gi [UID] - View player profile\n"
            "/gisave UID - Save your UID\n"
            "/gicharacters [UID] - View showcase characters\n"
            "/gibuilds [UID] - View stats, weapons and artifacts\n\n"
            "Region is detected automatically from the UID. Only public showcase data is available.",
            reply_to=message.get("message_id"))
        return
    if command == "/gisave":
        if not args or not re.fullmatch(r"[6789]\d{8}", args[0]):
            send_message(chat_id, "Usage: <code>/gisave 800000000</code> (9-digit UID)")
            return
        uid = args[0]
        _save_genshin_uid(user_id(message), uid)
        send_message(chat_id, f"✅ Your Genshin UID <code>{uid}</code> ({_uid_region(uid)}) has been saved.", reply_to=message.get("message_id"))
        return

    uid, error = _genshin_uid_for(message, args)
    if error:
        send_message(chat_id, error, reply_to=message.get("message_id"))
        return
    wait = send_message(chat_id, "⏳ Fetching Genshin showcase data from Enka.Network...")
    try:
        data = _get_genshin_data(uid)
        if command == "/gi":
            text = _gi_profile_text(uid, data)
        elif command == "/gicharacters":
            text = f"<b>🌟 Showcase Characters — {uid}</b>\n\n" + _gi_character_lines(data)
        else:
            text = f"<b>🛠 Character Builds — {uid}</b>\n" + _gi_build_lines(data)
        # Telegram message text is limited to 4096 characters.
        edit_message(chat_id, wait["message_id"], text[:4000])
    except ValueError as exc:
        edit_message(chat_id, wait["message_id"], f"❌ {escape(str(exc))}")
    except requests.RequestException as exc:
        print(f"Enka request failed for {uid}: {exc}")
        edit_message(chat_id, wait["message_id"], "❌ Could not reach Enka.Network. Please try again later.")
    except Exception as exc:
        print(f"Genshin command error ({command}, {uid}): {exc}")
        edit_message(chat_id, wait["message_id"], "❌ Something went wrong while reading the Genshin profile. Please try again later.")


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
    elif command == "/adminhelp" and is_private(message):
        handle_admin_help(message)
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
    elif command == "/topbooks" and is_private(message):
        handle_topbooks(message)
    elif command == "/topusers" and is_private(message):
        handle_topusers(message)
    elif command == "/genshinfeature":
        handle_genshin_feature(message, args)
    elif command in ("/genshin", "/gi", "/gisave", "/gicharacters", "/gibuilds"):
        handle_genshin_command(message, command, args)
    elif command in ("/setautodelete", "/autodelete"):
        handle_auto_delete(message, args)
    elif command == "/rename" and is_private(message):
        return handle_rename(message, args)
    elif command == "/removebook" and is_private(message):
        handle_removebook(message, args)
    elif is_private(message) and process_pending(message):
        pass
    elif is_private(message) and not command and USER_REPLY_TEXT:
        # Do not answer admin media messages twice.
        if not file_info_from_message(message):
            send_message(message["chat"]["id"], USER_REPLY_TEXT)


def initialize():
    global BOT_ME, BOT_USERNAME, CHANNEL_USERNAME

    start_auto_delete_worker()
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
            payload = {
                "url": f"{WEBHOOK_URL}/webhook",
                "allowed_updates": [
                    "message",
                    "callback_query",
                    "channel_post",
                    "edited_channel_post"
                ]
            }
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
        "status": "Annie's Bookshelf is running",
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
        # Webhooks are also a cleanup opportunity. This matters on Render Free:
        # if the service was asleep when a deletion became due, the next request
        # immediately processes overdue deletion tasks.
        process_pending_deletions()

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
    payload = {
        "url": f"{public_url}/webhook",
        "allowed_updates": [
            "message",
            "callback_query",
            "channel_post",
            "edited_channel_post"
        ]
    }
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
