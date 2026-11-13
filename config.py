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
SENTIMENT_CSV = DATA_DIR / "sentiment_history.csv"

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
STOCKTWITS_DIGEST_MSGS = 10       # Claude needs post text to read the crowd's emotion
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
AVOID_N = 5
TOP_MIN_MATERIALITY = 2       # top-5 names need a real catalyst (AI materiality >= 2, type != none)

# ── Behavioral setups (setups.py) ──────────────────────────────────────────────
# Drift: people underreact to real good news and catch up over days
DRIFT_MIN_MOVE = 0.03         # 1-day move or gap that confirms the news...
DRIFT_MIN_REL_VOLUME = 1.2    # ...on at least this much relative volume
DRIFT_MIN_5D = 0.06           # or: up this much over 5 days and not giving it back
DRIFT_MIN_SCORE = 60          # composite floor for a drift BUY
DRIFT_MIN_SCORE_WEAK = 65     # stricter when the market regime is weak

# Overreaction dip: panic selling on news that is not actually bad
DIP_MIN_DROP = 0.04           # 1-day drop of at least this much...
DIP_ATR_MULT = 1.25           # ...and at least this many ATRs
DIP_MIN_DROP_5D = 0.10        # or a 5-day drop of at least this much...
DIP_ATR_MULT_5D = 3.0         # ...and this many ATRs
DIP_MAX_PRIOR_RUN = 0.05      # not a pullback after a spike: 5-day return must be below this
DIP_MIN_NEWS = 45             # catalyst score must be at least neutral
DIP_MIN_PROSPECTS = 60        # business outlook must be solid
DIP_TRIGGER_ATR = 1.0         # buy trigger: a bounce of this many ATRs off the close (or the last high if nearer)
DIP_MIN_RISK_ATR = 0.75       # trigger entry risk is clamped to this many ATRs...
DIP_MAX_RISK_ATR = 2.0

# Hype fade: euphoria and herding without confirmed news
HYPE_MIN_INTENSITY = 4        # euphoria at this intensity (1-5)...
HYPE_BULL_RATIO = 0.85        # ...or euphoria with this share of tagged posts bullish

# Hope trap: falling price + bad news while the crowd stays bullish
HOPE_BULL_RATIO = 0.80        # StockTwits skews bullish by default, so this bar is high
HOPE_MAX_NEWS = 40
HOPE_MIN_DROP_20D = 0.10
HOPE_MIN_DROP_5D = 0.08
