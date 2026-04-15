# =============================================================================
# DAILY MACRO REPORT — CONFIGURATION
# =============================================================================
# Inserisci qui le tue API key prima di lanciare lo script.
# Le key gratuite sono sufficienti per uso giornaliero personale.
# =============================================================================

# --- NEWS API ---
# Registrati gratis su https://newsapi.org → "Get API Key"
# Piano free: 100 richieste/giorno (più che sufficienti)
NEWSAPI_KEY = "YOUR_NEWSAPI_KEY_HERE"

# --- FRED API (Federal Reserve) ---
# Registrati gratis su https://fred.stlouisfed.org/docs/api/api_key.html
# Completamente gratuito, nessun limite pratico
FRED_API_KEY = "YOUR_FRED_API_KEY_HERE"

# --- COINMARKETCAP API (per F&G Index) ---
# Registrati gratis su https://pro.coinmarketcap.com/account → piano Basic (gratuito)
# Usata per il CMC Fear & Greed Index (diverso da alternative.me)
# Se non configurata: viene mostrato solo alternative.me F&G
CMC_API_KEY = "00745888af784577bfda8bf40cb81863"

# --- COINGLASS API ---
# Registrati gratis su https://coinglass.com/pricing → piano Free
# Fornisce dati liquidazioni BTC/ETH/SOL e open interest
COINGLASS_API_KEY = "YOUR_COINGLASS_API_KEY_HERE"

# =============================================================================
# IMPOSTAZIONI REPORT
# =============================================================================

# Orario: Roma (GMT+2 in estate / CET+1 in inverno — gestito automaticamente)
TIMEZONE = "Europe/Rome"

# Quante ore indietro guardare per le news (default: 24h)
NEWS_HOURS_BACK = 24

# Numero massimo di notizie per sezione
MAX_NEWS_GENERAL = 12
MAX_NEWS_CENTRAL_BANKS = 8
MAX_NEWS_AI = 8

# Asset da monitorare
CRYPTO_ASSETS = {
    "BTC": "bitcoin",      # CoinGecko ID
    "ETH": "ethereum",
    "SOL": "solana",
}

US_INDICES = {
    "S&P 500": "^GSPC",
    "Dow Jones": "^DJI",
    "Nasdaq": "^IXIC",
    "VIX": "^VIX",
}

FUTURES = {
    "S&P 500 Futures": "ES=F",
    "Nasdaq Futures": "NQ=F",
    "Dow Futures": "YM=F",
}

OTHER_ASSETS = {
    "DXY (Dollar Index)": "DX-Y.NYB",
    "Gold": "GC=F",
    "Silver": "SI=F",
    "Copper": "HG=F",
    "WTI Crude Oil": "CL=F",
    "Brent Crude Oil": "BZ=F",
}

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLF": "Financials",
    "XLE": "Energy",
    "XLV": "Healthcare",
    "XLU": "Utilities",
    "XLI": "Industrials",
    "XLP": "Consumer Staples",
    "XLY": "Consumer Discret.",
    "XLB": "Materials",
    "XLRE": "Real Estate",
}

# Oil news keywords
OIL_KEYWORDS = [
    "oil", "crude", "brent", "wti", "opec", "opec+", "petroleum",
    "barrel", "energy", "gasoline", "refinery", "saudi", "aramco",
    "natural gas", "lng", "pipeline", "shale", "iran sanctions",
    "russia oil", "energy crisis", "oil supply", "oil demand",
]

GOLD_ETFS = {
    "GLD (SPDR Gold)": "GLD",
    "IAU (iShares Gold)": "IAU",
}

# FRED Series IDs per i Treasury yield
TREASURY_SERIES = {
    "2Y Yield": "DGS2",
    "10Y Yield": "DGS10",
    "30Y Yield": "DGS30",
}

# =============================================================================
# FONTI RSS — Suddivise per categoria
# =============================================================================

# ── NOTIZIE FINANZIARIE / MACRO ──
RSS_FEEDS_FINANCE = {
    "Bloomberg - Markets":    "https://feeds.bloomberg.com/markets/news.rss",
    "Bloomberg - Economics":  "https://feeds.bloomberg.com/economics/news.rss",
    "Bloomberg - Politics":   "https://feeds.bloomberg.com/politics/news.rss",
    "CNBC - Markets":         "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "CNBC - Finance":         "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069",
    "FT - Home":              "https://www.ft.com/rss/home/uk",
    "MarketWatch":            "https://feeds.content.dowjones.io/public/rss/mw_bulletins",
    "Seeking Alpha - Macro":  "https://seekingalpha.com/sector/macro-view.xml",
    "Investing.com":          "https://www.investing.com/rss/news_25.rss",
}

# ── NOTIZIE MONDO / GEOPOLITICA / ATTUALITÀ ──
RSS_FEEDS_WORLD = {
    "BBC - World":            "http://feeds.bbci.co.uk/news/world/rss.xml",
    "BBC - Business":         "http://feeds.bbci.co.uk/news/business/rss.xml",
    "The Guardian - World":   "https://www.theguardian.com/world/rss",
    "The Guardian - Economy": "https://www.theguardian.com/business/economics/rss",
    "Al Jazeera":             "https://www.aljazeera.com/xml/rss/all.xml",
    "CNBC - World":           "https://www.cnbc.com/id/100003114/device/rss/rss.html",
}

# Compatibilità: RSS_FEEDS usato in altri moduli = unione finance + world
RSS_FEEDS = {**RSS_FEEDS_FINANCE, **RSS_FEEDS_WORLD}

# ── BANCHE CENTRALI ──
RSS_FEEDS_CENTRAL_BANKS = {
    "Federal Reserve":        "https://www.federalreserve.gov/feeds/press_all.xml",
    "ECB":                    "https://www.ecb.europa.eu/rss/press.html",
    "BIS":                    "https://www.bis.org/rss/presrel.rss",
    "Bloomberg - Economics":  "https://feeds.bloomberg.com/economics/news.rss",
    "CNBC - Economy":         "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910274",
}

# ── AI & ROBOTICA ──
RSS_FEEDS_AI = {
    "Bloomberg - Technology": "https://feeds.bloomberg.com/technology/news.rss",
    "CNBC - Technology":      "https://www.cnbc.com/id/19854910/device/rss/rss.html",
    "BBC - Technology":       "http://feeds.bbci.co.uk/news/technology/rss.xml",
    "The Guardian - Tech":    "https://www.theguardian.com/technology/rss",
    "Seeking Alpha - Tech":   "https://seekingalpha.com/sector/technology.xml",
}

# Massimo articoli per singola fonte (evita monopolio di una sola fonte)
MAX_ARTICLES_PER_SOURCE = 2

# =============================================================================
# CALENDARIO — WHITELIST EVENTI
# Questi eventi vengono inclusi SEMPRE nel calendario indipendentemente
# dall'impatto assegnato da Forex Factory (Low/Medium/High).
# Aggiungere qui i titoli esatti (o parte di essi) come compaiono su FF.
# Il confronto è case-insensitive e per sottostringa.
# =============================================================================
CALENDAR_WHITELIST = [
    "Final Services PMI",      # S&P Global Services PMI (US) — Forex Factory lo chiama così
    "Crude Oil Inventories",   # EIA Weekly Crude Oil Inventories
    "10-y Bond Auction",       # 10-Year Note Auction (USD)
    "30-y Bond Auction",       # 30-Year Bond Auction (USD) — aggiunto 08/04/2026
    "German Final CPI",        # German Final CPI m/m (EUR) — aggiunto 08/04/2026
    "Existing Home Sales",     # USD — aggiunto 13/04/2026
]
