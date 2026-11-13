"""Deterministic component scores. Every scorer is pure (no network) and returns
(score 0–100 where 50 = neutral, [reasons]) so the digest/report can show *why*."""
from __future__ import annotations

import config


def clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:+.1f}%"


# ── Attention velocity (direction-neutral: how fast is buzz growing?) ─────────
def mention_ratio(mentions: int, baseline: float | None) -> float:
    return (mentions + 5) / ((baseline or 0) + 5)


def attention_score(ape: dict | None, st: dict | None, mover_screens: list[str],
                    baseline: float | None) -> tuple[float, list[str]]:
    s, why = 50.0, []
    if ape:
        base = baseline if baseline is not None else ape.get("mentions_24h_ago", 0)
        r = mention_ratio(ape.get("mentions", 0), base)
        label = "7-day avg" if baseline is not None else "24h ago"
        if r >= 3:
            s += 25
        elif r >= 2:
            s += 18
        elif r >= 1.3:
            s += 10
        elif r <= 0.5:
            s -= 15
        elif r <= 0.77:
            s -= 8
        why.append(f"Reddit mentions {ape.get('mentions', 0)} vs {base:.0f} ({label}) = {r:.1f}x")
        rank = ape.get("rank")
        if rank and rank <= 10:
            s += 10
            why.append(f"Reddit rank #{rank}")
        elif rank and rank <= 30:
            s += 5
            why.append(f"Reddit rank #{rank}")
    else:
        s -= 5
        why.append("not in Reddit top lists")
    if st:
        tr = st.get("trending_rank") or 99
        s += 10 if tr <= 10 else 5 if tr <= 30 else 0
        why.append(f"StockTwits trending #{tr}")
    if mover_screens:
        s += 5
        why.append("on " + "/".join(mover_screens))
    return clamp(s), why


# ── Technical setup (long-biased swing view) ────────────────────────────────
def technical_score(ind: dict) -> tuple[float, list[str]]:
    s, why = 50.0, []
    c, e20, e50 = ind.get("close"), ind.get("ema20"), ind.get("ema50")
    if c and e20 and e50:
        if c > e20 > e50:
            s += 15
            why.append("uptrend: price > EMA20 > EMA50")
        elif c > e20 and e20 <= e50:
            s += 5
            why.append("reclaiming EMA20 below EMA50")
        elif c < e20 < e50:
            s -= 15
            why.append("downtrend: price < EMA20 < EMA50")
        elif c < e20 and e20 >= e50:
            s -= 3
            why.append("pullback below EMA20 within uptrend")
    rsi = ind.get("rsi14")
    if rsi is not None:
        if 50 <= rsi <= 70:
            s += 10
        elif 45 <= rsi < 50:
            s += 3
        elif rsi > 80:
            s -= 10
        elif 30 <= rsi < 45:
            s -= 8
        elif rsi < 30:
            s -= 12
        why.append(f"RSI {rsi:.0f}")
    rv, ch = ind.get("rel_volume"), ind.get("change_1d")
    if rv is not None and ch is not None:
        if rv >= 2:
            s += 8 if ch > 0 else -8
            why.append(f"heavy volume {rv:.1f}x on {'up' if ch > 0 else 'down'} day")
        elif rv >= 1.5:
            s += 4 if ch > 0 else -4
            why.append(f"above-avg volume {rv:.1f}x")
    hi20 = ind.get("high20_prior")
    if c and hi20:
        if c > hi20:
            s += 10
            why.append("breakout above 20-day high")
        elif c >= hi20 * 0.97:
            s += 7
            why.append("within 3% of 20-day high")
    rs = ind.get("rs_20d")
    if rs is not None:
        s += 8 if rs > 0.05 else 4 if rs > 0 else -8 if rs < -0.05 else -4
        why.append(f"20d vs SPY {_pct(rs)}")
    gap = ind.get("gap")
    if gap is not None and abs(gap) >= 0.03:
        s += 3 if gap > 0 else -3
        why.append(f"gap {_pct(gap)}")
    return clamp(s), why


# ── Smart money & positioning ──────────────────────────────────────────────
def smart_money_score(info: dict, insiders: dict | None, options: dict | None) -> tuple[float, list[str]]:
    s, why = 50.0, []
    if insiders:
        if insiders["buys"]:
            s += 18 if insiders["buyers"] >= 2 else 12
            why.append(f"insider buying: {insiders['buyers']} insider(s), ${insiders['buy_value'] / 1e6:.1f}M")
        mcap = info.get("marketCap") or 0
        if insiders["sell_value"] and mcap and insiders["sell_value"] / mcap > 0.005:
            s -= 5
            why.append(f"heavy insider selling ${insiders['sell_value'] / 1e6:.0f}M")
    spf = info.get("shortPercentOfFloat")
    if spf is not None:
        if spf > 0.20:
            s -= 5
        elif spf > 0.10:
            s -= 2
        elif spf < 0.05:
            s += 3
        why.append(f"short {spf * 100:.1f}% of float")
    dtc = info.get("shortRatio")
    if dtc is not None and dtc > 7:
        s -= 3
        why.append(f"{dtc:.1f} days to cover")
    if options and options.get("pc_volume") is not None:
        pc = options["pc_volume"]
        s += 8 if pc < 0.5 else 4 if pc < 0.8 else 0 if pc <= 1.2 else -5 if pc <= 1.6 else -10
        why.append(f"put/call vol {pc:.2f}")
    inst = info.get("heldPercentInstitutions")
    if inst is not None:
        if 0.40 <= inst <= 0.90:
            s += 4
        elif inst < 0.15:
            s -= 4
        why.append(f"institutions {inst * 100:.0f}%")
    return clamp(s), why


