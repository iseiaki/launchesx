import requests
import time
import signal
import sys
from dotenv import load_dotenv
import os
from datetime import datetime, timezone

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

def check_liquidity_locked(token_address):
    """Check if liquidity is locked using DexScreener API"""
    try:
        dex_url = f"https://api.dexscreener.com/latest/dex/tokens/solana/{token_address}"
        response = requests.get(dex_url, timeout=10)
        data = response.json()
        
        if 'pairs' in data and len(data['pairs']) > 0:
            pair = data['pairs'][0]
            # Check if liquidity is locked (common indicators)
            if pair.get('info', {}).get('lock') or pair.get('liquidity', {}).get('locked'):
                return True
            # Check if liquidity is burned (dead address)
            if pair.get('info', {}).get('burned') or 'burn' in pair.get('info', {}).get('description', '').lower():
                return True
        return False
    except Exception as e:
        print(f"Error checking liquidity: {e}")
        return False

def calculate_safety_score(token):
    """
    Calculate a safety score (1-10) for a token based on available parameters
    """
    score = 5  # Neutral starting point
    
    # 1. Developer Fee (50% in example is very bad)
    try:
        dev_fee = float(token.get("developer_fee_percentage", 0))
        if dev_fee > 30:
            score -= 3  # Very high fee
        elif dev_fee > 20:
            score -= 1  # High fee
        elif dev_fee < 10:
            score += 1  # Low fee bonus
    except:
        pass
    
    # 2. Social Media Verification
    social_score = 0
    socials_to_check = [
        ("website_url", "http"),
        ("telegram_url", "https://t.me"),
        ("x_account_url", "https://x.com"),
    ]
    
    for field, prefix in socials_to_check:
        if token.get(field) and str(token[field]).startswith(prefix):
            social_score += 1
    
    # Adjust score based on social presence
    if social_score == len(socials_to_check):
        score += 2  # All socials present
    elif social_score >= len(socials_to_check) * 0.66:
        score += 1  # Most socials present
    elif social_score < len(socials_to_check) * 0.33:
        score -= 1  # Missing most socials
    
    # 3. Token Age (new tokens are riskier)
    try:
        created_at = datetime.fromisoformat(token["created_at"])
        age_hours = (datetime.now(timezone.utc) - created_at).total_seconds() / 3600
        if age_hours < 2:
            score -= 1  # Very new token
        elif age_hours > 24:
            score += 1  # Survived at least 1 day
    except:
        pass
    
    # 4. Liquidity Check (via DexScreener)
    try:
        if check_liquidity_locked(token["token_mint_address"]):
            score += 2  # Bonus for locked liquidity
    except:
        pass
    
    # 5. Same wallet check (dev and distribution same wallet is risky)
    if token.get("dev_wallet_address") and token.get("distribution_wallet_address"):
        if token["dev_wallet_address"] == token["distribution_wallet_address"]:
            score -= 1
    
    # 6. Website quality check
    if token.get("website_url"):
        website = token["website_url"].lower()
        if 'http://' in website and not 'https://':
            score -= 1  # No SSL is bad
        if any(bad_word in website for bad_word in ['example.com', 'temp.com', 'placeholder']):
            score -= 2  # Placeholder website
    
    # Ensure score stays within bounds
    return max(1, min(10, score))

def send_token_info(token):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    distribute_url = f"https://distributesol.io/token/{token['token_mint_address']}"
    dexscreener_url = f"https://dexscreener.com/solana/{token['token_mint_address']}"
    jupiter_url = f"https://jup.ag/swap/SOL-{token['token_mint_address']}"
    solscan_contract = f"https://solscan.io/token/{token['token_mint_address']}"
    solscan_dev_wallet = f"https://solscan.io/address/{token['dev_wallet_address']}"

    # Calculate safety score
    safety_score = calculate_safety_score(token)
    
    # Get safety emoji and description
    if safety_score >= 8:
        safety_emoji = "🟢"
        safety_comment = "High Safety"
    elif safety_score >= 5:
        safety_emoji = "🟡"
        safety_comment = "Medium Risk"
    else:
        safety_emoji = "🔴"
        safety_comment = "High Risk"

    # Add safety details to caption
    caption = f"""
🚀 New Token Launched On Distribute!

🌟 Token Name: {token["token_name"]}
💲 Ticker: {token["token_ticker"]}

{safety_emoji} *Safety Score: {safety_score}/10* - {safety_comment}
🔍 *Risk Analysis:*
- Dev Fee: {token["developer_fee_percentage"]}% {'⚠️ (High)' if float(token["developer_fee_percentage"]) > 20 else ''}
- {'🔒 Locked Liquidity' if check_liquidity_locked(token["token_mint_address"]) else '⚠️ Liquidity Not Verified'}
- Age: {(datetime.now(timezone.utc) - datetime.fromisoformat(token["created_at"])).total_seconds()/3600:.1f} hours

🔗 [Contract Address]({solscan_contract})
🌐 [Website]({token["website_url"]})
🐦 [Twitter]({token["x_account_url"]})
💬 [Telegram]({token["telegram_url"]})

🛠 [Dev Wallet]({solscan_dev_wallet})
📅 Distribution: Every {token["distribution_interval"]} mins

📢 *Always DYOR before investing!*
"""

    buttons = {
        "inline_keyboard": [
            [
                {"text": "Check on Distribute", "url": distribute_url},
                {"text": "DexScreener", "url": dexscreener_url},
                {"text": "Jupiter", "url": jupiter_url}
            ],
            [
                {"text": "🔍 Verify Liquidity", "url": dexscreener_url},
                {"text": "📊 Check Contract", "url": solscan_contract}
            ]
        ]
    }

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
    send_telegram_message("100x Kebab fetcher shutting down gracefully...")
    sys.exit(0)

if __name__ == "__main__":
    send_telegram_message("100x Kebab fetcher started successfully!")
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)
    monitor_new_tokens()