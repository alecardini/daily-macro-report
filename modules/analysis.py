"""
Micro-Analysis Engine

Generates data-driven contextual analysis for each asset.
Input: price data, changes, volume, flows, sentiment.
Output: concise text (~3-5 sentences) describing the current scenario.
"""


def _trend_label(pct):
    """Convert % change to trend label."""
    if pct is None:
        return "flat", "neutral"
    p = float(pct)
    if p > 3:
        return "strong rally", "up"
    elif p > 1:
        return "moderate gain", "up"
    elif p > 0.2:
        return "slight advance", "up"
    elif p < -3:
        return "sharp decline", "down"
    elif p < -1:
        return "moderate decline", "down"
    elif p < -0.2:
        return "slight pullback", "down"
    else:
        return "broadly flat", "neutral"


def _vol_label(vol_24h, mkt_cap):
    """Assess volume relative to market cap."""
    if not vol_24h or not mkt_cap or mkt_cap == 0:
        return ""
    ratio = vol_24h / mkt_cap
    if ratio > 0.15:
        return "High volume — intense activity."
    elif ratio > 0.07:
        return "Volume in line with average."
    else:
        return "Low volume — reduced liquidity."


def _ath_context(ath_pct):
    """Context about distance from ATH."""
    if ath_pct is None:
        return ""
    try:
        p = float(str(ath_pct).replace("%", ""))
        if p > -5:
            return "Near all-time highs."
        elif p > -20:
            return f"{abs(p):.0f}% below ATH — potential resistance zone."
        elif p > -50:
            return f"{abs(p):.0f}% below ATH — in recovery phase."
        else:
            return f"{abs(p):.0f}% below ATH — market still significantly depressed."
    except Exception:
        return ""


def _etf_flow_context(flow_raw):
    """Interpret ETF flow direction and magnitude."""
    if flow_raw is None:
        return ""
    try:
        f = float(flow_raw)
        if f > 500_000_000:
            return "ETF: very strong inflows — strong institutional demand."
        elif f > 100_000_000:
            return "ETF: positive inflows — constructive institutional sentiment."
        elif f > 0:
            return "ETF: modest inflows — institutional interest present but contained."
        elif f < -500_000_000:
            return "ETF: massive outflows — significant institutional de-risking."
        elif f < -100_000_000:
            return "ETF: notable outflows — institutional selling pressure."
        elif f < 0:
            return "ETF: minor outflows — light profit taking."
        else:
            return "ETF: neutral flows."
    except Exception:
        return ""


def _liq_context(long_raw, short_raw):
    """Interpret liquidation data."""
    if not long_raw and not short_raw:
        return ""
    try:
        l, s = float(long_raw or 0), float(short_raw or 0)
        total = l + s
        if total < 50_000_000:
            return "24h liquidations contained — relatively orderly market."
        if l > s * 2:
            return f"Liquidations dominated by longs ({_fmt_m(l)}) — bearish squeeze underway."
        elif s > l * 2:
            return f"Liquidations dominated by shorts ({_fmt_m(s)}) — short squeeze underway."
        else:
            return f"Balanced liquidations: longs {_fmt_m(l)} / shorts {_fmt_m(s)}."
    except Exception:
        return ""


def _fmt_m(val):
    if val >= 1e9:
        return f"${val/1e9:.1f}B"
    return f"${val/1e6:.0f}M"


def _vix_context(vix_val):
    if vix_val is None:
        return ""
    try:
        v = float(vix_val)
        if v < 15:
            return f"VIX at {v:.1f} — calm market, low implied volatility."
        elif v < 20:
            return f"VIX at {v:.1f} — volatility within normal range."
        elif v < 30:
            return f"VIX at {v:.1f} — rising tension, watch for risk events."
        elif v < 40:
            return f"VIX at {v:.1f} — significant market stress, caution advised."
        else:
            return f"VIX at {v:.1f} — market panic, crisis-level reading."
    except Exception:
        return ""


