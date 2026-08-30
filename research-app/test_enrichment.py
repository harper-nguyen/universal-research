"""
test_enrichment.py — Unit & Adversarial Tests for Enrichment Module v0.3.5

Tests DOI extraction, Title-based search, Crossref/OpenAlex parsing,
enrichment logic, title similarity, and edge cases.
Uses mock API response data — no live network calls.
"""

import sys
import json
from unittest.mock import patch, MagicMock
from citations import Source
from enrichment import (
    extract_doi_from_url,
    clean_title_for_search,
    title_similarity,
    _parse_crossref,
    _parse_openalex,
    enrich_source,
    enrich_sources,
    lookup_crossref,
    lookup_openalex,
    search_openalex_by_title,
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

print("\n=== Enrichment Module v0.3.5 — Unit & Adversarial Tests ===\n")

# ---------------------------------------------------------------------------
# 1. DOI Extraction
# ---------------------------------------------------------------------------
check("DOI from doi.org URL",
    extract_doi_from_url("https://doi.org/10.1234/example") == "10.1234/example")

check("DOI from dx.doi.org URL",
    extract_doi_from_url("https://dx.doi.org/10.1038/s41586-024-00001-x") == "10.1038/s41586-024-00001-x")

check("DOI strips trailing period",
    extract_doi_from_url("https://doi.org/10.1000/xyz123.") == "10.1000/xyz123")

check("DOI from non-DOI URL returns None",
    extract_doi_from_url("https://www.nytimes.com/2024/01/01/world/article.html") is None)

check("DOI from empty string returns None",
    extract_doi_from_url("") is None)

check("DOI from None returns None",
    extract_doi_from_url(None) is None)

check("DOI from Wikipedia URL returns None",
    extract_doi_from_url("https://en.wikipedia.org/wiki/Foreign_direct_investment") is None)

check("DOI from embedded doi: prefix",
    extract_doi_from_url("https://example.org/doi:10.5678/test-paper") == "10.5678/test-paper")

# ---------------------------------------------------------------------------
# 2. Title Cleaning & Similarity Matching
# ---------------------------------------------------------------------------
check("Clean title strips ScienceDirect suffix",
    clean_title_for_search("Foreign Direct Investment and Economic Growth - ScienceDirect") == "Foreign Direct Investment and Economic Growth")

check("Clean title strips [PDF] tag",
    clean_title_for_search("Determinants of FDI in Developing Countries [PDF]") == "Determinants of FDI in Developing Countries")

check("Clean title rejects short generic titles (< 3 words)",
    clean_title_for_search("Home Page") is None)

check("Title similarity identical titles is 1.0",
    title_similarity("Determinants of FDI", "Determinants of FDI") >= 0.99)

check("Title similarity minor punctuation difference is high",
    title_similarity("Determinants of FDI: A Panel Study", "Determinants of FDI a panel study") >= 0.90)

check("Title similarity completely different titles is low",
    title_similarity("Quantum Computing Algorithms", "Foreign Direct Investment in Asia") < 0.20)

# ---------------------------------------------------------------------------
# 3. Crossref Response Parsing
# ---------------------------------------------------------------------------
crossref_msg_full = {
    "DOI": "10.1234/example",
    "author": [
        {"family": "Dunning", "given": "John H."},
        {"family": "Lundan", "given": "Sarianna M."},
    ],
    "published": {"date-parts": [[1988, 6, 1]]},
    "container-title": ["Journal of International Business Studies"],
}

parsed_cr = _parse_crossref(crossref_msg_full)
check("Crossref parses DOI", parsed_cr.get("doi") == "10.1234/example")
check("Crossref parses two authors APA format",
    parsed_cr.get("author") == "Dunning, J. H., & Lundan, S. M.")
check("Crossref parses year", parsed_cr.get("year") == 1988)
check("Crossref parses journal", parsed_cr.get("journal") == "Journal of International Business Studies")

# Single author
crossref_single_author = {
    "DOI": "10.9999/single",
    "author": [{"family": "Smith", "given": "Adam B."}],
    "published": {"date-parts": [[2024]]},
    "container-title": ["Economics Letters"],
}
parsed_single = _parse_crossref(crossref_single_author)
check("Crossref single author — no ampersand", parsed_single.get("author") == "Smith, A. B.")

# Empty author list
crossref_no_author = {"DOI": "10.0000/x", "container-title": ["Test Journal"]}
parsed_no_author = _parse_crossref(crossref_no_author)
check("Crossref no author — field absent from result", parsed_no_author.get("author") is None)

# ---------------------------------------------------------------------------
# 4. OpenAlex Response Parsing
# ---------------------------------------------------------------------------
openalex_work = {
    "id": "https://openalex.org/W12345",
    "title": "Trade Policy and Foreign Investment",
    "doi": "https://doi.org/10.5678/oa-test",
    "publication_year": 2023,
    "authorships": [
        {"author": {"display_name": "Maria Garcia"}},
        {"author": {"display_name": "David Chen"}},
        {"author": {"display_name": "Priya Patel"}},
    ],
    "primary_location": {
        "source": {"display_name": "World Development"}
    },
}

parsed_oa = _parse_openalex(openalex_work)
check("OpenAlex parses DOI (strips prefix)",
    parsed_oa.get("doi") == "10.5678/oa-test")
check("OpenAlex parses year", parsed_oa.get("year") == 2023)
check("OpenAlex parses journal", parsed_oa.get("journal") == "World Development")
check("OpenAlex three authors with ampersand",
    parsed_oa.get("author") == "Maria Garcia, David Chen, & Priya Patel")

# Empty OpenAlex work
check("OpenAlex empty work returns empty dict", _parse_openalex({}) == {})

# ---------------------------------------------------------------------------
# 5. enrich_source Logic (DOI-based & Title-based)
# ---------------------------------------------------------------------------

# Case 1: DOI in URL -> DOI lookup
doi_source = Source(
    citation_id=1,
    title="Multinational Enterprises and the Global Economy",
    url="https://doi.org/10.1234/example",
)

with patch("enrichment.lookup_crossref") as mock_cr, \
     patch("enrichment.lookup_openalex") as mock_oa:
    mock_cr.return_value = crossref_msg_full
    mock_oa.return_value = None

    enriched_src = enrich_source(doi_source)

check("Enriched source has author", enriched_src.author == "Dunning, J. H., & Lundan, S. M.")
check("Enriched source has year", enriched_src.year == 1988)
check("Enriched source has journal", enriched_src.journal == "Journal of International Business Studies")
check("Enriched source has doi", enriched_src.doi == "10.1234/example")
check("Enriched source confidence is high", enriched_src.metadata_confidence == "high")
check("Enriched source type is academic", enriched_src.source_type == "academic")

# Case 2: Title-based search (URL has no DOI, e.g., University webpage)
title_only_source = Source(
    citation_id=2,
    title="Trade Policy and Foreign Investment - University Portal",
    url="https://university.edu/working-papers/123",
)

with patch("enrichment.search_openalex_by_title") as mock_title_search:
    mock_title_search.return_value = openalex_work

    enriched_title_src = enrich_source(title_only_source)

check("Title-based search: author populated", enriched_title_src.author == "Maria Garcia, David Chen, & Priya Patel")
check("Title-based search: year populated", enriched_title_src.year == 2023)
check("Title-based search: journal populated", enriched_title_src.journal == "World Development")
check("Title-based search: doi populated", enriched_title_src.doi == "10.5678/oa-test")
check("Title-based search: confidence is medium", enriched_title_src.metadata_confidence == "medium")

# Case 3: Title-based search fails / no match -> source remains unchanged
generic_web_source = Source(citation_id=3, title="BBC News World Report", url="https://bbc.com/news/123")
with patch("enrichment.search_openalex_by_title") as mock_title_search:
    mock_title_search.return_value = None

    unchanged_web = enrich_source(generic_web_source)

check("Non-academic title returned unchanged", unchanged_web.author is None)
check("Non-academic title confidence is low", unchanged_web.metadata_confidence == "low")

# ---------------------------------------------------------------------------
# 6. enrich_sources (batch)
# ---------------------------------------------------------------------------
sources_batch = [
    Source(citation_id=1, url="https://doi.org/10.1234/a"),
    Source(citation_id=2, title="BBC News Overview", url="https://bbc.com/article"),
    Source(citation_id=3, title="Trade Policy and Foreign Investment", url="https://edu.org/paper"),
]

with patch("enrichment.lookup_crossref") as mock_cr4, \
     patch("enrichment.lookup_openalex") as mock_oa4, \
     patch("enrichment.search_openalex_by_title") as mock_title_s:

    mock_cr4.side_effect = lambda doi: crossref_msg_full if "1234" in doi else None
    mock_oa4.return_value = None
    mock_title_s.side_effect = lambda t: openalex_work if "Trade Policy" in t else None

    batch_result = enrich_sources(sources_batch)

check("Batch: first source enriched from Crossref (DOI)", batch_result[0].year == 1988)
check("Batch: second source unchanged (news)", batch_result[1].author is None)
check("Batch: third source enriched via title search", batch_result[2].year == 2023)
check("Batch: returns same count as input", len(batch_result) == 3)

# ---------------------------------------------------------------------------
# 7. Adversarial Tests
# ---------------------------------------------------------------------------

# Exception during enrichment
bad_source = Source(citation_id=99, title="Bad", url="https://doi.org/10.0000/crash")
with patch("enrichment.enrich_source") as mock_enrich:
    mock_enrich.side_effect = RuntimeError("Simulated crash")
    result = enrich_sources([bad_source])

check("Adversarial: RuntimeError inside enrich_source handled safely",
    result[0].title == "Bad" and result[0].author is None)

# Malformed Crossref data
malformed_msg = {"DOI": "10.1/bad", "author": None, "container-title": None}
parsed_malformed = _parse_crossref(malformed_msg)
check("Adversarial: malformed Crossref data parsed safely", parsed_malformed.get("author") is None)

# Valid DOI prefix with trailing garbage
check("Adversarial: DOI with trailing ) stripped",
    extract_doi_from_url("https://doi.org/10.1016/test-paper)") == "10.1016/test-paper")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
passed = sum(results)
total = len(results)
print(f"\n{'='*60}")
print(f"Results: {passed}/{total} passed")
if passed == total:
    print("\033[92m✓ All enrichment tests passed. Module v0.3.5 is verified.\033[0m")
else:
    print(f"\033[91m✗ {total - passed} test(s) failed.\033[0m")
    sys.exit(1)
print("="*60 + "\n")
