#(©)Book-Sharing-Bot

import os
import asyncio
from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait, UserIsBlocked, InputUserDeactivated

from bot import Bot
from config import ADMINS, OWNER_ID, FORCE_MSG, START_MSG, CUSTOM_CAPTION, DISABLE_CHANNEL_BUTTON, PROTECT_CONTENT, START_PIC, AUTO_DELETE_TIME, AUTO_DELETE_MSG, JOIN_REQUEST_ENABLE,FORCE_SUB_CHANNEL
from helper_func import subscribed,decode, get_messages, delete_file, encode
from database.database import add_user, del_user, full_userbase, present_user
from database.admins import add_admin, remove_admin, get_all_admins


@Bot.on_message(filters.command('start') & filters.private & subscribed)
async def start_command(client: Client, message: Message):
    id = message.from_user.id
    if not await present_user(id):
        try:
            await add_user(id)
        except:
            pass
    text = message.text
    if len(text)>7:
        try:
            base64_string = text.split(" ", 1)[1]
        except:
            return
        string = await decode(base64_string)
        argument = string.split("-")
        if len(argument) == 3:
            try:
                start = int(int(argument[1]) / abs(client.db_channel.id))
                end = int(int(argument[2]) / abs(client.db_channel.id))
            except:
                return
            if start <= end:
                ids = range(start,end+1)
            else:
                ids = []
                i = start
                while True:
                    ids.append(i)
                    i -= 1
                    if i < end:
                        break
        elif len(argument) == 2:
            try:
                ids = [int(int(argument[1]) / abs(client.db_channel.id))]
            except:
                return
        temp_msg = await message.reply("Please wait...")
        try:
            messages = await get_messages(client, ids)
        except:
            await message.reply_text("Something went wrong..!")
            return
        await temp_msg.delete()

        track_msgs = []

        for msg in messages:

            if bool(CUSTOM_CAPTION) & bool(msg.document):
                caption = CUSTOM_CAPTION.format(previouscaption = "" if not msg.caption else msg.caption.html, filename = msg.document.file_name)
            else:
                caption = "" if not msg.caption else msg.caption.html

            if DISABLE_CHANNEL_BUTTON:
                reply_markup = msg.reply_markup
            else:
                reply_markup = None

            if AUTO_DELETE_TIME and AUTO_DELETE_TIME > 0:

                try:
                    copied_msg_for_deletion = await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                    if copied_msg_for_deletion:
                        track_msgs.append(copied_msg_for_deletion)
                    else:
                        print("Failed to copy message, skipping.")

                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    copied_msg_for_deletion = await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                    if copied_msg_for_deletion:
                        track_msgs.append(copied_msg_for_deletion)
                    else:
                        print("Failed to copy message after retry, skipping.")

                except Exception as e:
                    print(f"Error copying message: {e}")
                    pass

            else:
                try:
                    await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                    await asyncio.sleep(0.5)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
                    await msg.copy(chat_id=message.from_user.id, caption=caption, parse_mode=ParseMode.HTML, reply_markup=reply_markup, protect_content=PROTECT_CONTENT)
                except:
                    pass

        if track_msgs:
            delete_data = await client.send_message(
                chat_id=message.from_user.id,
                text=AUTO_DELETE_MSG.format(time=AUTO_DELETE_TIME)
            )
            # Schedule the file deletion task after all messages have been copied
            asyncio.create_task(delete_file(track_msgs, client, delete_data))
        else:
            print("No messages to track for deletion.")

        return
    else:
        reply_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("😊 About Me", callback_data = "about"),
                    InlineKeyboardButton("🔒 Close", callback_data = "close")
                ]
            ]
        )
        if START_PIC:  # Check if START_PIC has a value
            await message.reply_photo(
                photo=START_PIC,
                caption=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                quote=True
            )
        else:  # If START_PIC is empty, send only the text
            await message.reply_text(
                text=START_MSG.format(
                    first=message.from_user.first_name,
                    last=message.from_user.last_name,
                    username=None if not message.from_user.username else '@' + message.from_user.username,
                    mention=message.from_user.mention,
                    id=message.from_user.id
                ),
                reply_markup=reply_markup,
                disable_web_page_preview=True,
                quote=True
            )
        return

    
#=====================================================================================##

