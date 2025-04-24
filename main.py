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
    
    # Determine URL path based on token type
    url_path = "jackpot" if token.get('token_type') == "Jackpot" else "token"
    distribute_url = f"https://distributesol.io/{url_path}/{token['token_mint_address']}"
    
    dexscreener_url = f"https://dexscreener.com/solana/{token['token_mint_address']}"
    jupiter_url = f"https://jup.ag/swap/SOL-{token['token_mint_address']}"
    solscan_contract = f"https://solscan.io/token/{token['token_mint_address']}"
    solscan_dev_wallet = f"https://solscan.io/address/{token['dev_wallet_address']}"

    buttons = {
        "inline_keyboard": [
            [
                {"text": "Check on Distribute", "url": distribute_url},
                {"text": "DexS", "url": dexscreener_url},
                {"text": "Jupiter", "url": jupiter_url}

            ]
        ]
    }

    caption = f"""
🚀 New Token Launched On Distribute!

🌟 Token Name: {token["token_name"]}
💲 Ticker: {token["token_ticker"]}

🔗 Contract Address: `{token['token_mint_address']}`
📊 [View on Solscan]({solscan_contract})
🌐 [Website]({token["website_url"]})
💬 [Join Telegram]({token["telegram_url"]})

🛠 Developer Fee: {token["developer_fee_percentage"]}%
🔗 [Dev Wallet]({solscan_dev_wallet})
📅 Distribution Interval: {token["distribution_interval"]} minutes
🔒 Safu: {"yes" if token["is_safe"] else "no"}

📢 Get in on the launch early!
"""

    payload = {
        "chat_id": CHAT_ID,
        "photo": token["image_url"],
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

        time.sleep(8)

def graceful_shutdown(signum, frame):
    print("Shutting down gracefully...")
    send_telegram_message("Bot is shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    send_telegram_message("🤖 Bot started successfully!")
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    monitor_new_tokens()
