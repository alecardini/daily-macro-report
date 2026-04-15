"""
Micro-Analysis Engine

Genera analisi contestuale data-driven per ogni asset.
Input: dati di prezzo, variazione, volume, flows, sentiment.
Output: testo sintetico (~3-5 righe) che descrive lo scenario attuale.
"""


def _trend_label(pct):
    """Convert % change to trend label."""
    if pct is None:
        return "stabile", "neutral"
    p = float(pct)
    if p > 3:
        return "forte rialzo", "up"
    elif p > 1:
        return "rialzo moderato", "up"
    elif p > 0.2:
        return "lieve progresso", "up"
    elif p < -3:
        return "forte ribasso", "down"
    elif p < -1:
        return "ribasso moderato", "down"
    elif p < -0.2:
        return "lieve correzione", "down"
    else:
        return "sostanzialmente piatto", "neutral"


def _vol_label(vol_24h, mkt_cap):
    """Assess volume relative to market cap."""
    if not vol_24h or not mkt_cap or mkt_cap == 0:
        return ""
    ratio = vol_24h / mkt_cap
    if ratio > 0.15:
        return "Volume elevato — attività intensa."
    elif ratio > 0.07:
        return "Volume nella norma."
    else:
        return "Volume basso — liquidità ridotta."


def _ath_context(ath_pct):
    """Context about distance from ATH."""
    if ath_pct is None:
        return ""
    try:
        p = float(str(ath_pct).replace("%", ""))
        if p > -5:
            return "Vicino ai massimi storici."
        elif p > -20:
            return f"A {abs(p):.0f}% dall'ATH — zona di possibile resistenza."
        elif p > -50:
            return f"A {abs(p):.0f}% dall'ATH — in fase di recupero."
        else:
            return f"A {abs(p):.0f}% dall'ATH — mercato ancora depresso."
    except Exception:
        return ""


def _etf_flow_context(flow_raw):
    """Interpret ETF flow direction and magnitude."""
    if flow_raw is None:
        return ""
    try:
        f = float(flow_raw)
        if f > 500_000_000:
            return "ETF: afflussi molto forti — forte domanda istituzionale."
        elif f > 100_000_000:
            return "ETF: afflussi positivi — sentiment istituzionale costruttivo."
        elif f > 0:
            return "ETF: afflussi modesti — interesse istituzionale presente ma contenuto."
        elif f < -500_000_000:
            return "ETF: deflussi massicci — de-risking istituzionale significativo."
        elif f < -100_000_000:
            return "ETF: deflussi rilevanti — pressione di vendita istituzionale."
        elif f < 0:
            return "ETF: deflussi contenuti — leggera presa di profitto."
        else:
            return "ETF: flussi neutrali."
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
            return "Liquidazioni nelle 24h contenute — mercato relativamente ordinato."
        if l > s * 2:
            return f"Liquidazioni dominate dai long ({_fmt_m(l)}) — squeeze ribassista in atto."
        elif s > l * 2:
            return f"Liquidazioni dominate dagli short ({_fmt_m(s)}) — short squeeze in atto."
        else:
            return f"Liquidazioni bilanciate: long {_fmt_m(l)} / short {_fmt_m(s)}."
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
            return f"VIX a {v:.1f} — mercato calmo, bassa volatilità implicita."
        elif v < 20:
            return f"VIX a {v:.1f} — volatilità nella norma."
        elif v < 30:
            return f"VIX a {v:.1f} — tensione in aumento, attenzione ai risk event."
        elif v < 40:
            return f"VIX a {v:.1f} — forte stress di mercato, cautela raccomandata."
        else:
            return f"VIX a {v:.1f} — panico di mercato, livello da crisi."
    except Exception:
        return ""


def _yield_curve_context(spread_val):
    """Interpret 2Y-10Y yield curve."""
    if spread_val is None:
        return ""
    try:
        s = float(spread_val)
        if s < -0.5:
            return f"Curva invertita ({s:+.2f}%) — segnale recessivo storico, monitorare."
        elif s < 0:
            return f"Curva lievemente invertita ({s:+.2f}%) — attenzione."
        elif s < 0.5:
            return f"Curva piatta ({s:+.2f}%) — transizione in atto."
        else:
            return f"Curva normale ({s:+.2f}%) — aspettative di crescita."
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# ANALISI CRYPTO
# ─────────────────────────────────────────────────────────────────────────────

