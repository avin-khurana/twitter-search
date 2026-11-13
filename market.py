"""yfinance market data: price history, indicators, fundamentals, analyst actions, insiders,
earnings date, options put/call, and the market regime. Every network call is wrapped so a
missing field degrades to None instead of failing the run."""
from __future__ import annotations

import math
import warnings
from datetime import date, datetime

import numpy as np
import pandas as pd

import config

warnings.filterwarnings("ignore", category=FutureWarning)


def _f(x) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def fix_cols(df: pd.DataFrame) -> pd.DataFrame:  # ported from LEAPS/scanner.py
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.droplevel(1)
    return df


def download_history(tickers: list[str], period: str = "1y", start: str | None = None) -> dict[str, pd.DataFrame]:
    """Batch-download daily OHLCV (by `period`, or from `start`). Returns {ticker: df} only for tickers with data."""
    import yfinance as yf

    tickers = sorted(set(tickers))
    if not tickers:
        return {}
    span = {"start": start} if start else {"period": period}
    raw = yf.download(tickers, group_by="ticker", auto_adjust=True, progress=False, threads=True, **span)
    out: dict[str, pd.DataFrame] = {}
    if isinstance(raw.columns, pd.MultiIndex):
        for t in tickers:
            if t in raw.columns.get_level_values(0):
                df = raw[t].dropna(subset=["Close"])
                if len(df):
                    out[t] = df
    elif len(tickers) == 1 and len(raw):
        out[tickers[0]] = raw.dropna(subset=["Close"])
    return out


def _wilder(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(alpha=1 / n, adjust=False).mean()


def indicators(df: pd.DataFrame, spy_ret20: float | None = None) -> dict:
    """Latest-bar indicator snapshot (Wilder RSI/ATR to match TradingView)."""
    c, h, low, o, v = (df[k].astype(float) for k in ("Close", "High", "Low", "Open", "Volume"))
    d = c.diff()
    rs = _wilder(d.clip(lower=0), 14) / _wilder(-d.clip(upper=0), 14)
    rsi = 100 - 100 / (1 + rs)
    tr = pd.concat([h - low, (h - c.shift()).abs(), (low - c.shift()).abs()], axis=1).max(axis=1)
    atr = _wilder(tr, 14)
    ema20 = c.ewm(span=20, adjust=False).mean()
    ema50 = c.ewm(span=50, adjust=False).mean()
    avg_vol20 = v.shift(1).rolling(20).mean()

    def ret(n: int) -> float | None:
        return _f(c.iloc[-1] / c.iloc[-1 - n] - 1) if len(c) > n else None

    close = _f(c.iloc[-1])
    ret20 = ret(20)
    snap = {
        "bar_date": str(df.index[-1].date()),
        "bars": int(len(df)),
        "close": close,
        "high": _f(h.iloc[-1]),
        "low": _f(low.iloc[-1]),
        "prev_close": _f(c.iloc[-2]) if len(c) > 1 else None,
        "change_1d": ret(1),
        "gap": _f(o.iloc[-1] / c.iloc[-2] - 1) if len(c) > 1 else None,
        "ret_5d": ret(5),
        "ret_20d": ret20,
        "rsi14": _f(rsi.iloc[-1]),
        "atr14": _f(atr.iloc[-1]),
        "ema20": _f(ema20.iloc[-1]),
        "ema50": _f(ema50.iloc[-1]),
        "rel_volume": _f(v.iloc[-1] / avg_vol20.iloc[-1]) if _f(avg_vol20.iloc[-1]) else None,
        "dollar_vol20": _f((c * v).rolling(20).mean().iloc[-1]),
        "high20_prior": _f(h.shift(1).rolling(20).max().iloc[-1]),
        "low10": _f(low.rolling(10).min().iloc[-1]),
        "rs_20d": (ret20 - spy_ret20) if (ret20 is not None and spy_ret20 is not None) else None,
    }
    snap["atr_pct"] = (snap["atr14"] / close) if (snap["atr14"] and close) else None
    return snap


INFO_FIELDS = ("quoteType", "exchange", "marketCap", "currentPrice", "regularMarketPrice", "averageVolume",
               "recommendationMean", "recommendationKey", "numberOfAnalystOpinions", "targetMeanPrice",
               "shortPercentOfFloat", "shortRatio", "heldPercentInstitutions", "revenueGrowth",
               "earningsGrowth", "forwardPE", "sector", "industry", "longName", "shortName", "floatShares")


def fetch_info(ticker: str) -> dict:
    import yfinance as yf

    try:
        info = yf.Ticker(ticker).info or {}
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}
    return {k: info.get(k) for k in INFO_FIELDS}


def insider_summary(t_obj, days: int = config.INSIDER_LOOKBACK_DAYS) -> dict | None:
    """Open-market purchases vs sales only (awards, gifts, option exercises are ignored)."""
    try:
        df = t_obj.insider_transactions
    except Exception:
        return None
    if df is None or not len(df) or "Start Date" not in df.columns:
        return None
    cutoff = pd.Timestamp.now() - pd.Timedelta(days=days)
    df = df[pd.to_datetime(df["Start Date"], errors="coerce") >= cutoff]
    text = df.get("Text", pd.Series("", index=df.index)).fillna("").str.lower()
    buys, sells = df[text.str.startswith("purchase")], df[text.str.startswith("sale")]
    val = lambda x: float(pd.to_numeric(x.get("Value"), errors="coerce").fillna(0).sum())  # noqa: E731
    return {
        "buys": int(len(buys)), "buy_value": val(buys), "buyers": int(buys["Insider"].nunique()) if len(buys) else 0,
        "sells": int(len(sells)), "sell_value": val(sells),
        "sellers": int(sells["Insider"].nunique()) if len(sells) else 0,
    }


