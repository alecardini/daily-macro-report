"""
Market Data Module

Covers:
- US Indices: S&P 500, Dow Jones, Nasdaq, VIX
- Futures pre-market: ES, NQ, YM
- Treasury yields: 2Y, 10Y, 30Y + spread (via FRED API)
- Other assets: DXY, Gold, Silver, Copper
- Gold ETF data: GLD, IAU (AUM + flows)
- Market Sentiment: CNN Fear & Greed, AAII Bullish %
- Crypto Fear & Greed Index (alternative.me)

Primary sources: yfinance (Yahoo Finance), FRED API, alternative.me
"""

import requests
import yfinance as yf
from datetime import datetime, timezone, timedelta
import pytz
import re
import sys
import os
import json
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from bs4 import BeautifulSoup

ROME_TZ = pytz.timezone("Europe/Rome")


# ─────────────────────────────────────────────────────────────
# HELPER: Format price changes
# ─────────────────────────────────────────────────────────────

def fmt_change(current, previous):
    """Return (change, pct_change, direction) tuple."""
    if not current or not previous or previous == 0:
        return 0, 0, "neutral"
    change = current - previous
    pct = (change / previous) * 100
    direction = "up" if change > 0 else "down" if change < 0 else "neutral"
    return change, pct, direction


def fmt_price(val, decimals=2):
    if val is None:
        return "N/A"
    return f"{val:,.{decimals}f}"


def get_yf_ticker_data(symbol, name=""):
    """
    Fetch current price, daily change, and key stats for a Yahoo Finance ticker.
    Returns dict with standardized fields.
    """
    try:
        ticker = yf.Ticker(symbol)
        info = ticker.fast_info

        current = getattr(info, 'last_price', None)
        prev_close = getattr(info, 'previous_close', None)

        if current is None:
            hist = ticker.history(period="2d", interval="1d")
            if len(hist) >= 1:
                current = float(hist['Close'].iloc[-1])
                prev_close = float(hist['Close'].iloc[-2]) if len(hist) >= 2 else current

        change, pct, direction = fmt_change(current, prev_close)

        return {
            "name": name or symbol,
            "symbol": symbol,
            "price": current,
            "prev_close": prev_close,
            "change": change,
            "pct_change": pct,
            "direction": direction,
            "price_fmt": fmt_price(current),
            "change_fmt": f"{'+' if change >= 0 else ''}{change:.2f}",
            "pct_fmt": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
        }
    except Exception as e:
        print(f"[MarketData] yfinance error for {symbol}: {e}")
        return {
            "name": name or symbol,
            "symbol": symbol,
            "price": None,
            "price_fmt": "N/A",
            "change_fmt": "N/A",
            "pct_fmt": "N/A",
            "direction": "neutral",
        }


# ─────────────────────────────────────────────────────────────
# US INDICES + FUTURES
# ─────────────────────────────────────────────────────────────

def get_us_indices():
    """Fetch S&P 500, Dow Jones, Nasdaq, VIX."""
    print("[MarketData] Fetching US indices...")
    results = {}
    for name, symbol in config.US_INDICES.items():
        results[name] = get_yf_ticker_data(symbol, name)
    return results


def get_futures():
    """Fetch pre-market futures (ES, NQ, YM)."""
    print("[MarketData] Fetching futures...")
    results = {}
    for name, symbol in config.FUTURES.items():
        results[name] = get_yf_ticker_data(symbol, name)
    return results


# ─────────────────────────────────────────────────────────────
# TREASURY YIELDS (FRED API)
# ─────────────────────────────────────────────────────────────

_FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"


def _fred_obs(series_id, **extra):
    """Fetch FRED observations (filtered of missing '.' values)."""
    params = {"series_id": series_id, "api_key": config.FRED_API_KEY, "file_type": "json"}
    params.update(extra)
    resp = requests.get(_FRED_BASE_URL, params=params, timeout=15)
    resp.raise_for_status()
    return [o for o in resp.json().get("observations", []) if o["value"] not in (".", "")]


def _fred_latest(series_id):
    """(current, change_in_bps, date) from the last two observations."""
    obs = _fred_obs(series_id, sort_order="desc", limit=5)
    if not obs:
        return None, None, None
    cur = float(obs[0]["value"])
    prev = float(obs[1]["value"]) if len(obs) > 1 else cur
    return cur, (cur - prev) * 100, obs[0]["date"]