# ── Prospects base (Claude adds ±15 from guidance/strategy in the news) ──────
def prospects_score(info: dict, analysts: dict | None) -> tuple[float, list[str]]:
    s, why = 50.0, []
    rg, eg = info.get("revenueGrowth"), info.get("earningsGrowth")
    if rg is not None:
        s += 12 if rg > 0.25 else 6 if rg > 0.10 else -8 if rg < 0 else 0
        why.append(f"revenue growth {_pct(rg)}")
    if eg is not None:
        s += 8 if eg > 0.25 else 4 if eg > 0.10 else -6 if eg < 0 else 0
        why.append(f"EPS growth {_pct(eg)}")
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    tgt, n = info.get("targetMeanPrice"), info.get("numberOfAnalystOpinions") or 0
    if price and tgt and n >= 3:
        up = tgt / price - 1
        s += 10 if up > 0.25 else 5 if up > 0.10 else -8 if up < -0.05 else 0
        why.append(f"analyst target {_pct(up)} ({n} analysts)")
    rm = info.get("recommendationMean")
    if rm is not None and n >= 3:
        s += 6 if rm <= 1.8 else 2 if rm <= 2.5 else -8 if rm >= 3.5 else -4 if rm >= 3.0 else 0
        why.append(f"rating mean {rm:.1f}")
    if analysts:
        net = analysts["upgrades"] - analysts["downgrades"]
        pt_net = analysts["pt_raised"] - analysts["pt_lowered"]
        s += max(-12, min(12, 4 * net)) + max(-6, min(6, 2 * pt_net))
        if analysts["upgrades"] or analysts["downgrades"] or analysts["pt_raised"] or analysts["pt_lowered"]:
            why.append(f"30d: {analysts['upgrades']} up/{analysts['downgrades']} down, "
                       f"PT {analysts['pt_raised']} raised/{analysts['pt_lowered']} lowered")
    return clamp(s), why


# ── Social base from StockTwits author tags (Claude refines it) ─────────────
def social_base(bull: int, bear: int) -> tuple[float, str]:
    labeled = bull + bear
    if labeled == 0:
        return 50.0, "no tagged StockTwits posts"
    raw = 20 + 60 * bull / labeled              # 0% bull -> 20, 100% bull -> 80
    shrink = labeled / (labeled + 5)            # few tagged posts -> pull toward neutral
    return clamp(50 + (raw - 50) * shrink), f"StockTwits {bull} bull / {bear} bear tagged"


# ── Risk flags ─────────────────────────────────────────────────────────────
def risk_flags(ind: dict, bull: int, bear: int, ape: dict | None, baseline: float | None,
               earnings: dict | None, market_cap: float | None) -> dict:
    rsi, c, e20, atr = ind.get("rsi14"), ind.get("close"), ind.get("ema20"), ind.get("atr14")
    bull_ratio = bull / (bull + bear) if (bull + bear) >= 5 else None
    stretched = bool(c and e20 and atr and (c - e20) > 3 * atr)
    euphoria = bool((rsi is not None and rsi > 80) or (stretched and bull_ratio is not None and bull_ratio > 0.85))
    spike = None
    if ape:
        base = baseline if baseline is not None else ape.get("mentions_24h_ago", 0)
        spike = mention_ratio(ape.get("mentions", 0), base)
    mention_spike = bool(spike and spike > 5)
    earn_days = earnings.get("trading_days") if earnings else None
    earnings_in_window = earn_days is not None and 0 <= earn_days <= config.EARNINGS_WINDOW_TRADING_DAYS
    ch = ind.get("change_1d") or 0
    pump_suspect = bool(mention_spike and (market_cap or 0) < 5e9 and abs(ch) > 0.20)
    return {
        "euphoria": euphoria,
        "stretched_vs_ema20": stretched,
        "mention_spike": mention_spike,
        "mention_ratio": spike,
        "earnings_in_window": earnings_in_window,
        "earnings_trading_days": earn_days,
        "pump_suspect": pump_suspect,
        "bull_ratio": bull_ratio,
    }


def newsworthiness(attention: float, change_1d: float | None, n_sources: int, is_mover: bool) -> float:
    """Shortlist ranking — deliberately direction-neutral so bearish stories survive for the avoid list."""
    return attention + 2 * min(abs(change_1d or 0) * 100, 15) + 10 * max(0, n_sources - 1) + (10 if is_mover else 0)
