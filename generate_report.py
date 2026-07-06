#!/usr/bin/env python3
"""
Daily Macro Report — Main Script
Esegui ogni mattina: python generate_report.py
Output: report.html (si apre automaticamente nel browser)
"""

import sys, os, time
from datetime import datetime
import pytz
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROME_TZ = pytz.timezone("Europe/Rome")
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.html")


def banner():
    now = datetime.now(ROME_TZ).strftime("%d/%m/%Y %H:%M")
    print("\n" + "═"*60)
    print(f"  DAILY MACRO REPORT — {now} (Rome)")
    print("═"*60 + "\n")


def check_config():
    import config
    w = []
    if config.NEWSAPI_KEY == "YOUR_NEWSAPI_KEY_HERE":
        w.append("⚠  NEWSAPI_KEY → Bloomberg/WSJ/NYT/FT aggregator not available")
    if config.FRED_API_KEY == "YOUR_FRED_API_KEY_HERE":
        w.append("⚠  FRED_API_KEY → Treasury yields from Yahoo Finance (fallback)")
    if config.COINGLASS_API_KEY == "YOUR_COINGLASS_API_KEY_HERE":
        w.append("⚠  COINGLASS_API_KEY → Liquidations from OKX public API (sample, not full 24h)")
    if getattr(config, "CMC_API_KEY", "YOUR_CMC_API_KEY_HERE") == "YOUR_CMC_API_KEY_HERE":
        w.append("⚠  CMC_API_KEY → Crypto F&G: alternative.me + MA30 average (no CMC as second provider)")
    if w:
        print("Missing API keys:")
        for x in w: print(f"  {x}")
        print()


def fetch(name, func, *args, **kwargs):
    t = time.time()
    try:
        r = func(*args, **kwargs)
        print(f"  ✓ {name} ({time.time()-t:.1f}s)")
        return r
    except Exception as e:
        print(f"  ✗ {name} ERROR: {e}")
        return None


def main():
    banner()
    check_config()

    from modules.economic_calendar import get_economic_calendar
    from modules.news_aggregator import get_general_news, get_central_bank_news, get_ai_robotics_news, get_oil_news
    from modules.market_data import (
        get_us_indices, get_futures, get_treasury_yields,
        get_other_assets, get_gold_etf_data, get_all_sentiment, get_sector_rotation
    )
    from modules.crypto_data import get_all_crypto_data, get_stablecoin_liquidity
    from modules.extras import get_pc_ratios, get_earnings_this_week, get_asia_session, get_combined_crypto_fg
    from modules.analysis import (
        analyze_crypto, analyze_us_indices, analyze_asset, analyze_sentiment
    )
    from modules.html_template import generate_html

    print("Fetching data in parallel...\n")
    t0 = time.time()
    data = {}

    with ThreadPoolExecutor(max_workers=8) as ex:
        fmap = {
            ex.submit(fetch, "Calendario (3 giorni)", get_economic_calendar): "calendar",
            ex.submit(fetch, "Breaking News", get_general_news): "news",
            ex.submit(fetch, "News Banche Centrali", get_central_bank_news): "cb_news",
            ex.submit(fetch, "News AI & Robotica", get_ai_robotics_news): "ai_news",
            ex.submit(fetch, "News Oil & Energy", get_oil_news): "oil_news",
            ex.submit(fetch, "Sentiment (F&G + AAII)", get_all_sentiment): "sentiment",
            ex.submit(fetch, "Asia Session", get_asia_session): "asia",
            ex.submit(fetch, "Sector Rotation", get_sector_rotation): "sector_rotation",
        }
        for future in as_completed(fmap):
            data[fmap[future]] = future.result()

    # Extras paralleli (leggeri)
    with ThreadPoolExecutor(max_workers=4) as ex:
        fmap2 = {
            ex.submit(fetch, "Deribit P/C Ratio", get_pc_ratios): "pc_ratios",
            ex.submit(fetch, "Earnings Calendario", get_earnings_this_week): "earnings",
            ex.submit(fetch, "F&G Combinato", get_combined_crypto_fg): "_combined_fg",
            ex.submit(fetch, "Stablecoin Liquidity", get_stablecoin_liquidity): "stablecoin",
        }
        for future in as_completed(fmap2):
            data[fmap2[future]] = future.result()

    print()
    # Crypto (separato per CoinGecko rate limit)
    data["_crypto"] = fetch("Crypto (CoinGecko + farside + OKX + Binance)", get_all_crypto_data)

    # Market data (yfinance, sequenziale)
    data["indices"]      = fetch("Indici USA + VIX", get_us_indices) or {}
    data["futures"]      = fetch("Futures Pre-Market", get_futures) or {}
    data["yields"]       = fetch("Treasury Yields", get_treasury_yields) or {}
    data["other_assets"] = fetch("DXY / Gold / Silver / Copper", get_other_assets) or {}
    data["gold_etf"]     = fetch("Gold ETF (GLD/IAU)", get_gold_etf_data) or {}

    # Unpack crypto
    crypto_raw = data.pop("_crypto", {}) or {}
    data["crypto"] = {
        "prices":       crypto_raw.get("prices", {}),
        "btc_etf":      crypto_raw.get("btc_etf", {}),
        "eth_etf":      crypto_raw.get("eth_etf", {}),
        "sol_etf":      crypto_raw.get("sol_etf", {}),
        "liquidations": crypto_raw.get("liquidations", {}),
    }

    # Sostituisci crypto F&G nel sentiment con quello combinato
    sentiment = data.get("sentiment") or {}
    combined_fg = data.pop("_combined_fg", None)
    sentiment["crypto_fg"] = combined_fg if combined_fg else crypto_raw.get("fear_greed", {})
    data["sentiment"] = sentiment

    # Sanitize
    for k in ["calendar", "news", "cb_news", "ai_news", "oil_news"]:
        if not data.get(k):
            data[k] = [] if k != "calendar" else {}

    # ── Micro Analisi ──
    print("\nGenerating analysis...")
    prices  = data["crypto"].get("prices", {})
    btc_etf = data["crypto"].get("btc_etf", {})
    eth_etf = data["crypto"].get("eth_etf", {})
    sol_etf = data["crypto"].get("sol_etf", {})
    liqs    = data["crypto"].get("liquidations", {})

    data["analyses"] = {
        "crypto": {
            "BTC": analyze_crypto("BTC", prices.get("BTC"), btc_etf, liqs.get("BTC")),
            "ETH": analyze_crypto("ETH", prices.get("ETH"), eth_etf, liqs.get("ETH")),
            "SOL": analyze_crypto("SOL", prices.get("SOL"), sol_etf, liqs.get("SOL")),
        },
        "indices": analyze_us_indices(
            data["indices"], data["futures"], data["yields"],
            data["indices"].get("VIX")
        ),
        "assets": {
            name: analyze_asset(name, d)
            for name, d in data["other_assets"].items()
        },
        "sentiment": analyze_sentiment(data["sentiment"]),
    }

    # ── Genera HTML ──
    print("\nGenerating HTML...")
    html = generate_html(data)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'═'*60}")
    print(f"  ✅ Report ready in {time.time()-t0:.0f}s — {OUTPUT_FILE}")
    print(f"{'═'*60}\n")

    try:
        import subprocess
        subprocess.run(["open", OUTPUT_FILE], check=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
