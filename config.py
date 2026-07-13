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
CMC_API_KEY = "YOUR_CMC_API_KEY_HERE"

# --- COINGLASS API ---
# Registrati gratis su https://coinglass.com/pricing → piano Free
# Fornisce dati liquidazioni BTC/ETH/SOL e open interest
COINGLASS_API_KEY = "YOUR_COINGLASS_API_KEY_HERE"

# --- COINALYZE API (derivati crypto aggregati) ---
# Registrati gratis su https://coinalyze.net → genera API key (free tier, 40 req/min)
# Sostituto di CoinGlass: funding rate, open interest, liquidazioni 24h aggregati multi-exchange
COINALYZE_API_KEY = "YOUR_COINALYZE_API_KEY_HERE"

# --- FINNHUB API (fallback per yfinance su indici/commodities, gratis) ---
# Registrati gratis su https://finnhub.io (no carta, 60 req/min). Endpoint /quote (c=corrente,
# pc=chiusura prec). Scatta SOLO quando yfinance fallisce; usa ETF proxy (SPY/GLD/USO...).
FINNHUB_API_KEY = "YOUR_FINNHUB_API_KEY_HERE"

# --- GOOGLE GEMINI API (sintesi 'so what' delle news, gratis) ---
# Key gratuita da https://aistudio.google.com (free tier, ~1500 req/giorno, no carta).
# Usata per generare 2 righe di sintesi in cima alle sezioni news. Fallback: nessuna sintesi.
GEMINI_API_KEY = "YOUR_GEMINI_API_KEY_HERE"
GEMINI_MODEL   = "gemini-3.5-flash"   # il modello free PIÙ capace con budget sulla key (i 3.x/2.5 -pro hanno RPD 0). Con chiamata singola (1/run) sta nei limiti.
# Catena di fallback modello (per RESILIENZA): se il primario dà 503/5xx (sovraccarico
# Google) o 429 (quota di QUEL modello), _gemini_generate passa al successivo. Ognuno ha
# quota separata. Ordine = capacità → disponibilità. L'ultimo (flash-lite) ha 500 RPD/gg
# → backstop quasi sempre up. Id verificati via ListModels API (09/07/2026).
GEMINI_MODEL_FALLBACKS = ["gemini-2.5-flash", "gemini-3.1-flash-lite"]

# =============================================================================
# CHIAVI PRIVATE — caricate da config_local.py (git-ignored, NON su GitHub).
# I segnaposto qui sopra vengono sovrascritti dai valori reali. Su un clone senza
# config_local.py il report parte comunque (con i segnaposto → fallback puliti).
# Setup: cp config_local.example.py config_local.py  e inserisci le tue chiavi.
# =============================================================================
try:
    from config_local import *   # noqa: F401,F403
except ImportError:
    pass

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
MAX_NEWS_AI = 6
MAX_NEWS_CRYPTO = 8

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

