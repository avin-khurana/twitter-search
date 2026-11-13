"""Source health check: hits each data source once and prints OK/FAIL with a sample.
Run locally and in GitHub Actions (mode=probe) — cloud IPs are sometimes blocked where home IPs aren't.
Exit code 1 only if no discovery source works at all.
"""
from __future__ import annotations

import sys
import time

import config


def check(name: str, fn) -> bool:
    t0 = time.time()
    try:
        sample = fn()
        print(f"OK    {name:<22} {time.time() - t0:5.1f}s  {sample}")
        return True
    except Exception as e:
        print(f"FAIL  {name:<22} {time.time() - t0:5.1f}s  {type(e).__name__}: {str(e)[:150]}")
        return False


def main() -> int:
    import market
    from sources import apewisdom, movers, news, stocktwits

    print(f"Probing sources (Finnhub key: {'yes' if config.FINNHUB_API_KEY else 'no'}, "
          f"NewsAPI key: {'yes' if config.NEWS_API_KEY else 'no'}, "
          f"email: {'configured' if config.EMAIL_FROM and config.EMAIL_APP_PASSWORD else 'not configured'})\n")

    def ape():
        top = apewisdom.top(apewisdom.fetch_all(max_pages=1), 3)
        return ", ".join(f"{r['ticker']}({r['mentions']})" for r in top)

    def st_trend():
        return ", ".join(r["ticker"] for r in stocktwits.fetch_trending(5))

    def st_stream():
        posts = stocktwits.fetch_stream("AAPL")
        bull, bear, n = stocktwits.sentiment_counts(posts)
        return f"{n} msgs, {bull} bull / {bear} bear"

    def yahoo_movers():
        rows, status = movers.fetch_movers(per_screen=3)
        if not rows:
            raise RuntimeError(status)
        return ", ".join(f"{r['ticker']}({r['screen']})" for r in rows[:5])

    def history():
        h = market.download_history(["AAPL", "SPY"], period="3mo")
        return f"{len(h)} tickers, {len(h.get('AAPL', []))} bars"

    def info():
        i = market.fetch_info("AAPL")
        if "_error" in i:
            raise RuntimeError(i["_error"])
        return f"mcap ${i['marketCap'] / 1e9:.0f}B, target {i.get('targetMeanPrice')}"

    def profile():
        p = market.fetch_profile("AAPL")
        return ", ".join(f"{k}={'ok' if v else 'n/a'}" for k, v in p.items())

    def regime():
        return market.market_regime()["label"]

    def gnews():
        return news.google_news("AAPL", "Apple", 2)[0].title[:70]

    def finnhub():
        if not config.FINNHUB_API_KEY:
            return "skipped (no FINNHUB_API_KEY)"
        items = news.finnhub_news("AAPL", 2)
        return f"{len(items)} items" + (f": {items[0].title[:60]}" if items else "")

    def yfnews():
        return f"{len(news.yfinance_news('AAPL'))} items"

    def newsapi():
        if not config.NEWS_API_KEY:
            return "skipped (no NEWS_API_KEY)"
        return f"{len(news.newsapi_news('AAPL', 'Apple', 2))} items"

    discovery = [check("ApeWisdom (Reddit)", ape), check("StockTwits trending", st_trend),
                 check("Yahoo movers screens", yahoo_movers)]
    for name, fn in [("StockTwits stream", st_stream), ("yfinance history", history), ("yfinance info", info),
                     ("yfinance profile", profile), ("market regime", regime), ("Google News RSS", gnews),
                     ("Finnhub news", finnhub), ("yfinance news", yfnews), ("NewsAPI", newsapi)]:
        check(name, fn)
    if not any(discovery):
        print("\nNo discovery source works — the daily scan would find nothing.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
