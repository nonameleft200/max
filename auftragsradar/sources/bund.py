"""Quelle: Bekanntmachungsservice des Bundes (oeffentlichevergabe.de), OCDS-Export.

Offene Schnittstelle ohne Login, Lizenz CC0:
  GET https://oeffentlichevergabe.de/api/notice-exports?pubDay=YYYY-MM-DD&format=ocds.zip
Enthält ober- und unterschwellige Bekanntmachungen von Bund, vielen Ländern und Kommunen (eForms-DE).
"""
from __future__ import annotations

import html
import json
import logging
import re
import zipfile
from datetime import date, timedelta
from pathlib import Path

import requests

from ..models import Notice

log = logging.getLogger(__name__)

BASE = "https://oeffentlichevergabe.de"
EXPORT = BASE + "/api/notice-exports"
NOTICE_UI = BASE + "/ui/de/notices/{id}"
NOTICE_XML = BASE + "/api/notices/{id}"

# procurementMethodDetails-Werte, die auf nationale (unterschwellige) Verfahren hindeuten
NATIONAL = {
    "public announcement",              # Öffentliche Ausschreibung (UVgO)
    "restricted tender",                # Beschränkte Ausschreibung
    "restricted tender with public participation competition",
    "negotiated award",                 # Verhandlungsvergabe
    "negotiated award with public participation competition",
    "negotiated award without public participation competition",
    "direct award",                     # Direktauftrag
    "direct award with public participation competition",
    "negotiated without prior call for competition",
}
EU = {"open", "restricted", "competitive dialogue", "innovation partnership",
      "negotiated with prior publication of a call for competition / competitive with negotiation"}


def _days(days_back: int, today: date | None = None) -> list[date]:
    today = today or date.today()
    return [today - timedelta(days=i) for i in range(days_back)]


def download_day(day: date, cache_dir: Path, session: requests.Session | None = None) -> Path | None:
    """Lädt den Tages-Export als ZIP in den Cache (überspringt vorhandene Dateien außer für heute)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    target = cache_dir / f"{day.isoformat()}.zip"
    if target.exists() and day != date.today() and target.stat().st_size > 0:
        return target
    s = session or requests.Session()
    r = s.get(EXPORT, params={"pubDay": day.isoformat(), "format": "ocds.zip"}, timeout=180)
    if r.status_code != 200 or not r.content:
        # Der laufende Tag ist erst am Folgetag abrufbar (HTTP 400), das ist kein Fehler.
        log.log(logging.INFO if day == date.today() else logging.WARNING, "Bund-Export %s: HTTP %s", day, r.status_code)
        return None
    target.write_bytes(r.content)
    return target


def _region(release: dict) -> tuple[str, str]:
    for p in release.get("parties") or []:
        if "buyer" in (p.get("roles") or []):
            a = p.get("address") or {}
            return a.get("region") or "", a.get("locality") or ""
    return "", ""


def _value(tender: dict) -> float | None:
    v = (tender.get("value") or {}).get("amount")
    if v is not None:
        return float(v)
    total = 0.0
    found = False
    for lot in tender.get("lots") or []:
        lv = (lot.get("value") or {}).get("amount")
        if lv is not None:
            total += float(lv)
            found = True
    return total if found else None


def _cpvs(tender: dict) -> list[str]:
    out: list[str] = []
    for it in tender.get("items") or []:
        c = (it.get("classification") or {}).get("id")
        if c:
            out.append(c)
        for a in it.get("additionalClassifications") or []:
            if a.get("id"):
                out.append(a["id"])
    for lot in tender.get("lots") or []:
        for a in lot.get("additionalClassifications") or []:
            if a.get("id"):
                out.append(a["id"])
    return sorted(set(out))


def _desc(tender: dict) -> str:
    parts = [tender.get("description") or ""]
    for lot in tender.get("lots") or []:
        d = lot.get("description") or ""
        if d and d not in parts:
            parts.append(f"[{lot.get('title') or lot.get('id')}] {d}")
    text = "\n".join(p for p in parts if p)
    return html.unescape(re.sub(r"\n{3,}", "\n\n", text).strip())


def release_to_notice(release: dict) -> Notice | None:
    tender = release.get("tender") or {}
    tags = release.get("tag") or []
    if "award" in tags or release.get("awards"):
        kind = "award"
    elif "tender" in tags:
        kind = "tender"
    elif "planning" in tags:
        kind = "planning"
    else:
        kind = "other"
    pm = (tender.get("procurementMethodDetails") or "").strip()
    pml = pm.lower()
    regime = "UVgO" if pml in NATIONAL else ("VgV" if pml in EU else "")
    region, locality = _region(release)
    nid = str(release.get("id") or "")
    supplier = ""
    award_value = None
    for aw in release.get("awards") or []:
        for s in aw.get("suppliers") or []:
            if s.get("name"):
                supplier = s["name"]
        av = (aw.get("value") or {}).get("amount")
        if av is not None:
            award_value = (award_value or 0.0) + float(av)
    return Notice(
        id=f"bund:{nid}",
        source="bund",
        kind=kind,
        title=html.unescape((tender.get("title") or "").strip()),
        description=_desc(tender),
        buyer=((release.get("buyer") or {}).get("name") or "").strip(),
        region=region,
        locality=locality,
        cpv=_cpvs(tender),
        procedure=pm,
        regime=regime,
        value=award_value if (kind == "award" and award_value is not None) else _value(tender),
        published=(release.get("date") or "")[:10],
        url=NOTICE_UI.format(id=nid),
        supplier=supplier,
        raw_id=nid,
    )


def parse_zip(path: Path) -> list[Notice]:
    out: list[Notice] = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.endswith(".json"):
                continue
            try:
                data = json.loads(z.read(name))
            except Exception as e:  # noqa: BLE001
                log.debug("überspringe %s: %s", name, e)
                continue
            for rel in data.get("releases") or []:
                n = release_to_notice(rel)
                if n and n.title:
                    out.append(n)
    return out


def fetch(days_back: int, cache_dir: Path) -> list[Notice]:
    s = requests.Session()
    notices: list[Notice] = []
    for day in _days(days_back):
        p = download_day(day, cache_dir, s)
        if p:
            got = parse_zip(p)
            log.info("Bund %s: %d Releases", day, len(got))
            notices.extend(got)
    return notices


_DEADLINE_RE = re.compile(
    r"TenderSubmissionDeadlinePeriod>.*?<(?:\w+:)?EndDate>(\d{4}-\d{2}-\d{2})", re.S)
_DEADLINE_ALT = re.compile(r"<(?:\w+:)?EndDate>(\d{4}-\d{2}-\d{2})")
_AMOUNT_RE = re.compile(r"<(?:\w+:)?EstimatedOverallContractAmount[^>]*>([\d.]+)<")


def fetch_details(raw_id: str, session: requests.Session | None = None) -> dict:
    """Holt Angebotsfrist und geschätzten Auftragswert aus dem eForms-XML einer Bekanntmachung."""
    s = session or requests.Session()
    try:
        r = s.get(NOTICE_XML.format(id=raw_id), timeout=30)
    except requests.RequestException:
        return {}
    if r.status_code != 200:
        return {}
    out: dict = {}
    m = _DEADLINE_RE.search(r.text) or _DEADLINE_ALT.search(r.text)
    if m:
        out["deadline"] = m.group(1)
    m = _AMOUNT_RE.search(r.text)
    if m:
        try:
            out["value"] = float(m.group(1))
        except ValueError:
            pass
    return out
