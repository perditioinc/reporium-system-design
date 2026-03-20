"""Tests for documentation completeness and structure."""

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent

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
