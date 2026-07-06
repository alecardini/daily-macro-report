"""
HTML Template Generator — aggiornato con:
- Micro analisi per ogni asset
- VIX nella sezione sentiment
- ETF flows BTC/ETH da farside.co.uk
- Dual F&G label (alternative.me + nota CMC)
- News da fonti multiple (finance + world + geopolitics)
"""

from datetime import datetime
import pytz

ROME_TZ = pytz.timezone("Europe/Rome")


def cc(direction):
    if direction == "up": return "positive"
    if direction == "down": return "negative"
    return "neutral"


def arrow(direction):
    if direction == "up": return "▲"
    if direction == "down": return "▼"
    return "—"


# ─────────────────────────────────────────────────────────────
# CALENDARIO ECONOMICO
# ─────────────────────────────────────────────────────────────

def _render_calendar_table(events):
    rows = ""
    for ev in events:
        actual = ev.get("actual", "—")
        actual_overdue = ev.get("actual_overdue", False)
        actual_cls = "actual-ok" if actual not in ["—", "", "N/A"] else ""
        if actual_overdue:
            actual_cell = '<a href="https://www.investing.com/economic-calendar/" target="_blank" class="actual-pending-btn" title="Data released but not yet updated by Forex Factory — click to see the value on Investing.com">🔗 View data</a>'
        else:
            actual_cell = f'<span class="{actual_cls}">{actual}</span>'
        is_holiday = ev.get('impact') == 'CLOSED'
        is_early   = ev.get('impact') == 'EARLY'
        impact_val = ev.get('impact', 'HIGH')
        if impact_val == 'MED':
            impact_badge_cls = 'impact-med'
        elif impact_val == 'WL':
            impact_badge_cls = 'impact-wl'
        elif impact_val == 'CLOSED':
            impact_badge_cls = 'impact-chiuso'
        elif impact_val == 'EARLY':
            impact_badge_cls = 'impact-early'
        else:
            impact_badge_cls = ''
        row_cls = 'holiday-row' if is_holiday else ('early-close-row' if is_early else '')
        rows += f"""
        <tr class="{row_cls}">
            <td class="time-cell">{ev.get('time','—')}</td>
            <td><span class="flag-badge">{ev.get('flag','')} {ev.get('currency','—')}</span></td>
            <td class="event-name">{ev.get('event','—')}</td>
            <td><span class="impact-badge {impact_badge_cls}">{impact_val}</span></td>
            <td class="data-cell">{ev.get('forecast','—')}</td>
            <td class="data-cell">{ev.get('previous','—')}</td>
            <td class="data-cell {actual_cls}">{actual_cell}</td>
        </tr>"""
    return f"""
    <div class="table-wrapper">
        <table class="data-table">
            <thead><tr>
                <th>Time (Rome)</th><th>Currency</th><th>Event</th>
                <th>Impact</th><th>Forecast</th><th>Previous</th><th>Actual</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table>
    </div>"""


def render_calendar(events_data):
    """events_data can be dict {day_label: [events]} or list (legacy)."""
    if not events_data:
        return "<p class='no-data'>No high-impact events in the next 3 days.</p>"

    # Legacy: plain list → wrap in dict
    if isinstance(events_data, list):
        from datetime import datetime
        import pytz
        day_label = datetime.now(pytz.timezone("Europe/Rome")).strftime("%A %d %B")
        events_data = {day_label: events_data}

    html = ""
    from datetime import datetime
    import pytz
    today_label = datetime.now(pytz.timezone("Europe/Rome")).strftime("%A %d %B")

    for day_label, events in events_data.items():
        is_today = day_label == today_label
        badge = '<span class="day-today-badge">TODAY</span>' if is_today else ""
        html += f'<div class="cal-day-header">{day_label} {badge}</div>'
        if events:
            html += _render_calendar_table(events)
        else:
            html += "<p class='no-data' style='padding:8px 0'>No HIGH IMPACT events</p>"

    return html


# ─────────────────────────────────────────────────────────────
# NEWS
# ─────────────────────────────────────────────────────────────

def render_news_item(art, idx):
    has_full = art.get("has_full_text", False)
    full_badge = '<span class="full-badge">FULL TEXT</span>' if has_full else ""
    return f"""
    <div class="news-item">
        <div class="news-header">
            <span class="news-source">{art.get('source','')}</span>
            {full_badge}
            <span class="news-num">#{idx}</span>
        </div>
        <a href="{art.get('url','#')}" target="_blank" class="news-title">{art.get('title','')}</a>
        <p class="news-summary">{art.get('summary','')}</p>
    </div>"""


def render_news_section(articles, empty="No news available."):
    if not articles:
        return f"<p class='no-data'>{empty}</p>"
    html = '<div class="news-grid">'
    for i, a in enumerate(articles, 1):
        html += render_news_item(a, i)
    html += "</div>"
    return html


# ─────────────────────────────────────────────────────────────
# SENTIMENT + VIX
# ─────────────────────────────────────────────────────────────

def render_sentiment(sentiment, vix_data=None, sentiment_analysis=""):
    crypto_fg = sentiment.get("crypto_fg", {})
    equity_fg = sentiment.get("equity_fg", {})
    aaii = sentiment.get("aaii", {})

    def gauge(score, label, color, title, prev, source, note=""):
        sv = score if score is not None else 0
        prev_html = f'<span class="prev-score">Yesterday: {prev}</span>' if prev else ""
        note_html = f'<div class="fg-note">{note}</div>' if note else ""
        return f"""
        <div class="sentiment-card">
            <h4>{title}</h4>
            <div class="gauge-bar"><div class="gauge-fill" style="width:{sv}%;background:{color}"></div></div>
            <div class="gauge-labels"><span>Fear</span><span>Neutral</span><span>Greed</span></div>
            <div class="gauge-score" style="color:{color}">{sv if score is not None else 'N/A'}</div>
            <div class="gauge-label" style="color:{color}">{label}</div>
            {prev_html}
            {note_html}
            <span class="source-tag">{source}</span>
        </div>"""

    crypto_html = gauge(
        crypto_fg.get("score"), crypto_fg.get("label","N/A"),
        crypto_fg.get("color","#888"), "Crypto Fear & Greed",
        crypto_fg.get("prev_score"), crypto_fg.get("source","alternative.me"),
        note=crypto_fg.get("note","")
    )
    equity_html = gauge(
        equity_fg.get("score"), equity_fg.get("label","N/A"),
        equity_fg.get("color","#888"), "Equity USA Fear & Greed (CNN)",
        equity_fg.get("prev_score"), equity_fg.get("source","CNN Money"),
    )

    # AAII
    aaii_html = f"""
    <div class="sentiment-card">
        <h4>AAII Investor Sentiment</h4>
        <div class="aaii-bars">
            <div class="aaii-row">
                <span class="aaii-label positive">Bullish</span>
                <div class="aaii-bar-wrap"><div class="aaii-bar-fill positive" style="width:{aaii.get('bullish') or 0:.0f}%"></div></div>
                <span class="aaii-val">{aaii.get('bullish_fmt','N/A')}</span>
            </div>
            <div class="aaii-row">
                <span class="aaii-label neutral-c">Neutral</span>
                <div class="aaii-bar-wrap"><div class="aaii-bar-fill neutral-c" style="width:{aaii.get('neutral') or 0:.0f}%"></div></div>
                <span class="aaii-val">{aaii.get('neutral_fmt','N/A')}</span>
            </div>
            <div class="aaii-row">
                <span class="aaii-label negative">Bearish</span>
                <div class="aaii-bar-wrap"><div class="aaii-bar-fill negative" style="width:{aaii.get('bearish') or 0:.0f}%"></div></div>
                <span class="aaii-val">{aaii.get('bearish_fmt','N/A')}</span>
            </div>
        </div>
        <span class="source-tag">AAII — Weekly survey{(' · ' + aaii['survey_date']) if aaii.get('survey_date') else ''}</span>
    </div>"""

    # VIX card
    vix_html = ""
    if vix_data and vix_data.get("price") is not None:
        vix_val = vix_data["price"]
        vix_pct = vix_data.get("pct_fmt", "")
        if vix_val < 15:
            vix_label, vix_color = "Calm", "#27ae60"
        elif vix_val < 20:
            vix_label, vix_color = "Normal", "#2ecc71"
        elif vix_val < 30:
            vix_label, vix_color = "Elevated", "#f39c12"
        elif vix_val < 40:
            vix_label, vix_color = "High Stress", "#e67e22"
        else:
            vix_label, vix_color = "Panic", "#e74c3c"

        vix_html = f"""
        <div class="sentiment-card vix-card">
            <h4>VIX — Volatility Index</h4>
            <div class="vix-value" style="color:{vix_color}">{vix_val:.1f}</div>
            <div class="vix-label" style="color:{vix_color}">{vix_label}</div>
            <div class="vix-change {cc(vix_data.get('direction','neutral'))}">{vix_pct}</div>
            <div class="vix-scale">
                <span class="positive">0–15 Calm</span>
                <span class="neutral-c">15–25 Normal</span>
                <span class="negative">25+ Stress</span>
            </div>
            <span class="source-tag">CBOE via Yahoo Finance</span>
        </div>"""

    # Analysis text
    analysis_html = f'<div class="analysis-box"><p>{sentiment_analysis}</p></div>' if sentiment_analysis else ""

    return f"""
    {analysis_html}
    <div class="sentiment-grid">
        {crypto_html}
        {equity_html}
        {aaii_html}
        {vix_html}
    </div>"""


