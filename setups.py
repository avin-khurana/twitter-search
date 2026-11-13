"""Behavioral setups: classify each stock by the gap between what the crowd feels and what the
news and price are actually doing. Pure functions — inputs are Claude's crowd labels plus the
numeric snapshot. Thresholds live in config.py.

  drift            people underreact to real good news and catch up over days        -> buy
  overreaction_dip panic selling on news that is not actually bad                    -> buy on a trigger
  hype_fade        euphoria and herding with no confirmed news behind the move       -> avoid / sell
  hope_trap        falling price and bad news while the crowd stays bullish          -> avoid / sell
"""
from __future__ import annotations

import config

DRIFT, DIP, HYPE_FADE, HOPE_TRAP, NONE = "drift", "overreaction_dip", "hype_fade", "hope_trap", "none"
LABELS = {DRIFT: "Drift", DIP: "Overreaction dip", HYPE_FADE: "Hype fade", HOPE_TRAP: "Hope trap", NONE: "No setup"}
LONG_SETUPS = {DRIFT, DIP}
AVOID_SETUPS = {HYPE_FADE, HOPE_TRAP}

EMOTIONS = {"euphoria", "optimism", "hope", "fear", "panic", "anger", "apathy", "mixed"}
CROWD_VS_PRICE = {"aligned", "crowd_bullish_price_falling", "crowd_bearish_price_rising", "unclear"}
STAGES = {"early", "spreading", "consensus", "exhausted", "none"}
BULLISH_EMOTIONS = {"euphoria", "optimism", "hope"}
GIVEN_UP_EMOTIONS = {"fear", "panic", "anger"}
ADJECTIVE = {"euphoria": "euphoric", "optimism": "optimistic", "hope": "hopeful", "fear": "fearful",
             "panic": "panicking", "anger": "angry", "apathy": "indifferent", "mixed": "split"}


def _n(x, default: float = 0.0) -> float:
    return default if x is None else x


def _pct(x: float) -> str:
    return f"{x * 100:+.1f}%"


