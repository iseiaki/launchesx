import requests
import time
import signal
import sys
from dotenv import load_dotenv
import os
from datetime import datetime, timezone
import re

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

def get_dex_data(token_address):
    """Get comprehensive DexScreener data including liquidity and market cap"""
    try:
        dex_url = f"https://api.dexscreener.com/latest/dex/tokens/solana/{token_address}"
        response = requests.get(dex_url, timeout=10)
        data = response.json()
        
        if 'pairs' in data and len(data['pairs']) > 0:
            pair = data['pairs'][0]
            return {
                'liquidity': pair.get('liquidity', {}).get('usd'),
                'market_cap': pair.get('fdv', 0),
                'price': pair.get('priceUsd', 0),
                'volume': pair.get('volume', {}).get('h24', 0),
                'locked': pair.get('info', {}).get('lock') or pair.get('liquidity', {}).get('locked'),
                'burned': pair.get('info', {}).get('burned') or 'burn' in pair.get('info', {}).get('description', '').lower()
            }
        return None
    except Exception as e:
        print(f"Error getting Dex data: {e}")
        return None

def is_honeypot(token_address):
    """Check if token might be a honeypot using Honeypot.is API"""
    try:
        honeypot_url = f"https://api.honeypot.is/v2/IsHoneypot?address={token_address}"
        response = requests.get(honeypot_url, timeout=10)
        data = response.json()
        return data.get('honeypotResult', {}).get('isHoneypot', False)
    except Exception as e:
        print(f"Error checking honeypot: {e}")
        return False

def format_currency(value):
    """Format currency values in a human-readable way"""
    if not value:
        return "N/A"
    
    value = float(value)
    if value >= 1_000_000:
        return f"${value/1_000_000:.2f}M"
    elif value >= 1_000:
        return f"${value/1_000:.2f}K"
    return f"${value:.2f}"

def calculate_safety_score(token, dex_data):
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
        ("telegram_url", "t.me"),
        ("x_account_url", "x.com"),
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
    
    # 3. Liquidity Check (via DexScreener)
    try:
        if dex_data:
            if dex_data.get('locked') or dex_data.get('burned'):
                score += 2  # Bonus for locked liquidity
            # Penalize low liquidity
            liquidity = float(dex_data.get('liquidity', 0))
            if liquidity < 1000:
                score -= 2
            elif liquidity < 5000:
                score -= 1
            elif liquidity > 25000:
                score += 1
    except:
        pass
    
    # 4. Same wallet check (dev and distribution same wallet is risky)
    if token.get("dev_wallet_address") and token.get("distribution_wallet_address"):
        if token["dev_wallet_address"] == token["distribution_wallet_address"]:
            score -= 1
    
    # 5. Website quality check
    if token.get("website_url"):
        website = token["website_url"].lower()
        if 'http://' in website and not 'https://':
            score -= 1  # No SSL is bad
        if any(bad_word in website for bad_word in ['example.com', 'temp.com', 'placeholder']):
            score -= 2  # Placeholder website
    
    # 6. Honeypot check
    try:
        if is_honeypot(token["token_mint_address"]):
            score -= 3  # Big penalty for potential honeypot
    except:
        pass
    
    # Ensure score stays within bounds
    return max(1, min(10, score))

def format_contract_address(address):
    """Format contract address for easy copying"""
    return f"`{address}`"

def send_token_info(token):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto"
    
    distribute_url = f"https://distributesol.io/token/{token['token_mint_address']}"
    dexscreener_url = f"https://dexscreener.com/solana/{token['token_mint_address']}"
    jupiter_url = f"https://jup.ag/swap/SOL-{token['token_mint_address']}"
    solscan_contract = f"https://solscan.io/token/{token['token_mint_address']}"
    solscan_dev_wallet = f"https://solscan.io/address/{token['dev_wallet_address']}"

    # Get DexScreener data
    dex_data = get_dex_data(token["token_mint_address"])
    
    # Calculate safety score with dex data
    safety_score = calculate_safety_score(token, dex_data)
    
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

    # Add honeypot warning if detected
    honeypot_warning = ""
    try:
        if is_honeypot(token["token_mint_address"]):
            honeypot_warning = "\n🚨 *HONEYPOT WARNING* - Potential scam token detected!"
    except:
        pass

    # Prepare Dex data for display
    liquidity = format_currency(dex_data.get('liquidity')) if dex_data else "N/A"
    market_cap = format_currency(dex_data.get('market_cap')) if dex_data else "N/A"
    price = f"${float(dex_data.get('price', 0)):.6f}" if dex_data else "N/A"
    volume = format_currency(dex_data.get('volume')) if dex_data else "N/A"

    # Add safety details to caption
    caption = f"""
🚀 New Token Launched On Distribute! 🚀

📌 *Basic Info:*
🌟 Token Name: {token["token_name"]}
💲 Ticker: {token["token_ticker"]}
💰 Price: {price}
📈 MCap: {market_cap}
💧 Liquidity: {liquidity}
📊 24h Volume: {volume}

{safety_emoji} Safety Score: {safety_score}/10 - {safety_comment}

🔍 Risk Analysis:
- Dev Fee: {token["developer_fee_percentage"]}% {'⚠️ (High)' if float(token["developer_fee_percentage"]) > 20 else ''}
- {'🔒 Locked Liquidity' if dex_data and (dex_data.get('locked') or dex_data.get('burned')) else '⚠️ Liquidity Not Verified'}
- Contract: {format_contract_address(token["token_mint_address"])}

🔗 Links:
[View on Solscan]({solscan_contract}) | [Website]({token["website_url"]})
[Twitter]({token["x_account_url"]}) | [Telegram]({token["telegram_url"]})

🛠 [Dev Wallet]({solscan_dev_wallet})
📅 Distribution: Every {token["distribution_interval"]} mins
{honeypot_warning}

📢 Always DYOR before investing!
"""

    buttons = {
        "inline_keyboard": [
            [
                {"text": "📝 Copy CA", "callback_data": f"copy_{token['token_mint_address']}"},
                {"text": "DexS", "url": dexscreener_url}
            ],
            [
                {"text": "Jupiter", "url": jupiter_url},
                {"text": "Distribute", "url": distribute_url}
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