def _yield_curve_context(spread_val):
    """Interpret 2Y-10Y yield curve."""
    if spread_val is None:
        return ""
    try:
        s = float(spread_val)
        if s < -0.5:
            return f"Inverted curve ({s:+.2f}%) — historical recession signal, monitor closely."
        elif s < 0:
            return f"Slightly inverted curve ({s:+.2f}%) — caution."
        elif s < 0.5:
            return f"Flat curve ({s:+.2f}%) — transition in progress."
        else:
            return f"Normal curve ({s:+.2f}%) — growth expectations intact."
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# CRYPTO ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_crypto(sym, coin_data, etf_data=None, liq_data=None):
    """Generates textual analysis for BTC, ETH, SOL."""
    if not coin_data:
        return "Data not available."

    pct_24h = coin_data.get("change_24h", 0) or 0
    pct_7d = coin_data.get("change_7d", 0) or 0
    trend_24h, dir_24h = _trend_label(pct_24h)
    trend_7d, dir_7d = _trend_label(pct_7d)
    vol_note = _vol_label(coin_data.get("volume_24h"), coin_data.get("market_cap"))
    ath_note = _ath_context(coin_data.get("ath_distance"))

    parts = []

    trend_txt = f"{sym} showing {trend_24h} over the last 24h ({coin_data.get('change_24h_fmt','')})."
    if dir_7d != dir_24h:
        trend_txt += f" 7-day trend remains {trend_7d} ({coin_data.get('change_7d_fmt','')}), signaling possible divergence."
    else:
        trend_txt += f" 7-day trend confirms {trend_7d} ({coin_data.get('change_7d_fmt','')})."
    parts.append(trend_txt)

    if vol_note:
        parts.append(vol_note)

    if ath_note:
        parts.append(ath_note)

    if etf_data:
        flow_raw = etf_data.get("total_inflow_raw")
        flow_note = _etf_flow_context(flow_raw)
        if flow_note:
            parts.append(flow_note)

    if liq_data:
        long_r = liq_data.get("long_raw", 0)
        short_r = liq_data.get("short_raw", 0)
        liq_note = _liq_context(long_r, short_r)
        if liq_note:
            parts.append(liq_note)

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# US INDICES ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_us_indices(indices, futures, yields, vix_data=None):
    """Contextual analysis for S&P 500, Dow, Nasdaq, Futures, Treasury, VIX."""
    parts = []

    sp = indices.get("S&P 500", {})
    nq = indices.get("Nasdaq", {})
    dj = indices.get("Dow Jones", {})

    if sp.get("pct_change") is not None:
        sp_trend, _ = _trend_label(sp.get("pct_change"))
        nq_trend, _ = _trend_label(nq.get("pct_change"))
        dj_trend, _ = _trend_label(dj.get("pct_change"))

        parts.append(
            f"S&P 500 {sp_trend} ({sp.get('pct_fmt','')}), "
            f"Nasdaq {nq_trend} ({nq.get('pct_fmt','')}), "
            f"Dow {dj_trend} ({dj.get('pct_fmt','')})."
        )

        sp_pct = sp.get("pct_change") or 0
        nq_pct = nq.get("pct_change") or 0
        if abs(nq_pct - sp_pct) > 1.5:
            if nq_pct > sp_pct:
                parts.append("Tech (Nasdaq) outperforming the broad market — risk-on bias toward growth.")
            else:
                parts.append("Tech (Nasdaq) underperforming the broad market — rotation toward value/defensives.")

    vix = indices.get("VIX", {})
    vix_price = vix.get("price")
    vix_note = _vix_context(vix_price)
    if vix_note:
        parts.append(vix_note)

    es = futures.get("S&P 500 Futures", {})
    nqf = futures.get("Nasdaq Futures", {})
    if es.get("pct_change") is not None:
        es_pct = es.get("pct_change") or 0
        direction = "higher" if es_pct > 0.1 else "lower" if es_pct < -0.1 else "flat"
        parts.append(
            f"Pre-market futures {direction}: ES {es.get('pct_fmt','')}, NQ {nqf.get('pct_fmt','')}."
        )

    spread = yields.get("2Y-10Y Spread", {})
    spread_val = spread.get("value")
    yc_note = _yield_curve_context(spread_val)
    if yc_note:
        parts.append(yc_note)

    y10 = yields.get("10Y Yield", {})
    if y10.get("value"):
        direction_10y = y10.get("direction", "neutral")
        if direction_10y == "up":
            parts.append(f"10Y Treasury rising to {y10.get('value_fmt','')} — potential pressure on equities (compressed multiples).")
        elif direction_10y == "down":
            parts.append(f"10Y Treasury falling to {y10.get('value_fmt','')} — supportive for equities and growth.")

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# OTHER ASSETS ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_asset(name, data):
    """Analysis for DXY, Gold, Silver, Copper."""
    if not data or data.get("price") is None:
        return "Data not available."

    pct = data.get("pct_change", 0) or 0
    trend, direction = _trend_label(pct)
    parts = []

    if "DXY" in name or "Dollar" in name:
        parts.append(f"Dollar Index showing {trend} ({data.get('pct_fmt','')}).")
        if direction == "up":
            parts.append("Strong dollar = pressure on commodities and EM markets, potential headwind for crypto and gold.")
        elif direction == "down":
            parts.append("Weak dollar = supportive for commodities, gold and USD-denominated assets.")
        else:
            parts.append("Dollar stable — currency neutrality in the short term.")

    elif "Gold" in name:
        parts.append(f"Gold showing {trend} ({data.get('pct_fmt','')}).")
        if direction == "up":
            parts.append("Gold rising = possible risk-off, increasing safe haven demand.")
        elif direction == "down":
            parts.append("Gold falling = possible risk-on, or dollar strength weighing.")
        else:
            parts.append("Gold flat — neutral market sentiment or awaiting catalysts.")

    elif "Silver" in name:
        parts.append(f"Silver showing {trend} ({data.get('pct_fmt','')}).")
        parts.append("Silver has dual nature: safe haven + industrial metal. Monitor the Gold/Silver ratio.")

    elif "Copper" in name:
        parts.append(f"Copper showing {trend} ({data.get('pct_fmt','')}).")
        if direction == "up":
            parts.append("Copper rising = signal of global growth expectations (leading indicator).")
        elif direction == "down":
            parts.append("Copper falling = signal of expected global economic slowdown — monitor.")
        else:
            parts.append("Copper stable — unchanged global growth expectations.")

    else:
        parts.append(f"{name} showing {trend} ({data.get('pct_fmt','')}).")

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL SENTIMENT ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def analyze_sentiment(sentiment):
    """Summary text of global market sentiment."""
    parts = []
    crypto_fg = sentiment.get("crypto_fg", {})
    equity_fg = sentiment.get("equity_fg", {})
    aaii = sentiment.get("aaii", {})

    c_score = crypto_fg.get("score")
    e_score = equity_fg.get("score")
    c_label = crypto_fg.get("label", "N/A")
    e_label = equity_fg.get("label", "N/A")

    if c_score is not None:
        parts.append(f"Crypto Fear & Greed (alternative.me): {c_score}/100 — {c_label}.")

    if e_score is not None:
        parts.append(f"Equity USA Fear & Greed (CNN): {e_score}/100 — {e_label}.")

    if c_score is not None and e_score is not None:
        diff = abs(c_score - e_score)
        if diff > 20:
            if c_score < e_score:
                parts.append("Divergence: crypto more pessimistic than US equity — possible de-correlation or crypto capitulation underway.")
            else:
                parts.append("Divergence: crypto more optimistic than US equity — crypto momentum independent from traditional markets.")

    bull = aaii.get("bullish")
    bear = aaii.get("bearish")
    if bull is not None and bear is not None:
        if bull > 45:
            parts.append(f"AAII Bullish at {bull:.1f}% — optimistic retail sentiment (watch for contrarian signal).")
        elif bull < 25:
            parts.append(f"AAII Bullish at {bull:.1f}% — very pessimistic retail sentiment (possible contrarian bullish signal).")
        else:
            parts.append(f"AAII Bullish {aaii.get('bullish_fmt','N/A')}, Bearish {aaii.get('bearish_fmt','N/A')} — balanced retail sentiment.")

    return " ".join(parts) if parts else "Sentiment data not available."
