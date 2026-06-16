import os
import sys
import functools
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

# Explicitly FORCE online mode to override any sticky cloud environment variables
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
os.environ["TRANSFORMERS_VERBOSITY"] = "error"   # suppress torchvision noise
os.environ["TOKENIZERS_PARALLELISM"] = "false"   # prevent fork warnings

from dotenv import load_dotenv
from groq import Groq

from retrieve import vector_search

# ──────────────────────────────────────────────────────────────────────────────
# Environment bootstrap
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv(override=True)

# ──────────────────────────────────────────────────────────────────────────────
# Prompt constants
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = (
    "You are an elite legal compliance officer for LAWS.AI, tasked with analyzing cross-border copyright issues "
    "using Pamela Samuelson's 4-Question Framework. Synthesize a unified answer using ONLY the verified legislative chunks "
    "provided below.\n\n"
    "You must format your final answer using these exact uppercase tag blocks:\n"
    "[SYNTHESIS]\n"
    "(Your conversational cross-border comparative analysis here)\n"
    "[CLARITY_MATRIX]\n"
    "(Your Samuelson 0-3 Legal Clarity Score Matrix and table calculations here: 0 = No provision, 1 = Implied untested, 2 = Partial guidance, 3 = Clear settled law)\n"
    "[DEVELOPER_SCORES]\n"
    "(Your Developer-Friendly score metric and scenario risk profiles (High/Medium/Low) here)\n"
)

EXPANSION_PROMPT = (
    "You are a query semantic expander for a global legal compliance database. "
    "Given a raw user query, rewrite it as a dense string of formal legal "
    "terminology, legislative concepts, and related keywords suitable for a "
    "pgvector similarity search across EU, US, and Pakistani legal frameworks. "
    "Do NOT answer the question. Output ONLY the expanded keyword string.\n\n"
    "Example:\n"
    'User: "Am using AI actors for marketing what about law"\n'
    'Output: "generative AI, deepfakes, synthetic media, transparency obligations, '
    'audio-visual manipulation, marketing AI rules, consumer protection"'
)


# ──────────────────────────────────────────────────────────────────────────────
# Groq client (singleton — constructed once per process)
# ──────────────────────────────────────────────────────────────────────────────
def _build_groq_client() -> Groq:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Add it to .env (local) or Streamlit secrets (cloud)."
        )
    return Groq(api_key=api_key, timeout=5.0)


_groq_client: Groq | None = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        _groq_client = _build_groq_client()
    return _groq_client


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _expand_query(query_text: str) -> str:
    """
    Run a cheap LLM call to semantically enrich the raw user query before
    embedding — improves recall against legislative jargon.
    Falls back to the original text if the Groq call fails.
    """
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": EXPANSION_PROMPT},
                {"role": "user",   "content": f'User: "{query_text}"\nOutput:'},
            ],
            model="llama-3.1-8b-instant",
            temperature=0.3,
            max_tokens=100,
        )
        expanded = response.choices[0].message.content.strip().strip('"')
        print(f"[GENERATOR] Expanded query: {expanded}")
        return expanded
    except Exception as exc:
        print(f"[GENERATOR] Query expansion failed ({exc}) — using raw query.")
        return query_text


def _build_fallback_answer(results: list[dict]) -> str:
    """
    Construct a structured fallback message when the Groq inference call
    cannot reach the API (firewall / timeout).  Still surfaces the retrieved
    chunks so the user gets value from the database lookup.
    """
    lines = [
        "**⚠ NETWORK TIMEOUT — Groq inference unreachable.**\n",
        "The vector retrieval succeeded; here are the raw legislative fragments "
        "most relevant to your query:\n",
    ]
    for idx, r in enumerate(results, 1):
        snippet = r["chunk_text"][:200].replace("\n", " ") + "..."
        lines.append(
            f"**[{idx}] {r['jurisdiction']}"
            + (f" / {r['sub_jurisdiction']}" if r.get("sub_jurisdiction") else "")
            + f"** — [{r['source_url']}]({r['source_url']})\n> {snippet}\n"
        )
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# Public API — hard-locked signature (eliminates all kwarg TypeError crashes)
# ──────────────────────────────────────────────────────────────────────────────

