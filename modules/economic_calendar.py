"""
Economic Calendar Module
Sources: Forex Factory (public JSON)
Timezone: Europe/Rome (GMT+2 summer / GMT+1 winter)
Filter: High importance events only
"""

import requests
from datetime import datetime
import pytz
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

ROME_TZ = pytz.timezone("Europe/Rome")

# Timezone per paese/valuta — REGOLA GENERALE per collocare le FESTIVITÀ nel giorno
# corretto: le all-day di Forex Factory vanno lette nel fuso LOCALE del paese, non in
# ora di Roma (altrimenti per i paesi a est — NZ +12, JP +9, AU +10, CN +8 — la data
# slitta al giorno prima). Vale per qualsiasi festività di qualsiasi paese.
CURRENCY_TZ = {
    "USD": pytz.timezone("America/New_York"),
    "EUR": pytz.timezone("Europe/Berlin"),
    "GBP": pytz.timezone("Europe/London"),
    "JPY": pytz.timezone("Asia/Tokyo"),
    "CNY": pytz.timezone("Asia/Shanghai"),
    "AUD": pytz.timezone("Australia/Sydney"),
    "NZD": pytz.timezone("Pacific/Auckland"),
    "CAD": pytz.timezone("America/Toronto"),
    "CHF": pytz.timezone("Europe/Zurich"),
    "SEK": pytz.timezone("Europe/Stockholm"),
    "NOK": pytz.timezone("Europe/Oslo"),
}

# Rinomina eventi "rate decision" con nome banca centrale leggibile.
# Chiave: sottostringa (lowercase) nel titolo FF → valore: nome da mostrare
_RATE_DECISION_RENAME = {
    "official cash rate":          "RBNZ Interest Rate Decision",       # NZD
    "federal funds rate":          "Fed Interest Rate Decision",         # USD
    "interest rate decision":      None,  # gestito per valuta sotto
    "main refinancing rate":       "ECB Rates Decision (MRO + DFR)",     # EUR
    "deposit facility rate":       "ECB Interest Rate Decision",         # EUR
    "refinancing rate":            "ECB Interest Rate Decision",         # EUR
    "official bank rate":          "BoE Interest Rate Decision",         # GBP
    "boe bank rate":               "BoE Interest Rate Decision",         # GBP
    "cash rate":                   None,  # gestito per valuta sotto (RBA usa "Cash Rate")
    "overnight rate":              "BoC Interest Rate Decision",         # CAD
    "policy interest rate":        "BoC Interest Rate Decision",         # CAD
    "snb policy rate":             "SNB Interest Rate Decision",         # CHF
    "libor rate":                  "SNB Interest Rate Decision",         # CHF
    "policy rate":                 None,  # gestito per valuta sotto
    "short-term interest rate":    "BoJ Interest Rate Decision",         # JPY
    "boj policy rate":             "BoJ Interest Rate Decision",         # JPY
    "1-year loan prime rate":      "PBoC Loan Prime Rate",               # CNY
    "loan prime rate":             "PBoC Loan Prime Rate",               # CNY
    "riksbank rate":               "Riksbank Interest Rate Decision",    # SEK
    "repo rate":                   None,  # gestito per valuta sotto
}

# Per titoli ambigui (es. "Cash Rate", "Policy Rate") → disambigua per valuta
_RATE_BY_CURRENCY = {
    "AUD": "RBA Interest Rate Decision",
    "NZD": "RBNZ Interest Rate Decision",
    "USD": "Fed Interest Rate Decision",
    "EUR": "ECB Interest Rate Decision",
    "GBP": "BoE Interest Rate Decision",
    "JPY": "BoJ Interest Rate Decision",
    "CAD": "BoC Interest Rate Decision",
    "CHF": "SNB Interest Rate Decision",
    "SEK": "Riksbank Interest Rate Decision",
    "NOK": "Norges Bank Interest Rate Decision",
    "CNY": "PBoC Interest Rate Decision",
}


# Rename generali (match esatto case-insensitive sul titolo completo)
_GENERAL_RENAMES = {
    "unemployment claims":        "Initial Jobless Claims",
    "non-farm employment change": "Nonfarm Payrolls",
}


