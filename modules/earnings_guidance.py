"""
Earnings — Fase B: GUIDANCE del prossimo trimestre + MARGINE LORDO dal comunicato ufficiale SEC.

Perché così (verificato 18/11/2026): nessuna fonte GRATUITA dà la guidance come dato strutturato
(Finnhub/FMP/Yahoo/Nasdaq/Alpha Vantage no; Benzinga/Massive sì ma a pagamento; edgartools legge
solo le tabelle → guidance None anche per NVDA). Quindi:
  1. comunicato sugli utili dalla SEC (8-K Item 2.02 / 6-K, allegati EX-99.x), gratis;
  2. estrazione con Gemini in JSON (temperatura 0);
  3. CONTROLLI ANTI-ERRORE: ogni numero deve comparire TESTUALMENTE nella frase citata, la frase
     deve comparire TESTUALMENTE nel comunicato, la guidance deve riferirsi a un TRIMESTRE
     (non all'anno) e avere un ordine di grandezza coerente con i ricavi appena riportati.
     Se un controllo fallisce → il dato non viene mostrato (meglio vuoto che sbagliato).

L'identità per la SEC (obbligatoria) è SEC_USER_AGENT in config_local.py (git-ignored): non viene
mai stampata né inviata ad altri servizi.
"""

import json
import os
import re
import sys
import time
import html as _html
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR = os.path.join(_ROOT, ".cache")
_TICKERS_CACHE = os.path.join(_CACHE_DIR, "sec_company_tickers.json")
_RESULTS_CACHE = os.path.join(_CACHE_DIR, "earnings_guidance.json")


def _ua():
    ua = getattr(config, "SEC_USER_AGENT", "") or ""
    return ua if "@" in ua else ""


def _sec_get(url, timeout=30):
    ua = _ua()
    if not ua:
        return None
    for attempt in range(2):
        try:
            r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code in (429, 503) and attempt == 0:
                time.sleep(2)
                continue
            return None
        except Exception:
            if attempt == 0:
                time.sleep(2)
                continue
            return None
        finally:
            time.sleep(0.15)   # ben sotto il limite SEC (10 richieste/secondo)
    return None


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
    except Exception as e:
        print(f"[Guidance] cache save error: {e}")


def _cik_for(sym):
    """Ticker → CIK dalla mappa ufficiale SEC (cache 7 giorni)."""
    cache = _load_json(_TICKERS_CACHE, {})
    fresh = cache.get("_saved") and (time.time() - cache["_saved"] < 7 * 86400)
    if not fresh:
        r = _sec_get("https://www.sec.gov/files/company_tickers.json")
        if r is not None:
            m = {v["ticker"].upper(): int(v["cik_str"]) for v in r.json().values()}
            cache = {"_saved": time.time(), "map": m}
            _save_json(_TICKERS_CACHE, cache)
    m = cache.get("map", {})
    return m.get(sym.upper()) or m.get(sym.upper().replace(".", "-"))


def _find_release(cik, report_date):
    """
    Comunicato sugli utili depositato il giorno della trimestrale o il successivo:
    8-K con Item 2.02 (società USA) oppure 6-K (emittenti esteri). Ritorna il testo degli EX-99.x.
    """
    r = _sec_get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    if r is None:
        return None
    rec = r.json().get("filings", {}).get("recent", {})
    days = {report_date.isoformat(), (report_date + timedelta(days=1)).isoformat()}
    acc = None
    for form, fdate, items, a in zip(rec.get("form", []), rec.get("filingDate", []),
                                     rec.get("items", [""] * len(rec.get("form", []))), rec.get("accessionNumber", [])):
        if fdate not in days:
            continue
        if form == "8-K" and "2.02" in (items or ""):
            acc = a
            break
        if form == "6-K" and acc is None:
            acc = a
    if not acc:
        return None
    full = _sec_get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace('-', '')}/{acc}.txt", timeout=45)
    if full is None:
        return None
    texts = []
    for doc in re.split(r"<DOCUMENT>", full.text)[1:]:
        m = re.search(r"<TYPE>([^\n<]+)", doc)
        dtype = (m.group(1).strip().upper() if m else "")
        if not dtype.startswith("EX-99"):
            continue
        body = doc.split("<TEXT>", 1)[-1].split("</TEXT>", 1)[0]
        if "<html" in body.lower() or "<div" in body.lower() or "<p" in body.lower():
            body = BeautifulSoup(body, "lxml").get_text(" ")
        texts.append(body)
    if not texts:
        return None
    return {"accession": acc, "text": _norm(" ".join(texts))}


