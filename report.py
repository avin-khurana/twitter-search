"""Email-safe HTML report (inline styles only — Gmail strips <style> classes and all JavaScript)."""
from __future__ import annotations

from html import escape

import config
import setups

ACTION_STYLE = {
    "BUY": ("#0b6b2e", "#e3f4e8"),
    "HOLD": ("#7a5200", "#fff3d1"),
    "SELL": ("#a3241b", "#fde7e4"),
}
SETUP_STYLE = {
    setups.DRIFT: ("#0b6b2e", "#e3f4e8"),
    setups.DIP: ("#1a56db", "#e8effd"),
    setups.HYPE_FADE: ("#a3241b", "#fde7e4"),
    setups.HOPE_TRAP: ("#a3241b", "#fde7e4"),
}
VS_PRICE = {"aligned": "crowd and price agree", "crowd_bullish_price_falling": "crowd bullish while price falls",
            "crowd_bearish_price_rising": "crowd doubtful while price rises"}
STAGE = {"early": "story is early", "spreading": "story is spreading", "consensus": "everyone knows the story",
         "exhausted": "story is old"}
FONT = "font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
MUTED = "color:#5f6368;"
COMP_LABELS = [("social", "Social"), ("attention", "Attention"), ("catalyst", "Catalyst"),
               ("prospects", "Prospects"), ("technical", "Technical"), ("smart_money", "Smart money")]


def _e(x) -> str:
    return escape(str(x)) if x is not None else ""


def _pct(x, signed=True) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.1f}%" if signed else f"{x * 100:.1f}%"


def _badge(action: str) -> str:
    fg, bg = ACTION_STYLE.get(action, ("#333", "#eee"))
    return (f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;font-weight:700;'
            f'font-size:13px;color:{fg};background:{bg};">{_e(action)}</span>')


def _chip(text: str, fg="#5f6368", bg="#f1f3f4") -> str:
    return (f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:1px 8px;border-radius:10px;'
            f'font-size:12px;color:{fg};background:{bg};">{_e(text)}</span>')


def _setup_badge(r: dict) -> str:
    s = r.get("setup", setups.NONE)
    return _chip(r["setup_label"], *SETUP_STYLE[s]) if s in SETUP_STYLE else ""


def _crowd_text(r: dict) -> str:
    """'hope 4/5 · 13 bull / 1 bear tags · crowd bullish while price falls · everyone knows the story · last run: fear 3/5'"""
    j = r["judgment"] or {}
    if "crowd_emotion" not in j:
        return ""
    parts = [f"{j['crowd_emotion']} {j['emotion_intensity']}/5"]
    st = r.get("stocktwits") or {}
    if st.get("bull", 0) + st.get("bear", 0):
        parts.append(f"{st['bull']} bull / {st['bear']} bear tags")
    parts += [x for x in (VS_PRICE.get(j["crowd_vs_price"]), STAGE.get(j["narrative_stage"])) if x]
    prev = r.get("crowd_history") or {}
    if prev.get("crowd_emotion"):
        inten = f" {prev['emotion_intensity']}/5" if prev.get("emotion_intensity") else ""
        parts.append(f"last run ({prev['date']}): {prev['crowd_emotion']}{inten}")
    return " · ".join(parts)


def _crowd_div(r: dict) -> str:
    txt = _crowd_text(r)
    return f"<div style='{MUTED}font-size:13px;'><b>Crowd:</b> {_e(txt)}</div>" if txt else ""


def _setup_block(r: dict) -> str:
    if r.get("setup", setups.NONE) == setups.NONE:
        return ""
    also = f" Also: {', '.join(r['setup_confirmations'])}." if r["setup_confirmations"] else ""
    gate = f" <b>Not a buy yet:</b> {_e(r['gate_note'])}." if r.get("gate_note") else ""
    return (f"<div style='font-size:13px;margin-top:6px;'><b>{_e(r['setup_label'])}:</b> "
            f"{_e('; '.join(r['setup_reasons']))}.{_e(also)}{gate}</div>")


def _flags(r: dict) -> str:
    fl, chips = r["flags"], []
    if fl.get("earnings_in_window"):
        date = (r.get("earnings") or {}).get("date", "")
        chips.append(_chip(f"Earnings in {fl.get('earnings_trading_days')}d {date}", "#7a5200", "#fff3d1"))
    if fl.get("euphoria"):
        chips.append(_chip("Euphoria / extended", "#a3241b", "#fde7e4"))
    if fl.get("mention_spike"):
        chips.append(_chip(f"Mention spike {fl.get('mention_ratio', 0):.1f}x", "#1a56db", "#e8effd"))
    if r.get("pump"):
        chips.append(_chip("Pump/bot risk", "#a3241b", "#fde7e4"))
    return "".join(chips)


