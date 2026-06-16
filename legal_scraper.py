"""
legal_scraper.py
================
A modular Python script that programmatically extracts raw text from official,
open-access legal portals for three jurisdictions:

    1. United States  – Copyright Act § 107 (Fair Use) via Cornell LII
    2. European Union – EU AI Act (Regulation 2024/1689) via EUR-Lex
    3. Pakistan       – National AI Policy via MoITT public portal

Each function returns a list of dictionaries with keys:
    'jurisdiction', 'source_url', 'chunk_text', 'last_updated'

Dependencies:
    pip install requests beautifulsoup4

Author:  LAWS.AI Pipeline
Date:    2026-06-06
"""

# ──────────────────────────────────────────────────────────────────────
# Imports
# ──────────────────────────────────────────────────────────────────────
import re
import textwrap
from datetime import datetime, timezone
from typing import List, Dict, Optional

import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────────
# Constants & Configuration
# ──────────────────────────────────────────────────────────────────────

# Approximate token-to-character ratio (1 token ≈ 4 chars for English).
# We target 500-1000 tokens per chunk → 2000-4000 characters.
MIN_CHUNK_CHARS = 2000
MAX_CHUNK_CHARS = 4000

# Default HTTP timeout in seconds for all requests.
REQUEST_TIMEOUT = 30

