"""Tests for documentation completeness and structure."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
DOCS_DIR = REPO_ROOT / "docs"

# Markdown inline link: [text](target). We only care about links whose target
# points at a local Markdown file (ends in .md, optionally with a #anchor).
_MD_LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Per-decision ADR files live one-per-file in docs/ (and docs/archive/) and each
# carries exactly one "## Decision N: ..." heading plus a metadata block. The
# aggregate decision log (02) and narrative docs are intentionally excluded.
_DECISION_HEADING = re.compile(r"^##\s+Decision\s+\d+\b", re.MULTILINE)

# Current operating scale of the platform. The 826 figure is the historical
# launch-era baseline and must not be presented as current state in the README.
EXPECTED_REPO_COUNT = 1898
STALE_REPO_COUNT = 826


def _markdown_files():
    """All tracked Markdown files: README + everything under docs/ (recursive)."""
    files = [REPO_ROOT / "README.md"]
    files.extend(sorted(DOCS_DIR.rglob("*.md")))
    return files


def _adr_files():
    """Per-decision ADR files: any doc containing a '## Decision N:' heading.

    These are the standalone decision records (docs/10..16 and docs/archive/*).
    The aggregate decision log uses '## Decision N: Title' headings too, so it
    is filtered out explicitly by filename.
    """
    adrs = []
    for path in sorted(DOCS_DIR.rglob("*.md")):
        if path.name == "02-decision-log.md":
            continue
        text = path.read_text(encoding="utf-8")
        if _DECISION_HEADING.search(text):
            adrs.append(path)
    return adrs


def _platform_glance_block(readme: str) -> str:
    """Return the text of the README 'Platform at a Glance' section."""
    marker = "## Platform at a Glance"
    start = readme.index(marker)
    rest = readme[start + len(marker):]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def _metadata_value(text: str, key: str):
    """Return the value of a 'Key: value' metadata line, or None if absent.

    Tolerates the common Markdown emphasis form ('**Key:** value'), leading
    blockquote / list markers, and surrounding emphasis on the value itself.
    """
    pattern = rf"(?im)^\s*[*_>\- ]*{re.escape(key)}\s*[*_]*\s*:\s*(.+?)\s*$"
    m = re.search(pattern, text)
    if m is None:
        return None
    return m.group(1).strip().strip("*_` ").strip()

EXPECTED_DOCS = [
    "01-platform-overview.md",
    "02-decision-log.md",
    "03-cap-theorem.md",
    "04-scale-analysis.md",
    "05-tradeoffs.md",
    "06-working-with-engineers.md",
    "07-diagrams.md",
    "08-demo-guide.md",
    "09-navigating-ambiguity.md",
]


def test_all_doc_files_exist():
    """Every expected documentation file must exist in docs/."""
    docs_dir = REPO_ROOT / "docs"
    for filename in EXPECTED_DOCS:
        path = docs_dir / filename
        assert path.exists(), f"Missing doc file: {filename}"


def test_all_doc_files_are_nonempty():
    """Every doc file must have content."""
    docs_dir = REPO_ROOT / "docs"
    for filename in EXPECTED_DOCS:
        path = docs_dir / filename
        assert path.stat().st_size > 100, f"Doc file is too small: {filename}"


def test_readme_exists():
    """README.md must exist at repo root."""
    assert (REPO_ROOT / "README.md").exists()


def test_readme_has_live_stats_section():
    """README must contain a Live Stats section."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert "## Live Stats" in readme, "README missing '## Live Stats' section"


def test_readme_has_documentation_table():
    """README must link to all doc files."""
    readme = (REPO_ROOT / "README.md").read_text()
    assert "## Documentation" in readme, "README missing '## Documentation' section"
    for filename in EXPECTED_DOCS:
        assert filename in readme, f"README missing link to {filename}"


def test_diagrams_doc_has_mermaid_blocks():
    """The diagrams doc must contain Mermaid code blocks."""
    diagrams = (REPO_ROOT / "docs" / "07-diagrams.md").read_text()
    mermaid_count = diagrams.count("```mermaid")
    assert mermaid_count >= 5, f"Expected at least 5 Mermaid blocks, found {mermaid_count}"


def test_decision_log_has_nine_decisions():
    """The decision log must document all 9 decisions."""
    decision_log = (REPO_ROOT / "docs" / "02-decision-log.md").read_text()
    for i in range(1, 10):
        assert f"## Decision {i}" in decision_log, f"Missing Decision {i}"


# ---------------------------------------------------------------------------
# Doc-lint: no dead internal links
# ---------------------------------------------------------------------------


def test_no_dead_internal_markdown_links():
    """Every internal [text](*.md) link must resolve to a file on disk.

    Anchors (#section) and query strings are stripped; only the file portion is
    checked. External links (http/https/mailto) are ignored.
    """
    broken = []
    for md_file in _markdown_files():
        text = md_file.read_text(encoding="utf-8")
        for target in _MD_LINK.findall(text):
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            # Strip anchor / query suffix; we only resolve the file path.
            file_part = re.split(r"[#?]", target, maxsplit=1)[0]
            if not file_part.endswith(".md"):
                continue
            resolved = (md_file.parent / file_part).resolve()
            if not resolved.exists():
                broken.append(f"{md_file.name} -> {target}")
    assert not broken, "Dead internal links found: " + "; ".join(broken)


# ---------------------------------------------------------------------------
# Doc-lint: every Decision (ADR) carries Status / Date / KAN metadata
# ---------------------------------------------------------------------------


def test_decision_files_discovered():
    """Sanity guard: the ADR discovery must actually find the per-decision docs.

    Without this, an over-eager filter could silently make the metadata checks
    below vacuous (passing because they iterate over an empty list).
    """
    adrs = _adr_files()
    assert len(adrs) >= 7, f"Expected at least 7 ADR files, found {len(adrs)}: {[p.name for p in adrs]}"


def test_every_decision_has_status_date_kan_headers():
    """Each per-decision ADR must declare Status, Date, and a KAN tracking ref."""
    missing = []
    for adr in _adr_files():
        text = adr.read_text(encoding="utf-8")
        if _metadata_value(text, "Status") is None:
            missing.append(f"{adr.name}: missing Status")
        if _metadata_value(text, "Date") is None:
            missing.append(f"{adr.name}: missing Date")
        if not re.search(r"KAN-\d+", text):
            missing.append(f"{adr.name}: missing KAN reference")
    assert not missing, "ADR metadata gaps: " + "; ".join(missing)


def test_decision_dates_are_iso_format():
    """The Date header of each ADR must be an ISO YYYY-MM-DD value."""
    bad = []
    for adr in _adr_files():
        text = adr.read_text(encoding="utf-8")
        value = _metadata_value(text, "Date")
        assert value is not None, f"{adr.name}: no Date header to validate"
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            bad.append(f"{adr.name}: '{value}'")
    assert not bad, "Non-ISO ADR dates: " + "; ".join(bad)


def test_archived_decisions_are_marked():
    """Any ADR living under docs/archive/ must be explicitly marked ARCHIVED.

    The archive marker prevents a retired decision from being read as current
    architecture.
    """
    archive_dir = DOCS_DIR / "archive"
    if not archive_dir.exists():
        return
    unmarked = []
    for adr in sorted(archive_dir.rglob("*.md")):
        text = adr.read_text(encoding="utf-8")
        if "ARCHIVED" not in text:
            unmarked.append(adr.name)
        elif (_metadata_value(text, "Status") or "").lower() != "archived":
            unmarked.append(f"{adr.name} (no 'Status: Archived')")
    assert not unmarked, "Archived ADRs not marked: " + "; ".join(unmarked)


# ---------------------------------------------------------------------------
# Doc-lint: README repo count is current, not the stale 826 baseline
# ---------------------------------------------------------------------------


def test_platform_at_a_glance_uses_current_repo_count():
    """The 'Platform at a Glance' diagram must show the current repo count."""
    readme = (REPO_ROOT / "README.md").read_text()
    glance = _platform_glance_block(readme)
    assert str(EXPECTED_REPO_COUNT) in glance.replace(",", ""), (
        f"'Platform at a Glance' must reference current repo count {EXPECTED_REPO_COUNT}"
    )
    assert f"({STALE_REPO_COUNT} repos)" not in glance, (
        f"'Platform at a Glance' still shows the stale '({STALE_REPO_COUNT} repos)' baseline"
    )


def test_live_stats_repo_count_matches_glance():
    """README 'Live Stats' repos-tracked value must equal the glance count.

    Both are current-state claims; they must not drift apart.
    """
    readme = (REPO_ROOT / "README.md").read_text()
    m = re.search(r"\|\s*Repos tracked\s*\|\s*([\d,]+)", readme)
    assert m is not None, "README Live Stats missing 'Repos tracked' row"
    value = int(m.group(1).replace(",", ""))
    assert value == EXPECTED_REPO_COUNT, (
        f"Live Stats repos tracked is {value}, expected {EXPECTED_REPO_COUNT}"
    )
    assert value != STALE_REPO_COUNT, "Live Stats still reports the stale 826 baseline"
