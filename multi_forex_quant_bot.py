import os
import sys
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, timezone
import MetaTrader5 as mt5

# Force UTF-8 Encoding for Windows Console / GitHub Actions Runners
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ----------------------------------------------------------------------
# 1. Credentials & Configuration (Exness MT5 & Finnhub)
# ----------------------------------------------------------------------
raw_login = os.environ.get("EXNESS_MT5_LOGIN", "81908274").strip()
MT5_LOGIN = int(raw_login) if raw_login.isdigit() else 81908274

MT5_PASSWORD = os.environ.get("EXNESS_MT5_PASSWORD", "b8!T4*xQ9w").strip()
MT5_SERVER = os.environ.get("EXNESS_MT5_SERVER", "Exness-MT5Trial10").strip()

# Finnhub API Key for Macro Economic Calendar Filtering
NEWS_API_KEY = os.environ.get("FINNHUB_API_KEY", "dbcbqbhr01qioil6nl50dbcbqbhr01qioil6nl5g").strip()

# The 6 Major Currency Pairs Basket
BASKET_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF"]

# Quantitative Execution & Risk Parameters
BASE_LOT_PER_1000_EQUITY = 0.01  # 0.01 Lots (1,000 units) per $1,000 Account Equity
MAX_CONCURRENT_OPEN_TRADES = 3   # Maximum simultaneous trades allowed across basket
NEWS_BLACKOUT_MINUTES = 15      # Pause trading 15m before & after high-impact news

SL_PIPS = 20.0  # Stop Loss in pips
TP_PIPS = 40.0  # Take Profit in pips

# ----------------------------------------------------------------------
# 2. MT5 Terminal Connection Handler
# ----------------------------------------------------------------------
def initialize_mt5_connection():
    """Initializes connection to Exness MT5 Terminal."""
    if not mt5.initialize():
        print(f"[FAIL] MT5 Initialization failed: {mt5.last_error()}")
        sys.exit(1)
        
    authorized = mt5.login(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if not authorized:
        print(f"[FAIL] MT5 Login failed for account #{MT5_LOGIN} on {MT5_SERVER}: {mt5.last_error()}")
        mt5.shutdown()
        sys.exit(1)
        
    print(f"[SUCCESS] Connected to Exness MT5 Account #{MT5_LOGIN} ({MT5_SERVER})")

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
# 4. Symbol Resolution & Technical Signal Engine
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
    """Calculates lot sizing proportional to equity (0.01 lot per $1,000 equity)."""
    scaling_factor = equity / 1000.0
    lots = round(scaling_factor * BASE_LOT_PER_1000_EQUITY, 2)
    active_lots = max(0.01, lots)
    active_units = int(active_lots * 100000)
    return active_lots, active_units

def evaluate_market_signal(symbol: str) -> str:
    """
    Fetches M15 candle historical data and evaluates fast vs slow EMA crossover.
    Returns 'BUY', 'SELL', or 'NEUTRAL'.
    """
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 50)
    if rates is None or len(rates) < 50:
        return "NEUTRAL"

    df = pd.DataFrame(rates)
    df['ema_fast'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_slow'] = df['close'].ewm(span=21, adjust=False).mean()

    prev_fast, curr_fast = df['ema_fast'].iloc[-2], df['ema_fast'].iloc[-1]
    prev_slow, curr_slow = df['ema_slow'].iloc[-2], df['ema_slow'].iloc[-1]

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        return "BUY"
    elif prev_fast >= prev_slow and curr_fast < curr_slow:
        return "SELL"

    return "NEUTRAL"

# ----------------------------------------------------------------------
# 5. Order Placement Execution Engine
# ----------------------------------------------------------------------
def execute_market_order(symbol: str, order_type: str, lot_size: float) -> bool:
    """Constructs and sends trade execution request to Exness MT5 server."""
    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)
    if tick is None or symbol_info is None:
        print(f"  [FAIL] Order Failed: Unable to fetch market info for {symbol}")
        return False

    point = symbol_info.point
    pip_multiplier = 0.01 if "JPY" in symbol else 0.0001

    if order_type == "BUY":
        price = tick.ask
        sl = round(price - (SL_PIPS * pip_multiplier), symbol_info.digits)
        tp = round(price + (TP_PIPS * pip_multiplier), symbol_info.digits)
        trade_action = mt5.ORDER_TYPE_BUY
    else:
        price = tick.bid
        sl = round(price + (SL_PIPS * pip_multiplier), symbol_info.digits)
        tp = round(price - (TP_PIPS * pip_multiplier), symbol_info.digits)
        trade_action = mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": trade_action,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 1008274,
        "comment": "QuantRiskEngine Auto",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result is None:
        print(f"  [FAIL] Order send failed for {symbol}: No response from MT5 server")
        return False

    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"  [FAIL] Order execution rejected for {symbol}: Retcode {result.retcode} ({result.comment})")
        return False

    print(f"  [ORDER PLACED] {order_type} {lot_size} Lots on {symbol} @ {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} (Ticket #{result.order})")
    return True