def _scores_line(r: dict) -> str:
    c = r["components"]
    parts = [f"{label} <b>{c[k]:.0f}</b>" for k, label in COMP_LABELS if k in c]
    pen = "".join(f" · <span style='color:#a3241b'>−{p} {_e(n)}</span>" for n, p in r["penalties"])
    return " · ".join(parts) + pen


def _levels(r: dict) -> str:
    lv = r["levels"]
    if not lv:
        return "Levels n/a (missing ATR)"
    head = {"SELL": "If shorting: ", "HOLD": "Watch-list levels: "}.get(r["action"], "")
    return (f"{head}Entry <b>{lv['entry']:.2f}</b> · Stop <b>{lv['stop']:.2f}</b> · Target <b>{lv['target']:.2f}</b> "
            f"· time stop {lv['time_stop_days']} trading days <span style='{MUTED}'>({_e(lv['note'])})</span>")


def _headline_links(r: dict, n: int = 2) -> str:
    items = []
    for h in r["headlines"][:n]:
        items.append(f'<a href="{_e(h["url"])}" style="color:#1a56db;text-decoration:none;">{_e(h["title"])}</a> '
                     f'<span style="{MUTED}">— {_e(h["source"])}</span>')
    return "<br>".join(items)


def _top_card(i: int, r: dict) -> str:
    j, ind = r["judgment"], r["indicators"]
    why = j["why_in_news"] if j else "AI judgment unavailable — " + "; ".join(r["why"].get("attention", [])[:2])
    heading = (f"<div style='{MUTED}font-size:13px;margin-top:4px;'><b>Where it's heading:</b> {_e(j['direction_summary'])}</div>"
               f"<div style='{MUTED}font-size:13px;'><b>Catalyst:</b> {_e(j['catalyst_type'])} · {_e(j['catalyst_direction'])}"
               f" · materiality {j['catalyst_materiality']}/5{' · new' if j['catalyst_is_new'] else ''}</div>") if j else ""
    return f"""
<tr><td style="padding:14px 16px;border-bottom:1px solid #e8eaed;">
  <div style="font-size:16px;"><span style="{MUTED}font-weight:600;">#{i}</span>
    <b style="font-size:18px;">{_e(r['ticker'])}</b> <span style="{MUTED}">{_e(r['name'])}</span>
    &nbsp;{_badge(r['action'])} {_setup_badge(r)}
    <span style="font-size:14px;"> Score <b>{r['composite']:.0f}</b> · {_e(r['confidence'])} confidence</span></div>
  <div style="font-size:14px;margin-top:6px;">{_e(why)}</div>
  {heading}
  {_crowd_div(r)}
  {_setup_block(r)}
  <div style="font-size:13px;margin-top:6px;">{_levels(r)}</div>
  <div style="font-size:12px;margin-top:6px;{MUTED}">Price {ind.get('close') or 0:.2f} ({_pct(ind.get('change_1d'))} 1d,
    {_pct(ind.get('ret_5d'))} 5d) · RSI {ind.get('rsi14') or 0:.0f} · {_scores_line(r)}</div>
  <div style="margin-top:4px;">{_flags(r)}</div>
  <div style="font-size:12px;margin-top:6px;">{_headline_links(r)}</div>
</td></tr>"""


def _avoid_row(r: dict) -> str:
    j = r["judgment"]
    why = j["why_in_news"] if j else "; ".join(r["why"].get("technical", [])[:2])
    return f"""
<tr><td style="padding:10px 16px;border-bottom:1px solid #e8eaed;font-size:14px;">
  <b>{_e(r['ticker'])}</b> <span style="{MUTED}">{_e(r['name'])}</span> &nbsp;{_badge(r['action'])} {_setup_badge(r)}
  <span> Score <b>{r['composite']:.0f}</b> · {_e(r['confidence'])} confidence</span>
  <div style="margin-top:4px;">{_e(why)}</div>
  {_crowd_div(r)}
  {_setup_block(r)}
  <div style="font-size:12px;margin-top:4px;{MUTED}">{_scores_line(r)}</div>
</td></tr>"""


