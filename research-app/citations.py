"""
citations.py — Citation Engine for Universal Research App v0.2

This module is pure Python (no Streamlit). It handles:
  - Source data model (honest about what is/isn't available)
  - Source list construction from Gemini grounding_chunks
  - Deduplication by normalized URL
  - APA 7 formatting (only from available metadata — no fabrication)
  - References section generation
  - Inline [N] annotation using Gemini grounding_supports

METADATA AVAILABILITY IN v0.2:
  Available (from Gemini grounding):  title, url, domain
  NOT available (must stay None):     author, year, journal, doi

The unavailable fields exist solely to document the extension interface
for future enrichment (Crossref, OpenAlex, Semantic Scholar).
"""

from __future__ import annotations

import re
import html
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Source data model
# ---------------------------------------------------------------------------

@dataclass
class Source:
    """
    A single citation source.

    FIELD AVAILABILITY (v0.2)
    ┌──────────────────────────────────────────────────────────────────┐
    │ POPULATED from Gemini grounding_chunks:                          │
    │   citation_id  title  url  domain                                │
    │                                                                  │
    │ ALWAYS None in v0.2 — do NOT populate without enrichment:        │
    │   author  year  journal  doi                                     │
    │                                                                  │
    │ FUTURE EXTENSION POINT — see CITATION_ARCHITECTURE.md:          │
    │   author  year  journal  doi  ← from Crossref / OpenAlex / etc. │
    └──────────────────────────────────────────────────────────────────┘
    """
    citation_id: int                  # 1-based; deterministic
    title: Optional[str] = None       # grounding_chunk.web.title (may be None)
    url: Optional[str] = None         # grounding_chunk.web.uri  (may be None)
    domain: Optional[str] = None      # derived from url via urllib.parse
    source_type: str = "web"          # always "web" in v0.2
    metadata_confidence: str = "low"  # always "low" in v0.2

    # NOT AVAILABLE in v0.2 — future enrichment only
    author: Optional[str] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None

    def __post_init__(self) -> None:
        # Normalize empty strings to None
        if self.title is not None and not str(self.title).strip():
            self.title = None
        if self.url is not None and not str(self.url).strip():
            self.url = None
        # Derive domain from URL when not explicitly provided
        if self.url and self.domain is None:
            self.domain = _extract_domain(self.url)


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _extract_domain(url: str) -> Optional[str]:
    """Extract bare domain (no www.) from a URL string."""
    try:
        netloc = urlparse(url.strip()).netloc
        return netloc[4:] if netloc.startswith("www.") else netloc or None
    except Exception:
        return None


def _normalize_url(url: Optional[str]) -> Optional[str]:
    """
    Normalize a URL for deduplication.
    Lowercases scheme + host, strips trailing slash, preserves query string.
    Returns None for blank/invalid inputs.
    """
    if not url:
        return None
    try:
        url = url.strip()
        p = urlparse(url)
        norm = f"{p.scheme.lower()}://{p.netloc.lower()}{p.path.rstrip('/')}"
        if p.query:
            norm += f"?{p.query}"
        return norm
    except Exception:
        return url.strip().lower()


# ---------------------------------------------------------------------------
# Source list construction
# ---------------------------------------------------------------------------

