import os
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
        margin-bottom: 0.5rem !important;
        letter-spacing: -0.02em;
    }
    .subtitle {
        color: #666666;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

def get_api_key():
    """Read API key from st.secrets (Streamlit Cloud) or environment variable (local)."""
    try:
        return st.secrets["GEMINI_API_KEY"]
    except Exception:
        return os.environ.get("GEMINI_API_KEY", "")

def get_skill_content():
    """Load SKILL.md from the same directory as app.py."""
    skill_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SKILL.md")
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        st.error(f"Could not load SKILL.md. Ensure it exists at: {skill_path}")
        return None

def main():
    st.markdown("<h1>Universal Research</h1>", unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Evidence-based analysis driven by the Universal Research Skill.</div>', unsafe_allow_html=True)

    api_key = get_api_key()
    if not api_key:
        st.error("API Key not found. Set GEMINI_API_KEY in Streamlit Secrets (cloud) or in your .env file (local).")
        st.stop()

    skill_content = get_skill_content()
    if not skill_content:
        st.stop()

    client = genai.Client(api_key=api_key)

    with st.sidebar:
        st.markdown("### Settings")
        depth = st.radio("Analysis Depth", ["Quick Summary", "Standard", "Deep Dive"], index=1)
        st.markdown("---")
        st.markdown("<small>System Engine: <code>universal-research v0.1.1</code></small>", unsafe_allow_html=True)

    question = st.text_area(
        "",
        placeholder="Enter your research question (e.g., What are the main factors affecting FDI in developing countries?)",
        height=120
    )

    if st.button("Run Analysis", type="primary"):
        if not question.strip():
            st.warning("Please enter a research question.")
            return

        depth_prompt = {
            "Quick Summary": "Perform a quick analysis. Provide a concise, well-structured summary.",
            "Standard": "Perform a standard, balanced research analysis.",
            "Deep Dive": "Perform a deep, comprehensive analysis with detailed synthesis of evidence, methodology, and limitations.",
        }.get(depth, "")

        full_prompt = (
            f"Research Task: {question}\n\n"
            f"Constraints: {depth_prompt}\n\n"
            "Output your response in Markdown using this structure: "
            "Executive Summary, Key Findings, Evidence & Sources, "
            "Contradictory/Uncertain Evidence, Analysis, Conclusion, Limitations. "
            "Adapt the structure if the question warrants a different format."
        )

        with st.spinner("Analyzing..."):
            try:
                response = client.models.generate_content(
                    model="gemini-2.0-flash",
                    contents=full_prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=skill_content,
                        tools=[{"google_search": {}}],
                        temperature=0.2,
                    ),
                )

                st.markdown("---")
                st.markdown("### Analysis Report")
                st.markdown(response.text)

                # Sources from Google Search grounding
                try:
                    chunks = response.candidates[0].grounding_metadata.grounding_chunks
                    if chunks:
                        st.markdown("#### Sources referenced")
                        for chunk in chunks:
                            if hasattr(chunk, "web") and chunk.web:
                                st.markdown(
                                    f"<small>• <a href='{chunk.web.uri}' target='_blank' "
                                    f"style='color:#666; text-decoration:none;'>{chunk.web.title}</a></small>",
                                    unsafe_allow_html=True,
                                )
                except Exception:
                    pass

            except Exception as e:
                st.error(f"Analysis failed: {e}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    main()