def _full_table(rows: list[dict]) -> str:
    th = "padding:6px 6px;text-align:right;font-size:12px;border-bottom:2px solid #dadce0;"
    td = "padding:5px 6px;text-align:right;font-size:12px;border-bottom:1px solid #f1f3f4;"
    head = "".join(f'<th style="{th}">{h}</th>' for h in
                   ["Ticker", "Action", "Setup", "Crowd", "Score", "Social", "Attn", "Catal.", "Prosp.", "Tech",
                    "Smart", "1d"])
    body = []
    for r in sorted(rows, key=lambda x: (-x["composite"], x["ticker"])):
        c, ind, j = r["components"], r["indicators"], r["judgment"] or {}
        setup = r["setup_label"] if r.get("setup", setups.NONE) != setups.NONE else "–"
        crowd = f"{j['crowd_emotion']} {j['emotion_intensity']}" if "crowd_emotion" in j else "–"
        cells = [f"<b>{_e(r['ticker'])}</b>", r["action"], _e(setup), _e(crowd), f"{r['composite']:.0f}"]
        cells += [f"{c[k]:.0f}" if k in c else "–" for k, _ in COMP_LABELS]
        cells += [_pct(ind.get("change_1d"))]
        body.append("<tr>" + "".join(f'<td style="{td}">{x}</td>' for x in cells) + "</tr>")
    return (f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;">'
            f"<tr>{head}</tr>{''.join(body)}</table>")


def _track_table(first_col: str, items: list[tuple[str, dict]]) -> str:
    cell = "padding:4px 8px;"
    hdr = "".join(f"<th style='{cell}text-align:left;font-size:12px;{MUTED}'>{h}</th>"
                  for h in [first_col, "With 5d data", "Avg 5d return", "Right call", "Avg vs SPY", "Stop/target outcomes"])
    body = []
    for label_html, s in items:
        if not s["n"]:
            continue
        hit = "n/a" if s["hit_rate_5d"] is None else f"{s['hit_rate_5d'] * 100:.0f}%"
        outcomes = ", ".join(f"{k} {v}" for k, v in s["outcomes"].items()) or "–"
        body.append(f"<tr><td style='{cell}'>{label_html}</td><td style='{cell}'>{s['n']}</td>"
                    f"<td style='{cell}'>{_pct(s['avg_ret_5d'])}</td><td style='{cell}'>{hit}</td>"
                    f"<td style='{cell}'>{_pct(s['avg_excess_5d'])}</td><td style='{cell}'>{_e(outcomes)}</td></tr>")
    if not body:
        return ""
    return f"<table style='border-collapse:collapse;font-size:13px;margin-bottom:8px;'><tr>{hdr}</tr>{''.join(body)}</table>"


def _track(track: dict | None) -> str:
    if not track:
        return f"<p style='{MUTED}font-size:13px;'>Track record skipped.</p>"
    if track.get("error"):
        return f"<p style='{MUTED}font-size:13px;'>Track record unavailable: {_e(track['error'])}</p>"
    if not track.get("evaluated"):
        note = track.get("note", "Picks are being logged, but none has 5 trading days of history yet.")
        return f"<p style='{MUTED}font-size:13px;'>{_e(note)}</p>"
    by_setup = _track_table("Setup (all analyzed stocks)",
                            [(_chip(setups.LABELS[s], *SETUP_STYLE[s]), st) for s, st in track["by_setup"].items()])
    by_action = _track_table("Call (emailed lists)", [(_badge(a), st) for a, st in track["by_action"].items()])
    return (f"{by_setup}{by_action}"
            f"<p style='{MUTED}font-size:12px;'>{track['evaluated']} logged stocks have 5 trading days of history. "
            f"Right call = up after 5 days for BUY, HOLD, Drift and Overreaction dip; down after 5 days for SELL, "
            f"Hype fade and Hope trap.</p>")


