# Genshin Impact profile module for Annie's Bookshelf.
# Public showcase data is provided by Enka.Network. Only public showcase
# characters are available; this does not access private account data.

import asyncio
import html
import json
import os
import re
import time
from pathlib import Path

import requests
from pyrogram import filters
from pyrogram.types import Message

from bot import Bot
from config import ADMINS, OWNER_ID

ENKA_BASE = "https://enka.network/api/uid/{uid}/"
MONGO_URI = os.environ.get("MONGODB_URI", "").strip()
MONGO_DB_NAME = os.environ.get("MONGODB_DB_NAME", "book_sharing_bot")
LOCAL_STATE = Path(os.environ.get("DATA_DIR", ".")) / "genshin_settings.json"
CACHE_SECONDS = 300
_http = requests.Session()
_http.headers.update({"User-Agent": "AnniesBookshelfBot/1.0 (Genshin profile lookup)"})
_mongo = None
_profiles = None
_cache = None
_settings = None


def _collections():
    global _mongo, _profiles, _cache, _settings
    if _profiles is not None:
        return _profiles, _cache, _settings
    if not MONGO_URI:
        return None, None, None
    from pymongo import MongoClient, ASCENDING, DESCENDING
    _mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000)
    db = _mongo[MONGO_DB_NAME]
    _profiles, _cache, _settings = db["genshin_profiles"], db["genshin_cache"], db["settings"]
    _profiles.create_index([("telegram_user_id", ASCENDING)], unique=True)
    _cache.create_index([("uid", ASCENDING)], unique=True)
    return _profiles, _cache, _settings


def _local_settings():
    try:
        return json.loads(LOCAL_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _is_enabled():
    try:
        _, _, settings = _collections()
        if settings is not None:
            doc = settings.find_one({"_id": "genshin_feature"}) or {}
            return bool(doc.get("enabled", True))
    except Exception as exc:
        print(f"Genshin settings MongoDB read failed: {exc}")
    return bool(_local_settings().get("enabled", True))


def _set_enabled(enabled):
    _, _, settings = _collections()
    if settings is not None:
        settings.update_one(
            {"_id": "genshin_feature"},
            {"$set": {"enabled": bool(enabled), "updated_at": time.time()}},
            upsert=True,
        )
        return
    LOCAL_STATE.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_STATE.write_text(json.dumps({"enabled": bool(enabled)}), encoding="utf-8")


def _region(uid):
    first = str(uid)[0]
    return {"6": "America", "7": "Europe", "8": "Asia", "9": "TW/HK/MO", "1": "China"}.get(first, "Unknown")


def _valid_uid(uid):
    return bool(re.fullmatch(r"\d{9,10}", str(uid or "")))


def _save_uid(user_id, uid):
    profiles, _, _ = _collections()
    doc = {
        "telegram_user_id": int(user_id),
        "genshin_uid": str(uid),
        "region": _region(uid),
        "updated_at": time.time(),
    }
    if profiles is not None:
        profiles.update_one({"telegram_user_id": int(user_id)}, {"$set": doc}, upsert=True)
    else:
        # Local fallback is useful for development; configure MONGODB_URI for
        # persistence across serverless/function restarts or redeployments.
        path = Path(os.environ.get("DATA_DIR", ".")) / "genshin_profiles.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        data[str(user_id)] = doc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")


def _get_uid(user_id):
    profiles, _, _ = _collections()
    if profiles is not None:
        doc = profiles.find_one({"telegram_user_id": int(user_id)}) or {}
        return doc.get("genshin_uid")
    path = Path(os.environ.get("DATA_DIR", ".")) / "genshin_profiles.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(str(user_id), {}).get("genshin_uid")
    except Exception:
        return None


def _fetch_profile(uid):
    profiles, cache, _ = _collections()
    if cache is not None:
        cached = cache.find_one({"uid": str(uid)})
        if cached and time.time() - cached.get("cached_at", 0) < CACHE_SECONDS:
            return cached.get("data")
    response = _http.get(ENKA_BASE.format(uid=uid), timeout=15)
    if response.status_code == 404:
        raise ValueError("Profile not found. Check the UID and make sure Character Details are enabled in-game.")
    if response.status_code == 429:
        raise ValueError("Enka.Network is rate-limiting requests. Please try again in a minute.")
    response.raise_for_status()
    data = response.json()
    if not data.get("playerInfo"):
        raise ValueError("No public showcase profile was returned. Enable Character Details in Genshin and try again.")
    if cache is not None:
        cache.update_one(
            {"uid": str(uid)},
            {"$set": {"uid": str(uid), "data": data, "cached_at": time.time(), "ttl": CACHE_SECONDS}},
            upsert=True,
        )
    return data