# Common headers to politely identify our scraper to servers.
HEADERS = {
    "User-Agent": (
        "LAWS-AI-LegalScraper/1.0 "
        "(Educational Research; +https://github.com/LAWS-AI)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ──────────────────────────────────────────────────────────────────────
# Helper: Robust HTTP GET
# ──────────────────────────────────────────────────────────────────────

def _fetch_page(url: str, timeout: int = REQUEST_TIMEOUT) -> requests.Response:
    """
    Perform a GET request with error handling for HTTP errors and timeouts.

    Args:
        url:     The URL to fetch.
        timeout: Seconds to wait before timing out.

    Returns:
        A requests.Response object with the server's response.

    Raises:
        requests.exceptions.HTTPError:       On 4xx / 5xx responses.
        requests.exceptions.Timeout:         If the server doesn't respond in time.
        requests.exceptions.ConnectionError: If the server is unreachable.
        requests.exceptions.RequestException: Catch-all for any other issue.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        # Raise an exception for bad status codes (4xx, 5xx).
        response.raise_for_status()
        return response

    except requests.exceptions.Timeout:
        print(f"[ERROR] Request timed out after {timeout}s: {url}")
        raise
    except requests.exceptions.ConnectionError:
        print(f"[ERROR] Could not connect to server: {url}")
        raise
    except requests.exceptions.HTTPError as exc:
        print(f"[ERROR] HTTP {exc.response.status_code} for: {url}")
        raise
    except requests.exceptions.RequestException as exc:
        print(f"[ERROR] Unexpected request failure: {exc}")
        raise


# ──────────────────────────────────────────────────────────────────────
# Helper: Text Cleaning
# ──────────────────────────────────────────────────────────────────────

def _clean_text(raw: str) -> str:
    """
    Normalise whitespace and strip stray unicode artifacts from raw text.

    Steps:
        1. Replace non-breaking spaces and other unicode whitespace with ' '.
        2. Collapse multiple spaces / blank lines into single ones.
        3. Strip leading / trailing whitespace.
    """
    # Replace non-breaking spaces and other unicode whitespace variants.
    text = raw.replace("\xa0", " ").replace("\u200b", "")
    # Collapse runs of whitespace within lines.
    text = re.sub(r"[^\S\n]+", " ", text)
    # Collapse 3+ consecutive newlines into 2 (one blank line).
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ──────────────────────────────────────────────────────────────────────
# Helper: Chunking
# ──────────────────────────────────────────────────────────────────────

def _chunk_text(
    text: str,
    min_chars: int = MIN_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
) -> List[str]:
    """
    Split *text* into chunks of roughly 500-1000 tokens (2000-4000 chars).

    Strategy:
        1. Split on paragraph boundaries (double newlines).
        2. Accumulate paragraphs into a buffer until the buffer reaches
           the target range.
        3. If a single paragraph exceeds max_chars, hard-wrap it on
           sentence boundaries so no chunk is unreasonably large.

    Args:
        text:      The full document text to split.
        min_chars: Minimum character count before a chunk is "full enough".
        max_chars: Maximum character count; paragraphs beyond this are split.

    Returns:
        A list of text chunks, each roughly within the target size.
    """
    paragraphs = text.split("\n\n")
    chunks: List[str] = []
    buffer: List[str] = []
    buffer_len = 0

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        # If a single paragraph is too large, split it on sentence boundaries.
        if len(para) > max_chars:
            # Flush existing buffer first.
            if buffer:
                chunks.append("\n\n".join(buffer))
                buffer, buffer_len = [], 0

            # Split the oversized paragraph into sentences.
            sentences = re.split(r"(?<=[.!?])\s+", para)
            sent_buf: List[str] = []
            sent_len = 0
            for sent in sentences:
                if sent_len + len(sent) > max_chars and sent_buf:
                    chunks.append(" ".join(sent_buf))
                    sent_buf, sent_len = [], 0
                sent_buf.append(sent)
                sent_len += len(sent) + 1
            if sent_buf:
                chunks.append(" ".join(sent_buf))
            continue

        # Normal case: accumulate paragraphs.
        buffer.append(para)
        buffer_len += len(para) + 2  # +2 for the "\n\n" separator

        if buffer_len >= min_chars:
            chunks.append("\n\n".join(buffer))
            buffer, buffer_len = [], 0

    # Flush any remaining paragraphs.
    if buffer:
        chunks.append("\n\n".join(buffer))

    return chunks


# ──────────────────────────────────────────────────────────────────────
# Helper: Build Structured Output
# ──────────────────────────────────────────────────────────────────────

def _build_records(
    chunks: List[str],
    jurisdiction: str,
    source_url: str,
) -> List[Dict[str, str]]:
    """
    Wrap each text chunk in a dictionary with metadata.

    The 'last_updated' timestamp records the exact UTC moment the data was
    pulled, enabling downstream systems to detect **Regulatory Drift** —
    i.e., whether the statute text has changed since it was last ingested.

    Args:
        chunks:        List of text chunks from the document.
        jurisdiction:  E.g. "United States", "European Union", "Pakistan".
        source_url:    The URL the text was fetched from.

    Returns:
        A list of dicts, each containing:
            - jurisdiction  (str): The legal jurisdiction.
            - source_url    (str): Where the text was obtained.
            - chunk_text    (str): One chunk of the document.
            - last_updated  (str): ISO-8601 UTC timestamp of the scrape.
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    return [
        {
            "jurisdiction": jurisdiction,
            "source_url": source_url,
            "chunk_text": chunk,
            "last_updated": timestamp,
        }
        for chunk in chunks
    ]


# ══════════════════════════════════════════════════════════════════════
# TARGET 1: US Copyright Act § 107 — Fair Use  (Cornell LII)
# ══════════════════════════════════════════════════════════════════════

def fetch_us_copyright_section_107() -> List[Dict[str, str]]:
    """
    Fetch the text of **17 U.S.C. § 107 – Limitations on exclusive rights:
    Fair use** from the Cornell Legal Information Institute (LII).

    Source: https://www.law.cornell.edu/uscode/text/17/107

    The Cornell LII is a free, authoritative, open-access portal maintained
    by Cornell Law School.  It mirrors the United States Code and provides
    clean HTML that is straightforward to parse.

    Returns:
        A list of chunk dictionaries with 'jurisdiction', 'source_url',
        'chunk_text', and 'last_updated'.
    """
    url = "https://www.law.cornell.edu/uscode/text/17/107"
    print(f"[INFO] Fetching US Copyright Act § 107 from: {url}")

    response = _fetch_page(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # ── Extraction Strategy ──
    # Cornell LII wraps statute text inside a <div> with class
    # "field-name-body" or within the tab content area.  We look for
    # the primary content container.
    content_div = (
        soup.find("div", class_="field-name-body")
        or soup.find("div", id="block-system-main")
        or soup.find("div", class_="tab-pane active")
    )

    if content_div:
        # Extract only paragraph and list-item text from the content div.
        elements = content_div.find_all(["p", "li", "h3", "h4", "blockquote"])
        raw_text = "\n\n".join(el.get_text(separator=" ") for el in elements)
    else:
        # Fallback: grab all visible text from the page body.
        print("[WARN] Could not locate main content div; using full body text.")
        raw_text = soup.body.get_text(separator="\n") if soup.body else ""

    cleaned = _clean_text(raw_text)

    if not cleaned:
        print("[WARN] No text extracted for US Copyright § 107.")
        return []

    # § 107 is short (~300 words), so it will likely produce a single chunk.
    chunks = _chunk_text(cleaned)
    records = _build_records(chunks, jurisdiction="United States", source_url=url)

    print(f"[OK]   Extracted {len(records)} chunk(s) for US Copyright § 107.")
    return records


# ══════════════════════════════════════════════════════════════════════
# TARGET 2: Pakistan National AI Policy  (MoITT / public archives)
# ══════════════════════════════════════════════════════════════════════

def fetch_pakistan_ai_policy() -> List[Dict[str, str]]:
    """
    Fetch the text of **Pakistan's National Artificial Intelligence Policy**
    from the Ministry of Information Technology & Telecommunication (MoITT)
    or its publicly mirrored archives.

    Strategy (ordered by preference):
        1. Try the official MoITT policy/download pages for a direct PDF link.
        2. Fall back to known public mirrors (e.g., NIPA Peshawar gazette).

    Note:
        The final 2025 cabinet-approved policy may not yet have a stable
        public URL.  This function attempts several known endpoints and
        returns whatever is publicly available at scrape time.

    Returns:
        A list of chunk dictionaries.
    """
    # ── Candidate URLs ──
    # We try multiple known endpoints because government portals frequently
    # reorganise their file structures.
    candidate_urls = [
        # Primary: MoITT official policies page
        "https://moitt.gov.pk/SiteImage/Policy/National%20Artificial%20Intelligence%20Policy%20Pakistan.pdf",
        # Alternate: NIPA Peshawar public gazette mirror
        "https://nipapeshawar.gov.pk/wp-content/uploads/2024/01/National-AI-Policy-of-Pakistan.pdf",
        # Alternate: MoITT detail page (HTML)
        "https://moitt.gov.pk/Detail/national-artificial-intelligence-policy",
    ]

    jurisdiction = "Pakistan"
    response = None
    used_url = ""

    # ── Try each URL until one succeeds ──
    for url in candidate_urls:
        try:
            print(f"[INFO] Trying Pakistan AI Policy from: {url}")
            response = _fetch_page(url, timeout=45)
            used_url = url
            print(f"[OK]   Successfully reached: {url}")
            break
        except requests.exceptions.RequestException as exc:
            print(f"[WARN] Failed ({type(exc).__name__}): {url}")
            continue

    if response is None:
        print("[ERROR] All Pakistan AI Policy sources exhausted. Returning empty.")
        return []

    # ── Handle PDF vs HTML ──
    content_type = response.headers.get("Content-Type", "")

    if "pdf" in content_type.lower() or used_url.endswith(".pdf"):
        # For PDF: we save the binary and inform the user.
        # Full PDF text extraction requires PyPDF2 / pdfplumber which are
        # outside the requests+bs4 scope.  We store metadata and a note.
        print("[INFO] PDF detected. Saving binary and returning metadata chunk.")
        print("       TIP: Use `pdfplumber` or `PyPDF2` for full text extraction.")

        # Save the PDF locally for downstream processing.
        pdf_path = "pakistan_ai_policy.pdf"
        with open(pdf_path, "wb") as f:
            f.write(response.content)
        print(f"[OK]   PDF saved to: {pdf_path} ({len(response.content):,} bytes)")

        # Return a single metadata record so the pipeline knows the PDF exists.
        timestamp = datetime.now(timezone.utc).isoformat()
        return [
            {
                "jurisdiction": jurisdiction,
                "source_url": used_url,
                "chunk_text": (
                    f"[PDF DOWNLOADED] Pakistan National AI Policy\n"
                    f"File: {pdf_path}\n"
                    f"Size: {len(response.content):,} bytes\n"
                    f"Note: Use pdfplumber or PyPDF2 to extract full text "
                    f"from the downloaded PDF for chunking."
                ),
                "last_updated": timestamp,
            }
        ]

    else:
        # HTML page — parse with BeautifulSoup.
        soup = BeautifulSoup(response.text, "html.parser")
        # Look for the main content area on MoITT pages.
        content_div = (
            soup.find("div", class_="post-content")
            or soup.find("div", class_="entry-content")
            or soup.find("article")
            or soup.find("div", id="content")
            or soup.find("main")
        )

        if content_div:
            elements = content_div.find_all(["p", "li", "h2", "h3", "h4", "h5"])
            raw_text = "\n\n".join(el.get_text(separator=" ") for el in elements)
        else:
            raw_text = soup.body.get_text(separator="\n") if soup.body else ""

        cleaned = _clean_text(raw_text)

        if not cleaned:
            print("[WARN] No text extracted from Pakistan AI Policy HTML page.")
            return []

        chunks = _chunk_text(cleaned)
        records = _build_records(chunks, jurisdiction=jurisdiction, source_url=used_url)
        print(f"[OK]   Extracted {len(records)} chunk(s) for Pakistan AI Policy.")
        return records


# ══════════════════════════════════════════════════════════════════════
# TARGET 3: EU AI Act  (EUR-Lex Official Portal)
# ══════════════════════════════════════════════════════════════════════

def fetch_eu_ai_act() -> List[Dict[str, str]]:
    """
    Fetch the text of the **EU AI Act (Regulation (EU) 2024/1689)** from
    the official EUR-Lex portal.

    Source: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689

    EUR-Lex is the official online access point for EU law, maintained by
    the Publications Office of the European Union.  The HTML version
    contains the full regulation text in structured <div> elements.

    Returns:
        A list of chunk dictionaries.
    """
    url = "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689"
    print(f"[INFO] Fetching EU AI Act from: {url}")

    response = _fetch_page(url)
    soup = BeautifulSoup(response.text, "html.parser")

    # ── Extraction Strategy ──
    # EUR-Lex renders the regulation body inside a <div id="TexteOnly">
    # or a <div class="texte">.  We target those containers.
    content_div = (
        soup.find("div", id="TexteOnly")
        or soup.find("div", class_="texte")
        or soup.find("div", id="document1")
        or soup.find("body")
    )

    if content_div:
        # EUR-Lex structures articles in <p> and <table> elements.
        # We extract text from paragraphs, headings, and list items.
        elements = content_div.find_all(
            ["p", "li", "h1", "h2", "h3", "h4", "td"]
        )
        raw_text = "\n\n".join(el.get_text(separator=" ") for el in elements)
    else:
        print("[WARN] Could not locate EUR-Lex content container; using body.")
        raw_text = soup.body.get_text(separator="\n") if soup.body else ""

    cleaned = _clean_text(raw_text)

    if not cleaned:
        print("[WARN] No text extracted for EU AI Act.")
        return []

    chunks = _chunk_text(cleaned)
    records = _build_records(
        chunks, jurisdiction="European Union", source_url=url
    )

    print(f"[OK]   Extracted {len(records)} chunk(s) for EU AI Act.")
    return records


# ══════════════════════════════════════════════════════════════════════
# Orchestrator: Run All Scrapers
# ══════════════════════════════════════════════════════════════════════

def scrape_all_laws() -> List[Dict[str, str]]:
    """
    Run every target scraper and merge results into one flat list.

    This is the main entry point for the pipeline.  Each scraper is
    wrapped in its own try/except so that a failure in one jurisdiction
    does not prevent the others from completing.

    Returns:
        A combined list of all chunk dictionaries across jurisdictions.
    """
    all_records: List[Dict[str, str]] = []

    scrapers = [
        ("US Copyright § 107", fetch_us_copyright_section_107),
        ("Pakistan AI Policy", fetch_pakistan_ai_policy),
        ("EU AI Act",          fetch_eu_ai_act),
    ]

    for name, scraper_fn in scrapers:
        print(f"\n{'─' * 60}")
        print(f"  SCRAPING: {name}")
        print(f"{'─' * 60}")
        try:
            records = scraper_fn()
            all_records.extend(records)
        except Exception as exc:
            # Catch ANY exception so one broken scraper doesn't crash the
            # entire pipeline.  Log the error and continue.
            print(f"[FATAL] {name} scraper failed: {type(exc).__name__}: {exc}")

    return all_records


# ══════════════════════════════════════════════════════════════════════
# CLI Entry Point
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import json

    print("=" * 60)
    print("  LAWS.AI — Legal Text Scraper Pipeline")
    print(f"  Run started at: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    results = scrape_all_laws()

    # ── Summary ──
    print(f"\n{'═' * 60}")
    print(f"  SCRAPING COMPLETE")
    print(f"  Total chunks collected: {len(results)}")
    print(f"{'═' * 60}")

    # Print a compact summary per jurisdiction.
    jurisdictions = {}
    for rec in results:
        j = rec["jurisdiction"]
        jurisdictions[j] = jurisdictions.get(j, 0) + 1

    for j, count in jurisdictions.items():
        print(f"  • {j}: {count} chunk(s)")

    # ── Save to JSON ──
    output_file = "scraped_laws.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n[OK] Results saved to: {output_file}")

    # ── Preview first record from each jurisdiction ──
    print(f"\n{'─' * 60}")
    print("  PREVIEW (first 200 chars of first chunk per jurisdiction)")
    print(f"{'─' * 60}")
    seen = set()
    for rec in results:
        if rec["jurisdiction"] not in seen:
            seen.add(rec["jurisdiction"])
            preview = rec["chunk_text"][:200].replace("\n", " ")
            print(f"\n  [{rec['jurisdiction']}]")
            print(f"  Source: {rec['source_url']}")
            print(f"  Pulled: {rec['last_updated']}")
            print(f"  Text:   {preview}...")
