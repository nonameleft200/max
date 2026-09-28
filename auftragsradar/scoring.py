"""Bewertung: Wie gut passt eine Bekanntmachung zu einem Einzelunternehmer ohne Zertifizierungen?"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .config import Profile
from .models import Notice

EU_THRESHOLD_BUND = 140000.0


@dataclass
class Score:
    total: int
    reasons: list[str] = field(default_factory=list)
    excluded: bool = False

    def __str__(self) -> str:
        return "; ".join(self.reasons)


_W = "A-Za-z0-9ÄÖÜäöüß"


def _count(text: str, needle: str) -> int:
    """Zählt Treffer als ganzes Wort (Groß-/Kleinschreibung egal). Ein '*' am Ende erlaubt Wortfortsetzungen."""
    n = needle.strip()
    if not n:
        return 0
    prefix = n.endswith("*")
    n = n.rstrip("*")
    tail = "" if prefix else rf"(?![{_W}])"
    return len(re.findall(rf"(?<![{_W}]){re.escape(n)}{tail}", text, flags=re.IGNORECASE))


def _is_it(notice: Notice, prefixes: list[str]) -> bool:
    return any(c.startswith(tuple(prefixes)) for c in notice.cpv)


def score(notice: Notice, p: Profile) -> Score:
    reasons: list[str] = []
    title = notice.title or ""
    body = notice.description or ""
    full = f"{title}\n{body}"

    # 1. Harte Ausschlüsse
    for word in p.hart:
        if _count(title, word) or _count(body, word):
            return Score(0, [f"Ausschluss: {word}"], excluded=True)

    pts = 0
    # 2. Fachliche Passung über Schlüsselwörter (stark = KI, mittel = IT/Digital, schwach = generisch)
    kw = 0
    hits: list[str] = []
    specific = False
    for weight, cap, words in ((12, 40, p.stark), (5, 25, p.mittel), (2, 8, p.schwach)):
        part = 0
        for w in words:
            c = _count(title, w) * 2 + _count(body, w)
            if c:
                part += min(c, 3) * weight
                hits.append(w.strip("* "))
                if weight > 2:
                    specific = True
        kw += min(part, cap)
    if hits:
        reasons.append("Stichworte: " + ", ".join(dict.fromkeys(hits))[:120])
    pts += kw

    # 3. CPV: IT-nah? Ohne IT-CPV muss mindestens ein fachliches Stichwort treffen.
    it = _is_it(notice, p.cpv_prefixe)
    near = _is_it(notice, p.cpv_nah)
    if it:
        pts += 12
    elif near:
        if not specific:
            return Score(0, ["CPV nur IT-nah, kein fachliches Stichwort"], excluded=True)
        pts += 4
    elif not specific:
        return Score(0, ["kein IT-CPV und kein fachliches Stichwort"], excluded=True)
    else:
        pts -= 5
        reasons.append("CPV nicht IT")

    # 4. Verfahren / Regime
    proc = (notice.procedure or "").lower()
    if notice.regime == "UVgO" or any(k in proc for k in ("direct award", "direktauftrag", "negotiated award", "verhandlungsvergabe", "public announcement", "öffentliche ausschreibung", "beschränkte")):
        pts += 22
        reasons.append("nationales Verfahren (UVgO)")
    elif notice.regime == "VgV" or any(k in proc for k in ("open", "offenes verfahren", "restricted", "competitive")):
        pts -= 12
        reasons.append("EU-Verfahren")
    if "teilnahmewettbewerb" in proc or "participation competition" in proc or "tnw" in proc:
        pts += 3

    # 5. Auftragswert (Platzhalter wie 1 € oder 120 € gelten als unbekannt)
    v = notice.value if (notice.value is not None and notice.value >= 1000) else None
    if v is None:
        reasons.append("Wert unbekannt")
    elif v <= 50000:
        pts += 20
        reasons.append("Wert ≤ 50k (Direktauftragsbereich)")
    elif v <= 100000:
        pts += 14
        reasons.append("Wert ≤ 100k")
    elif v <= p.max_wert:
        pts += 6
        reasons.append("Wert unter EU-Schwelle")
    elif v <= 3 * p.max_wert:
        pts -= 20
        reasons.append("Wert über EU-Schwelle")
    else:
        pts -= 40
        reasons.append("Wert weit über EU-Schwelle")
    if v is not None and p.umsatz and v > 2 * float(p.umsatz) and v > p.max_wert:
        reasons.append("Mindestumsatz wahrscheinlich problematisch")

    # 6. Weiche Ausschlüsse
    soft = [w for w in p.weich if _count(full, w)]
    if soft:
        pts -= min(len(soft), 4) * 7
        reasons.append("Abzug: " + ", ".join(soft[:4]))

    # 7. Region
    for prefix, bonus in p.region_bonus.items():
        if (notice.region or "").startswith(prefix):
            pts += int(bonus)
            reasons.append(f"Region {prefix} +{bonus}")
            break

    pts = max(0, min(100, pts))
    return Score(pts, reasons)