def _fred_percentile(series_id, start="1997-01-01"):
    """(current, change_in_bps, percentile_vs_history, date) using full history."""
    obs = _fred_obs(series_id, observation_start=start, sort_order="asc")
    if not obs:
        return None, None, None, None
    vals = [float(o["value"]) for o in obs]
    cur = vals[-1]
    prev = vals[-2] if len(vals) > 1 else cur
    pctile = sum(1 for v in vals if v < cur) / len(vals) * 100
    return cur, (cur - prev) * 100, pctile, obs[-1]["date"]


def _curve_note(val):
    """Yield-curve spread interpretation. Structural thresholds (0 = inversion)."""
    if val < 0:
        return "Inverted", "negative"      # segnale recessione
    elif val < 0.5:
        return "Flat", "neutral"
    else:
        return "Normal", "positive"


def _credit_label(pctile):
    """Credit-spread interpretation via percentile-vs-history (institutional method)."""
    if pctile < 20:
        return "Tight", "positive"          # compresso / compiacente
    elif pctile < 80:
        return "Normal", "neutral"
    elif pctile < 95:
        return "Elevated", "negative"
    else:
        return "Stress", "warning"


def get_treasury_yields():
    """
    US Treasury yields + curve signals + real/breakeven + credit spreads, from FRED.
    Returns the yield curve as flat keys, plus a '_signals' dict with:
    spreads (2s10s, 3m10y), inflation (real yield, breakeven), credit (HY/IG OAS percentile).
    """
    print("[MarketData] Fetching Treasury yields + credit from FRED...")

    if not config.FRED_API_KEY or config.FRED_API_KEY == "YOUR_FRED_API_KEY_HERE":
        print("[MarketData] FRED API key not configured, using yfinance fallback.")
        return get_treasury_yields_yf()

    yields = {}

    # ── Curva completa ──
    for name, series_id in config.TREASURY_SERIES.items():
        try:
            cur, chg_bps, date = _fred_latest(series_id)
            if cur is not None:
                direction = "up" if chg_bps > 0 else "down" if chg_bps < 0 else "neutral"
                yields[name] = {
                    "value": cur,
                    "value_fmt": f"{cur:.2f}%",
                    "change_bps": chg_bps,
                    "change_bps_fmt": f"{chg_bps:+.0f}bp",
                    "direction": direction,
                    "date": date,
                    "source": "FRED",
                }
            else:
                yields[name] = {"value": None, "value_fmt": "N/A", "direction": "neutral"}
        except Exception as e:
            print(f"[MarketData] FRED error for {series_id}: {e}")
            yields[name] = {"value": None, "value_fmt": "N/A", "direction": "neutral"}

    # ── Signals: curve spreads + inflation + credit ──
    signals = {"spreads": {}, "inflation": {}, "credit": {}}

    # Spread calcolati come differenza dei yield GIÀ mostrati (consistency aritmetica,
    # non da serie FRED separate T10Y2Y/T10Y3M che hanno timing diverso → sfasamento bp).
    for name, long_k, short_k in [
        ("2s10s", "10Y Yield", "2Y Yield"),
        ("3m10y", "10Y Yield", "3M Yield"),
    ]:
        yl, ys = yields.get(long_k), yields.get(short_k)
        if yl and ys and yl.get("value") is not None and ys.get("value") is not None:
            val = yl["value"] - ys["value"]
            chg = (yl.get("change_bps", 0) or 0) - (ys.get("change_bps", 0) or 0)
            note, note_cls = _curve_note(val)
            signals["spreads"][name] = {
                "value_fmt": f"{'+' if val >= 0 else ''}{val:.2f}%",
                "change_bps_fmt": f"{chg:+.0f}bp",
                "note": note, "dir": note_cls,
            }

    for name, sid in getattr(config, "FRED_INFLATION", {}).items():
        try:
            cur, chg_bps, _ = _fred_latest(sid)
            if cur is not None:
                signals["inflation"][name] = {
                    "value_fmt": f"{cur:.2f}%",
                    "change_bps_fmt": f"{chg_bps:+.0f}bp",
                    "dir": "up" if chg_bps > 0 else "down" if chg_bps < 0 else "neutral",
                }
        except Exception as e:
            print(f"[MarketData] FRED inflation error {sid}: {e}")

    for name, sid in getattr(config, "FRED_CREDIT", {}).items():
        try:
            cur, chg_bps, pctile, _ = _fred_percentile(sid)
            if cur is not None:
                label, label_cls = _credit_label(pctile)
                signals["credit"][name] = {
                    "value_fmt": f"{cur:.2f}%",
                    "pctile_fmt": f"{pctile:.0f}th pctile",
                    "label": label, "dir": label_cls,
                    "change_bps_fmt": f"{chg_bps:+.0f}bp",
                    "widening": chg_bps > 0,
                }
        except Exception as e:
            print(f"[MarketData] FRED credit error {sid}: {e}")

    yields["_signals"] = signals
    return yields


