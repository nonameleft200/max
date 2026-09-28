from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Profile:
    raw: dict
    tage_zurueck: int = 14
    radar_tage: int = 90
    cpv_prefixe: list[str] = field(default_factory=list)
    cpv_nah: list[str] = field(default_factory=list)
    nrw_cpv_codes: list[str] = field(default_factory=list)
    nrw_suchbegriffe: list[str] = field(default_factory=list)
    mindest_score: int = 35
    max_wert: float = 216000.0
    stark: list[str] = field(default_factory=list)
    mittel: list[str] = field(default_factory=list)
    schwach: list[str] = field(default_factory=list)
    hart: list[str] = field(default_factory=list)
    weich: list[str] = field(default_factory=list)
    region_bonus: dict[str, int] = field(default_factory=dict)
    gruendungsjahr: int | None = None
    umsatz: float | None = None

    @classmethod
    def load(cls, path: str | Path) -> "Profile":
        raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        s = raw.get("suche", {})
        k = raw.get("schluesselwoerter", {})
        a = raw.get("ausschluss", {})
        u = raw.get("unternehmen", {})
        return cls(
            raw=raw,
            tage_zurueck=int(s.get("tage_zurueck", 14)),
            radar_tage=int(s.get("radar_tage", 90)),
            cpv_prefixe=list(s.get("cpv_prefixe", [])),
            cpv_nah=list(s.get("cpv_nah", [])),
            nrw_cpv_codes=list(s.get("nrw_cpv_codes", [])),
            nrw_suchbegriffe=list(s.get("nrw_suchbegriffe", [])),
            mindest_score=int(s.get("mindest_score", 35)),
            max_wert=float(s.get("max_wert", 216000)),
            stark=list(k.get("stark", [])),
            mittel=list(k.get("mittel", [])),
            schwach=list(k.get("schwach", [])),
            hart=list(a.get("hart", [])),
            weich=list(a.get("weich", [])),
            region_bonus=dict(raw.get("regionen", {}).get("bonus", {})),
            gruendungsjahr=u.get("gruendungsjahr"),
            umsatz=u.get("umsatz_letztes_jahr"),
        )
