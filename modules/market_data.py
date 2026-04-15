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

def get_treasury_yields():
    """
    Fetch US Treasury yields from FRED (Federal Reserve official data).
    Returns 2Y, 10Y, 30Y yields and 2-10 spread.
    """
    print("[MarketData] Fetching Treasury yields from FRED...")

    if not config.FRED_API_KEY or config.FRED_API_KEY == "YOUR_FRED_API_KEY_HERE":
        print("[MarketData] FRED API key not configured, using yfinance fallback.")
        return get_treasury_yields_yf()

    yields = {}
    base_url = "https://api.stlouisfed.org/fred/series/observations"

    for name, series_id in config.TREASURY_SERIES.items():
        try:
            resp = requests.get(
                base_url,
                params={
                    "series_id": series_id,
                    "api_key": config.FRED_API_KEY,
                    "file_type": "json",
                    "limit": 5,
                    "sort_order": "desc",
                },
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            obs = [o for o in data["observations"] if o["value"] != "."]

            if obs:
                current_val = float(obs[0]["value"])
                prev_val = float(obs[1]["value"]) if len(obs) > 1 else current_val
                change = current_val - prev_val
                direction = "up" if change > 0 else "down" if change < 0 else "neutral"

                yields[name] = {
                    "value": current_val,
                    "value_fmt": f"{current_val:.3f}%",
                    "change": change,
                    "change_fmt": f"{'+' if change >= 0 else ''}{change:.3f}%",
                    "direction": direction,
                    "date": obs[0]["date"],
                    "source": "FRED (Federal Reserve)",
                }
        except Exception as e:
            print(f"[MarketData] FRED error for {series_id}: {e}")
            yields[name] = {"value": None, "value_fmt": "N/A", "direction": "neutral"}

    # Calculate 2Y-10Y spread (yield curve)
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
                "source": "Calculated from FRED",
            }
    except Exception:
        pass

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

def get_cnn_fear_greed():
    """
    Fetch CNN Fear & Greed Index (US Equity).
    Scrapes CNN Money public page.
    """
    try:
        # CNN exposes F&G via a semi-public API endpoint
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
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

        return {
            "score": round(score),
            "label": label,
            "color": color,
            "prev_score": round(prev_score),
            "source": "CNN Money",
        }
    except Exception as e:
        print(f"[Sentiment] CNN F&G error: {e}")
        return {"score": None, "label": "N/A", "color": "#888", "source": "CNN Money"}


def get_aaii_sentiment():
    """
    Fetch AAII Investor Sentiment Survey (weekly).
    Returns % Bullish, % Bearish, % Neutral.
    """
    try:
        # AAII publishes weekly data via their RSS/page
        url = "https://www.aaii.com/sentimentsurvey/sent_results"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        }
        resp = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")

        # AAII table structure
        rows = soup.select("table tr")
        bullish, neutral, bearish = None, None, None

        for row in rows:
            cells = [td.get_text(strip=True) for td in row.select("td")]
            if len(cells) >= 2:
                label = cells[0].lower()
                if "bullish" in label:
                    try:
                        bullish = float(cells[1].replace("%", ""))
                    except Exception:
                        pass
                elif "neutral" in label:
                    try:
                        neutral = float(cells[1].replace("%", ""))
                    except Exception:
                        pass
                elif "bearish" in label:
                    try:
                        bearish = float(cells[1].replace("%", ""))
                    except Exception:
                        pass

        return {
            "bullish": bullish,
            "neutral": neutral,
            "bearish": bearish,
            "bullish_fmt": f"{bullish:.1f}%" if bullish else "N/A",
            "neutral_fmt": f"{neutral:.1f}%" if neutral else "N/A",
            "bearish_fmt": f"{bearish:.1f}%" if bearish else "N/A",
            "source": "AAII",
            "note": "Dati settimanali",
        }
    except Exception as e:
        print(f"[Sentiment] AAII error: {e}")
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
        regime = "Risk-ON — flussi settimanali verso settori ciclici e growth"
        regime_dir = "positive"
    elif risk_off_score > risk_on_score + 1.5:
        regime = "Risk-OFF — rotazione settimanale verso settori difensivi"
        regime_dir = "negative"
    else:
        regime = "Mercato misto — nessuna rotazione settoriale chiara questa settimana"
        regime_dir = "neutral"

    analysis = f"{regime}."
    if best.get("name"):
        analysis += f" Miglior settore (settimana): {best['name']} ({best['pct_week_fmt']})."
    if worst.get("name"):
        analysis += f" Peggior settore (settimana): {worst['name']} ({worst['pct_week_fmt']})."

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
