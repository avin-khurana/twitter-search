"""Market movers from yfinance's predefined Yahoo screens (prior/current session)."""
from __future__ import annotations

import config


def fetch_movers(per_screen: int = config.MOVERS_PER_SCREEN) -> tuple[list[dict], dict[str, str]]:
    import yfinance as yf

    out, status = [], {}
    for key in config.MOVER_SCREENS:
        try:
            quotes = (yf.screen(key, count=per_screen) or {}).get("quotes", [])
            status[key] = f"ok:{len(quotes)}"
        except Exception as e:
            status[key] = f"fail: {type(e).__name__}: {e}"
            continue
        for q in quotes:
            sym = str(q.get("symbol", "")).upper()
            if not sym or q.get("quoteType", "EQUITY") != "EQUITY":
                continue
            out.append({
                "ticker": sym,
                "screen": key,
                "name": q.get("shortName") or q.get("longName") or "",
                "change_pct": q.get("regularMarketChangePercent"),
                "market_cap": q.get("marketCap"),
                "exchange": q.get("exchange"),
            })
    return out, status