def build_source_list(
    grounding_chunks,
) -> Tuple[List[Source], Dict[int, int]]:
    """
    Build a deduplicated, numbered list of Sources from Gemini grounding_chunks.

    Deduplication: by normalized URL. When two chunks share the same URL,
    the first is kept. If the first has no title and the second does, the
    title is merged into the first (no data is lost).

    Chunks with no title AND no URL are discarded (no usable metadata).

    Returns:
        sources          — ordered list of Source objects (citation_id is 1-based)
        chunk_index_map  — maps original chunk index → citation_id
                           (needed to annotate text via grounding_supports)
    """
    seen_urls: Dict[str, int] = {}   # normalized_url → citation_id
    sources: List[Source] = []
    chunk_index_map: Dict[int, int] = {}

    for idx, chunk in enumerate(grounding_chunks or []):
        title: Optional[str] = None
        url: Optional[str] = None

        try:
            web = getattr(chunk, "web", None)
            if web is not None:
                raw_title = getattr(web, "title", None)
                raw_url = getattr(web, "uri", None)
                if raw_title and str(raw_title).strip():
                    title = str(raw_title).strip()
                if raw_url and str(raw_url).strip():
                    url = str(raw_url).strip()
        except Exception:
            pass  # Malformed chunk — skip silently

        if title is None and url is None:
            continue  # No usable data

        norm = _normalize_url(url)

        if norm and norm in seen_urls:
            existing_cid = seen_urls[norm]
            # Merge title if existing entry lacks one
            existing_src = sources[existing_cid - 1]
            if existing_src.title is None and title is not None:
                existing_src.title = title
            chunk_index_map[idx] = existing_cid
            continue

        citation_id = len(sources) + 1
        src = Source(citation_id=citation_id, title=title, url=url)
        sources.append(src)

        if norm:
            seen_urls[norm] = citation_id
        chunk_index_map[idx] = citation_id

    return sources, chunk_index_map


# ---------------------------------------------------------------------------
# APA 7 formatting
# ---------------------------------------------------------------------------

def format_apa7(source: Source) -> str:
    """
    Format a Source as APA 7 using ONLY available metadata.

    NEVER fabricates author, year, journal, or DOI.

    APA 7 patterns applied in order of completeness:
      Full (future):   Author, A. (Year). Title. Journal. https://doi.org/DOI
      v0.2 with URL:   Title. domain.com. url
      v0.2 no URL:     Title.
      URL only:        url
      Neither:         [Source metadata unavailable]
    """
    parts: List[str] = []

    # Author (not available in v0.2)
    if source.author:
        parts.append(f"{source.author}.")

    # Year (not available in v0.2)
    if source.year:
        parts.append(f"({source.year}).")

    # Title
    if source.title:
        parts.append(f"{source.title}.")

    # Journal (not available in v0.2)
    if source.journal:
        parts.append(f"*{source.journal}*.")

    # Publisher stand-in from domain (low confidence — informational only)
    if source.domain and not source.journal and not source.author:
        parts.append(f"{source.domain}.")

    # DOI or URL
    if source.doi:
        parts.append(f"https://doi.org/{source.doi}")
    elif source.url:
        parts.append(source.url)

    if not parts:
        return "[Source metadata unavailable]"

    return " ".join(parts)


# ---------------------------------------------------------------------------
# References section
# ---------------------------------------------------------------------------