def _norm(s):
    s = _html.unescape(s or "")
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = s.replace("–", "-").replace("—", "-").replace("−", "-").replace("•", " ")
    return re.sub(r"\s+", " ", s).strip()


_KW = re.compile(r"(outlook|guidance|expects?|expected|anticipat|forecast|gross margin|for the (?:first|second|third|fourth) quarter|next quarter)", re.I)


def _excerpt(text, cap=16000):
    """Solo le parti utili (intorno alle parole chiave) → meno token, stesso contenuto rilevante."""
    spans = []
    for m in _KW.finditer(text):
        a, b = max(0, m.start() - 500), min(len(text), m.end() + 900)
        if spans and a <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], b)
        else:
            spans.append([a, b])
    out = " [...] ".join(text[a:b] for a, b in spans)
    return out[:cap]


_PROMPT = """You extract data from a company's official quarterly earnings press release.
Return ONLY JSON with this schema (use null when something is not explicitly stated):
{{
 "gross_margin_current": {{"value": "<percent number as written, e.g. 74.9>", "basis": "GAAP|non-GAAP|unspecified", "quote": "<exact sentence copied verbatim>"}} or null,
 "next_quarter_guidance": {{
    "period": "<period as written, e.g. fourth quarter of fiscal 2027>",
    "revenue": {{"low": "...", "high": "...", "midpoint": "...", "plus_minus": "...", "unit": "billion|million|thousand"}} or null,
    "eps": {{"low": "...", "high": "...", "midpoint": "...", "plus_minus": "...", "basis": "GAAP|non-GAAP|unspecified"}} or null,
    "gross_margin": {{"low": "...", "high": "...", "midpoint": "...", "plus_minus": "...", "basis": "GAAP|non-GAAP|unspecified"}} or null,
    "quote": "<the exact sentence(s) copied verbatim that contain these numbers>"
 }} or null,
 "only_full_year_guidance": true|false
}}
How to fill low/high/midpoint/plus_minus (each a plain number as written, without $ or words; null if absent):
- "between A and B" or "A - B" or "A to B"  -> low=A, high=B, midpoint=null, plus_minus=null
- "approximately X" or "X"                  -> midpoint=X
- "X plus or minus Y%" or "X +/- Y%"        -> midpoint=X, plus_minus="Y%" (keep the % sign)
- "X plus or minus Y" or "X +/- Y" (absolute) -> midpoint=X, plus_minus=Y (no % sign)
- "unit" is the unit of the revenue numbers (e.g. "In millions" tables -> million).
Rules:
- "next_quarter_guidance" ONLY for the NEXT FISCAL QUARTER (not the full year, not the quarter just reported). If the company gives only full-year/annual guidance, set it to null and only_full_year_guidance=true.
- Copy numbers exactly as they appear (no calculations, no rounding). Quotes must be copied verbatim.
- gross_margin_current is the gross margin of the quarter just reported. If both GAAP and non-GAAP are given, use non-GAAP.
- For EPS and gross margin guidance: if both GAAP and adjusted/non-GAAP figures are given, use the adjusted/non-GAAP one.
- Do not guess. If unsure, use null.

Company: {company}
Press release (excerpts):
\"\"\"{text}\"\"\""""