# ─────────────────────────────────────────────────────────────
# CRYPTO
# ─────────────────────────────────────────────────────────────

def render_crypto(crypto_data, analyses=None):
    if analyses is None:
        analyses = {}
    prices = crypto_data.get("prices", {})
    btc_etf = crypto_data.get("btc_etf", {})
    eth_etf = crypto_data.get("eth_etf", {})
    sol_etf = crypto_data.get("sol_etf", {})
    liquidations = crypto_data.get("liquidations", {})
    gd = prices.get("_global", {})

    # Global banner
    tc_chg = gd.get("total_market_cap_change_24h")
    tc_chg_fmt = f"{'+' if (tc_chg or 0) > 0 else ''}{tc_chg:.2f}%" if tc_chg else ""
    tc_dir = "positive" if (tc_chg or 0) > 0 else "negative"
    global_html = f"""
    <div class="global-banner">
        <span>Total Crypto Market Cap: <strong>{gd.get('total_market_cap','N/A')}</strong>
        {'<span class="'+tc_dir+'"> '+tc_chg_fmt+'</span>' if tc_chg_fmt else ""}
        </span>
        <span>BTC Dominance: <strong>{gd.get('btc_dominance','N/A')}</strong></span>
        <span>ETH Dominance: <strong>{gd.get('eth_dominance','N/A')}</strong></span>
    </div>""" if gd else ""

    coins_html = '<div class="crypto-grid">'
    for sym in ["BTC", "ETH", "SOL"]:
        coin = prices.get(sym, {})
        if not coin:
            continue
        liq = liquidations.get(sym, {})
        etf_data = btc_etf if sym == "BTC" else (eth_etf if sym == "ETH" else sol_etf)
        direction = coin.get("direction", "neutral")
        analysis_text = analyses.get(sym, "")

        # Analysis block
        analysis_html = f'<div class="analysis-box"><p>{analysis_text}</p></div>' if analysis_text else ""

        # ETF flows block
        etf_html = ""
        if etf_data and sym in ["BTC", "ETH", "SOL"]:
            farside = etf_data.get("farside", {})
            flow_raw = etf_data.get("total_inflow_raw", 0) or 0
            flow_dir = "positive" if flow_raw > 0 else "negative" if flow_raw < 0 else "neutral"
            flow_arr = "▲" if flow_raw > 0 else "▼" if flow_raw < 0 else "—"
            flow_fmt = etf_data.get("total_inflow_24h", "N/A")
            last_date = farside.get("last_date", "") if farside else ""
            cum_fmt = farside.get("cumulative_fmt", "N/A") if farside else "N/A"

            # Per-ETF breakdown
            by_etf_html = ""
            if farside and farside.get("by_etf"):
                sorted_etfs = sorted(farside["by_etf"].items(), key=lambda x: abs(x[1]), reverse=True)[:5]
                for etf_sym, flow_val in sorted_etfs:
                    etf_dir = "positive" if flow_val > 0 else "negative" if flow_val < 0 else "neutral"
                    etf_arr = "▲" if flow_val > 0 else "▼" if flow_val < 0 else "—"
                    by_etf_html += f'<div class="etf-row"><span class="etf-sym">{etf_sym}</span><span class="{etf_dir}">{etf_arr} ${abs(flow_val):.1f}M</span></div>'

            sosovalue_map = {"BTC": "https://sosovalue.com/assets/etf/us-btc-spot", "ETH": "https://sosovalue.com/assets/etf/us-eth-spot", "SOL": "https://sosovalue.com/assets/etf/us-sol-spot"}
            farside_map   = {"BTC": "https://farside.co.uk/bitcoin-etf-flow-all-data/", "ETH": "https://farside.co.uk/ethereum-etf-flow-all-data/", "SOL": "https://farside.co.uk/sol/"}
            sosovalue_url = sosovalue_map.get(sym, "#")
            farside_url   = farside_map.get(sym, "#")
            etf_html = f"""
            <div class="etf-block">
                <div class="etf-title">{sym} ETF — Daily Flows</div>
                <div class="etf-flow-main {flow_dir}">{flow_arr} {flow_fmt}
                    <span class="etf-date">{last_date}</span>
                </div>
                <div class="etf-cum">Historical cumulative AUM: {cum_fmt}</div>
                {by_etf_html}
                <div class="etf-links">
                    <a href="{farside_url}" target="_blank">farside.co.uk</a>
                    &nbsp;|&nbsp;
                    <a href="{sosovalue_url}" target="_blank">SoSoValue</a>
                    &nbsp;|&nbsp;
                    <a href="https://www.coinglass.com/bitcoin-etf" target="_blank">CoinGlass ETF</a>
                </div>
            </div>"""

        # Funding Rate + Open Interest block
        fi_html = ""
        fr = liq.get("funding_rate")
        oi = liq.get("open_interest")
        fr_dir = liq.get("funding_direction", "neutral")
        fr_note = liq.get("funding_note", "")
        oi_chg = liq.get("oi_change_fmt", "")
        oi_chg_dir = liq.get("oi_change_dir", "neutral")
        fi_source = liq.get("source", "Binance FAPI (public)")
        oi_chg_html = f' <span class="{oi_chg_dir}" style="font-size:9px">{oi_chg} 24h</span>' if oi_chg else ""
        if fr and fr != "N/A":
            fi_html = f"""
            <div class="fi-block">
                <div class="fi-row">
                    <span class="fi-label">Funding Rate</span>
                    <span class="{fr_dir}">{fr}</span>
                </div>
                <div class="fi-note">{fr_note}</div>
                <div class="fi-row">
                    <span class="fi-label">Open Interest</span>
                    <span>{oi or 'N/A'}{oi_chg_html}</span>
                </div>
                <span class="source-tag">{fi_source}</span>
            </div>"""

        # Liquidations block
        liq_html = ""
        liq_total = liq.get("total_24h", "")
        if liq_total and liq_total not in ["N/A", "—", ""]:
            long_r = liq.get("long_raw", 0)
            short_r = liq.get("short_raw", 0)
            dom = "long" if long_r > short_r else "short"
            liq_html = f"""
            <div class="liq-block">
                <div class="liq-title">Liquidations 24h</div>
                <div class="liq-total">{liq_total}</div>
                <div class="liq-detail">
                    <span class="positive">Long: {liq.get('long_24h','—')}</span>
                    <span class="negative">Short: {liq.get('short_24h','—')}</span>
                </div>
                <span class="source-tag">{liq.get('source','Coinalyze')}</span>
            </div>"""
        else:
            liq_url = liq.get("url", "https://www.coinglass.com/LiquidationData")
            liq_html = f'<div class="liq-placeholder"><a href="{liq_url}" target="_blank">→ Liquidation data on CoinGlass (API key required)</a></div>'

        coins_html += f"""
        <div class="crypto-card {cc(direction)}-border">
            <div class="crypto-header">
                <span class="crypto-sym">{sym}</span>
                <span class="crypto-rank">#{coin.get('rank','—')}</span>
                <span class="{cc(direction)} crypto-pct">{arrow(direction)} {coin.get('change_24h_fmt','')}</span>
            </div>
            <div class="crypto-price">{coin.get('price_fmt','N/A')}</div>
            <div class="crypto-sub">
                <span class="sub-label">7d:</span>
                <span class="{cc('up' if (coin.get('change_7d') or 0) > 0 else 'down')}">{coin.get('change_7d_fmt','N/A')}</span>
                &nbsp;|&nbsp;
                <span class="sub-label">Market Cap:</span>
                <strong>{coin.get('market_cap_fmt','N/A')}</strong>
                &nbsp;|&nbsp;
                <span class="sub-label">Vol 24h:</span>
                <strong>{coin.get('volume_24h_fmt','N/A')}</strong>
                &nbsp;|&nbsp;
                <span class="sub-label">From ATH:</span>
                <span class="negative">{coin.get('ath_distance','N/A')}</span>
            </div>
            {analysis_html}
            {etf_html}
            {fi_html}
            {liq_html}
        </div>"""

    coins_html += "</div>"
    return global_html + coins_html


