"""Step 3: validate Claude's judgments -> scores -> behavioral setups -> BUY/HOLD/SELL + levels -> report, logs, email.

Usage:
  python finalize.py --validate-only --run-dir runs/<id>     # used by Claude to check its JSON
  python finalize.py --run-dir runs/<id> [--no-email] [--quant-only] [--no-track] [--no-log]
Without --run-dir the most recent run is used.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import config
import setups
from quant import clamp

CATALYST_TYPES = {"earnings", "guidance", "analyst", "m_and_a", "product", "contract", "regulatory", "legal",
                  "management", "macro_sector", "social_hype", "other", "none"}
DIRECTIONS = {"bullish", "bearish", "mixed", "none"}
ENUMS = {"catalyst_type": CATALYST_TYPES, "catalyst_direction": DIRECTIONS, "crowd_emotion": setups.EMOTIONS,
         "crowd_vs_price": setups.CROWD_VS_PRICE, "narrative_stage": setups.STAGES}
STR_LIMITS = {"why_in_news": 300, "direction_summary": 200, "key_evidence": 250}


# ── Validation ──────────────────────────────────────────────────────────────
def _int_errors(t: str, k: str, v, lo: int, hi: int) -> list[str]:
    if isinstance(v, bool) or not isinstance(v, int):
        return [f"{t}.{k}: must be an integer {lo}..{hi}, got {v!r}"]
    return [] if lo <= v <= hi else [f"{t}.{k}: {v} outside {lo}..{hi}"]


def validate(scores, shortlist: list[str]) -> list[str]:
    if not isinstance(scores, dict) or not isinstance(scores.get("tickers"), dict):
        return ['top level must be an object with a "tickers" object']
    tk = scores["tickers"]
    errors = [f"missing ticker {t}" for t in shortlist if t not in tk]
    errors += [f"unexpected ticker {t} (not in shortlist)" for t in tk if t not in shortlist]
    for t in shortlist:
        d = tk.get(t)
        if d is None:
            continue
        if not isinstance(d, dict):
            errors.append(f"{t}: must be an object")
            continue

        for k, limit in STR_LIMITS.items():
            v = d.get(k)
            if not isinstance(v, str) or not v.strip():
                errors.append(f"{t}.{k}: must be a non-empty string")
            elif len(v) > limit:
                errors.append(f"{t}.{k}: {len(v)} chars, max {limit}")
        for k, allowed in ENUMS.items():
            if d.get(k) not in allowed:
                errors.append(f"{t}.{k}: {d.get(k)!r} not in {sorted(allowed)}")
        lim = config.PROSPECTS_ADJ_LIMIT
        for k, lo, hi in (("catalyst_materiality", 1, 5), ("news_catalyst_score", 0, 100),
                          ("social_sentiment_score", 0, 100), ("prospects_adjustment", -lim, lim),
                          ("emotion_intensity", 1, 5)):
            errors += _int_errors(t, k, d.get(k), lo, hi)
        for k in ("catalyst_is_new", "pump_or_bot_flag"):
            if not isinstance(d.get(k), bool):
                errors.append(f"{t}.{k}: must be true/false")
    return errors


# ── Scoring ─────────────────────────────────────────────────────────────────
def composite_score(components: dict[str, float]) -> float:
    """Weighted average over the components present; missing ones are reweighted away."""
    w = {k: config.WEIGHTS[k] for k in components}
    return sum(w[k] * components[k] for k in components) / sum(w.values())


def decide_action(composite: float, technical: float, catalyst: float | None, close: float | None,
                  ema20: float | None, pump: bool, weak_regime: bool) -> str:
    """Score-threshold call, used when a stock fits none of the behavioral setups."""
    if composite <= config.SELL_THRESHOLD:
        return "SELL"
    if (catalyst is not None and catalyst <= config.SELL_BEARISH_CATALYST_MAX
            and close is not None and ema20 is not None and close < ema20):
        return "SELL"
    buy_th = config.BUY_THRESHOLD_WEAK_REGIME if weak_regime else config.BUY_THRESHOLD
    if composite >= buy_th and technical >= config.BUY_MIN_TECHNICAL and not pump:
        return "BUY"
    return "HOLD"


def decide_setup_action(setup: str, default_action: str, composite: float, ind: dict, emotion: str | None,
                        pump: bool, weak_regime: bool) -> tuple[str, str]:
    """A behavioral setup overrides the score thresholds. Returns (action, why a long setup is not a BUY)."""
    if setup == setups.NONE:
        return default_action, ""
    if setup in setups.AVOID_SETUPS:
        return "SELL", ""
    if pump:
        return "HOLD", "posts look coordinated, so not a buy"
    close, ema20 = ind.get("close"), ind.get("ema20")
    if setup == setups.DRIFT:
        floor = config.DRIFT_MIN_SCORE_WEAK if weak_regime else config.DRIFT_MIN_SCORE
        if composite < floor:
            return "HOLD", f"score {composite:.0f} is below the {floor} a drift buy needs" + (
                " in a weak market" if weak_regime else "")
        if close and ema20 and close < ema20:
            return "HOLD", "still below its 20-day average, so earlier buyers are likely to sell into the bounce"
        return "BUY", ""
    if weak_regime and emotion not in setups.GIVEN_UP_EMOTIONS:   # overreaction dip
        return "HOLD", "the market is weak and the crowd hasn't given up yet, so watch the trigger but don't pre-empt it"
    return "BUY", ""


def confidence(components: dict[str, float], composite: float) -> str:
    side = 1 if composite >= 50 else -1
    agree = sum(1 for v in components.values() if (v - 50) * side > 0) / len(components)
    complete = len(components) / len(config.WEIGHTS)
    dist = abs(composite - 50)
    if agree >= 0.67 and complete >= 0.99 and dist >= 15:
        return "High"
    if agree >= 0.5 and complete >= 0.8 and dist >= 7:
        return "Medium"
    return "Low"


def setup_confidence(setup: str, n_confirmations: int, weak_regime: bool) -> str:
    """Confidence of a setup call = how many extra confirmations it has; long setups lose one in a weak market."""
    n = n_confirmations - (1 if setup in setups.LONG_SETUPS and weak_regime else 0)
    return "High" if n >= 3 else "Medium" if n >= 2 else "Low"


def trade_levels(action: str, ind: dict, setup: str = setups.NONE) -> dict | None:
    close, atr, ema20, low10 = ind.get("close"), ind.get("atr14"), ind.get("ema20"), ind.get("low10")
    if not close or not atr:
        return None
    base = {"time_stop_days": config.TIME_STOP_DAYS}
    if action == "SELL":
        stop = close + config.STOP_ATR_MULT * atr
        return {**base, "side": "short", "entry_type": "market", "entry": close, "stop": stop,
                "target": close - config.TARGET_R * (stop - close),
                "note": "Exit longs. Only if shorting/buying puts: stop above, target below."}
    if setup == setups.DIP:
        # Don't catch the falling knife: buy only once price bounces 1 ATR off the close
        # (or clears the last session's high, if that is nearer). Stop under the last session's low.
        bounce = close + config.DIP_TRIGGER_ATR * atr
        high = ind.get("high") or bounce
        entry = min(high, bounce)
        risk = entry - (ind.get("low") or (entry - atr))
        risk = min(max(risk, config.DIP_MIN_RISK_ATR * atr), config.DIP_MAX_RISK_ATR * atr)
        what = "the last session's high" if high <= bounce else f"a {config.DIP_TRIGGER_ATR:g}-ATR bounce off the close"
        return {**base, "side": "long", "entry_type": "stop", "entry": entry, "stop": entry - risk,
                "target": entry + config.TARGET_R * risk,
                "note": f"Buy only if it trades above {entry:.2f} ({what}), which shows buyers are back"}
    extended = bool(ema20 and (close - ema20) > config.EXTENDED_ATR * atr)
    # Extended: buy a ~1 ATR pullback (never below EMA20) rather than chasing, or waiting for a full EMA20 retest
    entry = max(ema20, close - config.EXTENDED_ATR * atr) if extended else close
    stop = entry - config.STOP_ATR_MULT * atr
    if low10 and low10 > stop and (entry - low10) >= config.MIN_STOP_ATR * atr:
        stop = low10
    return {**base, "side": "long", "entry_type": "limit" if extended else "market", "entry": entry, "stop": stop,
            "target": entry + config.TARGET_R * (entry - stop),
            "note": f"Extended {(close - ema20) / atr:.1f} ATR above EMA20 — buy a pullback, don't chase" if extended
            else "Near last close"}


def euphoria_flag(fl: dict, ind: dict, judgment: dict | None) -> bool:
    """RSI above 80 always counts. A stretched price counts only if the crowd is euphoric: by Claude's read
    of the posts when there is one, otherwise by the bull-tag ratio (the flag set at collect time).
    StockTwits tags lean bullish, so tags alone would penalize every strong move on real news."""
    if not judgment or "crowd_emotion" not in judgment:
        return bool(fl.get("euphoria"))
    return (ind.get("rsi14") or 0) > 80 or (bool(fl.get("stretched_vs_ema20"))
                                            and judgment["crowd_emotion"] == "euphoria")


def score_ticker(t: dict, judgment: dict | None, weak_regime: bool) -> dict:
    q, ind = t["quant"], t["indicators"]
    fl = dict(t["flags"], euphoria=euphoria_flag(t["flags"], ind, judgment))
    comps = {"attention": q["attention"], "technical": q["technical"], "smart_money": q["smart_money"]}
    if judgment:
        comps["social"] = float(judgment["social_sentiment_score"])
        comps["catalyst"] = float(judgment["news_catalyst_score"])
        comps["prospects"] = clamp(q["prospects_base"] + judgment["prospects_adjustment"])
        pump = bool(judgment["pump_or_bot_flag"])
    else:
        comps["social"] = q["social_base"]
        comps["prospects"] = q["prospects_base"]
        pump = bool(fl.get("pump_suspect"))
    raw = composite_score(comps)
    penalties = []
    if fl.get("euphoria"):
        penalties.append(("euphoria", config.EUPHORIA_PENALTY))
    if fl.get("earnings_in_window"):
        penalties.append(("earnings in window", config.EARNINGS_PENALTY))
    composite = round(clamp(raw - sum(p for _, p in penalties)), 1)

    default = decide_action(composite, comps["technical"], comps.get("catalyst"), ind.get("close"),
                            ind.get("ema20"), pump, weak_regime)
    s = setups.classify(dict(t, flags=fl), judgment, comps["prospects"])
    setup = s["setup"]
    action, gate_note = decide_setup_action(setup, default, composite, ind, (judgment or {}).get("crowd_emotion"),
                                            pump, weak_regime)
    conf = (confidence(comps, composite) if setup == setups.NONE
            else setup_confidence(setup, len(s["confirmations"]), weak_regime))
    return {
        "ticker": t["ticker"], "name": t["name"], "sector": t.get("sector"),
        "components": {k: round(v, 1) for k, v in comps.items()},
        "raw": round(raw, 1), "penalties": penalties, "composite": composite,
        "action": action, "confidence": conf, "pump": pump,
        "setup": setup, "setup_label": setups.LABELS[setup], "setup_reasons": s["reasons"],
        "setup_confirmations": s["confirmations"], "gate_note": gate_note,
        "levels": trade_levels(action, ind, setup), "indicators": ind, "flags": fl,
        "judgment": judgment, "why": t.get("why", {}), "headlines": t.get("headlines", [])[:3],
        "earnings": t.get("earnings"), "stocktwits": t.get("stocktwits") or {},
        "crowd_history": t.get("crowd_history"),
    }


def has_real_catalyst(r: dict) -> bool:
    """Top-5 names must be in the news for a reason. Without AI judgment we can't tell, so allow all."""
    j = r.get("judgment")
    return j is None or (j["catalyst_type"] != "none" and j["catalyst_materiality"] >= config.TOP_MIN_MATERIALITY)


