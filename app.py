"""
app.py — LitRadar: Academic Literature Tracker
Run with: py -m streamlit run app.py
"""

import builtins
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

import streamlit as st
import paper_fetcher as pf

st.set_page_config(page_title="LitRadar", page_icon="📡", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap');

:root { --ink:#0f0e0d; --paper:#f7f4ef; --accent:#c84b2f; --soft:#e8e3db; --muted:#8a8480; }

html, body, [class*="css"] { font-family:'DM Sans',sans-serif; background-color:var(--paper); color:var(--ink); }

section[data-testid="stSidebar"] { background-color:var(--ink) !important; }
section[data-testid="stSidebar"] * { color:var(--paper) !important; }

/* Fix: API key input text black */
section[data-testid="stSidebar"] input { color:var(--ink) !important; background:#fff !important; }
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] * { color:var(--ink) !important; }
section[data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] * { color:var(--ink) !important; }

h1 { font-family:'DM Serif Display',serif; font-size:2.8rem; letter-spacing:-0.02em; }
h3 { font-family:'DM Sans',sans-serif; font-weight:500; font-size:1rem; }

.paper-card {
    background:white; border:1px solid var(--soft); border-left:3px solid var(--accent);
    border-radius:4px; padding:1.1rem 1.3rem; margin-bottom:0.75rem;
}
.paper-title { font-family:'DM Serif Display',serif; font-size:1.05rem; margin-bottom:0.2rem; }
.paper-meta  { font-family:'DM Mono',monospace; font-size:0.72rem; color:var(--muted); margin-bottom:0.4rem; }
.paper-tag {
    display:inline-block; font-family:'DM Mono',monospace; font-size:0.65rem;
    padding:2px 7px; border-radius:2px; background:var(--soft); color:var(--ink); margin-right:4px;
}
.tag-tier1 { background:#fde8e2; color:#c84b2f; }
.tag-tier2 { background:#e2edf7; color:#2a5f8f; }
.tag-tier3 { background:#e2f0e8; color:#2d6a4f; }

.stat-box   { background:white; border:1px solid var(--soft); border-radius:4px; padding:1rem; text-align:center; }
.stat-num   { font-family:'DM Serif Display',serif; font-size:2.2rem; color:var(--accent); }
.stat-label { font-size:0.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; }

.stButton > button {
    background:var(--accent) !important; color:white !important; border:none !important;
    border-radius:3px !important; font-family:'DM Sans',sans-serif !important;
    font-weight:500 !important; padding:0.5rem 1.5rem !important;
}
.abstract-text { font-size:0.85rem; color:#444; line-height:1.6; margin-top:0.5rem; }
.tag-tier5 { background: #f0e8f7; color: #6b3a8f; }
hr { border-color:var(--soft); }
</style>
""", unsafe_allow_html=True)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
TOPICS_PATH = BASE_DIR / "topics.json"
SAVED_PATH  = BASE_DIR / "saved_dois.json"

# ── Topic labels ──────────────────────────────────────────────────────────────
TOPIC_LABELS = {
    "tier1:ai_fairness_decolonial":          "AI Fairness & Decolonial",
    "tier1:sexual_behavior_youth":           "Sexual Behavior & Youth",
    "tier1:social_media_wellbeing":          "Social Media & Wellbeing",
    "tier1:gender_studies":                  "Gender Studies",
    "tier1:entertainment_youth_media":       "Entertainment & Youth Media",
    "tier2:biology_crossover":               "× Biology",
    "tier2:anthropology_crossover":          "× Anthropology",
    "tier2:sociology_crossover":             "× Sociology",
    "tier2:public_health_crossover":         "× Public Health",
    "tier2:political_psychology_crossover":  "× Political Psychology",
    "tier3:ascor":                           "ASCoR & Global Scholars",
    "tier5:your_watchlist":                  "📰 Your Watchlist Journals",
    "tier5:high_impact_comm":                "📰 High Impact Comm",
    "tier5:psychology_adjacent":             "📰 Psychology Adjacent",
    "tier5:gender_feminist":                 "📰 Gender & Feminist",
    "tier5:interdisciplinary_high_impact":   "📰 Interdisciplinary",
}

def get_topic_key(tag: str) -> str:
    if tag.startswith("ascor"): return "tier3:ascor"
    parts = tag.split(":")
    return f"{parts[0]}:{parts[1]}" if len(parts) >= 2 else tag

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json_safe(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    return None

def saved_count():
    data = load_json_safe(SAVED_PATH)
    return len(data) if data else 0

def tag_color(tag): return "tag-tier1" if tag.startswith("tier1") else "tag-tier2" if tag.startswith("tier2") else "tag-tier5" if tag.startswith("tier5") else "tag-tier3"
def tier_label(tag): return "Core" if tag.startswith("tier1") else "Crossover" if tag.startswith("tier2") else "Journal" if tag.startswith("tier5") else "Scholar"

def topic_display(tag):
    key = get_topic_key(tag)
    if key in TOPIC_LABELS: return TOPIC_LABELS[key]
    # For individual scholars
    parts = tag.split(":")
    return parts[1] if len(parts) >= 2 else tag

def render_paper_card(p):
    tag      = p.get("tag", "")
    doi      = p.get("doi", "")
    url      = p.get("url", "") or (f"https://doi.org/{doi}" if doi else "")
    title    = p.get("title", "Untitled")
    title_html = f'<a href="{url}" target="_blank" style="text-decoration:none;color:inherit;">{title}</a>' if url else title
    authors  = p.get("authors", [])
    authors_str = ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")
    journal  = p.get("journal", "")
    pub_date = p.get("pub_date", "") or p.get("year", "")
    cls      = tag_color(tag)

    st.markdown(f"""
    <div class="paper-card">
        <div class="paper-title">{title_html}</div>
        <div class="paper-meta">{authors_str} &nbsp;·&nbsp; {journal} &nbsp;·&nbsp; {pub_date}</div>
        <span class="paper-tag {cls}">{tier_label(tag)}</span>
        <span class="paper-tag">{topic_display(tag)}</span>
        {"<span class='paper-tag'>" + doi + "</span>" if doi else ""}
    </div>
    """, unsafe_allow_html=True)

    abstract = p.get("abstract", "")
    if abstract:
        with st.expander("Abstract", expanded=False):
            st.markdown(f'<p class="abstract-text">{abstract[:800]}{"…" if len(abstract)>800 else ""}</p>',
                        unsafe_allow_html=True)

def build_config(s2_key, zotero_id, zotero_key, notion_tok, notion_db):
    cfg = load_json_safe(CONFIG_PATH) or {}
    if s2_key: cfg["semantic_scholar"] = {"api_key": s2_key}
    if zotero_id and zotero_key:
        z = cfg.get("zotero", {})
        z.update({"library_id": zotero_id, "api_key": zotero_key, "library_type": "user"})
        cfg["zotero"] = z
    if notion_tok and notion_db:
        cfg["notion"] = {"token": notion_tok, "database_id": notion_db}
    return cfg

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {"results": [], "saved_this": 0}.items():
    if k not in st.session_state: st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📡 LitRadar")
    st.markdown("*Academic literature tracker*")
    st.divider()

    st.markdown("### API Keys")
    s2_key     = st.text_input("Semantic Scholar API Key", type="password", placeholder="Enter key…")
    zotero_id  = st.text_input("Zotero Library ID",        placeholder="e.g. 10541129")
    zotero_key = st.text_input("Zotero API Key",           type="password")
    notion_tok = st.text_input("Notion Token",             type="password", placeholder="secret_…")
    notion_db  = st.text_input("Notion Database ID",       placeholder="32-char ID")

    st.divider()
    st.markdown("### Search Settings")
    mode = st.selectbox("Mode", ["all","search","authors","journals"],
        format_func=lambda x: {"all":"All (keywords + scholars + journals)","search":"Keywords only","authors":"Scholars only","journals":"Journals only"}[x])
    target = st.selectbox("Save to", ["view","both","zotero","notion"],
        format_func=lambda x: {"view":"View only (no save)","both":"Zotero + Notion","zotero":"Zotero only","notion":"Notion only"}[x])
    days_back = st.slider("Look back (days)", 30, 365, 365, step=30)
    dry_run   = st.checkbox("Dry run (preview only, don't save)", value=True)

    st.divider()
    st.markdown("### Stats")
    st.markdown(f'<div class="stat-box"><div class="stat-num">{saved_count()}</div><div class="stat-label">Papers saved all-time</div></div>',
                unsafe_allow_html=True)
    if st.button("🗑 Reset saved history"):
        if SAVED_PATH.exists(): SAVED_PATH.unlink()
        st.success("History cleared.")

# ── Main ──────────────────────────────────────────────────────────────────────
st.markdown("# 📡 LitRadar")
st.markdown("*Weekly academic literature tracker · Semantic Scholar → Zotero & Notion*")
st.divider()

config_ok = bool(s2_key)
col_a, col_b, col_c = st.columns(3)
with col_a: st.markdown(f'<div class="stat-box"><div class="stat-num">{"✓" if s2_key else "✗"}</div><div class="stat-label">S2 API Key</div></div>', unsafe_allow_html=True)
with col_b: st.markdown(f'<div class="stat-box"><div class="stat-num">{"✓" if zotero_id and zotero_key else "–"}</div><div class="stat-label">Zotero</div></div>', unsafe_allow_html=True)
with col_c: st.markdown(f'<div class="stat-box"><div class="stat-num">{"✓" if notion_tok and notion_db else "–"}</div><div class="stat-label">Notion</div></div>', unsafe_allow_html=True)

st.divider()

col_run, col_info = st.columns([1, 3])
with col_run:
    run_btn = st.button("▶ Run", disabled=not config_ok)
with col_info:
    if not config_ok: st.warning("Enter your Semantic Scholar API key in the sidebar to start.")
    elif target == "view" or dry_run: st.info("Results will be shown but not saved.")

# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn:
    st.session_state["results"]    = []
    st.session_state["saved_this"] = 0

    config = build_config(s2_key, zotero_id, zotero_key, notion_tok, notion_db)
    topics = load_json_safe(TOPICS_PATH) or {}
    since  = (datetime.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    pf.S2_HEADERS = {"x-api-key": s2_key} if s2_key else {}

    st.markdown("### Progress")
    log_container = st.empty()
    log_lines = [f"Search range: {since} → today"]

    def update_log():
        log_text = "\n".join(log_lines[-80:])
        log_container.markdown(
            f'<div style="background:#0f0e0d;color:#a8d5a2;font-family:DM Mono,monospace;'
            f'font-size:0.75rem;padding:1rem;border-radius:4px;height:220px;overflow-y:auto;">'
            f'<pre>{log_text}</pre></div>', unsafe_allow_html=True)

    original_print = builtins.print
    def patched_print(*args, **kwargs):
        log_lines.append(" ".join(str(a) for a in args))
        update_log()
        original_print(*args, **kwargs)
    builtins.print = patched_print

    try:
        with st.spinner("Fetching papers…"):
            all_papers = []
            if mode in ("search", "all"):
                log_lines.append("\n── Tier 1 & 2: Keyword search ──"); update_log()
                all_papers.extend(pf.run_search(topics, since))
            if mode in ("authors", "all"):
                log_lines.append("\n── Tier 3 & 4: Scholar tracking ──"); update_log()
                all_papers.extend(pf.run_authors(topics, since))
            if mode in ("journals", "all"):
                log_lines.append("\n── Tier 5: Journal search ──"); update_log()
                all_papers.extend(pf.run_journals(topics, since))
            if mode == "all":
                all_papers = pf.deduplicate(all_papers)
            all_papers = pf.filter_new(all_papers)
            log_lines.append(f"\n{len(all_papers)} new papers found"); update_log()

            st.session_state["results"] = all_papers

            if all_papers:
                if target == "view":
                    log_lines.append("View only — nothing saved.")
                elif not dry_run:
                    if target in ("zotero","both") and config.get("zotero"):
                        log_lines.append("\n── Saving to Zotero ──"); update_log()
                        pf.save_to_zotero(all_papers, config)
                    if target in ("notion","both") and config.get("notion"):
                        log_lines.append("\n── Saving to Notion ──"); update_log()
                        pf.save_to_notion(all_papers, config)
                    pf.record_saved(all_papers)
                    pf.clear_cache()
                    st.session_state["saved_this"] = len(all_papers)
                else:
                    log_lines.append("Dry run — results previewed, nothing saved.")
            else:
                log_lines.append("No new papers.")

            log_lines.append("\n✓ Done."); update_log()

    except Exception as e:
        log_lines.append(f"\n[ERROR] {e}"); update_log()
    finally:
        builtins.print = original_print

# ── Results ───────────────────────────────────────────────────────────────────
results = st.session_state.get("results", [])

if results:
    st.divider()

    # ── Summary stats ──
    tier_counts = Counter(pf._get_tier(p["tag"]) for p in results)
    r1, r2, r3, r4, r5 = st.columns(5)
    with r1: st.markdown(f'<div class="stat-box"><div class="stat-num">{len(results)}</div><div class="stat-label">New papers</div></div>', unsafe_allow_html=True)
    with r2: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier1",0)}</div><div class="stat-label">Core topics</div></div>', unsafe_allow_html=True)
    with r3: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier2",0)}</div><div class="stat-label">Crossover</div></div>', unsafe_allow_html=True)
    with r4: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier3",0)}</div><div class="stat-label">Scholars</div></div>', unsafe_allow_html=True)
    with r5: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier5",0)}</div><div class="stat-label">Journals</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    # ── Filters (placed BEFORE breakdown so chart reacts to selection) ──
    all_topic_keys = sorted(set(get_topic_key(p["tag"]) for p in results))
    topic_options  = {tk: TOPIC_LABELS.get(tk, tk) for tk in all_topic_keys}

    fc1, fc2, fc3 = st.columns([1.2, 1.5, 2])
    with fc1:
        tier_filter = st.multiselect("Filter by tier", ["tier1","tier2","tier3","tier5"],
            default=["tier1","tier2","tier3","tier5"],
            format_func=lambda x: {"tier1":"Core","tier2":"Crossover","tier3":"Scholars","tier5":"Journals"}[x])
    with fc2:
        topic_filter = st.multiselect("Filter by topic", list(topic_options.keys()),
            default=list(topic_options.keys()),
            format_func=lambda x: topic_options[x])
    with fc3:
        search_filter = st.text_input("Search", placeholder="Filter by title, author, journal…")

    # Journal filter (separate row)
    all_journals = sorted(set(p["journal"] for p in results if p.get("journal")))
    journal_filter = st.multiselect(
        "Filter by journal",
        all_journals,
        default=[],
        placeholder="All journals (select to narrow down…)"
    )

    sc1, sc2 = st.columns([1, 4])
    with sc1:
        sort_by = st.selectbox("Sort by", ["date_desc","date_asc","journal"],
            format_func=lambda x: {"date_desc":"Date (newest first)","date_asc":"Date (oldest first)","journal":"Journal A–Z"}[x])

    # Apply filters
    filtered = [p for p in results
                if pf._get_tier(p["tag"]) in tier_filter
                and get_topic_key(p["tag"]) in topic_filter]
    if journal_filter:
        filtered = [p for p in filtered if p.get("journal") in journal_filter]
    if search_filter:
        q = search_filter.lower()
        filtered = [p for p in filtered
                    if q in p.get("title","").lower()
                    or q in " ".join(p.get("authors",[])).lower()
                    or q in p.get("journal","").lower()]

    # Sort
    if sort_by == "date_desc":
        filtered = sorted(filtered, key=lambda p: p.get("pub_date","") or p.get("year",""), reverse=True)
    elif sort_by == "date_asc":
        filtered = sorted(filtered, key=lambda p: p.get("pub_date","") or p.get("year",""))
    else:
        filtered = sorted(filtered, key=lambda p: p.get("journal","").lower())

    # ── Breakdown chart (reacts to filtered results) ──
    with st.expander("📊 Results breakdown", expanded=True):
        col_chart, col_journals = st.columns(2)

        with col_chart:
            st.markdown("**Papers per topic** *(filtered)*")
            filtered_topic_counts = Counter(get_topic_key(p["tag"]) for p in filtered)
            sorted_topics = sorted(filtered_topic_counts.items(), key=lambda x: -x[1])
            max_n = sorted_topics[0][1] if sorted_topics else 1
            for tk, n in sorted_topics:
                label = TOPIC_LABELS.get(tk, tk)
                bar_w = int((n / max_n) * 100)
                color = "#c84b2f" if tk.startswith("tier1") else "#2a5f8f" if tk.startswith("tier2") else "#2d6a4f"
                st.markdown(f"""
                <div style="margin-bottom:8px">
                  <div style="display:flex;justify-content:space-between;margin-bottom:2px">
                    <span style="font-size:0.78rem;color:#444">{label}</span>
                    <span style="font-family:'DM Mono',monospace;font-size:0.72rem;color:#8a8480">{n}</span>
                  </div>
                  <div style="background:#e8e3db;border-radius:2px;height:5px">
                    <div style="background:{color};width:{bar_w}%;height:5px;border-radius:2px"></div>
                  </div>
                </div>""", unsafe_allow_html=True)

        with col_journals:
            st.markdown("**Top journals** *(filtered)*")
            journals = [p["journal"] for p in filtered if p.get("journal")]
            if journals:
                top_j = Counter(journals).most_common(8)
                max_j = top_j[0][1]
                for j, n in top_j:
                    bar_w = int((n / max_j) * 100)
                    st.markdown(f"""
                    <div style="margin-bottom:8px">
                      <div style="display:flex;justify-content:space-between;margin-bottom:2px">
                        <span style="font-size:0.78rem;color:#444">{j[:40]}</span>
                        <span style="font-family:'DM Mono',monospace;font-size:0.72rem;color:#8a8480">{n}</span>
                      </div>
                      <div style="background:#e8e3db;border-radius:2px;height:5px">
                        <div style="background:#c84b2f;width:{bar_w}%;height:5px;border-radius:2px"></div>
                      </div>
                    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Pagination ──
    PAGE_SIZE = 20
    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)

    if "page" not in st.session_state:
        st.session_state["page"] = 1
    # Reset to page 1 when filters change
    if st.session_state.get("last_filtered_count") != len(filtered):
        st.session_state["page"] = 1
        st.session_state["last_filtered_count"] = len(filtered)

    page = st.session_state["page"]
    start = (page - 1) * PAGE_SIZE
    end   = start + PAGE_SIZE
    page_papers = filtered[start:end]

    st.markdown(
        f"### Results &nbsp;"
        f"<small style='color:#8a8480;font-size:0.8rem;font-family:DM Mono,monospace'>"
        f"{len(filtered)} papers · page {page}/{total_pages}</small>",
        unsafe_allow_html=True
    )

    for p in page_papers:
        render_paper_card(p)

    # Pagination controls
    if total_pages > 1:
        st.markdown("")
        pc1, pc2, pc3, pc4, pc5 = st.columns([1, 1, 2, 1, 1])
        with pc1:
            if st.button("⟪ First") and page > 1:
                st.session_state["page"] = 1
                st.rerun()
        with pc2:
            if st.button("← Prev") and page > 1:
                st.session_state["page"] = page - 1
                st.rerun()
        with pc3:
            st.markdown(
                f'<div style="text-align:center;font-family:DM Mono,monospace;font-size:0.8rem;'
                f'color:#8a8480;padding-top:0.5rem">Page {page} of {total_pages}</div>',
                unsafe_allow_html=True
            )
        with pc4:
            if st.button("Next →") and page < total_pages:
                st.session_state["page"] = page + 1
                st.rerun()
        with pc5:
            if st.button("Last ⟫") and page < total_pages:
                st.session_state["page"] = total_pages
                st.rerun()

    if st.session_state["saved_this"] > 0:
        st.success(f"✓ {st.session_state['saved_this']} papers saved to {target}.")
