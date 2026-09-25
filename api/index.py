from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

app = FastAPI()

bot = None
initialized = False

async def get_bot():
    global bot, initialized
    if not initialized:
        from bot import Bot
        bot = Bot()
        await bot.start()
        initialized = True
    return bot

@app.on_event("startup")
async def startup():
    try:
        await get_bot()
    except Exception as e:
        print(f"Bot startup error: {e}")

@app.get("/")
async def root():
    return JSONResponse({"status": "Annie's Bookshelf is running"})

@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()
        bot_instance = await get_bot()
        update = bot_instance.dispatcher.update
        from pyrogram import utils as pyrogram_utils
        pyrogram_utils.MIN_CHANNEL_ID = -1009999999999
        from pyrogram.types import Update
        parsed_update = Update(**data)
        await bot_instance.dispatcher.handle_update(parsed_update)
        return JSONResponse({"status": "ok"})
    except Exception as e:
        print(f"Webhook error: {e}")
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/setwebhook")
async def set_webhook():
    try:
        import httpx
        webhook_url = os.environ.get("WEBHOOK_URL", "")
        if not webhook_url:
            return JSONResponse({"status": "error", "message": "WEBHOOK_URL not set"})
        tg_token = os.environ.get("TG_BOT_TOKEN", "")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.telegram.org/bot{tg_token}/setWebhook",
                params={"url": f"{webhook_url}/webhook"}
            )
            return JSONResponse(response.json())
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/deletewebhook")
async def delete_webhook():
    try:
        import httpx
        tg_token = os.environ.get("TG_BOT_TOKEN", "")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.telegram.org/bot{tg_token}/deleteWebhook"
            )
            return JSONResponse(response.json())
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

@app.get("/getwebhook")
async def get_webhook():
    try:
        import httpx
        tg_token = os.environ.get("TG_BOT_TOKEN", "")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.telegram.org/bot{tg_token}/getWebhookInfo"
            )
            return JSONResponse(response.json())
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
