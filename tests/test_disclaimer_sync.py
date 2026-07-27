"""The legal notice must actually be reachable, and must say the same things
everywhere it appears.

Both user-facing surfaces mirror docs/disclaimer.md (the source of record).
Copy drift here is a legal exposure, not a cosmetic bug — if someone trims the
liability clause out of one surface, this fails.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CANON = REPO / "docs" / "disclaimer.md"
PWA = REPO / "pwa" / "src" / "components" / "Disclaimer.tsx"
ADMIN = REPO / "ingestion" / "src" / "ingestion" / "admin.html"

# Every surface must carry each of these. Kept deliberately short so wording can
# be improved without breaking the test — but a missing CLAUSE breaks it.
REQUIRED = (
    "not financial",
    "not licensed by the Philippine Insurance Commission",
    "licensed insurance agent",
    "as is",
    "not liable",
    "policy contract prevails",
)


def normalized(path: Path) -> str:
    """Text with markup/entities flattened, so a clause split across tags or
    written with &mdash;/&ldquo; still matches."""
    text = path.read_text()
    text = re.sub(r"<[^>]+>", " ", text)  # tags
    text = text.replace("&mdash;", "—").replace("&ldquo;", '"').replace("&rdquo;", '"')
    text = text.replace("{\" \"}", " ")  # JSX spacing expressions
    return re.sub(r"\s+", " ", text).lower()


def test_canonical_document_lists_every_required_clause() -> None:
    canon = normalized(CANON)
    for phrase in REQUIRED:
        assert phrase.lower() in canon, phrase


def test_pwa_disclaimer_carries_every_clause() -> None:
    text = normalized(PWA)
    for phrase in REQUIRED:
        assert phrase.lower() in text, f"PWA disclaimer is missing: {phrase}"


def test_reviewer_portal_disclaimer_carries_every_clause() -> None:
    text = normalized(ADMIN)
    for phrase in REQUIRED:
        assert phrase.lower() in text, f"admin.html disclaimer is missing: {phrase}"


def test_disclaimer_is_reachable_from_both_surfaces() -> None:
    # A notice nobody can open protects nobody.
    assert 'className="disclaimer-link"' in PWA.read_text()
    assert "<Disclaimer />" in (REPO / "pwa" / "src" / "App.tsx").read_text()
    admin = ADMIN.read_text()
    assert "getElementById('disclaimer').showModal()" in admin
    assert 'id="disclaimer"' in admin


def test_no_surface_claims_to_be_licensed() -> None:
    # The operator is not a licensed intermediary; the UI must never imply it.
    # (A "Licensed" badge used to sit in the PWA header.)
    for path in (PWA, ADMIN, REPO / "pwa" / "src" / "App.tsx",
                 REPO / "pwa" / "src" / "components" / "Intake.tsx"):
        text = normalized(path)
        assert ">licensed<" not in text
        assert "we are licensed" not in text
        # "licensed insurance agent" (go see one) and "not licensed" are fine;
        # a bare claim like "licensed insurers" implying brokerage is not.
        assert "match you with licensed" not in text
