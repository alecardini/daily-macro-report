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
                return "⚠ Extreme Euphoria", "warning"      # call frenzy — possibile top
            elif ratio < 0.50:
                return "Bullish / Call Dominance", "positive"
            elif ratio < 0.65:
                return "Moderately Bullish", "positive"      # range normale bull run Deribit
            elif ratio < 0.75:
                return "Neutral", "neutral"                  # baseline crypto-adjusted
            elif ratio < 0.90:
                return "Cautious / Rising Hedges", "neutral"
            elif ratio < 1.00:
                return "Bearish / Defensive Positioning", "negative"
            elif ratio < 1.20:
                return "Elevated Fear", "negative"
            else:
                return "⚠ Extreme Fear / Possible Bottom", "warning"

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

_TICKER_LIST_CACHE      = "/tmp/earnings_ticker_universe_cache.json"
_TICKER_LIST_TTL        = 90 * 24 * 3600   # build sano → 90 giorni
_TICKER_LIST_TTL_DEGRADED = 24 * 3600      # build degradato → ritenta domani (auto-heal)
_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}

# Avvisi sulla costruzione dell'universo (esposti al report → banner data-quality)
UNIVERSE_WARNINGS = []


def _slickcharts_table(path):
    """Costituenti indice da Slickcharts (sito live, auto-aggiornato). DataFrame o None."""
    import pandas as pd, io
    try:
        r = requests.get(f"https://www.slickcharts.com/{path}", headers=_UA, timeout=20)
        r.raise_for_status()
        t = pd.read_html(io.StringIO(r.text))[0]
        return t if "Symbol" in [str(c) for c in t.columns] else None
    except Exception as e:
        print(f"[Extras] Slickcharts /{path} error: {e}")
        return None


def _fetch_nasdaq100():
    """Nasdaq-100 constituents. Primario Slickcharts (live), fallback Wikipedia."""
    t = _slickcharts_table("nasdaq100")
    if t is not None and len(t) >= 90:
        return {str(row["Symbol"]).replace(".", "-"): str(row["Company"]) for _, row in t.iterrows()}
    # fallback Wikipedia (la pagina ha cambiato formato nel 2026 → spesso vuoto, ma tentiamo)
    try:
        import pandas as pd, io
        r = requests.get("https://en.wikipedia.org/wiki/Nasdaq-100", headers=_UA, timeout=20)
        for tab in pd.read_html(io.StringIO(r.text)):
            cols = [str(c) for c in tab.columns]
            if ("Ticker" in cols or "Symbol" in cols) and "Company" in cols:
                key = "Ticker" if "Ticker" in cols else "Symbol"
                return {str(row[key]).replace(".", "-"): str(row["Company"]) for _, row in tab.iterrows()}
    except Exception as e:
        print(f"[Extras] Nasdaq-100 Wikipedia fallback error: {e}")
    return {}


def _fetch_sp500_top100_by_marketcap():
    """S&P top 100. Primario Slickcharts per weight (no yfinance), fallback Wikipedia + yfinance."""
    t = _slickcharts_table("sp500")
    if t is not None and len(t) >= 400 and "Weight" in [str(c) for c in t.columns]:
        try:
            t = t.copy()
            t["_w"] = t["Weight"].astype(str).str.replace("%", "", regex=False).astype(float)
            t = t.sort_values("_w", ascending=False).head(100)
            return {str(row["Symbol"]).replace(".", "-"): str(row["Company"]) for _, row in t.iterrows()}
        except Exception as e:
            print(f"[Extras] Slickcharts sp500 parse error: {e}")
    # fallback: Wikipedia + ranking market-cap via yfinance (lento ~8-10 min, ma robusto)
    try:
        import pandas as pd, io
        r = requests.get("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies", headers=_UA, timeout=20)
        sp500_df = pd.read_html(io.StringIO(r.text))[0]
        pairs = [(str(row["Symbol"]).replace(".", "-"), row["Security"]) for _, row in sp500_df.iterrows()]
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
    except Exception as e:
        print(f"[Extras] S&P 500 Wikipedia fallback error: {e}")
        return {}


