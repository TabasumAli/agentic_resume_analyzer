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
st.set_page_config(page_title="Resume Review — Case File", page_icon="🗂️", layout="wide")

# ─────────────────────────────────────────────────────────────
# Design system — "recruiter's desk / case file"
# Ink navy hero, cool paper panels, emerald for matches,
# amber for gaps and score, Fraunces + Inter type pairing.
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,600;9..144,700&family=Inter:wght@400;500;600;700&display=swap');

:root {
    --ink:        #101820;
    --ink-soft:   #1B2530;
    --paper:      #EEF1F4;
    --paper-dim:  #E1E6EA;
    --emerald:    #1F7A5C;
    --emerald-bg: #E4F2EB;
    --amber:      #C9A227;
    --amber-bg:   #FAF3DE;
    --slate:      #5B6472;
    --white:      #FFFFFF;
    --muted-on-dark: #AEB8C4;
}

/* ---------- Base ---------- */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.5rem; max-width: 1100px; }
.stApp { background: var(--paper); }

/* Force dark text on light app background ONLY (not inside dark panels) */
.stApp, .stApp p, .stApp span, .stApp label, .stApp li,
.stMarkdown, .stMarkdown p, .stMarkdown li {
    color: var(--ink);
}

/* ---------- Hero letterhead (dark bg → light text) ---------- */
.case-hero {
    background: linear-gradient(155deg, var(--ink) 0%, var(--ink-soft) 100%);
    border-radius: 18px;
    padding: 2.6rem 2.8rem;
    margin-bottom: 1.8rem;
    position: relative;
    overflow: hidden;
}
.case-hero::after {
    content: "";
    position: absolute; top: -40%; right: -10%;
    width: 320px; height: 320px; border-radius: 50%;
    background: radial-gradient(circle, rgba(201,162,39,0.18) 0%, rgba(201,162,39,0) 70%);
}
.case-hero, .case-hero * { color: var(--white); }
.case-hero .tag {
    color: var(--amber) !important;
    font-size: 0.8rem;
    letter-spacing: 0.03em;
    font-weight: 600;
    margin-bottom: 0.6rem;
}
.case-hero h1 {
    font-family: 'Fraunces', serif;
    font-weight: 600;
    font-size: 2.6rem;
    color: var(--white) !important;
    margin: 0 0 0.5rem 0;
    line-height: 1.15;
}
.case-hero p {
    color: var(--muted-on-dark) !important;
    font-size: 1.02rem;
    max-width: 46ch;
    margin: 0;
}

/* ---------- Intake panel labels ---------- */
.panel-label {
    display: flex; align-items: center; gap: 0.6rem;
    font-family: 'Fraunces', serif;
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--ink) !important;
    margin: 0.2rem 0 0.7rem 0;
}
.panel-label .num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px; border-radius: 50%;
    background: var(--ink); color: var(--amber) !important;
    font-family: 'Inter', sans-serif; font-size: 0.8rem; font-weight: 700;
}

/* ---------- Inputs ---------- */
.stTextArea textarea {
    background: var(--white) !important;
    border: 1.5px solid var(--paper-dim) !important;
    border-radius: 10px !important;
    font-size: 0.92rem !important;
    color: var(--ink) !important;
    -webkit-text-fill-color: var(--ink) !important;
}
.stTextArea textarea::placeholder {
    color: var(--slate) !important;
    opacity: 1 !important;
}
.stTextArea textarea:focus {
    border-color: var(--emerald) !important;
    box-shadow: 0 0 0 3px var(--emerald-bg) !important;
}
[data-testid="stFileUploader"] {
    background: var(--white);
    border: 1.5px dashed var(--paper-dim);
    border-radius: 10px;
    padding: 0.4rem 0.6rem;
}
[data-testid="stFileUploader"] * { color: var(--ink) !important; }

/* ---------- CTA button ---------- */
.stButton > button {
    background: var(--ink) !important;
    color: var(--white) !important;
    border: none !important;
    border-radius: 999px !important;
    padding: 0.75rem 1.5rem !important;
    font-weight: 600 !important;
    font-size: 1rem !important;
    letter-spacing: 0.01em;
    transition: transform 0.12s ease, background 0.12s ease;
}
.stButton > button:hover {
    background: var(--emerald) !important;
    color: var(--white) !important;
    transform: translateY(-1px);
}
.stButton > button:active { transform: translateY(0); }

/* ---------- Report cards ---------- */
.report-card {
    background: var(--white);
    color: var(--ink);
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1rem;
    border-left: 5px solid var(--slate);
}
.report-card.match   { border-left-color: var(--emerald); }
.report-card.gap     { border-left-color: var(--amber); }
.report-card.summary { border-left-color: var(--ink); }
.report-card.plan    { border-left-color: var(--ink); background: var(--paper); }

.report-card, .report-card * { color: var(--ink) !important; }
.report-card h3 {
    font-family: 'Fraunces', serif;
    font-size: 1.15rem;
    font-weight: 600;
    color: var(--ink) !important;
    margin: 0 0 0.6rem 0;
}
.report-card p, .report-card li {
    color: var(--ink) !important;
    font-size: 0.96rem;
    line-height: 1.6;
}
.report-card ul, .report-card ol { margin: 0.3rem 0 0 0; padding-left: 1.3rem; }
.report-card li { margin-bottom: 0.35rem; }
.report-card strong { color: var(--ink) !important; font-weight: 700; }
.report-card em { color: var(--slate) !important; }

