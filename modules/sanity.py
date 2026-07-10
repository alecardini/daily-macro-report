"""
Data-quality / plausibility layer.

Copre il buco della regola d'oro che 'data not available' (fetch FALLITO) non copre:
il fetch che RIESCE ma con spazzatura — prezzo non positivo, movimento assurdo, fonte
congelata, implausibilità cross-asset (es. liquidazioni BTC << ETH/SOL).

Non invasivo: NON muta 'data'. Ritorna (warnings, snapshot). Lo snapshot dei prezzi
serve al confronto move-vs-last-run alla prossima esecuzione.
"""
import json

_SNAPSHOT_PATH = "/tmp/report_snapshot.json"

# |% move| oltre cui un movimento vs il run precedente è "assurdo" (per categoria)
_ABSURD_MOVE = {"crypto": 50.0, "index": 15.0, "commodity": 25.0, "fx": 10.0}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _price_items(data):
    """Genera (key, label, value, category) per ogni valore-prezzo chiave del report."""
    for sym, d in (data.get("crypto", {}).get("prices", {}) or {}).items():
        if isinstance(d, dict):
            yield (f"crypto:{sym}", f"{sym} price", _num(d.get("price")), "crypto")
    for grp, cat in (("indices", "index"), ("futures", "index"),
                     ("other_assets", "commodity"), ("fx", "fx")):
        for name, d in (data.get(grp, {}) or {}).items():
            if name == "VIX":
                continue                  # VIX ha il suo range-check; si muove legittimamente >15%/gg
            if isinstance(d, dict):
                yield (f"{grp}:{name}", name, _num(d.get("price")), cat)


def load_snapshot():
    try:
        with open(_SNAPSHOT_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def save_snapshot(snap):
    try:
        with open(_SNAPSHOT_PATH, "w") as f:
            json.dump(snap, f)
    except Exception:
        pass


def check_data_quality(data, prev_snapshot=None):
    """Ritorna (warnings: list[str], snapshot: dict) senza mutare 'data'."""
    warnings = []
    prev = prev_snapshot or {}
    snap = {}

    # 1) valori impossibili + 2) movimento assurdo / fonte congelata (vs run precedente)
    for key, label, val, cat in _price_items(data):
        if val is None:
            continue                      # fetch fallito → già gestito da 'data not available'
        snap[key] = val
        if val <= 0:
            warnings.append(f"{label}: non-positive value ({val:g})")
            continue
        pv = prev.get(key)
        if pv and pv > 0:
            move = abs(val - pv) / pv * 100
            if move > _ABSURD_MOVE.get(cat, 30.0):
                warnings.append(f"{label}: absurd {move:.0f}% move vs last run ({pv:g}→{val:g})")
            elif val == pv and cat == "crypto":   # solo crypto: 24/7, se identica è sospetta
                warnings.append(f"{label}: identical to last run ({val:g}) — possible frozen source")

    # VIX fuori range plausibile
    vix = data.get("indices", {}).get("VIX", {})
    v = _num(vix.get("price")) if isinstance(vix, dict) else None
    if v is not None and not (0 < v < 150):
        warnings.append(f"VIX out of plausible range ({v:g})")

    # 3) cross-asset: le liquidazioni 24h di BTC non devono essere ordini di grandezza
    #    SOTTO ETH/SOL (BTC è il mercato più grande). Becca il bug Coinalyze del 10/07.
    liq = data.get("crypto", {}).get("liquidations", {}) or {}

    def _liq_total(sym):
        d = liq.get(sym, {})
        if not isinstance(d, dict):
            return None
        l, s = _num(d.get("long_raw")), _num(d.get("short_raw"))
        if l is None and s is None:
            return None
        return (l or 0) + (s or 0)

    btc = _liq_total("BTC")
    peers = [x for x in (_liq_total("ETH"), _liq_total("SOL")) if x]
    if btc is not None and peers and btc < 0.5 * max(peers):
        warnings.append(
            f"BTC 24h liquidations (${btc:,.0f}) implausibly below ETH/SOL "
            f"(max ${max(peers):,.0f}) — check Coinalyze aggregation")

    return warnings, snap