def _in_text(fragment, text):
    """
    La citazione compare TESTUALMENTE nel comunicato? Se Gemini l'ha accorciata con "..." / "[...]"
    (QCOM 4/11), ogni pezzo deve comparire testualmente (pezzi ≥15 caratteri) — nessun testo inventato.
    """
    tl = text.lower()
    f = _norm(fragment).lower()
    if len(f.strip(' ."')) >= 15 and f.strip(' ."') in tl:
        return True
    # Citazione composta: spezzo su "..." e sui confini di frase; ogni pezzo (≥15 caratteri)
    # deve comparire testualmente e TUTTI entro 2.500 caratteri (stesso paragrafo "Outlook"),
    # così non si possono unire frasi lontane (es. annuale + trimestrale).
    parts = re.split(r"\s*(?:\[\.\.\.\]|\.\.\.|…)\s*|(?<=[.;:])\s+(?=[A-Z$•\-])", _norm(fragment))
    parts = [p.lower().strip(' ."') for p in parts if p and p.strip(' ."')]
    if not parts or any(len(p) < 15 for p in parts):
        return False
    pos = []
    for p in parts:
        i = tl.find(p)
        if i < 0:
            return False
        pos.append(i)
    return max(pos) - min(pos) <= 2500


_NUM_RE = re.compile(r"\(?-?\d[\d,]*(?:\.\d+)?\)?")


def _numtok(x):
    """Primo numero contenuto in una stringa ('$18.0 billion' → '18.0'; '(0.15)' → '-0.15'). None se assente."""
    if x in (None, "", "null"):
        return None
    m = _NUM_RE.search(str(x))
    if not m:
        return None
    t = m.group(0)
    neg = t.startswith("(") and t.endswith(")")
    t = t.strip("()").replace(",", "")
    return ("-" + t.lstrip("-")) if neg else t


def _num_in(x, quote):
    """Il numero (com'è scritto) compare nella citazione? Confronto sulle cifre, ignorando $ e virgole."""
    t = _numtok(x)
    if t is None:
        return x in (None, "", "null")   # campo vuoto = ok; testo senza numero = KO
    q = quote.replace(",", "")
    return re.search(r"(?<![\d.])" + re.escape(t.lstrip("-")) + r"(?![\d])", q) is not None


def _f(x):
    t = _numtok(x)
    try:
        return float(t) if t is not None else None
    except Exception:
        return None


def _range(d):
    """
    (low, mid, high) dai campi low/high/midpoint/plus_minus (± assoluto o in %).
    None se incoerente (es. low>high, ± senza numero) → il dato non si mostra.
    """
    lo, hi, mid = _f(d.get("low")), _f(d.get("high")), _f(d.get("midpoint"))
    pm_raw = d.get("plus_minus")
    pm = _f(pm_raw)
    if pm_raw not in (None, "", "null") and pm is None:
        return None
    if mid is not None and pm is not None:
        delta = mid * pm / 100 if "%" in str(pm_raw) else pm
        lo, hi = mid - delta, mid + delta
    if mid is None and lo is not None and hi is not None:
        mid = (lo + hi) / 2
    if mid is None and lo is not None and hi is None:
        mid = lo
    if mid is None:
        return None
    if lo is not None and hi is not None and not (lo <= mid <= hi):
        return None
    return lo, mid, hi


_UNIT = {"billion": 1e9, "million": 1e6, "thousand": 1e3}


# La citazione del margine attuale deve essere una FRASE (verbo), non una riga di tabella con più
# colonne/trimestri (DDOG: "Non-GAAP gross margin 81% 81% 80% 81%" → ambigua, scartata).
_GM_SENTENCE = re.compile(r"\b(was|were|of|at|reached|increased|decreased|expanded|came in)\b", re.I)


