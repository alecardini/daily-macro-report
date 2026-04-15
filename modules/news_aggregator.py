"""
News Aggregator + Analyzer Module

Fonti finanziarie/macro: Bloomberg, CNBC, FT, MarketWatch, Seeking Alpha, Investing.com
Fonti mondo/geopolitica: BBC, The Guardian, Al Jazeera
Banche centrali: Fed RSS, ECB RSS, BIS RSS + filtro da Bloomberg/CNBC
AI & Robotica: Bloomberg Tech, CNBC Tech, BBC Tech, Guardian Tech

Per le fonti con testo libero (CNBC, BBC, Guardian, Al Jazeera):
→ scarica il testo completo dell'articolo e ne estrae i punti chiave

Per fonti con paywall (Bloomberg, FT):
→ usa titolo + sommario dell'RSS

Diversità forzata: max MAX_ARTICLES_PER_SOURCE articoli per fonte.
"""

import requests
import feedparser
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import time
import re
from collections import defaultdict


# ── Keywords macro-rilevanti per filtrare notizie generiche ──
MACRO_KEYWORDS = [
    "federal reserve", "fed ", "fomc", "powell", "interest rate", "rate hike",
    "rate cut", "monetary policy", "ecb", "lagarde", "bank of japan", "boj",
    "bank of england", "boe", "bank of canada", "rba", "snb", "pboc",
    "central bank", "inflation", "cpi", "pce", "ppi", "gdp", "recession",
    "s&p 500", "nasdaq", "dow jones", "stocks", "equity", "bond", "yield",
    "treasury", "dollar", "dxy", "gold", "oil", "commodity", "crypto",
    "bitcoin", "btc", "ethereum", "earnings", "jobs report", "nonfarm",
    "unemployment", "tariff", "trade war", "sanctions", "debt",
    "ukraine", "russia", "china", "taiwan", "middle east", "iran", "israel",
    "opec", "g7", "g20", "imf", "world bank", "trump", "war", "geopolit",
    "election", "government", "congress", "senate", "military", "nato",
    "energy", "oil", "gas", "supply chain", "bank", "finance", "market",
]

CENTRAL_BANK_KEYWORDS = [
    "federal reserve", "fed ", "fomc", "powell", "ecb", "lagarde",
    "bank of japan", "boj", "ueda", "bank of england", "boe", "bailey",
    "bank of canada", "boc", "rba", "reserve bank", "snb", "pboc",
    "people's bank", "central bank", "rate decision", "monetary policy",
    "rate hike", "rate cut", "quantitative", "qe", "qt", "interest rate",
    "inflation target", "yield curve control", "forward guidance",
]

AI_KEYWORDS = [
    "artificial intelligence", " ai ", "machine learning", "deep learning",
    "openai", "chatgpt", "gpt", "anthropic", "claude", "gemini", "llm",
    "large language model", "nvidia", "robotics", "robot", "automation",
    "autonomous", "tesla bot", "humanoid", "boston dynamics", "waymo",
    "self-driving", "semiconductor", "chips", "jensen huang", "sam altman",
    "ai regulation", "deepseek", "xai", "grok", "meta ai", "llama",
]


def is_recent(pub_parsed, hours_back=24):
    """Check if feedparser time struct is within last N hours."""
    if not pub_parsed:
        return True
    try:
        pub_dt = datetime(*pub_parsed[:6], tzinfo=timezone.utc)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        return pub_dt >= cutoff
    except Exception:
        return True


def contains_keywords(text, keywords):
    text_lower = text.lower()
    return any(kw.lower() in text_lower for kw in keywords)


