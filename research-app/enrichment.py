"""
enrichment.py — Academic Metadata Enrichment for Universal Research App v0.3.5

Enriches Source objects with academic metadata from:
  1. DOI-based lookup via Crossref API & OpenAlex API (highest accuracy)
  2. Title-based search via OpenAlex API (when source URL lacks DOI)

PRINCIPLES:
  - Never fabricate: if APIs return no verified match, Source is left unchanged.
  - Strict matching: Title-based search requires high title similarity (>= 80%) to prevent false positives.
  - Graceful degradation: network errors or timeouts never crash the app.
  - Conservative confidence:
      * "high": direct DOI match with author + DOI verified
      * "medium": high-similarity title match or partial DOI match
      * "low": un-enriched web source
"""

from __future__ import annotations

import re
import urllib.request
import urllib.parse
import json
from typing import Optional, Dict, List, Tuple

from citations import Source


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CROSSREF_BASE = "https://api.crossref.org/works"
OPENALEX_BASE = "https://api.openalex.org/works"
SEMANTICSCHOLAR_BASE = "https://api.semanticscholar.org/graph/v1/paper"
TIMEOUT_SECONDS = 5

# Polite-pool header (helps avoid rate limiting)
_HEADERS = {
    "User-Agent": "universal-research-app/0.5 (https://github.com/harper-nguyen/universal-research)",
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
# Title cleaning & similarity matching
# ---------------------------------------------------------------------------

# Common website/publisher suffixes in web search titles
_TITLE_CLEAN_SUFFIXES = re.compile(
    r"\s*(?:[-|–—:]\s*(?:ScienceDirect|Nature|SpringerLink|Wiley|ResearchGate|PubMed|IEEE Xplore|Oxford Academic|Cambridge Core|arXiv|Wikipedia|JSTOR|SSRN|The World Bank|IMF|OECD).*$|\[PDF\]|\.pdf$)",
    re.IGNORECASE,
)


def clean_title_for_search(title: Optional[str]) -> Optional[str]:
    """
    Clean web page title for academic search.
    Strips publisher names, [PDF] tags, and trailing site branding.
    """
    if not title:
        return None
    cleaned = _TITLE_CLEAN_SUFFIXES.sub("", title).strip()
    # Remove leading/trailing quotes or punctuation
    cleaned = re.sub(r"^[\"\'\s]+|[\"\'\s]+$", "", cleaned)
    # Require at least 3 words to avoid generic terms like 'Home', 'Article', 'Index'
    if len(cleaned.split()) < 3:
        return None
    return cleaned


def title_similarity(t1: str, t2: str) -> float:
    """
    Calculate word-token Jaccard similarity and character sequence overlap between two titles.
    Returns a score between 0.0 and 1.0.
    """
    if not t1 or not t2:
        return 0.0

    def tokenize(text: str) -> set:
        clean = re.sub(r"[^\w\s]", "", text.lower())
        return set(clean.split())

    tokens1 = tokenize(t1)
    tokens2 = tokenize(t2)

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    jaccard = len(intersection) / len(union)

    # Clean string overlap check
    s1 = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t1.lower())).strip()
    s2 = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", "", t2.lower())).strip()

    # Exact substring or high containment boost
    if s1 in s2 or s2 in s1:
        containment = min(len(s1), len(s2)) / max(len(s1), len(s2))
        return max(jaccard, containment)

    return jaccard


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
# OpenAlex lookup (by DOI & by Title)
# ---------------------------------------------------------------------------

def lookup_openalex(doi: str) -> Optional[dict]:
    """
    Query OpenAlex API by DOI.
    Returns the raw work object, or None if not found / error.
    """
    encoded_doi = urllib.parse.quote(doi, safe="")
    data = _get_json(f"{OPENALEX_BASE}/https://doi.org/{encoded_doi}")
    if data and data.get("id"):
        return data
    return None


