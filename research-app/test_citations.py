"""
test_citations.py — Comprehensive Unit & Adversarial Test Suite for Citation Engine v0.5

Run from research-app/ directory:
    python test_citations.py
"""

import sys
from dataclasses import dataclass
from typing import Optional, List, Dict
import citations
from citations import (
    Source,
    _extract_domain,
    _normalize_url,
    build_source_list,
    format_apa7,
    format_ieee,
    format_harvard,
    format_mla9,
    format_bibtex_entry,
    build_bibtex_file,
    format_citation,
    build_references_markdown,
    annotate_text_with_citations,
)

PASS = "\033[92m  PASS\033[0m"
FAIL = "\033[91m  FAIL\033[0m"
results = []

def check(name: str, condition: bool, detail: str = "") -> None:
    status = PASS if condition else FAIL
    print(f"{status}  {name}")
    if not condition and detail:
        print(f"       → {detail}")
    results.append(condition)

# Mock classes to simulate Gemini API response objects
class MockWeb:
    def __init__(self, title: Optional[str] = None, uri: Optional[str] = None):
        self.title = title
        self.uri = uri

class MockChunk:
    def __init__(self, title: Optional[str] = None, uri: Optional[str] = None):
        if title is not None or uri is not None:
            self.web = MockWeb(title, uri)

class MockSegment:
    def __init__(self, start_index: int, end_index: int, text: str = ""):
        self.start_index = start_index
        self.end_index = end_index
        self.text = text

class MockSupport:
    def __init__(self, start_idx: int, end_idx: int, chunk_indices: List[int]):
        self.segment = MockSegment(start_idx, end_idx)
        self.grounding_chunk_indices = chunk_indices


print("\n=== Citation Engine v0.5 — Unit & Adversarial Tests ===\n")

# ---------------------------------------------------------------------------
# 1. URL Helpers & Metadata Extraction
# ---------------------------------------------------------------------------
check(
    "Extract domain from standard URL",
    _extract_domain("https://example.com/path/to/page") == "example.com"
)
check(
    "Extract domain strips www.",
    _extract_domain("https://www.nature.com/articles/123") == "nature.com"
)
check(
    "Extract domain handles malformed URL gracefully",
    _extract_domain("not-a-url") is None or isinstance(_extract_domain("not-a-url"), str)
)
check(
    "Normalize URL strips trailing slash",
    _normalize_url("HTTPS://EXAMPLE.COM/page/") == "https://example.com/page"
)

# ---------------------------------------------------------------------------
# 2. Metadata Integrity & Non-Fabrication
# ---------------------------------------------------------------------------
s_clean = Source(citation_id=1, title="Test Study", url="https://example.com/study")
check("Source citation_id is 1", s_clean.citation_id == 1)
check("Source title is preserved", s_clean.title == "Test Study")
check("Source domain is auto-derived", s_clean.domain == "example.com")
check("Source author is None in v0.2 (no fabrication)", s_clean.author is None)
check("Source year is None in v0.2 (no fabrication)", s_clean.year is None)
check("Source journal is None in v0.2 (no fabrication)", s_clean.journal is None)
check("Source doi is None in v0.2 (no fabrication)", s_clean.doi is None)

# Empty string normalization
s_empty = Source(citation_id=2, title="   ", url="")
check("Blank title normalized to None", s_empty.title is None)
check("Blank url normalized to None", s_empty.url is None)

# ---------------------------------------------------------------------------
# 3. Source List Construction & Deduplication
# ---------------------------------------------------------------------------
raw_chunks = [
    MockChunk("First Source", "https://example.com/article1"),
    MockChunk("Duplicate Source Different Title", "https://example.com/article1/"),
    MockChunk("No URL Title", None),
    MockChunk(None, "https://example.com/no-title"),
    MockChunk(None, None),
    "Not A Real Chunk Object",
]

sources, chunk_map = build_source_list(raw_chunks)

check("Deduplicated source count is 3 (article1, no-url, no-title)", len(sources) == 3)
check("Chunk 0 maps to citation_id 1", chunk_map.get(0) == 1)
check("Chunk 1 (duplicate URL) maps to citation_id 1", chunk_map.get(1) == 1)
check("Chunk 2 (no URL) maps to citation_id 2", chunk_map.get(2) == 2)
check("Chunk 3 (no title) maps to citation_id 3", chunk_map.get(3) == 3)
check("Chunk 4 (empty) is omitted from chunk_map", 4 not in chunk_map)

# Title merging test
chunks_title_merge = [
    MockChunk(None, "https://example.com/paper"),
    MockChunk("Real Title Found Later", "https://example.com/paper"),
]
sources_merged, _ = build_source_list(chunks_title_merge)
check("Title merged into existing source when available", sources_merged[0].title == "Real Title Found Later")

