"""
enrichment.py — Academic Metadata Enrichment for Universal Research App v0.3

Enriches Source objects with academic metadata from:
  1. Crossref API — best for DOI-based lookup (structured bibliographic data)
  2. OpenAlex API — open academic graph, no key required

Enrichment trigger: a DOI must be detectable in the source URL.
Sources without a recognizable DOI (e.g., news articles, government pages,
Wikipedia) are returned unchanged — no metadata is fabricated.

PRINCIPLES:
  - Never fabricate: if API returns no data, Source is left unchanged.
  - Graceful degradation: network errors never crash the app.
  - Conservative confidence: metadata_confidence updated only when verified.

FUTURE EXTENSION:
  - Add Semantic Scholar lookup by DOI or title.
  - Add title-based OpenAlex search for sources without DOIs.
"""

from __future__ import annotations

import re
import urllib.request
import urllib.parse
import json
from typing import Optional, Dict, List

from citations import Source


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CROSSREF_BASE = "https://api.crossref.org/works"
OPENALEX_BASE = "https://api.openalex.org/works"
TIMEOUT_SECONDS = 5

# Polite-pool header (helps avoid rate limiting)
_HEADERS = {
    "User-Agent": "universal-research-app/0.3 (https://github.com/harper-nguyen/universal-research)",
}


# ---------------------------------------------------------------------------
# DOI extraction
# ---------------------------------------------------------------------------

_DOI_PATTERN = re.compile(
    r"(?:doi\.org/|doi:)\s*(10\.\d{4,9}/[^\s\"\'<>\[\]&?#]+)",
    re.IGNORECASE,
)


def extract_doi_from_url(url: str) -> Optional[str]:
    """
    Extract a DOI from a URL if present.

    Recognizes:
      https://doi.org/10.1234/example
      http://dx.doi.org/10.1234/example
      https://nature.com/articles/... (no DOI — returns None)

    Returns the bare DOI string (e.g. '10.1234/example') or None.
    """
    if not url:
        return None
    match = _DOI_PATTERN.search(url)
    if not match:
        return None
    doi = match.group(1).rstrip(".,;)")  # Strip trailing punctuation
    return doi if doi else None


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _get_json(url: str, params: Optional[Dict] = None) -> Optional[dict]:
    """
    Fetch JSON from a URL using stdlib urllib (no extra dependencies).
    Returns None on any error (network, timeout, non-200 status, parse error).
    """
    try:
        if params:
            url = url + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None  # Any error → silent fallback


# ---------------------------------------------------------------------------
# Crossref lookup
# ---------------------------------------------------------------------------

def lookup_crossref(doi: str) -> Optional[dict]:
    """
    Query Crossref API by DOI.
    Returns the raw 'message' dict, or None if not found / error.
    """
    encoded_doi = urllib.parse.quote(doi, safe="")
    data = _get_json(f"{CROSSREF_BASE}/{encoded_doi}")
    if data and data.get("status") == "ok":
        return data.get("message")
    return None


def _parse_crossref(msg: dict) -> Dict:
    """
    Extract structured metadata from a Crossref 'message' object.
    Returns only fields that can be determined with confidence.
    """
    result: Dict = {}

    # Authors — Crossref gives structured family/given names
    raw_authors = msg.get("author") or []
    if raw_authors:
        names = []
        for a in raw_authors[:20]:  # APA 7 allows up to 20 before et al.
            family = str(a.get("family") or "").strip()
            given = str(a.get("given") or "").strip()
            if not family:
                continue
            if given:
                # APA 7: Family, G. I.
                initials = " ".join(p[0] + "." for p in given.split() if p)
                names.append(f"{family}, {initials}")
            else:
                names.append(family)
        if len(raw_authors) > 20:
            names.append("et al.")
        if names:
            if len(names) == 1:
                result["author"] = names[0]
            elif len(names) == 2:
                result["author"] = f"{names[0]}, & {names[1]}"
            else:
                result["author"] = ", ".join(names[:-1]) + f", & {names[-1]}"

    # Publication year
    for date_key in ("published", "published-print", "published-online", "issued"):
        date_obj = msg.get(date_key)
        if date_obj:
            parts = date_obj.get("date-parts", [[]])
            if parts and parts[0]:
                try:
                    result["year"] = int(parts[0][0])
                    break
                except (TypeError, ValueError):
                    pass

    # Journal / container title
    containers = msg.get("container-title") or []
    if containers:
        result["journal"] = str(containers[0]).strip()

    # DOI (confirm from response, not just from input URL)
    doi_val = msg.get("DOI")
    if doi_val:
        result["doi"] = str(doi_val).strip()

    return result