def _maybe_rename_rate_event(title: str, currency: str) -> str:
    """Rinomina eventi: rate decision con nome banca centrale + rename generali."""
    title_lower = title.lower()
    # Rename generali (match esatto)
    if title_lower in _GENERAL_RENAMES:
        return _GENERAL_RENAMES[title_lower]
    # Rate decision rename
    for pattern, new_name in _RATE_DECISION_RENAME.items():
        if pattern in title_lower:
            if new_name is not None:
                return new_name
            return _RATE_BY_CURRENCY.get(currency, title)
    return title

# Mappa valuta → bandiera emoji + nome paese
CURRENCY_FLAGS = {
    "USD": ("🇺🇸", "USA"),
    "EUR": ("🇪🇺", "Eurozona"),
    "GBP": ("🇬🇧", "UK"),
    "JPY": ("🇯🇵", "Giappone"),
    "CNY": ("🇨🇳", "Cina"),
    "CAD": ("🇨🇦", "Canada"),
    "AUD": ("🇦🇺", "Australia"),
    "NZD": ("🇳🇿", "N. Zelanda"),
    "CHF": ("🇨🇭", "Svizzera"),
    "SEK": ("🇸🇪", "Svezia"),
    "NOK": ("🇳🇴", "Norvegia"),
    "MXN": ("🇲🇽", "Messico"),
    "BRL": ("🇧🇷", "Brasile"),
    "INR": ("🇮🇳", "India"),
    "KRW": ("🇰🇷", "Corea del Sud"),
    "SGD": ("🇸🇬", "Singapore"),
    "HKD": ("🇭🇰", "Hong Kong"),
    "TRY": ("🇹🇷", "Turchia"),
    "ZAR": ("🇿🇦", "Sud Africa"),
    "ILS": ("🇮🇱", "Israele"),
}


def fetch_forex_factory_calendar():
    """
    Fetch today's high-impact events from Forex Factory weekly JSON.
    Dates in JSON are ISO 8601 with timezone offset (e.g. 2026-04-02T08:30:00-04:00).
    """
    events = []
    try:
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json",
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        today_rome = datetime.now(ROME_TZ).date()

        for event in data:
            try:
                impact = event.get("impact", "").lower()
                if impact != "high":
                    continue

                date_str = event.get("date", "")
                if not date_str:
                    continue

                # ISO 8601 parsing (handles timezone offset correctly)
                event_dt_aware = datetime.fromisoformat(date_str)

                # Convert to Rome timezone
                event_dt_rome = event_dt_aware.astimezone(ROME_TZ)

                # Only today's events
                if event_dt_rome.date() != today_rome:
                    continue

                events.append({
                    "time": event_dt_rome.strftime("%H:%M"),
                    "currency": event.get("country", "—"),
                    "event": event.get("title", "—"),
                    "impact": "HIGH",
                    "impact_color": "#e74c3c",
                    "forecast": event.get("forecast", "—") or "—",
                    "previous": event.get("previous", "—") or "—",
                    "actual": event.get("actual", "—") or "—",
                    "source": "Forex Factory",
                })

            except Exception:
                continue

        events.sort(key=lambda x: x["time"])
        print(f"[Calendar] Forex Factory: {len(events)} high-impact events today")
        return events

    except Exception as e:
        print(f"[Calendar] Forex Factory error: {e}")
        return []


# Mappa valuta → mercati chiusi (usata per le festività)
_HOLIDAY_MARKETS = {
    "USD": "US Markets (NYSE, Nasdaq)",
    "EUR": "European Markets",
    "GBP": "London Stock Exchange (LSE)",
    "JPY": "Tokyo Stock Exchange (TSE)",
    "CNY": "Chinese Markets (Shanghai, Shenzhen)",
    "AUD": "Australian Securities Exchange (ASX)",
    "NZD": "New Zealand Exchange (NZX)",
    "CHF": "Swiss Exchange (SIX)",
    "CAD": "Toronto Stock Exchange (TSX)",
}