# ----------------------------------------------------------------------
# 6. Multi-Asset Execution Loop
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
        print(f"[NEWS BLACKOUT] {news_msg}")
        print("[HOLD] Holding execution. News volatility protection active.")
        mt5.shutdown()
        return

    # Step C: Account Diagnostics & Capital Scaling
    account_info = mt5.account_info()
    if account_info is None:
        print("[FAIL] Failed to retrieve MT5 account info.")
        mt5.shutdown()
        return

    equity = account_info.equity
    balance = account_info.balance
    active_lots, active_units = calculate_proportional_lot_size(equity)
    
    positions = mt5.positions_get()
    open_count = len(positions) if positions is not None else 0

    open_symbols = [pos.symbol for pos in positions] if positions else []

    print(f"• Account Equity (NAV): ${equity:,.2f} | Balance: ${balance:,.2f}")
    print(f"• Dynamic Sizing Rule: {active_lots:.2f} Lots ({active_units:,} Units) per Trade")
    print(f"• Total Open Positions across Basket: {open_count} / Max Allowed: {MAX_CONCURRENT_OPEN_TRADES}")
    print("-" * 66)

    # Step D: Evaluate Open Position Limit Guard
    if open_count >= MAX_CONCURRENT_OPEN_TRADES:
        print("[HOLD] Max concurrent trade limit reached. Holding open positions for exit signals.")
        mt5.shutdown()
        return

    # Step E: Scan FX Basket, Evaluate Signals, and Execute Orders
    print("Active Exness FX Basket Quotes & Signal Execution Matrix:")
    for base_pair in BASKET_PAIRS:
        symbol = resolve_exness_symbol(base_pair)
        tick = mt5.symbol_info_tick(symbol)
        
        if tick is not None:
            spot_bid = tick.bid
            spot_ask = tick.ask
            symbol_info = mt5.symbol_info(symbol)
            point = symbol_info.point if symbol_info else 0.00001
            spread_pips = round((spot_ask - spot_bid) / point / 10, 1)
            
            signal = evaluate_market_signal(symbol)
            
            print(f"  └─ {symbol:<8} | Bid: {spot_bid:<8.5f} | Ask: {spot_ask:<8.5f} | Spread: {spread_pips:>4.1f} pips | Signal: {signal:<7}")

            if signal in ["BUY", "SELL"] and symbol not in open_symbols:
                if open_count < MAX_CONCURRENT_OPEN_TRADES:
                    executed = execute_market_order(symbol, signal, active_lots)
                    if executed:
                        open_count += 1
                        open_symbols.append(symbol)
                else:
                    print(f"     [HOLD] Max trade count reached. Skipping execution for {symbol}.")
        else:
            print(f"  └─ {symbol:<8} | Quote Fetch Note: Market closed or symbol inactive")

    print("-" * 66)
    print("[COMPLETE] System cycle complete. 0.01 lot / $1,000 equity rule enforced.")
    mt5.shutdown()

if __name__ == "__main__":
    run_multi_asset_quant_cycle()