# ─────────────────────────────────────────────────────────────
# INDICI USA + FUTURES + TREASURY
# ─────────────────────────────────────────────────────────────

def render_indices(indices, futures, yields, analysis_text=""):
    analysis_html = f'<div class="analysis-box"><p>{analysis_text}</p></div>' if analysis_text else ""

    def asset_card(data, show_label=None):
        d = data.get("direction","neutral")
        extra = f'<div class="asset-extra">{show_label}</div>' if show_label else ""
        return f"""
        <div class="asset-card {cc(d)}-border">
            <div class="asset-name">{data.get('name', data.get('symbol',''))}</div>
            <div class="asset-price">{data.get('price_fmt','N/A')}</div>
            <div class="asset-change {cc(d)}">{arrow(d)} {data.get('pct_fmt','N/A')} <span class="change-abs">{data.get('change_fmt','')}</span></div>
            {extra}
        </div>"""

    idx_html = '<div class="assets-grid">'
    for name, data in indices.items():
        if name == "VIX":
            continue  # VIX è nel sentiment
        idx_html += asset_card(data)
    idx_html += "</div>"

    fut_html = '<div class="assets-grid">'
    for name, data in futures.items():
        fut_html += asset_card(data)
    fut_html += "</div>"

    yld_html = '<div class="yields-grid">'
    for name, data in yields.items():
        if name.startswith("_"):
            continue  # _signals è renderizzato a parte
        if name == "2Y-10Y Spread":
            note = data.get("note","")
            note_cls = "negative" if note == "Inverted" else "positive"
            yld_html += f"""
            <div class="yield-card spread-card">
                <div class="yield-name">{name}</div>
                <div class="yield-val {cc(data.get('direction','neutral'))}">{data.get('value_fmt','N/A')}</div>
                <div class="yield-note {note_cls}">{note}</div>
                <span class="source-tag">{data.get('source','FRED')}</span>
            </div>"""
        else:
            change_disp = data.get('change_bps_fmt', data.get('change_fmt',''))
            yld_html += f"""
            <div class="yield-card">
                <div class="yield-name">{name}</div>
                <div class="yield-val {cc(data.get('direction','neutral'))}">{data.get('value_fmt','N/A')}</div>
                <div class="yield-change">{change_disp}</div>
                <span class="source-tag">{data.get('source','FRED')}</span>
            </div>"""
    yld_html += "</div>"

    # ── Rate Signals & Credit Stress (FRED) ──
    signals = yields.get("_signals") or {}
    signals_html = ""
    if any(signals.get(k) for k in ("spreads", "inflation", "credit")):
        cards = ""
        for nm, d in signals.get("spreads", {}).items():
            cards += f"""
            <div class="yield-card">
                <div class="yield-cat">Curve</div>
                <div class="yield-name">{nm}</div>
                <div class="yield-val {d.get('dir','neutral')}">{d.get('value_fmt','N/A')}</div>
                <div class="yield-note {d.get('dir','neutral')}">{d.get('note','')}</div>
                <div class="yield-change">{d.get('change_bps_fmt','')}</div>
            </div>"""
        for nm, d in signals.get("inflation", {}).items():
            cards += f"""
            <div class="yield-card">
                <div class="yield-cat">Inflation</div>
                <div class="yield-name">{nm}</div>
                <div class="yield-val {d.get('dir','neutral')}">{d.get('value_fmt','N/A')}</div>
                <div class="yield-change">{d.get('change_bps_fmt','')}</div>
            </div>"""
        for nm, d in signals.get("credit", {}).items():
            wid = "widening ▲" if d.get("widening") else "tightening ▼"
            cards += f"""
            <div class="yield-card">
                <div class="yield-cat">Credit</div>
                <div class="yield-name">{nm}</div>
                <div class="yield-val {d.get('dir','neutral')}">{d.get('value_fmt','N/A')}</div>
                <div class="yield-note {d.get('dir','neutral')}">{d.get('pctile_fmt','')} · {d.get('label','')}</div>
                <div class="yield-change">{d.get('change_bps_fmt','')} · {wid}</div>
            </div>"""
        signals_html = f"""
    <div class="subsection">
        <h3 class="subsection-title">Rate Signals & Credit Stress — FRED</h3>
        <div class="yields-grid">{cards}</div>
        <div class="pc-note" style="margin-top:10px">
            <strong>How to read:</strong> Curve spreads &lt;0 = inverted (recession signal, the 3m10y is the NY Fed's preferred gauge).
            Real yield up = tighter financial conditions (headwind for risk assets). Breakeven = market-priced inflation.
            Credit OAS shown as percentile vs its own history since 1997 — low percentile = tight/complacent, a widening move often precedes risk-off before equities react.
        </div>
    </div>"""

    return f"""
    {analysis_html}
    <div class="subsection">
        <h3 class="subsection-title">US Indices</h3>
        {idx_html}
    </div>
    <div class="subsection">
        <h3 class="subsection-title">Pre-Market Futures</h3>
        {fut_html}
    </div>
    <div class="subsection">
        <h3 class="subsection-title">Treasury Yields (US) — FRED / Federal Reserve</h3>
        {yld_html}
    </div>
    {signals_html}"""


# ─────────────────────────────────────────────────────────────
# ALTRI ASSET
# ─────────────────────────────────────────────────────────────

