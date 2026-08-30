import os
import io
import streamlit as st
from google import genai
from google.genai import types

import citations
from citations import Source
import enrichment

st.set_page_config(page_title="Universal Research", layout="wide")

st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    .stTextArea textarea {
        border-radius: 8px;
        border: 1px solid #E0E0E0;
        padding: 12px;
        font-size: 16px;
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        padding: 0.5rem 2rem;
    }
    h1 {
        font-weight: 600 !important;
        margin-bottom: 0.25rem !important;
        letter-spacing: -0.02em;
    }
    .subtitle {
        color: #888;
        font-size: 1rem;
        margin-bottom: 2rem;
    }
    .model-badge {
        display: inline-block;
        background: #f0f0f0;
        color: #555;
        font-size: 0.75rem;
        padding: 2px 8px;
        border-radius: 12px;
        font-family: monospace;
    }
</style>
""", unsafe_allow_html=True)

def get_api_key():
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")

def get_skill_content():
    """Load the canonical SKILL.md from research/SKILL.md (one level up from app.py)."""
    app_dir = os.path.dirname(os.path.abspath(__file__))
    skill_path = os.path.normpath(os.path.join(app_dir, "..", "SKILL.md"))
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            content = f.read()
        if not content.strip():
            st.error(f"SKILL.md loaded from {skill_path} but is empty.")
            return None
        return content
    except FileNotFoundError:
        st.error(f"SKILL.md not found at: {skill_path}\nExpected canonical path: research/SKILL.md")
        return None
    except Exception as e:
        st.error(f"Could not load SKILL.md: {e}")
        return None

# Models to try WITH Google Search (requires v1beta, newer models only)
MODELS_WITH_SEARCH = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

# Models to try WITHOUT search (broader compatibility)
MODELS_NO_SEARCH = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
    "gemini-1.0-pro",
]

def run_research(client, skill_content, prompt, use_search=True):
    """
    Try candidate models in order.
    Returns (response_text, model_used, sources, references_markdown, citations_inserted).
    """
    model_list = MODELS_WITH_SEARCH if use_search else MODELS_NO_SEARCH
    tools = [{"google_search": {}}] if use_search else []
    errors = []

    for model in model_list:
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=skill_content,
                    tools=tools,
                    temperature=0.2,
                ),
            )
            
            raw_chunks = None
            raw_supports = None
            try:
                meta = response.candidates[0].grounding_metadata
                raw_chunks = getattr(meta, "grounding_chunks", None)
                raw_supports = getattr(meta, "grounding_supports", None)
            except Exception:
                pass

            sources, chunk_map = citations.build_source_list(raw_chunks)

            # v0.3: Enrich sources with academic metadata (Crossref / OpenAlex)
            # Sources without detectable DOIs are returned unchanged.
            sources = enrichment.enrich_sources(sources)

            annotated_text, inserted = citations.annotate_text_with_citations(
                response.text, raw_supports, chunk_map
            )
            ref_markdown = citations.build_references_markdown(sources)

            return annotated_text, model, sources, ref_markdown, inserted

        except Exception as e:
            errors.append(f"{model}: {e}")
            continue  # Always try next model regardless of error type

    # All models with search failed — retry without search
    if use_search:
        st.info("ℹ️ Web search unavailable; falling back to knowledge-base analysis.")
        return run_research(client, skill_content, prompt, use_search=False)

    raise RuntimeError(
        "All models exhausted. This may be a daily quota limit on your free tier API key. "
        "Details:\n" + "\n".join(errors)
    )

def build_markdown_report(question, result_text, model_used, sources, ref_markdown):
    lines = [
        "# Research Report\n",
        f"**Question:** {question}\n",
        f"**Model:** `{model_used}`\n",
        "---\n",
        result_text,
    ]
    if ref_markdown and "## References" not in result_text:
        lines.extend(["\n", ref_markdown])
    elif sources and "## References" not in result_text:
        lines.append("\n---\n## Sources Referenced\n")
        for s in sources:
            apa = citations.format_apa7(s)
            lines.append(f"[{s.citation_id}] {apa}")
    return "\n".join(lines)

from datetime import datetime

def main():
    st.markdown("<h1>Universal Research</h1>", unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Evidence-based analysis · Universal Research Skill v0.3.5 — Academic Enrichment & Session Hub</div>', unsafe_allow_html=True)

    api_key = get_api_key()
    if not api_key:
        st.error("API Key not configured. Set `GEMINI_API_KEY` in Streamlit Secrets (cloud) or `.env` (local).")
        st.stop()

    skill_content = get_skill_content()
    if not skill_content:
        st.stop()

    client = genai.Client(api_key=api_key)

    # Initialize session history
    if "history" not in st.session_state:
        st.session_state["history"] = []
    if "active_report" not in st.session_state:
        st.session_state["active_report"] = None

    with st.sidebar:
        st.markdown("### Settings")
        depth = st.radio("Analysis Depth", ["Quick Summary", "Standard", "Deep Dive"], index=1)
        
        mode = st.selectbox(
            "Research Focus",
            [
                "🌐 Toàn diện (Web + Học thuật)",
                "🎓 Học thuật chuyên sâu (Peer-reviewed)",
                "⚡ Tóm tắt điều hành (Executive)",
            ],
            index=0,
        )

        st.markdown("---")
        st.markdown("### Citation Settings")
        citation_style = st.selectbox("Citation Style", ["APA 7"], index=0)
        st.markdown("---")

        # Session History section
        st.markdown("### 📜 Lịch sử phiên")
        if st.session_state["history"]:
            for idx, item in enumerate(reversed(st.session_state["history"])):
                q_snippet = (item['question'][:30] + "…") if len(item['question']) > 30 else item['question']
                time_str = item.get("timestamp", "")
                if st.button(f"📄 {q_snippet}", key=f"hist_{idx}", help=f"{time_str}\n{item['question']}"):
                    st.session_state["active_report"] = item

            if st.button("🗑️ Xóa lịch sử", type="secondary"):
                st.session_state["history"] = []
                st.session_state["active_report"] = None
                st.rerun()
        else:
            st.markdown("<small style='color:#888'>Chưa có báo cáo nào trong phiên này.</small>", unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<small>Universal Research &middot; <code>v0.4</code></small>", unsafe_allow_html=True)

    question = st.text_area(
        "",
        placeholder="Enter your research question…",
        height=120,
    )

    col1, col2 = st.columns([1, 5])
    run_clicked = col1.button("Run Analysis", type="primary")

    if run_clicked:
        if not question.strip():
            st.warning("Please enter a research question.")
            return

        depth_prompt = {
            "Quick Summary": "Provide a concise, well-structured summary.",
            "Standard": "Perform a standard, balanced research analysis.",
            "Deep Dive": "Perform a deep, comprehensive analysis with detailed synthesis of evidence, methodology, and limitations.",
        }.get(depth, "")

        mode_constraint = ""
        if "Học thuật" in mode:
            mode_constraint = (
                "Academic Focus Requirement: Prioritize peer-reviewed scientific studies, working papers, "
                "institutional data (IMF, World Bank, OECD, WHO), and empirical datasets. "
                "Explicitly emphasize methodology, sample sizes, and empirical consensus."
            )
        elif "Tóm tắt" in mode:
            mode_constraint = (
                "Executive Focus Requirement: Prioritize actionable insights, core key performance indicators, "
                "strategic takeaways, and concise bullet points for decision makers."
            )

        full_prompt = (
            f"Research Task: {question}\n\n"
            f"Depth constraint: {depth_prompt}\n"
            f"{mode_constraint}\n\n"
            "Output your response in Markdown using this structure: "
            "Executive Summary, Key Findings, Evidence & Sources, "
            "Contradictory/Uncertain Evidence, Analysis, Conclusion, Limitations. "
            "Adapt the structure if the question warrants a different format."
        )

        with st.spinner("Analyzing…"):
            try:
                result_text, model_used, sources, ref_markdown, inserted = run_research(
                    client, skill_content, full_prompt
                )

                # Save to history
                report_data = {
                    "question": question,
                    "result_text": result_text,
                    "model_used": model_used,
                    "sources": sources,
                    "ref_markdown": ref_markdown,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }
                st.session_state["history"].append(report_data)
                st.session_state["active_report"] = report_data

            except RuntimeError as e:
                st.warning(str(e))
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    # Render active report if available
    active = st.session_state.get("active_report")
    if active:
        st.markdown("---")
        st.markdown(
            f"**Research Report** · <span class='model-badge'>{active['model_used']}</span> · <small style='color:#888'>{active.get('timestamp', '')}</small>",
            unsafe_allow_html=True,
        )
        st.markdown(f"**Question:** *{active['question']}*")

        tab_report, tab_sources = st.tabs(["📄 Báo cáo (Report)", "🔍 Nguồn & Độ tin cậy (Sources & Integrity)"])

        with tab_report:
            st.markdown(active["result_text"])

            if active.get("ref_markdown") and "## References" not in active["result_text"]:
                st.markdown("---")
                st.markdown(active["ref_markdown"])

        with tab_sources:
            sources_list = active.get("sources", [])
            if sources_list:
                st.markdown(f"**Tổng số nguồn xác minh:** `{len(sources_list)}` tài liệu")
                for s in sorted(sources_list, key=lambda x: x.citation_id):
                    conf_color = {
                        "high": "🟢 **Độ tin cậy: Cao (DOI Verified)**",
                        "medium": "🟡 **Độ tin cậy: Trung bình (Title Verified)**",
                        "low": "⚪ **Độ tin cậy: Cơ bản (Web Grounding)**",
                    }.get(s.metadata_confidence, "⚪ Cơ bản")

                    with st.expander(f"[{s.citation_id}] {s.title or s.url or 'Nguồn không tên'}"):
                        st.markdown(f"- {conf_color}")
                        if s.author:
                            st.markdown(f"- **Tác giả:** {s.author}")
                        if s.year:
                            st.markdown(f"- **Năm xuất bản:** {s.year}")
                        if s.journal:
                            st.markdown(f"- **Tạp chí / Xuất bản:** *{s.journal}*")
                        if s.doi:
                            st.markdown(f"- **DOI:** [{s.doi}](https://doi.org/{s.doi})")
                        if s.url:
                            st.markdown(f"- **URL:** [{s.url}]({s.url})")
                        if s.domain:
                            st.markdown(f"- **Domain:** `{s.domain}`")
            else:
                st.info("Không có nguồn trích dẫn trực tiếp nào được liên kết.")

        # Export section
        st.markdown("---")
        col_dl1, col_dl2 = st.columns([1, 1])

        # Markdown Export
        md_report = build_markdown_report(
            active["question"],
            active["result_text"],
            active["model_used"],
            active.get("sources", []),
            active.get("ref_markdown", ""),
        )
        col_dl1.download_button(
            label="📥 Tải Markdown (.md)",
            data=md_report.encode("utf-8"),
            file_name="research-report.md",
            mime="text/markdown",
        )

        # HTML / Print PDF Export
        html_report = citations.build_html_report(
            active["question"],
            active["result_text"],
            active["model_used"],
            active.get("sources", []),
            active.get("ref_markdown", ""),
        )
        col_dl2.download_button(
            label="🖨️ Tải HTML / In PDF (.html)",
            data=html_report.encode("utf-8"),
            file_name="research-report.html",
            mime="text/html",
        )

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()