def _load_ticker_universe_cache():
    """Ritorna (data, warnings) se cache valida (TTL dipende da _ttl salvato), altrimenti None."""
    try:
        with open(_TICKER_LIST_CACHE) as f:
            c = json.load(f)
        ttl = c.get("_ttl", _TICKER_LIST_TTL)
        if time.time() - c.get("_ts", 0) < ttl and c.get("data"):
            return c.get("data"), c.get("_warnings", [])
        return None
    except Exception:
        return None


def _save_ticker_universe_cache(data, warnings, ttl):
    try:
        with open(_TICKER_LIST_CACHE, "w") as f:
            json.dump({"_ts": time.time(), "_ttl": ttl, "_warnings": warnings, "data": data}, f)
    except Exception:
        pass


def _build_earnings_ticker_universe():
    """
    Universo earnings = NASDAQ-100 + S&P top 100, da Slickcharts (auto-aggiornato) con
    fallback Wikipedia. Health-check: se una lista è degradata → cache TTL corto (ritenta
    domani) + warning esposto in UNIVERSE_WARNINGS (→ banner data-quality del report).
    """
    global UNIVERSE_WARNINGS
    cached = _load_ticker_universe_cache()
    if cached is not None:
        data, UNIVERSE_WARNINGS = cached[0], cached[1]
        return data

    print("[Extras] Building earnings ticker universe (Slickcharts, live)...")
    n100, sp = {}, {}
    try:
        n100 = _fetch_nasdaq100()
    except Exception as e:
        print(f"[Extras] Nasdaq-100 fetch error: {e}")
    try:
        sp = _fetch_sp500_top100_by_marketcap()
    except Exception as e:
        print(f"[Extras] S&P top 100 fetch error: {e}")

    universe = dict(_STATIC_KEY_STOCKS)
    universe.update(n100)
    universe.update(sp)

    warnings = []
    if len(n100) < 90:
        warnings.append(f"Earnings watchlist: Nasdaq-100 source degraded ({len(n100)} names) — some tech earnings may be missing")
    if len(sp) < 90:
        warnings.append(f"Earnings watchlist: S&P top-100 source degraded ({len(sp)} names)")
    healthy = len(n100) >= 90 and len(sp) >= 90 and len(universe) >= 150

    if len(universe) > len(_STATIC_KEY_STOCKS) + 10:
        ttl = _TICKER_LIST_TTL if healthy else _TICKER_LIST_TTL_DEGRADED
        _save_ticker_universe_cache(universe, warnings, ttl)
        UNIVERSE_WARNINGS = warnings
        print(f"[Extras] Earnings universe: {len(universe)} names (Nasdaq {len(n100)}, S&P100 {len(sp)}) — "
              f"{'healthy, cached 90d' if healthy else 'DEGRADED, will retry next run'}")
        return universe

    UNIVERSE_WARNINGS = ["Earnings watchlist build FAILED — using minimal static list; earnings coverage limited"]
    print("[Extras] Universe build failed, using static list")
    return dict(_STATIC_KEY_STOCKS)


KEY_STOCKS = _build_earnings_ticker_universe()
KEY_STOCKS.update(_CRYPTO_PROXIES)   # garantiti sempre, anche se non nel Nasdaq-100/S&P top 100


# v2 (18/11/2026): nuova struttura "yesterday" (Finnhub + yfinance) → path nuovo, così
# una cache della stessa giornata scritta dalla versione vecchia non viene riusata.
_EARNINGS_CACHE_PATH = "/tmp/earnings_results_cache_v2.json"

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