# Orari di apertura dei principali mercati (ora italiana, ora legale CEST = UTC+2)
# Formato: (apertura, chiusura)
_MARKET_HOURS_IT = {
    "Tokyo Stock Exchange (TSE)":             ("02:00", "08:30"),
    "Chinese Markets (Shanghai, Shenzhen)":   ("03:30", "10:00"),
    "Hong Kong Stock Exchange (HKEX)":        ("03:30", "10:00"),
    "Australian Securities Exchange (ASX)":   ("01:00", "07:00"),
    "New Zealand Exchange (NZX)":             ("22:00", "06:30"),  # opens previous evening
    "London Stock Exchange (LSE)":            ("09:00", "17:30"),
    "Frankfurt Stock Exchange (XETRA)":       ("09:00", "17:30"),
    "Paris Stock Exchange (Euronext Paris)":  ("09:00", "17:30"),
    "Milan Stock Exchange (Euronext Milan)":  ("09:00", "17:30"),
    "Madrid Stock Exchange (BME)":            ("09:00", "17:30"),
    "Swiss Exchange (SIX)":                  ("09:00", "17:30"),
    "European Markets":                       ("09:00", "17:30"),
    "US Markets (NYSE, Nasdaq)":              ("15:30", "22:00"),
    "Toronto Stock Exchange (TSX)":           ("15:30", "22:00"),
}

# Titoli specifici FF che indicano solo un paese EUR
_EUR_COUNTRY_MARKETS = {
    "french":  "Paris Stock Exchange (Euronext Paris)",
    "german":  "Frankfurt Stock Exchange (XETRA)",
    "italian": "Milan Stock Exchange (Euronext Milan)",
    "spanish": "Madrid Stock Exchange (BME)",
}

# Riepilogo orari weekend per tutti i mercati principali (ora italiana CEST)
# ── NYSE / Nasdaq Early Close ──────────────────────────────────────────────
# Calcolato algoritmicamente: nessun hardcoding, funziona per qualsiasi anno.
# NYSE chiude alle 13:00 ET = 19:00 ora italiana (estate e inverno: il fuso
# US↔Italia si sposta simmetricamente, quindi l'orario italiano è sempre fisso).
#
# Regole ufficiali NYSE (invariate da decenni):
#   1. Eve of Independence Day: 3 luglio SE è feriale e luglio 4 ≠ domenica/lunedì
#   2. Black Friday: venerdì dopo il 4° giovedì di novembre (Thanksgiving)
#   3. Christmas Eve: 24 dicembre SE è un giorno feriale

from datetime import date as _date


def _nyse_early_closes_for_year(year: int) -> dict:
    """
    Ritorna {date: (close_time_italian, reason)} per le early close NYSE dell'anno.
    Aggiornamento automatico: basta che il processo giri in un anno nuovo.
    """
    result = {}

    # 1. Eve of Independence Day (3 luglio)
    jul4 = _date(year, 7, 4)
    # weekday(): 0=Lun, 1=Mar, 2=Mer, 3=Gio, 4=Ven, 5=Sab, 6=Dom
    # L'early close azionario del 3 luglio avviene SOLO se il 4 luglio è Mar–Ven (1-4),
    # perché allora il 3 luglio è un normale giorno di borsa (Lun–Gio) prima della festività.
    #   - 4 luglio = Sabato (5) → festività osservata VENERDÌ 3 → mercato CHIUSO tutto il giorno
    #                             (la riga "CLOSED" arriva da Forex Factory), NIENTE early close
    #   - 4 luglio = Domenica (6) → osservato lunedì 5, il 3 luglio è venerdì normale → niente early close
    #   - 4 luglio = Lunedì (0) → il 3 luglio è domenica → niente early close
    if jul4.weekday() in (1, 2, 3, 4):
        result[_date(year, 7, 3)] = ("19:00", "Eve of Independence Day")

    # 2. Black Friday (giorno dopo il 4° giovedì di novembre)
    nov1 = _date(year, 11, 1)
    days_to_thu = (3 - nov1.weekday()) % 7        # giorni al 1° giovedì
    thanksgiving = _date.fromordinal(nov1.toordinal() + days_to_thu + 21)  # +3 settimane
    result[_date.fromordinal(thanksgiving.toordinal() + 1)] = (
        "19:00", "Black Friday — Day after Thanksgiving"
    )

    # 3. Christmas Eve (24 dicembre, solo se feriale)
    dec24 = _date(year, 12, 24)
    if dec24.weekday() < 5:
        result[dec24] = ("19:00", "Christmas Eve")

    return result


