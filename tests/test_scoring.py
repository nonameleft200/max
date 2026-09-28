from pathlib import Path

from auftragsradar.config import Profile
from auftragsradar.models import Notice
from auftragsradar.scoring import score, _count

ROOT = Path(__file__).resolve().parent.parent
P = Profile.load(ROOT / "profile.toml")


def n(**kw) -> Notice:
    base = dict(id="t:1", source="bund", kind="tender", title="", description="")
    base.update(kw)
    return Notice(**base)


def test_whole_word_matching():
    assert _count("Jugendberufsagentur Berlin", "Agent") == 0
    assert _count("KI-Agenten für die Verwaltung", "KI") == 1
    assert _count("Werkstudent gesucht", "Studie") == 0
    assert _count("Digitalisierungsstrategie", "Digitalisierung*") == 1
    assert _count("Digitalisierungsstrategie", "Digitalisierung") == 0


def test_ki_uvgo_small_value_scores_high():
    s = score(n(title="KI-Chatbot für das Bürgerbüro", cpv=["72000000-5"], regime="UVgO",
                procedure="Public announcement", value=40000, region="DEA23"), P)
    assert not s.excluded
    assert s.total >= 80


def test_iso27001_is_hard_exclusion():
    s = score(n(title="KI-Plattform", description="Nachweis ISO 27001 erforderlich", cpv=["72000000-5"]), P)
    assert s.excluded


def test_hardware_is_excluded():
    s = score(n(title="Hochleistungsnotebooks für KI-Entwicklung", cpv=["30213100-6"]), P)
    assert s.excluded


def test_generic_consulting_without_it_is_excluded():
    s = score(n(title="Stadtteilentwicklungskonzept", description="Beratung und Studie", cpv=["71400000-2"]), P)
    assert s.excluded


def test_eu_procedure_large_value_scores_low():
    s = score(n(title="KI-Plattform Landesverwaltung", cpv=["72000000-5"], regime="VgV",
                procedure="Open", value=2_500_000), P)
    assert not s.excluded
    assert s.total < P.mindest_score


def test_placeholder_value_is_unknown():
    s = score(n(title="Softwareentwicklung Webanwendung", cpv=["72000000-5"], regime="UVgO",
                procedure="Public announcement", value=1.0), P)
    assert "Wert unbekannt" in str(s)