def render_other_assets(assets, gold_etf, asset_analyses=None):
    if asset_analyses is None:
        asset_analyses = {}

    html = ""
    for name, data in assets.items():
        d = data.get("direction","neutral")
        analysis_text = asset_analyses.get(name, "")
        analysis_html = f'<div class="analysis-box analysis-box-sm"><p>{analysis_text}</p></div>' if analysis_text else ""

        # Gold ETF supplement
        etf_supp = ""
        if "Gold" in name and gold_etf:
            gld = gold_etf.get("GLD (SPDR Gold)", {})
            iau = gold_etf.get("IAU (iShares Gold)", {})
            etf_supp = f"""
            <div class="gold-etf-row">
                <span class="etf-tag">GLD</span> {gld.get('pct_fmt','N/A')} | AUM {gld.get('aum','N/A')}
                &nbsp;&nbsp;
                <span class="etf-tag">IAU</span> {iau.get('pct_fmt','N/A')} | AUM {iau.get('aum','N/A')}
            </div>"""

        html += f"""
        <div class="asset-row-card {cc(d)}-border">
            <div class="arc-left">
                <div class="arc-name">{name}</div>
                <div class="arc-price">{data.get('price_fmt','N/A')}</div>
                <div class="arc-change {cc(d)}">{arrow(d)} {data.get('pct_fmt','N/A')} <span class="change-abs">{data.get('change_fmt','')}</span></div>
                {etf_supp}
            </div>
            <div class="arc-right">
                {analysis_html}
            </div>
        </div>"""

    return html


# ─────────────────────────────────────────────────────────────
# ASIA SESSION
# ─────────────────────────────────────────────────────────────

def render_asia(asia_data):
    if not asia_data:
        return "<p class='no-data'>Asia data not available.</p>"

    analysis = asia_data.pop("_analysis", "") if isinstance(asia_data, dict) else ""
    crypto_asia = asia_data.pop("_crypto_asia", {}) if isinstance(asia_data, dict) else {}
    analysis_html = f'<div class="analysis-box"><p>{analysis}</p></div>' if analysis else ""

    # Indices grid
    cards = '<div class="assets-grid">'
    for name, d in asia_data.items():
        if name.startswith("_"):
            continue
        direction = d.get("direction", "neutral")
        cards += f"""
        <div class="asset-card {cc(direction)}-border">
            <div class="asset-name">{name}</div>
            <div class="asset-price">{d.get('price_fmt','N/A')}</div>
            <div class="asset-change {cc(direction)}">{arrow(direction)} {d.get('pct_fmt','N/A')} <span class="change-abs">{d.get('change_fmt','')}</span></div>
        </div>"""
    cards += "</div>"

    # Crypto during Asia session
    crypto_html = ""
    if crypto_asia:
        session_label = next(iter(crypto_asia.values()), {}).get("session_label", "00:00-08:00 UTC")
        crypto_html = f'<div class="subsection-title" style="margin-top:18px">Crypto — Asian Session ({session_label})</div>'
        crypto_html += '<div class="assets-grid">'
        for sym in ["BTC", "ETH", "SOL"]:
            d = crypto_asia.get(sym)
            if not d:
                continue
            direction = d.get("direction", "neutral")
            crypto_html += f"""
            <div class="asset-card {cc(direction)}-border">
                <div class="asset-name">{sym}</div>
                <div class="asset-price">${d.get('close', 0):,.2f}</div>
                <div class="asset-change {cc(direction)}">{arrow(direction)} {d.get('pct_fmt','N/A')}</div>
                <div class="asset-extra">H: ${d.get('high',0):,.2f} &nbsp; L: ${d.get('low',0):,.2f}</div>
            </div>"""
        crypto_html += "</div>"

    # Restore keys
    asia_data["_analysis"] = analysis
    asia_data["_crypto_asia"] = crypto_asia
    return analysis_html + cards + crypto_html


# ─────────────────────────────────────────────────────────────
# STABLECOIN LIQUIDITY (DefiLlama)
# ─────────────────────────────────────────────────────────────

def render_stablecoin_liquidity(d):
    if not d or d.get("total_fmt") in (None, "N/A"):
        return "<p class='no-data'>Stablecoin data not available.</p>"
    bd = " · ".join(f"{b['symbol']} {b['cap_fmt']}" for b in d.get("breakdown", []))
    return f"""
    <div class="yields-grid">
        <div class="yield-card">
            <div class="yield-cat">Liquidity</div>
            <div class="yield-name">Total Supply</div>
            <div class="yield-val neutral">{d.get('total_fmt','N/A')}</div>
            <div class="yield-change">{bd}</div>
        </div>
        <div class="yield-card">
            <div class="yield-cat">Flow</div>
            <div class="yield-name">Netflow 7d</div>
            <div class="yield-val {d.get('nf7_dir','neutral')}">{d.get('nf7_pct_fmt','—')}</div>
            <div class="yield-change">{d.get('nf7_abs_fmt','')}</div>
        </div>
        <div class="yield-card">
            <div class="yield-cat">Flow</div>
            <div class="yield-name">Netflow 30d</div>
            <div class="yield-val {d.get('nf30_dir','neutral')}">{d.get('nf30_pct_fmt','—')}</div>
            <div class="yield-note {d.get('nf30_dir','neutral')}">{d.get('nf30_abs_fmt','')} · {d.get('pctile_fmt','')} · {d.get('label','')}</div>
        </div>
    </div>
    <div class="pc-note" style="margin-top:10px">
        <strong>How to read:</strong> Total stablecoin supply is the "dry powder" in the crypto system.
        Expanding = fiat entering (structural tailwind); contracting = liquidity leaving (headwind).
        Slow structural signal — watch the trend, not a single day. Supply normally drifts up ~+1–3%/month, so flat-to-negative is already below trend. Percentile is vs full DefiLlama history.
    </div>"""


# ─────────────────────────────────────────────────────────────
# DERIBIT P/C RATIO
# ─────────────────────────────────────────────────────────────

def render_pc_ratios(pc_data):
    if not pc_data:
        return "<p class='no-data'>P/C data not available.</p>"

    html = '<div class="pc-grid">'
    for sym, d in pc_data.items():
        pc_vol = d.get("pc_volume_fmt", "N/A")
        pc_oi  = d.get("pc_oi_fmt", "N/A")
        vol_dir = d.get("pc_volume_dir", "neutral")
        oi_dir  = d.get("pc_oi_dir", "neutral")
        vol_lbl = d.get("pc_volume_label", "")
        oi_lbl  = d.get("pc_oi_label", "")

        dvol      = d.get("dvol_fmt", "N/A")
        dvol_chg  = d.get("dvol_change_fmt", "")
        dvol_dir  = d.get("dvol_dir", "neutral")
        dvol_lbl  = d.get("dvol_label", "")

        html += f"""
        <div class="pc-card">
            <div class="pc-header">{sym} — Put/Call Ratio</div>
            <div class="pc-row">
                <span class="pc-label">P/C Volume (24h)</span>
                <span class="pc-val {vol_dir}">{pc_vol}</span>
                <span class="pc-interp">{vol_lbl}</span>
            </div>
            <div class="pc-row">
                <span class="pc-label">P/C Open Interest</span>
                <span class="pc-val {oi_dir}">{pc_oi}</span>
                <span class="pc-interp">{oi_lbl}</span>
            </div>
            <div class="pc-row">
                <span class="pc-label">DVOL (implied vol)</span>
                <span class="pc-val {dvol_dir}">{dvol} <span class="dvol-chg">{dvol_chg} 24h</span></span>
                <span class="pc-interp">{dvol_lbl}</span>
            </div>
            <div class="pc-scale">
                <span class="warning">&lt;0.40 Euphoria</span>
                <span class="positive">0.40–0.65 Bullish</span>
                <span class="neutral-c">0.65–0.75 Neutral</span>
                <span class="negative">0.75–1.0 Defensive</span>
                <span class="warning">&gt;1.20 Extreme Fear</span>
            </div>
            <span class="source-tag">Deribit (public API)</span>
        </div>"""

    html += "</div>"
    html += """<div class="pc-note">
        <strong>How to read:</strong> Contrarian indicator — extreme values signal potential reversal.
        &lt;0.40 = call euphoria, possible top. &gt;1.20 = put panic, possible bottom.
        The "neutral" baseline in crypto is ~0.70 (not 1.0 as in equity).
        Volume P/C = intraday sentiment. OI P/C = institutional structural positioning.
        <br><strong>DVOL</strong> = Deribit's 30-day implied volatility index (the "crypto VIX", annualized %):
        low = complacency (cheap hedges, often precedes sharp moves), high = fear already priced in.
        ETH runs structurally higher than BTC, so thresholds are asset-specific.
    </div>"""
    return html