@functools.lru_cache(maxsize=128)
def generate_rag_response(
    query_text: str,
    jurisdiction_filter: str = "All Regions",
) -> tuple[str, tuple]:
    """
    Full RAG pipeline: expand → retrieve → synthesise.

    Parameters
    ----------
    query_text:
        The user's natural-language compliance question.
    jurisdiction_filter:
        One of ``"All Regions"``, ``"European Union"``, ``"United States"``,
        or ``"Pakistan"``.

    Returns
    -------
    ``(answer_markdown, sources_list)``
    *answer_markdown* is a Markdown-formatted string ready for ``st.markdown``.
    *sources_list* is a list of dicts with keys
    ``jurisdiction``, ``sub_jurisdiction``, ``source_url``, ``chunk_text``.
    On total failure, returns a descriptive error string and ``[]``.
    """
    # ── Step 1: Semantic query expansion ─────────────────────────────────────
    expanded_query = _expand_query(query_text)

    # ── Step 2: Vector retrieval with jurisdiction filter ─────────────────────
    results = vector_search(
        query_text=expanded_query,
        jurisdiction_filter=jurisdiction_filter,
        top_k=4,
    )

    if not results:
        return (
            "No relevant legislative context was found in the database for your "
            "query and the selected jurisdiction. "
            "Try broadening the region scope or rephrasing the question.",
            [],
        )

    # ── Step 3: Assemble prompt context ──────────────────────────────────────
    context_blocks = []
    sources: list[dict] = []

    for idx, r in enumerate(results, 1):
        jurisdiction_label = r["jurisdiction"]
        if r.get("sub_jurisdiction"):
            jurisdiction_label += f" / {r['sub_jurisdiction']}"

        context_blocks.append(
            f"[Chunk {idx}]\n"
            f"Source      : {r['source_url']}\n"
            f"Jurisdiction: {jurisdiction_label}\n"
            f"Text        : {r['chunk_text']}\n"
        )
        sources.append(
            {
                "jurisdiction":     r["jurisdiction"],
                "sub_jurisdiction": r.get("sub_jurisdiction", ""),
                "source_url":       r["source_url"],
                "chunk_text":       r["chunk_text"],
            }
        )

    context_str  = "\n".join(context_blocks)
    user_message = f"Context:\n{context_str}\n\nUser Question: {query_text}"

    print(f"\n{'='*60}")
    print(f"[GENERATOR] Initiating Groq inference (llama-3.1-8b-instant)...")
    print(f"[GENERATOR] Jurisdiction filter : {jurisdiction_filter!r}")
    print(f"[GENERATOR] Retrieved chunks    : {len(results):d}")
    print(f"{'='*60}")

    # ── Step 4: LLM synthesis ────────────────────────────────────────────────
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
            model="llama-3.1-8b-instant",
            temperature=0.2,
            max_tokens=1024,
        )
        answer = response.choices[0].message.content
        return answer, tuple(sources)   # tuple so lru_cache can hash it

    except Exception as exc:
        print(f"\n[GENERATOR] [!] Groq API unreachable: {exc}")
        print("[GENERATOR] Failing over to structured raw-chunk output.\n")
        return _build_fallback_answer(results), tuple(sources)


# ──────────────────────────────────────────────────────────────────────────────
# Standalone smoke-test  (python generator.py)
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_query  = "What are the rules regarding high-risk AI systems?"
    test_filter = "All Regions"

    answer, sources = generate_rag_response(test_query, jurisdiction_filter=test_filter)

    print("\n" + "="*60)
    print("LAWS.AI GENERATED RESPONSE:")
    print("="*60)
    print(answer)
    print(f"\n[{len(sources)} sources retrieved]")