def _stat_lines(character):
    fight = character.get("fightPropMap") or {}
    # Common Genshin fight property IDs: HP, ATK, DEF, crit rate, crit dmg, ER.
    fields = [
        ("HP", "2000"), ("ATK", "2001"), ("DEF", "2002"),
        ("CRIT Rate", "20"), ("CRIT DMG", "22"), ("Energy Recharge", "23"),
        ("Elemental Mastery", "28"),
    ]
    result = []
    for label, key in fields:
        value = fight.get(key)
        if value is not None:
            if label in ("CRIT Rate", "CRIT DMG", "Energy Recharge"):
                result.append(f"{label}: {float(value) * 100:.1f}%")
            elif label == "Elemental Mastery":
                result.append(f"{label}: {float(value):.0f}")
            else:
                result.append(f"{label}: {float(value):.0f}")
    return result


def _character_summary(character, index):
    avatar_id = character.get("avatarId", "Unknown")
    prop = character.get("propMap") or {}
    level = prop.get("4001", {}).get("val", "?")
    fetter = character.get("fetterInfo") or {}
    friendship = fetter.get("expLevel", "?")
    cons = character.get("talentIdList") or []
    constellation = len(cons)
    lines = [f"<b>{index}. Character ID {html.escape(str(avatar_id))}</b>"]
    lines.append(f"Level: {html.escape(str(level))} | Friendship: {html.escape(str(friendship))} | Constellation: C{constellation}")
    stats = _stat_lines(character)
    if stats:
        lines.append(" | ".join(stats[:5]))
    return "\n".join(lines)


def _character_detail(character, index):
    lines = [_character_summary(character, index)]
    equips = character.get("equipList") or []
    weapon = next((item for item in equips if item.get("weapon")), None)
    if weapon:
        w = weapon.get("weapon") or {}
        refinement = next(iter((w.get("affixMap") or {}).values()), "?")
        lines.append(f"Weapon ID: {html.escape(str(weapon.get('itemId', '?')))} | Level: {html.escape(str(w.get('level', '?')))} | Refinement: {html.escape(str(refinement))}")
    artifacts = [item for item in equips if item.get("reliquary")]
    if artifacts:
        lines.append(f"Artifacts equipped: {len(artifacts)}")
        for art in artifacts[:5]:
            rel = art.get("reliquary") or {}
            lines.append(f"• Artifact ID {html.escape(str(art.get('itemId', '?')))} — Level {html.escape(str(rel.get('level', '?')))}")
    return "\n".join(lines)


async def _send_profile(message, uid, mode="profile"):
    status = await message.reply_text("Fetching Genshin profile…")
    try:
        data = await asyncio.to_thread(_fetch_profile, uid)
        player = data.get("playerInfo") or {}
        chars = data.get("avatarInfoList") or []
        nickname = html.escape(str(player.get("nickname", "Traveler")))
        signature = html.escape(str(player.get("signature", "")))
        lines = [
            f"<b>Genshin Impact Profile</b>",
            f"Player: <b>{nickname}</b>",
            f"UID: <code>{uid}</code> ({_region(uid)})",
            f"Adventure Rank: {player.get('level', '?')} | World Level: {player.get('worldLevel', '?')}",
            f"Achievements: {player.get(' finishAchievementNum', player.get('finishAchievementNum', '?'))}",
        ]
        if signature:
            lines.append(f"Signature: {signature}")
        if mode == "profile":
            lines.append(f"Showcase characters: {len(chars)}")
            lines.append("\nUse /gicharacters to view the showcase or /gibuilds to view builds.")
        elif mode == "characters":
            if not chars:
                lines.append("No public showcase characters found.")
            else:
                lines.append("\n" + "\n\n".join(_character_summary(c, i) for i, c in enumerate(chars, 1)))
        else:
            if not chars:
                lines.append("No public showcase characters found.")
            else:
                lines.append("\n" + "\n\n".join(_character_detail(c, i) for i, c in enumerate(chars, 1)))
        text = "\n".join(lines)
        if len(text) > 4000:
            text = text[:3900] + "\n\n…Output shortened. Use the profile command to view a shorter summary."
        await status.edit_text(text, disable_web_page_preview=True)
    except ValueError as exc:
        await status.edit_text(html.escape(str(exc)))
    except requests.RequestException as exc:
        await status.edit_text("Could not reach Enka.Network right now. Please try again later.")
        print(f"Enka request failed for {uid}: {exc}")
    except Exception as exc:
        await status.edit_text("Unable to read this profile right now. Please try again later.")
        print(f"Genshin module error: {exc}")


