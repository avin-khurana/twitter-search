from datetime import date

import pandas as pd
import pytest

import collect
import config
import finalize as fz
import setups
import track


def judgment(**over):
    j = {"why_in_news": "Reason.", "catalyst_type": "earnings", "catalyst_direction": "bullish",
         "catalyst_materiality": 4, "catalyst_is_new": True, "news_catalyst_score": 77,
         "social_sentiment_score": 60, "prospects_adjustment": 0, "direction_summary": "Growing.",
         "pump_or_bot_flag": False, "key_evidence": "Headline.", "crowd_emotion": "optimism",
         "emotion_intensity": 3, "crowd_vs_price": "aligned", "narrative_stage": "spreading"}
    j.update(over)
    return j


def stock(ticker="AAA", bull_ratio=None, flags=None, **ind):
    base = {"close": 100.0, "ema20": 98.0, "ema50": 96.0, "atr14": 4.0, "atr_pct": 0.04, "rsi14": 55.0,
            "change_1d": 0.0, "gap": 0.0, "ret_5d": 0.0, "ret_20d": 0.0, "rel_volume": 1.0,
            "high": 101.0, "low": 99.0, "low10": 95.0, "bar_date": "2026-11-13"}
    base.update(ind)
    fl = {"euphoria": False, "earnings_in_window": False, "pump_suspect": False, "mention_spike": False,
          "stretched_vs_ema20": False, "bull_ratio": bull_ratio}
    fl.update(flags or {})
    return {"ticker": ticker, "name": f"{ticker} Inc", "indicators": base, "flags": fl,
            "quant": {"attention": 60, "technical": 60, "smart_money": 60, "prospects_base": 70, "social_base": 55},
            "stocktwits": {"bull": 13, "bear": 1, "messages": 30}}


# Fixtures modelled on the 2026-11-13 run
def nu():        # record profit, +10% on 1.3x volume, above EMA20 but below EMA50
    return stock("NU", 0.89, close=13.06, ema20=12.73, ema50=13.42, atr_pct=0.051, change_1d=0.104, gap=0.045,
                 ret_5d=0.086, ret_20d=-0.103, rel_volume=1.3)


def htfl():      # -18.5% after a beat and raised guidance
    return stock("HTFL", None, close=48.85, ema20=54.84, ema50=51.31, atr14=3.9, atr_pct=0.08, change_1d=-0.185,
                 ret_5d=-0.068, ret_20d=0.012, rel_volume=1.3, high=52.0, low=47.5)


def nbis():      # -29% in 20 days on bad news, 13 bulls to 1 bear
    return stock("NBIS", 0.93, close=117.98, ema20=152.8, ema50=179.5, atr_pct=0.156, change_1d=-0.083,
                 ret_5d=-0.089, ret_20d=-0.287)


BAD_NEWS = dict(catalyst_direction="bearish", catalyst_materiality=4, news_catalyst_score=26)


# ── classification ──
def test_drift_good_news_confirmed_by_price_and_calm_crowd():
    s = setups.classify(nu(), judgment(), prospects=96)
    assert s["setup"] == setups.DRIFT
    assert s["confirmations"] == ["major news"]            # 1.3x volume and below EMA50 don't confirm
    strong = stock(change_1d=0.06, rel_volume=2.0, ret_5d=0.07)
    s2 = setups.classify(strong, judgment(narrative_stage="early"), prospects=70)
    assert s2["confirmations"] == ["major news", "heavy volume (2.0x)", "above its 50-day average",
                                   "the crowd hasn't caught on yet"]


@pytest.mark.parametrize("over", [
    {"crowd_emotion": "euphoria", "emotion_intensity": 4},   # crowd already euphoric
    {"catalyst_materiality": 2},                             # news too small
    {"catalyst_is_new": False},                              # old news
    {"catalyst_direction": "mixed"},
    {"narrative_stage": "exhausted"},
    {"pump_or_bot_flag": True},
])
def test_drift_blockers(over):
    assert setups.classify(nu(), judgment(**over), prospects=96)["setup"] != setups.DRIFT


