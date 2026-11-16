#(©)Book-Sharing-Bot

import asyncio
from pyrogram import __version__
from bot import Bot
from config import OWNER_ID
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from helper_func import encode
from plugins.start import fetch_files_batch, format_size, FILES_PER_PAGE

@Bot.on_callback_query()
async def cb_handler(client: Bot, query: CallbackQuery):
    data = query.data
    if data == "about":
        await query.message.edit_text(
            text = f"<b>Annie's Bookshelf\n\nA bot to share and access books from Annie's Bookshelf.\n\nLanguage : <code>Python3</code>\nLibrary : <a href='https://docs.pyrogram.org/'>Pyrogram asyncio {__version__}</a></b>",
            disable_web_page_preview = True,
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Close", callback_data = "close")
                    ]
                ]
            )
        )
    elif data == "close":
        await query.message.delete()
        try:
            await query.message.reply_to_message.delete()
        except:
            pass
    elif data.startswith("files_page_"):
        page = int(data.split("_")[2])
        await query.answer()

        file_messages = await fetch_files_batch(client, start_id=1, count=200)
        total_files = len(file_messages)
        total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE

        start = (page - 1) * FILES_PER_PAGE
        end = start + FILES_PER_PAGE
        page_files = file_messages[start:end]

        text = f"<b>Available Files (Page {page}/{total_pages})</b>\n\n"
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
        if page > 1:
            nav_buttons.append(InlineKeyboardButton("Previous", callback_data=f"files_page_{page - 1}"))
        if page < total_pages:
            nav_buttons.append(InlineKeyboardButton("Next", callback_data=f"files_page_{page + 1}"))
        if nav_buttons:
            buttons.append(nav_buttons)

        buttons.append([InlineKeyboardButton("Close", callback_data="close")])

        await query.message.edit_text(
            text=text,
            reply_markup=InlineKeyboardMarkup(buttons),
            disable_web_page_preview=True
        )