def get_treasury_yields_yf():
    """Fallback: Treasury yields via Yahoo Finance."""
    yf_map = {
        "2Y Yield": "^IRX",   # 13-week proxy
        "10Y Yield": "^TNX",
        "30Y Yield": "^TYX",
    }
    yields = {}
    for name, sym in yf_map.items():
        try:
            data = get_yf_ticker_data(sym, name)
            val = data["price"]
            if val:
                val = val / 10 if sym == "^IRX" else val / 10
                yields[name] = {
                    "value": val,
                    "value_fmt": f"{val:.3f}%",
                    "change": data["change"] / 10 if data["change"] else 0,
                    "change_fmt": data["change_fmt"],
                    "direction": data["direction"],
                    "source": "Yahoo Finance",
                }
        except Exception:
            yields[name] = {"value_fmt": "N/A", "direction": "neutral"}

    # Spread
    try:
        y2 = yields.get("2Y Yield", {}).get("value")
        y10 = yields.get("10Y Yield", {}).get("value")
        if y2 and y10:
            spread = y10 - y2
            yields["2Y-10Y Spread"] = {
                "value": spread,
                "value_fmt": f"{'+' if spread >= 0 else ''}{spread:.3f}%",
                "direction": "up" if spread > 0 else "down",
                "note": "Inverted" if spread < 0 else "Normal",
                "source": "Yahoo Finance",
            }
    except Exception:
        pass

    return yields


# ─────────────────────────────────────────────────────────────
# OTHER ASSETS: DXY, Gold, Silver, Copper
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# FX MAJORS (Yahoo Finance primario, Frankfurter fallback keyless)
# ─────────────────────────────────────────────────────────────

def _frankfurter_fx_fallback():
    """
    Fallback FX via Frankfurter (ECB reference rates, keyless).
    Dà solo il livello (fixing giornaliero BCE, EUR-based) → ricostruisco i pair
    e calcolo la variazione D/D (day-over-day), NON 24h rolling → etichettata diversamente.
    """
    import datetime as _dt
    try:
        base = "https://api.frankfurter.dev/v1"
        latest = requests.get(f"{base}/latest?base=EUR&symbols=USD,JPY,GBP,CNY", timeout=12).json()
        cur_date = latest.get("date")
        cur = latest.get("rates", {})
        if not cur or not cur_date:
            return {}
        start = (_dt.date.fromisoformat(cur_date) - _dt.timedelta(days=7)).isoformat()
        series = requests.get(f"{base}/{start}..{cur_date}?base=EUR&symbols=USD,JPY,GBP,CNY", timeout=12).json()
        rates_by_date = series.get("rates", {})
        dates = sorted(rates_by_date.keys())
        prev = rates_by_date[dates[-2]] if len(dates) >= 2 else cur

        def _pairs(r):
            usd = r["USD"]
            return {
                "EUR/USD": usd,
                "USD/JPY": r["JPY"] / usd,
                "GBP/USD": usd / r["GBP"],
                "USD/CNY": r["CNY"] / usd,
            }
        pc, pp = _pairs(cur), _pairs(prev)
        out = {}
        for name in config.FX_PAIRS:
            v, pv = pc.get(name), pp.get(name)
            if v is None:
                continue
            dec = 2 if "JPY" in name else 4
            chg = v - (pv if pv else v)
            pct = (chg / pv * 100) if pv else 0
            direction = "up" if chg > 0 else "down" if chg < 0 else "neutral"
            out[name] = {
                "name": name,
                "price_fmt": f"{v:.{dec}f}",
                "change_fmt": f"{chg:+.{dec}f}",
                "pct_fmt": f"{pct:+.2f}%",
                "direction": direction,
                "source": "ECB ref. (Frankfurter), D/D",
            }
        return out
    except Exception as e:
        print(f"[MarketData] Frankfurter FX fallback error: {e}")
        return {}