# ─────────────────────────────────────────────────────────────
# RISULTATI DI IERI — fonti verificate il 18/11/2026 contro investing.com
# ─────────────────────────────────────────────────────────────
# PERCHÉ NON NASDAQ: la mattina dopo la trimestrale il campo "eps" del bulk Nasdaq contiene
# l'EPS dello STESSO trimestre dell'ANNO PRIMA (17/11: 0 righe su 46 con surprise; NVDA $1.24
# invece di $2.68) e Nasdaq aggiorna nell'arco di giorni. Nasdaq resta solo per l'ELENCO e
# l'orario PRE/AMC.
#   • Actual EPS + ricavi  → Finnhub /calendar/earnings (1 richiesta/giorno, già aggiornato la
#                             mattina dopo, identico a investing sui titoli USA); fallback EPS yfinance.
#   • Stima EPS            → yfinance (consenso che coincide con investing); fallback snapshot/Finnhub.
#   • Stima ricavi         → yfinance SALVATA PRIMA della pubblicazione (dopo, yfinance passa al
#                             trimestre successivo); fallback consenso Finnhub, marcato "F".
#   • Crescita YoY ricavi  → actual vs stesso trimestre anno prima (storico ricavi yfinance).
#   • Reazione prezzo      → AMC: ultimo prezzo after-hours vs chiusura ufficiale; PRE: seduta.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EST_SNAPSHOT_PATH = os.path.join(_PROJECT_ROOT, ".cache", "earnings_estimates.json")
_ET_TZ = pytz.timezone("America/New_York")


