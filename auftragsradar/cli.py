from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import requests

from . import __version__
from .config import Profile
from .report import render
from .scoring import score
from .sources import bund, nrw
from .store import Store

log = logging.getLogger("auftragsradar")


def run(args: argparse.Namespace) -> int:
    p = Profile.load(args.profile)
    data = Path(args.data)
    store = Store(data / "radar.db")
    stats: dict[str, int] = {}
    since = (date.today() - timedelta(days=p.tage_zurueck)).isoformat()
    since_awards = (date.today() - timedelta(days=p.radar_tage)).isoformat()

    notices = []
    if not args.skip_bund:
        got = bund.fetch(p.tage_zurueck, data / "cache" / "bund")
        stats["bund"] = len(got)
        notices.extend(got)
    if not args.skip_nrw:
        try:
            got = nrw.fetch(p.nrw_cpv_codes, p.nrw_suchbegriffe, since=since, since_awards=since_awards)
        except Exception as e:  # noqa: BLE001
            log.error("NRW-Quelle fehlgeschlagen: %s", e)
            got = []
        stats["nrw"] = len(got)
        notices.extend(got)

    # Duplikate zwischen Quellen (gleicher Titel + Auftraggeber) zugunsten der Quelle mit mehr Details (Bund) zusammenführen
    seen_keys: dict[tuple[str, str], str] = {}
    kept, new = 0, 0
    for n in sorted(notices, key=lambda x: 0 if x.source == "bund" else 1):
        key = (n.title.strip().lower()[:80], n.buyer.strip().lower()[:40])
        if key in seen_keys and seen_keys[key] != n.id:
            continue
        seen_keys[key] = n.id
        sc = score(n, p)
        stats["scored"] = stats.get("scored", 0) + 1
        if sc.total >= p.mindest_score and not sc.excluded:
            kept += 1
        if store.upsert(n, sc.total, str(sc), sc.excluded):
            new += 1
    stats["kept"] = kept
    store.commit()
    log.info("%d Bekanntmachungen bewertet, %d neu, %d über Schwelle", stats.get("scored", 0), new, kept)

    # Anreicherung nur für aussichtsreiche Treffer: Frist (Bund) bzw. CPV/Vergabeart/Frist (NRW)
    if not args.skip_enrich:
        todo = store.unenriched(p.mindest_score)[: args.enrich_max]
        if todo:
            log.info("reichere %d Treffer an", len(todo))
        s = requests.Session()
        nrw_client = nrw.NrwClient() if any(r["source"] == "nrw" for r in todo) else None
        for r in todo:
            n = _row_to_notice(r)
            if n.source == "bund":
                d = bund.fetch_details(n.raw_id, s)
                n.deadline = n.deadline or d.get("deadline", "")
                if d.get("value") and not n.value:
                    n.value = d["value"]
                    sc = score(n, p)
                    store.db.execute("UPDATE notices SET value=?, score=?, reasons=?, excluded=? WHERE id=?",
                                     (n.value, sc.total, str(sc), int(sc.excluded), n.id))
            elif n.source == "nrw" and nrw_client:
                nrw.enrich(n, nrw_client)
                sc = score(n, p)  # CPV jetzt bekannt → neu bewerten
                store.db.execute("UPDATE notices SET score=?, reasons=?, excluded=? WHERE id=?",
                                 (sc.total, str(sc), int(sc.excluded), n.id))
            store.set_enriched(n)
            time.sleep(0.5)
        store.commit()

    all_rows = [r for r in store.candidates(p.mindest_score) if not r["deadline"] or r["deadline"] >= date.today().isoformat()]
    new_rows = [r for r in all_rows if r["first_seen"] == date.today().isoformat()]
    awards = store.awards(max(10, p.mindest_score - 25))
    text = render(new_rows, all_rows, awards, stats, p.mindest_score)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{date.today().isoformat()}.md"
    target.write_text(text, encoding="utf-8")
    (out_dir / "latest.md").write_text(text, encoding="utf-8")
    print(f"Report: {target}  ({len(all_rows)} Treffer, {len(new_rows)} neu, {len(awards)} Zuschläge im Radar)")
    return 0


def _row_to_notice(r):
    from .models import Notice
    return Notice(
        id=r["id"], source=r["source"], kind=r["kind"], title=r["title"], description=r["description"] or "",
        buyer=r["buyer"] or "", region=r["region"] or "", locality=r["locality"] or "",
        cpv=[c for c in (r["cpv"] or "").split(",") if c], procedure=r["procedure"] or "", regime=r["regime"] or "",
        value=r["value"], published=r["published"] or "", deadline=r["deadline"] or "", url=r["url"] or "",
        supplier=r["supplier"] or "", raw_id=r["raw_id"] or "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="auftragsradar", description="Findet passende öffentliche KI-/Digitalisierungsaufträge.")
    ap.add_argument("--profile", default="profile.toml")
    ap.add_argument("--data", default="data", help="Verzeichnis für Cache und Datenbank")
    ap.add_argument("--out", default="reports", help="Verzeichnis für Markdown-Reports")
    ap.add_argument("--skip-bund", action="store_true")
    ap.add_argument("--skip-nrw", action="store_true")
    ap.add_argument("--skip-enrich", action="store_true", help="keine Detailabfragen (Fristen, CPV) nachladen")
    ap.add_argument("--enrich-max", type=int, default=60, help="max. Detailabfragen pro Lauf")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
    return run(args)
