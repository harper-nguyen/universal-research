# CITATION ARCHITECTURE — v0.2

**Universal Research App — Citation Engine v0.2**
*Document Version:* 1.0 (2026-08-29)

---

## 1. Overview & Execution Path

The Citation Engine v0.2 transforms Gemini Google Search grounding metadata into structured, numbered, APA 7-formatted citations and references.

```text
User Question
  │
  ▼
app.py :: main()
  │
  ▼
app.py :: run_research()
  │  ├── loads canonical research/SKILL.md as system_instruction
  │  └── configures tools = [{"google_search": {}}]
  │
  ▼
Gemini API generate_content()
  │  ├── Returns response.text
  │  ├── Returns grounding_metadata.grounding_chunks (sources)
  │  └── Returns grounding_metadata.grounding_supports (claim → source mappings)
  │
  ▼
citations.py :: build_source_list(grounding_chunks)
  │  ├── Normalizes URLs
  │  ├── Deduplicates sources by URL
  │  ├── Assigns 1-based deterministic citation_ids
  │  └── Builds chunk_index_map (chunk index → citation_id)
  │
  ▼
citations.py :: annotate_text_with_citations(text, grounding_supports, chunk_map)
  │  ├── Maps claim segments to citation_ids
  │  └── Inserts inline [N] markers right-to-left
  │
  ▼
citations.py :: build_references_markdown(sources)
  │  └── Formats each source using APA 7 (strictly based on available metadata)
  │
  ▼
Streamlit UI & Markdown Export
  └── Displays report + inline [N] citations + ## References section
```

---

## 2. Citation Data Model (`Source`)

```python
@dataclass
class Source:
    citation_id: int                  # 1-based index (e.g., 1, 2, 3)
    title: Optional[str] = None       # Source title
    url: Optional[str] = None         # Source URL
    domain: Optional[str] = None      # Auto-derived from URL (e.g., "imf.org")
    source_type: str = "web"          # "web", "academic", "book", etc.
    metadata_confidence: str = "low"  # "low", "medium", "high"

    # Enriched fields (None in v0.2; future expansion points)
    author: Optional[str] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
```

### Available Metadata (v0.2)
From Gemini `grounding_chunks`:
- `title` (from `chunk.web.title`)
- `url` (from `chunk.web.uri`)
- `domain` (derived automatically via `urllib.parse`)

### Unavailable Metadata (v0.2)
- `author` (None)
- `year` (None)
- `journal` (None)
- `doi` (None)

**Strict Rule:** Unavailable metadata MUST remain `None`. The system NEVER fabricates author names, publication dates, journal titles, or DOIs.

---

## 3. Claim-Source Traceability & Limitations

Gemini's grounding response includes `grounding_supports`, which maps text segments to `grounding_chunk_indices`.

1. **When `grounding_supports` is present:**
   `annotate_text_with_citations()` maps `grounding_chunk_indices` to `citation_id`s and places `[N]` inline markers at segment boundaries.

2. **When `grounding_supports` is missing or empty:**
   The original text is left untouched. The system does NOT guess inline citation placement. A `## References` section is still rendered at the end of the report using all verified sources returned in `grounding_chunks`.

---

## 4. APA 7 Generation Rules

APA 7 formatting adjusts dynamically to available metadata without inventing missing fields:

```text
Full metadata (Future enriched):
  Author, A. A. (Year). Title of work. Journal Name. https://doi.org/10.xxxx/xxxx

Web source with title + URL + domain (v0.2 standard):
  Title of work. domain.com. https://example.com/work

Web source with title only (no URL):
  Title of work.

Web source with URL only (no title):
  domain.com. https://example.com/work

No metadata available:
  [Source metadata unavailable]
```

---

## 5. Deduplication & Error Handling

- **URL Normalization:** Scheme and domain are lowercased, trailing slashes are stripped.
- **Duplicate URLs:** Merged under a single `citation_id`. If chunk 1 has no title but chunk 2 has a title for the same URL, the title is merged.
- **Malformed Chunks:** Handled via `try/except` without throwing exceptions or crashing the UI.
- **Malformed Supports:** Invalid or out-of-bounds character indices are safely ignored.

---

## 6. Future Extension Interface (Academic Metadata Enrichment)

The `Source` data model is pre-architected for academic enrichment without structural breaking changes:

```text
                       ┌─────────────────────────┐
                       │   Gemini Grounding      │
                       └───────────┬─────────────┘
                                   │ (title, url)
                                   ▼
                       ┌─────────────────────────┐
                       │     Source Object       │
                       └───────────┬─────────────┘
                                   │ (Enrichment Hook)
            ┌──────────────────────┼──────────────────────┐
            ▼                      ▼                      ▼
  ┌───────────────────┐  ┌───────────────────┐  ┌───────────────────┐
  │ Crossref API      │  │ OpenAlex API      │  │ Semantic Scholar  │
  │ (DOI lookup)      │  │ (Paper metadata)  │  │ (Author / Journal)│
  └─────────┬─────────┘  └─────────┬─────────┘  └─────────┬─────────┘
            │                      │                      │
            └──────────────────────┼──────────────────────┘
                                   │ populates: author, year, journal, doi
                                   ▼
                       ┌─────────────────────────┐
                       │ Enriched Source Object  │
                       │ metadata_confidence     │
                       │   = "high"              │
                       └─────────────────────────┘
```

When an external metadata service (OpenAlex, Crossref, Semantic Scholar) is added in a future version:
1. `Source` receives `author`, `year`, `journal`, `doi`.
2. `metadata_confidence` is updated to `"high"`.
3. `format_apa7()` automatically outputs full academic APA 7 formatting.
4. `citations.py` API contracts and Streamlit UI remain unchanged.
