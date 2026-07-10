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
    from modules.news_aggregator import get_general_news, get_central_bank_news, get_ai_robotics_news, get_oil_news, get_crypto_news
    from modules.market_data import (
        get_us_indices, get_futures, get_treasury_yields,
        get_other_assets, get_gold_etf_data, get_all_sentiment, get_sector_rotation, get_fx_majors, get_overnight_moves,
        get_rate_expectations
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
            ex.submit(fetch, "News Crypto", get_crypto_news): "crypto_news",
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
    data["rate_expectations"] = fetch("Rate Expectations (Atlanta Fed MPT)", get_rate_expectations)
    data["other_assets"] = fetch("DXY / Gold / Silver / Copper", get_other_assets) or {}
    data["fx"]           = fetch("FX Majors", get_fx_majors) or {}
    data["gold_etf"]     = fetch("Gold ETF (GLD/IAU)", get_gold_etf_data) or {}
    data["overnight"]    = fetch("Overnight Cross-Asset", get_overnight_moves) or {}

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
    for k in ["calendar", "news", "cb_news", "ai_news", "oil_news", "crypto_news"]:
        if not data.get(k):
            data[k] = [] if k != "calendar" else {}

    # ── Dedup CROSS-sezione (zero duplicati) + trim finale con BACKFILL. Priorità:
    #    Central Banks > Crypto > AI > Oil > Breaking (catch-all). Le sezioni pescano un
    #    pool ampio; qui si taglia al numero finale ripescando i migliori rimasti. ──
    import config as _cfg
    from modules.news_aggregator import deduplicate_across_sections, _enrich_selected
    _deduped = deduplicate_across_sections([
        ("cb_news",     data.get("cb_news", []),     getattr(_cfg, "MAX_NEWS_CENTRAL_BANKS", 8)),
        ("crypto_news", data.get("crypto_news", []), getattr(_cfg, "MAX_NEWS_CRYPTO", 8)),
        ("ai_news",     data.get("ai_news", []),     getattr(_cfg, "MAX_NEWS_AI", 6)),
        ("oil_news",    data.get("oil_news", []),    getattr(_cfg, "MAX_NEWS_OIL", 8)),
        ("news",        data.get("news", []),        getattr(_cfg, "MAX_NEWS_GENERAL", 12)),
    ])
    # Arricchimento (traduzione + full-text) SOLO sui finali mostrati, in parallelo.
    for _k, _v in _deduped.items():
        data[_k] = _enrich_selected(_v)

    # ── Sintesi 'so what' via Gemini — UNA SOLA chiamata per tutte (evita il 429 del free
    #    tier che prima faceva cadere alcune sintesi, es. il recap). Fallback sicuro. ──
    from modules.news_aggregator import get_all_syntheses
    print("\nGenerating 'so what' synthesis (Gemini, single call)...")
    _all_syn = get_all_syntheses(data)
    data["synthesis"] = {k: _all_syn.get(k, "") for k in ("news", "cb_news", "crypto_news", "oil_news", "ai_news")}
    data["recap_synthesis"] = _all_syn.get("recap", "")

    # ── Data-quality / plausibility layer (dopo i fetch, prima del render) ──
    from modules.sanity import check_data_quality, load_snapshot, save_snapshot
    _dq_warnings, _dq_snap = check_data_quality(data, load_snapshot())
    save_snapshot(_dq_snap)
    data["data_quality"] = _dq_warnings
    if _dq_warnings:
        print(f"\n⚠  DATA QUALITY — {len(_dq_warnings)} suspect value(s):")
        for _w in _dq_warnings:
            print(f"   ⚠ {_w}")
    else:
        print("\n✓ Data quality: no suspect values")

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
