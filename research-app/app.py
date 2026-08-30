import os
import io
import streamlit as st
from datetime import datetime
from typing import Optional, List, Dict
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
        padding: 0.5rem 1.5rem;
    }
    h1 {
        font-weight: 600 !important;
        margin-bottom: 0.25rem !important;
        letter-spacing: -0.02em;
    }
    .subtitle {
        color: #888;
        font-size: 1rem;
        margin-bottom: 1.5rem;
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
    .metric-card {
        background: #f8f9fa;
        border: 1px solid #e9ecef;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 12px;
    }
    .metric-title {
        font-size: 0.8rem;
        color: #6c757d;
        text-transform: uppercase;
        font-weight: 600;
    }
    .metric-val {
        font-size: 1.4rem;
        font-weight: 700;
        color: #212529;
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

# Models to try WITH Google Search
MODELS_WITH_SEARCH = [
    "gemini-3.6-flash",
    "gemini-3.6-pro",
    "gemini-2.5-flash",
    "gemini-2.0-flash-exp",
    "gemini-1.5-flash-latest",
]

# Models to try WITHOUT search (broader compatibility)
MODELS_NO_SEARCH = [
    "gemini-3.6-flash",
    "gemini-3.6-pro",
    "gemini-1.5-flash-latest",
    "gemini-1.5-pro-latest",
]

def run_research(
    client,
    skill_content: str,
    prompt: str,
    use_search: bool = True,
    preferred_model: Optional[str] = None,
    temperature: float = 0.2,
    citation_style: str = "APA 7",
):
    """
    Try candidate models in order.
    Returns (response_text, model_used, sources, references_markdown, citations_inserted).
    """
    base_list = MODELS_WITH_SEARCH if use_search else MODELS_NO_SEARCH
    
    # Place preferred model first if specified
    if preferred_model and preferred_model in base_list:
        model_list = [preferred_model] + [m for m in base_list if m != preferred_model]
    else:
        model_list = base_list

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
                    temperature=temperature,
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

            # v0.3+: Enrich sources with academic metadata (Crossref / OpenAlex / Semantic Scholar)
            sources = enrichment.enrich_sources(sources)

            annotated_text, inserted = citations.annotate_text_with_citations(
                response.text, raw_supports, chunk_map
            )
            ref_markdown = citations.build_references_markdown(sources, style=citation_style)

            return annotated_text, model, sources, ref_markdown, inserted

        except Exception as e:
            errors.append(f"{model}: {e}")
            continue

    # Fallback to no-search if search models failed
    if use_search:
        st.info("ℹ️ Web search unavailable; falling back to knowledge-base analysis.")
        return run_research(
            client,
            skill_content,
            prompt,
            use_search=False,
            preferred_model=preferred_model,
            temperature=temperature,
            citation_style=citation_style,
        )

    raise RuntimeError(
        "All models exhausted. Details:\n" + "\n".join(errors)
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


def main():
    st.markdown("<h1>Universal Research</h1>", unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Advanced Evidence-Based Research &amp; Academic Intelligence Hub &middot; <code>v0.5</code></div>', unsafe_allow_html=True)

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
        st.markdown("### Cài đặt nghiên cứu")
        mode = st.radio(
            "Chế độ phân tích",
            [
                "🌐 Tiêu chuẩn (Standard)",
                "🎓 Học thuật chuyên sâu (Deep Academic)",
                "⚡ Tóm tắt điều hành (Executive Brief)",
            ],
            index=0,
            help="Chọn mức độ chi tiết và định hướng trọng tâm của báo cáo",
        )

        st.markdown("---")
        # Session History section
        st.markdown("### 📜 Lịch sử phiên")
        if st.session_state["history"]:
            for idx, item in enumerate(reversed(st.session_state["history"])):
                q_snippet = (item['question'][:28] + "…") if len(item['question']) > 28 else item['question']
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
        st.markdown("<small>Universal Research &middot; <code>v0.5</code></small>", unsafe_allow_html=True)


    question = st.text_area(
        "",
        placeholder="Enter your research question… (ví dụ: Tác động của chính sách thuế tối thiểu toàn cầu đến FDI tại các nước đang phát triển)",
        height=120,
    )

    col1, col2 = st.columns([1, 5])
    run_clicked = col1.button("Run Analysis", type="primary")

    if run_clicked:
        if not question.strip():
            st.warning("Please enter a research question.")
            return
        if "Học thuật" in mode:
            mode_constraint = (
                "CHẾ ĐỘ: PHÂN TÍCH HỌC THUẬT CHUYÊN SÂU (ACADEMIC DEEP DIVE).\n"
                "YÊU CẦU NGHIÊN CỨU & TRÍCH DẪN:\n"
                "1. Chủ động tìm kiếm và trích dẫn trực tiếp các bài báo khoa học đã xuất bản, nghiên cứu có bình duyệt (peer-reviewed), "
                "bài báo từ Google Scholar, Nature, ScienceDirect, Springer, JSTOR, PubMed, arXiv, SSRN, NBER, và báo cáo từ các tổ chức uy tín (IMF, World Bank, OECD, WHO).\n"
                "2. Với mỗi luận điểm quan trọng, phải dẫn rõ tên tác giả, năm công bố, tên tạp chí và link/DOI của nghiên cứu.\n"
                "3. Nêu rõ phương pháp luận, số liệu thực nghiệm và đối chiếu các kết quả nghiên cứu mâu thuẫn."
            )
        elif "Tóm tắt" in mode:
            mode_constraint = (
                "Chế độ: Tóm tắt điều hành (Executive Summary).\n"
                "Yêu cầu: Ngắn gọn, súc tích, tập trung vào các phát hiện then chốt, chỉ số định lượng cốt lõi và bài học chiến lược."
            )
        else:
            mode_constraint = (
                "Chế độ: Nghiên cứu tiêu chuẩn (Standard Research).\n"
                "Yêu cầu: Khách quan, cân bằng, bao quát toàn diện các khía cạnh của chủ đề kèm dẫn chứng xác minh."
            )

        full_prompt = (
            f"Nhiệm vụ nghiên cứu: {question}\n\n"
            f"{mode_constraint}\n\n"
            "Cấu trúc báo cáo bằng Markdown gồm: "
            "Tóm tắt tổng quan, Các phát hiện chính, Bằng chứng & Nguồn số liệu, "
            "Dữ liệu mâu thuẫn/Chưa chắc chắn, Phân tích chuyên sâu, Kết luận, Hạn chế của nghiên cứu. "
            "Có thể điều chỉnh cấu trúc linh hoạt cho phù hợp với nội dung câu hỏi."
        )

        with st.spinner("Đang nghiên cứu & xác minh nguồn dữ liệu…"):
            try:
                result_text, model_used, sources, ref_markdown, inserted = run_research(
                    client=client,
                    skill_content=skill_content,
                    prompt=full_prompt,
                    preferred_model=None,
                    temperature=0.2,
                    citation_style="APA 7",
                )

                # Save to history
                report_data = {
                    "question": question,
                    "result_text": result_text,
                    "model_used": model_used,
                    "sources": sources,
                    "ref_markdown": ref_markdown,
                    "citation_style": "APA 7",
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                    "followups": [],
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

        # Key Metrics Fact Box
        sources_list = active.get("sources", [])
        acad_count = sum(1 for s in sources_list if s.source_type == "academic" or s.doi or s.author)
        high_conf_count = sum(1 for s in sources_list if s.metadata_confidence in ("high", "medium"))
        
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            st.markdown(f"<div class='metric-card'><div class='metric-title'>Tổng số nguồn</div><div class='metric-val'>{len(sources_list)}</div></div>", unsafe_allow_html=True)
        with mcol2:
            st.markdown(f"<div class='metric-card'><div class='metric-title'>Nguồn học thuật</div><div class='metric-val'>{acad_count}</div></div>", unsafe_allow_html=True)
        with mcol3:
            st.markdown(f"<div class='metric-card'><div class='metric-title'>Đã xác minh DOI/Title</div><div class='metric-val'>{high_conf_count}</div></div>", unsafe_allow_html=True)
        with mcol4:
            st.markdown("<div class='metric-card'><div class='metric-title'>Chuẩn trích dẫn</div><div class='metric-val'>APA 7</div></div>", unsafe_allow_html=True)

        tab_report, tab_sources, tab_markdown = st.tabs([
            "📄 Báo cáo (Report)",
            "🔍 Nguồn & Bằng chứng (Evidence Audit)",
            "📋 Mã Markdown (Xem & Copy)",
        ])

        with tab_report:
            st.markdown(active["result_text"])

            # Render follow-up additions if any
            for fup in active.get("followups", []):
                st.markdown(f"### 💬 Đào sâu tiếp nối: {fup['question']}")
                st.markdown(f"<small style='color:#888'>Bổ sung bởi {fup['model_used']} lúc {fup['timestamp']}</small>", unsafe_allow_html=True)
                st.markdown(fup["text"])

            if active.get("ref_markdown") and "## References" not in active["result_text"]:
                st.markdown("---")
                st.markdown(active["ref_markdown"])

        with tab_sources:
            if sources_list:
                st.markdown(f"**Danh sách tài liệu xác minh ({len(sources_list)} nguồn):**")
                for s in sorted(sources_list, key=lambda x: x.citation_id):
                    conf_color = {
                        "high": "🟢 **Độ tin cậy: Cao (DOI Verified)**",
                        "medium": "🟡 **Độ tin cậy: Trung bình (Title Match)**",
                        "low": "⚪ **Độ tin cậy: Cơ bản (Web Grounding)**",
                    }.get(s.metadata_confidence, "⚪ Cơ bản")

                    highly_cited_tag = " 🔥 **Highly Cited Paper**" if s.is_highly_cited else ""
                    cite_cnt_str = f" · **Trích dẫn:** `{s.citation_count}` lượt" if s.citation_count is not None else ""

                    with st.expander(f"[{s.citation_id}] {s.title or s.url or 'Nguồn không tên'}{highly_cited_tag}"):
                        st.markdown(f"- {conf_color}{cite_cnt_str}")
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

        with tab_markdown:
            st.markdown("##### 📋 Mã nguồn Markdown đầy đủ (Nhấn biểu tượng Copy góc trên bên phải khung):")
            raw_md = build_markdown_report(
                active["question"],
                active["result_text"],
                active["model_used"],
                active.get("sources", []),
                active.get("ref_markdown", ""),
            )
            st.code(raw_md, language="markdown")


        # Interactive Follow-up Research Section
        st.markdown("---")
        st.markdown("### 💬 Đào sâu tiếp nối (Follow-up Deep Dive)")
        with st.form("followup_form", clear_on_submit=True):
            fup_query = st.text_input(
                "Hỏi thêm về báo cáo này:",
                placeholder="Ví dụ: Phân tích kỹ hơn số liệu ở mục 2, hoặc so sánh với trường hợp của Việt Nam...",
            )
            fup_submit = st.form_submit_button("Gửi câu hỏi tiếp nối")

            if fup_submit and fup_query.strip():
                fup_prompt = (
                    f"Bối cảnh báo cáo trước đó:\n"
                    f"Câu hỏi gốc: {active['question']}\n"
                    f"Nội dung tóm tắt: {active['result_text'][:1200]}...\n\n"
                    f"Yêu cầu đào sâu tiếp nối của người dùng: {fup_query}\n\n"
                    "Hãy thực hiện phân tích cụ thể, tập trung đúng vào yêu cầu tiếp nối này, "
                    "nêu rõ bằng chứng và số liệu hỗ trợ."
                )
                with st.spinner("Đang nghiên cứu và đào sâu nội dung…"):
                    try:
                        fup_text, fup_model, fup_sources, _, _ = run_research(
                            client=client,
                            skill_content=skill_content,
                            prompt=fup_prompt,
                            preferred_model=selected_model,
                            temperature=temperature,
                            citation_style=citation_style,
                        )
                        active["followups"].append({
                            "question": fup_query,
                            "text": fup_text,
                            "model_used": fup_model,
                            "timestamp": datetime.now().strftime("%H:%M:%S"),
                        })
                        st.rerun()
                    except Exception as e:
                        st.error(f"Lỗi khi thực hiện phân tích tiếp nối: {e}")

        # Triple Export section
        st.markdown("---")
        st.markdown("#### 📥 Xuất báo cáo (Export Options)")
        col_dl1, col_dl2, col_dl3 = st.columns(3)

        # 1. Markdown Export
        md_report = build_markdown_report(
            active["question"],
            active["result_text"],
            active["model_used"],
            active.get("sources", []),
            active.get("ref_markdown", ""),
        )
        col_dl1.download_button(
            label="📄 Tải Markdown (.md)",
            data=md_report.encode("utf-8"),
            file_name="research-report.md",
            mime="text/markdown",
        )

        # 2. HTML / Print PDF Export
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

        # 3. BibTeX Export
        bib_content = citations.build_bibtex_file(active.get("sources", []))
        col_dl3.download_button(
            label="📜 Tải BibTeX (.bib)",
            data=bib_content.encode("utf-8"),
            file_name="references.bib",
            mime="text/plain",
        )

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
