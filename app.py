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

    print("Received update:")
    print(update)

    # We will process the Telegram update here

    return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)