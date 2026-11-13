"""Track record: forward returns of every logged stock vs SPY, by call and by behavioral setup,
and whether stop or target was hit first.

Usage: python track.py   (prints per-pick results and the summary)
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import config
import market
import setups

HORIZONS = (1, 5, 10)
SETUP_ORDER = (setups.DRIFT, setups.DIP, setups.HYPE_FADE, setups.HOPE_TRAP)


def _fwd_bars(df: pd.DataFrame, bar_date: str) -> pd.DataFrame:
    return df[df.index > pd.Timestamp(bar_date)]


def stop_target_outcome(fwd: pd.DataFrame, side: str, entry: float, stop: float, target: float,
                        ref_close: float, window: int = config.TIME_STOP_DAYS, entry_type: str = "auto") -> str:
    """'target' / 'stop' / 'time' / 'open' / 'not filled'.
    entry_type: 'market' (in at the close), 'limit' (wait for a pullback to entry), 'stop' (wait for a
    break through entry), 'auto' (market if entry is at the close, else limit).
    If stop and target fall in the same bar, counts the stop (conservative)."""
    if not (entry and stop and target):
        return "n/a"
    bars = fwd.iloc[:window]
    if entry_type not in ("market", "limit", "stop"):
        entry_type = "market" if abs(entry - ref_close) / ref_close <= 0.002 else "limit"
    start = 0
    if entry_type != "market":
        def filled(b) -> bool:
            if entry_type == "stop":
                return b["High"] >= entry if side == "long" else b["Low"] <= entry
            return b["Low"] <= entry if side == "long" else b["High"] >= entry

        hits = [i for i, (_, b) in enumerate(bars.iterrows()) if filled(b)]
        if not hits:
            return "not filled" if len(bars) >= window else "open"
        start = hits[0]
    for _, b in bars.iloc[start:].iterrows():
        hit_stop = b["Low"] <= stop if side == "long" else b["High"] >= stop
        hit_tgt = b["High"] >= target if side == "long" else b["Low"] <= target
        if hit_stop:
            return "stop"
        if hit_tgt:
            return "target"
    return "time" if len(bars) >= window else "open"


def evaluate(picks: pd.DataFrame, hist: dict[str, pd.DataFrame]) -> pd.DataFrame:
    spy = hist.get("SPY")
    rows = []
    for p in picks.to_dict("records"):
        df = hist.get(p["ticker"])
        if df is None:
            continue
        fwd = _fwd_bars(df, p["bar_date"])
        ref = float(p["close"])
        row = dict(p)
        spy_ref = float(spy["Close"][spy.index <= pd.Timestamp(p["bar_date"])].iloc[-1]) if spy is not None else None
        spy_fwd = _fwd_bars(spy, p["bar_date"]) if spy is not None else None
        for h in HORIZONS:
            row[f"ret_{h}d"] = float(fwd["Close"].iloc[h - 1] / ref - 1) if len(fwd) >= h else None
            if row[f"ret_{h}d"] is not None and spy_fwd is not None and len(spy_fwd) >= h:
                row[f"xs_{h}d"] = row[f"ret_{h}d"] - float(spy_fwd["Close"].iloc[h - 1] / spy_ref - 1)
            else:
                row[f"xs_{h}d"] = None
        side = "short" if p["action"] == "SELL" else "long"
        row["outcome"] = stop_target_outcome(fwd, side, float(p["entry"]), float(p["stop"]), float(p["target"]),
                                             ref, entry_type=str(p.get("entry_type") or "auto"))
        rows.append(row)
    return pd.DataFrame(rows)


def _stats(sub: pd.DataFrame, expect_down: bool) -> dict:
    r5 = sub["ret_5d"].dropna() if len(sub) else pd.Series(dtype=float)
    x5 = sub["xs_5d"].dropna() if len(sub) else pd.Series(dtype=float)
    hits = (r5 < 0) if expect_down else (r5 > 0)
    return {
        "n": int(len(r5)),
        "avg_ret_5d": float(r5.mean()) if len(r5) else None,
        "hit_rate_5d": float(hits.mean()) if len(r5) else None,
        "avg_excess_5d": float(x5.mean()) if len(x5) else None,
        "outcomes": {k: int(v) for k, v in sub["outcome"].value_counts().items()} if len(sub) else {},
    }


def summarize(ev: pd.DataFrame) -> dict:
    """by_action covers the emailed lists (top + avoid); by_setup covers every analyzed stock."""
    if not len(ev):
        empty = _stats(ev, False)
        return {"evaluated": 0, "by_action": {a: empty for a in ("BUY", "HOLD", "SELL")},
                "by_setup": {s: empty for s in SETUP_ORDER}}
    listed = ev[ev["list"].isin(["top", "avoid"])]
    return {
        "evaluated": int(ev["ret_5d"].notna().sum()),
        "by_action": {a: _stats(listed[listed["action"] == a], a == "SELL") for a in ("BUY", "HOLD", "SELL")},
        "by_setup": {s: _stats(ev[ev["setup"] == s], s in setups.AVOID_SETUPS) for s in SETUP_ORDER},
    }


def load_picks(today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    if not config.PICKS_CSV.exists():
        return pd.DataFrame()
    picks = pd.read_csv(config.PICKS_CSV)
    for col, default in (("setup", setups.NONE), ("entry_type", "auto"), ("list", "top")):
        if col not in picks:
            picks[col] = default
        picks[col] = picks[col].fillna(default)
    return picks[(picks["bar_date"] < str(today)) & (picks["close"] > 0)]


def _history_for(picks: pd.DataFrame) -> dict[str, pd.DataFrame]:
    start = (pd.Timestamp(picks["bar_date"].min()) - timedelta(days=7)).date()
    return market.download_history(sorted(set(picks["ticker"])) + ["SPY"], start=str(start))


def summary(today: date | None = None) -> dict:
    picks = load_picks(today)
    if not len(picks):
        return {"evaluated": 0, "note": "No picks old enough to evaluate yet — the track record starts after the first full trading day."}
    return summarize(evaluate(picks, _history_for(picks)))


if __name__ == "__main__":
    picks = load_picks()
    if not len(picks):
        print("No picks old enough to evaluate yet.")
    else:
        ev = evaluate(picks, _history_for(picks))
        cols = ["date", "list", "ticker", "action", "setup", "composite", "close", "ret_1d", "ret_5d", "ret_10d",
                "xs_5d", "outcome"]
        with pd.option_context("display.width", 180, "display.float_format", "{:.3f}".format):
            print(ev[[c for c in cols if c in ev.columns]].to_string(index=False))
        print(summarize(ev))
