import copy

import pytest

import config
import finalize as fz


def judgment(**over):
    j = {"why_in_news": "Reason.", "catalyst_type": "earnings", "catalyst_direction": "bullish",
         "catalyst_materiality": 3, "catalyst_is_new": True, "news_catalyst_score": 70,
         "social_sentiment_score": 60, "prospects_adjustment": 5, "direction_summary": "Growing.",
         "pump_or_bot_flag": False, "key_evidence": "Headline."}
    j.update(over)
    return j


def ticker(t="AAA", **flags):
    fl = {"euphoria": False, "earnings_in_window": False, "pump_suspect": False, "mention_spike": False}
    fl.update(flags)
    return {"ticker": t, "name": f"{t} Inc", "sector": "Tech",
            "quant": {"attention": 70, "technical": 70, "smart_money": 60, "prospects_base": 65, "social_base": 55},
            "flags": fl, "indicators": {"close": 100.0, "atr14": 4.0, "ema20": 98.0, "low10": 95.0, "bar_date": "2026-11-13"},
            "why": {"attention": ["x"]}, "headlines": []}


# ── composite ──
def test_composite_reweights_missing_components():
    comps = {"social": 60, "attention": 80, "technical": 50, "smart_money": 40, "prospects": 70}  # no catalyst
    w = {k: config.WEIGHTS[k] for k in comps}
    expected = sum(w[k] * comps[k] for k in comps) / sum(w.values())
    assert fz.composite_score(comps) == pytest.approx(expected)
    full = dict(comps, catalyst=50)
    assert fz.composite_score(full) == pytest.approx(sum(config.WEIGHTS[k] * full[k] for k in full))


def test_score_ticker_full_and_penalties():
    r = fz.score_ticker(ticker(), judgment(), weak_regime=False)
    c = r["components"]
    assert c["catalyst"] == 70 and c["social"] == 60 and c["prospects"] == 70
    raw = sum(config.WEIGHTS[k] * c[k] for k in c)
    assert r["composite"] == pytest.approx(round(raw, 1))
    pen = fz.score_ticker(ticker(euphoria=True, earnings_in_window=True), judgment(), weak_regime=False)
    assert pen["composite"] == pytest.approx(round(raw - config.EUPHORIA_PENALTY - config.EARNINGS_PENALTY, 1))


def test_score_ticker_quant_only_uses_social_base_and_drops_catalyst():
    r = fz.score_ticker(ticker(pump_suspect=True), None, weak_regime=False)
    assert "catalyst" not in r["components"]
    assert r["components"]["social"] == 55 and r["components"]["prospects"] == 65
    assert r["pump"] is True


def test_prospects_adjustment_is_clamped():
    t = ticker()
    t["quant"]["prospects_base"] = 95
    r = fz.score_ticker(t, judgment(prospects_adjustment=15), weak_regime=False)
    assert r["components"]["prospects"] == 100


# ── actions ──
@pytest.mark.parametrize("composite,tech,catalyst,close,ema20,pump,weak,expected", [
    (65, 55, 60, 100, 98, False, False, "BUY"),
    (64.9, 80, 60, 100, 98, False, False, "HOLD"),
    (70, 80, 60, 100, 98, False, True, "HOLD"),      # weak regime needs 72
    (72, 80, 60, 100, 98, False, True, "BUY"),
    (80, 54.9, 60, 100, 98, False, False, "HOLD"),   # technical confirmation required
    (80, 80, 60, 100, 98, True, False, "HOLD"),      # pump never BUY
    (40, 50, 50, 100, 98, False, False, "SELL"),
    (40.1, 50, 50, 100, 98, False, False, "HOLD"),
    (55, 50, 30, 95, 98, False, False, "SELL"),      # bearish catalyst + below EMA20
    (55, 50, 30, 100, 98, False, False, "HOLD"),     # bearish catalyst but above EMA20
    (55, 50, None, 95, 98, False, False, "HOLD"),    # quant-only: no catalyst rule
])
def test_decide_action(composite, tech, catalyst, close, ema20, pump, weak, expected):
    assert fz.decide_action(composite, tech, catalyst, close, ema20, pump, weak) == expected


def test_confidence_levels():
    full_bull = {"social": 70, "attention": 80, "catalyst": 75, "prospects": 70, "technical": 72, "smart_money": 65}
    assert fz.confidence(full_bull, 72) == "High"
    mixed = {"social": 40, "attention": 80, "catalyst": 45, "prospects": 70, "technical": 62, "smart_money": 55}
    assert fz.confidence(mixed, 58) == "Medium"
    quant_only = {k: v for k, v in full_bull.items() if k != "catalyst"}
    assert fz.confidence(quant_only, 72) == "Medium"   # never High without the AI catalyst score
    assert fz.confidence(mixed, 52) == "Low"


