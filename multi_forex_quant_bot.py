import os
import sys
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone

# ----------------------------------------------------------------------
# 1. Credentials & Configuration
# ----------------------------------------------------------------------
OANDA_ACCOUNT_ID = os.environ.get("OANDA_ACCOUNT_ID", "101-001-XXXXXXX-001")
OANDA_ACCESS_TOKEN = os.environ.get("OANDA_ACCESS_TOKEN", "your_oanda_demo_token_here")
OANDA_ENVIRONMENT = "practice"  # 'practice' for Demo, 'live' for Real

NEWS_API_KEY = os.environ.get("FINNHUB_API_KEY", "your_finnhub_key_here")

OANDA_BASE_URL = "https://api-fxpractice.oanda.com/v20" if OANDA_ENVIRONMENT == "practice" else "https://api-fxtrade.oanda.com/v20"

HEADERS = {
    "Authorization": f"Bearer {OANDA_ACCESS_TOKEN}",
    "Content-Type": "application/json"
}

# The 6 Major Currency Pairs Basket
BASKET_PAIRS = ["EUR_USD", "GBP_USD", "USD_JPY", "AUD_USD", "USD_CAD", "USD_CHF"]

# Execution Parameters
BASE_LOT_PER_1000_EQUITY = 0.01  # 0.01 Lots (1,000 units) per $1,000 Account Equity
MAX_CONCURRENT_OPEN_TRADES = 3   # Maximum simultaneous trades allowed across basket
NEWS_BLACKOUT_MINUTES = 15      # Pause trading 15m before & after high-impact news

def get_pip_location(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001

# ----------------------------------------------------------------------
# 2. Multi-Central Bank Macro News Filter
# ----------------------------------------------------------------------
def is_news_blackout_active() -> tuple[bool, str]:
    try:
        now_utc = datetime.now(timezone.utc)
        start_date = (now_utc - timedelta(minutes=NEWS_BLACKOUT_MINUTES)).strftime("%Y-%m-%d")
        end_date = (now_utc + timedelta(minutes=NEWS_BLACKOUT_MINUTES)).strftime("%Y-%m-%d")

        url = f"https://finnhub.io/api/v1/economic-calendar?from={start_date}&to={end_date}&token={NEWS_API_KEY}"
        res = requests.get(url, timeout=5)
        
        if res.status_code == 200:
            events = res.json().get("economicCalendar", [])
            major_countries = ["US", "EU", "GB", "JP", "AU", "CA", "CH", "DE"]
            
            for event in events:
                impact = str(event.get("impact", "")).lower()
                country = str(event.get("country", "")).upper()
                
                if impact in ["high", "3"] and country in major_countries:
                    event_time_str = event.get("time", "")
                    if event_time_str:
                        event_dt = datetime.strptime(event_time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                        time_diff_minutes = abs((event_dt - now_utc).total_seconds()) / 60.0
                        
                        if time_diff_minutes <= NEWS_BLACKOUT_MINUTES:
                            return True, f"High-Impact Macro Event ({country}: {event.get('event', 'News')}) at {event_time_str} UTC"
                            
        return False, "Clear"
    except Exception as e:
        return False, f"News Feed Note: {str(e)}"

# ----------------------------------------------------------------------
# 3. Account Diagnostics & Proportional Sizing Engine
# ----------------------------------------------------------------------
def get_account_summary() -> dict:
    url = f"{OANDA_BASE_URL}/accounts/{OANDA_ACCOUNT_ID}/summary"
    res = requests.get(url, headers=HEADERS, timeout=10)
    res.raise_for_status()
    summary = res.json().get("account", {})
    return {
        "nav": float(summary.get("NAV", 0.0)),
        "balance": float(summary.get("balance", 0.0)),
        "unrealized_pnl": float(summary.get("unrealizedPL", 0.0)),
        "open_position_count": int(summary.get("openPositionCount", 0))
    }

def get_pair_quote(pair: str) -> float:
    url = f"{OANDA_BASE_URL}/instruments/{pair}/candles?count=1&price=M&granularity=M1"
    res = requests.get(url, headers=HEADERS, timeout=5)
    res.raise_for_status()
    candles = res.json().get("candles", [])
    if candles:
        return float(candles[0]["mid"]["c"])
    raise ValueError(f"Failed to fetch quote for {pair}")

def calculate_proportional_lot_units(nav: float) -> tuple[float, int]:
    scaling_factor = nav / 1000.0
    lots = round(scaling_factor * BASE_LOT_PER_1000_EQUITY, 2)
    units = int(lots * 100000)
    return max(0.01, lots), max(1000, units)

# ----------------------------------------------------------------------
# 4. Multi-Asset Execution Loop
# ----------------------------------------------------------------------
def run_multi_asset_quant_cycle():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n==================================================================")
    print(f"[{timestamp}] Multi-Asset Proportional Risk Automation Engine")
    print(f"==================================================================")

    is_news, news_msg = is_news_blackout_active()
    if is_news:
        print(f"🚨 MULTI-ASSET NEWS BLACKOUT TRIGGERED: {news_msg}")
        print("🛡️ Holding execution. News volatility protection active.")
        return

    summary = get_account_summary()
    nav = summary['nav']
    active_lots, active_units = calculate_proportional_lot_units(nav)
    
    print(f"• Account Equity (NAV): ${nav:,.2f} | Balance: ${summary['balance']:,.2f}")
    print(f"• Dynamic Sizing Rule: {active_lots:.2f} Lots ({active_units:,} Units) per Trade")
    print(f"• Total Open Positions across Basket: {summary['open_position_count']} / Max Allowed: {MAX_CONCURRENT_OPEN_TRADES}")
    print("-" * 66)

    if summary['open_position_count'] >= MAX_CONCURRENT_OPEN_TRADES:
        print("🛡️ Max concurrent trade limit reached. Holding open positions for exit signals.")
        return

    print("📊 Active FX Basket Quotes & Position Sizing Matrix:")
    for pair in BASKET_PAIRS:
        try:
            spot = get_pair_quote(pair)
            pip_loc = get_pip_location(pair)
            
            sl_distance = 20 * pip_loc
            tp_distance = 40 * pip_loc
            
            print(f"  └─ {pair:<7} | Spot: {spot:<9.5f} | Size: {active_lots:.2f} Lots ({active_units:>6,} units) | SL: {sl_distance:.4f} | TP: {tp_distance:.4f}")
        except Exception as err:
            print(f"  └─ {pair:<7} | Quote Fetch Note: {str(err)}")

    print("-" * 66)
    print("✅ System monitoring active. 0.01 lot / $1,000 equity rule enforced.")

if __name__ == "__main__":
    run_multi_asset_quant_cycle()
