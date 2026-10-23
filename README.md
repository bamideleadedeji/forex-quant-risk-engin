# Institutional Multi-Asset Forex Quantitative Risk & Execution Engine

An automated, data-driven quantitative trading engine engineered for systematic multi-asset Forex trading on the **Exness MetaTrader 5 (MT5)** platform using Python and GitHub Actions.

This system eliminates manual trading fatigue, emotional biases, and news-spike drawdowns by deploying a strict capital preservation framework across a G7 major currency basket (`EUR/USD`, `GBP/USD`, `USD/JPY`, `AUD/USD`, `USD/CAD`, `USD/CHF`).

---

## Core Institutional Safeguards

- **Proportional Equity Position Sizing:** Automatically scales order sizes at **0.01 Lots (1,000 units) per $1,000 Account Equity**. As portfolio equity grows, trade size expands proportionally; during drawdowns, position size contracts automatically to safeguard capital.
- **Automated Macroeconomic News Blackout Filter:** Connects to live macroeconomic calendar feeds via the Finnhub API. Automatically holds execution and protects open trades **15 minutes before and after** high-impact news events (e.g., US NFP, CPI, Central Bank rate decisions).
- **Server-Side Risk Controls:** Every trade automatically attaches non-negotiable, server-enforced **Stop-Loss** and **Take-Profit** orders directly at market entry.
- **Basket Exposure Limits:** Caps concurrent open positions across the currency basket (maximum 3 simultaneous trades) to prevent over-leverage and correlated USD exposure.
- **Headless Cloud Execution:** Runs headlessly on a scheduled Windows runner via GitHub Actions, initializing the MT5 terminal and maintaining full trade audit logs (`trade_log.csv`) automatically.

---

## Repository Architecture

```text
forex-quant-risk-engine/
├── .github/
│   └── workflows/
│       └── cron_execution.yml   # 15-minute GitHub Actions automated workflow
├── multi_forex_quant_bot.py     # Main multi-asset trading engine & news filter
├── requirements.txt             # Python package dependencies
├── .gitignore                   # Version control exclusions
├── LICENSE                      # License terms
└── README.md                    # Project documentation
Installation & Setup
Clone the Repository:

Bash
git clone [https://github.com/bamideleadedeji/forex-quant-risk-engine.git
cd forex-quant-risk-engine
Install Python Dependencies:

Bash
pip install -r requirements.txt
