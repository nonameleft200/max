from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class Notice:
    """Eine Bekanntmachung, quellenunabhängig normalisiert."""

    id: str                      # quellenpräfixierte, stabile ID (z. B. "bund:25807566")
    source: str                  # "bund" | "nrw"
    kind: str                    # "tender" | "award" | "planning" | "other"
    title: str
    description: str = ""
    buyer: str = ""
    region: str = ""             # NUTS-Code des Auftraggebers, z. B. "DEA22"
    locality: str = ""
    cpv: list[str] = field(default_factory=list)
    procedure: str = ""          # Verfahrensbezeichnung der Quelle
    regime: str = ""             # "UVgO" | "VgV" | "" (unbekannt)
    value: float | None = None   # geschätzter Auftragswert netto
    published: str = ""          # ISO-Datum
    deadline: str = ""           # ISO-Datum, Angebots-/Teilnahmefrist
    url: str = ""
    supplier: str = ""           # nur bei Zuschlägen
    raw_id: str = ""             # ID in der Quelle (für Nachladen von Details)

    def text(self) -> str:
        return f"{self.title}\n{self.description}"

    def to_row(self) -> dict:
        d = asdict(self)
        d["cpv"] = ",".join(self.cpv)
        return d
