"""
Extras Module

- Deribit Put/Call ratio (BTC + ETH) — API pubblica
- Earnings settimana corrente (yfinance calendar) — come breaking news
- Asia session indices (yfinance) + overnight recap
- F&G combinato (average alternative.me + CMC se disponibile)
"""

import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta, date
import pytz
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ROME_TZ = pytz.timezone("Europe/Rome")

# ─────────────────────────────────────────────────────────────
# DERIBIT: Put/Call Ratio
# ─────────────────────────────────────────────────────────────

_PC_CACHE_TTL = 4 * 3600  # 4 ore — P/C cambia durante la giornata

def _pc_cache_path(currency):
    return f"/tmp/deribit_pc_{currency.lower()}_cache.json"

def _load_pc_cache(currency):
    try:
        with open(_pc_cache_path(currency)) as f:
            cached = json.load(f)
        age = time.time() - cached.get("_ts", 0)
        return cached.get("data"), age
    except Exception:
        return None, None

def _save_pc_cache(currency, data):
    try:
        with open(_pc_cache_path(currency), "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass

def get_deribit_pc_ratio(currency="BTC"):
    """
    Calcola Put/Call ratio da Deribit (API pubblica, no key).
    Cache 4h su disco. Se API non risponde usa ultimo dato disponibile (max 24h).
    """
    cached_data, cache_age = _load_pc_cache(currency)

    try:
        resp = requests.get(
            "https://www.deribit.com/api/v2/public/get_book_summary_by_currency",
            params={"currency": currency, "kind": "option"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        resp.raise_for_status()
        instruments = resp.json().get("result", [])

        put_vol = sum(float(x.get("volume", 0) or 0) for x in instruments if x.get("instrument_name", "").endswith("-P"))
        call_vol = sum(float(x.get("volume", 0) or 0) for x in instruments if x.get("instrument_name", "").endswith("-C"))
        put_oi = sum(float(x.get("open_interest", 0) or 0) for x in instruments if x.get("instrument_name", "").endswith("-P"))
        call_oi = sum(float(x.get("open_interest", 0) or 0) for x in instruments if x.get("instrument_name", "").endswith("-C"))

        pc_vol = put_vol / call_vol if call_vol > 0 else None
        pc_oi = put_oi / call_oi if call_oi > 0 else None

        def interpret(ratio):
            # Threshold istituzionali (Deribit Insights, Greeks.live, Flipster)
            # Crypto baseline "neutro" è ~0.70, non 1.0 come in equity
            if ratio is None:
                return "N/A", "neutral"
            if ratio < 0.40:
                return "⚠ Euforia Estrema", "warning"       # call frenzy — possibile top
            elif ratio < 0.50:
                return "Bullish / Call Dominance", "positive"
            elif ratio < 0.65:
                return "Moderatamente Bullish", "positive"   # range normale bull run Deribit
            elif ratio < 0.75:
                return "Neutro", "neutral"                   # baseline crypto-adjusted
            elif ratio < 0.90:
                return "Cauto / Hedge in Aumento", "neutral"
            elif ratio < 1.00:
                return "Bearish / Posizionamento Difensivo", "negative"
            elif ratio < 1.20:
                return "Paura Elevata", "negative"
            else:
                return "⚠ Paura Estrema / Possibile Bottom", "warning"

        vol_label, vol_dir = interpret(pc_vol)
        oi_label, oi_dir = interpret(pc_oi)

        return {
            "currency": currency,
            "pc_volume": round(pc_vol, 3) if pc_vol else None,
            "pc_volume_fmt": f"{pc_vol:.3f}" if pc_vol else "N/A",
            "pc_volume_label": vol_label,
            "pc_volume_dir": vol_dir,
            "pc_oi": round(pc_oi, 3) if pc_oi else None,
            "pc_oi_fmt": f"{pc_oi:.3f}" if pc_oi else "N/A",
            "pc_oi_label": oi_label,
            "pc_oi_dir": oi_dir,
            "put_oi_contracts": int(put_oi),
            "call_oi_contracts": int(call_oi),
            "source": "Deribit (public API)",
        }
        _save_pc_cache(currency, result)
        return result
    except Exception as e:
        print(f"[Extras] Deribit P/C error ({currency}): {e}")
        if cached_data and cache_age is not None and cache_age < 24 * 3600:
            print(f"[Extras] Deribit P/C {currency}: uso cache ({int(cache_age/3600)}h fa) come fallback")
            return cached_data
        return {"currency": currency, "pc_volume_fmt": "N/A", "pc_oi_fmt": "N/A", "source": "Deribit"}


# ─────────────────────────────────────────────────────────────
# DERIBIT: DVOL (implied volatility index — the "crypto VIX")
# ─────────────────────────────────────────────────────────────

_DVOL_CACHE_TTL = 4 * 3600  # 4h, come il P/C

def _dvol_cache_path(currency):
    return f"/tmp/deribit_dvol_{currency.lower()}_cache.json"

def _load_dvol_cache(currency):
    try:
        with open(_dvol_cache_path(currency)) as f:
            cached = json.load(f)
        age = time.time() - cached.get("_ts", 0)
        return cached.get("data"), age
    except Exception:
        return None, None

def _save_dvol_cache(currency, data):
    try:
        with open(_dvol_cache_path(currency), "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass

# Soglie DVOL separate per asset (ETH gira strutturalmente ~+12 pt su BTC)
_DVOL_BANDS = {
    "BTC": (40, 55, 70),
    "ETH": (52, 67, 82),
}

def _interpret_dvol(currency, value):
    if value is None:
        return "N/A", "neutral"
    low, normal, elevated = _DVOL_BANDS.get(currency, _DVOL_BANDS["BTC"])
    if value < low:
        return "Low Vol / Complacency", "positive"
    elif value < normal:
        return "Normal Range", "neutral"
    elif value < elevated:
        return "Elevated / Rising Stress", "negative"
    else:
        return "High Vol / Fear Priced In", "warning"

def get_dvol(currency="BTC"):
    """
    Deribit DVOL — 30-day implied volatility index (the 'crypto VIX') for BTC/ETH.
    API pubblica, no key. Cache 4h + fallback stale (max 24h) come il P/C ratio.
    """
    cached_data, cache_age = _load_dvol_cache(currency)
    try:
        now   = int(time.time() * 1000)
        start = now - 2 * 24 * 3600 * 1000  # finestra 48h
        resp = requests.get(
            "https://www.deribit.com/api/v2/public/get_volatility_index_data",
            params={"currency": currency, "start_timestamp": start,
                    "end_timestamp": now, "resolution": "3600"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=12,
        )
        resp.raise_for_status()
        candles = resp.json().get("result", {}).get("data", [])
        if not candles:
            raise ValueError("empty DVOL data")

        latest = candles[-1][4]  # close dell'ultima candela oraria
        # valore ~24h fa: candela 25 posizioni indietro (24h + corrente), close per coerenza
        idx_24h = -25 if len(candles) >= 25 else 0
        ago_24h = candles[idx_24h][4]
        change  = latest - ago_24h
        label, direction = _interpret_dvol(currency, latest)

        result = {
            "dvol":            round(latest, 2),
            "dvol_fmt":        f"{latest:.1f}",
            "dvol_change":     round(change, 2),
            "dvol_change_fmt": f"{change:+.1f}",
            "dvol_label":      label,
            "dvol_dir":        direction,
        }
        _save_dvol_cache(currency, result)
        return result
    except Exception as e:
        print(f"[Extras] Deribit DVOL error ({currency}): {e}")
        if cached_data and cache_age is not None and cache_age < 24 * 3600:
            print(f"[Extras] DVOL {currency}: using cache ({int(cache_age/3600)}h old) as fallback")
            return cached_data
        return {"dvol_fmt": "N/A", "dvol_change_fmt": "—", "dvol_label": "N/A", "dvol_dir": "neutral"}


def get_pc_ratios():
    """BTC + ETH Put/Call ratios + DVOL (implied vol index)."""
    print("[Extras] Fetching Deribit P/C ratios + DVOL...")
    result = {}
    for cur in ("BTC", "ETH"):
        d = get_deribit_pc_ratio(cur)
        d.update(get_dvol(cur))
        result[cur] = d
    return result


# ─────────────────────────────────────────────────────────────
# EARNINGS: Prossime settimane — key stocks
# ─────────────────────────────────────────────────────────────

_STATIC_KEY_STOCKS = {
    # Mega Tech
    "NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft",
    "GOOGL": "Alphabet", "META": "Meta", "AMZN": "Amazon",
    "TSLA": "Tesla",
    # Finance
    "JPM": "JPMorgan", "GS": "Goldman Sachs", "BAC": "Bank of America",
    "MS": "Morgan Stanley",
    # Other market-moving
    "AMD": "AMD", "INTC": "Intel", "NFLX": "Netflix", "MU": "Micron",
}

# Crypto-proxy: NON sono nel Nasdaq-100 né nell'S&P top 100 (i miner quasi certamente
# fuori) → vanno tracciati ESPLICITAMENTE altrimenti l'utente non li vede mai. Sono i
# nomi che muovono il sentiment crypto (focus dell'utente).
_CRYPTO_PROXIES = {
    "COIN": "Coinbase", "MSTR": "MicroStrategy", "MARA": "MARA Holdings",
    "RIOT": "Riot Platforms", "CLSK": "CleanSpark", "HUT": "Hut 8",
    "CRCL": "Circle",   # emittente USDC
}

# Set per categorizzare gli earnings per RILEVANZA (tag colorato). Non esaustivi: i nomi
# non elencati ricadono in 'other'. crypto = focus utente; bigtech = risk sentiment; bank = credito.
_CAT_BIGTECH = {"NVDA", "AAPL", "MSFT", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "AMD",
                "AVGO", "MU", "INTC", "NFLX", "ADBE", "CRM", "ORCL", "CSCO", "QCOM",
                "TXN", "AMAT", "ARM", "SMCI", "PLTR"}
_CAT_BANK = {"JPM", "GS", "BAC", "MS", "WFC", "C", "BLK", "SCHW", "USB", "PNC",
             "TFC", "COF", "AXP", "BK", "STT"}


def _earnings_category(sym):
    """→ (category, tag_label). Ordine di priorità: crypto > bigtech > bank > other."""
    if sym in _CRYPTO_PROXIES:
        return "crypto", "CRYPTO"
    if sym in _CAT_BIGTECH:
        return "bigtech", "TECH"
    if sym in _CAT_BANK:
        return "bank", "BANK"
    return "other", ""

_TICKER_LIST_CACHE = "/tmp/earnings_ticker_universe_cache.json"
_TICKER_LIST_TTL   = 90 * 24 * 3600  # 90 giorni (~3 mesi) — rebuild costoso (~500 yfinance calls), va fatto raramente


def _fetch_nasdaq100():
    """Scrape Nasdaq-100 constituents from Wikipedia."""
    import pandas as pd, io
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    r = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100", headers=headers, timeout=20)
    tables = pd.read_html(io.StringIO(r.text))
    for t in tables:
        cols = [str(c) for c in t.columns]
        if "Ticker" in cols and "Company" in cols:
            return {row["Ticker"].replace(".", "-"): row["Company"] for _, row in t.iterrows()}
    return {}


def _fetch_sp500_top100_by_marketcap():
    """Scrape all S&P 500 tickers from Wikipedia, fetch market cap via yfinance, return top 100."""
    import pandas as pd, io
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=headers, timeout=20)
    tables = pd.read_html(io.StringIO(r.text))
    sp500_df = tables[0]
    pairs = [(row["Symbol"].replace(".", "-"), row["Security"]) for _, row in sp500_df.iterrows()]

    ranked = []
    for sym, name in pairs:
        try:
            mc = yf.Ticker(sym).fast_info.get("marketCap")
            if mc:
                ranked.append((sym, name, mc))
        except Exception:
            continue

    ranked.sort(key=lambda x: x[2], reverse=True)
    return {sym: name for sym, name, _ in ranked[:100]}


def _load_ticker_universe_cache():
    try:
        with open(_TICKER_LIST_CACHE) as f:
            cached = json.load(f)
        age = time.time() - cached.get("_ts", 0)
        if age < _TICKER_LIST_TTL:
            return cached.get("data")
        return None
    except Exception:
        return None


def _save_ticker_universe_cache(data):
    try:
        with open(_TICKER_LIST_CACHE, "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass


def _build_earnings_ticker_universe():
    """
    Build the full earnings tracking universe: NASDAQ-100 + S&P 500 top 100 by market cap.
    Cached on disk for 30 days — building the S&P 500 ranking requires ~500 yfinance calls (~8 min).
    """
    cached = _load_ticker_universe_cache()
    if cached:
        return cached

    print("[Extras] Building earnings ticker universe (Nasdaq-100 + S&P 500 top 100) — one-time, ~8-10 min...")
    universe = dict(_STATIC_KEY_STOCKS)
    try:
        universe.update(_fetch_nasdaq100())
    except Exception as e:
        print(f"[Extras] Nasdaq-100 fetch error: {e}")
    try:
        universe.update(_fetch_sp500_top100_by_marketcap())
    except Exception as e:
        print(f"[Extras] S&P 500 top 100 fetch error: {e}")

    if len(universe) > len(_STATIC_KEY_STOCKS):
        _save_ticker_universe_cache(universe)
        print(f"[Extras] Earnings ticker universe built: {len(universe)} companies (cached 90 days)")
        return universe
    print("[Extras] Failed to build ticker universe, falling back to static list")
    return _STATIC_KEY_STOCKS


KEY_STOCKS = _build_earnings_ticker_universe()
KEY_STOCKS.update(_CRYPTO_PROXIES)   # garantiti sempre, anche se non nel Nasdaq-100/S&P top 100


_EARNINGS_CACHE_PATH = "/tmp/earnings_results_cache.json"

def _load_earnings_cache():
    """Cache valida solo per la stessa data (ora Roma) — dati earnings cambiano giorno per giorno."""
    try:
        with open(_EARNINGS_CACHE_PATH) as f:
            cached = json.load(f)
        if cached.get("_date") == datetime.now(ROME_TZ).date().isoformat():
            return cached.get("data")
        return None
    except Exception:
        return None

def _save_earnings_cache(data):
    try:
        with open(_EARNINGS_CACHE_PATH, "w") as f:
            json.dump({"_date": datetime.now(ROME_TZ).date().isoformat(), "data": data}, f, default=str)
    except Exception:
        pass


def _parse_money(text):
    """Parse '$1.73' / '12.5%' / 'N/A' style strings into float, or None."""
    if not text or text in ("N/A", "—", ""):
        return None
    try:
        return float(text.replace("$", "").replace(",", "").replace("%", "").strip())
    except Exception:
        return None


def _yf_earnings_fallback(sym):
    """
    Lightweight yfinance fallback for EPS + revenue estimates.
    Called only when Nasdaq.com bulk API returns no epsForecast (mainly non-US companies).
    """
    try:
        cal = yf.Ticker(sym).calendar
        if isinstance(cal, dict):
            eps = cal.get("Earnings Average") or cal.get("EPS Estimate")
            rev = cal.get("Revenue Average") or cal.get("Revenue Estimate")
            return eps, rev
    except Exception:
        pass
    return None, None


def _fetch_nasdaq_earnings_day(date_obj):
    """
    Bulk earnings calendar for a single date from Nasdaq.com public API.
    One request returns ALL companies reporting that day (no per-ticker calls needed).
    """
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
    url = f"https://api.nasdaq.com/api/calendar/earnings?date={date_obj.isoformat()}"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    rows = (data.get("data") or {}).get("rows") or []
    return rows


_TIME_LABEL_MAP = {
    "time-pre-market":   "Pre-Market",
    "time-after-hours":  "After-Market",
    "time-not-supplied": "",
}


def get_earnings_this_week():
    """
    Earnings in tre fasce: yesterday (actuals) / today / upcoming (7gg).
    Usa il bulk earnings calendar pubblico di Nasdaq.com (1 richiesta per data, ~9 richieste totali)
    invece di interrogare yfinance per ognuno dei ~200 ticker dell'universo — evita rate-limit.
    Il risultato viene poi filtrato sull'universo NASDAQ-100 + S&P 500 top 100 (KEY_STOCKS).
    Cache giornaliera su disco.
    """
    cached = _load_earnings_cache()
    if cached:
        print("[Extras] Earnings: using today's cache")
        return cached

    print("[Extras] Fetching earnings calendar (Nasdaq.com bulk)...")
    today     = datetime.now(ROME_TZ).date()
    yesterday = today - timedelta(days=1)

    earnings_yesterday = []
    earnings_today     = []
    earnings_upcoming  = []

    universe = set(KEY_STOCKS.keys())

    # yesterday: 1 giorno, today: 1 giorno, upcoming: 7 giorni → 9 richieste totali
    dates_to_fetch = [yesterday, today] + [today + timedelta(days=i) for i in range(1, 8)]

    for d in dates_to_fetch:
        try:
            rows = _fetch_nasdaq_earnings_day(d)
        except Exception as e:
            print(f"[Extras] Nasdaq earnings calendar error ({d}): {e}")
            continue

        for row in rows:
            sym = row.get("symbol", "")
            if sym not in universe:
                continue
            name = KEY_STOCKS.get(sym, row.get("name", sym))
            cat, cat_label = _earnings_category(sym)
            release_label = _TIME_LABEL_MAP.get(row.get("time", ""), "")
            eps_est = _parse_money(row.get("epsForecast"))

            if d == yesterday:
                eps_actual = _parse_money(row.get("eps"))
                surprise   = _parse_money(row.get("surprise"))
                # Fallback yfinance quando Nasdaq.com non fornisce EPS est / revenue
                # (tipico società estere del Nasdaq-100 con copertura scarsa).
                yf_eps, yf_rev = None, None
                if eps_est is None:
                    yf_eps, yf_rev = _yf_earnings_fallback(sym)
                eps_est_final = eps_est if eps_est is not None else yf_eps
                beat = None
                if eps_actual is not None and eps_est_final is not None and eps_est_final != 0:
                    beat = eps_actual >= eps_est_final
                earnings_yesterday.append({
                    "symbol":        sym,
                    "name":          name,
                    "category":      cat,
                    "cat_label":     cat_label,
                    "date_fmt":      d.strftime("%a %d %b"),
                    "release_label": release_label,
                    "eps_actual":    f"${eps_actual:.2f}"    if eps_actual    is not None else "—",
                    "eps_estimate":  f"${eps_est_final:.2f}" if eps_est_final is not None else "—",
                    "surprise":      f"{surprise:+.1f}%"     if surprise      is not None else "—",
                    "beat":          beat,
                    "rev_estimate":  _fmt_rev(yf_rev) if yf_rev is not None else "—",
                })
            else:
                # Righe forward (today + upcoming): chiamo SEMPRE yfinance per la revenue
                # estimate (Nasdaq.com non la fornisce). L'EPS di yfinance si usa solo se
                # Nasdaq non ce l'ha. Le chiamate avvengono 1 volta/giorno (result cachato),
                # e solo per le ~7-20 società effettivamente mostrate → no rate-limit.
                yf_eps, yf_rev = _yf_earnings_fallback(sym)
                eps_final = eps_est if eps_est is not None else yf_eps
                entry = {
                    "symbol":        sym,
                    "name":          name,
                    "category":      cat,
                    "cat_label":     cat_label,
                    "date_fmt":      d.strftime("%a %d %b"),
                    "release_time":  "",
                    "release_label": release_label,
                    "eps_estimate":  f"${eps_final:.2f}" if eps_final is not None else "—",
                    "rev_estimate":  _fmt_rev(yf_rev) if yf_rev is not None else "N/A",
                    "eps_actual":    "—",
                    "surprise":      "—",
                    "beat":          None,
                    "_sort_date":    d.isoformat(),
                }
                if d == today:
                    earnings_today.append(entry)
                else:
                    earnings_upcoming.append(entry)

    earnings_upcoming.sort(key=lambda x: x["_sort_date"])
    for e in earnings_today + earnings_upcoming:
        e.pop("_sort_date", None)

    print(f"[Extras] Earnings: {len(earnings_yesterday)} yesterday (actuals), {len(earnings_today)} today, {len(earnings_upcoming)} next 7d")

    result = {
        "yesterday": earnings_yesterday,
        "today":     earnings_today,
        "upcoming":  earnings_upcoming,
    }
    _save_earnings_cache(result)
    return result


def _fmt_rev(val):
    if not val:
        return "N/A"
    if val >= 1e9:
        return f"${val/1e9:.1f}B"
    if val >= 1e6:
        return f"${val/1e6:.0f}M"
    return f"${val:,.0f}"


# ─────────────────────────────────────────────────────────────
# ASIA SESSION
# ─────────────────────────────────────────────────────────────

ASIA_INDICES = {
    "Nikkei 225":   "^N225",
    "Hang Seng":    "^HSI",
    "Shanghai":     "000001.SS",
    "CSI 300":      "000300.SS",
    "ASX 200":      "^AXJO",
    "KOSPI":        "^KS11",
}


def _get_crypto_asia_performance():
    """
    Fetch BTC/ETH/SOL performance during the last Asia session (00:00-08:00 UTC).
    Uses Binance public kline API (no key needed).
    Returns dict: { "BTC": {open, close, pct, direction, ...}, ... }
    """
    from datetime import timezone as tz
    import math

    now_utc = datetime.now(tz.utc)
    # Asia session: 00:00 UTC to 08:00 UTC today
    asia_open_utc  = now_utc.replace(hour=0,  minute=0, second=0, microsecond=0)
    asia_close_utc = now_utc.replace(hour=8,  minute=0, second=0, microsecond=0)

    # If current time is before 08:00 UTC, use previous day's Asia session
    if now_utc < asia_close_utc:
        from datetime import timedelta
        asia_open_utc  -= timedelta(days=1)
        asia_close_utc -= timedelta(days=1)

    start_ms = int(asia_open_utc.timestamp() * 1000)
    end_ms   = int(asia_close_utc.timestamp() * 1000)

    result = {}
    symbols = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "SOL": "SOLUSDT"}

    for sym, pair in symbols.items():
        try:
            resp = requests.get(
                "https://api.binance.com/api/v3/klines",
                params={
                    "symbol": pair,
                    "interval": "1h",
                    "startTime": start_ms,
                    "endTime": end_ms,
                    "limit": 9,
                },
                timeout=10,
            )
            resp.raise_for_status()
            candles = resp.json()
            if not candles:
                continue

            open_price  = float(candles[0][1])   # open of first candle
            close_price = float(candles[-1][4])  # close of last candle
            high_price  = max(float(c[2]) for c in candles)
            low_price   = min(float(c[3]) for c in candles)

            if open_price <= 0:
                continue

            pct = (close_price - open_price) / open_price * 100
            direction = "up" if pct > 0 else "down" if pct < 0 else "neutral"

            result[sym] = {
                "open":  open_price,
                "close": close_price,
                "high":  high_price,
                "low":   low_price,
                "pct":   pct,
                "pct_fmt": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                "direction": direction,
                "session_label": f"{asia_open_utc.strftime('%H:%M')}-{asia_close_utc.strftime('%H:%M')} UTC",
            }
        except Exception:
            continue

    return result


def get_asia_session():
    """
    Fetch Asian market indices performance + BTC/ETH/SOL during Asia hours.
    Includes a contextual analysis text.
    """
    print("[Extras] Fetching Asia session data...")
    results = {}

    for name, sym in ASIA_INDICES.items():
        try:
            # Retry/backoff: Yahoo throttla su chiamate ravvicinate → prima Asia usciva N/A.
            price = prev = None
            for attempt in range(3):
                try:
                    fi = yf.Ticker(sym).fast_info
                    price = getattr(fi, "last_price", None)
                    prev = getattr(fi, "previous_close", None)
                    if price and prev and prev > 0:
                        break
                except Exception:
                    pass
                time.sleep(2 * (attempt + 1))   # 2s, 4s, 6s
            if price and prev and prev > 0:
                change = price - prev
                pct = (change / prev) * 100
                direction = "up" if pct > 0 else "down" if pct < 0 else "neutral"
                results[name] = {
                    "symbol": sym,
                    "price": price,
                    "price_fmt": f"{price:,.2f}",
                    "change": change,
                    "change_fmt": f"{'+' if change >= 0 else ''}{change:.2f}",
                    "pct": pct,
                    "pct_fmt": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                    "direction": direction,
                }
            else:
                results[name] = {"price_fmt": "N/A", "pct_fmt": "N/A", "direction": "neutral"}
        except Exception:
            results[name] = {"price_fmt": "N/A", "pct_fmt": "N/A", "direction": "neutral"}

    # Crypto performance during Asia session
    results["_crypto_asia"] = _get_crypto_asia_performance()

    # Generate analysis (indices)
    valid = {k: v for k, v in results.items() if isinstance(v, dict) and v.get("pct") is not None}
    if valid:
        avg_pct = sum(v["pct"] for v in valid.values()) / len(valid)
        if avg_pct > 0.5:
            tone = "Positive Asian session"
        elif avg_pct < -0.5:
            tone = "Negative Asian session"
        else:
            tone = "Mixed Asian session"

        parts = [f"{tone} (average index: {avg_pct:+.1f}%)."]
        if any(v["pct"] < -0.3 for v in valid.values()):
            worst = min(valid.items(), key=lambda x: x[1]["pct"])
            parts.append(f"Biggest weakness in {worst[0]} ({worst[1]['pct_fmt']}).")
        if any(v["pct"] > 0.3 for v in valid.values()):
            best = max(valid.items(), key=lambda x: x[1]["pct"])
            parts.append(f"Best performance in {best[0]} ({best[1]['pct_fmt']}).")
        if avg_pct < -1.0:
            parts.append("Asia weakness = possible pressure on European/US open.")
        elif avg_pct > 1.0:
            parts.append("Asia strength = support for European/US open.")

        # Add crypto context to analysis
        crypto_asia = results.get("_crypto_asia", {})
        if crypto_asia:
            c_parts = []
            for sym in ["BTC", "ETH", "SOL"]:
                d = crypto_asia.get(sym)
                if d:
                    c_parts.append(f"{sym} {d['pct_fmt']}")
            if c_parts:
                parts.append(f"Crypto during the Asian session: {', '.join(c_parts)}.")

        results["_analysis"] = " ".join(parts)
    else:
        results["_analysis"] = "Asia data not available."

    return results


# ─────────────────────────────────────────────────────────────
# F&G COMBINATO
# ─────────────────────────────────────────────────────────────

def get_combined_crypto_fg():
    """Crypto Fear & Greed da alternative.me (fonte ufficiale, API pubblica)."""
    color_map = {
        "Extreme Fear": "#e74c3c", "Fear": "#e67e22",
        "Neutral": "#f1c40f", "Greed": "#2ecc71", "Extreme Greed": "#27ae60",
    }
    try:
        resp = requests.get("https://api.alternative.me/fng/?limit=2", timeout=8)
        items = resp.json().get("data", [])
        if items:
            score = int(items[0]["value"])
            label = items[0]["value_classification"]
            prev  = int(items[1]["value"]) if len(items) > 1 else score
            return {
                "score":      score,
                "label":      label,
                "color":      color_map.get(label, "#888"),
                "prev_score": prev,
                "source":     "alternative.me",
            }
    except Exception:
        pass
    return {"score": None, "label": "N/A", "color": "#888", "source": "alternative.me"}