def search_openalex_by_title(title: str, min_similarity: float = 0.70) -> Optional[dict]:
    """
    Search OpenAlex for academic papers by title.
    Returns the best matching work object if similarity >= min_similarity, else None.
    """
    cleaned = clean_title_for_search(title)
    if not cleaned:
        return None

    params = {
        "filter": f"title.search:{cleaned}",
        "per-page": 3,
    }
    data = _get_json(OPENALEX_BASE, params=params)
    if not data or not data.get("results"):
        # Try general search if filter returned nothing
        params = {"search": cleaned, "per-page": 3}
        data = _get_json(OPENALEX_BASE, params=params)

    if not data or not data.get("results"):
        return None

    best_match = None
    best_score = 0.0

    for work in data.get("results", []):
        cand_title = work.get("title") or work.get("display_name") or ""
        score = title_similarity(cleaned, cand_title)
        if score > best_score:
            best_score = score
            best_match = work

    if best_match and best_score >= min_similarity:
        return best_match

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


def lookup_semanticscholar(doi: str) -> Optional[dict]:
    """
    Query Semantic Scholar Graph API by DOI for citation metrics.
    Returns paper metadata dict with citationCount, or None on error.
    """
    encoded_doi = urllib.parse.quote(doi, safe="")
    url = f"{SEMANTICSCHOLAR_BASE}/DOI:{encoded_doi}?fields=citationCount,influentialCitationCount"
    return _get_json(url)


# ---------------------------------------------------------------------------
# Enrichment orchestration
# ---------------------------------------------------------------------------

def enrich_source(source: Source) -> Source:
    """
    Attempt to enrich a Source with academic metadata.

    Strategy:
      Phase 1: DOI-based lookup (Crossref + OpenAlex) if URL contains a DOI.
      Phase 2: Title-based search (OpenAlex) if source has a valid title.
      Phase 3: Semantic Scholar citation metric lookup if DOI is known.

    Never overwrites existing values.
    Returns source unchanged if no verified academic metadata is found.
    """
    enriched: Dict = {}
    is_doi_match = False

    # 1. DOI in URL check
    if source.url:
        doi = extract_doi_from_url(source.url)
        if doi:
            # Step 1a: Crossref (most structured for DOI)
            crossref_data = lookup_crossref(doi)
            if crossref_data:
                enriched = _parse_crossref(crossref_data)

            # Step 1b: OpenAlex supplement (fill missing fields)
            needs_supplement = not enriched.get("author") or not enriched.get("year")
            if needs_supplement:
                oa_data = lookup_openalex(doi)
                if oa_data:
                    oa_enriched = _parse_openalex(oa_data)
                    for key, value in oa_enriched.items():
                        if key not in enriched or not enriched[key]:
                            enriched[key] = value

            if enriched:
                is_doi_match = True

    # 2. Title-based OpenAlex search (fallback when no DOI in URL)
    if not enriched and source.title:
        oa_work = search_openalex_by_title(source.title)
        if oa_work:
            enriched = _parse_openalex(oa_work)

    if not enriched:
        return source  # No match found — leave source unchanged

    # Apply verified metadata — only fill empty fields
    if not source.author and enriched.get("author"):
        source.author = enriched["author"]
    if not source.year and enriched.get("year"):
        source.year = enriched["year"]
    if not source.journal and enriched.get("journal"):
        source.journal = enriched["journal"]
    if not source.doi and enriched.get("doi"):
        source.doi = enriched["doi"]

    if source.author or source.doi:
        source.source_type = "academic"

    # Set confidence level based on matching method
    if is_doi_match and source.author and source.doi:
        source.metadata_confidence = "high"
    elif enriched.get("author") or enriched.get("year"):
        source.metadata_confidence = "medium"

    # Phase 3: Semantic Scholar citation count enrichment
    if source.doi and source.citation_count is None:
        try:
            s2_data = lookup_semanticscholar(source.doi)
            if s2_data and isinstance(s2_data.get("citationCount"), int):
                count = s2_data["citationCount"]
                source.citation_count = count
                if count >= 50:
                    source.is_highly_cited = True
        except Exception:
            pass

    return source


def enrich_sources(sources: List[Source]) -> List[Source]:
    """
    Enrich a list of Sources with academic metadata.
    Handles both DOI-based and title-based matches safely.
    Network errors never crash the caller — fallback is always the original source.
    """
    enriched = []
    for source in sources:
        try:
            enriched.append(enrich_source(source))
        except Exception:
            enriched.append(source)  # Safety net
    return enriched