def test_drift_needs_price_confirmation():
    flat = stock(change_1d=0.01, gap=0.0, ret_5d=0.02, rel_volume=2.0)
    assert setups.classify(flat, judgment(), prospects=70)["setup"] == setups.NONE
    day_two = stock(change_1d=-0.01, ret_5d=0.08, rel_volume=0.9)      # still up since the news
    assert setups.classify(day_two, judgment(), prospects=70)["setup"] == setups.DRIFT


def test_overreaction_dip_sharp_drop_on_news_that_is_not_bad():
    j = judgment(catalyst_direction="mixed", catalyst_materiality=3, news_catalyst_score=55)
    s = setups.classify(htfl(), j, prospects=72)
    assert s["setup"] == setups.DIP and s["confirmations"] == ["strong business outlook"]
    scared = setups.classify(htfl(), dict(j, crowd_emotion="panic", catalyst_direction="bullish"), prospects=72)
    assert scared["confirmations"][:2] == ["the crowd has given up (panic)", "the news was actually good"]


def test_dip_exclusions():
    j = judgment(catalyst_direction="mixed", catalyst_materiality=3, news_catalyst_score=55)
    assert setups.classify(htfl(), dict(j, catalyst_direction="bearish"), 72)["setup"] != setups.DIP
    assert setups.classify(htfl(), dict(j, news_catalyst_score=44), 72)["setup"] == setups.NONE
    assert setups.classify(htfl(), j, prospects=59)["setup"] == setups.NONE              # weak business
    after_spike = stock(change_1d=-0.091, ret_5d=0.185, atr_pct=0.05)                    # pullback after a run
    assert setups.classify(after_spike, j, 90)["setup"] == setups.NONE
    small = stock(change_1d=-0.045, atr_pct=0.04)                                        # under 1.25 ATR
    assert setups.classify(small, j, 90)["setup"] == setups.NONE


def test_hope_trap_falling_on_bad_news_while_crowd_stays_bullish():
    j = judgment(**BAD_NEWS, crowd_emotion="hope", emotion_intensity=4,
                 crowd_vs_price="crowd_bullish_price_falling", narrative_stage="consensus")
    s = setups.classify(nbis(), j, prospects=62)
    assert s["setup"] == setups.HOPE_TRAP
    assert s["confirmations"] == ["major bad news", "strong denial in the posts", "almost no bears left",
                                  "deep downtrend"]


def test_falling_on_bad_news_with_a_fearful_crowd_is_not_a_hope_trap():
    nvda = stock("NVDA", 0.33, close=162.0, ema20=193.0, ema50=207.0, change_1d=-0.022, ret_5d=-0.13, ret_20d=-0.24)
    j = judgment(**BAD_NEWS, crowd_emotion="fear", crowd_vs_price="aligned")
    assert setups.classify(nvda, j, prospects=58)["setup"] == setups.NONE
    # bullish tags alone don't make a hope trap below the 80% bar (StockTwits skews bullish)
    assert setups.classify(stock(bull_ratio=0.7, close=90, ema20=100, ret_20d=-0.2),
                           judgment(**BAD_NEWS, crowd_emotion="mixed"), 60)["setup"] == setups.NONE


def test_hype_fade_euphoria_and_run_up_without_confirmed_news():
    rumor = stock("VKTX", 0.875, change_1d=0.057, ret_5d=0.086)
    j = judgment(catalyst_type="m_and_a", catalyst_materiality=2, crowd_emotion="euphoria", emotion_intensity=3)
    assert setups.classify(rumor, j, prospects=68)["setup"] == setups.HYPE_FADE        # euphoria + 87% bulls
    assert setups.classify(rumor, dict(j, crowd_emotion="optimism"), 68)["setup"] == setups.NONE
    assert setups.classify(stock(bull_ratio=0.875, change_1d=0.01), j, 68)["setup"] == setups.NONE   # no run-up
    real_news = dict(j, catalyst_materiality=4, emotion_intensity=5)
    assert setups.classify(rumor, real_news, 68)["setup"] == setups.NONE               # real news, not stretched
    stretched = stock(bull_ratio=0.9, change_1d=0.08, flags={"euphoria": True})
    assert setups.classify(stretched, real_news, 68)["setup"] == setups.HYPE_FADE      # stretched even with news