# ---------------------------------------------------------------------------
# OpenAlex lookup
# ---------------------------------------------------------------------------

def lookup_openalex(doi: str) -> Optional[dict]:
    """
    Query OpenAlex API by DOI.
    Returns the raw work object, or None if not found / error.

    OpenAlex is queried as fallback when Crossref doesn't return complete data.
    """
    encoded_doi = urllib.parse.quote(doi, safe="")
    data = _get_json(f"{OPENALEX_BASE}/https://doi.org/{encoded_doi}")
    if data and data.get("id"):
        return data
    return None


def _parse_openalex(work: dict) -> Dict:
    """
    Extract structured metadata from an OpenAlex work object.
    Returns only fields that can be determined with confidence.
    """
    result: Dict = {}

    # Authors — OpenAlex gives display_name (not always family/given split)
    authorships = work.get("authorships") or []
    if authorships:
        names = []
        for a in authorships[:20]:
            author = a.get("author") or {}
            name = str(author.get("display_name") or "").strip()
            if name:
                names.append(name)
        if len(authorships) > 20:
            names.append("et al.")
        if names:
            if len(names) == 1:
                result["author"] = names[0]
            elif len(names) == 2:
                result["author"] = f"{names[0]} & {names[1]}"
            else:
                result["author"] = ", ".join(names[:-1]) + f", & {names[-1]}"

    # Publication year
    year = work.get("publication_year")
    if year:
        try:
            result["year"] = int(year)
        except (TypeError, ValueError):
            pass

    # Journal / source name
    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    journal = str(source.get("display_name") or "").strip()
    if journal:
        result["journal"] = journal

    # DOI
    doi_raw = work.get("doi") or ""
    doi_clean = re.sub(r"https?://doi\.org/", "", doi_raw).strip()
    if doi_clean:
        result["doi"] = doi_clean

    return result


# ---------------------------------------------------------------------------
# Enrichment orchestration
# ---------------------------------------------------------------------------

def enrich_source(source: Source) -> Source:
    """
    Attempt to enrich a Source with academic metadata.

    Steps:
      1. Extract DOI from source URL.
      2. If no DOI found, return source unchanged.
      3. Query Crossref by DOI.
      4. If Crossref returns incomplete data, supplement from OpenAlex.
      5. Populate Source fields; update metadata_confidence.

    Never modifies a field that already has a value (no overwrite).
    Returns source unchanged if no enrichment data is available.
    """
    if not source.url:
        return source

    doi = extract_doi_from_url(source.url)
    if not doi:
        return source  # Non-academic URL — no enrichment possible

    enriched: Dict = {}

    # Step 1: Crossref (most structured data for DOI lookup)
    crossref_data = lookup_crossref(doi)
    if crossref_data:
        enriched = _parse_crossref(crossref_data)

    # Step 2: OpenAlex supplement (fill missing fields only)
    needs_supplement = not enriched.get("author") or not enriched.get("year")
    if needs_supplement:
        oa_data = lookup_openalex(doi)
        if oa_data:
            oa_enriched = _parse_openalex(oa_data)
            for key, value in oa_enriched.items():
                if key not in enriched or not enriched[key]:
                    enriched[key] = value

    if not enriched:
        return source  # No data from either API

    # Apply enriched data — only fill empty fields, never overwrite
    if not source.author and enriched.get("author"):
        source.author = enriched["author"]
    if not source.year and enriched.get("year"):
        source.year = enriched["year"]
    if not source.journal and enriched.get("journal"):
        source.journal = enriched["journal"]
    if not source.doi and enriched.get("doi"):
        source.doi = enriched["doi"]
        source.source_type = "academic"

    # Update confidence level
    if source.author and source.doi:
        source.metadata_confidence = "high"
    elif source.year or source.journal:
        source.metadata_confidence = "medium"

    return source


def enrich_sources(sources: List[Source]) -> List[Source]:
    """
    Enrich a list of Sources with academic metadata.

    Sources without detectable DOIs are returned unchanged.
    Network errors never crash the caller — fallback is always the original source.
    """
    enriched = []
    for source in sources:
        try:
            enriched.append(enrich_source(source))
        except Exception:
            enriched.append(source)  # Safety net — always preserve original
    return enriched
