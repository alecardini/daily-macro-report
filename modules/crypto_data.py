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
                # farside dà i flussi in MILIONI arrotondati a 0.1M. Per i flussi <$1M (es. SOL)
                # mostrare "$200,000" è falsa precisione (in realtà è ~$0.15-0.2M): sotto $1M
                # mostriamo "$0.2M" (precisione reale della fonte); ≥$1M invariato (BTC/ETH).
                "daily_total_fmt": (fmt_large(daily_total * 1e6) if abs(daily_total) >= 1
                                    else f"{'-' if daily_total < 0 else ''}${abs(daily_total):.1f}M"),
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

# ─────────────────────────────────────────────────────────────
# COINALYZE — derivati crypto aggregati multi-exchange (funding, OI, liquidazioni)
# ─────────────────────────────────────────────────────────────

_COINALYZE_BASE   = "https://api.coinalyze.net/v1"
_CZ_MARKETS_CACHE = "/tmp/coinalyze_markets_cache.json"
_CZ_MARKETS_TTL   = 7 * 24 * 3600      # lista mercati cambia raramente
_CZ_DERIV_CACHE   = "/tmp/coinalyze_deriv_cache.json"
_CZ_DERIV_TTL     = 30 * 60            # evita di rifare ~12 call su rigenerazioni ravvicinate

# Pacing ADATTIVO condiviso: invece di martellare e poi fare backoff (che alimenta il
# throttle), teniamo un gap minimo tra chiamate e lo ALLARGHIAMO quando becchiamo un 429.
# Così ci auto-tariamo sul rate reale di Coinalyze (qualunque sia) e le chiamate passano al
# primo colpo → dati completi nel tempo minimo. Stato per-processo (si ri-tara ogni run).
_CZ_MIN_GAP = 2.0     # spaziatura iniziale tra chiamate (s)
_CZ_MAX_GAP = 10.0    # tetto della cadenza adattiva
_cz_pace = {"gap": _CZ_MIN_GAP, "last": 0.0}


def _cz_get(ep, **params):
    key = getattr(config, "COINALYZE_API_KEY", "")
    if not key or key == "YOUR_COINALYZE_API_KEY_HERE":
        return None
    params["api_key"] = key
    for attempt in range(2):     # 1 chiamata + 1 retry EFFICIENTE (attesa lunga singola)
        # pacing: rispetta il gap corrente dall'ultima chiamata
        wait = _cz_pace["gap"] - (time.time() - _cz_pace["last"])
        if wait > 0:
            time.sleep(wait)
        try:
            r = requests.get(_COINALYZE_BASE + ep, params=params, timeout=15)
            _cz_pace["last"] = time.time()
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                # adattivo: rallenta la cadenza per TUTTE le chiamate successive
                _cz_pace["gap"] = min(_CZ_MAX_GAP, _cz_pace["gap"] * 1.6)
                if attempt == 0:
                    time.sleep(15)   # attesa lunga: la finestra rientra → il retry passa
                    continue
        except Exception:
            _cz_pace["last"] = time.time()
            if attempt == 0:
                time.sleep(5); continue
        return None
    return None

