"""Markdown-Report: neue Treffer, alle offenen Treffer, Behördenradar."""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date


def _eur(v) -> str:
    if v is None:
        return "–"
    return f"{float(v):,.0f} €".replace(",", ".")


def _proc(r: sqlite3.Row) -> str:
    p = (r["procedure"] or "").strip()
    reg = (r["regime"] or "").strip()
    if reg and reg not in p:
        return f"{reg}: {p}" if p else reg
    return p or "–"


def _row(r: sqlite3.Row) -> str:
    title = (r["title"] or "").replace("|", "/").strip()
    if len(title) > 90:
        title = title[:87] + "…"
    src = {"bund": "Bund", "nrw": "NRW"}.get(r["source"], r["source"])
    where = r["locality"] or r["region"] or ""
    return (f"| {r['score']} | {src} | [{title}]({r['url']}) | {(r['buyer'] or '')[:45]} | {where} | "
            f"{_proc(r)[:40]} | {_eur(r['value'])} | {r['deadline'] or '–'} | {(r['reasons'] or '')[:110]} |")


HEADER = ("| Score | Quelle | Titel | Auftraggeber | Ort | Verfahren | Wert | Frist | Gründe |\n"
          "|---|---|---|---|---|---|---|---|---|")


def render(new_rows: list[sqlite3.Row], all_rows: list[sqlite3.Row], award_rows: list[sqlite3.Row],
           stats: dict, min_score: int) -> str:
    today = date.today().isoformat()
    out = [f"# Auftragsradar – {today}", ""]
    out.append(f"Geladen: {stats.get('bund', 0)} Releases Bund, {stats.get('nrw', 0)} Einträge NRW. "
               f"Bewertet: {stats.get('scored', 0)}, davon {stats.get('kept', 0)} über Score {min_score}. "
               f"Neu seit letztem Lauf: {len(new_rows)}.")
    out.append("")
    out.append("Score-Logik: nationales Verfahren (UVgO) +22, Wert ≤ 50k +20, IT-CPV +12, KI-Stichworte bis +55, "
               "NRW +15; Abzüge für EU-Verfahren, Werte über der Schwelle und weiche Ausschlüsse. "
               "Harte Ausschlüsse (ISO 27001, Rechenzentrum, Lizenzen, Hardware …) erscheinen nicht.")
    out.append("")
    out.append(f"## Neue Treffer ({len(new_rows)})")
    out.append("")
    if new_rows:
        out.append(HEADER)
        out.extend(_row(r) for r in new_rows)
    else:
        out.append("Keine neuen Treffer.")
    out.append("")
    out.append(f"## Alle offenen Treffer ({len(all_rows)})")
    out.append("")
    if all_rows:
        out.append(HEADER)
        out.extend(_row(r) for r in all_rows)
    else:
        out.append("Keine Treffer.")
    out.append("")
    out.append("## Behördenradar (Zuschläge für passende Aufträge, Ziel-Liste für Direktansprache)")
    out.append("")
    out.append("Diese Auftraggeber haben zuletzt Aufträge vergeben, die zum Profil passen. "
               "Direktaufträge unter der Wertgrenze werden nicht vorab ausgeschrieben; hier lohnt die Ansprache.")
    out.append("")
    by_buyer: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in award_rows:
        by_buyer[r["buyer"] or "unbekannt"].append(r)
    ranked = sorted(by_buyer.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    if ranked:
        out.append("| Auftraggeber | Ort | Zuschläge | Beispiele (Wert, Auftragnehmer) |")
        out.append("|---|---|---|---|")
        for buyer, rows in ranked[:60]:
            ex = "; ".join(
                f"[{(r['title'] or '')[:50]}]({r['url']}) ({_eur(r['value'])}{', ' + r['supplier'][:30] if r['supplier'] else ''})"
                for r in rows[:3])
            out.append(f"| {buyer[:50]} | {rows[0]['locality'] or rows[0]['region'] or ''} | {len(rows)} | {ex} |")
    else:
        out.append("Keine passenden Zuschläge im Zeitraum.")
    out.append("")
    return "\n".join(out)