def analyze_crypto(sym, coin_data, etf_data=None, liq_data=None):
    """
    Genera analisi testuale per BTC, ETH, SOL.
    """
    if not coin_data:
        return "Dati non disponibili."

    pct_24h = coin_data.get("change_24h", 0) or 0
    pct_7d = coin_data.get("change_7d", 0) or 0
    trend_24h, dir_24h = _trend_label(pct_24h)
    trend_7d, dir_7d = _trend_label(pct_7d)
    vol_note = _vol_label(coin_data.get("volume_24h"), coin_data.get("market_cap"))
    ath_note = _ath_context(coin_data.get("ath_distance"))

    parts = []

    # 1. Trend
    trend_txt = f"{sym} registra un {trend_24h} nelle ultime 24h ({coin_data.get('change_24h_fmt','')})."
    if dir_7d != dir_24h:
        trend_txt += f" Su 7 giorni il trend rimane {trend_7d} ({coin_data.get('change_7d_fmt','')}), segnalando possibile divergenza."
    else:
        trend_txt += f" Su 7 giorni il trend conferma {trend_7d} ({coin_data.get('change_7d_fmt','')})."
    parts.append(trend_txt)

    # 2. Volume
    if vol_note:
        parts.append(vol_note)

    # 3. ATH distance
    if ath_note:
        parts.append(ath_note)

    # 4. ETF flows (BTC + ETH)
    if etf_data:
        flow_raw = etf_data.get("total_inflow_raw")
        flow_note = _etf_flow_context(flow_raw)
        if flow_note:
            parts.append(flow_note)

    # 5. Liquidations
    if liq_data:
        long_r = liq_data.get("long_raw", 0)
        short_r = liq_data.get("short_raw", 0)
        liq_note = _liq_context(long_r, short_r)
        if liq_note:
            parts.append(liq_note)

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# ANALISI INDICI USA
# ─────────────────────────────────────────────────────────────────────────────

def analyze_us_indices(indices, futures, yields, vix_data=None):
    """
    Analisi contestuale per S&P 500, Dow, Nasdaq, Futures, Treasury, VIX.
    """
    parts = []

    # Indici
    sp = indices.get("S&P 500", {})
    nq = indices.get("Nasdaq", {})
    dj = indices.get("Dow Jones", {})

    if sp.get("pct_change") is not None:
        sp_trend, _ = _trend_label(sp.get("pct_change"))
        nq_trend, _ = _trend_label(nq.get("pct_change"))
        dj_trend, _ = _trend_label(dj.get("pct_change"))

        parts.append(
            f"S&P 500 in {sp_trend} ({sp.get('pct_fmt','')}), "
            f"Nasdaq {nq_trend} ({nq.get('pct_fmt','')}), "
            f"Dow {dj_trend} ({dj.get('pct_fmt','')})."
        )

        # Divergenza tech vs broad market
        sp_pct = sp.get("pct_change") or 0
        nq_pct = nq.get("pct_change") or 0
        if abs(nq_pct - sp_pct) > 1.5:
            if nq_pct > sp_pct:
                parts.append("Il tech (Nasdaq) sovraperforma il mercato allargato — risk-on sul growth.")
            else:
                parts.append("Il tech (Nasdaq) sottoperforma il mercato allargato — rotazione verso value/defensive.")

    # VIX
    vix = indices.get("VIX", {})
    vix_price = vix.get("price")
    vix_note = _vix_context(vix_price)
    if vix_note:
        parts.append(vix_note)

    # Futures pre-market
    es = futures.get("S&P 500 Futures", {})
    nqf = futures.get("Nasdaq Futures", {})
    if es.get("pct_change") is not None:
        es_pct = es.get("pct_change") or 0
        direction = "in rialzo" if es_pct > 0.1 else "in ribasso" if es_pct < -0.1 else "piatti"
        parts.append(
            f"Futures pre-market {direction}: ES {es.get('pct_fmt','')}, NQ {nqf.get('pct_fmt','')}."
        )

    # Yield curve
    spread = yields.get("2Y-10Y Spread", {})
    spread_val = spread.get("value")
    yc_note = _yield_curve_context(spread_val)
    if yc_note:
        parts.append(yc_note)

    # 10Y Treasury context
    y10 = yields.get("10Y Yield", {})
    if y10.get("value"):
        v = y10["value"]
        direction_10y = y10.get("direction", "neutral")
        if direction_10y == "up":
            parts.append(f"Treasury 10Y in salita a {y10.get('value_fmt','')} — possibile pressione su equity (multipli compressi).")
        elif direction_10y == "down":
            parts.append(f"Treasury 10Y in calo a {y10.get('value_fmt','')} — supporto per equity e growth.")

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# ANALISI ALTRI ASSET
# ─────────────────────────────────────────────────────────────────────────────

