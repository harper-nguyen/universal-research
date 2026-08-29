import os
import io
import streamlit as st
from google import genai
from google.genai import types

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

# Models to try in priority order (most capable first)
CANDIDATE_MODELS = [
    "gemini-3.6-flash",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
]

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
    """Try candidate models in order. Returns (response_text, model_used, sources)."""
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
            # Extract sources
            sources = []
            try:
                chunks = response.candidates[0].grounding_metadata.grounding_chunks
                for chunk in (chunks or []):
                    if hasattr(chunk, "web") and chunk.web:
                        sources.append({"title": chunk.web.title, "uri": chunk.web.uri})
            except Exception:
                pass
            return response.text, model, sources
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

def build_markdown_report(question, result_text, model_used, sources):
    lines = [
        f"# Research Report\n",
        f"**Question:** {question}\n",
        f"**Model:** `{model_used}`\n",
        "---\n",
        result_text,
    ]
    if sources:
        lines.append("\n---\n## Sources Referenced\n")
        for s in sources:
            lines.append(f"- [{s['title']}]({s['uri']})")
    return "\n".join(lines)

def main():
    st.markdown("<h1>Universal Research</h1>", unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Evidence-based analysis · Universal Research Skill v0.1.1</div>', unsafe_allow_html=True)

    api_key = get_api_key()
    if not api_key:
        st.error("API Key not configured. Set `GEMINI_API_KEY` in Streamlit Secrets (cloud) or `.env` (local).")
        st.stop()

    skill_content = get_skill_content()
    if not skill_content:
        st.stop()

    client = genai.Client(api_key=api_key)

    with st.sidebar:
        st.markdown("### Settings")
        depth = st.radio("Analysis Depth", ["Quick Summary", "Standard", "Deep Dive"], index=1)
        st.markdown("---")
        st.markdown("<small>Skill: <code>universal-research v0.1.1</code></small>", unsafe_allow_html=True)
        st.markdown("<small>Models: auto-selected</small>", unsafe_allow_html=True)

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

        full_prompt = (
            f"Research Task: {question}\n\n"
            f"Depth constraint: {depth_prompt}\n\n"
            "Output your response in Markdown using this structure: "
            "Executive Summary, Key Findings, Evidence & Sources, "
            "Contradictory/Uncertain Evidence, Analysis, Conclusion, Limitations. "
            "Adapt the structure if the question warrants a different format."
        )

        with st.spinner("Analyzing…"):
            try:
                result_text, model_used, sources = run_research(client, skill_content, full_prompt)

                st.markdown("---")
                st.markdown(
                    f"**Analysis complete** · <span class='model-badge'>{model_used}</span>",
                    unsafe_allow_html=True,
                )
                st.markdown("### Report")
                st.markdown(result_text)

                if sources:
                    st.markdown("#### Sources referenced")
                    for s in sources:
                        st.markdown(
                            f"<small>· <a href='{s['uri']}' target='_blank' style='color:#666;text-decoration:none'>{s['title']}</a></small>",
                            unsafe_allow_html=True,
                        )

                # Export button
                md_report = build_markdown_report(question, result_text, model_used, sources)
                st.download_button(
                    label="Download report (.md)",
                    data=md_report.encode("utf-8"),
                    file_name="research-report.md",
                    mime="text/markdown",
                )

            except RuntimeError as e:
                st.warning(str(e))
            except Exception as e:
                st.error(f"Unexpected error: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()