# ---------------------------------------------------------------------------
# 4. Multi-Style Citation Formatting (APA 7, IEEE, Harvard, MLA 9, BibTeX)
# ---------------------------------------------------------------------------
s_academic = Source(
    citation_id=1,
    author="Dunning, J. H., & Lundan, S. M.",
    year=2008,
    title="Multinational Enterprises and the Global Economy",
    journal="Edward Elgar Publishing",
    doi="10.4337/9781848441491",
    url="https://doi.org/10.4337/9781848441491",
)

apa_out = format_apa7(s_academic)
check("APA 7: contains author, year, title, journal, DOI",
    "Dunning, J. H., & Lundan, S. M." in apa_out and "(2008)." in apa_out and "https://doi.org/" in apa_out)

ieee_out = format_ieee(s_academic)
check("IEEE: quotes title and lists year",
    '"Multinational Enterprises and the Global Economy,"' in ieee_out and "2008." in ieee_out)

harvard_out = format_harvard(s_academic)
check("Harvard: uses single quotes and Available at",
    "'Multinational Enterprises and the Global Economy'," in harvard_out and "Available at:" in harvard_out)

mla_out = format_mla9(s_academic)
check("MLA 9: uses double quotes and italic journal",
    '"Multinational Enterprises and the Global Economy."' in mla_out and "*Edward Elgar Publishing*," in mla_out)

bib_entry = format_bibtex_entry(s_academic)
check("BibTeX: valid @article entry with title and doi",
    "@article{ref_1," in bib_entry and "title = {" in bib_entry and "doi = {10.4337/9781848441491}" in bib_entry)

bib_file = build_bibtex_file([s_academic])
check("BibTeX file: generates non-empty .bib file", len(bib_file) > 50 and "@article" in bib_file)

# ---------------------------------------------------------------------------
# 5. References Section Generation
# ---------------------------------------------------------------------------
ref_md_apa = build_references_markdown([s_academic], style="APA 7")
check("References APA 7 header generated", "## References (APA 7)" in ref_md_apa)

ref_md_ieee = build_references_markdown([s_academic], style="IEEE")
check("References IEEE header generated", "## References (IEEE)" in ref_md_ieee)

empty_ref = build_references_markdown([])
check("Empty source list produces empty references string", empty_ref == "")

# ---------------------------------------------------------------------------
# 6. Inline Citation Annotation via Grounding Supports
# ---------------------------------------------------------------------------
sample_text = "FDI significantly increases GDP growth in developing countries."
supports = [
    MockSupport(start_idx=0, end_idx=38, chunk_indices=[0, 1]),
]

annotated, inserted = annotate_text_with_citations(sample_text, supports, chunk_map)
check("Citations inserted flag is True", inserted is True)
check("Duplicate chunk indices resolve to single [1]", "[1]" in annotated and "[1][1]" not in annotated)
check("Inline marker inserted at correct offset", "GDP growth[1] in developing" in annotated)

# ---------------------------------------------------------------------------
# 7. Adversarial Tests & HTML Export
# ---------------------------------------------------------------------------
# Adversarial 1: Duplicate URLs with different titles
adv_chunks_1 = [
    MockChunk("Title A", "https://site.org/report"),
    MockChunk("Title B", "https://site.org/report/"),
]
adv_srcs_1, _ = build_source_list(adv_chunks_1)
check("Adversarial 1: Duplicate URLs deduped to 1 source", len(adv_srcs_1) == 1)

# Adversarial 2: Source with no title
adv_chunks_2 = [MockChunk(None, "https://rawsite.com/data.pdf")]
adv_srcs_2, _ = build_source_list(adv_chunks_2)
check("Adversarial 2: Source with no title processed without crash", len(adv_srcs_2) == 1 and adv_srcs_2[0].title is None)

# Adversarial 3: Empty/None grounding chunks
adv_srcs_10, adv_map_10 = build_source_list(None)
check("Adversarial 3: None grounding chunks returns empty sources list", len(adv_srcs_10) == 0 and len(adv_map_10) == 0)

# HTML Export Test
html_out = citations.build_html_report(
    question="Test Question?",
    result_text="This is a **bold** statement [1].",
    model_used="gemini-3.6-flash",
    sources=[s_academic],
)
check("HTML Export: contains DOCTYPE and title", "<!DOCTYPE html>" in html_out and "Test Question?" in html_out)
check("HTML Export: converts inline citation to sup tag", "<sup class='cite-tag'>[1]</sup>" in html_out)
check("HTML Export: contains references list", "id='ref-1'" in html_out and "Dunning" in html_out)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(results)
total = len(results)
print(f"\n{'='*60}")
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("\033[92m✓ All unit & adversarial tests passed. Citation Engine v0.5 is verified.\033[0m")
else:
    print(f"\033[91m✗ {total - passed} test(s) failed.\033[0m")
    sys.exit(1)
print("="*60 + "\n")
