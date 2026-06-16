import os
import sys
sys.stdout.reconfigure(line_buffering=True, encoding='utf-8')

# Block HuggingFace Hub network calls — use only locally-cached model weights
os.environ["HF_HUB_OFFLINE"] = "1"

import psycopg2
import psycopg2.pool
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from sentence_transformers import SentenceTransformer

# ──────────────────────────────────────────────────────────────────────────────
# Environment bootstrap
# ──────────────────────────────────────────────────────────────────────────────
load_dotenv(override=True)

# ──────────────────────────────────────────────────────────────────────────────
# Streamlit-aware caching (no-op fallback when running outside Streamlit)
# ──────────────────────────────────────────────────────────────────────────────
try:
    import streamlit as st
    _cache_resource = st.cache_resource
except Exception:
    # Running in a plain Python script — provide a pass-through decorator
    def _cache_resource(fn):
        return fn


@_cache_resource
def get_cached_model() -> SentenceTransformer:
    """Load the 384-dimension MiniLM embedding model from local disk cache."""
    print("[RETRIEVE] Loading featherweight local embedding model (all-MiniLM-L6-v2)...")
    return SentenceTransformer(
        "sentence-transformers/all-MiniLM-L6-v2",
        local_files_only=True,
    )


@_cache_resource
def get_connection_pool() -> psycopg2.pool.SimpleConnectionPool:
    """
    Build a thread-safe SimpleConnectionPool (min=1, max=10).

    Using a pool instead of a single raw connection prevents Supabase from
    hitting the PgBouncer socket limit when Streamlit re-runs on every
    user keystroke.
    """
    # Prefer injected Streamlit secrets; fall back to .env for local runs
    try:
        db_url = st.secrets["SUPABASE_DB_URL"]
    except Exception:
        db_url = os.getenv("SUPABASE_DB_URL")

    if not db_url:
        raise RuntimeError(
            "SUPABASE_DB_URL is not set. "
            "Add it to .env (local) or Streamlit secrets (cloud)."
        )

    print("[RETRIEVE] Initialising Supabase connection pool (min=1, max=10)...")
    pool = psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=10,
        dsn=db_url,
    )
    # Register pgvector type on a throw-away connection so all future
    # connections from the pool already know about the vector type.
    _bootstrap = pool.getconn()
    try:
        register_vector(_bootstrap)
    finally:
        pool.putconn(_bootstrap)

    print("[RETRIEVE] Connection pool ready.")
    return pool


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

LOCAL_FALLBACK_DICTIONARY = {
    "Pakistan": {
        "jurisdiction": "Pakistan",
        "sub_jurisdiction": "National Law",
        "source_url": "fallback:pakistan-copyright-1962",
        "chunk_text": "Pakistan Copyright Ordinance 1962 (Section 3 on definitions, authorship requirements): Requires human authorship for copyright protection. Machine-generated content without sufficient human creative input is ineligible for copyright protection.",
        "distance": 0.0
    },
    "United States": {
        "jurisdiction": "United States",
        "sub_jurisdiction": "US federal law",
        "source_url": "fallback:us-copyright-act-sec-107",
        "chunk_text": "US Copyright Act Section 107 (The 4 factors of Fair Use regarding machine training): The fair use of a copyrighted work is not an infringement. The four factors are: 1) purpose and character of the use, 2) nature of the copyrighted work, 3) amount and substantiality of the portion used, and 4) effect upon the potential market.",
        "distance": 0.0
    },
    "European Union": {
        "jurisdiction": "European Union",
        "sub_jurisdiction": "EU Directives",
        "source_url": "fallback:eu-dsm-directive-art-3-4",
        "chunk_text": "EU DSM Directive Articles 3-4 (Text and Data Mining exemptions for automated scrapers): Provides exceptions for text and data mining (TDM) for scientific research (Art 3), and a general TDM exception allowing commercial scraping unless rightsholders have explicitly reserved their rights (Art 4).",
        "distance": 0.0
    },
    "United Kingdom": {
        "jurisdiction": "United Kingdom",
        "sub_jurisdiction": "England and Wales",
        "source_url": "fallback:uk-ai-regulation-white-paper-2023",
        "chunk_text": "UK AI Regulation White Paper 2023 (Pro-innovation approach): The UK government adopts a principles-based, context-specific framework for AI regulation rather than a single horizontal AI Act. Five cross-sector principles apply: safety/security/robustness, transparency/explainability, fairness, accountability/governance, and contestability/redress. Sector regulators (ICO, FCA, CMA, Ofcom) implement these within their domains.",
        "distance": 0.0
    },
    "Canada": {
        "jurisdiction": "Canada",
        "sub_jurisdiction": "Federal",
        "source_url": "fallback:canada-aida-bill-c27-2022",
        "chunk_text": "Canada Artificial Intelligence and Data Act (AIDA) — Bill C-27, Part 3 (2022): Regulates high-impact AI systems. Requires impact assessments, risk mitigation measures, and transparency obligations for operators of high-impact AI. Prohibits reckless deployment of AI systems that cause serious harm. The Office of the Artificial Intelligence and Data Commissioner (OADC) is established to oversee compliance.",
        "distance": 0.0
    },
}