# FX majors (Yahoo Finance primario, Frankfurter fallback keyless)
FX_PAIRS = {
    "USD/JPY": "USDJPY=X",   # il più rilevante: carry trade ↔ risk crypto
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/CNY": "USDCNY=X",
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

# FRED Series IDs per i Treasury yield — curva completa
TREASURY_SERIES = {
    "3M Yield":  "DGS3MO",
    "2Y Yield":  "DGS2",
    "5Y Yield":  "DGS5",
    "10Y Yield": "DGS10",
    "30Y Yield": "DGS30",
}

# Curve signals: 2s10s e 3m10y sono calcolati in market_data come differenza dei yield
# della curva già mostrati (DGS10-DGS2, DGS10-DGS3MO) per consistenza aritmetica —
# NON da serie FRED separate (T10Y2Y/T10Y3M) che hanno timing diverso.

# Real yield & breakeven inflation (TIPS) — crescita vs inflazione
FRED_INFLATION = {
    "10Y Real Yield": "DFII10",
    "10Y Breakeven":  "T10YIE",
}

# Credit spreads (OAS) — mostrati come percentile vs storia
FRED_CREDIT = {
    "HY OAS": "BAMLH0A0HYM2",
    "IG OAS": "BAMLC0A0CM",
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
    "Bank of England":        "https://www.bankofengland.co.uk/rss/news",   # verificato 08/07: 200, 50 art
    "Bank of Japan":          "https://www.boj.or.jp/en/rss/whatsnew.xml",  # verificato 08/07: 200, 48 art
    "Bloomberg - Economics":  "https://feeds.bloomberg.com/economics/news.rss",
    # BIS rimosso (08/07): tutti gli URL RSS testati davano 404 o 0 articoli. CNBC Economy
    # rimosso (0 art). Fed/ECB/BoE/BoJ + Bloomberg = copertura banche centrali sufficiente.
}

# ── CRYPTO-NATIVE (verificate dal vivo 07/07/2026) ──
# The Block = summary ricchi; CoinDesk/Decrypt = affidabili. DL News SCARTATA (sta chiudendo),
# Cointelegraph scartata (irraggiungibile in test).
RSS_FEEDS_CRYPTO = {
    "The Block":  "https://www.theblock.co/rss.xml",
    "CoinDesk":   "https://www.coindesk.com/arc/outboundfeeds/rss/?outputType=xml",
    "Decrypt":    "https://decrypt.co/feed",
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
    "Final Services PMI",      # S&P Global Services PMI (US)
    "10-y Bond Auction",       # 10-Year Note Auction (USD)
    "30-y Bond Auction",       # 30-Year Bond Auction (USD)
    "German Final CPI",        # German Final CPI m/m (EUR)
    "Existing Home Sales",     # USD
    "Manufacturing PMI",       # CNY
    "Chicago PMI",             # USD
    "Final CPI y/y",           # EUR Eurozone Final CPI y/y
    "Final Core CPI y/y",      # EUR Eurozone Final Core CPI y/y
    "German Final GDP",        # EUR German Final GDP q/q
    "New Home Sales",          # USD
    "Crude Oil Inventories",   # EIA Weekly — Low on FF, kept via whitelist
    "Durable Goods Orders",    # USD — Low on FF, kept via whitelist
    "Final GDP q/q",           # GBP — Low on FF, kept via whitelist
    "GDP q/y",                 # CNY China GDP — Low on FF, kept via whitelist
]

# =============================================================================
# CALENDARIO — BLACKLIST EVENTI
# Questi eventi vengono SEMPRE esclusi dal calendario, qualunque sia il loro impatto.
# Confronto case-insensitive per sottostringa sul titolo FF.
# =============================================================================
CALENDAR_BLACKLIST = [
    "French Flash Manufacturing PMI",
    "French Flash Services PMI",
    "Trimmed Mean CPI",
    "German 10-y Bond Auction",
    "Final GDP Price Index",
    "Core Durable Goods Orders",
    "Macklem Speaks",                  # BOC Gov speeches — not requested
    "Italian 10-y Bond Auction",       # aste italiane non rilevanti
    "Revised UoM Consumer Sentiment",  # revisione secondaria
    "Revised UoM Inflation Expectations", # revisione secondaria
    "Spanish Manufacturing PMI",
    "Italian Manufacturing PMI",
    "French Final Manufacturing PMI",
    "German Final Manufacturing PMI",
    "BOE Gov Bailey Speaks",
    "Spanish 10-y Bond Auction",
    "French 10-y Bond Auction",
    "German Final Services PMI",
    "French Final Services PMI",
    "German 30-y Bond Auction",        # EUR — escluso (whitelist "30-y Bond Auction" lo catturava)
    "BOC Monetary Policy Report",      # CAD — non richiesto (la decisione "Overnight Rate" resta)
    "BOC Rate Statement",              # CAD — non richiesto
    "BOC Press Conference",            # CAD — non richiesto
]

# =============================================================================
# CALENDARIO — BLACKLIST EVENTI CON VALUTA
# Stessa logica di CALENDAR_BLACKLIST ma filtra anche per valuta.
# Formato: ("sottostringa_titolo", "VALUTA") — entrambi obbligatori.
# Usato per escludere eventi con stesso titolo FF ma valuta diversa (es. 10-y Bond Auction JPY/GBP).
# =============================================================================
CALENDAR_BLACKLIST_CURRENCY = [
    ("10-y Bond Auction", "JPY"),   # Japan bond auction
    ("10-y Bond Auction", "GBP"),   # UK gilt auction
    ("30-y Bond Auction", "JPY"),   # Japan 30y bond auction (USD 30y resta visibile)
    ("Employment Change", "CAD"),   # Canada jobs — rimosso (USD/AUD restano)
    ("Unemployment Rate", "CAD"),   # Canada — rimosso (USD/AUD restano)
]

# =============================================================================
# CALENDARIO — OVERRIDE IMPATTO AD ALTO
# Formato: ("sottostringa_titolo", "VALUTA_o_None")
# None = qualsiasi valuta. Altrimenti solo per quella valuta.
# =============================================================================
CALENDAR_IMPACT_HIGH = [
    ("Flash Manufacturing PMI", "USD"),   # solo US Flash PMI
    ("Flash Services PMI",      "USD"),   # solo US Flash Services PMI
    ("Trump Speaks",            None),    # discorsi del presidente
    ("President Speaks",        None),    # generico
    ("Crude Oil Inventories",   "USD"),   # EIA settimanale
    ("New Home Sales",          "USD"),   # USD
    ("Durable Goods Orders",    "USD"),   # USD (Core già in blacklist)
    ("Unemployment Claims",      "USD"),   # FF title → renamed to Initial Jobless Claims
    ("Manufacturing PMI",        "CNY"),   # copre anche Non-Manufacturing PMI (CNY)
    ("German Prelim CPI m/m",    "EUR"),
    ("Chicago PMI",               "USD"),
    ("CB Consumer Confidence",    "USD"),
    ("JOLTS Job Openings",        "USD"),
    ("Final GDP q/q",             "GBP"),
    ("CPI Flash Estimate y/y",    "EUR"),   # copre anche Core CPI Flash Estimate y/y (EUR)
    ("ADP Non-Farm Employment Change", "USD"),
    ("ISM Manufacturing Prices",  "USD"),
    ("Final Services PMI",        "USD"),   # US Final Services PMI → alto
    ("10-y Bond Auction",         "USD"),   # 10-Year Note Auction USD → alto
    ("30-y Bond Auction",         "USD"),   # 30-Year Bond Auction USD → alto (JPY resta escluso da blacklist)
    ("Existing Home Sales",       "USD"),   # USD → alto
    ("German Final CPI",          "EUR"),   # German Final CPI m/m → alto
    ("GDP q/y",                   "CNY"),   # China GDP → alto
]

# =============================================================================
# CALENDARIO — OVERRIDE IMPATTO A MEDIO
# Formato: ("sottostringa_titolo", "VALUTA_o_None")
# Abbassa a MED eventi che FF classifica High ma che sono meno rilevanti.
# =============================================================================
CALENDAR_IMPACT_MED = [
    ("CPI",                 "AUD"),   # AUD CPI → medio
    ("Employment Change",   "AUD"),   # AUD Employment → medio
    ("Unemployment Rate",   "AUD"),   # AUD Unemployment → medio
    ("GDP m/m",                    "CAD"),
    ("Manufacturing PMI",          "CAD"),   # CAD Manufacturing PMI → medio
    ("Final Manufacturing PMI",    "JPY"),
    ("RatingDog Manufacturing PMI","CNY"),
    ("Manufacturing PMI",          "CHF"),
    ("Final Manufacturing PMI",    "EUR"),
    ("Final Manufacturing PMI",    "GBP"),
    ("Final Manufacturing PMI",    "USD"),
    ("Final Services PMI",         "EUR"),   # Eurozone Final Services PMI → medio
    ("Final Services PMI",         "GBP"),   # UK Final Services PMI → medio
]

# =============================================================================
# RATE EXPECTATIONS — Atlanta Fed Market Probability Tracker (primaria) + ZQ (fallback)
# MPT = distribuzione probabilità del SOFR medio 3M implicita nelle opzioni CME,
# calcolata dalla Fed di Atlanta. File storico xlsx ufficiale, aggiornato ~giornalmente.
# =============================================================================
ATLANTA_FED_MPT_URL = "https://www.atlantafed.org/-/media/Project/Atlanta/FRBA/Documents/cenfis/market-probability-tracker/mpt_histdata.xlsx"
