import io
import os
import re
import streamlit as st
from crewai import Agent, LLM
from pypdf import PdfReader

# ─────────────────────────────────────────────────────────────
# Workaround for a known CrewAI/litellm bug (crewAIInc/crewAI#6789):
# CrewAI tags the system message with an internal "cache_breakpoint"
# key meant only for native providers (e.g. Anthropic). For providers
# routed through litellm — Groq included — that key is supposed to be
# stripped before the request goes out, but isn't in some CrewAI
# versions, so Groq's strict schema validation rejects the call. We
# strip it ourselves at the litellm layer as a safety net.
import litellm

_original_completion = litellm.completion

def _stripped_completion(*args, **kwargs):
    messages = kwargs.get("messages")
    if messages:
        kwargs["messages"] = [
            {k: v for k, v in m.items() if k != "cache_breakpoint"}
            if isinstance(m, dict) else m
            for m in messages
        ]
    return _original_completion(*args, **kwargs)

litellm.completion = _stripped_completion

# ─────────────────────────────────────────────────────────────
# Page setup
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Resume Review — Case File",
    page_icon="🗂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────
# Design system — single dark theme, white text, red accent.
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --bg:      #000000;
    --surface: #0E0E0E;
    --surface-2: #161616;
    --ink:     #FFFFFF;
    --muted:   #B8B8B8;
    --border:  #2A2A2A;
    --red:     #E63946;
    --red-hover:#FF4D5E;
    --emerald: #4ADE80;
    --amber:   #FBBF24;
}

/* ---------- Universal base: ONE bg, ONE fg ---------- */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background: var(--bg) !important;
    color: var(--ink) !important;
}
.stApp { background: var(--bg) !important; }
[data-testid="stAppViewContainer"] { background: var(--bg) !important; }
[data-testid="stHeader"] { background: var(--bg) !important; }
[data-testid="stSidebar"] { background: var(--surface) !important; }

/* Every text node inherits white unless explicitly overridden */
.stApp, .stApp * { color: var(--ink); }
.stApp p, .stApp span, .stApp label, .stApp li,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp h5, .stApp h6,
.stMarkdown, .stMarkdown * { color: var(--ink) !important; }

#MainMenu, footer { visibility: hidden; }
.block-container { padding-top: 1.2rem; max-width: 1400px; }

/* ---------- Hero ---------- */
.case-hero {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 6px solid var(--red);
    border-radius: 12px;
    padding: 1.4rem 1.8rem;
    margin-bottom: 1.2rem;
}
.case-hero .tag {
    color: var(--red) !important;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    font-weight: 700;
    text-transform: uppercase;
    margin-bottom: 0.4rem;
}
.case-hero h1 {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: 1.7rem;
    color: var(--ink) !important;
    margin: 0 0 0.3rem 0;
    line-height: 1.2;
}
.case-hero p {
    color: var(--muted) !important;
    font-size: 0.92rem;
    max-width: 70ch;
    margin: 0;
    line-height: 1.5;
}

/* ---------- Section headings ---------- */
.section-title {
    display: flex; align-items: center; gap: 0.6rem;
    font-family: 'Fraunces', serif;
    font-size: 1.05rem;
    font-weight: 600;
    color: var(--ink) !important;
    margin: 0.4rem 0 0.7rem 0;
}
.section-title .num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 22px; height: 22px; border-radius: 50%;
    background: var(--red);
    color: #FFFFFF !important;
    font-family: 'Inter', sans-serif; font-size: 0.72rem; font-weight: 700;
}

/* ---------- Inputs ---------- */
.stTextArea textarea,
.stTextInput input {
    background: var(--surface-2) !important;
    border: 1px solid var(--border) !important;
    border-radius: 10px !important;
    font-size: 0.9rem !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}
.stTextArea textarea::placeholder,
.stTextInput input::placeholder {
    color: #6B6B6B !important;
    opacity: 1 !important;
}
.stTextArea textarea:focus,
.stTextInput input:focus {
    border-color: var(--red) !important;
    box-shadow: 0 0 0 3px rgba(230,57,70,0.18) !important;
}
[data-testid="stFileUploader"] {
    background: var(--surface-2) !important;
    border: 1px dashed var(--border);
    border-radius: 10px;
    padding: 0.4rem 0.6rem;
}
[data-testid="stFileUploader"] * { color: var(--ink) !important; }
[data-testid="stFileUploader"] svg { fill: var(--ink) !important; }

