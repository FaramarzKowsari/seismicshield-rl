from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANUSCRIPT = ROOT / "paper" / "softwarex_manuscript.md"


def _section(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_softwarex_required_top_level_sections_are_present_in_order():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    headings = [
        "## 1. Motivation and significance",
        "## 2. Software description",
        "## 3. Illustrative examples",
        "## 4. Impact",
        "## 5. Conclusions",
    ]
    positions = [text.index(heading) for heading in headings]
    assert positions == sorted(positions)


def test_softwarex_abstract_and_keyword_limits():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    abstract = _section(text, "## Abstract", "**Keywords:**")
    words = re.findall(r"\b[\w’-]+\b", abstract, flags=re.UNICODE)
    assert 80 <= len(words) <= 120

    keyword_line = text.split("**Keywords:**", 1)[1].splitlines()[0]
    keywords = [item.strip() for item in keyword_line.split(";") if item.strip()]
    assert len(keywords) == 6


def test_softwarex_main_body_stays_below_word_limit():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    body = _section(text, "## 1. Motivation and significance", "## Acknowledgements")
    words = re.findall(r"\b[\w’-]+\b", body, flags=re.UNICODE)
    assert len(words) < 3000


def test_softwarex_code_metadata_matches_publication_package():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    assert "| C1 | Current code version | v0.8.3 |" in text
    assert "10.5281/zenodo.22067278" in text
    assert "10.5281/zenodo.22067277" in text
    assert "10.17605/OSF.IO/64DTX" in text
    assert "MIT License" in text


def test_softwarex_manuscript_preserves_confirmatory_boundary():
    text = MANUSCRIPT.read_text(encoding="utf-8")
    assert "confirmatory_data_used = false" in text
    assert "paper_level_efficacy_claim = false" in text
    assert "no evidence that any included optimization method is superior" in text
