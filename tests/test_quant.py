import pytest

import quant

UPTREND = {"close": 110, "ema20": 105, "ema50": 100, "rsi14": 62, "rel_volume": 2.2, "change_1d": 0.03,
           "high20_prior": 108, "rs_20d": 0.08, "gap": 0.01, "atr14": 2.0}
DOWNTREND = {"close": 80, "ema20": 90, "ema50": 100, "rsi14": 28, "rel_volume": 2.5, "change_1d": -0.06,
             "high20_prior": 105, "rs_20d": -0.12, "gap": -0.04, "atr14": 3.0}


def test_technical_uptrend_scores_high_and_downtrend_low():
    up, up_why = quant.technical_score(UPTREND)
    down, _ = quant.technical_score(DOWNTREND)
    # 50 +15 trend +10 rsi +8 vol +10 breakout +8 rs = 101 -> clamped
    assert up == 100
    assert any("uptrend" in w for w in up_why)
    # 50 -15 trend -12 rsi -8 vol -8 rs -3 gap = 4
    assert down == pytest.approx(4)


def test_technical_handles_missing_fields():
    s, why = quant.technical_score({})
    assert s == 50 and why == []


def test_attention_rewards_growing_buzz_and_rank():
    ape = {"mentions": 300, "mentions_24h_ago": 95, "rank": 4}
    s, why = quant.attention_score(ape, {"trending_rank": 3}, ["day_gainers"], None)
    # ratio (305/100)=3.05 -> +25, rank<=10 +10, ST top10 +10, mover +5 -> 100
    assert s == 100
    assert "24h ago" in why[0]


def test_attention_uses_baseline_when_available_and_penalizes_fading():
    ape = {"mentions": 20, "mentions_24h_ago": 200, "rank": 40}
    s, why = quant.attention_score(ape, None, [], baseline=100.0)
    # ratio 25/105 = 0.24 -> -15 ; rank 40 -> 0
    assert s == 35
    assert "7-day avg" in why[0]


def test_attention_without_reddit():
    s, _ = quant.attention_score(None, None, [], None)
    assert s == 45


def test_smart_money_insider_buying_and_low_put_call():
    info = {"marketCap": 10e9, "shortPercentOfFloat": 0.03, "shortRatio": 1.0, "heldPercentInstitutions": 0.6}
    ins = {"buys": 2, "buyers": 2, "buy_value": 2e6, "sells": 0, "sell_value": 0, "sellers": 0}
    s, _ = quant.smart_money_score(info, ins, {"pc_volume": 0.4})
    assert s == 50 + 18 + 3 + 8 + 4


def test_smart_money_heavy_shorts_and_puts():
    info = {"marketCap": 5e9, "shortPercentOfFloat": 0.30, "shortRatio": 9, "heldPercentInstitutions": 0.1}
    ins = {"buys": 0, "buyers": 0, "buy_value": 0, "sells": 4, "sell_value": 40e6, "sellers": 3}
    s, _ = quant.smart_money_score(info, ins, {"pc_volume": 2.0})
    assert s == 50 - 5 - 5 - 3 - 10 - 4


def test_prospects_clamped_and_analyst_net():
    info = {"revenueGrowth": 0.4, "earningsGrowth": 0.5, "currentPrice": 100, "targetMeanPrice": 140,
            "numberOfAnalystOpinions": 20, "recommendationMean": 1.5}
    an = {"upgrades": 3, "downgrades": 0, "pt_raised": 5, "pt_lowered": 0}
    s, _ = quant.prospects_score(info, an)
    assert s == 100
    bad = {"revenueGrowth": -0.1, "earningsGrowth": -0.3, "currentPrice": 100, "targetMeanPrice": 90,
           "numberOfAnalystOpinions": 10, "recommendationMean": 3.6}
    s2, _ = quant.prospects_score(bad, {"upgrades": 0, "downgrades": 4, "pt_raised": 0, "pt_lowered": 5})
    assert s2 == 50 - 8 - 6 - 8 - 8 - 12 - 6


def test_prospects_ignores_targets_with_few_analysts():
    s, _ = quant.prospects_score({"currentPrice": 10, "targetMeanPrice": 30, "numberOfAnalystOpinions": 1}, None)
    assert s == 50


@pytest.mark.parametrize("bull,bear,expected", [
    (0, 0, 50.0),
    (10, 0, 50 + 30 * (10 / 15)),     # raw 80, shrink 10/15
    (0, 10, 50 - 30 * (10 / 15)),
    (1, 0, 50 + 30 * (1 / 6)),        # one tag barely moves it
])
def test_social_base_shrinks_small_samples(bull, bear, expected):
    s, _ = quant.social_base(bull, bear)
    assert s == pytest.approx(expected)


def test_risk_flags():
    ind = {"rsi14": 85, "close": 120, "ema20": 100, "atr14": 5, "change_1d": 0.25}
    ape = {"mentions": 100, "mentions_24h_ago": 5}
    fl = quant.risk_flags(ind, 18, 2, ape, None, {"trading_days": 3, "date": "2026-11-18"}, 3e9)
    assert fl["euphoria"] and fl["stretched_vs_ema20"] and fl["mention_spike"]
    assert fl["earnings_in_window"] and fl["pump_suspect"]
    calm = quant.risk_flags({"rsi14": 55, "close": 100, "ema20": 99, "atr14": 2}, 3, 3, None, None,
                            {"trading_days": 30}, 50e9)
    assert not any(calm[k] for k in ("euphoria", "mention_spike", "earnings_in_window", "pump_suspect"))


def test_newsworthiness_is_direction_neutral():
    assert quant.newsworthiness(60, 0.08, 2, True) == quant.newsworthiness(60, -0.08, 2, True)