def fetch_full_article_text(url):
    """
    Fetch and extract article text from free sources (CNBC, BBC, Guardian, Al Jazeera).
    Returns up to 2500 chars of cleaned article text.
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "form", "iframe", "noscript"]):
            tag.decompose()

        paragraphs = []

        if "cnbc.com" in url:
            paragraphs = soup.select(".ArticleBody-articleBody p, .article-body p")
        elif "bbc." in url:
            paragraphs = soup.select('[data-component="text-block"] p, article p, .story-body p')
        elif "theguardian.com" in url:
            paragraphs = soup.select('.article-body-commercial-selector p, .dcr-p p, article p')
        elif "aljazeera.com" in url:
            paragraphs = soup.select('.article-p-wrapper p, .wysiwyg p')
        elif "marketwatch.com" in url:
            paragraphs = soup.select('.article__body p')

        if not paragraphs:
            paragraphs = soup.select("article p") or soup.select("p")

        text = " ".join(p.get_text(strip=True) for p in paragraphs[:20])
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:2500]

    except Exception:
        return ""


def extract_key_points(title, summary, full_text=""):
    """
    Extract 2-3 macro-relevant key sentences from article content.
    """
    content = full_text if len(full_text) > 100 else summary or ""
    if not content:
        return summary or title

    sentences = re.split(r'(?<=[.!?])\s+', content)
    scored = []

    for i, sent in enumerate(sentences[:25]):
        sent = sent.strip()
        if len(sent) < 40:
            continue
        score = max(0, 6 - i)  # Prefer early sentences
        sent_lower = sent.lower()
        for kw in MACRO_KEYWORDS:
            if kw in sent_lower:
                score += 2
        if re.search(r'\d+\.?\d*%', sent):
            score += 3
        if re.search(r'\$[\d,]+', sent):
            score += 2
        scored.append((score, i, sent))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top = sorted(scored[:3], key=lambda x: x[1])
    result = " ".join(s[2] for s in top)
    return result[:450].strip() if result else (summary or title)[:450]


# Whether to fetch full text for this source
FULL_TEXT_SOURCES = {"cnbc", "bbc", "theguardian", "aljazeera"}

def should_fetch_full(url):
    return any(s in url for s in FULL_TEXT_SOURCES)


def fetch_rss_feed(name, url, filter_keywords=None, hours_back=24):
    """Parse an RSS feed and return list of article dicts."""
    articles = []
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        resp = requests.get(url, headers=headers, timeout=12)
        if resp.status_code != 200:
            return []

        feed = feedparser.parse(resp.text)

        for entry in feed.entries[:25]:
            title = entry.get("title", "")
            summary = BeautifulSoup(entry.get("summary", "") or entry.get("description", ""), "html.parser").get_text(strip=True)
            link = entry.get("link", "")
            pub_date = entry.get("published_parsed")

            if not is_recent(pub_date, hours_back):
                continue

            if filter_keywords:
                combined = f"{title} {summary}"
                if not contains_keywords(combined, filter_keywords):
                    continue

            full_text = ""
            if link and should_fetch_full(link):
                full_text = fetch_full_article_text(link)
                time.sleep(0.2)

            summary_out = extract_key_points(title, summary, full_text)

            articles.append({
                "title": title,
                "summary": summary_out,
                "url": link,
                "source": name,
                "has_full_text": bool(full_text),
                "pub_date": pub_date,
            })

    except Exception as e:
        print(f"[News] RSS error for {name}: {e}")
    return articles


def fetch_newsapi(category="macro", hours_back=24):
    """Fetch from NewsAPI.org (Bloomberg, WSJ, NYT, FT, Economist, CNN)."""
    if not config.NEWSAPI_KEY or config.NEWSAPI_KEY == "YOUR_NEWSAPI_KEY_HERE":
        return []
    articles = []
    try:
        from_time = (datetime.now(timezone.utc) - timedelta(hours=hours_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
        queries = {
            "macro": "economy OR inflation OR recession OR \"Federal Reserve\" OR \"interest rate\" OR tariff OR GDP",
            "central_banks": "\"Federal Reserve\" OR ECB OR \"Bank of Japan\" OR \"Bank of England\" OR \"central bank\" OR \"rate decision\"",
            "ai": "\"artificial intelligence\" OR \"OpenAI\" OR Nvidia OR robotics OR \"machine learning\"",
        }
        resp = requests.get(
            "https://newsapi.org/v2/everything",
            params={
                "q": queries.get(category, queries["macro"]),
                "from": from_time,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": 20,
                "apiKey": config.NEWSAPI_KEY,
            },
            timeout=15,
        )
        resp.raise_for_status()
        for art in resp.json().get("articles", []):
            source_name = art.get("source", {}).get("name", "NewsAPI")
            title = art.get("title", "") or ""
            if "[Removed]" in title or not title:
                continue
            summary = extract_key_points(title, art.get("description", "") or "", art.get("content", "") or "")
            articles.append({
                "title": title,
                "summary": summary,
                "url": art.get("url", ""),
                "source": source_name,
                "has_full_text": False,
            })
    except Exception as e:
        print(f"[News] NewsAPI error: {e}")
    return articles


def deduplicate_with_source_limit(articles, max_total=14, max_per_source=None):
    """
    Deduplicate articles and enforce per-source limit.
    Interleaves sources so the final list has diversity.
    """
    if max_per_source is None:
        max_per_source = getattr(config, 'MAX_ARTICLES_PER_SOURCE', 2)

    # Group by source
    by_source = defaultdict(list)
    seen_titles = []

    for art in articles:
        title_words = set(art["title"].lower().split())
        is_dup = False
        for seen in seen_titles:
            seen_words = set(seen.lower().split())
            overlap = len(title_words & seen_words) / max(len(title_words), 1)
            if overlap > 0.55:
                is_dup = True
                break
        if not is_dup:
            by_source[art["source"]].append(art)
            seen_titles.append(art["title"])

    # Round-robin interleaving with per-source cap
    result = []
    sources = list(by_source.keys())
    source_count = defaultdict(int)
    round_idx = 0

    while len(result) < max_total:
        added_any = False
        for src in sources:
            pool = by_source[src]
            if source_count[src] < max_per_source and source_count[src] < len(pool):
                result.append(pool[source_count[src]])
                source_count[src] += 1
                added_any = True
                if len(result) >= max_total:
                    break
        if not added_any:
            break
        round_idx += 1

    return result


# ────────────────────────────────────────────────────────────────────
# SEZIONE 1: Breaking News Generali (Finanza + Geopolitica + Attualità)
# ────────────────────────────────────────────────────────────────────

def get_general_news():
    """
    Breaking news ultime 24h — finanza, macro, geopolitica, attualità mondiale.
    Fonti: Bloomberg, CNBC, FT, BBC, Guardian, Al Jazeera, MarketWatch.
    """
    print("[News] Fetching general news (finance + world + geopolitics)...")
    all_articles = []

    # Fonti finanziarie/macro
    finance_feeds = [
        ("Bloomberg - Markets",    config.RSS_FEEDS_FINANCE.get("Bloomberg - Markets", "")),
        ("Bloomberg - Economics",  config.RSS_FEEDS_FINANCE.get("Bloomberg - Economics", "")),
        ("Bloomberg - Politics",   config.RSS_FEEDS_FINANCE.get("Bloomberg - Politics", "")),
        ("CNBC - Markets",         config.RSS_FEEDS_FINANCE.get("CNBC - Markets", "")),
        ("FT - Home",              config.RSS_FEEDS_FINANCE.get("FT - Home", "")),
        ("MarketWatch",            config.RSS_FEEDS_FINANCE.get("MarketWatch", "")),
        ("Seeking Alpha - Macro",  config.RSS_FEEDS_FINANCE.get("Seeking Alpha - Macro", "")),
        ("Investing.com",          config.RSS_FEEDS_FINANCE.get("Investing.com", "")),
    ]

    # Fonti mondo/geopolitica (no filtro keywords — tutto è rilevante da queste fonti)
    world_feeds = [
        ("BBC - World",            config.RSS_FEEDS_WORLD.get("BBC - World", "")),
        ("BBC - Business",         config.RSS_FEEDS_WORLD.get("BBC - Business", "")),
        ("The Guardian - World",   config.RSS_FEEDS_WORLD.get("The Guardian - World", "")),
        ("The Guardian - Economy", config.RSS_FEEDS_WORLD.get("The Guardian - Economy", "")),
        ("Al Jazeera",             config.RSS_FEEDS_WORLD.get("Al Jazeera", "")),
        ("CNBC - World",           config.RSS_FEEDS_WORLD.get("CNBC - World", "")),
    ]

    for name, url in finance_feeds:
        if not url:
            continue
        arts = fetch_rss_feed(name, url, filter_keywords=MACRO_KEYWORDS, hours_back=config.NEWS_HOURS_BACK)
        all_articles.extend(arts)
        print(f"  {name}: {len(arts)} articoli")

    for name, url in world_feeds:
        if not url:
            continue
        arts = fetch_rss_feed(name, url, filter_keywords=None, hours_back=config.NEWS_HOURS_BACK)
        all_articles.extend(arts)
        print(f"  {name}: {len(arts)} articoli")

    # NewsAPI per paywalled sources
    newsapi_arts = fetch_newsapi(category="macro")
    all_articles.extend(newsapi_arts)
    if newsapi_arts:
        print(f"  NewsAPI: {len(newsapi_arts)} articoli")

    result = deduplicate_with_source_limit(all_articles, max_total=config.MAX_NEWS_GENERAL, max_per_source=2)
    print(f"[News] Breaking news totali: {len(result)} da {len(set(a['source'] for a in result))} fonti")
    return result


# ────────────────────────────────────────────────────────────────────
# SEZIONE 2: Banche Centrali
# ────────────────────────────────────────────────────────────────────

def get_central_bank_news():
    """News banche centrali: Fed, ECB, BoJ, BoE, BoC, RBA, SNB, PBOC."""
    print("[News] Fetching central bank news...")
    all_articles = []

    # Feed ufficiali (tutto rilevante, no filtro)
    official_feeds = [
        ("Federal Reserve",       config.RSS_FEEDS_CENTRAL_BANKS.get("Federal Reserve", "")),
        ("ECB",                   config.RSS_FEEDS_CENTRAL_BANKS.get("ECB", "")),
        ("BIS",                   config.RSS_FEEDS_CENTRAL_BANKS.get("BIS", "")),
    ]
    for name, url in official_feeds:
        if not url:
            continue
        arts = fetch_rss_feed(name, url, filter_keywords=None, hours_back=72)
        all_articles.extend(arts)
        print(f"  {name}: {len(arts)} articoli")

    # Bloomberg + CNBC filtrati per CB keywords
    filtered_feeds = [
        ("Bloomberg - Economics", config.RSS_FEEDS_CENTRAL_BANKS.get("Bloomberg - Economics", "")),
        ("CNBC - Economy",        config.RSS_FEEDS_CENTRAL_BANKS.get("CNBC - Economy", "")),
        ("BBC - Business",        config.RSS_FEEDS_WORLD.get("BBC - Business", "")),
    ]
    for name, url in filtered_feeds:
        if not url:
            continue
        arts = fetch_rss_feed(name, url, filter_keywords=CENTRAL_BANK_KEYWORDS, hours_back=72)
        all_articles.extend(arts)
        print(f"  {name}: {len(arts)} articoli (filtrati CB)")

    newsapi_arts = fetch_newsapi(category="central_banks")
    all_articles.extend(newsapi_arts)

    result = deduplicate_with_source_limit(all_articles, max_total=config.MAX_NEWS_CENTRAL_BANKS, max_per_source=3)
    print(f"[News] CB news totali: {len(result)}")
    return result


# ────────────────────────────────────────────────────────────────────
# SEZIONE 3: AI & Robotica
# ────────────────────────────────────────────────────────────────────

def get_oil_news():
    """News Oil & Energy ultime 24h — WTI, Brent, OPEC, geopolitica energetica."""
    print("[News] Fetching Oil & Energy news...")
    all_articles = []

    oil_feeds = [
        ("Bloomberg - Markets",    config.RSS_FEEDS_FINANCE.get("Bloomberg - Markets", "")),
        ("Bloomberg - Economics",  config.RSS_FEEDS_FINANCE.get("Bloomberg - Economics", "")),
        ("CNBC - Markets",         config.RSS_FEEDS_FINANCE.get("CNBC - Markets", "")),
        ("BBC - Business",         config.RSS_FEEDS_WORLD.get("BBC - Business", "")),
        ("Al Jazeera",             config.RSS_FEEDS_WORLD.get("Al Jazeera", "")),
        ("MarketWatch",            config.RSS_FEEDS_FINANCE.get("MarketWatch", "")),
        ("Investing.com",          config.RSS_FEEDS_FINANCE.get("Investing.com", "")),
    ]

    oil_kw = getattr(config, "OIL_KEYWORDS", [
        "oil", "crude", "brent", "wti", "opec", "petroleum", "barrel",
        "energy", "gasoline", "saudi", "aramco", "natural gas", "lng",
    ])

    for name, url in oil_feeds:
        if not url:
            continue
        arts = fetch_rss_feed(name, url, filter_keywords=oil_kw, hours_back=config.NEWS_HOURS_BACK)
        if arts:
            all_articles.extend(arts)
            print(f"  {name}: {len(arts)} articoli (oil/energy)")

    result = deduplicate_with_source_limit(all_articles, max_total=8, max_per_source=2)
    print(f"[News] Oil news totali: {len(result)}")
    return result


def get_ai_robotics_news():
    """News AI & Robotica ultime 24h."""
    print("[News] Fetching AI & Robotics news...")
    all_articles = []

    ai_feeds = [
        ("Bloomberg - Technology", config.RSS_FEEDS_AI.get("Bloomberg - Technology", "")),
        ("CNBC - Technology",      config.RSS_FEEDS_AI.get("CNBC - Technology", "")),
        ("BBC - Technology",       config.RSS_FEEDS_AI.get("BBC - Technology", "")),
        ("The Guardian - Tech",    config.RSS_FEEDS_AI.get("The Guardian - Tech", "")),
        ("Seeking Alpha - Tech",   config.RSS_FEEDS_AI.get("Seeking Alpha - Tech", "")),
    ]

    for name, url in ai_feeds:
        if not url:
            continue
        arts = fetch_rss_feed(name, url, filter_keywords=AI_KEYWORDS, hours_back=config.NEWS_HOURS_BACK)
        all_articles.extend(arts)
        print(f"  {name}: {len(arts)} articoli")

    newsapi_arts = fetch_newsapi(category="ai")
    all_articles.extend(newsapi_arts)

    result = deduplicate_with_source_limit(all_articles, max_total=config.MAX_NEWS_AI, max_per_source=2)
    print(f"[News] AI news totali: {len(result)}")
    return result
