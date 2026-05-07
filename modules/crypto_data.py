"""
Crypto Data Module

- BTC, ETH, SOL: prezzi + variazioni (CoinGecko)
- BTC ETF flows: farside.co.uk (fonte principale settore) + yfinance per AUM
- ETH ETF flows: farside.co.uk
- Liquidazioni: CoinGlass API
- Crypto Fear & Greed: alternative.me (API pubblica)
"""

import requests
import yfinance as yf
from bs4 import BeautifulSoup
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from datetime import datetime, timezone


def fmt_large(val):
    if val is None:
        return "N/A"
    if val >= 1e12:
        return f"${val/1e12:.2f}T"
    if val >= 1e9:
        return f"${val/1e9:.2f}B"
    if val >= 1e6:
        return f"${val/1e6:.2f}M"
    return f"${val:,.0f}"

def fmt_price(val, decimals=2):
    if val is None:
        return "N/A"
    return f"${val:,.{decimals}f}"


# ─────────────────────────────────────────────────────────────
# COINGECKO: BTC, ETH, SOL
# ─────────────────────────────────────────────────────────────

def get_crypto_prices():
    """BTC, ETH, SOL da CoinGecko (API gratuita)."""
    print("[Crypto] Fetching crypto prices from CoinGecko...")
    try:
        ids = ",".join(config.CRYPTO_ASSETS.values())
        resp = requests.get(
            "https://api.coingecko.com/api/v3/coins/markets",
            params={
                "vs_currency": "usd",
                "ids": ids,
                "order": "market_cap_desc",
                "sparkline": False,
                "price_change_percentage": "24h,7d",
            },
            headers={"Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        coins = resp.json()

        result = {}
        for coin in coins:
            sym = coin["symbol"].upper()
            price = coin.get("current_price")
            ch24 = coin.get("price_change_percentage_24h", 0) or 0
            ch7d = coin.get("price_change_percentage_7d_in_currency", 0) or 0
            mkt = coin.get("market_cap")
            vol = coin.get("total_volume")
            ath = coin.get("ath")
            ath_pct = coin.get("ath_change_percentage")
            direction = "up" if ch24 > 0 else "down" if ch24 < 0 else "neutral"

            result[sym] = {
                "name": coin.get("name"),
                "symbol": sym,
                "price": price,
                "price_fmt": fmt_price(price),
                "change_24h": ch24,
                "change_24h_fmt": f"{'+' if ch24 >= 0 else ''}{ch24:.2f}%",
                "change_7d": ch7d,
                "change_7d_fmt": f"{'+' if ch7d >= 0 else ''}{ch7d:.2f}%",
                "market_cap": mkt,
                "market_cap_fmt": fmt_large(mkt),
                "volume_24h": vol,
                "volume_24h_fmt": fmt_large(vol),
                "ath": ath,
                "ath_fmt": fmt_price(ath),
                "ath_distance": f"{ath_pct:.1f}%" if ath_pct else "N/A",
                "direction": direction,
                "rank": coin.get("market_cap_rank"),
                "source": "CoinGecko",
            }

        # Global market stats
        try:
            gr = requests.get("https://api.coingecko.com/api/v3/global", timeout=10)
            gd = gr.json().get("data", {})
            btc_dom = gd.get("market_cap_percentage", {}).get("btc")
            eth_dom = gd.get("market_cap_percentage", {}).get("eth")
            total_mc = gd.get("total_market_cap", {}).get("usd")
            result["_global"] = {
                "btc_dominance": f"{btc_dom:.1f}%" if btc_dom else "N/A",
                "eth_dominance": f"{eth_dom:.1f}%" if eth_dom else "N/A",
                "total_market_cap": fmt_large(total_mc),
                "total_market_cap_change_24h": gd.get("market_cap_change_percentage_24h_usd"),
            }
        except Exception:
            result["_global"] = {}

        return result

    except Exception as e:
        print(f"[Crypto] CoinGecko error: {e}")
        return {}


# ─────────────────────────────────────────────────────────────
# FARSIDE: BTC + ETH ETF Flows
# ─────────────────────────────────────────────────────────────

def _parse_farside_flow(text):
    """Parse farside flow value: '(86.5)' = -86.5, '123.4' = 123.4"""
    text = text.strip()
    if not text or text in ['-', '']:
        return 0.0
    if text.startswith('(') and text.endswith(')'):
        try:
            return -float(text[1:-1].replace(',', ''))
        except Exception:
            return 0.0
    try:
        return float(text.replace(',', ''))
    except Exception:
        return 0.0


_FARSIDE_CACHE_TTL = 1800  # 30 minuti

def _farside_cache_path(asset_name):
    return f"/tmp/farside_{asset_name.lower()}_cache.json"

def _load_farside_cache(asset_name):
    path = _farside_cache_path(asset_name)
    try:
        with open(path) as f:
            cached = json.load(f)
        age = time.time() - cached.get("_ts", 0)
        if age < _FARSIDE_CACHE_TTL:
            print(f"[Crypto] Farside {asset_name}: cache fresca ({int(age)}s fa)")
            return cached.get("data"), False  # (data, is_stale)
        return cached.get("data"), True  # stale but available as fallback
    except Exception:
        return None, True

def _save_farside_cache(asset_name, data):
    path = _farside_cache_path(asset_name)
    try:
        with open(path, "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass

def _fetch_farside(url, asset_name):
    """
    Scrape farside.co.uk ETF flow table.
    Cache su disco 30min + retry con backoff su errori HTTP.
    Returns dict with: last_date, daily_total, by_etf, cumulative_total
    """
    cached_data, is_stale = _load_farside_cache(asset_name)
    if cached_data and not is_stale:
        return cached_data

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    for attempt in range(3):
        if attempt > 0:
            time.sleep(4 * (2 ** (attempt - 1)))  # 4s, 8s
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=20)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            tables = soup.find_all("table")
            main_table = None
            for t in tables:
                rows = t.find_all("tr")
                if len(rows) > 10:
                    main_table = t
                    break

            if not main_table:
                raise ValueError("No data table found")

            rows = main_table.find_all("tr")
            headers_row = [th.get_text(strip=True) for th in rows[0].find_all(["th", "td"])]

            skip_labels = {"Total", "Average", "Maximum", "Minimum", ""}
            data_rows = []
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if cells and cells[0] and cells[0] not in skip_labels and len(cells) >= 3:
                    data_rows.append(cells)

            if not data_rows:
                raise ValueError("No data rows found")

            last_row = None
            for row in reversed(data_rows):
                vals = [_parse_farside_flow(c) for c in row[1:] if c and c not in ("-", "")]
                if any(v != 0 for v in vals):
                    last_row = row
                    break
            if last_row is None:
                last_row = data_rows[-1]
            last_date = last_row[0]

            by_etf = {}
            total_col = None
            for i, col_name in enumerate(headers_row):
                if col_name.upper() == "TOTAL":
                    total_col = i
                elif col_name not in ("Date", ""):
                    if i < len(last_row):
                        val = _parse_farside_flow(last_row[i])
                        by_etf[col_name] = val

            daily_total = _parse_farside_flow(last_row[total_col]) if total_col and total_col < len(last_row) else sum(by_etf.values())

            cum_total = None
            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if cells and cells[0] == "Total" and total_col and total_col < len(cells):
                    cum_total = _parse_farside_flow(cells[total_col])
                    break

            result = {
                "last_date": last_date,
                "daily_total_m": daily_total,
                "daily_total_fmt": fmt_large(daily_total * 1e6),
                "daily_total_raw": daily_total * 1e6,
                "by_etf": by_etf,
                "cumulative_total_m": cum_total,
                "cumulative_fmt": fmt_large(cum_total * 1e6) if cum_total else "N/A",
                "direction": "up" if daily_total > 0 else "down" if daily_total < 0 else "neutral",
                "source": f"farside.co.uk — {asset_name} ETF Flows",
            }
            _save_farside_cache(asset_name, result)
            return result

        except Exception as e:
            print(f"[Crypto] Farside {asset_name} tentativo {attempt+1}/3: {e}")

    print(f"[Crypto] Farside {asset_name}: tutti i tentativi falliti, nessun dato disponibile")
    return None


def get_btc_etf_flows():
    """BTC spot ETF flows da farside.co.uk + AUM da yfinance."""
    print("[Crypto] Fetching BTC ETF flows (farside.co.uk)...")
    farside = _fetch_farside("https://farside.co.uk/bitcoin-etf-flow-all-data/", "BTC")

    # AUM dai principali ETF BTC via yfinance
    btc_etfs = {
        "IBIT": "iShares Bitcoin Trust",
        "FBTC": "Fidelity Wise Origin Bitcoin",
        "GBTC": "Grayscale Bitcoin Trust",
        "ARKB": "ARK 21Shares Bitcoin ETF",
        "BITB": "Bitwise Bitcoin ETF",
    }
    etf_aum = {}
    total_aum = 0
    for sym, name in btc_etfs.items():
        try:
            t = yf.Ticker(sym)
            aum = t.info.get("totalAssets")
            price = getattr(t.fast_info, "last_price", None)
            prev = getattr(t.fast_info, "previous_close", None)
            pct = ((price - prev) / prev * 100) if price and prev and prev > 0 else None
            if aum:
                total_aum += aum
            etf_aum[sym] = {
                "name": name,
                "aum": fmt_large(aum) if aum else "N/A",
                "price_fmt": f"${price:.2f}" if price else "N/A",
                "pct_fmt": f"{'+' if (pct or 0) >= 0 else ''}{pct:.2f}%" if pct is not None else "N/A",
                "direction": "up" if (pct or 0) > 0 else "down" if (pct or 0) < 0 else "neutral",
            }
        except Exception:
            etf_aum[sym] = {"name": name, "aum": "N/A", "price_fmt": "N/A", "pct_fmt": "N/A"}

    result = {
        "farside": farside,
        "etf_aum": etf_aum,
        "total_aum": fmt_large(total_aum) if total_aum else "N/A",
        "source": "farside.co.uk + Yahoo Finance",
        "url": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    }

    if farside:
        result["total_inflow_raw"] = farside["daily_total_raw"]
        result["total_inflow_24h"] = farside["daily_total_fmt"]
        result["total_direction"] = farside["direction"]

    return result


def get_eth_etf_flows():
    """ETH spot ETF flows da farside.co.uk."""
    print("[Crypto] Fetching ETH ETF flows (farside.co.uk)...")
    farside = _fetch_farside("https://farside.co.uk/ethereum-etf-flow-all-data/", "ETH")

    eth_etfs = {
        "ETHA": "iShares Ethereum Trust",
        "FETH": "Fidelity Ethereum Fund",
        "ETHW": "Bitwise Ethereum ETF",
        "CETH": "21Shares Core Ethereum ETF",
        "ETHU": "ProShares Ethereum ETF",
    }
    etf_aum = {}
    total_aum = 0
    for sym, name in eth_etfs.items():
        try:
            t = yf.Ticker(sym)
            aum = t.info.get("totalAssets")
            price = getattr(t.fast_info, "last_price", None)
            prev = getattr(t.fast_info, "previous_close", None)
            pct = ((price - prev) / prev * 100) if price and prev and prev > 0 else None
            if aum:
                total_aum += aum
            etf_aum[sym] = {
                "name": name,
                "aum": fmt_large(aum) if aum else "N/A",
                "price_fmt": f"${price:.2f}" if price else "N/A",
                "pct_fmt": f"{'+' if (pct or 0) >= 0 else ''}{pct:.2f}%" if pct is not None else "N/A",
                "direction": "up" if (pct or 0) > 0 else "down" if (pct or 0) < 0 else "neutral",
            }
        except Exception:
            etf_aum[sym] = {"name": name, "aum": "N/A", "price_fmt": "N/A", "pct_fmt": "N/A"}

    result = {
        "farside": farside,
        "etf_aum": etf_aum,
        "total_aum": fmt_large(total_aum) if total_aum else "N/A",
        "source": "farside.co.uk + Yahoo Finance",
        "url": "https://farside.co.uk/ethereum-etf-flow-all-data/",
    }
    if farside:
        result["total_inflow_raw"] = farside["daily_total_raw"]
        result["total_inflow_24h"] = farside["daily_total_fmt"]
        result["total_direction"] = farside["direction"]

    return result


def get_sol_etf_flows():
    """
    SOL spot ETF flows da farside.co.uk + AUM da yfinance.
    ETF approvati: BSOL, GSOL, FSOL, VSOL, SOEZ, QSOL, TSOL, SOLC
    """
    print("[Crypto] Fetching SOL ETF flows (farside.co.uk)...")

    # farside usa /sol/ per Solana (URL diverso da BTC/ETH)
    farside = _fetch_farside("https://farside.co.uk/sol/", "SOL")

    sol_etfs = {
        "BSOL": "Bitwise Solana ETF",
        "GSOL": "Grayscale Solana Trust",
        "FSOL": "Fidelity Solana ETF",
        "VSOL": "VanEck Solana ETF",
        "SOEZ": "Franklin Solana ETF",
        "QSOL": "Invesco Solana ETF",
        "TSOL": "21Shares Solana ETF",
        "SOLC": "Canary Solana ETF",
    }
    etf_aum = {}
    total_aum = 0
    for sym, name in sol_etfs.items():
        try:
            t = yf.Ticker(sym)
            aum = t.info.get("totalAssets")
            price = getattr(t.fast_info, "last_price", None)
            prev = getattr(t.fast_info, "previous_close", None)
            pct = ((price - prev) / prev * 100) if price and prev and prev > 0 else None
            if aum:
                total_aum += aum
            etf_aum[sym] = {
                "name": name,
                "aum": fmt_large(aum) if aum else "N/A",
                "price_fmt": f"${price:.2f}" if price else "N/A",
                "pct_fmt": f"{'+' if (pct or 0) >= 0 else ''}{pct:.2f}%" if pct is not None else "N/A",
                "direction": "up" if (pct or 0) > 0 else "down" if (pct or 0) < 0 else "neutral",
            }
        except Exception:
            etf_aum[sym] = {"name": name, "aum": "N/A", "price_fmt": "N/A", "pct_fmt": "N/A"}

    result = {
        "farside": farside,
        "etf_aum": etf_aum,
        "total_aum": fmt_large(total_aum) if total_aum else "N/A",
        "source": "farside.co.uk + Yahoo Finance",
        "url": "https://farside.co.uk/sol/",
    }
    if farside:
        result["total_inflow_raw"] = farside["daily_total_raw"]
        result["total_inflow_24h"] = farside["daily_total_fmt"]
        result["total_direction"] = farside["direction"]
    else:
        # Fallback: tutto zero (SOL ETF ancora piccoli, flows spesso $0)
        result["total_inflow_raw"] = 0
        result["total_inflow_24h"] = "$0.00M"
        result["total_direction"] = "neutral"

    return result


# ─────────────────────────────────────────────────────────────
# COINGLASS: Liquidazioni
# ─────────────────────────────────────────────────────────────

def get_liquidations_and_oi():
    """
    Liquidazioni + Open Interest + Funding Rate senza API key.

    Fonti:
    - OKX public API: liquidazione ordini recenti per BTC, ETH, SOL
    - Binance FAPI: open interest + funding rate (public, no key)
    - CoinGlass API (opzionale, se key configurata): dati 24h aggregati precisi

    NOTA: OKX restituisce gli ultimi ~100 ordini di liquidazione (non il totale 24h).
    Usa il dato come indicatore direzionale (long vs short dominanti).
    Per il totale 24h preciso → link CoinGlass.
    """
    print("[Crypto] Fetching liquidations + OI + funding rates...")
    result = {}

    okx_map = {"BTC": "BTC-USD", "ETH": "ETH-USD", "SOL": "SOL-USD"}
    binance_map = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}
    headers = {"User-Agent": "Mozilla/5.0"}

    for sym in ["BTC", "ETH", "SOL"]:
        entry = {
            "long_raw": 0, "short_raw": 0,
            "long_24h": "—", "short_24h": "—", "total_24h": "—",
            "open_interest": "N/A",
            "funding_rate": "N/A",
            "funding_direction": "neutral",
            "source": "OKX + Binance (public)",
            "url": f"https://www.coinglass.com/LiquidationData",
        }

        # ── OKX: liquidazioni recenti (indicatore direzionale) ──
        try:
            uly = okx_map[sym]
            resp = requests.get(
                "https://www.okx.com/api/v5/public/liquidation-orders",
                params={"instType": "SWAP", "uly": uly, "state": "filled", "limit": 100},
                headers=headers, timeout=10,
            )
            details = resp.json().get("data", [{}])[0].get("details", [])
            long_liq_usd = 0.0
            short_liq_usd = 0.0
            for d in details:
                sz = float(d.get("sz", 0))
                px = float(d.get("bkPx", 0))
                usd_val = sz * px
                if d.get("posSide") == "long":
                    long_liq_usd += usd_val   # long liquidated = sold
                else:
                    short_liq_usd += usd_val  # short liquidated = bought

            total_usd = long_liq_usd + short_liq_usd
            entry.update({
                "long_raw": long_liq_usd,
                "short_raw": short_liq_usd,
                "long_24h": fmt_large(long_liq_usd),
                "short_24h": fmt_large(short_liq_usd),
                "total_24h": fmt_large(total_usd),
                "liq_note": f"Ultimo campione OKX (~100 ordini). Long liq = pressione ribassista. Short liq = short squeeze.",
            })
        except Exception as e:
            print(f"[Crypto] OKX liq error {sym}: {e}")

        # ── Binance FAPI: Open Interest ──
        try:
            b_sym = binance_map[sym]
            oi_resp = requests.get(
                f"https://fapi.binance.com/fapi/v1/openInterest?symbol={b_sym}",
                headers=headers, timeout=8,
            )
            oi_data = oi_resp.json()
            oi_val = float(oi_data.get("openInterest", 0))
            # Get current price to convert to USD
            price_resp = requests.get(
                f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={b_sym}",
                headers=headers, timeout=8,
            )
            price_val = float(price_resp.json().get("price", 0))
            oi_usd = oi_val * price_val
            entry["open_interest"] = fmt_large(oi_usd)
        except Exception as e:
            print(f"[Crypto] Binance OI error {sym}: {e}")

        # ── Binance FAPI: Funding Rate ──
        try:
            b_sym = binance_map[sym]
            fr_resp = requests.get(
                f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={b_sym}&limit=1",
                headers=headers, timeout=8,
            )
            fr_data = fr_resp.json()
            if fr_data:
                fr = float(fr_data[0].get("fundingRate", 0))
                fr_annualized = fr * 3 * 365 * 100  # 3 funding/day, annualizzato
                direction = "positive" if fr > 0 else "negative" if fr < 0 else "neutral"
                note = "Longs pagano Shorts (mercato long-biased)" if fr > 0 else "Shorts pagano Longs (mercato short-biased)"
                entry["funding_rate"] = f"{fr*100:.4f}% ({fr_annualized:.1f}% ann.)"
                entry["funding_direction"] = direction
                entry["funding_note"] = note
        except Exception as e:
            print(f"[Crypto] Binance funding rate error {sym}: {e}")

        # ── CoinGlass (se key disponibile) ──
        if config.COINGLASS_API_KEY and config.COINGLASS_API_KEY != "YOUR_COINGLASS_API_KEY_HERE":
            try:
                cg_headers = {"CG-API-KEY": config.COINGLASS_API_KEY}
                cg_resp = requests.get(
                    "https://open-api.coinglass.com/public/v2/liquidation_symbol",
                    params={"symbol": sym, "time_type": "h24"},
                    headers=cg_headers, timeout=10,
                )
                cg_data = cg_resp.json().get("data", {})
                long_liq = float(cg_data.get("longLiquidationUsd", 0) or 0)
                short_liq = float(cg_data.get("shortLiquidationUsd", 0) or 0)
                entry.update({
                    "long_raw": long_liq,
                    "short_raw": short_liq,
                    "long_24h": fmt_large(long_liq),
                    "short_24h": fmt_large(short_liq),
                    "total_24h": fmt_large(long_liq + short_liq),
                    "source": "CoinGlass (24h aggregato)",
                    "liq_note": "Dati 24h aggregati multi-exchange.",
                })
            except Exception:
                pass

        result[sym] = entry

    return result


# ─────────────────────────────────────────────────────────────
# FEAR & GREED: alternative.me
# ─────────────────────────────────────────────────────────────

def get_crypto_fear_greed():
    """
    Crypto Fear & Greed Index da alternative.me (API pubblica).
    NOTA: Indice alternativo al CMC F&G — metodologie diverse, valori possono differire.
    CMC F&G richiede API key (pro.coinmarketcap.com).
    """
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=2", timeout=10)
        resp.raise_for_status()
        items = resp.json().get("data", [])
        if not items:
            raise ValueError("No data")
        current = items[0]
        previous = items[1] if len(items) > 1 else items[0]
        score = int(current["value"])
        label = current["value_classification"]
        prev_score = int(previous["value"])
        color_map = {
            "Extreme Fear": "#e74c3c",
            "Fear": "#e67e22",
            "Neutral": "#f1c40f",
            "Greed": "#2ecc71",
            "Extreme Greed": "#27ae60",
        }
        return {
            "score": score,
            "label": label,
            "color": color_map.get(label, "#888"),
            "prev_score": prev_score,
            "source": "alternative.me",
            "note": "Indice alternativo — CMC F&G può differire",
        }
    except Exception as e:
        print(f"[Crypto] F&G error: {e}")
        return {"score": None, "label": "N/A", "color": "#888", "source": "alternative.me"}


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def get_all_crypto_data():
    prices = get_crypto_prices()
    btc_etf = get_btc_etf_flows()
    time.sleep(2)
    eth_etf = get_eth_etf_flows()
    time.sleep(2)
    sol_etf = get_sol_etf_flows()
    liquidations = get_liquidations_and_oi()
    fear_greed = get_crypto_fear_greed()
    return {
        "prices": prices,
        "btc_etf": btc_etf,
        "eth_etf": eth_etf,
        "sol_etf": sol_etf,
        "liquidations": liquidations,
        "fear_greed": fear_greed,
    }
