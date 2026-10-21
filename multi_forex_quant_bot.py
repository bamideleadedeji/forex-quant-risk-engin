import os
import sys
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import MetaTrader5 as mt5

# ----------------------------------------------------------------------
# 1. Credentials & Configuration (Exness MT5 & Finnhub)
# ----------------------------------------------------------------------
MT5_LOGIN = int(os.environ.get("EXNESS_MT5_LOGIN", "81908274"))
MT5_PASSWORD = os.environ.get("EXNESS_MT5_PASSWORD", "b8!T4*xQ9w")
MT5_SERVER = os.environ.get("EXNESS_MT5_SERVER", "Exness-MT5Trial10")

# Finnhub API Key for Macro Economic Calendar Filtering
NEWS_API_KEY = os.environ.get("FINNHUB_API_KEY", "dbcbqbhr01qioil6nl50dbcbqbhr01qioil6nl5g")

# The 6 Major Currency Pairs Basket
BASKET_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]

# Quantitative Execution & Risk Parameters
BASE_LOT_PER_1000_EQUITY = 0.01  # 0.01 Lots (1,000 units) per $1,000 Account Equity
MAX_CONCURRENT_OPEN_TRADES = 3   # Maximum simultaneous trades allowed across basket
NEWS_BLACKOUT_MINUTES = 15      # Pause trading 15m before & after high-impact news

# ----------------------------------------------------------------------
# 2. MT5 Terminal Connection Handler
# ----------------------------------------------------------------------
def initialize_mt5_connection():
    """Initializes connection to Exness MT5 Terminal."""
    if not mt5.initialize():
        print(f"❌ MT5 Initialization failed: {mt5.last_error()}")
        sys.exit(1)
        
    authorized = mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if not authorized:
        print(f"❌ MT5 Login failed for account #{MT5_LOGIN} on {MT5_SERVER}: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)
        
    print(f"✅ Connected to Exness MT5 Account #{MT5_LOGIN} ({MT5_SERVER})")

# ----------------------------------------------------------------------
# 3. Multi-Central Bank Macro News Filter
# ----------------------------------------------------------------------
def is_news_blackout_active() -> tuple[bool, str]:
    """
    Checks Finnhub economic calendar for High-Impact macro events across G7 economies
    within the ±15-minute window.
    """
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
# 4. Symbol Resolution & Proportional Sizing Engine
# ----------------------------------------------------------------------
def resolve_exness_symbol(base_pair: str) -> str:
    """Detects symbol suffix on Exness accounts (e.g. EURUSD vs EURUSDm)."""
    possible_symbols = [base_pair, f"{base_pair}m", f"{base_pair}.c", f"{base_pair}c"]
    for sym in possible_symbols:
        info = mt5.symbol_info(sym)
        if info is not None:
            if not info.visible:
                mt5.symbol_select(sym, True)
            return sym
    return base_pair

def calculate_proportional_lot_size(equity: float) -> tuple[float, int]:
    """
    Calculates exact lot sizing proportional to equity:
    0.01 Lots (1,000 units) per $1,000 Account Equity.
    For a $500 account, lot size = 0.01 lots (1,000 units minimum).
    """
    scaling_factor = equity / 1000.0
    lots = round(scaling_factor * BASE_LOT_PER_1000_EQUITY, 2)
    active_lots = max(0.01, lots)
    active_units = int(active_lots * 100000)
    return active_lots, active_units

# ----------------------------------------------------------------------
# 5. Multi-Asset Execution Loop
# ----------------------------------------------------------------------
def run_multi_asset_quant_cycle():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n==================================================================")
    print(f"[{timestamp}] Multi-Asset Proportional Risk Automation Engine (Exness MT5)")
    print(f"==================================================================")

    # Step A: Initialize MT5 Terminal Connection
    initialize_mt5_connection()

    # Step B: High-Impact Macro News Filter Check
    is_news, news_msg = is_news_blackout_active()
    if is_news:
        print(f"🚨 MULTI-ASSET NEWS BLACKOUT TRIGGERED: {news_msg}")
        print("🛡️ Holding execution. News volatility protection active.")
        mt5.shutdown()
        return

    # Step C: Account Diagnostics & Capital Scaling
    account_info = mt5.account_info()
    if account_info is None:
        print("❌ Failed to retrieve MT5 account info.")
        mt5.shutdown()
        return

    equity = account_info.equity
    balance = account_info.balance
    active_lots, active_units = calculate_proportional_lot_size(equity)
    
    positions = mt5.positions_get()
    open_count = len(positions) if positions is not None else 0

    print(f"• Account Equity (NAV): ${equity:,.2f} | Balance: ${balance:,.2f}")
    print(f"• Dynamic Sizing Rule: {active_lots:.2f} Lots ({active_units:,} Units) per Trade")
    print(f"• Total Open Positions across Basket: {open_count} / Max Allowed: {MAX_CONCURRENT_OPEN_TRADES}")
    print("-" * 66)

    # Step D: Evaluate Open Position Limit Guard
    if open_count >= MAX_CONCURRENT_OPEN_TRADES:
        print("🛡️ Max concurrent trade limit reached. Holding open positions for exit signals.")
        mt5.shutdown()
        return

    # Step E: Iterate and Monitor FX Basket Quotes & Risk
    print("📊 Active Exness FX Basket Quotes & Position Sizing Matrix:")
    for base_pair in BASKET_PAIRS:
        symbol = resolve_exness_symbol(base_pair)
        tick = mt5.symbol_info_tick(symbol)
        
        if tick is not None:
            spot_bid = tick.bid
            spot_ask = tick.ask
            symbol_info = mt5.symbol_info(symbol)
            point = symbol_info.point if symbol_info else 0.00001
            spread_pips = round((spot_ask - spot_bid) / point / 10, 1)
            
            # Stop-Loss / Take-Profit calculations (20 pips SL / 40 pips TP)
            pip_location = 0.01 if "JPY" in symbol else 0.0001
            sl_distance = 20 * pip_location
            tp_distance = 40 * pip_location
            
            print(f"  └─ {symbol:<8} | Bid: {spot_bid:<8.5f} | Ask: {spot_ask:<8.5f} | Spread: {spread_pips:>4.1f} pips | Size: {active_lots:.2f} Lots ({active_units:>6,} units) | SL: {sl_distance:.4f} | TP: {tp_distance:.4f}")
        else:
            print(f"  └─ {symbol:<8} | Quote Fetch Note: Market closed or symbol inactive")

    print("-" * 66)
    print("✅ System monitoring active. 0.01 lot / $1,000 equity rule enforced.")
    mt5.shutdown()

if __name__ == "__main__":
    run_multi_asset_quant_cycle()