def rank(rows: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """(top N long ideas, avoid list, pump warnings).
    Top: BUYs first, then long setups still waiting (HOLD), then other HOLDs — each by score. SELLs,
    pumps and buzz-without-news never make the top list."""
    ordered = sorted(rows, key=lambda r: (-r["composite"], r["ticker"]))
    clean = [r for r in ordered if not r["pump"]]

    def tier(r: dict) -> int:
        if r["action"] == "BUY":
            return 0
        return 1 if r.get("setup") in setups.LONG_SETUPS else 2

    longs = [r for r in clean if r["action"] != "SELL" and has_real_catalyst(r)]
    top = sorted(longs, key=lambda r: (tier(r), -r["composite"], r["ticker"]))[: config.TOP_N]
    top_set = {r["ticker"] for r in top}
    rest = [r for r in reversed(clean) if r["ticker"] not in top_set]          # lowest composite first
    avoid = [r for r in rest if r["action"] == "SELL"][: config.AVOID_N]
    if len(avoid) < config.AVOID_N:
        avoid_set = {r["ticker"] for r in avoid}
        avoid += [r for r in rest if r["ticker"] not in avoid_set and r["composite"] < 45][: config.AVOID_N - len(avoid)]
    return top, avoid, [r for r in ordered if r["pump"]]


# ── Persistence ─────────────────────────────────────────────────────────────
PICK_COLS = ["date", "run_id", "list", "rank", "ticker", "action", "setup", "composite", "confidence", "mode",
             "bar_date", "close", "entry_type", "entry", "stop", "target"]
SENTIMENT_COLS = ["date", "ticker", "bull", "bear", "messages", "bull_ratio", "social_score", "crowd_emotion",
                  "emotion_intensity", "crowd_vs_price", "narrative_stage", "setup", "action", "composite", "close"]


def _replace_date_rows(path: Path, date: str, new_rows: list[dict], cols: list[str]) -> None:
    """Idempotent daily log: drop any rows already written for `date`, then append the new ones."""
    path.parent.mkdir(parents=True, exist_ok=True)
    old = pd.read_csv(path, dtype=str, keep_default_na=False) if path.exists() else pd.DataFrame(columns=cols)
    old = old[old["date"] != date]
    new = pd.DataFrame(new_rows, columns=cols).astype(str)
    out = pd.concat([old, new], ignore_index=True) if len(old) else new
    out.reindex(columns=cols).fillna("").sort_values(["date"], kind="stable").to_csv(path, index=False)


def save_picks(run: dict, rows: list[dict], top: list[dict], avoid: list[dict], mode: str) -> None:
    """Log every analyzed stock (not just the lists) so each setup builds its own track record."""
    place = {r["ticker"]: ("top", i) for i, r in enumerate(top, 1)}
    place.update({r["ticker"]: ("avoid", i) for i, r in enumerate(avoid, 1)})
    out = []
    for r in rows:
        lst, rk = place.get(r["ticker"], ("other", ""))
        lv, ind = r["levels"] or {}, r["indicators"]
        out.append({"date": run["run_date"], "run_id": run["run_id"], "list": lst, "rank": rk,
                    "ticker": r["ticker"], "action": r["action"], "setup": r["setup"], "composite": r["composite"],
                    "confidence": r["confidence"], "mode": mode, "bar_date": ind.get("bar_date"),
                    "close": round(ind.get("close") or 0, 4), "entry_type": lv.get("entry_type", ""),
                    "entry": round(lv.get("entry") or 0, 4), "stop": round(lv.get("stop") or 0, 4),
                    "target": round(lv.get("target") or 0, 4)})
    out.sort(key=lambda x: ({"top": 0, "avoid": 1, "other": 2}[x["list"]], x["rank"] or 0, x["ticker"]))
    _replace_date_rows(config.PICKS_CSV, run["run_date"], out, PICK_COLS)


def save_sentiment(run: dict, rows: list[dict]) -> None:
    """Daily crowd read per stock, so later runs can see sentiment changing."""
    out = []
    for r in rows:
        st, j = r["stocktwits"], r["judgment"] or {}
        bull, bear = st.get("bull", 0), st.get("bear", 0)
        out.append({"date": run["run_date"], "ticker": r["ticker"], "bull": bull, "bear": bear,
                    "messages": st.get("messages", 0),
                    "bull_ratio": round(bull / (bull + bear), 3) if bull + bear else "",
                    "social_score": r["components"].get("social", ""),
                    "crowd_emotion": j.get("crowd_emotion", ""), "emotion_intensity": j.get("emotion_intensity", ""),
                    "crowd_vs_price": j.get("crowd_vs_price", ""), "narrative_stage": j.get("narrative_stage", ""),
                    "setup": r["setup"], "action": r["action"], "composite": r["composite"],
                    "close": round(r["indicators"].get("close") or 0, 4)})
    _replace_date_rows(config.SENTIMENT_CSV, run["run_date"], out, SENTIMENT_COLS)


def save_mentions(run: dict) -> None:
    rows = [{"date": run["run_date"], **r} for r in run.get("ape_snapshot", [])]
    if rows:
        _replace_date_rows(config.MENTIONS_CSV, run["run_date"], rows, ["date", "ticker", "rank", "mentions", "upvotes"])


# ── Output ──────────────────────────────────────────────────────────────────
def subject_line(run: dict, top: list[dict], avoid: list[dict], mode: str) -> str:
    d = datetime.strptime(run["run_date"], "%Y-%m-%d").strftime("%a %b %-d")
    n_buy = sum(1 for r in top if r["action"] == "BUY")
    s = f"Stock Buzz — {d}: {n_buy} BUY / {len(top) - n_buy} HOLD · {len(avoid)} to avoid"
    return s + (" (numbers-only)" if mode != "full" else "")


def markdown_summary(top: list[dict], avoid: list[dict], warnings: list[dict]) -> str:
    def lv(r):
        x = r["levels"]
        return f"{x['entry']:.2f} / {x['stop']:.2f} / {x['target']:.2f}" if x else "n/a"

    def why(r):
        j = r["judgment"]
        return (j["why_in_news"] if j else "; ".join(r["why"].get("attention", [])[:2])).replace("|", "/")

    def crowd(r):
        j = r["judgment"] or {}
        return f"{j['crowd_emotion']} {j['emotion_intensity']}/5" if "crowd_emotion" in j else "n/a"

    lines = ["| # | Ticker | Action | Setup | Crowd | Score | Conf. | Entry / Stop / Target | Why in the news |",
             "|---|---|---|---|---|---|---|---|---|"]
    lines += [f"| {i} | {r['ticker']} | {r['action']} | {r['setup_label']} | {crowd(r)} | {r['composite']:.0f} | "
              f"{r['confidence']} | {lv(r)} | {why(r)} |" for i, r in enumerate(top, 1)]
    if avoid:
        lines += ["", "**Avoid / sell:**"]
        lines += [f"- {r['ticker']} ({r['action']}, {r['setup_label']}, crowd {crowd(r)}, score {r['composite']:.0f}) — {why(r)}"
                  for r in avoid]
    if warnings:
        lines += ["", "**Pump/bot warnings (excluded):** " + ", ".join(r["ticker"] for r in warnings)]
    return "\n".join(lines)


def latest_run_dir() -> Path:
    runs = sorted(config.RUNS_DIR.glob("*/candidates.json"), key=lambda p: p.stat().st_mtime)
    if not runs:
        sys.exit("No runs found — run collect.py first")
    return runs[-1].parent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-dir")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--quant-only", action="store_true", help="ignore claude_scores.json")
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--no-track", action="store_true", help="skip the track-record lookup (no network)")
    ap.add_argument("--no-log", action="store_true",
                    help="ad-hoc run: don't touch data/ or reports/ (keeps the daily track record clean)")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir) if args.run_dir else latest_run_dir()
    run = json.loads((run_dir / "candidates.json").read_text())
    scores_path = run_dir / "claude_scores.json"

    judgments, mode, mode_note = {}, "quant-only", ""
    if args.validate_only or not args.quant_only:
        if scores_path.exists():
            try:
                scores = json.loads(scores_path.read_text())
                errors = validate(scores, run["shortlist"])
            except json.JSONDecodeError as e:
                errors = [f"invalid JSON: {e}"]
        else:
            errors = [f"{scores_path.name} not found"]
        if args.validate_only:
            if errors:
                print("INVALID")
                print("\n".join(f"- {e}" for e in errors))
                return 1
            print(f"VALID ({len(run['shortlist'])} tickers)")
            return 0
        if errors:
            mode_note = f"AI judgment unavailable ({errors[0]}{' …' if len(errors) > 1 else ''}) — numbers-only ranking."
            print(f"WARNING: {mode_note}")
        else:
            judgments, mode = scores["tickers"], "full"
    else:
        mode_note = "Run with --quant-only — numbers-only ranking."

    weak = bool(run["regime"].get("weak"))
    rows = [score_ticker(run["tickers"][t], judgments.get(t), weak) for t in run["shortlist"]]
    top, avoid, warnings = rank(rows)

    track = None
    if not args.no_track:
        try:
            import track as track_mod
            track = track_mod.summary()
        except Exception as e:
            track = {"error": f"{type(e).__name__}: {e}"}

    import report
    html = report.render(run, rows, top, avoid, warnings, mode, mode_note, track)
    (run_dir / "report.html").write_text(html)
    if not args.no_log:
        config.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        (config.REPORTS_DIR / f"{run['run_date']}.html").write_text(html)
    (run_dir / "result.json").write_text(json.dumps(
        {"mode": mode, "top": [r["ticker"] for r in top], "avoid": [r["ticker"] for r in avoid],
         "rows": [{k: r[k] for k in ("ticker", "composite", "action", "setup", "setup_reasons",
                                     "setup_confirmations", "gate_note", "confidence", "components",
                                     "penalties", "levels", "pump")} for r in rows]}, indent=2, default=str))
    if not args.no_log:
        save_picks(run, rows, top, avoid, mode)
        save_sentiment(run, rows)
        save_mentions(run)

    subject = subject_line(run, top, avoid, mode)
    summary = markdown_summary(top, avoid, warnings)
    print(f"\n{subject}\n\n{summary}\n\nReport: {run_dir / 'report.html'}")

    if not args.no_email:
        import notify
        sent = notify.send_email(subject, html)
        notify.send_telegram(f"<b>{subject}</b>\n" + "\n".join(
            f"{i}. {r['ticker']} {r['action']} · {r['setup_label']} ({r['composite']:.0f})"
            for i, r in enumerate(top, 1)))
        if not sent and config.EMAIL_FROM:
            return 2  # email configured but failed — surface it in CI
    return 0


if __name__ == "__main__":
    sys.exit(main())