def test_no_crowd_labels_means_no_setup():
    old_style = {k: v for k, v in judgment().items() if k not in
                 ("crowd_emotion", "emotion_intensity", "crowd_vs_price", "narrative_stage")}
    assert setups.classify(nu(), None, 96)["setup"] == setups.NONE
    assert setups.classify(nu(), old_style, 96)["setup"] == setups.NONE


# ── calls ──
@pytest.mark.parametrize("setup,default,composite,ind,emotion,pump,weak,expected", [
    (setups.DRIFT, "HOLD", 72, {"close": 13.06, "ema20": 12.73}, "optimism", False, True, "BUY"),
    (setups.DRIFT, "HOLD", 64, {"close": 13.06, "ema20": 12.73}, "optimism", False, True, "HOLD"),   # weak floor 65
    (setups.DRIFT, "HOLD", 64, {"close": 13.06, "ema20": 12.73}, "optimism", False, False, "BUY"),   # normal floor 60
    (setups.DRIFT, "HOLD", 80, {"close": 108.0, "ema20": 110.0}, "optimism", False, False, "HOLD"),  # below EMA20
    (setups.DRIFT, "BUY", 80, {"close": 13.06, "ema20": 12.73}, "optimism", True, False, "HOLD"),    # pump
    (setups.DIP, "HOLD", 54, {}, "hope", False, True, "HOLD"),       # weak market, crowd not given up
    (setups.DIP, "HOLD", 54, {}, "panic", False, True, "BUY"),
    (setups.DIP, "SELL", 39, {}, "optimism", False, False, "BUY"),   # low score is expected in a dip
    (setups.HOPE_TRAP, "HOLD", 60, {}, "hope", False, False, "SELL"),
    (setups.HYPE_FADE, "BUY", 75, {}, "euphoria", False, False, "SELL"),
    (setups.NONE, "BUY", 75, {}, "optimism", False, False, "BUY"),
    (setups.NONE, "SELL", 30, {}, None, False, False, "SELL"),
])
def test_decide_setup_action(setup, default, composite, ind, emotion, pump, weak, expected):
    action, note = fz.decide_setup_action(setup, default, composite, ind, emotion, pump, weak)
    assert action == expected
    assert bool(note) == (setup in setups.LONG_SETUPS and action == "HOLD")    # every gated long says why


def test_setup_confidence():
    assert fz.setup_confidence(setups.DRIFT, 3, False) == "High"
    assert fz.setup_confidence(setups.DRIFT, 3, True) == "Medium"      # long setups lose one in a weak market
    assert fz.setup_confidence(setups.HOPE_TRAP, 3, True) == "High"
    assert fz.setup_confidence(setups.DIP, 1, False) == "Low"