def _cz_perp_symbols():
    """Lista symbol perp per BTC/ETH/SOL + mappa symbol→base. Cache 7 giorni."""
    try:
        with open(_CZ_MARKETS_CACHE) as f:
            c = json.load(f)
        if time.time() - c["_ts"] < _CZ_MARKETS_TTL:
            return c["data"]
    except Exception:
        pass
    mk = _cz_get("/future-markets")
    if not isinstance(mk, list):
        return None
    by_base, sym2base = {}, {}
    for base in ("BTC", "ETH", "SOL"):
        syms = [m["symbol"] for m in mk if m.get("base_asset") == base and m.get("is_perpetual")]
        by_base[base] = syms
        for s in syms:
            sym2base[s] = base
    data = {"by_base": by_base, "sym2base": sym2base}
    try:
        with open(_CZ_MARKETS_CACHE, "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass
    return data

def _cz_chunks(lst, n=20):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

def _funding_label(fr_pct):
    """fr_pct = funding rate in % per 8h. Bande fisse convenzionali (funding = metrica recente, no standard desk)."""
    if fr_pct > 0.05:
        return "Overheated Longs", "warning"      # leva long affollata, rischio squeeze/reversal
    elif fr_pct >= 0.01:
        return "Bullish Positioning", "positive"
    elif fr_pct > -0.01:
        return "Neutral", "neutral"
    else:
        return "Shorts Crowded", "negative"       # potenziale short squeeze (contrarian)

def _get_coinalyze_derivatives():
    """
    OI + funding + liquidazioni 24h AGGREGATI multi-exchange da Coinalyze.
    Ritorna {sym: {...campi...}} oppure {} se non disponibile (→ fallback Binance/OKX).
    Cache 30 min su disco per non rifare ~12 call su rigenerazioni ravvicinate.
    """
    # cache
    try:
        with open(_CZ_DERIV_CACHE) as f:
            c = json.load(f)
        if time.time() - c["_ts"] < _CZ_DERIV_TTL:
            return c["data"]
    except Exception:
        pass

    mkt = _cz_perp_symbols()
    if not mkt:
        return {}
    sym2base = mkt["sym2base"]
    all_syms = [s for syms in mkt["by_base"].values() for s in syms]
    if not all_syms:
        return {}

    now = int(time.time())
    agg = {b: {"oi_now": 0.0, "oi_prev": 0.0, "fr": [], "long": 0.0, "short": 0.0,
               "has_oi": False, "has_fr": False, "has_liq": False} for b in ("BTC", "ETH", "SOL")}

    # Accumulatori per-endpoint: ognuno ritorna True se il chunk ha risposto (lista, anche
    # vuota), False se None (429/errore) → il chunk fallito va nella retry-pass.
    def _acc_oi(data):
        if not isinstance(data, list):
            return False
        for item in data:
            b = sym2base.get(item.get("symbol")); hist = item.get("history", [])
            if b and hist:
                agg[b]["oi_now"]  += hist[-1].get("c", 0) or 0
                agg[b]["oi_prev"] += (hist[-2].get("c", 0) if len(hist) >= 2 else hist[-1].get("c", 0)) or 0
                agg[b]["has_oi"] = True
        return True

    def _acc_fr(data):
        if not isinstance(data, list):
            return False
        for item in data:
            b = sym2base.get(item.get("symbol")); v = item.get("value")
            if b and v is not None:
                agg[b]["fr"].append(float(v)); agg[b]["has_fr"] = True
        return True

    def _acc_liq(data):
        if not isinstance(data, list):
            return False
        for item in data:
            b = sym2base.get(item.get("symbol"))
            if b:
                for h in item.get("history", []):
                    agg[b]["long"]  += h.get("l", 0) or 0
                    agg[b]["short"] += h.get("s", 0) or 0
                    agg[b]["has_liq"] = True
        return True

    def _fetch_all(ep, extra, acc):
        """Fetch tutti i chunk per un endpoint (pacing adattivo in _cz_get) + RETRY-PASS sui
        chunk falliti dopo cooldown → COMPLETEZZA garantita: nessun asset azzerato da un 429.
        Con il pacing la retry-pass scatta di rado (fresh run: quasi mai)."""
        failed = [c for c in _cz_chunks(all_syms) if not acc(_cz_get(ep, symbols=",".join(c), **extra))]
        if failed:
            time.sleep(12)
            for c in failed:
                acc(_cz_get(ep, symbols=",".join(c), **extra))

    # OI daily (last vs prev close = livello + 24h). Liq interval ORARIO = vera finestra rolling
    # 24h (il daily è etichettato a mezzanotte UTC → scartava il giorno prima, sommava parziale).
    _fetch_all("/open-interest-history", {"interval": "daily", "from": now - 3 * 24 * 3600, "to": now, "convert_to_usd": "true"}, _acc_oi)
    _fetch_all("/funding-rate", {}, _acc_fr)
    _fetch_all("/liquidation-history", {"interval": "1hour", "from": now - 24 * 3600, "to": now, "convert_to_usd": "true"}, _acc_liq)

    out = {}
    for b, a in agg.items():
        e = {}
        if a["has_oi"] and a["oi_now"] > 0:
            e["open_interest"] = fmt_large(a["oi_now"])
            if a["oi_prev"] > 0:
                chg = (a["oi_now"] - a["oi_prev"]) / a["oi_prev"] * 100
                e["oi_change_fmt"] = f"{chg:+.1f}%"
                e["oi_change_dir"] = "positive" if chg > 0 else "negative" if chg < 0 else "neutral"
        if a["has_fr"] and a["fr"]:
            avg = sum(a["fr"]) / len(a["fr"])
            ann = avg * 3 * 365   # % per 8h → annualizzato (3 funding/giorno)
            label, dirn = _funding_label(avg)
            e["funding_rate"] = f"{avg:.4f}% ({ann:.1f}% ann.)"
            e["funding_direction"] = dirn
            e["funding_note"] = label
        if a["has_liq"] and (a["long"] > 0 or a["short"] > 0):
            e["long_raw"] = a["long"]; e["short_raw"] = a["short"]
            e["long_24h"] = fmt_large(a["long"]); e["short_24h"] = fmt_large(a["short"])
            e["total_24h"] = fmt_large(a["long"] + a["short"])
            e["liq_note"] = "24h aggregated multi-exchange (Coinalyze)"
        if e:
            e["source"] = "Coinalyze (aggregated)"
            out[b] = e

    if out:
        try:
            with open(_CZ_DERIV_CACHE, "w") as f:
                json.dump({"_ts": time.time(), "data": out}, f)
        except Exception:
            pass
    return out


def get_liquidations_and_oi():
    """
    Liquidazioni + Open Interest + Funding Rate.
    PRIMARIO: Coinalyze aggregato multi-exchange (funding, OI + change 24h, liquidazioni 24h).
    FALLBACK per campo mancante: OKX (liq campione) + Binance FAPI (OI + funding single-exchange).
    """
    print("[Crypto] Fetching derivatives (Coinalyze aggregated, fallback Binance/OKX)...")
    coinalyze = _get_coinalyze_derivatives()
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
            "url": "https://www.coinglass.com/LiquidationData",
        }
        cz = coinalyze.get(sym)
        if cz:
            entry.update(cz)

        # ── Fallback OKX: liquidazioni campione (solo se Coinalyze non le ha date) ──
        if entry.get("total_24h") in ("—", "N/A", ""):
            try:
                uly = okx_map[sym]
                resp = requests.get(
                    "https://www.okx.com/api/v5/public/liquidation-orders",
                    params={"instType": "SWAP", "uly": uly, "state": "filled", "limit": 100},
                    headers=headers, timeout=10,
                )
                details = resp.json().get("data", [{}])[0].get("details", [])
                long_liq_usd = short_liq_usd = 0.0
                for d in details:
                    usd_val = float(d.get("sz", 0)) * float(d.get("bkPx", 0))
                    if d.get("posSide") == "long":
                        long_liq_usd += usd_val
                    else:
                        short_liq_usd += usd_val
                entry.update({
                    "long_raw": long_liq_usd, "short_raw": short_liq_usd,
                    "long_24h": fmt_large(long_liq_usd), "short_24h": fmt_large(short_liq_usd),
                    "total_24h": fmt_large(long_liq_usd + short_liq_usd),
                    "liq_note": "OKX sample (~100 orders, fallback). Long liq = downside pressure. Short liq = short squeeze.",
                })
            except Exception as e:
                print(f"[Crypto] OKX liq fallback error {sym}: {e}")

        # ── Fallback Binance: Open Interest (solo se mancante) ──
        if entry.get("open_interest") in ("N/A", None):
            try:
                b_sym = binance_map[sym]
                oi_val = float(requests.get(
                    f"https://fapi.binance.com/fapi/v1/openInterest?symbol={b_sym}",
                    headers=headers, timeout=8).json().get("openInterest", 0))
                price_val = float(requests.get(
                    f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={b_sym}",
                    headers=headers, timeout=8).json().get("price", 0))
                entry["open_interest"] = fmt_large(oi_val * price_val)
            except Exception as e:
                print(f"[Crypto] Binance OI fallback error {sym}: {e}")

        # ── Fallback Binance: Funding Rate (solo se mancante) ──
        if entry.get("funding_rate") in ("N/A", None):
            try:
                b_sym = binance_map[sym]
                fr_data = requests.get(
                    f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={b_sym}&limit=1",
                    headers=headers, timeout=8).json()
                if fr_data:
                    fr = float(fr_data[0].get("fundingRate", 0)) * 100  # → % per 8h
                    label, dirn = _funding_label(fr)
                    entry["funding_rate"] = f"{fr:.4f}% ({fr*3*365:.1f}% ann.)"
                    entry["funding_direction"] = dirn
                    entry["funding_note"] = label
            except Exception as e:
                print(f"[Crypto] Binance funding fallback error {sym}: {e}")

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
            "note": "Alternative index — CMC F&G may differ",
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


