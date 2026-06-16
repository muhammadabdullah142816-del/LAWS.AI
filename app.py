import streamlit as st
import groq
import psycopg2

# ── Page config ── must be FIRST Streamlit call ───────────────────────────────
st.set_page_config(
    page_title="LAWS.AI — Compliance Engine",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS injection via st.html (Streamlit ≥ 1.36) ─────────────────────────────
# st.html() bypasses the markdown sanitiser that strips <style> tags
_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
html, body, [class*="css"] { font-family: 'Inter', sans-serif !important; }

/* ── base ───────────────────────────────────────── */
.stApp { background: #080c14 !important; }
section[data-testid="stMain"] > div { background: transparent; }
[data-testid="stSidebar"] {
  background: #05070d !important;
  border-right: 1px solid rgba(48,54,61,.8) !important;
}

/* ── keyframes ───────────────────────────────────── */
@keyframes shimmer { 0%{background-position:-200% center} 100%{background-position:200% center} }
@keyframes fadeUp  { from{opacity:0;transform:translateY(14px)} to{opacity:1;transform:translateY(0)} }
@keyframes fadeIn  { from{opacity:0} to{opacity:1} }
@keyframes pulse   { 0%,100%{opacity:1} 50%{opacity:.45} }

/* ── wordmark ────────────────────────────────────── */
.wm {
  font-size: 2.6rem; font-weight: 900; letter-spacing: -1.6px; line-height: 1;
  background: linear-gradient(135deg,#f0a500 0%,#4da6ff 50%,#3fb950 100%);
  background-size: 220% auto;
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: shimmer 5s linear infinite, fadeUp .5s ease both;
  margin: 0 0 4px;
}
.wm-tag { font-size:.77rem; color:#7d8590; letter-spacing:.3px; margin-bottom:20px; }

/* ── status card ─────────────────────────────────── */
.sc-ok  { display:flex;align-items:center;gap:9px;padding:11px 14px;border-radius:10px;
          background:rgba(63,185,80,.07);border:1px solid rgba(63,185,80,.22);
          font-size:.82rem;font-weight:600;color:#3fb950;margin-bottom:5px; }
.sc-warn{ display:flex;align-items:center;gap:9px;padding:11px 14px;border-radius:10px;
          background:rgba(240,165,0,.07);border:1px solid rgba(240,165,0,.22);
          font-size:.82rem;font-weight:600;color:#f0a500;margin-bottom:5px; }
.sdot   { width:9px;height:9px;border-radius:50%;flex-shrink:0;animation:pulse 2.2s infinite; }

/* ── diag rows ───────────────────────────────────── */
.dr  { display:flex;align-items:center;gap:8px;padding:7px 2px;
       border-bottom:1px solid rgba(48,54,61,.35);font-size:.75rem;color:#b0bac4; }
.dr:last-child { border-bottom:none; }
.dd  { width:7px;height:7px;border-radius:50%;flex-shrink:0;animation:pulse 2.2s infinite; }
.dg  { background:#3fb950; }
.db  { background:#4da6ff; }
.da  { background:#f0a500; }
.dred{ background:#ff6b6b; }

/* ── sidebar labels ──────────────────────────────── */
.sb-lbl { font-size:.68rem;font-weight:700;letter-spacing:.9px;text-transform:uppercase;
          color:#7d8590;margin:16px 0 8px; }

/* ── section label ───────────────────────────────── */
.ctrl-lbl { font-size:.68rem;font-weight:700;letter-spacing:.9px;text-transform:uppercase;
            color:#7d8590;margin:16px 0 7px; }

/* ── flag pills ──────────────────────────────────── */
.fp-row { display:flex;flex-wrap:wrap;gap:5px;margin-bottom:12px; }
.fp     { display:inline-flex;align-items:center;gap:3px;padding:3px 9px;border-radius:20px;
          font-size:.71rem;font-weight:500;background:rgba(255,255,255,.03);
          border:1px solid rgba(48,54,61,.8);color:#b0bac4;
          transition:all .16s ease;cursor:default; }

/* ── divider ─────────────────────────────────────── */
.hr { height:1px;background:linear-gradient(90deg,transparent,rgba(48,54,61,.9),transparent);margin:14px 0; }

/* ── example chips ───────────────────────────────── */
.ex { display:block;padding:8px 11px;border-radius:8px;
      background:rgba(255,255,255,.03);border:1px solid rgba(48,54,61,.8);
      color:#7d8590;font-size:.73rem;line-height:1.5;margin-bottom:5px;font-style:italic; }

/* ── idle placeholder ────────────────────────────── */
.idle { display:flex;flex-direction:column;align-items:center;justify-content:center;
        min-height:58vh;text-align:center;padding:40px 24px;animation:fadeIn .7s ease both; }
.idle-ic { font-size:3.2rem;opacity:.18;margin-bottom:14px; }
.idle-h  { font-size:.98rem;font-weight:600;color:#7d8590;margin-bottom:6px; }
.idle-p  { font-size:.77rem;color:#484f58;line-height:1.65;max-width:320px; }

/* ── stats bar ───────────────────────────────────── */
.stats { display:flex;align-items:center;flex-wrap:wrap;gap:14px;padding:8px 13px;
         background:rgba(255,255,255,.03);border:1px solid rgba(48,54,61,.8);
         border-radius:8px;font-size:.74rem;color:#7d8590;margin-bottom:12px;
         animation:fadeIn .35s ease both; }
.sv    { color:#f0a500;font-weight:600;font-family:'JetBrains Mono',monospace; }

/* ── chips (in stats + blockquotes) ─────────────── */
.chip     { display:inline-flex;align-items:center;gap:3px;padding:2px 7px;
            border-radius:20px;font-size:.67rem;font-weight:600;letter-spacing:.1px; }
.c-eu { background:rgba(77,166,255,.1);color:#4da6ff;border:1px solid rgba(77,166,255,.25); }
.c-us { background:rgba(255,107,107,.1);color:#ff6b6b;border:1px solid rgba(255,107,107,.25); }
.c-pk { background:rgba(63,185,80,.1);color:#3fb950;border:1px solid rgba(63,185,80,.25); }
.c-uk { background:rgba(201,160,245,.1);color:#c9a0f5;border:1px solid rgba(201,160,245,.25); }
.c-ca { background:rgba(255,170,64,.1);color:#ffaa40;border:1px solid rgba(255,170,64,.25); }
.c-xx { background:rgba(125,133,144,.1);color:#7d8590;border:1px solid rgba(125,133,144,.25); }

/* ── source blockquotes ──────────────────────────── */
.src-hdr { display:flex;align-items:center;gap:8px;margin-top:24px;padding-top:18px;
           border-top:1px solid rgba(48,54,61,.8);
           font-size:.67rem;font-weight:700;letter-spacing:.9px;text-transform:uppercase;color:#7d8590; }
.bq     { border-left:3px solid;border-radius:0 8px 8px 0;
          padding:11px 15px 11px 18px;margin-bottom:9px;
          background:rgba(0,0,0,.15);animation:fadeUp .35s ease both; }
.bq-eu  { border-color:#4da6ff; }
.bq-us  { border-color:#ff6b6b; }
.bq-pk  { border-color:#3fb950; }
.bq-uk  { border-color:#c9a0f5; }
.bq-ca  { border-color:#ffaa40; }
.bq-xx  { border-color:#484f58; }
.bq-hd  { display:flex;align-items:center;gap:6px;margin-bottom:6px;flex-wrap:wrap; }
.bq-url { font-family:'JetBrains Mono',monospace;font-size:.67rem;color:#7d8590;word-break:break-all; }
.bq-url a { color:#4da6ff;text-decoration:none; }
.bq-url a:hover { text-decoration:underline; }
.bq-txt { font-size:.8rem;line-height:1.68;color:#b0bac4;margin-top:7px;font-style:italic; }

/* ── Streamlit tab overrides ─────────────────────── */
.stTabs [data-baseweb="tab-list"] {
  background: transparent !important; gap: 3px !important;
  border-bottom: 1px solid rgba(48,54,61,.9) !important;
}
.stTabs [data-baseweb="tab"] {
  background: transparent !important;
  border-radius: 8px 8px 0 0 !important;
  border: 1px solid transparent !important; border-bottom: none !important;
  color: #7d8590 !important; font-family: 'Inter', sans-serif !important;
  font-weight: 500 !important; font-size: .84rem !important;
  padding: 9px 16px !important; transition: all .17s ease !important;
  margin-bottom: -1px !important;
}
.stTabs [data-baseweb="tab"]:hover { color: #e6edf3 !important; background: rgba(255,255,255,.03) !important; }
.stTabs [aria-selected="true"] {
  background: rgba(22,27,34,.9) !important;
  border-color: rgba(48,54,61,.9) !important;
  border-bottom: 2px solid #f0a500 !important;
  color: #f0a500 !important; font-weight: 700 !important;
}
.stTabs [data-baseweb="tab-panel"] {
  background: rgba(22,27,34,.88) !important;
  border: 1px solid rgba(48,54,61,.9) !important; border-top: none !important;
  border-radius: 0 0 14px 14px !important; padding: 24px 28px !important;
  animation: fadeIn .25s ease !important; backdrop-filter: blur(16px) !important;
}
.stTabs [data-baseweb="tab-panel"] p,
.stTabs [data-baseweb="tab-panel"] li { color:#b0bac4 !important; line-height:1.78 !important; }
.stTabs [data-baseweb="tab-panel"] h1,
.stTabs [data-baseweb="tab-panel"] h2,
.stTabs [data-baseweb="tab-panel"] h3 { color:#e6edf3 !important; font-weight:700 !important; }
.stTabs [data-baseweb="tab-panel"] table { width:100% !important; border-collapse:collapse !important; font-size:.85rem !important; }
.stTabs [data-baseweb="tab-panel"] th {
  background:rgba(240,165,0,.08) !important; border:1px solid rgba(48,54,61,.9) !important;
  padding:8px 13px !important; color:#f0a500 !important; font-weight:600 !important; text-align:left !important;
}
.stTabs [data-baseweb="tab-panel"] td { border:1px solid rgba(48,54,61,.9) !important; padding:8px 13px !important; color:#b0bac4 !important; }
.stTabs [data-baseweb="tab-panel"] tr:hover td { background:rgba(255,255,255,.03) !important; }

/* ── Streamlit inputs ────────────────────────────── */
.stTextInput > div > div > input {
  background: rgba(10,13,20,.9) !important; border: 1.5px solid rgba(48,54,61,.9) !important;
  border-radius: 12px !important; color: #e6edf3 !important;
  padding: 13px 17px !important; font-size: .95rem !important;
  font-family: 'Inter', sans-serif !important; caret-color: #f0a500 !important;
  transition: all .2s ease !important;
}
.stTextInput > div > div > input:focus {
  border-color: #f0a500 !important;
  box-shadow: 0 0 0 3px rgba(240,165,0,.1) !important;
}
.stTextInput > div > div > input::placeholder { color:#7d8590 !important; font-style:italic; }

.stSelectbox > div > div {
  background: rgba(255,255,255,.03) !important; border: 1px solid rgba(48,54,61,.9) !important;
  border-radius: 8px !important; color: #e6edf3 !important;
  font-family: 'Inter', sans-serif !important; transition: all .18s ease !important;
}
.stSelectbox > div > div:hover { border-color: rgba(240,165,0,.3) !important; }

/* ── Primary button ──────────────────────────────── */
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg,#f0a500,#d08900) !important;
  border: none !important; border-radius: 12px !important;
  color: #060a10 !important; font-weight: 800 !important;
  font-size: .9rem !important; letter-spacing: .3px !important;
  font-family: 'Inter', sans-serif !important;
  box-shadow: 0 4px 16px rgba(240,165,0,.25) !important;
  transition: all .2s ease !important;
}
.stButton > button[kind="primary"]:hover {
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 26px rgba(240,165,0,.42) !important;
  background: linear-gradient(135deg,#fdb92b,#f0a500) !important;
}
.stButton > button[kind="primary"]:active { transform: translateY(0) !important; }

/* ── Expander ────────────────────────────────────── */
.streamlit-expanderHeader {
  background: rgba(255,255,255,.03) !important; border: 1px solid rgba(48,54,61,.8) !important;
  border-radius: 8px !important; color: #b0bac4 !important;
  font-size: .78rem !important; transition: all .18s ease !important;
}
.streamlit-expanderHeader:hover {
  background: rgba(255,255,255,.06) !important;
  border-color: rgba(240,165,0,.2) !important; color: #e6edf3 !important;
}
.streamlit-expanderContent { background: transparent !important; border: none !important; }

/* ── Scrollbar ───────────────────────────────────── */
::-webkit-scrollbar { width:5px; height:5px; }
::-webkit-scrollbar-track { background:#0d1117; }
::-webkit-scrollbar-thumb { background:#30363d; border-radius:3px; }
::-webkit-scrollbar-thumb:hover { background:#484f58; }

/* ── Spinner ─────────────────────────────────────── */
.stSpinner > div { border-color:#f0a500 transparent transparent transparent !important; }

/* ── Right panel vertical gutter ────────────────── */
.out-panel { padding-left: 8px; }
</style>
"""

try:
    st.html(_CSS)           # Streamlit ≥ 1.36 — preferred, bypasses sanitiser
except AttributeError:
    st.markdown(_CSS, unsafe_allow_html=True)   # fallback for older versions

# ── Backend imports ───────────────────────────────────────────────────────────
try:
    from generator import generate_rag_response
    from retrieve  import get_cached_model, get_connection_pool
    _imports_ok = True
except Exception as _ie:
    _imports_ok = False
    _import_error = str(_ie)

@st.cache_resource
def _warm():
    if not _imports_ok:
        return f"Import error: {_import_error}"
    try:
        get_cached_model()
        get_connection_pool()
        return True
    except Exception as e:
        return str(e)

_ok = _warm()

# ── Session state ─────────────────────────────────────────────────────────────
_defaults = dict(
    synthesis="", clarity="", scores="",
    sources=[], has_result=False, error="", region="All Regions",
)
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Constants ─────────────────────────────────────────────────────────────────
REGIONS = {
    "All Regions":    "🌍",
    "European Union": "🇪🇺",
    "United States":  "🇺🇸",
    "Pakistan":       "🇵🇰",
    "United Kingdom": "🇬🇧",
    "Canada":         "🇨🇦",
}

CHIP_DATA = {
    "European Union": ("c-eu", "bq-eu", "🇪🇺"),
    "United States":  ("c-us", "bq-us", "🇺🇸"),
    "Pakistan":       ("c-pk", "bq-pk", "🇵🇰"),
    "United Kingdom": ("c-uk", "bq-uk", "🇬🇧"),
    "Canada":         ("c-ca", "bq-ca", "🇨🇦"),
}

EXAMPLES = [
    "Is AI folk music training lawful under Pakistan's Copyright Ordinance 1962 vs US Fair Use?",
    "What transparency requirements apply to high-risk AI under the EU AI Act?",
    "Compare Canada's AIDA risk thresholds with EU AI Act Annex III categories.",
    "How does the UK's pro-innovation stance differ from the EU's horizontal AI regulation?",
]

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="wm" style="font-size:1.3rem;margin-bottom:2px;">⚖️ LAWS.AI</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:.72rem;color:#484f58;margin-bottom:16px;">Global Compliance Intelligence Engine<br>Samuelson Framework</div>', unsafe_allow_html=True)
    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

    # ── Step 2: Single status card ────────────────────────────────────────────
    if _ok is True:
        st.markdown(
            '<div class="sc-ok"><span class="sdot" style="background:#3fb950;"></span>🟢&nbsp; System Status: Active</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="sc-warn"><span class="sdot" style="background:#f0a500;"></span>🟡&nbsp; System Status: Degraded</div>',
            unsafe_allow_html=True,
        )

    with st.expander("🛠️ System Diagnostics"):
        db_lbl  = "Connected" if _ok is True else f"Error"
        db_cls  = "dg" if _ok is True else "dred"
        m_lbl   = "Cached"    if _ok is True else "Loading…"
        rows = [
            ("dg",   f"MiniLM-L6-v2 Embeddings — {m_lbl}"),
            (db_cls, f"Supabase pgvector — {db_lbl}"),
            ("dg",   "Groq — llama-3.1-8b-instant"),
            ("da",   "Semantic Query Expansion — Enabled"),
            ("db",   "Balanced Retrieval — 5 Regions"),
        ]
        st.markdown(
            "".join(f'<div class="dr"><span class="dd {d}"></span>{l}</div>' for d, l in rows),
            unsafe_allow_html=True,
        )

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-lbl">🌍 Target Jurisdiction</div>', unsafe_allow_html=True)

    chosen = st.selectbox(
        "Region",
        options=list(REGIONS.keys()),
        index=list(REGIONS.keys()).index(st.session_state.region),
        label_visibility="collapsed",
        format_func=lambda x: f"{REGIONS[x]}  {x}",
        key="sidebar_region",
    )
    st.session_state.region = chosen
    st.markdown('<p style="font-size:.67rem;color:#3d444d;margin-top:18px;">v2.1 · EU · US · PK · UK · CA</p>', unsafe_allow_html=True)

# ── STEP 1: 2-column split canvas ────────────────────────────────────────────
left, right = st.columns([2, 3], gap="large")

# ════════════════════════════════════════════════════════════════════
# LEFT — Control Deck
# ════════════════════════════════════════════════════════════════════
with left:
    region = st.session_state.region

    # Wordmark
    st.markdown(
        '<h1 class="wm">LAWS.AI</h1>'
        '<p class="wm-tag">Cross-border AI compliance analysis</p>',
        unsafe_allow_html=True,
    )

    # Flag pills
    active = list(REGIONS.items())[1:] if region == "All Regions" else [(region, REGIONS[region])]
    st.markdown(
        '<div class="fp-row">' +
        "".join(f'<span class="fp">{f} {j}</span>' for j, f in active) +
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ctrl-lbl">📋 Compliance Question</div>', unsafe_allow_html=True)

    query = st.text_input(
        "query",
        placeholder="e.g. Is AI training on folk music lawful under Pakistani copyright law?",
        label_visibility="collapsed",
        key="query_input",
    )

    analyse = st.button(
        f"{REGIONS[region]}  Analyse →",
        use_container_width=True,
        type="primary",
        key="analyse_btn",
    )

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    st.markdown('<div class="ctrl-lbl">💡 Example Queries</div>', unsafe_allow_html=True)
    st.markdown(
        "".join(f'<div class="ex">"{q}"</div>' for q in EXAMPLES),
        unsafe_allow_html=True,
    )

    # ── Execute ───────────────────────────────────────────────────────────────
    if analyse and query.strip():
        if not _imports_ok:
            st.session_state.error      = f"⚠️ Backend import error: {_import_error}"
            st.session_state.has_result = False
        else:
            with st.spinner(f"{REGIONS[region]} Retrieving & synthesising across {region}…"):
                try:
                    raw, _srcs = generate_rag_response(
                        query_text=query,
                        jurisdiction_filter=region,
                    )
                    sources = list(_srcs)  # lru_cache returns tuple; convert back
                    has = "[SYNTHESIS]" in raw and "[CLARITY_MATRIX]" in raw and "[DEVELOPER_SCORES]" in raw
                    if has:
                        st.session_state.synthesis = raw.split("[SYNTHESIS]")[1].split("[CLARITY_MATRIX]")[0].strip()
                        st.session_state.clarity   = raw.split("[CLARITY_MATRIX]")[1].split("[DEVELOPER_SCORES]")[0].strip()
                        st.session_state.scores    = raw.split("[DEVELOPER_SCORES]")[1].strip()
                    else:
                        st.session_state.synthesis = raw
                        st.session_state.clarity   = "*Clarity matrix embedded in synthesis.*"
                        st.session_state.scores    = "*Developer scores embedded in synthesis.*"

                    st.session_state.sources    = sources
                    st.session_state.has_result = True
                    st.session_state.error      = ""

                except (groq.APIConnectionError, psycopg2.Error) as e:
                    st.session_state.error      = f"⚠️ **Connection error** — {type(e).__name__}: {e}"
                    st.session_state.has_result = False
                except Exception as e:
                    st.session_state.error      = f"⚠️ **Error:** {e}"
                    st.session_state.has_result = False

# ════════════════════════════════════════════════════════════════════
# RIGHT — Analytical Workspace
# ════════════════════════════════════════════════════════════════════
with right:
    st.markdown('<div class="out-panel">', unsafe_allow_html=True)

    if st.session_state.error:
        st.warning(st.session_state.error)

    # Idle state
    if not st.session_state.has_result:
        st.markdown(
            '<div class="idle">'
            '  <div class="idle-ic">⚖️</div>'
            '  <div class="idle-h">Analytical Workspace</div>'
            '  <div class="idle-p">Enter a compliance question on the left and click '
            '    <strong style="color:#f0a500;">Analyse →</strong> to generate a cross-jurisdictional '
            '    legal synthesis with verified legislative citations.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        sources = st.session_state.sources

        # Stats bar
        jc: dict[str, int] = {}
        for s in sources:
            j = s.get("jurisdiction", "Unknown")
            jc[j] = jc.get(j, 0) + 1

        sc_html = " ".join(
            f'<span class="chip {CHIP_DATA.get(j, ("c-xx","","🌐"))[0]}">'
            f'{CHIP_DATA.get(j,("","","🌐"))[2]} {j} ({c})</span>'
            for j, c in jc.items()
        )
        st.markdown(
            f'<div class="stats">'
            f'<span>📦 <span class="sv">{len(sources)}</span> chunks</span>'
            f'<span>🌍 <span class="sv">{len(jc)}</span> region(s)</span>'
            f'<span>🔎 <span class="sv">{st.session_state.region}</span></span>'
            f'<span>{sc_html}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── STEP 3: Source blockquotes ────────────────────────────────────────
        def _bq(srcs: list[dict]) -> str:
            if not srcs:
                return ""
            out = ['<div class="src-hdr">📌 Legal Basis — Verified Citations</div>']
            for i, s in enumerate(srcs):
                j   = s["jurisdiction"]
                sub = s.get("sub_jurisdiction", "")
                url = s["source_url"]
                txt = s["chunk_text"]
                cc, bc, fl = CHIP_DATA.get(j, ("c-xx", "bq-xx", "🌐"))
                lbl  = f"{fl} {j}" + (f" / {sub}" if sub else "")
                snip = txt[:300].replace("\n", " ") + ("…" if len(txt) > 300 else "")
                is_u = url.startswith("http")
                uh   = f'<a href="{url}" target="_blank">{url}</a>' if is_u else f'<span style="color:#484f58;">{url}</span>'
                out.append(
                    f'<div class="bq {bc}" style="animation-delay:{i*.06:.2f}s">'
                    f'<div class="bq-hd"><span class="chip {cc}">{lbl}</span>'
                    f'<span style="color:#484f58;font-size:.66rem;">Source {i+1}</span></div>'
                    f'<div class="bq-url">{uh}</div>'
                    f'<div class="bq-txt">&#8220;{snip}&#8221;</div>'
                    f'</div>'
                )
            return "\n".join(out)

        bq_html = _bq(sources)

        # Tabs
        t1, t2, t3 = st.tabs([
            "📊  Executive Synthesis",
            "⚖️  Legal Clarity Matrix",
            "🧠  Developer Risk Scores",
        ])
        with t1:
            st.markdown(st.session_state.synthesis)
            if bq_html:
                st.markdown(bq_html, unsafe_allow_html=True)
        with t2:
            st.markdown(st.session_state.clarity)
            if bq_html:
                st.markdown(bq_html, unsafe_allow_html=True)
        with t3:
            st.markdown(st.session_state.scores)
            if bq_html:
                st.markdown(bq_html, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)