def test_dip_levels_use_a_trigger_above_last_high():
    lv = fz.trade_levels("BUY", htfl()["indicators"], setups.DIP)
    assert (lv["entry_type"], lv["entry"], lv["stop"], lv["target"]) == ("stop", 52.0, 47.5, 61.0)
    # a collapse day: the high is far away, so the trigger is a 1-ATR bounce off the close instead
    crash = fz.trade_levels("HOLD", dict(htfl()["indicators"], close=49.65, high=58.38, low=48.62), setups.DIP)
    assert crash["entry"] == pytest.approx(53.55) and crash["stop"] == 48.62
    assert crash["target"] == pytest.approx(53.55 + 2 * (53.55 - 48.62)) and "bounce" in crash["note"]
    wide = fz.trade_levels("HOLD", dict(htfl()["indicators"], high=60.0, low=40.0), setups.DIP)
    assert wide["entry"] == pytest.approx(52.75) and wide["stop"] == pytest.approx(52.75 - 2.0 * 3.9)   # risk capped at 2 ATR
    tight = fz.trade_levels("BUY", dict(htfl()["indicators"], high=49.0, low=48.8), setups.DIP)
    assert tight["stop"] == pytest.approx(49.0 - 0.75 * 3.9)                              # and floored at 0.75 ATR
    assert fz.trade_levels("BUY", nu()["indicators"])["entry_type"] == "market"
    assert fz.trade_levels("SELL", nbis()["indicators"], setups.HOPE_TRAP)["side"] == "short"


def test_score_ticker_end_to_end():
    trap = fz.score_ticker(nbis(), judgment(**BAD_NEWS, crowd_emotion="hope", emotion_intensity=4,
                                            crowd_vs_price="crowd_bullish_price_falling"), weak_regime=True)
    assert (trap["setup"], trap["action"], trap["confidence"]) == (setups.HOPE_TRAP, "SELL", "High")
    dip = fz.score_ticker(htfl(), judgment(catalyst_direction="mixed", catalyst_materiality=3,
                                           news_catalyst_score=55, crowd_emotion="fear"), weak_regime=True)
    assert (dip["setup"], dip["action"], dip["levels"]["entry_type"]) == (setups.DIP, "BUY", "stop")
    quant_only = fz.score_ticker(nbis(), None, weak_regime=True)
    assert quant_only["setup"] == setups.NONE and quant_only["setup_reasons"] == []


def test_rank_puts_buys_first_and_keeps_sells_out_of_the_top():
    def row(t, comp, action, setup=setups.NONE):
        return {"ticker": t, "composite": comp, "action": action, "pump": False, "setup": setup}
    rows = [row("HOLD70", 70, "HOLD"), row("TRAP60", 60, "SELL", setups.HOPE_TRAP),
            row("DIPBUY", 55, "BUY", setups.DIP), row("DRIFTWAIT", 61, "HOLD", setups.DRIFT),
            row("DRIFTBUY", 72, "BUY", setups.DRIFT), row("SELL30", 30, "SELL")]
    top, avoid, _ = fz.rank(rows)
    assert [r["ticker"] for r in top] == ["DRIFTBUY", "DIPBUY", "DRIFTWAIT", "HOLD70"]
    assert [r["ticker"] for r in avoid] == ["SELL30", "TRAP60"]


# ── history files ──
RUN = {"run_date": "2026-11-13", "run_id": "2026-11-13_0600", "ape_snapshot": []}


def _rows():
    trap = fz.score_ticker(nbis(), judgment(**BAD_NEWS, crowd_emotion="hope", emotion_intensity=4), True)
    drift = fz.score_ticker(nu(), judgment(), False)
    return [trap, drift]


def test_sentiment_history_roundtrip_and_streak(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "SENTIMENT_CSV", tmp_path / "sentiment.csv")
    rows = _rows()
    fz.save_sentiment(RUN, rows)
    fz.save_sentiment(RUN, rows)                                          # rerun must not duplicate
    assert len(pd.read_csv(config.SENTIMENT_CSV)) == 2
    assert collect.load_crowd_history("2026-11-13") == {}                 # same-day rows are not "history"
    h = collect.load_crowd_history("2026-11-14")
    assert h["NBIS"] == {"date": "2026-11-13", "bull": 13, "bear": 1, "crowd_emotion": "hope",
                         "emotion_intensity": 4, "setup": "hope_trap", "action": "SELL", "close": 117.98,
                         "streak_days": 1}
    fz.save_sentiment(dict(RUN, run_date="2026-11-14"), rows[1:])         # next day: only NU shortlisted
    h2 = collect.load_crowd_history("2026-11-15")
    assert h2["NU"]["streak_days"] == 2
    assert h2["NBIS"]["streak_days"] == 0 and h2["NBIS"]["date"] == "2026-11-13"