# ─────────────────────────────────────────────────────────────
# EARNINGS
# ─────────────────────────────────────────────────────────────

def _earnings_table_header():
    return """
    <div class="etable-header">
        <span class="etcol-sym">Ticker</span>
        <span class="etcol-name">Company</span>
        <span class="etcol-date">Date</span>
        <span class="etcol-time">Time</span>
        <span class="etcol-eps">EPS Actual</span>
        <span class="etcol-eps">EPS Est.</span>
        <span class="etcol-rev">Rev Est.</span>
        <span class="etcol-surp">Surprise</span>
    </div>"""


def _earnings_row(e, badge=None):
    beat = e.get("beat")
    surp_cls = "positive" if beat is True else "negative" if beat is False else "neutral-c"
    badge_html = f'<span class="earning-badge">{badge}</span>' if badge else ""

    release_time  = e.get("release_time", "—")
    release_label = e.get("release_label", "")
    if release_label == "Pre-Market":
        time_badge = '<span class="release-badge release-pre">PRE</span>'
    elif release_label == "After-Market":
        time_badge = '<span class="release-badge release-amc">AMC</span>'
    elif release_label == "During session":
        time_badge = '<span class="release-badge release-intra">INTRA</span>'
    else:
        time_badge = ""

    return f"""
    <div class="etable-row">
        <span class="etcol-sym"><span class="earning-sym">{e['symbol']}</span>{badge_html}</span>
        <span class="etcol-name earning-name">{e['name']}</span>
        <span class="etcol-date earning-date">{e['date_fmt']}</span>
        <span class="etcol-time">{release_time} {time_badge}</span>
        <span class="etcol-eps {'positive' if beat is True else 'negative' if beat is False else ''}">{e.get('eps_actual','—')}</span>
        <span class="etcol-eps neutral-c">{e.get('eps_estimate','—')}</span>
        <span class="etcol-rev neutral-c">{e.get('rev_estimate','—')}</span>
        <span class="etcol-surp {surp_cls}">{e.get('surprise','—')}</span>
    </div>"""


def render_earnings(earnings_data):
    if not earnings_data:
        return ""

    yesterday_list = earnings_data.get("yesterday", [])
    today_list     = earnings_data.get("today", [])
    upcoming       = earnings_data.get("upcoming", [])

    if not yesterday_list and not today_list and not upcoming:
        return ""

    html = ""

    # ── Ieri: actuals freschi ──
    if yesterday_list:
        html += '<div class="earnings-section-label">📋 Yesterday\'s results</div>'
        html += '<div class="etable">'
        html += _earnings_table_header()
        for e in yesterday_list:
            html += _earnings_row(e)
        html += "</div>"

    # ── Oggi: urgente ──
    if today_list:
        html += '<div class="earnings-urgent">'
        html += '<div class="earnings-section-label">🔔 Reports TODAY</div>'
        html += '<div class="etable">'
        html += _earnings_table_header()
        for e in today_list:
            html += _earnings_row(e, badge="TODAY")
        html += "</div></div>"

    # ── Prossimi 7 giorni ──
    if upcoming:
        html += '<div class="earnings-section-label" style="margin-top:18px">📅 Next 7 days</div>'
        html += '<div class="etable">'
        html += _earnings_table_header()
        for e in upcoming[:10]:
            html += _earnings_row(e)
        html += "</div>"

    return html


# ─────────────────────────────────────────────────────────────
# SECTOR ROTATION
# ─────────────────────────────────────────────────────────────

def render_sector_rotation(sr_data):
    if not sr_data:
        return "<p class='no-data'>Sector data not available.</p>"

    sectors = sr_data.get("sectors", [])
    analysis = sr_data.get("analysis", "")
    analysis_html = f'<div class="analysis-box"><p>{analysis}</p></div>' if analysis else ""

    if not sectors:
        return analysis_html or "<p class='no-data'>Sector data not available.</p>"

    max_abs_week = max(abs(s.get("pct_week") or 0) for s in sectors) or 1

    rows = ""
    for s in sectors:
        pct_w = s.get("pct_week") or 0
        direction = s.get("direction", "neutral")
        bar_w = min(abs(pct_w) / max_abs_week * 100, 100)

        pct_m_val = s.get("pct_month") or 0
        pct_q_val = s.get("pct_quarter") or 0
        dir_m = "positive" if pct_m_val >= 0 else "negative"
        dir_q = "positive" if pct_q_val >= 0 else "negative"

        rows += f"""
        <div class="sector-row">
            <span class="sector-name">{s['name']}</span>
            <span class="sector-sym">{s['symbol']}</span>
            <div class="sector-bar-wrap">
                <div class="sector-bar {direction}" style="width:{bar_w:.0f}%"></div>
            </div>
            <span class="sector-pct {direction}" title="Week">{s['pct_week_fmt']}</span>
            <span class="sector-pct-sec {dir_m}" title="Month">{s['pct_month_fmt']}</span>
            <span class="sector-pct-sec {dir_q}" title="Quarter">{s['pct_quarter_fmt']}</span>
        </div>"""

    header = """
        <div class="sector-row sector-header">
            <span class="sector-name"></span>
            <span class="sector-sym"></span>
            <div class="sector-bar-wrap"></div>
            <span class="sector-pct-label">1W</span>
            <span class="sector-pct-label">1M</span>
            <span class="sector-pct-label">3M</span>
        </div>"""

    return f"""
    {analysis_html}
    <div class="sector-grid">{header}{rows}</div>
    <span class="source-tag">Yahoo Finance — S&P 500 Sectors</span>"""


# ─────────────────────────────────────────────────────────────
# FULL HTML
# ─────────────────────────────────────────────────────────────

def generate_html(data):
    now_rome = datetime.now(ROME_TZ)
    gen_time = now_rome.strftime("%d %B %Y — %H:%M (Roma)")
    day_name = now_rome.strftime("%A")

    analyses = data.get("analyses", {})
    vix_data = data.get("indices", {}).get("VIX", {})

    earnings_html = render_earnings(data.get("earnings", {}))
    cal_html      = render_calendar(data.get("calendar", {}))
    news_html     = render_news_section(data.get("news", []))
    cb_news_html  = render_news_section(data.get("cb_news", []), "No central bank news in the last 48h.")
    sentiment_html = render_sentiment(data.get("sentiment", {}), vix_data, analyses.get("sentiment",""))
    crypto_html   = render_crypto(data.get("crypto", {}), analyses.get("crypto",{}))
    stablecoin_html = render_stablecoin_liquidity(data.get("stablecoin", {}))
    indices_html  = render_indices(data.get("indices",{}), data.get("futures",{}), data.get("yields",{}), analyses.get("indices",""))
    asia_html     = render_asia(data.get("asia", {}))
    assets_html   = render_other_assets(data.get("other_assets",{}), data.get("gold_etf",{}), analyses.get("assets",{}))
    oil_news_html = render_news_section(data.get("oil_news", []), "No Oil & Energy news available.")
    pc_html       = render_pc_ratios(data.get("pc_ratios", {}))
    sector_html   = render_sector_rotation(data.get("sector_rotation", {}))
    ai_html       = render_news_section(data.get("ai_news", []), "No AI & Robotics news available.")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Daily Macro Report — {now_rome.strftime('%d/%m/%Y')}</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
