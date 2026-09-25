#(©)Book-Sharing-Bot

import os
import logging
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
import pyrogram.utils
pyrogram.utils.MIN_CHANNEL_ID = -1009999999999

load_dotenv()

#Bot token @Botfather
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", os.environ["BOT_TOKEN"])

#Your API ID from my.telegram.org
APP_ID = int(os.environ.get("APP_ID", os.environ["APP_ID"]))

#Your API Hash from my.telegram.org
API_HASH = os.environ.get("API_HASH", os.environ["API_HASH"])

#Your db channel Id
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", os.environ["CHANNEL_ID"]))

#OWNER ID
OWNER_ID = int(os.environ.get("OWNER_ID", os.environ["OWNER_ID"]))

#Port
PORT = os.environ.get("PORT", "8080")

#force sub channel id, if you want enable force sub
FORCE_SUB_CHANNEL = int(os.environ.get("FORCE_SUB_CHANNEL", "0"))
JOIN_REQUEST_ENABLE = os.environ.get("JOIN_REQUEST_ENABLED", None)

TG_BOT_WORKERS = int(os.environ.get("TG_BOT_WORKERS", "4"))

#start message
START_PIC = os.environ.get("START_PIC","")
START_MSG = os.environ.get("START_MESSAGE", "Hello {first}. I am Annie's Bookshelf which will help you get the books which are agreed to read by people in Annie's Bookshelf.")

ADMINS = []
try:
    for x in (os.environ.get("ADMINS", "").split()):
        ADMINS.append(int(x))
except ValueError:
    raise Exception("Your Admins list does not contain valid integers.")

from database.admins import load_admins
for admin_id in load_admins():
    if admin_id not in ADMINS:
        ADMINS.append(admin_id)

#Force sub message 
FORCE_MSG = os.environ.get("FORCE_SUB_MESSAGE", "Hello {first}\n\n<b>You need to join in my Channel/Group to use me\n\nKindly Please join Channel</b>")

#set your Custom Caption here, Keep None for Disable Custom Caption
CUSTOM_CAPTION = os.environ.get("CUSTOM_CAPTION", None)

#set True if you want to prevent users from forwarding files from bot
PROTECT_CONTENT = True if os.environ.get('PROTECT_CONTENT', "False") == "True" else False

# Auto delete time in seconds.
AUTO_DELETE_TIME = int(os.getenv("AUTO_DELETE_TIME", "0"))
AUTO_DELETE_MSG = os.environ.get("AUTO_DELETE_MSG", "This file will be automatically deleted in {time} seconds. Please ensure you have saved any necessary content before this time.")
AUTO_DEL_SUCCESS_MSG = os.environ.get("AUTO_DEL_SUCCESS_MSG", "Your file has been successfully deleted. Thank you for using our service. ✅")

#Set true if you want Disable your Channel Posts Share button
DISABLE_CHANNEL_BUTTON = os.environ.get("DISABLE_CHANNEL_BUTTON", None) == 'True'

BOT_STATS_TEXT = "<b>BOT UPTIME</b>\n{uptime}"
USER_REPLY_TEXT = "❌Don't send me messages directly I'm only Annie's Bookshelf!"

ADMINS.append(OWNER_ID)

LOG_FILE_NAME = "anniesbookshelf.txt"

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt='%d-%b-%y %H:%M:%S',
    handlers=[
        RotatingFileHandler(
            LOG_FILE_NAME,
            maxBytes=50000000,
            backupCount=10
        ),
        logging.StreamHandler()
    ]
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)

def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