def _build_nyse_early_close_map() -> dict:
    """Costruisce la mappa per l'anno corrente + prossimo (copre sempre il rolling 3-day window)."""
    from datetime import datetime
    current_year = datetime.now().year
    result = {}
    for yr in (current_year, current_year + 1):
        result.update(_nyse_early_closes_for_year(yr))
    return result


# Calcolato a import time, si ricalcola ad ogni avvio del processo
NYSE_EARLY_CLOSE = _build_nyse_early_close_map()
# ────────────────────────────────────────────────────────────────────────────

_WEEKEND_CLOSURE_TEXT = (
    "🔴 ALL MARKETS CLOSED — Weekend &nbsp;·&nbsp; "
    "Reopening Monday: Tokyo 02:00 · Shanghai 03:30 · London/Frankfurt 09:00 · New York 15:30 (Italian time)"
)


def _build_weekend_event(date_obj) -> dict:
    """Crea una riga 'mercati chiusi - weekend' per sabato o domenica."""
    import calendar
    day_name = calendar.day_name[date_obj.weekday()]  # 'Saturday' / 'Sunday'
    label = "Saturday" if day_name == "Saturday" else "Sunday"
    return {
        "time": "All day",
        "currency": "—",
        "flag": "",
        "event": _WEEKEND_CLOSURE_TEXT,
        "impact": "CLOSED",
        "forecast": "—",
        "previous": "—",
        "actual": "—",
        "actual_overdue": False,
        "source": "Forex Factory",
    }


def _match_impact_override(overrides, title, currency):
    """Check if title+currency matches any (title_substr, currency_or_None) tuple."""
    for entry in overrides:
        t, c = entry
        if t.lower() in title:
            if c is None or c == currency:
                return True
    return False


