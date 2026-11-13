"""Central configuration: secrets from env/.env, plus every tunable weight and threshold."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

RUNS_DIR = ROOT / "runs"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
PICKS_CSV = DATA_DIR / "picks.csv"
MENTIONS_CSV = DATA_DIR / "mentions_history.csv"

# ── Secrets (all optional; missing ones just disable that feature) ─────────────
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "")
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
EMAIL_APP_PASSWORD = os.getenv("EMAIL_APP_PASSWORD", "")
EMAIL_TO = os.getenv("EMAIL_TO", "")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

USER_AGENT = "stock-buzz-scanner/0.1 (personal research script)"
HTTP_TIMEOUT = 15

# ── Discovery ──────────────────────────────────────────────────────────────────
APEWISDOM_TOP_N = 30          # Reddit-trending tickers added to the pool
APEWISDOM_MAX_PAGES = 3       # 100 tickers/page; pages beyond top-N are used only for lookups
STOCKTWITS_TRENDING_N = 30
MOVERS_PER_SCREEN = 25        # per yfinance screen: day_gainers / day_losers / most_actives
MOVER_SCREENS = ("day_gainers", "day_losers", "most_actives")

# ── Universe filters ───────────────────────────────────────────────────────────
MIN_PRICE = 5.0
MIN_MARKET_CAP = 2e9
MIN_DOLLAR_VOLUME = 20e6      # 20-day average close*volume
MIN_HISTORY_BARS = 60
# yfinance exchange codes for US-listed stocks
US_EXCHANGES = {"NMS", "NGM", "NCM", "NYQ", "ASE", "PCX", "BTS", "NAS", "NYS"}

MAX_DEEP = 20                 # tickers that get full enrichment + Claude judgment

# ── Enrichment ─────────────────────────────────────────────────────────────────
NEWS_LOOKBACK_DAYS = 2
MAX_HEADLINES = 8
STOCKTWITS_DIGEST_MSGS = 6
INSIDER_LOOKBACK_DAYS = 90
ANALYST_LOOKBACK_DAYS = 30
MENTION_BASELINE_DAYS = 7

# ── Scoring ────────────────────────────────────────────────────────────────────
WEIGHTS = {
    "social": 0.20,
    "attention": 0.10,
    "catalyst": 0.20,
    "prospects": 0.15,
    "technical": 0.20,
    "smart_money": 0.15,
}
EUPHORIA_PENALTY = 10
EARNINGS_PENALTY = 5
EARNINGS_WINDOW_TRADING_DAYS = 10
PROSPECTS_ADJ_LIMIT = 15

# Weak market regime: SPY below its 50-day EMA or VIX above this
VIX_WEAK = 25.0

# ── Actions (2–10 trading-day swing) ───────────────────────────────────────────
BUY_THRESHOLD = 65
BUY_THRESHOLD_WEAK_REGIME = 72
BUY_MIN_TECHNICAL = 55
SELL_THRESHOLD = 40
SELL_BEARISH_CATALYST_MAX = 30

# ── Trade levels ───────────────────────────────────────────────────────────────
STOP_ATR_MULT = 1.5
MIN_STOP_ATR = 1.0
TARGET_R = 2.0
EXTENDED_ATR = 1.0            # price more than this many ATRs above EMA20 => wait for pullback
TIME_STOP_DAYS = 10

TOP_N = 5
AVOID_N = 3
TOP_MIN_MATERIALITY = 2       # top-5 names need a real catalyst (AI materiality >= 2, type != none)