/* ---------- Buttons — RED ---------- */
.stButton > button,
.stDownloadButton > button {
    background: var(--red) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.65rem 1.4rem !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
    transition: background 0.15s ease, transform 0.12s ease;
}
.stButton > button:hover,
.stDownloadButton > button:hover {
    background: var(--red-hover) !important;
    color: #FFFFFF !important;
    transform: translateY(-1px);
}
.stButton > button *,
.stDownloadButton > button * { color: #FFFFFF !important; }

/* ---------- Score strip ---------- */
.score-wrap {
    display: flex; align-items: center; gap: 1.4rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 6px solid var(--red);
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1rem;
}
.score-wrap .score-text h4 {
    font-family: 'Fraunces', serif;
    color: var(--ink) !important;
    font-size: 1rem;
    margin: 0 0 0.25rem 0;
}
.score-wrap .score-text p {
    color: var(--muted) !important;
    font-size: 0.9rem;
    margin: 0;
    max-width: 60ch;
    line-height: 1.5;
}

/* ---------- Tabs ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.3rem;
    border-bottom: 1px solid var(--border);
    background: transparent;
}
.stTabs [data-baseweb="tab"] {
    background: var(--surface) !important;
    border: 1px solid var(--border);
    border-bottom: none;
    border-radius: 8px 8px 0 0;
    padding: 0.55rem 1rem;
    color: var(--ink) !important;
    font-weight: 600;
    font-size: 0.9rem;
}
.stTabs [data-baseweb="tab"] * { color: var(--ink) !important; }
.stTabs [aria-selected="true"] {
    background: var(--red) !important;
    border-color: var(--red) !important;
}
.stTabs [aria-selected="true"] * { color: #FFFFFF !important; }

.stTabs [role="tabpanel"] {
    background: var(--surface) !important;
    border: 1px solid var(--border);
    border-top: none;
    border-left: 5px solid var(--red);
    border-radius: 0 10px 10px 10px;
    padding: 1.2rem 1.4rem;
}
.stTabs [role="tabpanel"] * { color: var(--ink) !important; }
.stTabs [role="tabpanel"] ul,
.stTabs [role="tabpanel"] ol { padding-left: 1.3rem; margin: 0.4rem 0; }
.stTabs [role="tabpanel"] li {
    margin-bottom: 0.4rem;
    line-height: 1.55;
}
.stTabs [role="tabpanel"] p { line-height: 1.55; margin: 0.35rem 0; }
.stTabs [role="tabpanel"] strong { font-weight: 700; color: var(--ink) !important; }
.stTabs [role="tabpanel"] em { color: var(--muted) !important; }

/* Per-tab accent border */
.stTabs [role="tabpanel"]:nth-of-type(1) { border-left-color: var(--red); }
.stTabs [role="tabpanel"]:nth-of-type(2) { border-left-color: var(--emerald); }
.stTabs [role="tabpanel"]:nth-of-type(3) { border-left-color: var(--amber); }
.stTabs [role="tabpanel"]:nth-of-type(4) { border-left-color: var(--red); }

/* ---------- Alerts ---------- */
.stAlert {
    border-radius: 10px;
    background: var(--surface) !important;
    color: var(--ink) !important;
    border: 1px solid var(--border);
}
.stAlert * { color: var(--ink) !important; }

/* ---------- Caption ---------- */
.stCaption, [data-testid="stCaptionContainer"] * {
    color: var(--muted) !important;
}

/* ---------- Sidebar tweaks ---------- */
[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
[data-testid="stSidebar"] hr { border-color: var(--border); }

/* ---------- Divider between JD and output ---------- */
.divider {
    height: 1px;
    background: var(--border);
    margin: 1.4rem 0 1.2rem 0;
    border: none;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Load Groq API key
# ─────────────────────────────────────────────────────────────
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("🔑 GROQ_API_KEY missing. Add it to `.streamlit/secrets.toml` locally "
             "or to the Streamlit Cloud secrets manager.")
    st.stop()

os.environ["GROQ_API_KEY"] = GROQ_API_KEY

# ─────────────────────────────────────────────────────────────
# PDF extraction helper
# ─────────────────────────────────────────────────────────────
def extract_pdf_text(file) -> str:
    """Return text from an uploaded PDF, or '' if extraction fails."""
    try:
        reader = PdfReader(io.BytesIO(file.getvalue()))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages).strip()
        if not text:
            st.warning("⚠️ No text found in the PDF — it may be a scanned image. "
                       "Please paste the resume text instead.")
        return text
    except Exception as e:
        st.error(f"❌ Could not read PDF: {e}")
        return ""

# ─────────────────────────────────────────────────────────────
# Agent builder
# ─────────────────────────────────────────────────────────────
def build_agent() -> Agent:
    llm = LLM(
        model="groq/openai/gpt-oss-120b",
        temperature=0.2,
    )
    return Agent(
        role="Senior Technical Recruiter & Career Coach",
        goal="Evaluate how well a resume matches a job description and give "
             "honest, actionable improvement recommendations.",
        backstory=(
            "You are a senior recruiter with 10+ years of experience hiring "
            "for tech roles. You only reference skills and experience that "
            "actually appear in the resume — you never invent qualifications."
        ),
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

# ─────────────────────────────────────────────────────────────
# Output parsing
# ─────────────────────────────────────────────────────────────
SECTION_MAP = [
    ("Match Summary", "summary"),
    ("Matching Skills", "match"),
    ("Missing or Weak Areas", "gap"),
    ("Improvement Recommendations", "plan"),
    ("Match Score", "score"),
]

def parse_sections(raw: str) -> dict:
    parts = re.split(r"^##\s*", raw, flags=re.MULTILINE)
    sections = {}
    for part in parts:
        if not part.strip():
            continue
        lines = part.strip().split("\n", 1)
        header = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        header_clean = re.sub(r"[^\w\s]", "", header).strip()
        for label, key in SECTION_MAP:
            if label.lower() in header_clean.lower():
                sections[key] = body
                break
    return sections

def extract_score(text: str) -> int:
    match = re.search(r"(\d{1,3})\s*/\s*100", text) or re.search(r"\b(\d{1,3})\b", text)
    if match:
        return max(0, min(100, int(match.group(1))))
    return 0

def render_gauge(score: int) -> str:
    radius = 46
    circumference = 2 * 3.14159 * radius
    offset = circumference * (1 - score / 100)
    color = "#4ADE80" if score >= 70 else "#FBBF24" if score >= 40 else "#E63946"
    return f"""
    <svg width="110" height="110" viewBox="0 0 110 110">
        <circle cx="55" cy="55" r="{radius}" fill="none" stroke="#2A2A2A" stroke-width="10"/>
        <circle cx="55" cy="55" r="{radius}" fill="none" stroke="{color}" stroke-width="10"
                stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
                stroke-linecap="round" transform="rotate(-90 55 55)"/>
        <text x="55" y="61" text-anchor="middle" font-family="Fraunces, serif"
              font-size="26" font-weight="600" fill="#FFFFFF">{score}</text>
    </svg>
    """

# ─────────────────────────────────────────────────────────────
# SIDEBAR — CV upload + resume text
# ─────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### 📎 Resume")
    uploaded = st.file_uploader("Upload PDF", type=["pdf"], label_visibility="collapsed")
    resume_pdf_text = extract_pdf_text(uploaded) if uploaded else ""

    resume_text = st.text_area(
        "Or paste resume text",
        value=resume_pdf_text,
        height=380,
        placeholder="Paste the full resume text here…",
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.caption("Built with CrewAI + Groq")

# ─────────────────────────────────────────────────────────────
# MAIN — top 40% JD, bottom 60% output
# ─────────────────────────────────────────────────────────────
# Hero (compact)
st.markdown("""
<div class="case-hero">
    <div class="tag">Case File · Resume Review</div>
    <h1>Match a resume against a job description</h1>
    <p>Upload the resume in the sidebar, paste the job description below,
    and open the case for an honest read.</p>
</div>
""", unsafe_allow_html=True)

# ---- TOP 40%: Job description input ----
jd_container = st.container()
with jd_container:
    st.markdown('<div class="section-title"><span class="num">1</span> Job description</div>',
                unsafe_allow_html=True)
    jd_text = st.text_area(
        "jd_text",
        height=260,
        placeholder="Paste the full job description here…",
        label_visibility="collapsed",
    )
    col_a, col_b = st.columns([1, 4])
    with col_a:
        run = st.button("Open the case", type="primary", use_container_width=True)

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ---- BOTTOM 60%: Output ----
output_container = st.container()
with output_container:
    if not run:
        st.markdown(
            '<div class="section-title"><span class="num">2</span> Report</div>',
            unsafe_allow_html=True,
        )
        st.caption("The report will appear here once you open the case.")

    else:
        if not resume_text.strip() or not jd_text.strip():
            st.warning("Add both a resume (sidebar) and a job description before opening the case.")
            st.stop()

        prompt = f"""
You are reviewing a resume against a job description.

CRITICAL RULES:
- Only reference skills, tools, and experience that ACTUALLY APPEAR in the resume.
- Never invent or assume qualifications.
- If something is missing, say it is missing.

RESUME:
\"\"\"
{resume_text[:8000]}
\"\"\"

JOB DESCRIPTION:
\"\"\"
{jd_text[:8000]}
\"\"\"

Return your answer in this exact Markdown structure.
Use ONE bullet per idea, keep each bullet to 1–2 lines, and
put a blank line between every bullet and every section.

## ✅ Match Summary
One short paragraph (2–3 sentences) on overall fit.

## 🎯 Matching Skills
- **Skill name** — how it appears in the resume
- **Skill name** — how it appears in the resume

## ❌ Missing or Weak Areas
- **Requirement** — what's absent or thin
- **Requirement** — what's absent or thin

## 💡 Improvement Recommendations
1. **Action title** — one concrete step.
2. **Action title** — one concrete step.
3. **Action title** — one concrete step.

## 📊 Match Score
Score: NN/100
One sentence of justification.
"""

        with st.spinner("Reading the file…"):
            try:
                agent = build_agent()
                result = agent.kickoff(prompt)
                output = getattr(result, "raw", None) or str(result)
                sections = parse_sections(output)

                # ── Score strip ──
                score_body = sections.get("score", "")
                score = extract_score(score_body)
                justification = re.sub(r"(?i)score\s*:?\s*\d{1,3}\s*/\s*100", "", score_body)
                justification = re.sub(r"\d{1,3}\s*/\s*100", "", justification).strip(" .-—\n")

                st.markdown(f"""
<div class="score-wrap">
    {render_gauge(score)}
</div>
""", unsafe_allow_html=True)

                # ── Tabbed report ──
                tab_labels = []
                if "summary" in sections: tab_labels.append("📋 The read")
                if "match"   in sections: tab_labels.append("✅ What lands")
                if "gap"     in sections: tab_labels.append("⚠️ What's missing")
                if "plan"    in sections: tab_labels.append("🛠️ Fix these first")

                if tab_labels:
                    tabs = st.tabs(tab_labels)
                    i = 0
                    if "summary" in sections:
                        with tabs[i]:
                            st.markdown(sections["summary"])
                        i += 1
                    if "match" in sections:
                        with tabs[i]:
                            st.markdown(sections["match"])
                        i += 1
                    if "gap" in sections:
                        with tabs[i]:
                            st.markdown(sections["gap"])
                        i += 1
                    if "plan" in sections:
                        with tabs[i]:
                            st.markdown(sections["plan"])
                        i += 1
                else:
                    st.markdown(output)

            except Exception as e:
                msg = str(e)
                if "429" in msg or "rate limit" in msg.lower():
                    st.error("⏳ Groq rate limit hit. Wait ~30 seconds and try again.")
                elif "api_key" in msg.lower() or "authentication" in msg.lower():
                    st.error("🔑 Invalid Groq API key. Check your secrets.")
                else:
                    st.error(f"❌ Something went wrong: {msg}")