def get_fx_majors():
    """FX majors da Yahoo Finance (primario) con fallback Frankfurter per i pair mancanti."""
    print("[MarketData] Fetching FX majors...")
    results = {}
    for name, sym in config.FX_PAIRS.items():
        d = get_yf_ticker_data(sym, name)
        if d.get("price"):
            dec = 2 if "JPY" in name else 4
            results[name] = {
                "name": name,
                "price_fmt": f"{d['price']:.{dec}f}",
                "change_fmt": f"{d['change']:+.{dec}f}",
                "pct_fmt": d["pct_fmt"],
                "direction": d["direction"],
                "source": "Yahoo Finance",
            }
        else:
            results[name] = None

    # Fallback Frankfurter solo per i pair che Yahoo non ha dato
    if any(v is None for v in results.values()):
        fb = _frankfurter_fx_fallback()
        for name in list(results):
            if results[name] is None:
                results[name] = fb.get(name)

    return {k: v for k, v in results.items() if v}


def get_other_assets():
    """Fetch DXY, Gold, Silver, Copper prices."""
    print("[MarketData] Fetching commodities and DXY...")
    results = {}
    for name, symbol in config.OTHER_ASSETS.items():
        results[name] = get_yf_ticker_data(symbol, name)
    return results


def get_gold_etf_data():
    """
    Fetch GLD and IAU ETF data (price, AUM, volume).
    Also attempts to get weekly flow data from public sources.
    """
    print("[MarketData] Fetching Gold ETF data...")
    etf_data = {}

    for name, symbol in config.GOLD_ETFS.items():
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            fast = ticker.fast_info

            current_price = getattr(fast, 'last_price', None)
            prev_close = getattr(fast, 'previous_close', None)

            # AUM in billions
            aum = info.get("totalAssets")
            aum_fmt = f"${aum/1e9:.1f}B" if aum else "N/A"

            # Shares outstanding * price = approx AUM
            shares = info.get("sharesOutstanding")
            volume = getattr(fast, 'three_month_average_volume', None)

            change, pct, direction = fmt_change(current_price, prev_close)

            etf_data[name] = {
                "symbol": symbol,
                "price": current_price,
                "price_fmt": fmt_price(current_price),
                "change_fmt": f"{'+' if change >= 0 else ''}{change:.2f}",
                "pct_fmt": f"{'+' if pct >= 0 else ''}{pct:.2f}%",
                "direction": direction,
                "aum": aum_fmt,
                "shares_outstanding": f"{shares/1e6:.0f}M" if shares else "N/A",
            }
        except Exception as e:
            print(f"[MarketData] Gold ETF error {symbol}: {e}")
            etf_data[name] = {
                "symbol": symbol,
                "price_fmt": "N/A",
                "pct_fmt": "N/A",
                "direction": "neutral",
                "aum": "N/A",
            }

    # Try WGC flow data (public endpoint)
    try:
        wgc_url = "https://www.gold.org/goldhub/data/gold-etfs-holdings-and-flows"
        etf_data["wgc_note"] = "Dati flussi aggiornati: gold.org/goldhub"
        etf_data["wgc_url"] = wgc_url
    except Exception:
        pass

    return etf_data


# ─────────────────────────────────────────────────────────────
# SENTIMENT: CNN Fear & Greed + AAII
# ─────────────────────────────────────────────────────────────

_CNN_FG_CACHE_PATH    = "/tmp/cnn_fg_cache.json"
_CNN_FG_FALLBACK_MAX  = 24 * 3600  # fallback max 24h — dato giornaliero

def _load_cnn_fg_cache():
    try:
        with open(_CNN_FG_CACHE_PATH) as f:
            cached = json.load(f)
        age = time.time() - cached.get("_ts", 0)
        return cached.get("data"), age
    except Exception:
        return None, None

