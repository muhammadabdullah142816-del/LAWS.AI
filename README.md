# LAWS.AI — Global Compliance Engine

> Cross-border AI compliance analysis powered by a Retrieval-Augmented Generation (RAG) pipeline over live legislative data from **EU · US · Pakistan · UK · Canada**.

[![Streamlit](https://img.shields.io/badge/Streamlit-1.35%2B-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io)
[![Groq](https://img.shields.io/badge/Groq-llama--3.1--8b-F55036?logo=groq)](https://groq.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://python.org)
[![Supabase](https://img.shields.io/badge/Supabase-pgvector-3ECF8E?logo=supabase)](https://supabase.com)

---

## Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  Streamlit UI (app.py)                              │
│  Split-screen: Control Deck │ Analytical Workspace  │
└────────────────┬────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│  Generator (generator.py) — LRU cached             │
│  1. Semantic query expansion  (Groq llama-3.1-8b)  │
│  2. pgvector similarity search (retrieve.py)       │
│  3. RAG synthesis             (Groq llama-3.1-8b)  │
└────────────────┬────────────────────────────────────┘
                 │
         ┌───────┴────────┐
         ▼                ▼
  Supabase pgvector    Fallback dictionary
  (live legal chunks)  (core statutory anchors)
```

**Output format:**
- `[SYNTHESIS]` — Cross-border comparative analysis (Samuelson 4-Question Framework)
- `[CLARITY_MATRIX]` — 0–3 legal clarity score table per jurisdiction
- `[DEVELOPER_SCORES]` — Risk profiles (High / Medium / Low)

---

## Quick Start (Local)

### 1. Prerequisites
```bash
# Python 3.10+
python --version

# Supabase project with pgvector enabled
# Groq API key from https://console.groq.com
```

### 2. Clone & install
```bash
git clone https://github.com/YOUR_USERNAME/LAWS.AI.git
cd LAWS.AI
pip install -r requirements.txt
```

### 3. Configure secrets
```bash
cp .env.example .env
# Edit .env with your SUPABASE_DB_URL and GROQ_API_KEY
```

### 4. Set up the database
Run this SQL in your Supabase SQL Editor:
```sql
-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Legal chunks table
CREATE TABLE IF NOT EXISTS public.legal_frameworks (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    jurisdiction    VARCHAR(255) NOT NULL,
    sub_jurisdiction VARCHAR(255),
    source_url      TEXT NOT NULL,
    chunk_text      TEXT NOT NULL,
    embedding       vector(384),
    source_hash     VARCHAR(64) NOT NULL,
    date_scraped    TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Speed-up indexes
CREATE INDEX IF NOT EXISTS idx_lf_jurisdiction ON public.legal_frameworks(jurisdiction);
CREATE INDEX IF NOT EXISTS idx_lf_embedding    ON public.legal_frameworks USING ivfflat (embedding vector_cosine_ops);
```

### 5. Run
```bash
streamlit run app.py
# → http://localhost:8501
```

---

## Deploy on Streamlit Community Cloud (Free)

1. **Push to GitHub** (see below)
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select repo → set Main file: `app.py`
4. Click **Advanced settings → Secrets** and paste:

```toml
SUPABASE_DB_URL = "postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"
GROQ_API_KEY    = "gsk_your_key_here"
```

5. Click **Deploy** — live in ~2 minutes.

---

## Data Ingestion (Scrapy Pipeline)

```bash
cd legal_monitor
# Run a single spider
python run_spider.py eu_ai_act
python run_spider.py us_ai_laws
python run_spider.py moitt_pakistan
python run_spider.py uk_ai_laws
python run_spider.py canada_ai_laws
```

Or via Docker:
```bash
docker build -t laws-ai-scraper .
docker run --env-file .env laws-ai-scraper
```

---

## Performance Notes

| Optimization | Effect |
|---|---|
| `@functools.lru_cache(maxsize=128)` on RAG pipeline | Identical queries returned from memory in <10ms |
| `HF_HUB_OFFLINE=1` env var | Blocks network calls from SentenceTransformers at startup |
| `fileWatcherType=none` in config.toml | Eliminates Streamlit's 2,000-line torchvision scan on every reload |
| `fastReruns=true` | Partial widget rerun instead of full page rerun |
| `@st.cache_resource` on model + pool | Model loaded once per process, not per request |
| pgvector `ivfflat` index | Sub-10ms nearest-neighbour search across all chunks |

---

## Jurisdiction Coverage

| Region | Primary Source | Fallback |
|---|---|---|
| 🇪🇺 European Union | EUR-Lex EU AI Act | DSM Articles 3–4 |
| 🇺🇸 United States | congress.gov / FTC | 17 U.S.C. § 107 Fair Use |
| 🇵🇰 Pakistan | MOITT.gov.pk | Copyright Ordinance 1962 |
| 🇬🇧 United Kingdom | gov.uk / ICO | UK CDPA 1988 |
| 🇨🇦 Canada | justice.gc.ca | AIDA Bill C-27 |

---

## License

MIT — see [LICENSE](LICENSE).

> **Disclaimer:** LAWS.AI provides AI-generated legal analysis for educational and research purposes only. It is not a substitute for advice from a qualified legal professional.
