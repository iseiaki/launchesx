import requests
import time
import signal
import sys
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Constants
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
AUTHORIZATION = os.getenv("AUTHORIZATION")

HEADERS = {
    "accept": "*/*",
    "apikey": API_KEY,
    "authorization": AUTHORIZATION,
}

# In-memory storage for fetched tokens
fetched_tokens = {}

def send_telegram_message(text, photo=None):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }

    if photo:
        payload["photo"] = photo
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Message sent successfully!")
    except Exception as e:
        print(f"Error sending message: {e}")

def fetch_data():
    try:
        response = requests.get(API_URL, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error fetching data: {e}")
        return []

def send_token_info(token):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    distribute_url = f"https://distributesol.io/bonding-token/{token['token_mint_address']}"
    raydium = f"https://raydium.io/launchpad/token/?mint={token['token_mint_address']}"
    solscan_contract = f"https://solscan.io/token/{token['token_mint_address']}"

    buttons = {
        "inline_keyboard": [
            [
                {"text": "Check on Distribute", "url": distribute_url},
                {"text": "Raydium", "url": raydium}
            ]
        ]
    }

    caption = f"""
💵 New token launched on Distribute using bonding curve (SSLS) system. 💵

🌟 Token Name: {token["token_name"]}
💲 Symbol: {token["token_symbol"]}

🔗 Contract Address: `{token['token_mint_address']}`

📊 [View on Solscan]({solscan_contract})
🌐 [Website]({token["website_url"]})
🐦 [Twitter]({token["x_account_url"]})
💬 [Telegram]({token["telegram_url"]})

💎 First Buy Amount: {"No first buy set" if token["first_buy_amount"] is None else f"{token['first_buy_amount']} SOL"}

📢 DYOR & Get in on the launch early!
"""

    payload = {
        "chat_id": CHAT_ID,
        "photo": token["logo_url"],
        "caption": caption,
        "parse_mode": "Markdown",
        "reply_markup": buttons
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Message sent successfully!")
    except Exception as e:
        print(f"Error sending message: {e}")

def monitor_new_tokens():
    global fetched_tokens

    print("Fetching initial data...")
    initial_tokens = fetch_data()
    if initial_tokens:
        for token in initial_tokens:
            token_id = token["token_mint_address"]
            fetched_tokens[token_id] = token
        print(f"Initial data loaded. {len(fetched_tokens)} tokens in memory.")

    while True:
        print("Fetching new tokens...")
        tokens = fetch_data()

        if tokens:
            for token in tokens:
                token_id = token["token_mint_address"]
                if token_id not in fetched_tokens:
                    print(f"New token detected: {token['token_name']}")
                    fetched_tokens[token_id] = token
                    send_token_info(token)

        time.sleep(2)

def graceful_shutdown(signum, frame):
    print("Shutting down gracefully...")
    send_telegram_message("bot has shut down")
    sys.exit(0)

if __name__ == "__main__":
    send_telegram_message("bot has started ")
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    monitor_new_tokens()
