"""Your household: people, health, home, pets. Used to tailor every answer.

Stored only in household.json on this Mac (owner-only file, not in git). Edit it from the web page
(Household button) or by hand.
"""
import json, os, re, time

from . import config as C

PERSON = ("name", "born", "sex", "weight", "pregnant", "conditions", "medications", "allergies",
          "blood_type", "mobility", "skills", "notes")
HOME = ("setting", "location", "water", "heat", "power", "supplies", "notes")


def load():
    try:
        return json.loads(C.HOUSEHOLD.read_text())
    except (FileNotFoundError, ValueError):
        return None


def _clean(d, keys):
    out = {}
    for k in keys:
        v = str((d or {}).get(k) or "").strip()[:600]
        if v:
            out[k] = v
    return out


def save(data):
    h = {"updated": time.strftime("%Y-%m-%d"),
         "people": [p for p in (_clean(p, PERSON) for p in data.get("people", [])[:20]) if p.get("name")],
         "home": _clean(data.get("home"), HOME),
         "pets": str(data.get("pets") or "").strip()[:600]}
    tmp = C.HOUSEHOLD.with_suffix(".tmp")
    tmp.write_text(json.dumps(h, indent=1) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, C.HOUSEHOLD)
    return h


def age_months(born):
    """'1984', '2024-03', or '2024-03-15' -> age in months (mid-year if no month)."""
    m = re.match(r"\s*(\d{4})(?:-(\d{1,2}))?", born or "")
    if not m:
        return None
    t = time.localtime()
    months = (t.tm_year - int(m[1])) * 12 + t.tm_mon - int(m[2] or 7)
    return months if months >= 0 else None


def age_text(born):
    m = age_months(born)
    if m is None:
        return ""
    return f"{m} months old" if m < 24 else f"{m // 12} years old"


def lines():
    """The household as short plain-text lines, for the model and the printed binder."""
    h = load() or {}
    out = []
    for p in h.get("people", []):
        bits = [b for b in (age_text(p.get("born")), p.get("sex"),
                            p.get("weight") and f"weighs {p['weight']}") if b]
        s = p["name"] + (f" ({', '.join(bits)})" if bits else "")
        if p.get("pregnant"):
            s += f". {p['pregnant']}"
        for k, label in (("conditions", "Conditions"), ("medications", "Daily medicines"),
                         ("allergies", "Allergies"), ("blood_type", "Blood type"),
                         ("mobility", "Mobility and other needs"), ("skills", "Training"),
                         ("notes", "Notes")):
            if p.get(k):
                s += f". {label}: {p[k]}"
        out.append(s)
    home = h.get("home", {})
    for k, label in (("setting", "Home"), ("location", "Location"), ("water", "Water"), ("heat", "Heat and cooking"),
                     ("power", "Backup power"), ("supplies", "Supplies on hand"), ("notes", "Home notes")):
        if home.get(k):
            out.append(f"{label}: {home[k]}")
    if h.get("pets"):
        out.append(f"Pets: {h['pets']}")
    return out


def prompt():
    ls = lines()
    return "HOUSEHOLD (the user's own family and home, from their intake):\n" + \
        "\n".join(f"- {l}" for l in ls) if ls else ""


def search_hint(text):
    """Words to add to the search when the question names someone: their age group or pregnancy.

    Allergies and conditions go to the model, not the search, so they don't pull in off-topic passages.
    """
    extra = []
    for p in (load() or {}).get("people", []):
        if re.search(rf"\b{re.escape(p['name'])}\b", text, re.I):
            m = age_months(p.get("born"))
            if m is not None and m < 12:
                extra.append("infant")
            elif m is not None and m < 18 * 12:
                extra.append("child")
            if p.get("pregnant"):
                extra.append(p["pregnant"].lower())
    return " ".join(dict.fromkeys(extra))
