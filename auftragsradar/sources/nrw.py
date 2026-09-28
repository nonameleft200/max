"""Quelle: Vergabemarktplatz NRW (evergabe.nrw.de, cosinex).

Keine offizielle API. Die Web-Suche lädt ihre Liste per JSON von
  POST /VMPCenter/api/v2/project/search
und braucht dafür einen Session-Token (X-JWT), der erst beim zweiten Aufruf der
Suchseite innerhalb derselben Session im HTML steht. Bitte fair nutzen: wenige Anfragen, Pausen.
"""
from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime

import requests

from ..models import Notice

log = logging.getLogger(__name__)

BASE = "https://www.evergabe.nrw.de"
PAGE = BASE + "/VMPCenter/company/announcements/categoryOverview.do?method=showCategoryOverview"
SEARCH = BASE + "/VMPCenter/api/v2/project/search"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 auftragsradar/0.1"
_TOKEN_RE = re.compile(r'id="token" value="([^"]*)"')


class NrwClient:
    def __init__(self, pause: float = 0.8):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = UA
        self.token = ""
        self.pause = pause

    def _login(self) -> None:
        for _ in range(3):
            r = self.s.get(PAGE, timeout=60)
            m = _TOKEN_RE.search(r.text)
            if m and m.group(1):
                self.token = m.group(1)
                return
            time.sleep(self.pause)
        raise RuntimeError("NRW: kein Such-Token erhalten")

    def search(self, *, cpv: str | None = None, text: str = "", publication_types=("Tender",),
               rules=("VOL",), max_pages: int = 10) -> list[dict]:
        if not self.token:
            self._login()
        rows: list[dict] = []
        page = 1
        while page <= max_pages:
            payload = {
                "cpvCodes": [{"code": cpv}] if cpv else [],
                "contractingRules": list(rules),
                "publicationTypes": list(publication_types),
                "location": {},
                "pageNumber": page,
                "searchText": text,
                "sort": {"order": [{"property": "PROJECT_PUBLICATION_DATE_LNG", "direction": "DESC"}]},
            }
            r = self.s.post(SEARCH, json=payload, timeout=60, headers={
                "Accept": "application/json", "X-JWT": self.token,
                "Content-Type": "application/json; charset=utf-8"})
            if r.status_code == 403:
                self.token = ""
                self._login()
                continue
            if r.status_code != 200:
                log.warning("NRW Suche HTTP %s: %s", r.status_code, r.text[:200])
                break
            d = r.json()
            rows.extend(d.get("projects") or [])
            if page >= int(d.get("allPages") or 1):
                break
            page += 1
            time.sleep(self.pause)
        return rows

    def detail(self, url: str) -> dict:
        """Liest VO, Vergabeart, CPV und Abgabefrist von der öffentlichen Projektseite."""
        try:
            r = self.s.get(url, timeout=60, allow_redirects=True)
        except requests.RequestException:
            return {}
        if r.status_code != 200:
            return {}
        t = re.sub(r"<script.*?</script>", "", r.text, flags=re.S)
        t = html.unescape(re.sub(r"<[^>]+>", "\n", t))
        lines = [l.strip() for l in t.split("\n") if l.strip()]
        out: dict = {"final_url": r.url}
        for i, l in enumerate(lines[:-2]):
            if l == "VO:":
                out["regime"] = lines[i + 1]
            elif l == "Vergabeart:":
                out["procedure"] = lines[i + 1]
            elif l == "Abgabefrist":
                out["deadline"] = _iso(lines[i + 1])
            elif l == "Auftragsgegenstand":
                codes = [x for x in lines[i + 1:i + 8] if re.fullmatch(r"\d{8}-\d", x)]
                out["cpv"] = codes
                out["cpv_text"] = " ".join(x for x in lines[i + 1:i + 4] if not re.fullmatch(r"\d{8}-\d", x))[:200]
        return out


def _iso(s: str) -> str:
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", s or "")
    return f"{m.group(3)}-{m.group(2)}-{m.group(1)}" if m else ""


def _clean(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def row_to_notice(row: dict, kind: str) -> Notice:
    pid = str(row.get("projectId"))
    rule = _clean(row.get("contractingRule") or "")
    return Notice(
        id=f"nrw:{pid}",
        source="nrw",
        kind=kind,
        title=_clean(row.get("title") or ""),
        buyer=_clean(row.get("organisationName") or ""),
        region="DEA",
        procedure=_clean(row.get("publicationType") or ""),
        regime="UVgO" if "UVgO" in rule else ("VgV" if "VgV" in rule else rule),
        published=_iso(row.get("publishingDate") or ""),
        deadline=_iso(row.get("relevantDate") or "") if kind == "tender" else "",
        url=((row.get("links") or {}).get("enterprojectroom") or
             f"{BASE}/VMPCenter/public/company/projectForwarding.do?pid={pid}"),
        raw_id=pid,
    )


def fetch(cpv_codes: list[str], search_terms: list[str], since: str = "",
          include_expost: bool = True, since_awards: str = "") -> list[Notice]:
    """Sucht Ausschreibungen (und optional Ex-post-Vergaben) nach CPV-Codes und Stichworten; dedupliziert."""
    c = NrwClient()
    seen: dict[str, Notice] = {}

    def add(rows: list[dict], kind: str, cpv: str = "") -> None:
        cutoff = since_awards if kind == "award" else since
        for r in rows:
            n = row_to_notice(r, kind)
            if cutoff and n.published and n.published < cutoff:
                continue
            if cpv:
                n.cpv = [cpv]  # der Suchlauf kennt den CPV-Code, die Liste selbst nicht
            seen.setdefault(n.id, n)

    for code in cpv_codes:
        add(c.search(cpv=code), "tender", cpv=code)
        time.sleep(c.pause)
    for term in search_terms:
        # Die Volltextsuche des Marktplatzes ist unscharf; kurze Begriffe liefern Rauschen.
        if len(term) >= 6:
            add(c.search(text=term, max_pages=3), "tender")
            time.sleep(c.pause)
    if include_expost:
        for code in cpv_codes:
            add(c.search(cpv=code, publication_types=("ExPost",), max_pages=5), "award", cpv=code)
            time.sleep(c.pause)
    log.info("NRW: %d eindeutige Einträge", len(seen))
    return list(seen.values())


def enrich(notice: Notice, client: NrwClient | None = None) -> Notice:
    c = client or NrwClient()
    d = c.detail(notice.url)
    if d.get("cpv"):
        notice.cpv = d["cpv"]
    if d.get("procedure"):
        notice.procedure = d["procedure"]
    if d.get("regime"):
        notice.regime = d["regime"]
    if d.get("deadline") and not notice.deadline:
        notice.deadline = d["deadline"]
    if d.get("cpv_text") and not notice.description:
        notice.description = d["cpv_text"]
    if d.get("final_url"):
        notice.url = d["final_url"].split(";jsessionid")[0]
    return notice
