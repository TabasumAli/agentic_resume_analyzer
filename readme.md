# 📄 Resume Review Agent

An AI-powered resume reviewer built with **Streamlit**, **CrewAI**, and **Groq**. Paste or upload a resume and a job description, and get an honest, structured breakdown of fit — matching skills, gaps, a prioritized fix list, and a match score — rendered as a styled "case file" report instead of plain text.

## Features

- **PDF or paste input** — upload a resume PDF or paste raw text
- **Single-agent review** via CrewAI, powered by an open-weight model (`openai/gpt-oss-120b`) hosted on Groq
- **Grounded output** — the agent is instructed to only reference what's actually in the resume, never invent qualifications
- **Structured report**: match summary, matching skills, missing/weak areas, improvement recommendations, and a 0–100 match score
- **Custom UI** — dark letterhead hero, styled intake panels, color-coded result cards, and a circular score gauge, built entirely with custom CSS on top of Streamlit

## Tech stack

| Layer        | Tool                                  |
|--------------|----------------------------------------|
| UI           | Streamlit                              |
| Agent orchestration | CrewAI (`Agent`, `LLM`)         |
| Model routing| litellm (via CrewAI's `LLM` class)     |
| Inference    | Groq (`groq/openai/gpt-oss-120b`)      |
| PDF parsing  | pypdf                                  |

## Setup

### 1. Clone and install dependencies

```bash
pip install -r requirements.txt
```

`requirements.txt`:

```
streamlit>=1.38.0
crewai>=0.80.0
litellm>=1.50.0
pypdf>=4.0.0
```

> `litellm` is required explicitly — recent CrewAI versions only natively support a fixed list of providers (OpenAI, Anthropic, Azure, Google, Bedrock, etc.). Groq isn't one of them, so CrewAI falls back to litellm for it, but only if it's installed.

### 2. Add your Groq API key

Get a key from [console.groq.com](https://console.groq.com), then create `.streamlit/secrets.toml` in the project root:

```toml
GROQ_API_KEY = "your-groq-api-key-here"
```

On **Streamlit Community Cloud**, add the same key under your app's **Settings → Secrets** instead of committing a `secrets.toml` file.

### 3. Run locally

```bash
streamlit run resume_agent.py
```

## Usage

1. Upload a resume PDF, or paste resume text directly into the left panel
2. Paste the target job description into the right panel
3. Click **Open the case**
4. Review the score gauge and the color-coded report: what matches (green), what's missing (amber), and what to fix first

## Notes on known fixes baked into this app

Two upstream CrewAI/litellm quirks are already worked around in the code, in case you extend it or hit them elsewhere:

- **Model string**: Groq models must use the `groq/` provider prefix (e.g. `groq/openai/gpt-oss-120b`), not `openai/`, since litellm treats `openai/` as "call OpenAI's real API."
- **`cache_breakpoint` error**: a known CrewAI/litellm bug ([crewAIInc/crewAI#6789](https://github.com/crewAIInc/crewAI/issues/6789)) leaks an internal caching marker into requests sent to non-native providers, which Groq's strict schema validation rejects. This app monkey-patches `litellm.completion` to strip that key before the request goes out. Safe to remove once the upstream fix ships in a stable CrewAI release.

## Limitations

- Scanned/image-only PDFs won't extract text — paste the resume manually in that case
- Groq's free tier has rate limits; the app surfaces a friendly message if you hit one
- This is a server-rendered Streamlit app, not a React SPA — there's no client-side state or animated transitions beyond what's built with CSS

## License

Add your preferred license here (MIT, etc.).