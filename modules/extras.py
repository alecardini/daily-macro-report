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


def get_pc_ratios():
    """BTC + ETH Put/Call ratios."""
    print("[Extras] Fetching Deribit P/C ratios...")
    return {
        "BTC": get_deribit_pc_ratio("BTC"),
        "ETH": get_deribit_pc_ratio("ETH"),
    }


# ─────────────────────────────────────────────────────────────
# EARNINGS: Prossime settimane — key stocks
# ─────────────────────────────────────────────────────────────

KEY_STOCKS = {
    # Mega Tech
    "NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft",
    "GOOGL": "Alphabet", "META": "Meta", "AMZN": "Amazon",
    "TSLA": "Tesla",
    # Finance
    "JPM": "JPMorgan", "GS": "Goldman Sachs", "BAC": "Bank of America",
    "MS": "Morgan Stanley",
    # Other market-moving
    "AMD": "AMD", "INTC": "Intel", "NFLX": "Netflix",
}


def get_earnings_this_week():
    """
    Earnings in tre fasce:
    - yesterday: usciti ieri dopo chiusura (~22:00 IT) → actuals + surprise visibili la mattina dopo
    - today:     riportano oggi → banner urgente con estimates
    - upcoming:  prossimi 7gg → tabella con estimates

    Colonne mostrate: EPS actual/estimate | Revenue estimate | EPS Surprise% | Data | Orario report
    """
    print("[Extras] Fetching earnings calendar...")
    today     = datetime.now(ROME_TZ).date()
    yesterday = today - timedelta(days=1)
    week_end  = today + timedelta(days=7)

    earnings_yesterday = []
    earnings_today     = []
    earnings_upcoming  = []

    def _safe(val):
        """Return None if NaN, else val."""
        try:
            import math
            if val is None: return None
            if isinstance(val, float) and math.isnan(val): return None
            return val
        except Exception:
            return None

    for sym, name in KEY_STOCKS.items():
        try:
            t = yf.Ticker(sym)

            # ── Actuals da earnings_dates (per ieri) ──
            try:
                ed_df = t.earnings_dates
                if ed_df is not None and not ed_df.empty:
                    for idx, row in ed_df.iterrows():
                        try:
                            ed_date = idx.date() if hasattr(idx, 'date') else idx
                        except Exception:
                            continue
                        if ed_date != yesterday:
                            continue
                        eps_actual  = _safe(row.get("Reported EPS"))
                        eps_est     = _safe(row.get("EPS Estimate"))
                        surprise    = _safe(row.get("Surprise(%)"))
                        # Determina beat/miss
                        beat = None
                        if eps_actual is not None and eps_est is not None and eps_est != 0:
                            beat = eps_actual >= eps_est
                        earnings_yesterday.append({
                            "symbol":       sym,
                            "name":         name,
                            "date_fmt":     ed_date.strftime("%a %d %b"),
                            "eps_actual":   f"${eps_actual:.2f}"  if eps_actual  is not None else "—",
                            "eps_estimate": f"${eps_est:.2f}"     if eps_est     is not None else "—",
                            "surprise":     f"{surprise:+.1f}%"   if surprise    is not None else "—",
                            "beat":         beat,
                            "rev_estimate": "—",   # yfinance free non dà revenue actuals
                        })
                        break
            except Exception:
                pass

            # ── Upcoming + oggi via calendar ──
            cal = t.calendar
            if not cal or "Earnings Date" not in cal:
                continue
            dates = cal["Earnings Date"]
            if not isinstance(dates, list):
                dates = [dates]

            for ed in dates:
                if isinstance(ed, datetime):
                    ed = ed.date()
                if not (today <= ed <= week_end):
                    continue
                eps_est = _safe(cal.get("Earnings Average"))
                rev_est = _safe(cal.get("Revenue Average"))

                # Orario rilascio da earningsTimestampStart (ora italiana)
                release_time = "—"
                release_label = ""
                try:
                    ts = t.info.get("earningsTimestampStart")
                    if ts:
                        from datetime import timezone as _tz
                        dt_rome = datetime.fromtimestamp(ts, tz=ROME_TZ)
                        release_time = dt_rome.strftime("%H:%M")
                        hour = dt_rome.hour
                        if hour < 15 or (hour == 15 and dt_rome.minute < 30):
                            release_label = "Pre-Market"
                        elif hour >= 22 or (hour == 21 and dt_rome.minute >= 30):
                            release_label = "After-Market"
                        else:
                            release_label = "Durante sessione"
                except Exception:
                    pass

                entry = {
                    "symbol":           sym,
                    "name":             name,
                    "date":             ed,
                    "date_fmt":         ed.strftime("%a %d %b"),
                    "release_time":     release_time,
                    "release_label":    release_label,
                    "eps_estimate":     f"${eps_est:.2f}" if eps_est is not None else "—",
                    "rev_estimate":     _fmt_rev(rev_est),
                    "eps_actual":       "—",
                    "surprise":         "—",
                    "beat":             None,
                }
                if ed == today:
                    earnings_today.append(entry)
                else:
                    earnings_upcoming.append(entry)
                break

        except Exception:
            continue

    earnings_upcoming.sort(key=lambda x: x["date"])
    print(f"[Extras] Earnings: {len(earnings_yesterday)} ieri (actuals), {len(earnings_today)} oggi, {len(earnings_upcoming)} prossimi 7gg")
    return {
        "yesterday": earnings_yesterday,
        "today":     earnings_today,
        "upcoming":  earnings_upcoming,
    }


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
            t = yf.Ticker(sym)
            fi = t.fast_info
            price = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
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
            tone = "Sessione asiatica positiva"
        elif avg_pct < -0.5:
            tone = "Sessione asiatica negativa"
        else:
            tone = "Sessione asiatica mista"

        parts = [f"{tone} (media indici: {avg_pct:+.1f}%)."]
        if any(v["pct"] < -0.3 for v in valid.values()):
            worst = min(valid.items(), key=lambda x: x[1]["pct"])
            parts.append(f"Maggiore debolezza su {worst[0]} ({worst[1]['pct_fmt']}).")
        if any(v["pct"] > 0.3 for v in valid.values()):
            best = max(valid.items(), key=lambda x: x[1]["pct"])
            parts.append(f"Miglior performance su {best[0]} ({best[1]['pct_fmt']}).")
        if avg_pct < -1.0:
            parts.append("Debolezza Asia = possibile pressione all'apertura europea/americana.")
        elif avg_pct > 1.0:
            parts.append("Forza Asia = supporto per apertura europea/americana.")

        # Add crypto context to analysis
        crypto_asia = results.get("_crypto_asia", {})
        if crypto_asia:
            c_parts = []
            for sym in ["BTC", "ETH", "SOL"]:
                d = crypto_asia.get(sym)
                if d:
                    c_parts.append(f"{sym} {d['pct_fmt']}")
            if c_parts:
                parts.append(f"Crypto durante la sessione asiatica: {', '.join(c_parts)}.")

        results["_analysis"] = " ".join(parts)
    else:
        results["_analysis"] = "Dati Asia non disponibili."

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