# ─────────────────────────────────────────────────────────────
# STABLECOIN LIQUIDITY (DefiLlama) — proxy della "dry powder" crypto
# ─────────────────────────────────────────────────────────────

_STABLE_CACHE_PATH = "/tmp/stablecoin_liquidity_cache.json"
_STABLE_CACHE_TTL = 6 * 3600  # 6h

def _load_stable_cache():
    try:
        with open(_STABLE_CACHE_PATH) as f:
            c = json.load(f)
        return c.get("data"), time.time() - c.get("_ts", 0)
    except Exception:
        return None, None

def _save_stable_cache(data):
    try:
        with open(_STABLE_CACHE_PATH, "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass

def _stable_label(pct30):
    """Soglie data-driven dalla distribuzione netflow 30g ultimi 12 mesi (DefiLlama).
    La supply ha drift strutturale ~+1.3%/mese, quindi il neutro NON è zero."""
    if pct30 < -0.5:
        return "Liquidity Contracting", "negative"   # quintile basso → headwind
    elif pct30 <= 5.0:
        return "Normal", "neutral"                     # in linea col drift
    else:
        return "Liquidity Expanding", "positive"       # quintile alto → tailwind

def get_stablecoin_liquidity():
    """
    Total stablecoin supply (USDT+USDC+...) + 7d/30d netflows da DefiLlama.
    Proxy della liquidità / dry powder che entra o esce dal sistema crypto.
    Tier A, no key. Cache 6h + fallback stale (max 24h). Percentile netflow 30g vs storia.
    """
    cached, age = _load_stable_cache()
    try:
        h = {"User-Agent": "Mozilla/5.0"}
        r = requests.get("https://stablecoins.llama.fi/stablecoincharts/all", headers=h, timeout=20)
        r.raise_for_status()
        data = r.json()

        def tot(x):
            p = x.get("totalCirculatingUSD", {})
            return sum(p.values()) if isinstance(p, dict) else float(p)

        series = [tot(x) for x in data if tot(x) > 0]
        cur = series[-1]
        d7  = series[-8]  if len(series) >= 8  else series[0]
        d30 = series[-31] if len(series) >= 31 else series[0]
        nf7_pct  = (cur - d7)  / d7  * 100 if d7  else 0
        nf30_pct = (cur - d30) / d30 * 100 if d30 else 0

        # percentile del netflow 30g corrente vs tutta la storia DefiLlama
        hist30 = [(series[i] - series[i-30]) / series[i-30] * 100
                  for i in range(30, len(series)) if series[i-30] > 0]
        pctile = sum(1 for v in hist30 if v < nf30_pct) / len(hist30) * 100 if hist30 else None
        label, direction = _stable_label(nf30_pct)

        # breakdown top-3 stablecoin
        breakdown = []
        try:
            r2 = requests.get("https://stablecoins.llama.fi/stablecoins?includePrices=true", headers=h, timeout=20)
            pegged = r2.json().get("peggedAssets", [])
            top = sorted(pegged, key=lambda a: a.get("circulating", {}).get("peggedUSD", 0), reverse=True)[:3]
            breakdown = [{"symbol": a["symbol"], "cap_fmt": f"${a['circulating']['peggedUSD']/1e9:.0f}B"} for a in top]
        except Exception:
            pass

        result = {
            "total_fmt":    f"${cur/1e9:.1f}B",
            "nf7_pct_fmt":  f"{nf7_pct:+.2f}%",
            "nf7_abs_fmt":  f"${(cur-d7)/1e9:+.1f}B",
            "nf7_dir":      "positive" if nf7_pct > 0 else "negative" if nf7_pct < 0 else "neutral",
            "nf30_pct_fmt": f"{nf30_pct:+.2f}%",
            "nf30_abs_fmt": f"${(cur-d30)/1e9:+.1f}B",
            "nf30_dir":     direction,
            "pctile_fmt":   f"{pctile:.0f}th pctile" if pctile is not None else "",
            "label":        label,
            "breakdown":    breakdown,
            "source":       "DefiLlama",
        }
        _save_stable_cache(result)
        return result
    except Exception as e:
        print(f"[Crypto] Stablecoin liquidity error: {e}")
        if cached and age is not None and age < 24 * 3600:
            print(f"[Crypto] Stablecoin: using cache ({int(age/3600)}h old) as fallback")
            return cached
        return {"total_fmt": "N/A", "label": "data not available", "breakdown": [], "source": "DefiLlama"}