# All known jurisdictions in the database — used for balanced "All Regions" retrieval
KNOWN_JURISDICTIONS = ["European Union", "United States", "Pakistan", "United Kingdom", "Canada"]


def _run_single_query(
    cur,
    embedding: list,
    jurisdiction: str,
    limit: int,
    has_sub_jurisdiction: bool,
) -> list[dict]:
    """
    Execute a single pgvector cosine-distance query for one jurisdiction.
    Returns a list of result dicts (possibly empty).
    """
    if has_sub_jurisdiction:
        sql = """
            SELECT
                jurisdiction,
                sub_jurisdiction,
                source_url,
                chunk_text,
                (embedding <=> %s::vector) AS distance
            FROM legal_frameworks
            WHERE jurisdiction = %s
            ORDER BY distance ASC
            LIMIT %s;
        """
        cur.execute(sql, (embedding, jurisdiction, limit))
        return [
            {
                "jurisdiction":     row[0],
                "sub_jurisdiction": row[1],
                "source_url":       row[2],
                "chunk_text":       row[3],
                "distance":         row[4],
            }
            for row in cur.fetchall()
        ]
    else:
        sql = """
            SELECT
                jurisdiction,
                source_url,
                chunk_text,
                (embedding <=> %s::vector) AS distance
            FROM legal_frameworks
            WHERE jurisdiction = %s
            ORDER BY distance ASC
            LIMIT %s;
        """
        cur.execute(sql, (embedding, jurisdiction, limit))
        return [
            {
                "jurisdiction":     row[0],
                "sub_jurisdiction": "",
                "source_url":       row[1],
                "chunk_text":       row[2],
                "distance":         row[3],
            }
            for row in cur.fetchall()
        ]