def _parse_ff_json(data, target_dates):
    """Parse Forex Factory JSON into {day_key: [events]} for target_dates."""
    whitelist         = [w.lower() for w in getattr(config, "CALENDAR_WHITELIST", [])]
    blacklist         = [w.lower() for w in getattr(config, "CALENDAR_BLACKLIST", [])]
    blacklist_currency = getattr(config, "CALENDAR_BLACKLIST_CURRENCY", [])
    high_force        = getattr(config, "CALENDAR_IMPACT_HIGH", [])
    med_force         = getattr(config, "CALENDAR_IMPACT_MED", [])
    result = {}
    for event in data:
        try:
            impact   = event.get("impact", "").lower()
            title    = event.get("title", "").lower()
            currency = event.get("country", "—")

            # Blacklist: escludi sempre questi eventi
            if any(b in title for b in blacklist):
                continue
            if _match_impact_override(blacklist_currency, title, currency):
                continue

            in_whitelist = any(w in title for w in whitelist)
            is_holiday = impact == "holiday"
            if impact not in ("high", "medium") and not in_whitelist and not is_holiday:
                continue
            date_str = event.get("date", "")
            if not date_str:
                continue
            event_dt = datetime.fromisoformat(date_str)
            event_dt_rome = event_dt.astimezone(ROME_TZ)
            # FESTIVITÀ: data nel fuso del PAESE (regola generale via CURRENCY_TZ), non di Roma,
            # altrimenti slitta al giorno prima per i paesi a est. Eventi orari: restano su Roma.
            if is_holiday:
                event_dt_for_date = event_dt.astimezone(CURRENCY_TZ.get(currency, ROME_TZ))
            else:
                event_dt_for_date = event_dt_rome
            if event_dt_for_date.date() not in target_dates:
                continue

            day_key = event_dt_for_date.strftime("%A %d %B")
            if day_key not in result:
                result[day_key] = []

            if is_holiday:
                currency = event.get("country", "—")
                flag, _ = CURRENCY_FLAGS.get(currency, ("", currency))
                # Determina mercato specifico dal titolo
                market = _HOLIDAY_MARKETS.get(currency, f"Market {currency}")
                if currency == "EUR":
                    for keyword, mkt in _EUR_COUNTRY_MARKETS.items():
                        if keyword in title:
                            market = mkt
                            break
                hours = _MARKET_HOURS_IT.get(market)
                if hours:
                    hours_txt = f"Normal hours: {hours[0]}–{hours[1]} (Italian time)"
                else:
                    hours_txt = "Hours not available"
                result[day_key].append({
                    "time": "All day",
                    "currency": currency,
                    "flag": flag,
                    "event": f"🔴 {market} CLOSED — {event.get('title', 'Bank Holiday')} · {hours_txt}",
                    "impact": "CLOSED",
                    "forecast": "—",
                    "previous": "—",
                    "actual": "—",
                    "actual_overdue": False,
                    "source": "Forex Factory",
                })
                continue

            force_high = _match_impact_override(high_force, title, currency)
            force_med  = _match_impact_override(med_force,  title, currency)
            if force_med:
                impact_label = "MED"
            elif impact == "high" or force_high:
                impact_label = "HIGH"
            elif in_whitelist and impact not in ("high", "medium"):
                impact_label = "WL"
            else:
                impact_label = "MED"
            actual_raw = event.get("actual", "") or ""
            now_rome = datetime.now(ROME_TZ)
            # Flag: evento già passato ma actual ancora vuoto (FF API lag)
            actual_overdue = (actual_raw == "") and (event_dt_rome < now_rome)
            currency = event.get("country", "—")
            flag, _ = CURRENCY_FLAGS.get(currency, ("", currency))

            raw_title = event.get("title", "—")
            renamed   = _maybe_rename_rate_event(raw_title, currency)

            result[day_key].append({
                "time": event_dt_rome.strftime("%H:%M"),
                "currency": currency,
                "flag": flag,
                "event": renamed,
                "impact": impact_label,
                "forecast": event.get("forecast", "—") or "—",
                "previous": event.get("previous", "—") or "—",
                "actual": actual_raw if actual_raw else "—",
                "actual_overdue": actual_overdue,
                "source": "Forex Factory",
            })


        except Exception:
            continue
    for day in result:
        result[day].sort(key=lambda x: x["time"])
    return result