def _save_cnn_fg_cache(data):
    try:
        with open(_CNN_FG_CACHE_PATH, "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass

def get_cnn_fear_greed():
    """
    Fetch CNN Fear & Greed Index (US Equity).
    Cache 24h su disco — fallback su ultimo dato se CNN non risponde.
    """
    cached_data, cache_age = _load_cnn_fg_cache()
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://edition.cnn.com/",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        score = data["fear_and_greed"]["score"]
        rating = data["fear_and_greed"]["rating"]
        prev_score = data["fear_and_greed"].get("previous_close", score)

        label_map = {
            "extreme fear": ("Extreme Fear", "#e74c3c"),
            "fear": ("Fear", "#e67e22"),
            "neutral": ("Neutral", "#f1c40f"),
            "greed": ("Greed", "#2ecc71"),
            "extreme greed": ("Extreme Greed", "#27ae60"),
        }
        label, color = label_map.get(rating.lower(), (rating.title(), "#888"))

        result = {
            "score": round(score),
            "label": label,
            "color": color,
            "prev_score": round(prev_score),
            "source": "CNN Money",
        }
        _save_cnn_fg_cache(result)
        return result
    except Exception as e:
        print(f"[Sentiment] CNN F&G error: {e}")
        if cached_data and cache_age is not None and cache_age < _CNN_FG_FALLBACK_MAX:
            print(f"[Sentiment] CNN F&G: uso cache ({int(cache_age/3600)}h fa) come fallback")
            return cached_data
        return {"score": None, "label": "N/A", "color": "#888", "source": "CNN Money"}


_AAII_CACHE_PATH   = "/tmp/aaii_cache.json"
_AAII_FALLBACK_MAX = 6 * 24 * 3600  # fallback max 6 giorni — oltre: N/A

def _load_aaii_cache():
    """Restituisce (data, age_seconds) oppure (None, None) se non esiste."""
    try:
        with open(_AAII_CACHE_PATH) as f:
            cached = json.load(f)
        age = time.time() - cached.get("_ts", 0)
        return cached.get("data"), age
    except Exception:
        return None, None

def _save_aaii_cache(data):
    try:
        with open(_AAII_CACHE_PATH, "w") as f:
            json.dump({"_ts": time.time(), "data": data}, f)
    except Exception:
        pass

def get_aaii_sentiment():
    """
    Fetch AAII Investor Sentiment Survey (weekly, pubblicato ogni giovedì).
    Tenta sempre il fetch. Se fallisce usa cache come fallback solo se < 6 giorni.
    Oltre 6 giorni → N/A, così il problema è visibile.
    """
    cached_data, cache_age = _load_aaii_cache()

    try:
        url = "https://www.aaii.com/sentimentsurvey/sent_results"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")

        # AAII table: header row = [Reported Date, Bullish, Neutral, Bearish]
        # Data rows: [date, bull%, neutral%, bear%]
        table = soup.select_one("table")
        rows = table.find_all("tr") if table else []
        bullish, neutral, bearish, survey_date = None, None, None, None

        if rows:
            headers = [th.get_text(strip=True).lower() for th in rows[0].find_all(["th", "td"])]
            bull_col    = next((i for i, h in enumerate(headers) if "bullish" in h), None)
            neutral_col = next((i for i, h in enumerate(headers) if "neutral" in h), None)
            bear_col    = next((i for i, h in enumerate(headers) if "bearish" in h), None)
            date_col    = next((i for i, h in enumerate(headers) if "date" in h), 0)

            for row in rows[1:]:
                cells = [td.get_text(strip=True) for td in row.find_all(["td", "th"])]
                if len(cells) < 3:
                    continue
                try:
                    if bull_col and bull_col < len(cells):
                        bullish = float(cells[bull_col].replace("%", "").strip())
                    if neutral_col and neutral_col < len(cells):
                        neutral = float(cells[neutral_col].replace("%", "").strip())
                    if bear_col and bear_col < len(cells):
                        bearish = float(cells[bear_col].replace("%", "").strip())
                    survey_date = cells[date_col]
                    break  # prima riga = dato più recente
                except Exception:
                    continue

        result = {
            "bullish": bullish,
            "neutral": neutral,
            "bearish": bearish,
            "bullish_fmt": f"{bullish:.1f}%" if bullish is not None else "N/A",
            "neutral_fmt": f"{neutral:.1f}%" if neutral is not None else "N/A",
            "bearish_fmt": f"{bearish:.1f}%" if bearish is not None else "N/A",
            "survey_date": survey_date or "",
            "source": "AAII",
            "note": "Weekly data",
        }
        _save_aaii_cache(result)
        return result
    except Exception as e:
        print(f"[Sentiment] AAII error: {e}")
        if cached_data and cache_age is not None and cache_age < _AAII_FALLBACK_MAX:
            print(f"[Sentiment] AAII: uso cache ({int(cache_age/3600)}h fa) come fallback")
            return cached_data
        return {
            "bullish_fmt": "N/A", "neutral_fmt": "N/A", "bearish_fmt": "N/A",
            "source": "AAII"
        }


def get_crypto_fear_greed():
    """
    Fetch Crypto Fear & Greed Index from alternative.me (official public API).
    """
    try:
        resp = requests.get(
            "https://api.alternative.me/fng/?limit=2",
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("data", [])

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
        color = color_map.get(label, "#888")

        return {
            "score": score,
            "label": label,
            "color": color,
            "prev_score": prev_score,
            "source": "alternative.me",
        }
    except Exception as e:
        print(f"[Sentiment] Crypto F&G error: {e}")
        return {"score": None, "label": "N/A", "color": "#888", "source": "alternative.me"}


def _pct_change_period(sym: str, period: str) -> float | None:
    """Calcola la performance % su un periodo (es. '5d', '1mo', '3mo') via yfinance."""
    try:
        import yfinance as yf
        hist = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=True)
        closes = hist["Close"].dropna()
        if len(closes) < 2:
            return None
        start = float(closes.iloc[0])
        end   = float(closes.iloc[-1])
        if start == 0:
            return None
        return round((end - start) / start * 100, 2)
    except Exception:
        return None


def _fmt_pct(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def get_sector_rotation():
    """
    Fetch S&P 500 sector ETF performance su base settimanale, mensile e trimestrale.
    La rotazione settoriale è un fenomeno multi-settimana: il giornaliero genera troppo rumore.
    Classifica settori best → worst sulla performance settimanale.
    """
    print("[MarketData] Fetching sector rotation...")
    sectors = {}

    for sym, name in config.SECTOR_ETFS.items():
        pct_week    = _pct_change_period(sym, "5d")
        pct_month   = _pct_change_period(sym, "1mo")
        pct_quarter = _pct_change_period(sym, "3mo")
        dir_week    = "positive" if (pct_week or 0) >= 0 else "negative"
        sectors[sym] = {
            "name":            name,
            "symbol":          sym,
            "pct_week":        pct_week,
            "pct_month":       pct_month,
            "pct_quarter":     pct_quarter,
            "pct_week_fmt":    _fmt_pct(pct_week),
            "pct_month_fmt":   _fmt_pct(pct_month),
            "pct_quarter_fmt": _fmt_pct(pct_quarter),
            "direction":       dir_week,
        }

    # Ordina per performance settimanale (best → worst)
    sorted_sectors = sorted(sectors.values(), key=lambda x: x["pct_week"] or 0, reverse=True)

    # Risk-on / Risk-off sulla settimana
    tech       = sectors.get("XLK", {}).get("pct_week") or 0
    energy     = sectors.get("XLE", {}).get("pct_week") or 0
    utilities  = sectors.get("XLU", {}).get("pct_week") or 0
    financials = sectors.get("XLF", {}).get("pct_week") or 0
    staples    = sectors.get("XLP", {}).get("pct_week") or 0
    healthcare = sectors.get("XLV", {}).get("pct_week") or 0

    risk_on_score  = tech + financials + energy
    risk_off_score = utilities + staples + healthcare

    best  = sorted_sectors[0]  if sorted_sectors else {}
    worst = sorted_sectors[-1] if sorted_sectors else {}

    if risk_on_score > risk_off_score + 1.5:
        regime = "Risk-ON — weekly flows toward cyclical and growth sectors"
        regime_dir = "positive"
    elif risk_off_score > risk_on_score + 1.5:
        regime = "Risk-OFF — weekly rotation toward defensive sectors"
        regime_dir = "negative"
    else:
        regime = "Mixed market — no clear sector rotation this week"
        regime_dir = "neutral"

    analysis = f"{regime}."
    if best.get("name"):
        analysis += f" Best sector (week): {best['name']} ({best['pct_week_fmt']})."
    if worst.get("name"):
        analysis += f" Worst sector (week): {worst['name']} ({worst['pct_week_fmt']})."

    return {
        "sectors":    sorted_sectors,
        "regime":     regime,
        "regime_dir": regime_dir,
        "analysis":   analysis,
        "source":     "Yahoo Finance",
    }


def get_all_sentiment():
    """Aggregate all sentiment indicators."""
    print("[Sentiment] Fetching sentiment data...")
    return {
        "crypto_fg": get_crypto_fear_greed(),
        "equity_fg": get_cnn_fear_greed(),
        "aaii": get_aaii_sentiment(),
    }