def classify(t: dict, j: dict | None, prospects: float) -> dict:
    """Returns {"setup", "reasons", "confirmations"}. Needs Claude's crowd labels; without them there is no setup.
    `confirmations` are extra supporting facts — they set the confidence, not the setup itself."""
    out = {"setup": NONE, "reasons": [], "confirmations": []}
    if not j or "crowd_emotion" not in j:
        return out
    ind, fl = t["indicators"], t["flags"]
    close, ema20, ema50 = ind.get("close"), ind.get("ema20"), ind.get("ema50")
    ch1, gap = _n(ind.get("change_1d")), _n(ind.get("gap"))
    r5, r20 = _n(ind.get("ret_5d")), _n(ind.get("ret_20d"))
    relvol, rsi = _n(ind.get("rel_volume")), _n(ind.get("rsi14"))
    atr_pct = ind.get("atr_pct") or 0.03
    br = fl.get("bull_ratio")                       # None when fewer than 5 tagged posts
    emotion, intensity = j["crowd_emotion"], j["emotion_intensity"]
    direction, mat, news = j["catalyst_direction"], j["catalyst_materiality"], j["news_catalyst_score"]
    ctype, stage, pump = j["catalyst_type"], j["narrative_stage"], j["pump_or_bot_flag"]
    below20 = bool(close and ema20 and close < ema20)
    tags = f" ({br:.0%} of tagged posts bullish)" if br is not None else ""

    crowd_hot = emotion == "euphoria" and (intensity >= config.HYPE_MIN_INTENSITY
                                           or (br is not None and br >= config.HYPE_BULL_RATIO))
    crowd_bullish = (emotion in BULLISH_EMOTIONS or j["crowd_vs_price"] == "crowd_bullish_price_falling"
                     or (br is not None and br >= config.HOPE_BULL_RATIO))

    # ── Hope trap ──
    downtrend = below20 and (r20 <= -config.HOPE_MIN_DROP_20D or r5 <= -config.HOPE_MIN_DROP_5D)
    bad_news = (direction == "bearish" and mat >= 3) or news <= config.HOPE_MAX_NEWS
    if downtrend and bad_news and crowd_bullish:
        conf = []
        if mat >= 4:
            conf.append("major bad news")
        if emotion == "hope" and intensity >= 4:
            conf.append("strong denial in the posts")
        if br is not None and br >= 0.85:
            conf.append("almost no bears left")
        if r20 <= -0.20 and ema50 and close < ema50:
            conf.append("deep downtrend")
        an = t.get("analysts") or {}
        if an.get("downgrades", 0) >= 2 or an.get("pt_lowered", 0) >= 5:
            conf.append("analysts are cutting")
        return {"setup": HOPE_TRAP, "confirmations": conf, "reasons": [
            f"price is falling ({_pct(r20)} over 20 days, below its 20-day average)",
            f"the news is bad ({ctype}, {direction}, materiality {mat}/5)",
            (f"but the crowd is still {ADJECTIVE[emotion]}{tags}" if emotion in BULLISH_EMOTIONS
             else f"but most tagged posts are still bullish{tags}")]}

    # ── Hype fade ──
    thin_news = ctype in ("none", "social_hype") or mat <= 2 or pump
    run_up = ch1 >= 0.05 or r5 >= 0.10 or bool(fl.get("stretched_vs_ema20")) or rsi >= 70
    if crowd_hot and run_up and (thin_news or fl.get("euphoria")):
        conf = []
        if intensity == 5:
            conf.append("extreme euphoria")
        if fl.get("euphoria"):
            conf.append("price stretched far above its 20-day average")
        if fl.get("mention_spike"):
            conf.append("mention spike")
        if pump:
            conf.append("posts look coordinated")
        if stage in ("consensus", "exhausted"):
            conf.append("everyone already knows the story")
        return {"setup": HYPE_FADE, "confirmations": conf, "reasons": [
            f"the crowd is euphoric (intensity {intensity}/5){tags}",
            f"price has already run ({_pct(ch1)} today, {_pct(r5)} over 5 days)",
            "no confirmed news behind it" if thin_news else "the move is stretched even with real news"]}

    # ── Drift ──
    good_news = direction == "bullish" and mat >= 3 and j["catalyst_is_new"]
    confirmed = ((max(ch1, gap) >= config.DRIFT_MIN_MOVE and relvol >= config.DRIFT_MIN_REL_VOLUME)
                 or (r5 >= config.DRIFT_MIN_5D and ch1 > -0.02))
    if good_news and confirmed and not crowd_hot and stage != "exhausted" and not pump:
        conf = []
        if mat >= 4:
            conf.append("major news")
        if relvol >= 1.5:
            conf.append(f"heavy volume ({relvol:.1f}x)")
        if close and ema50 and close > ema50:
            conf.append("above its 50-day average")
        if stage == "early" or j["crowd_vs_price"] == "crowd_bearish_price_rising":
            conf.append("the crowd hasn't caught on yet")
        return {"setup": DRIFT, "confirmations": conf, "reasons": [
            f"new, material good news ({ctype}, materiality {mat}/5)",
            f"price confirmed it ({_pct(ch1)} today, {_pct(r5)} over 5 days, {relvol:.1f}x volume)",
            f"the crowd is {ADJECTIVE[emotion]}, not euphoric"]}

    # ── Overreaction dip ──
    sharp_1d = -ch1 >= max(config.DIP_MIN_DROP, config.DIP_ATR_MULT * atr_pct)
    sharp_5d = -r5 >= max(config.DIP_MIN_DROP_5D, config.DIP_ATR_MULT_5D * atr_pct)
    news_ok = direction != "bearish" and news >= config.DIP_MIN_NEWS
    if ((sharp_1d or sharp_5d) and r5 <= config.DIP_MAX_PRIOR_RUN and news_ok
            and prospects >= config.DIP_MIN_PROSPECTS and not pump):
        conf = []
        if emotion in GIVEN_UP_EMOTIONS:
            conf.append(f"the crowd has given up ({emotion})")
        if direction == "bullish":
            conf.append("the news was actually good")
        if -ch1 >= 2.5 * atr_pct:
            conf.append("unusually large drop")
        if prospects >= 70:
            conf.append("strong business outlook")
        if (t.get("insiders") or {}).get("buys"):
            conf.append("insiders are buying")
        return {"setup": DIP, "confirmations": conf, "reasons": [
            f"sharp drop ({_pct(ch1)} today, {_pct(r5)} over 5 days)",
            f"but the news isn't bad ({ctype}, {direction}, catalyst score {news})",
            f"and the business outlook is solid (prospects {prospects:.0f})"]}
    return out
