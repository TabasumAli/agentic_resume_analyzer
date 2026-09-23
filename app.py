import io
import streamlit as st
from crewai import Agent, LLM
from langchain_groq import ChatGroq
from pypdf import PdfReader

# ─────────────────────────────────────────────────────────────
# Page setup
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="Resume Review Agent", page_icon="📄", layout="wide")
st.title("📄 Resume Review Agent")
st.caption("Paste or upload a resume + a job description. Get skill gaps & suggestions.")

# ─────────────────────────────────────────────────────────────
# Load Groq API key from Streamlit secrets
# ─────────────────────────────────────────────────────────────
try:
    GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
except (KeyError, FileNotFoundError):
    st.error("🔑 GROQ_API_KEY missing. Add it to `.streamlit/secrets.toml` locally "
             "or to the Streamlit Cloud secrets manager.")
    st.stop()

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
    llm = ChatGroq(
        temperature=0.2,
        model="llama-3.3-70b-versatile",   # active Groq model
        groq_api_key=GROQ_API_KEY,
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
# UI — inputs
# ─────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("1️⃣ Resume")
    uploaded = st.file_uploader("Upload PDF (optional)", type=["pdf"])
    resume_pdf_text = extract_pdf_text(uploaded) if uploaded else ""
    resume_text = st.text_area(
        "…or paste resume text here",
        value=resume_pdf_text,
        height=300,
        placeholder="Paste the full resume text…",
    )

with col2:
    st.subheader("2️⃣ Job Description")
    jd_text = st.text_area(
        "Paste the job description",
        height=300,
        placeholder="Paste the full job description…",
    )

# ─────────────────────────────────────────────────────────────
# Run button
# ─────────────────────────────────────────────────────────────
if st.button("🔍 Review My Resume", type="primary", use_container_width=True):
    if not resume_text.strip() or not jd_text.strip():
        st.warning("Please provide both a resume and a job description.")
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

Return your answer in this exact Markdown structure:

## ✅ Match Summary
One short paragraph on overall fit.

## 🎯 Matching Skills
Bullet list of skills/experience in the resume that match the JD.

## ❌ Missing or Weak Areas
Bullet list of JD requirements not found in the resume.

## 💡 Improvement Recommendations
Numbered, actionable suggestions to strengthen the resume for this role.

## 📊 Match Score
Give a score from 0–100 with one sentence of justification.
"""

    with st.spinner("Analyzing…"):
        try:
            agent = build_agent()
            result = agent.kickoff(prompt)

            # CrewAI returns a CrewOutput — extract the text
            output = getattr(result, "raw", None) or str(result)

            st.success("Review complete!")
            st.markdown(output)

        except Exception as e:
            msg = str(e)
            if "429" in msg or "rate limit" in msg.lower():
                st.error("⏳ Groq rate limit hit. Wait ~30 seconds and try again.")
            elif "api_key" in msg.lower() or "authentication" in msg.lower():
                st.error("🔑 Invalid Groq API key. Check your secrets.")
            else:
                st.error(f"❌ Something went wrong: {msg}")

st.divider()
st.caption("Built with CrewAI + Groq + Streamlit · Single-agent design")