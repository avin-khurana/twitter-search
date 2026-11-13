"""Email-safe HTML report (inline styles only — Gmail strips <style> classes and all JavaScript)."""
from __future__ import annotations

from html import escape

import config

ACTION_STYLE = {
    "BUY": ("#0b6b2e", "#e3f4e8"),
    "HOLD": ("#7a5200", "#fff3d1"),
    "SELL": ("#a3241b", "#fde7e4"),
}
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
    &nbsp;{_badge(r['action'])}
    <span style="font-size:14px;"> Score <b>{r['composite']:.0f}</b> · {_e(r['confidence'])} confidence</span></div>
  <div style="font-size:14px;margin-top:6px;">{_e(why)}</div>
  {heading}
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
  <b>{_e(r['ticker'])}</b> <span style="{MUTED}">{_e(r['name'])}</span> &nbsp;{_badge(r['action'])}
  <span> Score <b>{r['composite']:.0f}</b></span>
  <div style="margin-top:4px;">{_e(why)}</div>
  <div style="font-size:12px;margin-top:4px;{MUTED}">{_scores_line(r)}</div>
</td></tr>"""


def _full_table(rows: list[dict]) -> str:
    th = "padding:6px 8px;text-align:right;font-size:12px;border-bottom:2px solid #dadce0;"
    td = "padding:5px 8px;text-align:right;font-size:12px;border-bottom:1px solid #f1f3f4;"
    head = "".join(f'<th style="{th}">{h}</th>' for h in
                   ["Ticker", "Action", "Score", "Conf.", "Social", "Attn", "Catal.", "Prosp.", "Tech", "Smart", "1d", "RSI"])
    body = []
    for r in sorted(rows, key=lambda x: (-x["composite"], x["ticker"])):
        c, ind = r["components"], r["indicators"]
        cells = [f"<b>{_e(r['ticker'])}</b>", r["action"], f"{r['composite']:.0f}", r["confidence"][0]]
        cells += [f"{c[k]:.0f}" if k in c else "–" for k, _ in COMP_LABELS]
        cells += [_pct(ind.get("change_1d")), f"{ind.get('rsi14') or 0:.0f}"]
        body.append("<tr>" + "".join(f'<td style="{td}">{x}</td>' for x in cells) + "</tr>")
    return (f'<table cellpadding="0" cellspacing="0" style="border-collapse:collapse;width:100%;">'
            f"<tr>{head}</tr>{''.join(body)}</table>")


def _track(track: dict | None) -> str:
    if not track:
        return f"<p style='{MUTED}font-size:13px;'>Track record skipped.</p>"
    if track.get("error"):
        return f"<p style='{MUTED}font-size:13px;'>Track record unavailable: {_e(track['error'])}</p>"
    if not track.get("evaluated"):
        return f"<p style='{MUTED}font-size:13px;'>{_e(track.get('note', 'No picks old enough to evaluate yet.'))}</p>"
    rows = []
    for action, s in track["by_action"].items():
        if not s["n"]:
            continue
        hit = "n/a" if s["hit_rate_5d"] is None else f"{s['hit_rate_5d'] * 100:.0f}%"
        outcomes = ", ".join(f"{k} {v}" for k, v in s["outcomes"].items()) or "–"
        rows.append(f"<tr><td style='padding:4px 8px;'>{_badge(action)}</td><td style='padding:4px 8px;'>{s['n']}</td>"
                    f"<td style='padding:4px 8px;'>{_pct(s['avg_ret_5d'])}</td><td style='padding:4px 8px;'>{hit}</td>"
                    f"<td style='padding:4px 8px;'>{_pct(s['avg_excess_5d'])}</td>"
                    f"<td style='padding:4px 8px;'>{_e(outcomes)}</td></tr>")
    hdr = "".join(f"<th style='padding:4px 8px;text-align:left;font-size:12px;{MUTED}'>{h}</th>"
                  for h in ["Call", "Picks w/ 5d data", "Avg 5d return", "Hit rate", "Avg vs SPY", "Stop/target outcomes"])
    return (f"<table style='border-collapse:collapse;font-size:13px;'><tr>{hdr}</tr>{''.join(rows)}</table>"
            f"<p style='{MUTED}font-size:12px;'>{track['evaluated']} logged picks evaluated. Hit rate = BUY/HOLD up after 5 "
            f"days, SELL down after 5 days.</p>")


def render(run: dict, rows: list[dict], top: list[dict], avoid: list[dict], warnings: list[dict],
           mode: str, mode_note: str, track: dict | None) -> str:
    rg = run["regime"]
    regime_line = _e(rg.get("label", ""))
    if rg.get("spy_close"):
        regime_line += f" · SPY {rg['spy_close']:.2f} vs EMA50 {rg['spy_ema50']:.2f} · VIX {rg['vix']:.1f}"
    banner = ""
    if mode != "full":
        banner = (f'<div style="margin:12px 0;padding:10px 14px;border-radius:8px;background:#fff3d1;color:#7a5200;'
                  f'font-size:14px;"><b>Numbers-only report.</b> {_e(mode_note)}</div>')
    health = "".join(f"<li><b>{_e(k)}</b>: {_e(v)}</li>" for k, v in run["health"].items())
    warn_html = ""
    if warnings:
        warn_html = ("<h3 style='font-size:15px;margin:22px 0 6px;'>Pump / bot warnings (excluded from ranking)</h3><p style='font-size:13px;'>"
                     + ", ".join(f"<b>{_e(r['ticker'])}</b> ({r['composite']:.0f})" for r in warnings) + "</p>")
    weak_note = (f" BUY needs score ≥ {config.BUY_THRESHOLD_WEAK_REGIME} (weak market) instead of {config.BUY_THRESHOLD}."
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
    <p style="{MUTED}font-size:11px;line-height:1.5;margin-top:18px;">Score = social 20% · catalyst 20% · technical 20% ·
      prospects 15% · smart money 15% · attention 10%, minus penalties (euphoria −{config.EUPHORIA_PENALTY}, earnings
      inside the window −{config.EARNINGS_PENALTY}). BUY ≥ {config.BUY_THRESHOLD} with technical ≥ {config.BUY_MIN_TECHNICAL};
      SELL ≤ {config.SELL_THRESHOLD} or a strongly bearish catalyst below EMA20. Stops are {config.STOP_ATR_MULT}×ATR (or the
      10-day low), targets {config.TARGET_R:.0f}R. Experimental research output, not financial advice — judge it by the
      track record before trading on it.</p>
  </div>
</div></body></html>"""