def render(run: dict, rows: list[dict], top: list[dict], avoid: list[dict], warnings: list[dict],
           mode: str, mode_note: str, track: dict | None) -> str:
    rg = run["regime"]
    regime_line = _e(rg.get("label", ""))
    if rg.get("spy_close"):
        regime_line += f" · SPY {rg['spy_close']:.2f} vs EMA50 {rg['spy_ema50']:.2f} · VIX {rg['vix']:.1f}"
    banner = ""
    if mode != "full":
        banner = (f'<div style="margin:12px 0;padding:10px 14px;border-radius:8px;background:#fff3d1;color:#7a5200;'
                  f'font-size:14px;"><b>Numbers-only report.</b> {_e(mode_note)} Setups need the AI crowd read, '
                  f'so none are shown.</div>')
    health = "".join(f"<li><b>{_e(k)}</b>: {_e(v)}</li>" for k, v in run["health"].items())
    warn_html = ""
    if warnings:
        warn_html = ("<h3 style='font-size:15px;margin:22px 0 6px;'>Pump / bot warnings (excluded from ranking)</h3><p style='font-size:13px;'>"
                     + ", ".join(f"<b>{_e(r['ticker'])}</b> ({r['composite']:.0f})" for r in warnings) + "</p>")
    weak_note = (f" In a weak market a drift buy needs score ≥ {config.DRIFT_MIN_SCORE_WEAK} (normally "
                 f"{config.DRIFT_MIN_SCORE}) and a dip buy needs a crowd that has given up."
                 if rg.get("weak") else "")
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stock Buzz {_e(run['run_date'])}</title></head>
<body style="margin:0;padding:0;background:#f6f7f9;{FONT}color:#202124;">
<div style="max-width:780px;margin:0 auto;padding:16px;">
  <div style="background:#ffffff;border-radius:12px;padding:18px 18px 8px;border:1px solid #e8eaed;">
    <div style="font-size:22px;font-weight:700;">Stock Buzz — {_e(run['run_date'])}</div>
    <div style="{MUTED}font-size:13px;margin-top:4px;">Top {config.TOP_N} swing ideas (2–10 trading days) from Reddit,
      StockTwits and news buzz · {run['discovered']} tickers discovered → {run['eligible']} passed filters →
      {len(run['shortlist'])} analyzed</div>
    <div style="font-size:13px;margin-top:6px;"><b>Market:</b> {regime_line}.{_e(weak_note)}</div>
    {banner}
    <h3 style="font-size:16px;margin:18px 0 4px;">Top {len(top)}</h3>
    <table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;">{''.join(_top_card(i, r) for i, r in enumerate(top, 1))}</table>
    <h3 style="font-size:16px;margin:22px 0 4px;">Avoid / sell</h3>
    {('<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;">' + ''.join(_avoid_row(r) for r in avoid) + '</table>') if avoid else f"<p style='{MUTED}font-size:13px;'>Nothing scored low enough today.</p>"}
    {warn_html}
    <h3 style="font-size:15px;margin:22px 0 6px;">All analyzed tickers</h3>
    {_full_table(rows)}
    <h3 style="font-size:15px;margin:22px 0 6px;">Track record</h3>
    {_track(track)}
    <h3 style="font-size:15px;margin:22px 0 6px;">Data sources this run</h3>
    <ul style="font-size:12px;{MUTED}padding-left:18px;">{health}</ul>
    <p style="{MUTED}font-size:11px;line-height:1.5;margin-top:18px;"><b>Setups</b> compare what the crowd feels with what
      news and price are doing. <b>Drift:</b> new, material good news that price confirmed and the crowd isn't yet
      euphoric about. <b>Overreaction dip:</b> a sharp drop on news that isn't bad, bought only after a
      {config.DIP_TRIGGER_ATR:g}-ATR bounce (or a break of the last session's high). <b>Hype fade:</b> euphoria and a run-up with no confirmed news. <b>Hope trap:</b> falling price
      and bad news while the crowd stays bullish. A setup decides the call; stocks with no setup use the score
      (BUY ≥ {config.BUY_THRESHOLD}, or ≥ {config.BUY_THRESHOLD_WEAK_REGIME} in a weak market, with technical ≥
      {config.BUY_MIN_TECHNICAL}; SELL ≤ {config.SELL_THRESHOLD}). Score = social 20% · catalyst 20% · technical 20% ·
      prospects 15% · smart money 15% · attention 10%, minus penalties (euphoria −{config.EUPHORIA_PENALTY}, earnings
      inside the window −{config.EARNINGS_PENALTY}). Stops are {config.STOP_ATR_MULT}×ATR (or the 10-day low),
      targets {config.TARGET_R:.0f}R. The crowd read comes from StockTwits posts, whose users lean bullish by default.
      Experimental research output, not financial advice — judge each setup by its track record before trading on it.</p>
  </div>
</div></body></html>"""