@Bot.on_message(filters.command('help') & filters.private & subscribed)
async def help_command(client: Client, message: Message):
    help_text = """<b>Annie's Bookshelf - Help</b>

<b>What is this bot?</b>
This bot helps you access books that are agreed to read by people in Annie's Bookshelf.

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
Contact the bot owner for support.</b>"""

    await message.reply_text(
        text=help_text,
        disable_web_page_preview=True,
        quote=True
    )

@Bot.on_message(filters.command('ping') & filters.private)
async def ping_command(client: Client, message: Message):
    import time
    start_time = time.time()
    msg = await message.reply("Pinging...")
    end_time = time.time()
    ping_ms = round((end_time - start_time) * 1000, 2)
    await msg.edit(f"Pong!\nResponse time: <code>{ping_ms}ms</code>")

#=====================================================================================##

def format_size(size_bytes):
    if size_bytes is None:
        return "Unknown size"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.2f} TB"

FILES_PER_PAGE = 10

async def fetch_files_batch(client, start_id, count, status_msg=None):
    files = []
    batch_size = 200
    max_scan = 50000
    scanned = 0
    while len(files) < count and scanned < max_scan:
        ids = list(range(start_id + scanned, start_id + scanned + batch_size))
        try:
            msgs = await client.get_messages(chat_id=client.db_channel.id, message_ids=ids)
        except FloodWait as e:
            await asyncio.sleep(e.value)
            msgs = await client.get_messages(chat_id=client.db_channel.id, message_ids=ids)
        for m in msgs:
            if m is not None and (m.document or m.video or m.audio or m.photo):
                files.append(m)
                if len(files) >= count:
                    break
        scanned += batch_size
        if status_msg and scanned % 2000 == 0:
            try:
                percentage = round((scanned / max_scan) * 100)
                await status_msg.edit(f"Waiting... {percentage}%")
            except:
                pass
    return files

@Bot.on_message(filters.command('files') & filters.private & subscribed)
async def list_files(client: Client, message: Message):
    msg = await message.reply("Waiting... 0%")
    file_messages = await fetch_files_batch(client, start_id=1, count=200, status_msg=msg)

    if not file_messages:
        await msg.edit("No files found in the channel.")
        return

    total_files = len(file_messages)
    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE
    current_page = 1

    await msg.delete()
    await send_files_page(client, message, file_messages, current_page, total_pages)

async def send_files_page(client, message, file_messages, current_page, total_pages):
    start = (current_page - 1) * FILES_PER_PAGE
    end = start + FILES_PER_PAGE
    page_files = file_messages[start:end]

    text = f"<b>Available Files (Page {current_page}/{total_pages})</b>\n\n"
    buttons = []

    for i, msg_item in enumerate(page_files, start=start + 1):
        file_name = "Unknown"
        file_size = "Unknown size"

        if msg_item.document:
            file_name = msg_item.document.file_name or "Unnamed file"
            file_size = format_size(msg_item.document.file_size)
        elif msg_item.video:
            file_name = msg_item.video.file_name or "Video"
            file_size = format_size(msg_item.video.file_size)
        elif msg_item.audio:
            file_name = msg_item.audio.file_name or "Audio"
            file_size = format_size(msg_item.audio.file_size)
        elif msg_item.photo:
            file_name = "Photo"
            file_size = format_size(msg_item.photo.file_size if msg_item.photo.file_size else None)

        converted_id = msg_item.id * abs(client.db_channel.id)
        base64_string = await encode(f"get-{converted_id}")
        link = f"https://t.me/{client.username}?start={base64_string}"

        text += f"<b>{i}.</b> <code>{file_name}</code> ({file_size})\n"
        buttons.append([InlineKeyboardButton(f"{i}. {file_name}", url=link)])

    nav_buttons = []
    if current_page > 1:
        nav_buttons.append(InlineKeyboardButton("Previous", callback_data=f"files_page_{current_page - 1}"))
    if current_page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Next", callback_data=f"files_page_{current_page + 1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton("Close", callback_data="close")])

    await client.send_message(
        chat_id=message.chat.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(buttons),
        disable_web_page_preview=True
    )

WAIT_MSG = """"<b>Processing ...</b>"""

REPLY_ERROR = """<code>Use this command as a replay to any telegram message with out any spaces.</code>"""

#=====================================================================================##