def fetch_forex_factory_multiday(days=3):
    """
    Fetch high + medium impact events for today + next N days.
    Also fetches next week JSON when the window crosses the week boundary.
    Returns dict: { date_str: [events] }
    """
    headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
    today_rome = datetime.now(ROME_TZ)
    target_dates = set()
    for i in range(days):
        d = today_rome.date().__class__.fromordinal(today_rome.date().toordinal() + i)
        target_dates.add(d)

    result = {}

    # Precompila i giorni weekend + NYSE early close
    for i in range(days):
        d = today_rome.date().__class__.fromordinal(today_rome.date().toordinal() + i)
        day_key = datetime(d.year, d.month, d.day, tzinfo=ROME_TZ).strftime("%A %d %B")
        if d.weekday() in (5, 6):  # 5=sabato, 6=domenica
            if day_key not in result:
                result[day_key] = [_build_weekend_event(d)]
        elif d in NYSE_EARLY_CLOSE:
            close_time, reason = NYSE_EARLY_CLOSE[d]
            flag, _ = CURRENCY_FLAGS.get("USD", ("🇺🇸", "USA"))
            early_ev = {
                "time": "All day",
                "currency": "USD",
                "flag": flag,
                "event": (
                    f"🟡 US Markets (NYSE, Nasdaq) EARLY CLOSE — {reason}"
                    f" &nbsp;·&nbsp; Closes at {close_time} (Italian time) instead of 22:00"
                ),
                "impact": "EARLY",
                "forecast": "—",
                "previous": "—",
                "actual": "—",
                "actual_overdue": False,
                "source": "NYSE Official Calendar",
            }
            if day_key not in result:
                result[day_key] = []
            # Inserisce la riga early close in testa alla giornata
            result[day_key].insert(0, early_ev)

    import time as _time

    import os, json as _json, tempfile

    CACHE_TTL = 1800  # 30 minuti — evita 429 su rigenerazioni ravvicinate

    def _cache_path(url):
        fname = url.split("/")[-1].replace(".json", "_cache.json")
        return os.path.join(tempfile.gettempdir(), f"ff_{fname}")

    def _fetch_ff_with_retry(url, max_retries=4, base_delay=4):
        """Fetch FF JSON con cache su disco (TTL 30 min) e retry su 429."""
        cache_file = _cache_path(url)
        # Usa cache se fresca
        if os.path.exists(cache_file):
            age = _time.time() - os.path.getmtime(cache_file)
            if age < CACHE_TTL:
                try:
                    with open(cache_file) as f:
                        return _json.load(f)
                except Exception:
                    pass  # cache corrotta, rifetch

        for attempt in range(max_retries):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                if resp.status_code == 404:
                    return None  # nextweek non ancora disponibile
                if resp.status_code == 429:
                    wait = base_delay * (2 ** attempt)  # backoff: 4s, 8s, 16s, 32s
                    print(f"[Calendar] 429 rate limit su {url.split('/')[-1]}, retry in {wait}s...")
                    _time.sleep(wait)
                    continue
                resp.raise_for_status()
                if not resp.text.strip():
                    wait = base_delay * (2 ** attempt)
                    print(f"[Calendar] Empty response from FF, retrying in {wait}s...")
                    _time.sleep(wait)
                    continue
                data = resp.json()
                # Salva in cache
                try:
                    with open(cache_file, "w") as f:
                        _json.dump(data, f)
                except Exception:
                    pass
                return data
            except Exception as e:
                print(f"[Calendar] Fetch error {url}: {e}")
                if attempt < max_retries - 1:
                    _time.sleep(base_delay)
        # Tutti i retry falliti — usa cache scaduta se disponibile (meglio vecchi dati che niente)
        if os.path.exists(cache_file):
            try:
                with open(cache_file) as f:
                    print(f"[Calendar] Using expired cache for {url.split('/')[-1]}")
                    return _json.load(f)
            except Exception:
                pass
        return None

    for url in [
        "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
        "https://nfs.faireconomy.media/ff_calendar_nextweek.json",
    ]:
        data = _fetch_ff_with_retry(url)
        if data is None:
            continue
        try:
            partial = _parse_ff_json(data, target_dates)
            for day_key, events in partial.items():
                if day_key not in result:
                    result[day_key] = []
                # Merge without duplicates
                existing_keys = {(e["time"], e["event"]) for e in result[day_key]}
                for ev in events:
                    if (ev["time"], ev["event"]) not in existing_keys:
                        result[day_key].append(ev)
                result[day_key].sort(key=lambda x: x["time"])
        except Exception as e:
            print(f"[Calendar] Parsing error {url}: {e}")

    # Riordina cronologicamente (il weekend precompilation può inserire giorni fuori ordine)
    def _day_key_to_date(key):
        try:
            from datetime import datetime as _dt
            return _dt.strptime(key, "%A %d %B").replace(year=today_rome.year)
        except Exception:
            return today_rome.replace(tzinfo=None)

    result = dict(sorted(result.items(), key=lambda x: _day_key_to_date(x[0])))
    return result


def get_economic_calendar():
    """
    Returns high-impact events for today + next 2 days.
    """
    print("[Calendar] Fetching 3-day economic calendar...")
    multiday = fetch_forex_factory_multiday(days=3)

    total = sum(len(v) for v in multiday.values())
    print(f"[Calendar] {total} high-impact events in next 3 days")

    if not multiday:
        today_key = datetime.now(ROME_TZ).strftime("%A %d %B")
        return {today_key: [{
            "time": "—", "currency": "—", "flag": "",
            "event": "No high-impact events scheduled",
            "impact": "HIGH", "forecast": "—", "previous": "—", "actual": "—",
            "actual_overdue": False, "source": "Forex Factory",
        }]}

    return multiday
