# Stock Buzz

Finds the stocks people are talking about (Reddit via ApeWisdom, StockTwits, Yahoo movers, news),
explains **why** each is in the news, scores them, and emails a **top 5 with BUY / HOLD / SELL for a
2–10 trading-day swing** plus an **avoid list**. Runs every weekday at 6:00 AM Central on GitHub Actions.

```
collect.py ──► runs/<id>/digest.md ──► Claude (prompts/judge.md) ──► claude_scores.json ──► finalize.py ──► email + reports/ + data/picks.csv
 (Python: data + numeric scores)        (judgment: why, catalyst, sentiment, direction)       (Python: composite, actions, levels)
```

## Scoring
| Component | Weight | Source |
|---|---|---|
| Social sentiment | 20% | StockTwits bull/bear tags, refined by Claude reading the posts |
| News catalyst | 20% | Claude: type, direction, materiality, freshness |
| Technical setup | 20% | EMA20/50 trend, RSI, relative volume, 20-day high, strength vs SPY |
| Future prospects | 15% | Growth, analyst targets/revisions, ±15 from Claude for guidance and strategy news |
| Smart money | 15% | Insider buys/sells, short interest, put/call ratio, institutional ownership |
| Attention velocity | 10% | Reddit mentions vs 7-day baseline, StockTwits trending rank, mover lists |

Penalties: euphoria −10, earnings inside the window −5. Top-5 names need a real catalyst.

## Behavioral setups (these decide the call)
Claude labels the crowd for each stock (emotion, intensity, whether crowd and price agree, how far the
story has spread). `setups.py` then compares what the crowd feels with what news and price are doing:

| Setup | The psychology | Rule of thumb | Call |
|---|---|---|---|
| Drift | People underreact to real news | New, material good news + price confirmed it + crowd not euphoric | BUY if score ≥ 60 (65 in a weak market) and price is above EMA20 |
| Overreaction dip | Panic selling on news that isn't bad | Drop ≥ 1.25 ATR, catalyst ≥ 45, prospects ≥ 60 | BUY only after a 1-ATR bounce; in a weak market only if the crowd has given up |
| Hype fade | Herding late in a move | Euphoric crowd + run-up + no confirmed news | SELL / avoid |
| Hope trap | Holders won't sell losers | Downtrend + bad news + crowd still bullish | SELL / avoid |

Stocks with no setup fall back to the score: BUY ≥ 65 (≥ 72 when SPY < 50-day EMA or VIX > 25) with
technical ≥ 55; SELL ≤ 40 or a strongly bearish catalyst below EMA20; otherwise HOLD.

Every analyzed stock is logged to `data/picks.csv` with its setup, and its crowd read to
`data/sentiment_history.csv`. The track record in the email reports 5-day results per setup, which is
how to tell which pattern actually works. All thresholds are in `config.py`; they are starting guesses.

## One-time setup
1. **Claude token:** run `claude setup-token` in your terminal and copy the token.
2. **Repository secrets** (GitHub → Settings → Secrets and variables → Actions):
   - `CLAUDE_CODE_OAUTH_TOKEN`: the token from step 1 (uses your Claude subscription, no API bill)
   - `EMAIL_FROM`, `EMAIL_APP_PASSWORD`: Gmail address and app password (same as the LEAPS scanner)
   - `EMAIL_TO`: where the report goes
   - `FINNHUB_API_KEY` (optional, free at finnhub.io: adds article summaries), `NEWS_API_KEY` (optional fallback)
   - Optional: `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`; `ANTHROPIC_API_KEY` (used only if the Claude token is missing)
3. **Actions → Stock Buzz daily scan → Run workflow** with `mode=probe` to check the sources from GitHub's servers,
   then `mode=full` to get the first email.

## Running locally
```bash
pip install -r requirements.txt
cp .env.example .env            # optional keys
python probe.py                 # source health
python collect.py               # or: python collect.py --tickers NVDA PLTR
# judgment: in Claude Code, type /stock-buzz (does all steps), or follow prompts/judge.md by hand
python finalize.py --no-email --no-log
python track.py                 # forward returns of logged picks vs SPY
python -m pytest -q
```

## Notes
- If the AI step fails (token expired, usage limit), the email still goes out as a numbers-only ranking with a banner.
- Reddit's own API is closed to new apps and its public JSON returns 403, so Reddit data is ApeWisdom's mention counts.
- X/Twitter is not included (its API is pay-per-use). Add it later as `sources/x.py` returning `Post` records.
- GitHub can start scheduled runs 5–30+ minutes late. To move the time, edit both cron lines and `ci_guard.py`.
- Experimental research output, not financial advice. Watch the track record before trading on it.