# ── levels ──
def test_levels_long_uses_atr_stop_when_swing_low_too_close():
    ind = {"close": 100.0, "atr14": 4.0, "ema20": 98.0, "low10": 97.0}   # low10 only 0.75 ATR away
    lv = fz.trade_levels("BUY", ind)
    assert lv["entry"] == 100 and lv["stop"] == pytest.approx(94.0) and lv["target"] == pytest.approx(112.0)


def test_levels_long_uses_swing_low_when_tighter_but_at_least_1_atr():
    ind = {"close": 100.0, "atr14": 4.0, "ema20": 98.0, "low10": 95.0}   # 1.25 ATR away, tighter than 94
    lv = fz.trade_levels("HOLD", ind)
    assert lv["stop"] == 95.0 and lv["target"] == pytest.approx(110.0)


def test_levels_extended_buys_one_atr_pullback():
    ind = {"close": 110.0, "atr14": 4.0, "ema20": 100.0, "low10": 90.0}   # 2.5 ATR above EMA20
    lv = fz.trade_levels("BUY", ind)
    assert lv["entry"] == 106.0 and "pullback" in lv["note"]
    assert lv["stop"] == pytest.approx(100.0) and lv["target"] == pytest.approx(118.0)
    assert lv["target"] > ind["close"]


def test_levels_barely_extended_never_below_ema20():
    ind = {"close": 104.4, "atr14": 4.0, "ema20": 100.0, "low10": 90.0}   # 1.1 ATR above EMA20
    assert fz.trade_levels("BUY", ind)["entry"] == pytest.approx(100.4)


def test_levels_sell_is_short_side():
    lv = fz.trade_levels("SELL", {"close": 50.0, "atr14": 2.0, "ema20": 52.0, "low10": 48.0})
    assert lv["side"] == "short" and lv["stop"] == pytest.approx(53.0) and lv["target"] == pytest.approx(44.0)


def test_levels_missing_atr():
    assert fz.trade_levels("BUY", {"close": 10.0}) is None


# ── validation ──
def test_validate_accepts_good_file():
    assert fz.validate({"tickers": {"AAA": judgment(), "BBB": judgment()}}, ["AAA", "BBB"]) == []


def test_validate_reports_specific_problems():
    bad = judgment(catalyst_type="rumor", news_catalyst_score=120, catalyst_materiality=True,
                   prospects_adjustment=-20, why_in_news="x" * 301, pump_or_bot_flag="no")
    errs = fz.validate({"tickers": {"AAA": bad, "ZZZ": judgment()}}, ["AAA", "BBB"])
    text = "\n".join(errs)
    for needle in ("missing ticker BBB", "unexpected ticker ZZZ", "catalyst_type", "news_catalyst_score: 120",
                   "catalyst_materiality: must be an integer", "prospects_adjustment: -20", "why_in_news: 301",
                   "pump_or_bot_flag"):
        assert needle in text, needle


def test_validate_rejects_wrong_shape():
    assert fz.validate([], ["AAA"]) and fz.validate({"AAA": {}}, ["AAA"])


# ── ranking ──
def test_rank_excludes_pumps_and_builds_avoid_list():
    rows = []
    for t, comp, action, pump in ([("A", 80, "BUY", False), ("B", 75, "BUY", True), ("C", 70, "BUY", False),
                                                 ("D", 60, "HOLD", False), ("E", 55, "HOLD", False), ("F", 50, "HOLD", False),
                                                 ("G", 44, "HOLD", False), ("H", 38, "SELL", False), ("I", 20, "SELL", False)]):
        rows.append({"ticker": t, "composite": comp, "action": action, "pump": pump})
    top, avoid, warn = fz.rank(rows)
    assert [r["ticker"] for r in top] == ["A", "C", "D", "E", "F"]
    assert [r["ticker"] for r in avoid] == ["I", "H", "G"]    # SELLs first (lowest first), then < 45
    assert [r["ticker"] for r in warn] == ["B"]


def test_rank_requires_real_catalyst_for_top_list():
    def row(t, comp, j):
        return {"ticker": t, "composite": comp, "action": "HOLD", "pump": False, "judgment": j}
    rows = [row("BUZZ", 90, judgment(catalyst_type="none", catalyst_materiality=1)),
            row("WEAK", 85, judgment(catalyst_materiality=1)),
            row("REAL", 60, judgment(catalyst_materiality=3)),
            row("QUANT", 55, None)]                       # quant-only rows can't be judged -> allowed
    top, _, _ = fz.rank(rows)
    assert [r["ticker"] for r in top] == ["REAL", "QUANT"]


def test_scoring_is_deterministic():
    t, j = ticker(), judgment()
    a = fz.score_ticker(copy.deepcopy(t), copy.deepcopy(j), False)
    b = fz.score_ticker(copy.deepcopy(t), copy.deepcopy(j), False)
    assert a == b