def test_picks_log_covers_every_stock_and_migrates_old_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PICKS_CSV", tmp_path / "picks.csv")
    config.PICKS_CSV.write_text(                                          # file written before setups existed
        "date,run_id,list,rank,ticker,action,composite,confidence,mode,bar_date,close,entry,stop,target\n"
        "2026-11-12,r0,top,1,OLD,HOLD,60.0,Medium,full,2026-11-12,10.0,10.0,9.0,12.0\n")
    rows = _rows()
    fz.save_picks(RUN, rows, top=[rows[1]], avoid=[rows[0]], mode="full")
    df = pd.read_csv(config.PICKS_CSV)
    assert list(df.columns) == fz.PICK_COLS and len(df) == 3
    assert df.set_index("ticker")["list"].to_dict() == {"OLD": "top", "NU": "top", "NBIS": "avoid"}
    assert df.set_index("ticker")["setup"].to_dict()["NBIS"] == "hope_trap"
    loaded = track.load_picks(today=date(2026, 11, 20)).set_index("ticker")
    assert loaded.loc["OLD", "setup"] == "none" and loaded.loc["OLD", "entry_type"] == "auto"
    assert loaded.loc["NU", "entry_type"] == "market"


# ── track record ──
def _bars(rows):
    idx = pd.to_datetime([f"2026-11-{16 + i}" for i in range(len(rows))])
    return pd.DataFrame(rows, columns=["Open", "High", "Low", "Close"], index=idx)


def test_trigger_entry_fills_only_when_price_breaks_above():
    never = _bars([(49, 51, 48, 50)] * 3)
    assert track.stop_target_outcome(never, "long", 52, 47.5, 61, ref_close=48.85, window=3, entry_type="stop") == "not filled"
    breaks = _bars([(49, 51, 48, 50), (51, 53, 50.5, 52.5), (53, 62, 52, 61)])
    assert track.stop_target_outcome(breaks, "long", 52, 47.5, 61, ref_close=48.85, window=10, entry_type="stop") == "target"
    # the same bars read as a pullback limit would have "filled" on day one — the entry type matters
    assert track.stop_target_outcome(never, "long", 52, 47.5, 61, ref_close=48.85, window=3, entry_type="limit") == "time"


def test_summary_by_setup_scores_avoid_setups_on_falling_prices():
    ev = pd.DataFrame([
        {"list": "top", "action": "BUY", "setup": "drift", "ret_5d": 0.04, "xs_5d": 0.03, "outcome": "target"},
        {"list": "top", "action": "BUY", "setup": "drift", "ret_5d": -0.02, "xs_5d": -0.01, "outcome": "stop"},
        {"list": "avoid", "action": "SELL", "setup": "hope_trap", "ret_5d": -0.06, "xs_5d": -0.05, "outcome": "target"},
        {"list": "other", "action": "SELL", "setup": "hope_trap", "ret_5d": 0.01, "xs_5d": 0.02, "outcome": "open"},
        {"list": "other", "action": "HOLD", "setup": "none", "ret_5d": None, "xs_5d": None, "outcome": "open"},
    ])
    s = track.summarize(ev)
    assert s["evaluated"] == 4
    assert s["by_setup"]["drift"]["n"] == 2 and s["by_setup"]["drift"]["hit_rate_5d"] == 0.5
    assert s["by_setup"]["hope_trap"]["hit_rate_5d"] == 0.5               # one fell (right), one rose (wrong)
    assert s["by_setup"]["hope_trap"]["avg_ret_5d"] == pytest.approx(-0.025)
    assert s["by_action"]["SELL"]["n"] == 1                               # only the emailed lists count here
    assert s["by_setup"]["overreaction_dip"]["n"] == 0
    assert track.summarize(pd.DataFrame())["evaluated"] == 0