def analyze_asset(name, data):
    """
    Analisi per DXY, Gold, Silver, Copper.
    """
    if not data or data.get("price") is None:
        return "Dati non disponibili."

    pct = data.get("pct_change", 0) or 0
    trend, direction = _trend_label(pct)
    parts = []

    # Asset-specific context
    if "DXY" in name or "Dollar" in name:
        parts.append(f"Il Dollar Index è in {trend} ({data.get('pct_fmt','')}).")
        if direction == "up":
            parts.append("Dollaro forte = pressione su commodity e mercati emergenti, potenziale vento contrario per crypto e oro.")
        elif direction == "down":
            parts.append("Dollaro debole = supporto per commodity, oro e asset denominati in USD.")
        else:
            parts.append("Dollaro stabile — neutralità valutaria nel breve.")

    elif "Gold" in name:
        parts.append(f"L'oro è in {trend} ({data.get('pct_fmt','')}).")
        if direction == "up":
            parts.append("Oro in salita = possibile risk-off, domanda di safe haven in aumento.")
        elif direction == "down":
            parts.append("Oro in calo = possibile risk-on, o forza del dollaro che pesa.")
        else:
            parts.append("Oro piatto — sentiment di mercato neutro o attesa di catalizzatori.")

    elif "Silver" in name:
        parts.append(f"L'argento è in {trend} ({data.get('pct_fmt','')}).")
        parts.append("L'argento ha doppia natura: safe haven + metallo industriale. Monitora il rapporto Gold/Silver.")

    elif "Copper" in name:
        parts.append(f"Il rame è in {trend} ({data.get('pct_fmt','')}).")
        if direction == "up":
            parts.append("Rame in salita = segnale di aspettative di crescita globale (indicatore leading).")
        elif direction == "down":
            parts.append("Rame in calo = segnale di rallentamento economico globale atteso — monitorare.")
        else:
            parts.append("Rame stabile — aspettative di crescita globale invariate.")

    else:
        parts.append(f"{name} in {trend} ({data.get('pct_fmt','')}).")

    return " ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# ANALISI SENTIMENT GLOBALE
# ─────────────────────────────────────────────────────────────────────────────

def analyze_sentiment(sentiment):
    """
    Testo di sintesi del sentiment globale di mercato.
    """
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

    # Divergenza crypto vs equity
    if c_score is not None and e_score is not None:
        diff = abs(c_score - e_score)
        if diff > 20:
            if c_score < e_score:
                parts.append("Divergenza: crypto più pessimista dell'equity USA — possibile de-correlazione o capitolazione crypto in atto.")
            else:
                parts.append("Divergenza: crypto più ottimista dell'equity USA — momentum crypto indipendente dal mercato tradizionale.")

    # AAII
    bull = aaii.get("bullish")
    bear = aaii.get("bearish")
    if bull is not None and bear is not None:
        if bull > 45:
            parts.append(f"AAII Bullish al {bull:.1f}% — sentiment retail ottimista (attenzione al contrarian signal).")
        elif bull < 25:
            parts.append(f"AAII Bullish al {bull:.1f}% — sentiment retail molto pessimista (possibile segnale contrarian rialzista).")
        else:
            parts.append(f"AAII Bullish {aaii.get('bullish_fmt','N/A')}, Bearish {aaii.get('bearish_fmt','N/A')} — sentiment retail bilanciato.")

    return " ".join(parts) if parts else "Dati sentiment non disponibili."
