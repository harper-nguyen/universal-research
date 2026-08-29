# ARCHITECTURE AUDIT
**Universal Research App — v0.1.1**
*Audit date: 2026-08-29*

---

## 1. Current Architecture

```
User submits question (browser)
  → Streamlit UI (app.py :: main())
     → skill_content loaded from SKILL.md (app.py :: get_skill_content(), line 61–68)
     → run_research() called (app.py :: line 86–125)
        → google-genai client.models.generate_content()
           → Gemini API (server-side)
              → google_search grounding executed internally by Google
              → Snippets + grounding_chunks injected into model context
           → Model generates response
        → grounding_chunks (title + URI only) extracted (lines 106–109)
     → result_text + model_used + sources returned to UI
  → Report rendered in Streamlit
  → Download button produces .md export
```

**Files involved:**

| File | Role |
|---|---|
| `research-app/app.py` | Sole application file. All logic lives here. |
| `research-app/SKILL.md` | Behavioral specification. Loaded as `system_instruction`. |
| `research-app/.streamlit/config.toml` | UI theme only. No research logic. |
| `research-app/requirements.txt` | `streamlit`, `google-genai`, `python-dotenv`. No retrieval libraries. |

---

## 2. Actual Research Capability

| Capability | Status | Evidence |
|---|---|---|
| Gemini Google Search Grounding | ✅ Enabled | `tools=[{"google_search": {}}]` — app.py line 89 |
| URL fetching (full page content) | ❌ Not present | No `requests`, `httpx`, `playwright`, or similar in code |
| Academic database retrieval | ❌ Not present | No Semantic Scholar, PubMed, arXiv, or similar API |
| Custom RAG / vector search | ❌ Not present | No embedding, vector DB, or chunking pipeline |
| Model knowledge fallback | ✅ Active | `use_search=False` path — app.py lines 117–120 |

**Critical distinction:**

`google_search` grounding is a **server-side capability of the Gemini API**. Google runs the search query internally, extracts snippets from search results, and injects those snippets into the model's context window. The application does not control which pages are fetched, what content is extracted, or how many tokens per page the model receives. The application receives only the **citation metadata** (title + URL) after the fact.

This is fundamentally different from an agent that fetches URLs, reads full content, and explicitly passes it to the model.

---

## 3. Source Verification

**Short answer: No.**

When the model produces a citation, neither the application nor the model has read the full text of the linked page.

**What actually happens:**
1. Google Search grounding surfaces a set of search results for the query.
2. Google's infrastructure extracts short snippets (~1–3 sentences) from each result.
3. These snippets are injected into the model's context — not the full articles.
4. The model synthesizes a response based on those snippets.
5. The `grounding_chunks` returned to the app contain only `title` and `uri` — no snippet text is surfaced to the application layer.

**Where the limitation sits:**

```
SKILL.md requirement:
  "Verify the source's content actually supports the specific claim."

What the model actually has access to:
  Search snippet (1–3 sentences from each source page)

What the model does NOT have:
  - Full article text
  - Full methodology sections
  - Tables, appendices, or supplementary data
  - The ability to navigate to the URL
```

The model can only verify that the **snippet** supports the claim. Whether the full article does is unknowable within this architecture. The SKILL.md rule is partially satisfied (snippet-level verification) but cannot be fully enforced (full-content verification).

This is not a code defect. It is a structural constraint of the grounding-based approach.

---

## 4. Architecture Options

### Option A — Keep v0.1.1 as-is (Current)

| Dimension | Assessment |
|---|---|
| **How it works** | Gemini Google Search grounding (snippet-level) |
| **Pros** | Zero additional dependencies. Free on Gemini free tier. Already deployed. Simple codebase. |
| **Cons** | Source verification is snippet-level only. No academic database access. App has no control over retrieval. |
| **Cost** | Free (within Gemini API free tier limits) |
| **Complexity** | Low |
| **Reliability** | Medium — depends on Gemini model availability and grounding quality per query |

### Option B — Gemini Native Grounding

This is effectively what Option A already is. Gemini's `google_search` grounding is the only native retrieval mechanism in the current google-genai SDK. There is no "advanced grounding" or "full-page fetch" mode available via the standard API.

### Option C — External Retrieval Layer

Add an independent retrieval step before the model call:

```
User question
  → App fetches search results via external API (e.g. Tavily, SerpAPI)
  → App fetches full page content (requests + trafilatura)
  → App chunks and passes full content to Gemini as context
  → Gemini synthesizes from actual page content
```

| Dimension | Assessment |
|---|---|
| **How it works** | External search API + server-side URL fetching + content chunking |
| **Pros** | Full source content available to model. Genuine claim-to-source verification possible. Academic sources (arXiv, Semantic Scholar) can be added. |
| **Cons** | Additional API keys required. Many pages block scrapers. Paywalled academic content cannot be fetched. Significantly higher complexity. Longer response time (2–5x). |
| **Cost** | Tavily free tier: 1,000 searches/month. Beyond: ~$0.008/search. |
| **Complexity** | High |
| **Reliability** | Lower — scraping failures, paywalls, anti-bot measures |

---

## 5. Recommendation

**Stay with Option A (v0.1.1) for this stage.**

The Universal Research Skill is at proof-of-concept phase. The current architecture works, is deployed, and is honest about its limitations. Option C is the correct target for a *production* research tool requiring hard source verification. However, adding an external retrieval layer now introduces new failure modes with no guaranteed improvement for most queries where snippets are sufficient.

**Upgrade trigger for Option C:**
- A specific important failure where snippet-level evidence produced a wrong conclusion.
- Use case requiring verified academic citations (e.g., literature review for publication).
- Project has moved past proof-of-concept to a sustained research workflow.

**Upgrade path is already clean:** `SKILL.md` is model-independent, and the retrieval mechanism is isolated in `run_research()` in `app.py`. Upgrading to Option C requires modifying only that function.