def build_references_markdown(sources: List[Source]) -> str:
    """
    Build a Markdown ## References section from a list of Sources.
    Sources are sorted by citation_id. Returns empty string if sources is empty.
    Only sources passed in this list are included.
    """
    if not sources:
        return ""
    lines = ["## References", ""]
    for src in sorted(sources, key=lambda s: s.citation_id):
        lines.append(f"[{src.citation_id}] {format_apa7(src)}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Inline citation annotation
# ---------------------------------------------------------------------------

def annotate_text_with_citations(
    response_text: str,
    grounding_supports,
    chunk_index_map: Dict[int, int],
) -> Tuple[str, bool]:
    """
    Insert inline [N] markers into response_text using Gemini's
    grounding_supports (segment-level claim → source mappings).

    This function NEVER fabricates claim-source relationships.
    If grounding_supports is None/empty, the original text is returned
    unchanged and citations_inserted is False.

    Algorithm:
      1. For each GroundingSupport, get the text segment's end_index and
         the grounding_chunk_indices that support it.
      2. Map chunk indices to citation_ids via chunk_index_map.
      3. Collect (end_index, marker) pairs.
      4. Sort descending by end_index and insert markers from right to left
         so earlier offsets are not shifted.

    Returns:
        (annotated_text, citations_inserted)
    """
    if not grounding_supports:
        return response_text, False

    insertions: List[Tuple[int, str]] = []

    for support in grounding_supports:
        try:
            seg = getattr(support, "segment", None)
            if seg is None:
                continue
            end_idx = getattr(seg, "end_index", None)
            if not isinstance(end_idx, int):
                continue

            raw_indices = getattr(support, "grounding_chunk_indices", None) or []
            if not raw_indices:
                continue

            cite_ids = sorted({
                chunk_index_map[ci]
                for ci in raw_indices
                if ci in chunk_index_map
            })
            if not cite_ids:
                continue

            marker = "".join(f"[{cid}]" for cid in cite_ids)
            insertions.append((end_idx, marker))

        except Exception:
            continue  # Never crash on malformed grounding data

    if not insertions:
        return response_text, False

    # Deduplicate insertions at the same position
    deduped: Dict[int, str] = {}
    for end_idx, marker in insertions:
        deduped[end_idx] = deduped.get(end_idx, "") + marker

    # Insert from right to left to preserve character offsets
    text = response_text
    for end_idx in sorted(deduped.keys(), reverse=True):
        marker = deduped[end_idx]
        end_idx = max(0, min(end_idx, len(text)))
        text = text[:end_idx] + marker + text[end_idx:]

    return text, True


# ---------------------------------------------------------------------------
# HTML & Multi-Format Export
# ---------------------------------------------------------------------------

def build_html_report(
    question: str,
    result_text: str,
    model_used: str,
    sources: List[Source],
    ref_markdown: str = "",
) -> str:
    """
    Build a standalone, beautifully styled HTML report suitable for printing (PDF)
    or sharing. Uses modern typography and CSS print media queries.
    """
    import html

    safe_question = html.escape(question)
    safe_model = html.escape(model_used)

    # Basic markdown to HTML formatting for headers, bold, italics, lists, and line breaks
    def simple_md_to_html(md: str) -> str:
        lines = md.split("\n")
        html_lines = []
        in_list = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append("<br/>")
                continue

            if stripped.startswith("### "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h3>{html.escape(stripped[4:])}</h3>")
            elif stripped.startswith("## "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h2>{html.escape(stripped[3:])}</h2>")
            elif stripped.startswith("# "):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append(f"<h1>{html.escape(stripped[2:])}</h1>")
            elif stripped.startswith("- ") or stripped.startswith("* "):
                if not in_list:
                    html_lines.append("<ul>")
                    in_list = True
                content = html.escape(stripped[2:])
                # Replace inline bold
                content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", content)
                html_lines.append(f"<li>{content}</li>")
            elif stripped.startswith("---"):
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                html_lines.append("<hr/>")
            else:
                if in_list:
                    html_lines.append("</ul>")
                    in_list = False
                content = html.escape(line)
                content = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", content)
                content = re.sub(r"\*(.*?)\*", r"<em>\1</em>", content)
                content = re.sub(r"\[(\d+)\]", r"<sup class='cite-tag'>[\1]</sup>", content)
                html_lines.append(f"<p>{content}</p>")

        if in_list:
            html_lines.append("</ul>")
        return "\n".join(html_lines)

    body_html = simple_md_to_html(result_text)

    # References list
    ref_items = []
    for s in sorted(sources, key=lambda x: x.citation_id):
        apa = format_apa7(s)
        # Linkify URL
        if s.url:
            apa = apa.replace(s.url, f"<a href='{html.escape(s.url)}' target='_blank'>{html.escape(s.url)}</a>")
        badge = f"<span class='badge badge-{s.metadata_confidence}'>{s.metadata_confidence.upper()}</span>"
        ref_items.append(f"<li id='ref-{s.citation_id}'><strong>[{s.citation_id}]</strong> {apa} {badge}</li>")

    refs_html = "".join(ref_items) if ref_items else "<li>No external sources cited.</li>"

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Báo cáo nghiên cứu — {safe_question[:50]}</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&display=swap');

        body {{
            font-family: 'Newsreader', Georgia, serif;
            font-size: 18px;
            line-height: 1.7;
            color: #1a1a1a;
            background-color: #ffffff;
            margin: 0;
            padding: 40px 20px;
        }}

        .container {{
            max-width: 820px;
            margin: 0 auto;
        }}

        .header {{
            font-family: 'Inter', sans-serif;
            border-bottom: 2px solid #eaeaea;
            padding-bottom: 24px;
            margin-bottom: 32px;
        }}

        .title {{
            font-size: 28px;
            font-weight: 700;
            color: #111;
            margin: 0 0 12px 0;
            line-height: 1.3;
        }}

        .meta-bar {{
            display: flex;
            gap: 16px;
            font-size: 13px;
            color: #666;
            flex-wrap: wrap;
        }}

        .meta-item strong {{
            color: #333;
        }}

        h1, h2, h3, h4 {{
            font-family: 'Inter', sans-serif;
            color: #111;
            margin-top: 36px;
            margin-bottom: 14px;
        }}

        h1 {{ font-size: 24px; border-bottom: 1px solid #eee; padding-bottom: 8px; }}
        h2 {{ font-size: 20px; }}
        h3 {{ font-size: 17px; }}

        p {{
            margin: 0 0 16px 0;
        }}

        ul {{
            padding-left: 24px;
            margin-bottom: 18px;
        }}

        li {{
            margin-bottom: 8px;
        }}

        hr {{
            border: none;
            border-top: 1px solid #eee;
            margin: 32px 0;
        }}

        .cite-tag {{
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 600;
            color: #1a73e8;
            margin-left: 2px;
        }}

        .references-section {{
            margin-top: 48px;
            padding-top: 24px;
            border-top: 2px solid #111;
        }}

        .references-list {{
            list-style: none;
            padding: 0;
        }}

        .references-list li {{
            font-size: 15px;
            line-height: 1.6;
            margin-bottom: 14px;
            padding-left: 28px;
            text-indent: -28px;
            color: #333;
        }}

        .references-list a {{
            color: #1a73e8;
            text-decoration: none;
            word-break: break-all;
        }}

        .references-list a:hover {{
            text-decoration: underline;
        }}

        .badge {{
            font-family: 'Inter', sans-serif;
            font-size: 10px;
            font-weight: 600;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 6px;
            vertical-align: middle;
        }}

        .badge-high {{ background: #e6f4ea; color: #137333; }}
        .badge-medium {{ background: #fef7e0; color: #b06000; }}
        .badge-low {{ background: #f1f3f4; color: #5f6368; }}

        .footer {{
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            color: #888;
            text-align: center;
            margin-top: 60px;
            border-top: 1px solid #eee;
            padding-top: 20px;
        }}

        @media print {{
            body {{ padding: 0; font-size: 15px; }}
            .container {{ max-width: 100%; }}
            .header {{ border-bottom-color: #000; }}
            a {{ color: #000 !important; text-decoration: none !important; }}
            .badge {{ border: 1px solid #ccc; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1 class="title">Báo cáo nghiên cứu học thuật</h1>
            <div class="meta-bar">
                <div class="meta-item"><strong>Câu hỏi:</strong> {safe_question}</div>
                <div class="meta-item"><strong>Mô hình:</strong> <code>{safe_model}</code></div>
                <div class="meta-item"><strong>Nguồn trích dẫn:</strong> {len(sources)} tài liệu</div>
            </div>
        </div>

        <div class="content">
            {body_html}
        </div>

        <div class="references-section">
            <h2>Tài liệu tham khảo (References - APA 7)</h2>
            <ul class="references-list">
                {refs_html}
            </ul>
        </div>

        <div class="footer">
            Báo cáo được tạo tự động bởi <strong>Universal Research v0.4</strong> &middot; Xác minh bằng chứng bởi Gemini AI &amp; OpenAlex/Crossref
        </div>
    </div>
</body>
</html>
"""