def _feature_guard(func):
    async def wrapped(client, message):
        if not _is_enabled():
            await message.reply_text("The Genshin Impact feature is currently disabled by an administrator.")
            return
        await func(client, message)
    return wrapped


@Bot.on_message(filters.private & filters.command("genshin"))
@_feature_guard
async def genshin_help(client, message: Message):
    await message.reply_text(
        "<b>Genshin Impact Module</b>\n\n"
        "/gi UID — look up a player profile\n"
        "/gi — view your saved profile\n"
        "/gisave UID — save your Genshin UID\n"
        "/gicharacters — view showcase characters\n"
        "/gibuilds — view weapons, artifacts and character stats\n\n"
        "Only characters displayed in your in-game Character Showcase can be retrieved."
    )


@Bot.on_message(filters.private & filters.command("gi"))
@_feature_guard
async def genshin_profile(client, message: Message):
    uid = message.command[1] if len(message.command) > 1 else _get_uid(message.from_user.id)
    if not uid:
        await message.reply_text("You haven't saved a UID yet. Use /gisave YOUR_UID or /gi YOUR_UID.")
        return
    if not _valid_uid(uid):
        await message.reply_text("Please provide a valid 9- or 10-digit Genshin UID.")
        return
    await _send_profile(message, uid, "profile")


@Bot.on_message(filters.private & filters.command("gisave"))
@_feature_guard
async def genshin_save(client, message: Message):
    if len(message.command) < 2 or not _valid_uid(message.command[1]):
        await message.reply_text("Usage: /gisave YOUR_9_OR_10_DIGIT_UID")
        return
    uid = message.command[1]
    try:
        await asyncio.to_thread(_save_uid, message.from_user.id, uid)
        await message.reply_text(f"Your Genshin UID <code>{uid}</code> ({_region(uid)}) has been saved.")
    except Exception as exc:
        print(f"Could not save Genshin UID: {exc}")
        await message.reply_text("Couldn't save your UID. Check the MongoDB connection and try again.")


@Bot.on_message(filters.private & filters.command("gicharacters"))
@_feature_guard
async def genshin_characters(client, message: Message):
    uid = message.command[1] if len(message.command) > 1 else _get_uid(message.from_user.id)
    if not uid:
        await message.reply_text("Save your UID first with /gisave YOUR_UID, or use /gicharacters YOUR_UID.")
        return
    if not _valid_uid(uid):
        await message.reply_text("Please provide a valid 9- or 10-digit Genshin UID.")
        return
    await _send_profile(message, uid, "characters")


@Bot.on_message(filters.private & filters.command("gibuilds"))
@_feature_guard
async def genshin_builds(client, message: Message):
    uid = message.command[1] if len(message.command) > 1 else _get_uid(message.from_user.id)
    if not uid:
        await message.reply_text("Save your UID first with /gisave YOUR_UID, or use /gibuilds YOUR_UID.")
        return
    if not _valid_uid(uid):
        await message.reply_text("Please provide a valid 9- or 10-digit Genshin UID.")
        return
    await _send_profile(message, uid, "builds")


@Bot.on_message(filters.private & filters.command("genshinfeature"))
async def genshin_toggle(client, message: Message):
    if message.from_user.id not in ADMINS and message.from_user.id != OWNER_ID:
        await message.reply_text("This command is available to admins only.")
        return
    if len(message.command) < 2 or message.command[1].lower() not in ("on", "off", "status"):
        await message.reply_text("Usage: /genshinfeature on | off | status")
        return
    action = message.command[1].lower()
    try:
        if action == "status":
            enabled = await asyncio.to_thread(_is_enabled)
            await message.reply_text(f"Genshin feature is currently <b>{'ENABLED' if enabled else 'DISABLED'}</b>.")
        else:
            await asyncio.to_thread(_set_enabled, action == "on")
            await message.reply_text(f"Genshin feature has been <b>{'ENABLED' if action == 'on' else 'DISABLED'}</b> for all users.")
    except Exception as exc:
        print(f"Genshin toggle failed: {exc}")
        await message.reply_text("Could not update the setting. Check MongoDB connectivity.")
