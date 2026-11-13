"""Track record: forward returns of logged picks vs SPY, and whether stop or target was hit first.

Usage: python track.py   (prints per-pick results and the summary)
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

import config
import market

HORIZONS = (1, 5, 10)


def _fwd_bars(df: pd.DataFrame, bar_date: str) -> pd.DataFrame:
    return df[df.index > pd.Timestamp(bar_date)]


def stop_target_outcome(fwd: pd.DataFrame, side: str, entry: float, stop: float, target: float,
                        ref_close: float, window: int = config.TIME_STOP_DAYS) -> str:
    """'target' / 'stop' / 'time' / 'open' / 'not filled'. Assumes the planned entry fills when traded through;
    if stop and target fall in the same bar, counts the stop (conservative)."""
    if not (entry and stop and target):
        return "n/a"
    bars = fwd.iloc[:window]
    start = 0
    if abs(entry - ref_close) / ref_close > 0.002:                  # pullback entry: wait for a fill
        filled = [i for i, (_, b) in enumerate(bars.iterrows()) if b["Low"] <= entry <= b["High"]
                  or (side == "long" and b["Open"] <= entry) or (side == "short" and b["Open"] >= entry)]
        if not filled:
            return "not filled" if len(bars) >= window else "open"
        start = filled[0]
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
        row["outcome"] = stop_target_outcome(fwd, side, float(p["entry"]), float(p["stop"]), float(p["target"]), ref)
        rows.append(row)
    return pd.DataFrame(rows)


def summarize(ev: pd.DataFrame) -> dict:
    by_action = {}
    for action in ("BUY", "HOLD", "SELL"):
        sub = ev[ev["action"] == action] if len(ev) else ev
        r5 = sub["ret_5d"].dropna() if len(sub) else pd.Series(dtype=float)
        hits = (r5 < 0) if action == "SELL" else (r5 > 0)
        x5 = sub["xs_5d"].dropna() if len(sub) else pd.Series(dtype=float)
        by_action[action] = {
            "n": int(len(r5)),
            "avg_ret_5d": float(r5.mean()) if len(r5) else None,
            "hit_rate_5d": float(hits.mean()) if len(r5) else None,
            "avg_excess_5d": float(x5.mean()) if len(x5) else None,
            "outcomes": {k: int(v) for k, v in sub["outcome"].value_counts().items()} if len(sub) else {},
        }
    return {"evaluated": int(len(ev)), "by_action": by_action}


def load_picks(today: date | None = None) -> pd.DataFrame:
    today = today or date.today()
    if not config.PICKS_CSV.exists():
        return pd.DataFrame()
    picks = pd.read_csv(config.PICKS_CSV)
    return picks[(picks["bar_date"] < str(today)) & (picks["close"] > 0)]


def summary(today: date | None = None) -> dict:
    picks = load_picks(today)
    if not len(picks):
        return {"evaluated": 0, "note": "No picks old enough to evaluate yet — the track record starts after the first full trading day."}
    start = (pd.Timestamp(picks["bar_date"].min()) - timedelta(days=7)).date()
    hist = market.download_history(sorted(set(picks["ticker"])) + ["SPY"], start=str(start))
    return summarize(evaluate(picks, hist))


if __name__ == "__main__":
    picks = load_picks()
    if not len(picks):
        print("No picks old enough to evaluate yet.")
    else:
        start = (pd.Timestamp(picks["bar_date"].min()) - timedelta(days=7)).date()
        hist = market.download_history(sorted(set(picks["ticker"])) + ["SPY"], start=str(start))
        ev = evaluate(picks, hist)
        cols = ["date", "list", "ticker", "action", "composite", "close", "ret_1d", "ret_5d", "ret_10d", "xs_5d", "outcome"]
        with pd.option_context("display.width", 160, "display.float_format", "{:.3f}".format):
            print(ev[[c for c in cols if c in ev.columns]].to_string(index=False))
        print(summarize(ev))