def _validate(raw, text, rev_actual):
    """Applica i controlli. Ritorna dict pulito con solo i campi che li superano."""
    out = {"gm_current": None, "guid": None, "only_fy": bool(raw.get("only_full_year_guidance"))}

    gm = raw.get("gross_margin_current") or None
    if gm and gm.get("quote") and _in_text(gm["quote"], text) and "gross margin" in gm["quote"].lower() \
            and _GM_SENTENCE.search(gm["quote"]) and _num_in(gm.get("value"), gm["quote"]):
        v = _f(gm.get("value"))
        if v is not None and 0 < v < 100:
            out["gm_current"] = {"value": v, "basis": gm.get("basis") or "unspecified", "quote": _norm(gm["quote"])}

    g = raw.get("next_quarter_guidance") or None
    if g and g.get("quote") and _in_text(g["quote"], text):
        q = _norm(g["quote"])
        period = (g.get("period") or "")
        is_quarter = re.search(r"\b(quarter|q[1-4])\b", f"{period} {q}", re.I) is not None
        if is_quarter:
            res = {"period": period, "quote": q}
            _F = ("low", "high", "midpoint", "plus_minus")
            rv = g.get("revenue") or None
            if rv and all(_num_in(rv.get(k), q) for k in _F):
                mult = _UNIT.get((rv.get("unit") or "").lower())
                rg = _range(rv)
                if mult and rg:
                    lo, mid, hi = rg
                    mid_abs = mid * mult
                    # coerenza con i ricavi appena riportati (unità sbagliate / numero sbagliato → scarto)
                    if mid > 0 and (not rev_actual or 0.6 <= mid_abs / rev_actual <= 1.7):
                        res["rev_mid"] = mid_abs
                        res["rev_low"] = lo * mult if lo is not None else None
                        res["rev_high"] = hi * mult if hi is not None else None
            ep = g.get("eps") or None
            if ep and all(_num_in(ep.get(k), q) for k in _F):
                rg = _range(ep)
                if rg:
                    lo, mid, hi = rg
                    res.update(eps_mid=mid, eps_low=lo, eps_high=hi, eps_basis=ep.get("basis") or "unspecified")
            gg = g.get("gross_margin") or None
            if gg and "gross margin" in q.lower() and all(_num_in(gg.get(k), q) for k in _F):
                rg = _range(gg)
                if rg and all(v is None or 0 < v < 100 for v in rg):
                    lo, mid, hi = rg
                    res.update(gm_low=lo, gm_mid=mid, gm_high=hi)
            if any(k in res for k in ("rev_mid", "eps_mid", "gm_mid")):
                out["guid"] = res
    return out


def get_guidance(sym, company, report_date, rev_actual=None, gemini_fn=None):
    """
    Ritorna {"status": "ok"|"no_release"|"unavailable", "gm_current", "guid", "only_fy"}.
    Cache su disco per (ticker, data): niente nuove richieste/chiamate Gemini ai rilanci.
    """
    key = f"{sym}|{report_date.isoformat()}"
    cache = _load_json(_RESULTS_CACHE, {})
    if key in cache:
        return cache[key]
    if not _ua():
        return {"status": "unavailable"}
    cik = _cik_for(sym)
    if not cik:
        return {"status": "unavailable"}
    rel = _find_release(cik, report_date)
    if not rel:
        res = {"status": "no_release"}
        # Non metto in cache: il comunicato potrebbe arrivare più tardi (es. 6-K il giorno dopo).
        return res
    if gemini_fn is None:
        from modules.news_aggregator import _gemini_generate as gemini_fn
    txt = gemini_fn(_PROMPT.format(company=company, text=_excerpt(rel["text"])),
                    max_tokens=900, temperature=0, json_mode=True, timeout=60)
    try:
        raw = json.loads(txt)
    except Exception:
        return {"status": "unavailable"}   # Gemini non disponibile → riprova al prossimo run
    res = _validate(raw if isinstance(raw, dict) else {}, rel["text"], rev_actual)
    res.update(status="ok", accession=rel["accession"])
    # In cache solo esiti "certi": guidance trovata e validata, oppure "solo annuale".
    # Un "nessuna guidance" può dipendere da un modello di riserva più debole → si ritenta al run dopo.
    if not res.get("guid") and not res.get("only_fy"):
        return res
    cache[key] = res
    cutoff = (datetime.now().date() - timedelta(days=30)).isoformat()
    cache = {k: v for k, v in cache.items() if k.split("|")[-1] >= cutoff}
    _save_json(_RESULTS_CACHE, cache)
    return res
