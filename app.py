import os
import requests

from flask import Flask, request

app = Flask(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]


@app.route("/")
def home():
    return "Book Sharing Bot is running!"


@app.route("/webhook", methods=["POST"])
def webhook():

    update = request.get_json()

    if "message" not in update:
        return "OK", 200

    message = update["message"]

    chat_id = message["chat"]["id"]
    text = message.get("text", "")

    if text == "/start":

        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": "Welcome to the Book Sharing Bot!"
            }
        )

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)