/* ---------- Score gauge (dark bg → light text) ---------- */
.score-wrap {
    display: flex; align-items: center; gap: 1.6rem;
    background: var(--ink);
    border-radius: 14px;
    padding: 1.6rem 1.8rem;
    margin-bottom: 1.2rem;
}
.score-wrap, .score-wrap * { color: var(--white) !important; }
.score-wrap .score-text h4 {
    font-family: 'Fraunces', serif;
    color: var(--white) !important;
    font-size: 1.1rem;
    margin: 0 0 0.3rem 0;
}
.score-wrap .score-text p {
    color: var(--muted-on-dark) !important;
    font-size: 0.92rem;
    margin: 0;
    max-width: 42ch;
}

/* ---------- Streamlit tabs ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.4rem;
    border-bottom: 1px solid var(--paper-dim);
}
.stTabs [data-baseweb="tab"] {
    background: var(--white);
    border-radius: 10px 10px 0 0;
    padding: 0.6rem 1.1rem;
    color: var(--slate) !important;
    font-weight: 600;
}
.stTabs [data-baseweb="tab"] * { color: inherit !important; }
.stTabs [aria-selected="true"] {
    background: var(--ink) !important;
    color: var(--white) !important;
}
.stTabs [aria-selected="true"] * { color: var(--white) !important; }

/* Tab panel: give it card-like styling */
.stTabs [role="tabpanel"] {
    background: var(--white);
    border-radius: 0 14px 14px 14px;
    padding: 1.4rem 1.6rem;
    border-left: 5px solid var(--ink);
    margin-top: 0;
}
.stTabs [role="tabpanel"] * { color: var(--ink) !important; }
.stTabs [role="tabpanel"] ul,
.stTabs [role="tabpanel"] ol { padding-left: 1.3rem; }
.stTabs [role="tabpanel"] li {
    margin-bottom: 0.4rem;
    line-height: 1.6;
}
.stTabs [role="tabpanel"] strong { font-weight: 700; }
.stTabs [role="tabpanel"] p { line-height: 1.6; }

/* Colored left border per tab index (summary/match/gap/plan) */
.stTabs [role="tabpanel"]:nth-of-type(1) { border-left-color: var(--ink); }
.stTabs [role="tabpanel"]:nth-of-type(2) { border-left-color: var(--emerald); }
.stTabs [role="tabpanel"]:nth-of-type(3) { border-left-color: var(--amber); }
.stTabs [role="tabpanel"]:nth-of-type(4) { border-left-color: var(--ink); }

.stAlert { border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Hero
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="case-hero">
    <div class="tag">CASE FILE · RESUME REVIEW</div>
    <h1>Put your resume<br>under a recruiter's lens</h1>
    <p>Drop in a resume and a job description. Get an honest read on
    fit — what lands, what's missing, and what to fix first.</p>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Load Groq API key from Streamlit secrets
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
    color = "#1F7A5C" if score >= 70 else "#C9A227" if score >= 40 else "#B5432E"
    return f"""
    <svg width="110" height="110" viewBox="0 0 110 110">
        <circle cx="55" cy="55" r="{radius}" fill="none" stroke="#2A3542" stroke-width="10"/>
        <circle cx="55" cy="55" r="{radius}" fill="none" stroke="{color}" stroke-width="10"
                stroke-dasharray="{circumference:.1f}" stroke-dashoffset="{offset:.1f}"
                stroke-linecap="round" transform="rotate(-90 55 55)"/>
        <text x="55" y="61" text-anchor="middle" font-family="Fraunces, serif"
              font-size="26" font-weight="600" fill="#FFFFFF">{score}</text>
    </svg>
    """

# ─────────────────────────────────────────────────────────────
# UI — inputs
# ─────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="panel-label"><span class="num">1</span> Resume</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader("Upload PDF (optional)", type=["pdf"], label_visibility="collapsed")
    resume_pdf_text = extract_pdf_text(uploaded) if uploaded else ""
    resume_text = st.text_area(
        "resume_text",
        value=resume_pdf_text,
        height=280,
        placeholder="…or paste the full resume text here",
        label_visibility="collapsed",
    )

with col2:
    st.markdown('<div class="panel-label"><span class="num">2</span> Job description</div>', unsafe_allow_html=True)
    st.markdown('<div style="height: 44px;"></div>', unsafe_allow_html=True)
    jd_text = st.text_area(
        "jd_text",
        height=280,
        placeholder="Paste the full job description here",
        label_visibility="collapsed",
    )

st.write("")
run = st.button("Open the case", type="primary", use_container_width=False)

# ─────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────
if run:
    if not resume_text.strip() or not jd_text.strip():
        st.warning("Add both a resume and a job description before opening the case.")
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

            st.write("")

            # ── Score gauge ──────────────────────────────────
            score_body = sections.get("score", "")
            score = extract_score(score_body)
            justification = re.sub(r"(?i)score\s*:?\s*\d{1,3}\s*/\s*100", "", score_body)
            justification = re.sub(r"\d{1,3}\s*/\s*100", "", justification).strip(" .-—\n")

            st.markdown(f"""
            <div class="score-wrap">
                {render_gauge(score)}
                <div class="score-text">
                    <h4>Match score</h4>
                    <p>{justification or "Overall fit against this role, out of 100."}</p>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── Tabbed report ────────────────────────────────
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
                # Fallback: render raw markdown properly
                st.markdown(output)

        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate limit" in msg.lower():
                st.error("⏳ Groq rate limit hit. Wait ~30 seconds and try again.")
            elif "api_key" in msg.lower() or "authentication" in msg.lower():
                st.error("🔑 Invalid Groq API key. Check your secrets.")
            else:
                st.error(f"❌ Something went wrong: {msg}")

st.write("")
st.caption("Built with CrewAI + Groq (openai/gpt-oss-120b) + Streamlit")