def _load_est_snapshots():
    try:
        with open(_EST_SNAPSHOT_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_est_snapshots(snaps):
    """Snapshot persistenti (NON in /tmp: devono sopravvivere al riavvio fino al giorno dopo)."""
    try:
        cutoff = (datetime.now(ROME_TZ).date() - timedelta(days=30)).isoformat()
        snaps = {k: v for k, v in snaps.items() if k.split("|")[-1] >= cutoff}
        os.makedirs(os.path.dirname(_EST_SNAPSHOT_PATH), exist_ok=True)
        with open(_EST_SNAPSHOT_PATH, "w") as f:
            json.dump(snaps, f, indent=1, sort_keys=True)
    except Exception as e:
        print(f"[Extras] Earnings estimate snapshot save error: {e}")


def _is_pre_release(report_date, release_label):
    """True se ADESSO la trimestrale del giorno report_date non è ancora uscita (ora USA)."""
    now_et = datetime.now(_ET_TZ)
    if report_date > now_et.date():
        return True
    if report_date < now_et.date():
        return False
    # Stesso giorno: PRE esce dalle ~06:00 ET, AMC dalle 16:00 ET. Orario ignoto → prudente (06:00).
    cutoff_h = 16 if release_label == "After-Market" else 6
    return now_et.hour < cutoff_h


def _finnhub_earnings_day(d):
    """Calendario Finnhub di un giorno: {symbol: row} con epsActual/epsEstimate/revenueActual/revenueEstimate."""
    key = getattr(config, "FINNHUB_API_KEY", "") or ""
    if not key or "YOUR_" in key:
        return {}
    try:
        r = requests.get("https://finnhub.io/api/v1/calendar/earnings",
                         params={"from": d.isoformat(), "to": d.isoformat(), "token": key}, timeout=20)
        r.raise_for_status()
        return {e.get("symbol"): e for e in (r.json().get("earningsCalendar") or []) if e.get("date") == d.isoformat()}
    except Exception as e:
        print(f"[Extras] Finnhub earnings calendar error ({d}): {e}")
        return {}


def _num(v):
    try:
        f = float(v)
        return None if f != f else f   # NaN → None
    except (TypeError, ValueError):
        return None


def _yf_reported(t, d):
    """(EPS riportato, stima EPS) di yfinance per la trimestrale pubblicata il giorno d (data USA)."""
    try:
        ed = t.get_earnings_dates(limit=12)
        if ed is None or ed.empty:
            return None, None
        idx = ed.index.tz_convert(_ET_TZ) if ed.index.tz is not None else ed.index
        for ts, (_, row) in zip(idx, ed.iterrows()):
            if ts.date() == d:
                return _num(row.get("Reported EPS")), _num(row.get("EPS Estimate"))
    except Exception:
        pass
    return None, None


def _yf_next_q_consensus(sym):
    """
    Consenso Yahoo del trimestre SUCCESSIVO (riga "+1q") — da salvare PRIMA dell'uscita, per
    confrontarlo con la guidance. Ritorna (rev, eps) o (None, None).
    """
    try:
        t = yf.Ticker(sym)
        re_, ee = t.revenue_estimate, t.earnings_estimate
        rev = _num(re_.loc["+1q", "avg"]) if re_ is not None and "+1q" in re_.index else None
        eps = _num(ee.loc["+1q", "avg"]) if ee is not None and "+1q" in ee.index else None
        return rev, eps
    except Exception:
        return None, None


def _revenue_yoy(t, d, rev_actual):
    """
    Crescita YoY dei ricavi del trimestre riportato il giorno d + YoY del trimestre precedente
    (per dire se accelera o rallenta). Storico trimestrale yfinance (≈5 trimestri).
    Il trimestre "anno prima" è il più recente chiuso tra d-365-100gg e d-365gg.
    """
    try:
        rev = t.quarterly_income_stmt.loc["Total Revenue"].dropna()
        hist = sorted(((ts.date(), float(v)) for ts, v in rev.items()), reverse=True)
    except Exception:
        return None, None, None
    if not hist:
        return None, None, None

    def _pick(lo, hi):
        cands = [(dt, v) for dt, v in hist if lo <= dt <= hi]
        return cands[0] if cands else None

    yago = _pick(d - timedelta(days=465), d - timedelta(days=365))
    yago_rev = yago[1] if yago else None
    yoy = None
    if yago and yago[1] and rev_actual:
        yoy = (rev_actual / yago[1] - 1) * 100
        if not (-90 <= yoy <= 400):   # valute/ADR disallineati → meglio niente
            yoy = None

    # Trimestre precedente: il più recente chiuso PRIMA del trimestre riportato
    # (se yfinance ha già il trimestre nuovo, lo salto).
    prev = _pick(d - timedelta(days=200), d - timedelta(days=101))
    prev_yoy = None
    if prev:
        prev_yago = _pick(prev[0] - timedelta(days=380), prev[0] - timedelta(days=350))
        if prev_yago and prev_yago[1]:
            prev_yoy = (prev[1] / prev_yago[1] - 1) * 100
            if not (-90 <= prev_yoy <= 400):
                prev_yoy = None
    return yoy, prev_yoy, yago_rev


def _price_reaction(t, d, release_label):
    """
    Reazione del prezzo alla trimestrale del giorno d.
    AMC → ultimo prezzo after-hours (16:00–20:00 ET) vs chiusura ufficiale di d.
    PRE / orario ignoto → variazione della seduta di d (chiusura d vs chiusura precedente).
    """
    try:
        daily = t.history(period="10d", interval="1d", auto_adjust=False)
        daily.index = daily.index.tz_convert(_ET_TZ) if daily.index.tz is not None else daily.index
        days = [(ts.date(), float(c)) for ts, c in daily["Close"].items()]
        close_d = next((c for dt, c in days if dt == d), None)
        if close_d is None:
            return None, None
        if release_label == "After-Market":
            # Barre da 1 MINUTO: quelle da 5m/15m di Yahoo in after-hours sono troncate
            # (18/11: NVDA 5m finiva alle 18:55 a 161.46, 1m arriva alle 19:59 a 162.94).
            intr = t.history(period="5d", interval="1m", prepost=True, auto_adjust=False)
            intr.index = intr.index.tz_convert(_ET_TZ)
            ah = intr[(intr.index.date == d) & (intr.index.hour >= 16) & (intr.index.hour < 20)]
            if ah.empty:
                return None, None
            return ((float(ah["Close"].iloc[-1]) / close_d - 1) * 100,
                    f"after-hours {ah.index[-1].strftime('%H:%M')} ET")
        prev_close = next((c for dt, c in reversed(days) if dt < d), None)
        if not prev_close:
            return None, None
        return (close_d / prev_close - 1) * 100, "session"
    except Exception:
        return None, None


def _fmt_money_ccy(val, ccy):
    if val is None:
        return "—"
    if not ccy or ccy == "USD":
        return _fmt_rev(val)
    s = _fmt_rev(val).replace("$", "")
    return f"{ccy} {s}"


def _yesterday_result(sym, d, release_label, nasdaq_eps_est, fh_row, snapshot):
    """Costruisce la riga "risultati di ieri" per un ticker. Nessun numero dubbio: se manca → None."""
    t = yf.Ticker(sym)
    yf_act, yf_est = _yf_reported(t, d)
    fh_row = fh_row or {}

    # ── EPS ──
    fh_act, fh_est = _num(fh_row.get("epsActual")), _num(fh_row.get("epsEstimate"))
    eps_act = fh_act if fh_act is not None else yf_act
    # Disaccordo tra fonti (≈10% dei casi nel backtest 28/10–17/11, aziende con voci straordinarie):
    # nessuna delle due ha sempre ragione (GOOGL: giusto Yahoo; RIOT/NBIS: giusto Finnhub) →
    # NON scegliamo in silenzio: il report mostra entrambi i valori con ⚠ e sorpresa in grigio.
    eps_conflict = None
    if fh_act is not None and yf_act is not None and abs(fh_act - yf_act) > max(0.03, abs(yf_act) * 0.05):
        eps_conflict = yf_act
        print(f"[Extras] Earnings {sym}: EPS actual disagree Finnhub {fh_act} vs Yahoo {yf_act} (shown both)")
    eps_est = next((v for v in (yf_est, _num((snapshot or {}).get("eps_est")), fh_est, nasdaq_eps_est) if v is not None), None)

    # ── Ricavi ──
    rev_act = _num(fh_row.get("revenueActual"))
    fh_rev_est = _num(fh_row.get("revenueEstimate"))
    snap_rev = _num((snapshot or {}).get("rev_est"))
    # Stima ricavi SOLO dallo snapshot Yahoo pre-uscita. Il consenso ricavi Finnhub NON si usa come
    # fallback: test 2–4/11/2026 su 52 società vs investing → beat/miss ricavi concorde solo 34/52
    # (stime Finnhub sistematicamente più alte). Senza snapshot → "—", nessuna sorpresa.
    # Finnhub serve solo come controllo di coerenza (snapshot >15% lontano = trimestre sbagliato).
    rev_est, rev_src = None, ""
    if snap_rev and (fh_rev_est is None or abs(snap_rev / fh_rev_est - 1) <= 0.15):
        rev_est = snap_rev

    ccy = None
    if rev_act is not None:
        try:
            ccy = (t.info or {}).get("financialCurrency")
        except Exception:
            ccy = None

    yoy, prev_yoy, yago_rev = _revenue_yoy(t, d, rev_act) if rev_act else (None, None, None)
    reaction, reaction_kind = _price_reaction(t, d, release_label)

    # Consenso del trimestre SUCCESSIVO (per confrontarlo con la guidance): SOLO snapshot pre-uscita.
    # NIENTE fallback "dopo l'uscita": 18/11 NVDA il consenso Yahoo è passato da $124.9B (mattina)
    # a $130.8B (pomeriggio, analisti già allineati alla guidance $130B) → il confronto diceva
    # "in linea" quando era +4% sopra. Senza snapshot → guidance mostrata senza confronto.
    next_rev = _num((snapshot or {}).get("rev_est_next"))
    next_eps = _num((snapshot or {}).get("eps_est_next"))
    next_src = "pre-release" if (next_rev or next_eps is not None) else ""

    def _surp(a, e):
        if a is None or e is None or e == 0:
            return None
        return (a - e) / abs(e) * 100

    eps_surp, rev_surp = _surp(eps_act, eps_est), _surp(rev_act, rev_est)
    # Sorpresa enorme con stima non vicina a zero = quasi sempre GAAP vs rettificato (UBER 4/11:
    # tutte le fonti gratuite $0.25 GAAP vs stima rettificata $0.90 → falso −72%). Avviso, non verdetto.
    eps_gap_warn = (eps_surp is not None and eps_conflict is None and eps_est is not None
                    and abs(eps_est) >= 0.25 and abs(eps_surp) > 40)
    return {
        "eps_actual_v": eps_act, "eps_estimate_v": eps_est, "eps_surprise_v": eps_surp,
        "rev_actual_v": rev_act, "rev_estimate_v": rev_est, "rev_surprise_v": rev_surp,
        "rev_est_src":  rev_src,
        "eps_actual":   f"${eps_act:.2f}" if eps_act is not None else "pending",
        "eps_estimate": f"${eps_est:.2f}" if eps_est is not None else "—",
        "eps_surprise": f"{eps_surp:+.1f}%" if eps_surp is not None else "—",
        "eps_conflict": f"${eps_conflict:.2f}" if eps_conflict is not None else "",
        "eps_gap_warn": eps_gap_warn,
        "rev_actual":   _fmt_money_ccy(rev_act, ccy) if rev_act is not None else "—",
        "rev_estimate": _fmt_money_ccy(rev_est, ccy) if rev_est is not None else "—",
        "rev_surprise": f"{rev_surp:+.1f}%" if rev_surp is not None else "—",
        "rev_yoy":      f"{yoy:+.1f}%" if yoy is not None else "—",
        "rev_yoy_prev": f"{prev_yoy:+.1f}%" if prev_yoy is not None else "",
        "rev_yoy_trend": (None if yoy is None or prev_yoy is None
                          else "accel" if yoy > prev_yoy + 0.5 else "decel" if yoy < prev_yoy - 0.5 else "flat"),
        "reaction":     f"{reaction:+.2f}%" if reaction is not None else "—",
        "reaction_v":   reaction,
        "reaction_kind": reaction_kind or "",
        "ccy": ccy,
        "next_rev_cons": next_rev, "next_eps_cons": next_eps, "next_cons_src": next_src,
        # compat: "beat" = EPS sopra/sotto stima (pari → None, colore neutro)
        "beat": (None if eps_surp is None or abs(eps_surp) < 1e-9 or eps_conflict is not None or eps_gap_warn
                 else eps_surp > 0),
    }


def _guidance_fields(g, e):
    """Dal risultato di earnings_guidance.get_guidance → campi pronti per il render (stringhe + valori)."""
    out = {"guid_main": "—", "guid_sub": "", "guid_vs_v": None, "guid_note": "",
           "gm_now": "—", "gm_guid": "", "gm_trend": None, "guid_quote": "", "gm_quote": ""}
    if not g or g.get("status") != "ok":
        return out
    # Frasi ORIGINALI del comunicato (già verificate testualmente) → tooltip per il controllo umano
    out["guid_quote"] = (g.get("guid") or {}).get("quote", "") or ""
    out["gm_quote"] = (g.get("gm_current") or {}).get("quote", "") or ""
    ccy = e.get("ccy")
    gm = g.get("gm_current") or {}
    if gm.get("value") is not None:
        out["gm_now"] = f"{gm['value']:.1f}%"
    gd = g.get("guid") or {}
    if gd.get("gm_mid") is not None:
        lo, hi = gd.get("gm_low"), gd.get("gm_high")
        out["gm_guid"] = (f"guid. {lo:.1f}–{hi:.1f}%" if lo is not None and hi is not None and lo != hi
                          else f"guid. ~{gd['gm_mid']:.1f}%")
        if gm.get("value") is not None:
            diff = gd["gm_mid"] - gm["value"]
            out["gm_trend"] = "up" if diff > 0.25 else "down" if diff < -0.25 else "flat"

    subs = []
    if gd.get("rev_mid"):
        lo, hi, mid = gd.get("rev_low"), gd.get("rev_high"), gd["rev_mid"]
        out["guid_main"] = f"Rev {_fmt_money_ccy(mid, ccy)}"
        if lo and hi and abs(hi - lo) / mid > 0.002:
            subs.append(f"range {_fmt_money_ccy(lo, ccy)}–{_fmt_money_ccy(hi, ccy).replace('$', '')}")
        cons = e.get("next_rev_cons")
        if cons:
            vs = (mid / cons - 1) * 100
            out["guid_vs_v"] = vs
            subs.append(f"vs est. {_fmt_money_ccy(cons, ccy)} ({vs:+.1f}%)")
    out["guid_sub"] = " · ".join(subs)
    if gd.get("eps_mid") is not None:
        lo, hi, mid = gd.get("eps_low"), gd.get("eps_high"), gd["eps_mid"]
        eps_txt = f"EPS ${lo:.2f}–{hi:.2f}" if lo is not None and hi is not None and lo != hi else f"EPS ${mid:.2f}"
        cons = e.get("next_eps_cons")
        if cons:
            vs_e = (mid / cons - 1) * 100 if cons else None
            eps_txt += f" vs est. ${cons:.2f}"
            if out["guid_vs_v"] is None and vs_e is not None and abs(cons) >= 0.10:
                out["guid_vs_v"] = vs_e
        if out["guid_main"] == "—":
            out["guid_main"] = eps_txt
        else:
            out["guid_sub"] = (out["guid_sub"] + " · " if out["guid_sub"] else "") + eps_txt
    if out["guid_main"] == "—":
        out["guid_main"] = "FY only" if g.get("only_fy") else "none in release"
    elif out["guid_vs_v"] is None:
        out["guid_note"] = "no pre-release est. to compare"
    return out


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

    snapshots = _load_est_snapshots()
    yesterday_jobs = []   # (sym, name, cat, cat_label, release_label, nasdaq_eps_est)

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
                # NB: il campo "eps" di Nasdaq la mattina dopo è l'EPS dell'anno prima → NON usato.
                yesterday_jobs.append((sym, name, cat, cat_label, release_label, eps_est))
            else:
                # Righe forward (today + upcoming): chiamo SEMPRE yfinance per la revenue
                # estimate (Nasdaq.com non la fornisce). L'EPS di yfinance si usa solo se
                # Nasdaq non ce l'ha. Le chiamate avvengono 1 volta/giorno (result cachato),
                # e solo per le ~7-20 società effettivamente mostrate → no rate-limit.
                yf_eps, yf_rev = _yf_earnings_fallback(sym)
                # Stima EPS: yfinance PRIMA (test 18/11 su 44 società: coincide con investing entro 2%
                # in 34/44; Nasdaq dava es. PANW $0.52 vs $0.97). Nasdaq solo se yfinance non c'è.
                eps_final = _num(yf_eps) if _num(yf_eps) is not None else eps_est
                # Snapshot del consenso PRIMA dell'uscita: dopo la trimestrale yfinance passa al
                # trimestre successivo, quindi domattina la stima ricavi "giusta" esiste solo qui.
                snap_key = f"{sym}|{d.isoformat()}"
                if _is_pre_release(d, release_label):
                    if yf_rev or yf_eps is not None:
                        nx_rev, nx_eps = _yf_next_q_consensus(sym)
                        snapshots[snap_key] = {
                            "rev_est": _num(yf_rev), "eps_est": _num(yf_eps),
                            "rev_est_next": nx_rev, "eps_est_next": nx_eps,
                            "saved_at": datetime.now(ROME_TZ).isoformat(timespec="minutes"),
                        }
                else:
                    # Già pubblicata (es. report lanciato nel pomeriggio): yfinance mostra ormai il
                    # trimestre SUCCESSIVO → uso lo snapshot pre-uscita, altrimenti EPS Nasdaq e ricavi N/A.
                    snap = snapshots.get(snap_key) or {}
                    eps_final = _num(snap.get("eps_est")) if _num(snap.get("eps_est")) is not None else eps_est
                    yf_rev = snap.get("rev_est")
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

    # ── Risultati di ieri: Finnhub (1 richiesta) + yfinance per ticker, in parallelo ──
    fh_day = _finnhub_earnings_day(yesterday)
    # Elenco = unione Nasdaq ∪ Finnhub (Nasdaq a metà aggiornamento può perdere righe/orari).
    # GOOG e GOOGL = stessa società (due classi di azioni) → tengo solo GOOGL.
    if any(j[0] == "GOOGL" for j in yesterday_jobs) or "GOOGL" in fh_day:
        yesterday_jobs = [j for j in yesterday_jobs if j[0] != "GOOG"]
    _seen = {j[0] for j in yesterday_jobs}
    for sym in fh_day:
        if sym in universe and sym not in _seen:
            cat, cat_label = _earnings_category(sym)
            yesterday_jobs.append((sym, KEY_STOCKS.get(sym, sym), cat, cat_label, "", None))
    # Orario: Finnhub "hour" (bmo/amc/dmh) prima; Nasdaq solo se Finnhub non lo dà
    # (18/11: Nasdaq è passato da "time-after-hours" a "time-not-supplied" per NVDA in giornata).
    _FH_HOUR = {"bmo": "Pre-Market", "amc": "After-Market", "dmh": "During session"}
    yesterday_jobs = [
        (s, n, c, cl, _FH_HOUR.get((fh_day.get(s) or {}).get("hour", ""), rl), est)
        for (s, n, c, cl, rl, est) in yesterday_jobs
    ]

    if yesterday_jobs:
        from concurrent.futures import ThreadPoolExecutor

        def _job(j):
            sym, name, cat, cat_label, release_label, nq_est = j
            try:
                res = _yesterday_result(sym, yesterday, release_label, nq_est,
                                        fh_day.get(sym), snapshots.get(f"{sym}|{yesterday.isoformat()}"))
            except Exception as e:
                print(f"[Extras] Earnings result error {sym}: {e}")
                res = {"eps_actual": "pending", "eps_estimate": "—", "eps_surprise": "—",
                       "rev_actual": "—", "rev_estimate": "—", "rev_surprise": "—",
                       "rev_yoy": "—", "rev_yoy_prev": "", "rev_yoy_trend": None,
                       "reaction": "—", "reaction_kind": "", "rev_est_src": "", "beat": None}
            res.update({"symbol": sym, "name": name, "category": cat, "cat_label": cat_label,
                        "date_fmt": yesterday.strftime("%a %d %b"), "release_label": release_label})
            return res

        with ThreadPoolExecutor(max_workers=6) as ex:
            earnings_yesterday = list(ex.map(_job, yesterday_jobs))

        # Fase B — guidance + margine lordo dal comunicato SEC (in SEQUENZA: una chiamata Gemini
        # per società, evita i 429 del free tier; risultati in cache su disco per i rilanci).
        try:
            from modules.earnings_guidance import get_guidance
        except Exception as e:
            get_guidance = None
            print(f"[Extras] Guidance module error: {e}")
        for e in earnings_yesterday:
            g = None
            if get_guidance is not None:
                try:
                    g = get_guidance(e["symbol"], e["name"], yesterday, e.get("rev_actual_v"))
                except Exception as ex_:
                    print(f"[Extras] Guidance error {e['symbol']}: {ex_}")
            e.update(_guidance_fields(g, e))

    _save_est_snapshots(snapshots)

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


def get_asia_session():
    """
    Fetch Asian market indices performance + contextual analysis text.
    Crypto RIMOSSE il 30/10/2026 (scelta utente): ripetevano l'Overnight Cross-Asset Recap,
    che copre già la notte (dalla chiusura USA a ora) con una finestra più completa — due
    numeri diversi per "BTC stanotte" creavano solo confusione.
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
