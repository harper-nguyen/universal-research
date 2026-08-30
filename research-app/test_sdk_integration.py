"""
test_sdk_integration.py — End-to-End SDK Integration Audit Test

Uses real google.genai.types Pydantic model instances to test citations.py
and app.py integration without needing a live network API call.
"""

import sys
from google.genai import types
import citations
from app import build_markdown_report

print("=== End-to-End SDK Integration Audit Test ===")

# Construct actual google.genai.types instances
chunk_1 = types.GroundingChunk(
    web=types.GroundingChunkWeb(
        title="IMF World Economic Outlook 2024",
        uri="https://www.imf.org/en/Publications/WEO/Issues/2024/04/16/world-economic-outlook-april-2024",
        domain="imf.org",
    )
)

chunk_2 = types.GroundingChunk(
    web=types.GroundingChunkWeb(
        title="World Bank FDI Data",
        uri="https://data.worldbank.org/indicator/BX.KGV.DINV.WD.GD.ZS",
        domain="worldbank.org",
    )
)

# Duplicate chunk (same normalized URL as chunk_1)
chunk_3 = types.GroundingChunk(
    web=types.GroundingChunkWeb(
        title="IMF WEO April 2024 Report",
        uri="https://www.imf.org/en/Publications/WEO/Issues/2024/04/16/world-economic-outlook-april-2024/",
        domain="imf.org",
    )
)

raw_chunks = [chunk_1, chunk_2, chunk_3]

# Grounding supports using real google.genai.types instances
text_sample = "Global foreign direct investment showed moderate recovery in 2024. Developing economies faced mixed capital inflow trends."

support_1 = types.GroundingSupport(
    segment=types.Segment(
        start_index=0,
        end_index=66, # Exact end of "Global foreign direct investment showed moderate recovery in 2024."
        text="Global foreign direct investment showed moderate recovery in 2024.",
    ),
    grounding_chunk_indices=[0, 2], # chunks 0 & 2 (both map to citation 1)
    confidence_scores=[0.95, 0.92],
)

support_2 = types.GroundingSupport(
    segment=types.Segment(
        start_index=67,
        end_index=123, # Exact end of "Developing economies faced mixed capital inflow trends."
        text="Developing economies faced mixed capital inflow trends.",
    ),
    grounding_chunk_indices=[1], # chunk 1 (maps to citation 2)
    confidence_scores=[0.88],
)

raw_supports = [support_1, support_2]

# Step 1: Build source list
sources, chunk_map = citations.build_source_list(raw_chunks)
print(f"1. Sources count: {len(sources)} (Expected: 2 after deduplication)")
print(f"   Chunk index map: {chunk_map}")
assert len(sources) == 2, f"Expected 2 sources, got {len(sources)}"
assert chunk_map[0] == 1 and chunk_map[2] == 1, "Duplicate URL chunk 2 should map to citation 1"
assert chunk_map[1] == 2, "Chunk 1 should map to citation 2"

# Step 2: Annotate text with citations
annotated_text, inserted = citations.annotate_text_with_citations(
    text_sample, raw_supports, chunk_map
)
print(f"2. Inline citations inserted: {inserted}")
print(f"   Annotated text:\n   {annotated_text}")
assert inserted is True, "Citations should be inserted"
assert "in 2024.[1] Developing" in annotated_text, "Citation [1] placed correctly"
assert "inflow trends.[2]" in annotated_text, "Citation [2] placed correctly"

# Step 3: Build references markdown
ref_markdown = citations.build_references_markdown(sources)
print(f"3. References Markdown:\n{ref_markdown}")
assert "[1] IMF World Economic Outlook 2024. imf.org." in ref_markdown
assert "[2] World Bank FDI Data. data.worldbank.org." in ref_markdown

# Step 4: Build final exported markdown report
report_markdown = build_markdown_report(
    question="What are recent FDI trends?",
    result_text=annotated_text,
    model_used="gemini-3.6-flash",
    sources=sources,
    ref_markdown=ref_markdown,
)

print(f"4. Final Exported Report:\n{report_markdown}")
assert "# Research Report" in report_markdown
assert "in 2024.[1]" in report_markdown
assert "inflow trends.[2]" in report_markdown
assert "## References" in report_markdown

print("\n✅ ALL SDK INTEGRATION AUDIT TESTS PASSED!")