def vector_search(
    query_text: str,
    jurisdiction_filter: str = "All Regions",
    top_k: int = 4,
) -> list[dict]:
    """
    Embed *query_text* and run a pgvector cosine-distance search against the
    ``legal_frameworks`` table.

    Parameters
    ----------
    query_text:
        The user's natural-language compliance question (already semantically
        expanded upstream if desired).
    jurisdiction_filter:
        One of ``"All Regions"``, ``"European Union"``, ``"United States"``,
        or ``"Pakistan"``.

        **Balanced retrieval for "All Regions"**: Instead of a single global
        top-k query (which can return all results from one jurisdiction when
        that corpus is large), this function issues one query per known
        jurisdiction, takes the best chunk from each, then backfills remaining
        slots with the globally-closest remaining results.  This guarantees
        cross-jurisdictional coverage regardless of corpus size imbalance.
    top_k:
        Maximum number of result rows to return.

    Returns
    -------
    A list of dicts with keys
    ``jurisdiction``, ``sub_jurisdiction``, ``source_url``,
    ``chunk_text``, ``distance``.
    Returns ``[]`` on any network or database error.
    """
    try:
        model = get_cached_model()
        pool  = get_connection_pool()
    except Exception as exc:
        print(f"[RETRIEVE] Initialisation failed: {exc}")
        return []

    embedding = model.encode([query_text], convert_to_numpy=True)[0].tolist()

    conn = None
    try:
        conn = pool.getconn()
        register_vector(conn)

        # ── Detect schema: does sub_jurisdiction column exist? ────────────────
        has_sub_jurisdiction = True
        try:
            with conn.cursor() as probe:
                probe.execute(
                    """
                    SELECT 1 FROM legal_frameworks
                    WHERE sub_jurisdiction IS NOT NULL
                    LIMIT 1;
                    """
                )
        except Exception as col_exc:
            err_str = str(col_exc).lower()
            if "sub_jurisdiction" in err_str or "column" in err_str:
                print("[RETRIEVE] sub_jurisdiction column not found — using legacy schema.")
                conn.rollback()
                has_sub_jurisdiction = False
            else:
                raise

        # ── Branch: single-jurisdiction filter ───────────────────────────────
        if jurisdiction_filter != "All Regions":
            with conn.cursor() as cur:
                results = _run_single_query(
                    cur, embedding, jurisdiction_filter, top_k, has_sub_jurisdiction
                )

        # ── Branch: balanced multi-jurisdiction retrieval ─────────────────────
        # Guarantees at least one chunk per jurisdiction so the answer is never
        # skewed entirely toward the largest corpus in the DB.
        else:
            # Step 1: one best chunk per jurisdiction
            per_juris_best: list[dict] = []
            for juris in KNOWN_JURISDICTIONS:
                with conn.cursor() as cur:
                    juris_results = _run_single_query(
                        cur, embedding, juris, 1, has_sub_jurisdiction
                    )
                if juris_results:
                    per_juris_best.append(juris_results[0])
                    print(
                        f"[RETRIEVE] Best chunk for '{juris}': "
                        f"distance={juris_results[0]['distance']:.4f}"
                    )
                else:
                    # No DB chunk for this jurisdiction → inject fallback
                    fallback = LOCAL_FALLBACK_DICTIONARY.get(juris)
                    if fallback:
                        per_juris_best.append(fallback)
                        print(f"[RETRIEVE] No DB chunk for '{juris}' — injecting fallback.")

            slots_used = {r["source_url"] for r in per_juris_best}

            # Step 2: global top-(top_k * 2) to backfill remaining slots
            remaining_slots = top_k - len(per_juris_best)
            backfill: list[dict] = []
            if remaining_slots > 0:
                if has_sub_jurisdiction:
                    global_sql = """
                        SELECT
                            jurisdiction,
                            sub_jurisdiction,
                            source_url,
                            chunk_text,
                            (embedding <=> %s::vector) AS distance
                        FROM legal_frameworks
                        ORDER BY distance ASC
                        LIMIT %s;
                    """
                else:
                    global_sql = """
                        SELECT
                            jurisdiction,
                            source_url,
                            chunk_text,
                            (embedding <=> %s::vector) AS distance
                        FROM legal_frameworks
                        ORDER BY distance ASC
                        LIMIT %s;
                    """
                with conn.cursor() as cur:
                    cur.execute(global_sql, (embedding, top_k * 3))
                    for row in cur.fetchall():
                        url = row[2] if has_sub_jurisdiction else row[1]
                        if url not in slots_used:
                            if has_sub_jurisdiction:
                                backfill.append({
                                    "jurisdiction":     row[0],
                                    "sub_jurisdiction": row[1],
                                    "source_url":       row[2],
                                    "chunk_text":       row[3],
                                    "distance":         row[4],
                                })
                            else:
                                backfill.append({
                                    "jurisdiction":     row[0],
                                    "sub_jurisdiction": "",
                                    "source_url":       row[1],
                                    "chunk_text":       row[2],
                                    "distance":         row[3],
                                })
                            slots_used.add(url)
                            if len(backfill) >= remaining_slots:
                                break

            # Step 3: merge — per-jurisdiction anchors first, then backfill
            results = per_juris_best + backfill

        # ── Zero-result safety net ────────────────────────────────────────────
        if len(results) == 0:
            print("[RETRIEVE] Zero chunks retrieved from DB. Injecting full fallback dictionary.")
            if jurisdiction_filter in LOCAL_FALLBACK_DICTIONARY:
                results = [LOCAL_FALLBACK_DICTIONARY[jurisdiction_filter]]
            else:
                results = list(LOCAL_FALLBACK_DICTIONARY.values())

        # Log jurisdiction breakdown for diagnostics
        juris_counts: dict[str, int] = {}
        for r in results:
            juris_counts[r["jurisdiction"]] = juris_counts.get(r["jurisdiction"], 0) + 1
        print(
            f"[RETRIEVE] '{query_text[:60]}' -> {len(results)} chunks "
            f"(filter={jurisdiction_filter!r}) | breakdown={juris_counts}"
        )
        return results

    except Exception as exc:
        # Encode exc safely — exception text may contain non-ASCII chars
        safe_exc = str(exc).encode("ascii", errors="replace").decode("ascii")
        print(f"[RETRIEVE] [!] Database query failed - returning empty list. Error: {safe_exc}")
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        return []

    finally:
        if conn is not None:
            try:
                pool.putconn(conn)
            except Exception:
                pass



# ──────────────────────────────────────────────────────────────────────────────
# Standalone smoke-test  (python retrieve.py)
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_query  = "What are the rules regarding high-risk AI systems?"
    test_filter = "All Regions"

    results = vector_search(test_query, jurisdiction_filter=test_filter, top_k=4)

    if not results:
        print("[RETRIEVE] No results returned — check DB connectivity and table schema.")
    else:
        print(f"\n[RETRIEVE] Top {len(results)} results for: '{test_query}'")
        for idx, r in enumerate(results, 1):
            print(
                f"\n[{idx}] Distance: {r['distance']:.4f} | "
                f"Jurisdiction: {r['jurisdiction']} / {r['sub_jurisdiction']}"
            )
            print(f"     Source : {r['source_url']}")
            print(f"     Snippet: {r['chunk_text'][:300]}...")