:root{{
  --bg:#0d0f14;--bg2:#141720;--bg3:#1a1e2b;--card:#1e2330;
  --border:#2a2f3f;--text:#e4e6ef;--text2:#8b90a7;--text3:#5c6080;
  --pos:#00d09c;--neg:#f44336;--neu:#888ea8;--acc:#4f8ef7;
  --acc2:#7c5cbf;--gold:#f5a623;
}}
body{{background:var(--bg);color:var(--text);font-family:'SF Mono','Fira Code',Consolas,monospace;font-size:13px;line-height:1.6}}

/* HEADER */
.header{{background:linear-gradient(135deg,#0d0f14,#1a1e2b);border-bottom:1px solid var(--border);padding:20px 32px;display:flex;justify-content:space-between;align-items:center;position:sticky;top:0;z-index:100}}
.header h1{{font-size:20px;font-weight:700;letter-spacing:1px}}.header h1 span{{color:var(--acc)}}
.header-date{{color:var(--text2);font-size:11px;margin-top:3px}}
.live-badge{{display:inline-block;background:#00d09c22;color:var(--pos);border:1px solid var(--pos);padding:2px 10px;border-radius:12px;font-size:9px;font-weight:700;letter-spacing:2px}}
.gen-time{{color:var(--text3);font-size:10px;margin-top:4px}}

/* LAYOUT */
.container{{max-width:1400px;margin:0 auto;padding:0 24px 48px}}
.section{{margin:28px 0;border:1px solid var(--border);border-radius:12px;overflow:hidden;background:var(--bg2)}}
.section-header{{background:var(--bg3);padding:12px 24px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px}}
.section-icon{{font-size:16px}}.section-title{{font-size:13px;font-weight:700;letter-spacing:1.5px;text-transform:uppercase}}
.section-sub{{color:var(--text3);font-size:10px;margin-left:auto}}
.section-body{{padding:22px}}
.subsection{{margin-bottom:24px}}.subsection:last-child{{margin-bottom:0}}
.subsection-title{{font-size:10px;color:var(--text3);text-transform:uppercase;letter-spacing:2px;margin-bottom:12px;padding-bottom:5px;border-bottom:1px solid var(--border)}}

/* ANALYSIS BOX */
.analysis-box{{background:#4f8ef711;border-left:3px solid var(--acc);border-radius:0 6px 6px 0;padding:12px 16px;margin-bottom:18px}}
.analysis-box p{{color:var(--text2);font-size:12px;line-height:1.7}}
.analysis-box-sm{{margin:10px 0 0;padding:10px 14px;font-size:11px}}
.analysis-box-sm p{{font-size:11px}}

/* CALENDAR */
.table-wrapper{{overflow-x:auto}}
.data-table{{width:100%;border-collapse:collapse;font-size:12px}}
.data-table th{{background:var(--bg3);color:var(--text3);font-size:9px;text-transform:uppercase;letter-spacing:1px;padding:9px 14px;text-align:left;border-bottom:1px solid var(--border)}}
.data-table td{{padding:11px 14px;border-bottom:1px solid var(--border);vertical-align:middle}}
.data-table tr:last-child td{{border-bottom:none}}
.data-table tr:hover td{{background:var(--bg3)}}
.time-cell{{color:var(--acc);font-weight:700;white-space:nowrap}}
.event-name{{color:var(--text);font-weight:500}}
.data-cell{{color:var(--text2);text-align:center}}
.actual-ok{{color:var(--pos);font-weight:700}}
.actual-pending-btn{{display:inline-block;background:#2c3e5022;border:1px solid #3498db;color:#3498db;padding:2px 8px;border-radius:4px;font-size:10px;font-weight:700;text-decoration:none;white-space:nowrap}}
.actual-pending-btn:hover{{background:#3498db33;color:#74b9ff}}
.flag-badge{{background:var(--bg3);border:1px solid var(--border);padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700;color:var(--gold)}}
.impact-badge{{background:#e74c3c22;color:#e74c3c;border:1px solid #e74c3c;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:700}}
.impact-badge.impact-med{{background:#f39c1222;color:#f39c12;border-color:#f39c12}}
.impact-badge.impact-chiuso{{background:#c0392b33;color:#e74c3c;border-color:#c0392b;letter-spacing:0.5px}}
.impact-badge.impact-early{{background:#f39c1233;color:#f39c12;border-color:#f39c12;letter-spacing:0.5px}}
.holiday-row{{background:#c0392b08;border-left:2px solid #c0392b}}
.early-close-row{{background:#f39c1208;border-left:2px solid #f39c12}}
.impact-badge.impact-wl{{background:#7c5cbf22;color:#a78bfa;border-color:#7c5cbf}}

/* NEWS */
.news-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:14px}}
.news-item{{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px;transition:border-color .2s}}
.news-item:hover{{border-color:var(--acc)}}
.news-header{{display:flex;align-items:center;gap:7px;margin-bottom:7px}}
.news-source{{background:var(--acc);color:#fff;padding:2px 7px;border-radius:4px;font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:1px}}
.full-badge{{background:#00d09c22;color:var(--pos);border:1px solid var(--pos);padding:1px 5px;border-radius:4px;font-size:7px;font-weight:700}}
.news-num{{color:var(--text3);font-size:9px;margin-left:auto}}
.news-title{{display:block;color:var(--text);font-weight:600;font-size:12px;text-decoration:none;margin-bottom:7px;line-height:1.4}}
.news-title:hover{{color:var(--acc)}}
.news-summary{{color:var(--text2);font-size:11px;line-height:1.6}}

/* SENTIMENT */
.sentiment-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:18px}}
.sentiment-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:18px}}
.sentiment-card h4{{color:var(--text2);font-size:10px;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:14px}}
.gauge-bar{{width:100%;height:8px;background:var(--bg3);border-radius:4px;overflow:hidden;margin-bottom:4px}}
.gauge-fill{{height:100%;border-radius:4px;transition:width .5s}}
.gauge-labels{{display:flex;justify-content:space-between;font-size:8px;color:var(--text3);margin-bottom:8px}}
.gauge-score{{font-size:34px;font-weight:700;text-align:center;margin:6px 0 3px}}
.gauge-label{{text-align:center;font-size:13px;font-weight:600;margin-bottom:6px}}
.prev-score{{display:block;text-align:center;color:var(--text3);font-size:9px;margin-bottom:4px}}
.fg-note{{text-align:center;color:var(--text3);font-size:9px;font-style:italic;margin-bottom:4px}}
.aaii-bars{{margin:10px 0}}
.aaii-row{{display:flex;align-items:center;gap:7px;margin-bottom:8px}}
.aaii-label{{width:55px;font-size:10px;font-weight:600}}
.aaii-bar-wrap{{flex:1;height:7px;background:var(--bg3);border-radius:4px;overflow:hidden}}
.aaii-bar-fill{{height:100%;border-radius:4px}}
.aaii-bar-fill.positive{{background:var(--pos)}}.aaii-bar-fill.negative{{background:var(--neg)}}.aaii-bar-fill.neutral-c{{background:var(--neu)}}
.aaii-val{{width:42px;text-align:right;font-size:11px;font-weight:600}}
.aaii-label.positive{{color:var(--pos)}}.aaii-label.negative{{color:var(--neg)}}.aaii-label.neutral-c{{color:var(--neu)}}
/* VIX */
.vix-card{{border:1px solid var(--acc2)!important}}
.vix-value{{font-size:40px;font-weight:700;text-align:center;margin:10px 0 4px}}
.vix-label{{text-align:center;font-size:14px;font-weight:600;margin-bottom:4px}}
.vix-change{{text-align:center;font-size:13px;margin-bottom:10px}}
.vix-scale{{display:flex;justify-content:space-between;font-size:9px;border-top:1px solid var(--border);padding-top:8px;margin-top:8px}}

/* ASSETS */
.assets-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px;margin-bottom:18px}}
.asset-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px}}
.asset-card.positive-border{{border-left:3px solid var(--pos)}}
.asset-card.negative-border{{border-left:3px solid var(--neg)}}
.asset-card.neutral-border{{border-left:3px solid var(--neu)}}
.asset-name{{color:var(--text2);font-size:9px;text-transform:uppercase;letter-spacing:1px;margin-bottom:5px}}
.asset-price{{font-size:18px;font-weight:700;margin-bottom:3px}}
.asset-change{{font-size:12px;font-weight:600}}
.change-abs{{color:var(--text3);font-size:10px;margin-left:5px}}
.asset-extra{{margin-top:7px;font-size:10px;color:var(--text3)}}
.asset-extra strong{{color:var(--text2)}}

/* YIELDS */
.yields-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:12px}}
.yield-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:14px;text-align:center}}
.spread-card{{border:1px solid var(--acc2)}}
.yield-cat{{color:var(--acc);font-size:8px;font-weight:700;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}}
.yield-name{{color:var(--text2);font-size:9px;text-transform:uppercase;letter-spacing:1px;margin-bottom:7px}}
.yield-val{{font-size:20px;font-weight:700}}
.yield-change{{color:var(--text3);font-size:10px;margin-top:3px}}
.yield-note{{font-size:11px;font-weight:600;margin-top:3px}}

/* CRYPTO */
.global-banner{{background:var(--bg3);border:1px solid var(--border);border-radius:7px;padding:10px 18px;display:flex;gap:24px;flex-wrap:wrap;font-size:11px;color:var(--text2);margin-bottom:18px}}
.global-banner strong{{color:var(--text)}}
.crypto-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:18px}}
.crypto-card{{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:18px}}
.crypto-card.positive-border{{border-top:3px solid var(--pos)}}
.crypto-card.negative-border{{border-top:3px solid var(--neg)}}
.crypto-card.neutral-border{{border-top:3px solid var(--neu)}}
.crypto-header{{display:flex;align-items:center;gap:10px;margin-bottom:6px}}
.crypto-sym{{font-size:20px;font-weight:700}}
.crypto-rank{{color:var(--text3);font-size:10px}}
.crypto-pct{{font-size:14px;font-weight:700;margin-left:auto}}
.crypto-price{{font-size:28px;font-weight:700;margin-bottom:6px}}
.crypto-sub{{font-size:10px;color:var(--text2);margin-bottom:12px}}
.crypto-sub .sub-label{{color:var(--text3)}}

/* ETF FLOWS */
.etf-block{{background:var(--bg3);border-radius:8px;padding:12px;margin-bottom:10px}}
.etf-title{{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:1px;margin-bottom:7px}}
.etf-flow-main{{font-size:18px;font-weight:700;margin-bottom:4px}}
.etf-date{{font-size:9px;color:var(--text3);margin-left:8px;font-weight:normal}}
.etf-cum{{font-size:10px;color:var(--text3);margin-bottom:8px}}
.etf-row{{display:flex;align-items:center;justify-content:space-between;padding:4px 0;border-top:1px solid var(--border);font-size:11px}}
.etf-sym{{font-weight:700;color:var(--text)}}
.liq-block{{background:#e7433611;border:1px solid #e7433633;border-radius:8px;padding:12px;margin-bottom:8px}}
.liq-placeholder{{font-size:10px;color:var(--text3);padding:8px 0}}
.liq-placeholder a{{color:var(--text3);text-decoration:none}}
.liq-placeholder a:hover{{color:var(--acc)}}
.liq-title{{font-size:9px;color:var(--text3);text-transform:uppercase;letter-spacing:1px;margin-bottom:5px}}
.liq-total{{font-size:14px;font-weight:700;margin-bottom:5px}}
.liq-detail{{display:flex;gap:14px;font-size:10px}}
.fi-block{{background:#4f8ef711;border:1px solid #4f8ef733;border-radius:8px;padding:10px 12px;margin-bottom:8px}}
.fi-row{{display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px}}
.fi-label{{color:var(--text3)}}
.fi-note{{font-size:9px;color:var(--text3);margin-bottom:5px;font-style:italic}}
.etf-links{{margin-top:8px;font-size:9px;color:var(--text3)}}
.etf-links a{{color:var(--acc);text-decoration:none}}.etf-links a:hover{{text-decoration:underline}}

/* OTHER ASSETS (row cards) */
.asset-row-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:14px;display:flex;gap:20px;align-items:flex-start}}
.asset-row-card.positive-border{{border-left:3px solid var(--pos)}}
.asset-row-card.negative-border{{border-left:3px solid var(--neg)}}
.asset-row-card.neutral-border{{border-left:3px solid var(--neu)}}
.arc-left{{min-width:200px}}
.arc-right{{flex:1}}
.arc-name{{color:var(--text2);font-size:9px;text-transform:uppercase;letter-spacing:1px;margin-bottom:4px}}
.arc-price{{font-size:22px;font-weight:700;margin-bottom:3px}}
.arc-change{{font-size:13px;font-weight:600}}
.gold-etf-row{{margin-top:8px;font-size:10px;color:var(--text3)}}
.etf-tag{{background:var(--bg3);border:1px solid var(--border);padding:1px 5px;border-radius:3px;font-size:9px;font-weight:700;color:var(--gold)}}

/* UTILITIES */
.positive{{color:var(--pos)}}.negative{{color:var(--neg)}}.neutral{{color:var(--neu)}}.neutral-c{{color:var(--neu)}}.warning{{color:#f39c12}}
.source-tag{{display:block;color:var(--text3);font-size:8px;margin-top:8px;text-transform:uppercase;letter-spacing:1px}}
.no-data{{color:var(--text3);padding:16px 0;font-style:italic}}

/* CALENDAR DAY HEADERS */
.cal-day-header{{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1.5px;color:var(--acc);padding:14px 0 6px;border-top:1px solid var(--border);margin-top:14px}}
.cal-day-header:first-child{{border-top:none;margin-top:0;padding-top:0}}
.day-today-badge{{background:var(--pos);color:#000;padding:1px 7px;border-radius:10px;font-size:8px;font-weight:700;margin-left:8px;vertical-align:middle}}

/* PUT/CALL RATIO */
.pc-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:16px;margin-bottom:14px}}
.pc-card{{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:16px}}
.pc-header{{font-size:11px;font-weight:700;color:var(--text);margin-bottom:12px;letter-spacing:.5px}}
.pc-row{{display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid var(--border)}}
.pc-row:last-of-type{{border-bottom:none}}
.pc-label{{color:var(--text3);font-size:10px;flex:1}}
.pc-val{{font-size:14px;font-weight:700;min-width:50px;text-align:right}}
.pc-interp{{font-size:9px;color:var(--text2);flex:1;text-align:right}}
.pc-scale{{display:flex;justify-content:space-between;font-size:8px;border-top:1px solid var(--border);padding-top:8px;margin-top:8px}}
.pc-note{{background:var(--bg3);border-radius:6px;padding:10px 14px;font-size:10px;color:var(--text3);line-height:1.6}}
.dvol-chg{{font-size:9px;font-weight:600;color:var(--text3)}}

/* EARNINGS */
.earnings-urgent{{background:#f5a62311;border:1px solid #f5a62344;border-radius:8px;padding:12px 16px;margin-bottom:16px}}
.earning-sym{{background:var(--gold);color:#000;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700;white-space:nowrap}}
.earning-name{{font-size:11px;color:var(--text2)}}
.earning-badge{{background:#e74c3c;color:#fff;padding:1px 6px;border-radius:8px;font-size:8px;font-weight:700;letter-spacing:1px;margin-left:4px;vertical-align:middle}}
.earning-date{{color:var(--acc);font-size:10px}}
.earnings-section-label{{font-size:10px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px;padding-bottom:4px;border-bottom:1px solid var(--border)}}
/* Earnings table */
.etable{{background:var(--card);border:1px solid var(--border);border-radius:8px;overflow:hidden;margin-bottom:6px}}
.etable-header{{display:grid;grid-template-columns:80px 1fr 90px 100px 80px 80px 90px 80px;gap:8px;padding:7px 14px;background:var(--bg3);font-size:8px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:1px}}
.etable-row{{display:grid;grid-template-columns:80px 1fr 90px 100px 80px 80px 90px 80px;gap:8px;padding:9px 14px;border-top:1px solid var(--border);font-size:11px;align-items:center}}
.etable-row:hover{{background:var(--bg3)}}
.etcol-sym{{display:flex;align-items:center;gap:4px}}
.etcol-name{{color:var(--text2);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.etcol-date{{color:var(--acc);font-size:10px}}
.etcol-time{{display:flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:var(--text1)}}
.etcol-eps,.etcol-rev,.etcol-surp{{font-weight:600;font-size:11px}}
.release-badge{{padding:1px 5px;border-radius:3px;font-size:8px;font-weight:700;letter-spacing:.5px;white-space:nowrap}}
.release-pre{{background:#3498db22;color:#3498db;border:1px solid #3498db}}
.release-amc{{background:#9b59b622;color:#a855f7;border:1px solid #9b59b6}}
.release-intra{{background:#2ecc7122;color:#2ecc71;border:1px solid #2ecc71}}

/* SECTOR ROTATION */
.sector-grid{{display:flex;flex-direction:column;gap:7px;margin-bottom:14px}}
.sector-row{{display:flex;align-items:center;gap:10px;padding:6px 0;border-bottom:1px solid var(--border)}}
.sector-row:last-child{{border-bottom:none}}
.sector-header{{opacity:.5;padding-bottom:2px;border-bottom:1px solid var(--border)}}
.sector-name{{width:140px;font-size:11px;color:var(--text2);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
.sector-sym{{width:44px;font-size:9px;font-weight:700;color:var(--text3)}}
.sector-bar-wrap{{flex:1;height:8px;background:var(--bg3);border-radius:4px;overflow:hidden}}
.sector-bar{{height:100%;border-radius:4px;transition:width .4s}}
.sector-pct{{width:62px;text-align:right;font-size:12px;font-weight:700;white-space:nowrap}}
.sector-pct-sec{{width:58px;text-align:right;font-size:11px;font-weight:600;white-space:nowrap;opacity:.85}}
.sector-pct-label{{width:58px;text-align:right;font-size:9px;font-weight:700;color:var(--text3);text-transform:uppercase;letter-spacing:.5px}}
.sector-pct-label:first-of-type{{width:62px}}
.sector-bar.up{{background:var(--pos)}}.sector-bar.down{{background:var(--neg)}}.sector-bar.neutral{{background:var(--neu)}}
.sector-pct{{width:58px;text-align:right;font-size:12px;font-weight:700}}

/* FOOTER */
.footer{{text-align:center;padding:28px;color:var(--text3);font-size:9px;border-top:1px solid var(--border);margin-top:40px}}

/* SCROLLBAR */
::-webkit-scrollbar{{width:5px;height:5px}}::-webkit-scrollbar-track{{background:var(--bg)}}
::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>DAILY <span>MACRO</span> REPORT</h1>
    <div class="header-date">{day_name} — {gen_time}</div>
  </div>
  <div style="text-align:right">
    <div class="live-badge">● UPDATED</div>
    <div class="gen-time">Generated at {now_rome.strftime('%H:%M')}</div>
  </div>
</div>

<div class="container">

<div class="section">
  <div class="section-header">
    <span class="section-icon">📅</span>
    <span class="section-title">Economic Calendar</span>
    <span class="section-sub">HIGH IMPACT only — Rome time (GMT+2) — Forex Factory</span>
  </div>
  <div class="section-body">{cal_html}</div>
</div>

{f'''<div class="section">
  <div class="section-header">
    <span class="section-icon">📊</span>
    <span class="section-title">Earnings — Key Companies</span>
    <span class="section-sub">Reports today + next 7 days</span>
  </div>
  <div class="section-body">{earnings_html}</div>
</div>''' if earnings_html else ""}

<div class="section">
  <div class="section-header">
    <span class="section-icon">📰</span>
    <span class="section-title">Breaking News — Last 24h</span>
    <span class="section-sub">Bloomberg · CNBC · FT · BBC · Guardian · Al Jazeera · MarketWatch</span>
  </div>
  <div class="section-body">{news_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">🏦</span>
    <span class="section-title">Central Banks</span>
    <span class="section-sub">Fed · ECB · BoJ · BoC · RBA · BoE · SNB · PBOC — Last 48h</span>
  </div>
  <div class="section-body">{cb_news_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">🧠</span>
    <span class="section-title">Sentiment & Momentum</span>
    <span class="section-sub">Fear & Greed · AAII · VIX</span>
  </div>
  <div class="section-body">{sentiment_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">₿</span>
    <span class="section-title">Crypto — BTC · ETH · SOL</span>
    <span class="section-sub">CoinGecko · farside.co.uk (ETF flows) · Coinalyze (funding/OI/liq)</span>
  </div>
  <div class="section-body">{crypto_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">💧</span>
    <span class="section-title">Stablecoin Liquidity</span>
    <span class="section-sub">Dry powder proxy — DefiLlama</span>
  </div>
  <div class="section-body">{stablecoin_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">⚖️</span>
    <span class="section-title">Deribit Put/Call Ratio — BTC · ETH</span>
    <span class="section-sub">Volume 24h + Open Interest — Deribit (public API)</span>
  </div>
  <div class="section-body">{pc_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">📈</span>
    <span class="section-title">US Markets & Treasury Yields</span>
    <span class="section-sub">Yahoo Finance · FRED (Federal Reserve)</span>
  </div>
  <div class="section-body">{indices_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">🌏</span>
    <span class="section-title">Asian Session</span>
    <span class="section-sub">Nikkei · Hang Seng · Shanghai · CSI 300 · ASX 200 · KOSPI — Yahoo Finance</span>
  </div>
  <div class="section-body">{asia_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">🪙</span>
    <span class="section-title">Other Assets — DXY · Gold · Silver · Copper · Oil</span>
    <span class="section-sub">Yahoo Finance · WGC</span>
  </div>
  <div class="section-body">{assets_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">🛢️</span>
    <span class="section-title">Oil & Energy — News Last 24h</span>
    <span class="section-sub">WTI · Brent · OPEC · Energy Geopolitics</span>
  </div>
  <div class="section-body">{oil_news_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">🔄</span>
    <span class="section-title">Sector Rotation — S&P 500</span>
    <span class="section-sub">XLK · XLF · XLE · XLV · XLU · XLI · XLP · XLY · XLB · XLRE — Yahoo Finance</span>
  </div>
  <div class="section-body">{sector_html}</div>
</div>

<div class="section">
  <div class="section-header">
    <span class="section-icon">🤖</span>
    <span class="section-title">AI & Robotics — Last 24h</span>
    <span class="section-sub">Bloomberg Tech · CNBC Tech · BBC Tech · Guardian Tech</span>
  </div>
  <div class="section-body">{ai_html}</div>
</div>

</div>

<div class="footer">
  Daily Macro Report — {gen_time} &nbsp;|&nbsp;
  Bloomberg · CNBC · FT · BBC · Guardian · Al Jazeera · CoinGecko · FRED · alternative.me · farside.co.uk · CoinGlass · Forex Factory
</div>
</body>
</html>"""