@Bot.on_message(filters.command('start') & filters.private)
async def not_joined(client: Client, message: Message):

    if bool(JOIN_REQUEST_ENABLE):
        invite = await client.create_chat_invite_link(
            chat_id=FORCE_SUB_CHANNEL,
            creates_join_request=True
        )
        ButtonUrl = invite.invite_link
    else:
        ButtonUrl = client.invitelink

    buttons = [
        [
            InlineKeyboardButton(
                "Join Channel",
                url = ButtonUrl)
        ]
    ]

    try:
        buttons.append(
            [
                InlineKeyboardButton(
                    text = 'Try Again',
                    url = f"https://t.me/{client.username}?start={message.command[1]}"
                )
            ]
        )
    except IndexError:
        pass

    await message.reply(
        text = FORCE_MSG.format(
                first = message.from_user.first_name,
                last = message.from_user.last_name,
                username = None if not message.from_user.username else '@' + message.from_user.username,
                mention = message.from_user.mention,
                id = message.from_user.id
            ),
        reply_markup = InlineKeyboardMarkup(buttons),
        quote = True,
        disable_web_page_preview = True
    )

@Bot.on_message(filters.command('users') & filters.private & filters.user(ADMINS))
async def get_users(client: Bot, message: Message):
    msg = await client.send_message(chat_id=message.chat.id, text=WAIT_MSG)
    users = await full_userbase()
    await msg.edit(f"{len(users)} users are using this bot")

@Bot.on_message(filters.private & filters.command('broadcast') & filters.user(ADMINS))
async def send_text(client: Bot, message: Message):
    if message.reply_to_message:
        query = await full_userbase()
        broadcast_msg = message.reply_to_message
        total = 0
        successful = 0
        blocked = 0
        deleted = 0
        unsuccessful = 0
        
        pls_wait = await message.reply("<i>Broadcasting Message.. This will Take Some Time</i>")
        for chat_id in query:
            try:
                await broadcast_msg.copy(chat_id)
                successful += 1
            except FloodWait as e:
                await asyncio.sleep(e.x)
                await broadcast_msg.copy(chat_id)
                successful += 1
            except UserIsBlocked:
                await del_user(chat_id)
                blocked += 1
            except InputUserDeactivated:
                await del_user(chat_id)
                deleted += 1
            except:
                unsuccessful += 1
                pass
            total += 1
        
        status = f"""<b><u>Broadcast Completed</u>

Total Users: <code>{total}</code>
Successful: <code>{successful}</code>
Blocked Users: <code>{blocked}</code>
Deleted Accounts: <code>{deleted}</code>
Unsuccessful: <code>{unsuccessful}</code></b>"""
        
        return await pls_wait.edit(status)

    else:
        msg = await message.reply(REPLY_ERROR)
        await asyncio.sleep(8)
        await msg.delete()

#=====================================================================================##

@Bot.on_message(filters.command('addadmin') & filters.private & filters.user(ADMINS))
async def add_new_admin(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /addadmin <user_id>\n\nGet user ID from @userinfobot")
        return
    try:
        user_id = int(message.command[1])
    except ValueError:
        await message.reply("Invalid user ID. Please provide a numeric ID.")
        return
    if user_id == OWNER_ID:
        await message.reply("You are already the owner.")
        return
    if user_id in ADMINS:
        await message.reply("This user is already an admin.")
        return
    add_admin(user_id)
    ADMINS.append(user_id)
    await message.reply(f"User <code>{user_id}</code> has been added as admin.")

@Bot.on_message(filters.command('removeadmin') & filters.private & filters.user(ADMINS))
async def remove_existing_admin(client: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("Usage: /removeadmin <user_id>")
        return
    try:
        user_id = int(message.command[1])
    except ValueError:
        await message.reply("Invalid user ID. Please provide a numeric ID.")
        return
    if user_id == OWNER_ID:
        await message.reply("You cannot remove the owner.")
        return
    if user_id not in ADMINS:
        await message.reply("This user is not an admin.")
        return
    remove_admin(user_id)
    if user_id in ADMINS:
        ADMINS.remove(user_id)
    await message.reply(f"User <code>{user_id}</code> has been removed from admins.")

@Bot.on_message(filters.command('listadmins') & filters.private & filters.user(ADMINS))
async def list_all_admins(client: Client, message: Message):
    admins = get_all_admins()
    if not admins:
        await message.reply("No admins found in the database.")
        return
    admin_list = "\n".join([f"<code>{admin_id}</code>" for admin_id in admins])
    await message.reply(f"<b>Admin List:</b>\n\n{admin_list}")

