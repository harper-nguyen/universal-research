"""
test_citations.py — Comprehensive Unit & Adversarial Test Suite for Citation Engine v0.2

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


print("\n=== Citation Engine v0.2 — Unit & Adversarial Tests ===\n")

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
# Multiple sources with duplicates & malformed data
raw_chunks = [
    MockChunk("First Source", "https://example.com/article1"),
    MockChunk("Duplicate Source Different Title", "https://example.com/article1/"),  # duplicate URL
    MockChunk("No URL Title", None),
    MockChunk(None, "https://example.com/no-title"),
    MockChunk(None, None),  # Completely empty chunk
    "Not A Real Chunk Object",  # Malformed object
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
# 4. APA 7 Formatting (Strict Non-Fabrication)
# ---------------------------------------------------------------------------
apa_full_available = format_apa7(Source(1, title="FDI Impact", url="https://imf.org/fdi"))
check("APA 7 output contains title", "FDI Impact." in apa_full_available)
check("APA 7 output contains domain", "imf.org." in apa_full_available)
check("APA 7 output contains URL", "https://imf.org/fdi" in apa_full_available)
check("APA 7 does NOT invent author or year", "(" not in apa_full_available and "et al." not in apa_full_available)

apa_no_url = format_apa7(Source(1, title="Offline Paper Title", url=None))
check("APA 7 output with no URL formats title cleanly", apa_no_url == "Offline Paper Title.")

apa_no_title = format_apa7(Source(1, title=None, url="https://example.com/doc"))
check("APA 7 output with no title uses domain and URL", "example.com." in apa_no_title and "https://example.com/doc" in apa_no_title)

# ---------------------------------------------------------------------------
# 5. References Section Generation
# ---------------------------------------------------------------------------
ref_md = build_references_markdown(sources)
check("References header generated", "## References" in ref_md)
check("References contains [1]", "[1] First Source." in ref_md)
check("References contains [2]", "[2] No URL Title." in ref_md)
check("References contains [3]", "[3] example.com." in ref_md)

empty_ref = build_references_markdown([])
check("Empty source list produces empty references string", empty_ref == "")

# ---------------------------------------------------------------------------
# 6. Inline Citation Annotation via Grounding Supports
# ---------------------------------------------------------------------------
sample_text = "FDI significantly increases GDP growth in developing countries."
# Segment covers "FDI significantly increases GDP growth" (end index 38)
supports = [
    MockSupport(start_idx=0, end_idx=38, chunk_indices=[0, 1]), # chunk 0 & 1 both map to citation 1
]

annotated, inserted = annotate_text_with_citations(sample_text, supports, chunk_map)
check("Citations inserted flag is True", inserted is True)
check("Duplicate chunk indices resolve to single [1]", "[1]" in annotated and "[1][1]" not in annotated)
check("Inline marker inserted at correct offset", "GDP growth[1] in developing" in annotated)

# Multiple citations at different positions
sample_multi = "FDI drives growth. Political risk reduces investment."
supports_multi = [
    MockSupport(start_idx=0, end_idx=18, chunk_indices=[0]),   # "FDI drives growth." -> [1]
    MockSupport(start_idx=19, end_idx=53, chunk_indices=[3]),  # "Political risk reduces investment." -> [3]
]

annotated_m, inserted_m = annotate_text_with_citations(sample_multi, supports_multi, chunk_map)
check("Multiple inline markers placed correctly", "growth.[1]" in annotated_m and "investment.[3]" in annotated_m)


# ---------------------------------------------------------------------------
# 7. Adversarial Tests
# ---------------------------------------------------------------------------

# Adversarial 1: Duplicate URLs with different titles
adv_chunks_1 = [
    MockChunk("Title A", "https://site.org/report"),
    MockChunk("Title B", "https://site.org/report/"),
]
adv_srcs_1, adv_map_1 = build_source_list(adv_chunks_1)
check("Adversarial 1: Duplicate URLs deduped to 1 source", len(adv_srcs_1) == 1)

# Adversarial 2: Source with no title
adv_chunks_2 = [MockChunk(None, "https://rawsite.com/data.pdf")]
adv_srcs_2, _ = build_source_list(adv_chunks_2)
check("Adversarial 2: Source with no title processed without crash", len(adv_srcs_2) == 1 and adv_srcs_2[0].title is None)

# Adversarial 3: Source with title but no URL
adv_chunks_3 = [MockChunk("UNCTAD World Investment Report 2023", None)]
adv_srcs_3, _ = build_source_list(adv_chunks_3)
check("Adversarial 3: Title-only source processed cleanly", len(adv_srcs_3) == 1 and adv_srcs_3[0].url is None)

# Adversarial 4: Malformed / weird URL
adv_chunks_4 = [MockChunk("Odd Link", "ht-tp://bad_url!!")]
adv_srcs_4, _ = build_source_list(adv_chunks_4)
check("Adversarial 4: Malformed URL handled safely", len(adv_srcs_4) == 1)

# Adversarial 5: Metadata attempts to inject suspicious author string (simulated)
s_suspicious = Source(1, title="Test", url="http://test.com", author="Unverified Author")
check("Adversarial 5: Explicit author preserved if set, but format_apa7 shows it", "Unverified Author." in format_apa7(s_suspicious))

# Adversarial 6: Model text mentions paper "Dunning (1988)" but no grounding metadata
s_no_grounding, map_empty = build_source_list([])
ann_no_grounding, ins_no_g = annotate_text_with_citations("According to Dunning (1988), OLI paradigm applies.", None, map_empty)
check("Adversarial 6: Text unchanged when no grounding supports exist", ann_no_grounding == "According to Dunning (1988), OLI paradigm applies.")
check("Adversarial 6: Citations inserted flag is False", ins_no_g is False)

# Adversarial 7: Factual claim with no grounding source
ann_unsupported, ins_unsupported = annotate_text_with_citations("Claim without support.", [], map_empty)
check("Adversarial 7: Unsupported claim is not given fake inline citation", ins_unsupported is False)

# Adversarial 8: Identical titles but different URLs
adv_chunks_8 = [
    MockChunk("FDI Report", "https://siteA.com/fdi"),
    MockChunk("FDI Report", "https://siteB.com/fdi"),
]
adv_srcs_8, _ = build_source_list(adv_chunks_8)
check("Adversarial 8: Identical titles with different URLs kept as separate sources", len(adv_srcs_8) == 2)
check("Adversarial 8: Citation IDs are distinct (1 and 2)", adv_srcs_8[0].citation_id == 1 and adv_srcs_8[1].citation_id == 2)

# Adversarial 9: Source cited multiple times in grounding supports
supports_repeat = [
    MockSupport(start_idx=0, end_idx=10, chunk_indices=[0]),
    MockSupport(start_idx=20, end_idx=30, chunk_indices=[0]),
]
text_repeat = "Sentence 1 is short. Sentence 2 is short."
ann_repeat, _ = annotate_text_with_citations(text_repeat, supports_repeat, chunk_map)
check("Adversarial 9: Source cited multiple times inserts marker at both positions", ann_repeat.count("[1]") == 2)

# Adversarial 10: Empty/None grounding chunks
adv_srcs_10, adv_map_10 = build_source_list(None)
check("Adversarial 10: None grounding chunks returns empty sources list", len(adv_srcs_10) == 0 and len(adv_map_10) == 0)


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(results)
total = len(results)
print(f"\n{'='*60}")
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("\033[92m✓ All unit & adversarial tests passed. Citation Engine v0.2 is verified.\033[0m")
else:
    print(f"\033[91m✗ {total - passed} test(s) failed. Fix before release.\033[0m")
    sys.exit(1)
print("="*60 + "\n")
