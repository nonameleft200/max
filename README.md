# Auftragsradar

Findet öffentliche KI- und Digitalisierungsaufträge, die für einen Einzelunternehmer ohne
ISO-Zertifizierung realistisch sind, und erzeugt daraus einen täglichen Markdown-Report.

Die Recherche dazu (Rechtsrahmen 2026, was realistisch ist, Datenquellen) steht in
[`docs/01-recherche-was-ist-realistisch.md`](docs/01-recherche-was-ist-realistisch.md).

## Was das Tool macht

1. **Bund laden**: täglicher OCDS-Export des Bekanntmachungsservice (oeffentlichevergabe.de), ohne Login,
   ober- und unterschwellig, Bund + viele Länder und Kommunen.
2. **NRW laden**: Vergabemarktplatz NRW (evergabe.nrw.de) über dessen interne Such-API,
   CPV-basiert, inklusive Ex-post-Vergaben.
3. **Bewerten**: Score 0 bis 100 pro Bekanntmachung. Hoch bei nationalem Verfahren (UVgO), kleinem Wert,
   IT-CPV, KI-Stichworten und NRW. Harte Ausschlüsse (ISO 27001, Rechenzentrum, Hardware, Lizenzen …) fliegen raus.
4. **Anreichern**: für Treffer über der Schwelle Frist und Wert (Bund, eForms-XML) bzw. CPV, Vergabeart, Frist (NRW).
5. **Report**: `reports/JJJJ-MM-TT.md` und `reports/latest.md` mit neuen Treffern, allen offenen Treffern und dem
   **Behördenradar** (Auftraggeber, die zuletzt passende Aufträge vergeben haben, als Ziel-Liste für Direktansprache).

## Benutzen

```bash
pip install -r requirements.txt
python -m auftragsradar -v            # voller Lauf, Report unter reports/
python -m auftragsradar --skip-nrw    # nur Bund
python -m auftragsradar --skip-enrich # ohne Detailabfragen (schneller)
python -m pytest tests                # Tests
```

Das Profil (`profile.toml`) steuert alles: Region, Stichworte, Ausschlüsse, Schwellen. Anpassen und neu laufen lassen.
Die SQLite-Datenbank unter `data/` merkt sich gesehene Bekanntmachungen, damit der nächste Lauf nur Neues meldet.

## Automatisch

`.github/workflows/radar.yml` läuft werktags morgens, schreibt den Report nach `reports/` und committet ihn.
Manuell starten: Actions → Auftragsradar → Run workflow.

## Grenzen

- Direktaufträge unter der Wertgrenze werden nirgends vorab veröffentlicht. Dafür gibt es das Behördenradar.
- Der Bund-Export kennt bei den meisten unterschwelligen Vergaben keinen Auftragswert.
- Der NRW-Marktplatz liefert in der Liste nur Titel, Auftraggeber und Fristen. CPV kommt aus dem Suchlauf,
  Details werden nur für gute Treffer nachgeladen. Bitte sparsam abfragen.
- Weitere Landesportale (Bayern, BW, Hessen) sind noch nicht angebunden.