def analyst_actions(t_obj, days: int = config.ANALYST_LOOKBACK_DAYS) -> dict | None:
    try:
        ud = t_obj.upgrades_downgrades
    except Exception:
        return None
    if ud is None or not len(ud):
        return None
    ud = ud.copy()
    ud.index = pd.to_datetime(ud.index, errors="coerce")
    ud = ud[ud.index >= pd.Timestamp.now() - pd.Timedelta(days=days)].sort_index(ascending=False)
    action = ud.get("Action", pd.Series(dtype=str)).fillna("").str.lower()
    pta = ud.get("priceTargetAction", pd.Series(dtype=str)).fillna("").str.lower()
    recent = []
    for ts, r in ud.head(4).iterrows():
        grade = f"{r.get('FromGrade') or '—'}→{r.get('ToGrade')}" if r.get("FromGrade") else f"{r.get('ToGrade')}"
        pt_now, pt_prev = _f(r.get("currentPriceTarget")), _f(r.get("priorPriceTarget"))
        pt = f", PT {pt_prev:.0f}→{pt_now:.0f}" if (pt_now and pt_prev) else (f", PT {pt_now:.0f}" if pt_now else "")
        recent.append(f"{ts.date()} {r.get('Firm')}: {grade}{pt}")
    return {
        "upgrades": int((action == "up").sum()), "downgrades": int((action == "down").sum()),
        "initiations": int((action == "init").sum()),
        "pt_raised": int((pta == "raises").sum()), "pt_lowered": int((pta == "lowers").sum()),
        "recent": recent,
    }


def trading_days_between(start: date, end: date) -> int:
    return int(np.busday_count(start, end))


def earnings_info(t_obj, today: date | None = None) -> dict | None:
    today = today or date.today()
    try:
        cal = t_obj.calendar
    except Exception:
        return None
    dates = []
    if isinstance(cal, dict):
        dates = cal.get("Earnings Date") or []
    elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.index:
        dates = list(cal.loc["Earnings Date"].values)
    upcoming = sorted(d for d in (pd.to_datetime(x, errors="coerce") for x in dates)
                      if d is not pd.NaT and d.date() >= today)
    if not upcoming:
        return None
    d = upcoming[0].date()
    return {"date": str(d), "trading_days": trading_days_between(today, d)}


def put_call(t_obj, today: date | None = None, n_expiries: int = 2, min_volume: int = 500) -> dict | None:
    """Put/call volume and OI ratios over the nearest expiries after today (skips same-day 0DTE)."""
    today = today or date.today()
    try:
        exps = [e for e in (t_obj.options or []) if datetime.strptime(e, "%Y-%m-%d").date() > today][:n_expiries]
        cv = pv = co = po = 0.0
        for e in exps:
            ch = t_obj.option_chain(e)
            cv += float(ch.calls["volume"].fillna(0).sum())
            pv += float(ch.puts["volume"].fillna(0).sum())
            co += float(ch.calls["openInterest"].fillna(0).sum())
            po += float(ch.puts["openInterest"].fillna(0).sum())
    except Exception:
        return None
    if cv + pv < min_volume or cv == 0:
        return None
    return {"pc_volume": pv / cv, "pc_oi": (po / co) if co else None, "option_volume": cv + pv,
            "expiries": exps}


def fetch_profile(ticker: str) -> dict:
    """Everything beyond price history for one ticker."""
    import yfinance as yf

    t = yf.Ticker(ticker)
    return {
        "insiders": insider_summary(t),
        "analysts": analyst_actions(t),
        "earnings": earnings_info(t),
        "options": put_call(t),
    }


def market_regime() -> dict:
    import yfinance as yf

    spy = fix_cols(yf.download("SPY", period="1y", progress=False, auto_adjust=True))
    vix = fix_cols(yf.download("^VIX", period="10d", progress=False, auto_adjust=True))
    c = spy["Close"].astype(float)
    spy_close, spy_ema50 = float(c.iloc[-1]), float(c.ewm(span=50, adjust=False).mean().iloc[-1])
    vix_close = float(vix["Close"].dropna().iloc[-1])
    weak = spy_close < spy_ema50 or vix_close > config.VIX_WEAK
    reasons = []
    if spy_close < spy_ema50:
        reasons.append("SPY below 50-day EMA")
    if vix_close > config.VIX_WEAK:
        reasons.append(f"VIX above {config.VIX_WEAK:.0f}")
    return {
        "spy_close": spy_close, "spy_ema50": spy_ema50, "vix": vix_close,
        "spy_ret20": float(c.iloc[-1] / c.iloc[-21] - 1), "weak": weak,
        "label": "WEAK — " + ", ".join(reasons) if weak else "OK — SPY above 50-day EMA, VIX calm",
        "bar_date": str(spy.index[-1].date()),
    }

