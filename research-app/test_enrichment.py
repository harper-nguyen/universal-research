"""
test_enrichment.py — Unit & Adversarial Tests for Enrichment Module v0.3

Tests DOI extraction, metadata parsing, enrichment logic, and edge cases.
Uses mock API response data — no live network calls.
"""

import sys
import json
from unittest.mock import patch, MagicMock
from citations import Source
from enrichment import (
    extract_doi_from_url,
    _parse_crossref,
    _parse_openalex,
    enrich_source,
    enrich_sources,
    lookup_crossref,
    lookup_openalex,
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

print("\n=== Enrichment Module v0.3 — Unit & Adversarial Tests ===\n")

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
# 2. Crossref Response Parsing
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
# 3. OpenAlex Response Parsing
# ---------------------------------------------------------------------------
openalex_work = {
    "id": "https://openalex.org/W12345",
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
# 4. enrich_source Logic (Mocked API)
# ---------------------------------------------------------------------------

# Source with DOI URL — should trigger enrichment
doi_source = Source(
    citation_id=1,
    title="Multinational Enterprises and the Global Economy",
    url="https://doi.org/10.1234/example",
)

# Mock Crossref returning full data
with patch("enrichment.lookup_crossref") as mock_cr, \
     patch("enrichment.lookup_openalex") as mock_oa:
    mock_cr.return_value = crossref_msg_full
    mock_oa.return_value = None  # Crossref was sufficient

    enriched_src = enrich_source(doi_source)

check("Enriched source has author", enriched_src.author == "Dunning, J. H., & Lundan, S. M.")
check("Enriched source has year", enriched_src.year == 1988)
check("Enriched source has journal", enriched_src.journal == "Journal of International Business Studies")
check("Enriched source has doi", enriched_src.doi == "10.1234/example")
check("Enriched source confidence is high", enriched_src.metadata_confidence == "high")
check("Enriched source type is academic", enriched_src.source_type == "academic")

# Source with no URL — should return unchanged
no_url_source = Source(citation_id=2, title="Offline Paper", url=None)
unchanged = enrich_source(no_url_source)
check("Source with no URL returned unchanged", unchanged.author is None and unchanged.doi is None)

# Source without DOI in URL — should return unchanged
web_source = Source(citation_id=3, title="BBC News Article", url="https://bbc.com/news/world-123")
unchanged_web = enrich_source(web_source)
check("Non-DOI URL source returned unchanged", unchanged_web.author is None)

# Crossref fails, OpenAlex succeeds
doi_src2 = Source(citation_id=4, title="Trade Policy Paper", url="https://doi.org/10.5678/oa-test")
with patch("enrichment.lookup_crossref") as mock_cr2, \
     patch("enrichment.lookup_openalex") as mock_oa2:
    mock_cr2.return_value = None  # Crossref not found
    mock_oa2.return_value = openalex_work  # OpenAlex succeeds

    enriched_oa = enrich_source(doi_src2)

check("Fallback to OpenAlex when Crossref fails", enriched_oa.year == 2023)
check("OpenAlex enriched author populated", enriched_oa.author is not None)

# Both APIs fail — source unchanged
doi_src3 = Source(citation_id=5, title="Unknown Paper", url="https://doi.org/10.9999/notfound")
with patch("enrichment.lookup_crossref") as mock_cr3, \
     patch("enrichment.lookup_openalex") as mock_oa3:
    mock_cr3.return_value = None
    mock_oa3.return_value = None

    unchanged_both = enrich_source(doi_src3)

check("Both APIs fail — source returned unchanged", unchanged_both.author is None)
check("Both APIs fail — confidence stays low", unchanged_both.metadata_confidence == "low")

# ---------------------------------------------------------------------------
# 5. enrich_sources (batch)
# ---------------------------------------------------------------------------
sources_batch = [
    Source(citation_id=1, url="https://doi.org/10.1234/a"),
    Source(citation_id=2, url="https://www.imf.org/en/Publications"),  # no DOI
    Source(citation_id=3, url="https://doi.org/10.5678/b"),
]

with patch("enrichment.lookup_crossref") as mock_cr4, \
     patch("enrichment.lookup_openalex") as mock_oa4:
    mock_cr4.side_effect = lambda doi: crossref_msg_full if "1234" in doi else None
    mock_oa4.side_effect = lambda doi: openalex_work if "5678" in doi else None

    batch_result = enrich_sources(sources_batch)

check("Batch: first source enriched from Crossref", batch_result[0].year == 1988)
check("Batch: web source remains unchanged", batch_result[1].author is None)
check("Batch: third source enriched from OpenAlex", batch_result[2].year == 2023)
check("Batch: returns same count as input", len(batch_result) == 3)

# ---------------------------------------------------------------------------
# 6. Adversarial Tests
# ---------------------------------------------------------------------------

# Exception during enrichment — must not crash enrich_sources
bad_source = Source(citation_id=99, title="Bad", url="https://doi.org/10.0000/crash")
with patch("enrichment.enrich_source") as mock_enrich:
    mock_enrich.side_effect = RuntimeError("Simulated crash")
    result = enrich_sources([bad_source])

check("Adversarial: RuntimeError inside enrich_source handled safely by enrich_sources",
    result[0].title == "Bad" and result[0].author is None)

# Crossref returns malformed data (missing required keys)
malformed_msg = {"DOI": "10.1/bad", "author": None, "container-title": None}
parsed_malformed = _parse_crossref(malformed_msg)
check("Adversarial: malformed Crossref data parsed safely", parsed_malformed.get("author") is None)

# OpenAlex returns empty authorships list
oa_empty_authors = {"id": "W0", "authorships": [], "publication_year": 2020, "doi": "https://doi.org/10.0/x"}
parsed_empty = _parse_openalex(oa_empty_authors)
check("Adversarial: empty OpenAlex authorships handled", parsed_empty.get("author") is None)
check("Adversarial: OpenAlex year still parsed when authors empty", parsed_empty.get("year") == 2020)

# DOI with trailing garbage characters (valid DOI prefix: 4+ digits)
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
    print("\033[92m✓ All enrichment tests passed. Module v0.3 is verified.\033[0m")
else:
    print(f"\033[91m✗ {total - passed} test(s) failed.\033[0m")
    sys.exit(1)
print("="*60 + "\n")
