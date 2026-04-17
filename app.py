"""
app.py — Wise Waffle: Academic Literature Tracker
Run with: py -m streamlit run app.py
"""

import builtins
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

import streamlit as st
import paper_fetcher as pf

st.set_page_config(page_title="Wise Waffle", page_icon="🧇", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:wght@300;400;500&display=swap');

:root {
    --ink:    #1a1a1a;
    --paper:  #fdf8f2;
    --accent: #d63d6e;
    --teal:   #2aaa8a;
    --yellow: #f5a623;
    --blush:  #f7c5d5;
    --soft:   #ede8e0;
    --muted:  #9a9490;
}

html, body, [class*="css"] { font-family: Cambria, Georgia, serif; background-color:var(--paper); color:var(--ink); }

section[data-testid="stSidebar"] { background-color:#3d2c1e !important; }
section[data-testid="stSidebar"] * { color:#fdf0e4 !important; }
section[data-testid="stSidebar"] input { color:var(--ink) !important; background:#fff !important; }
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] * { color:var(--ink) !important; }
section[data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] * { color:var(--ink) !important; }

h1, h2, h3 { font-family: Cambria, Georgia, serif; }
h1 { font-size:2.8rem; letter-spacing:-0.02em; }
h3 { font-weight:500; font-size:1rem; }

.paper-card {
    background:white; border:1px solid var(--soft); border-left:3px solid var(--accent);
    border-radius:6px; padding:1.1rem 1.3rem; margin-bottom:0.75rem;
    transition: box-shadow 0.15s;
}
.paper-card:hover { box-shadow: 0 2px 12px rgba(214,61,110,0.1); }
.paper-title { font-family:Cambria,Georgia,serif; font-size:1.05rem; margin-bottom:0.2rem; }
.paper-meta  { font-family:'DM Mono',monospace; font-size:0.72rem; color:var(--muted); margin-bottom:0.4rem; }
.paper-tag {
    display:inline-block; font-family:'DM Mono',monospace; font-size:0.65rem;
    padding:2px 7px; border-radius:20px; background:var(--soft); color:var(--ink); margin-right:4px;
}
.tag-tier1 { background:#fde0ea; color:#d63d6e; }
.tag-tier2 { background:#d4f0e8; color:#1e8a6e; }
.tag-tier3 { background:#fef3d6; color:#b87c0a; }
.tag-tier5 { background:#e8e0f5; color:#6b3a8f; }

.stat-box   { background:white; border:1px solid var(--soft); border-radius:8px; padding:1rem; text-align:center; }
.stat-num   { font-family:Cambria,Georgia,serif; font-size:2.2rem; color:var(--accent); }
.stat-label { font-size:0.75rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em; }

.stButton > button {
    background:var(--accent) !important; color:white !important; border:none !important;
    border-radius:20px !important; font-family:Cambria,Georgia,serif !important;
    font-weight:500 !important; padding:0.5rem 1.8rem !important;
}
.stButton > button:hover { opacity:0.88; }

.intro-box {
    background: linear-gradient(135deg, #fff5f8 0%, #f0faf6 100%);
    border: 1px solid var(--blush); border-radius: 12px;
    padding: 1.8rem 2rem; margin-bottom: 1rem;
}
.tier-pill {
    display:inline-block; font-family:'DM Mono',monospace; font-size:0.7rem;
    padding:3px 10px; border-radius:20px; margin:2px;
}
.abstract-text { font-size:0.85rem; color:#444; line-height:1.6; margin-top:0.5rem; }
hr { border-color:var(--soft); }

@keyframes bounce {
    0%, 100% { transform: translateY(0); }
    50%       { transform: translateY(-8px); }
}
</style>
""", unsafe_allow_html=True)

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
TOPICS_PATH = BASE_DIR / "topics.json"
SAVED_PATH  = BASE_DIR / "saved_dois.json"

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
    "tier5:your_watchlist":                  "📰 Watchlist Journals",
    "tier5:high_impact_comm":                "📰 High Impact Comm",
    "tier5:psychology_adjacent":             "📰 Psychology Adjacent",
    "tier5:gender_feminist":                 "📰 Gender & Feminist",
    "tier5:interdisciplinary_high_impact":   "📰 Interdisciplinary",
}

JOURNAL_GROUPS = {
    "your_watchlist":                "📌 Watchlist",
    "high_impact_comm":              "📡 High Impact Communication",
    "psychology_adjacent":           "🧠 Psychology Adjacent",
    "gender_feminist":               "♀ Gender & Feminist",
    "interdisciplinary_high_impact": "🔬 Interdisciplinary",
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_json_safe(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    return None

def saved_count():
    data = load_json_safe(SAVED_PATH)
    return len(data) if data else 0

def get_topic_key(tag):
    if tag.startswith("ascor"): return "tier3:ascor"
    parts = tag.split(":")
    return f"{parts[0]}:{parts[1]}" if len(parts) >= 2 else tag

def tag_color(tag):
    if tag.startswith("tier1"): return "tag-tier1"
    if tag.startswith("tier2"): return "tag-tier2"
    if tag.startswith("tier5"): return "tag-tier5"
    return "tag-tier3"

def tier_label(tag):
    if tag.startswith("tier1"): return "Core"
    if tag.startswith("tier2"): return "Crossover"
    if tag.startswith("tier5"): return "Journal"
    return "Scholar"

def topic_display(tag):
    key = get_topic_key(tag)
    if key in TOPIC_LABELS: return TOPIC_LABELS[key]
    parts = tag.split(":")
    return parts[1] if len(parts) >= 2 else tag

def paper_key(p):
    return (p.get("doi") or p.get("title", "")).strip().lower()

def render_paper_card(p):
    tag        = p.get("tag", "")
    doi        = p.get("doi", "")
    url        = p.get("url", "") or (f"https://doi.org/{doi}" if doi else "")
    title      = p.get("title", "Untitled")
    title_html = f'<a href="{url}" target="_blank" style="text-decoration:none;color:inherit;">{title}</a>' if url else title
    authors    = p.get("authors", [])
    authors_str = ", ".join(authors[:4]) + (" et al." if len(authors) > 4 else "")
    journal    = p.get("journal", "")
    pub_date   = p.get("pub_date", "") or p.get("year", "")
    cls        = tag_color(tag)

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

COLLECTION_KEY_LABELS = {
    "tier1:ai_fairness_decolonial":          "Core — AI Fairness & Decolonial",
    "tier1:sexual_behavior_youth":           "Core — Sexual Behavior & Youth",
    "tier1:social_media_wellbeing":          "Core — Social Media & Wellbeing",
    "tier1:gender_studies":                  "Core — Gender Studies",
    "tier1:entertainment_youth_media":       "Core — Entertainment & Youth",
    "tier2:biology_crossover":               "Cross — Biology",
    "tier2:anthropology_crossover":          "Cross — Anthropology",
    "tier2:sociology_crossover":             "Cross — Sociology",
    "tier2:public_health_crossover":         "Cross — Public Health",
    "tier2:political_psychology_crossover":  "Cross — Political Psychology",
    "tier3:ascor":                           "Scholars — ASCoR & Global",
    "tier5:your_watchlist":                  "Journal — Watchlist",
    "tier5:high_impact_comm":                "Journal — High Impact Comm",
    "tier5:psychology_adjacent":             "Journal — Psychology Adjacent",
    "tier5:gender_feminist":                 "Journal — Gender & Feminist",
    "tier5:interdisciplinary_high_impact":   "Journal — Interdisciplinary",
}

def build_config(s2_key, zotero_id, zotero_key, notion_tok, notion_db, collection_keys=None):
    cfg = load_json_safe(CONFIG_PATH) or {}
    if s2_key: cfg["semantic_scholar"] = {"api_key": s2_key}
    if zotero_id and zotero_key:
        z = cfg.get("zotero", {})
        z.update({"library_id": zotero_id, "api_key": zotero_key, "library_type": "user"})
        if collection_keys:
            z["collection_keys"] = {k: v for k, v in collection_keys.items() if v.strip()}
        cfg["zotero"] = z
    if notion_tok and notion_db:
        cfg["notion"] = {"token": notion_tok, "database_id": notion_db}
    return cfg

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {"results": [], "saved_this": 0, "selected_keys": set(), "page": 1, "last_filtered_count": 0, "prefill": False}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 🧇")
    st.divider()

    # Host auto-fill
    try:
        host_secrets = dict(st.secrets["host"]) if "host" in st.secrets else {}
    except Exception:
        host_secrets = {}
    is_host = bool(host_secrets)

    st.markdown("### API Keys")
    if is_host:
        if st.button("⚡ Fill my credentials"):
            st.session_state["prefill"] = True
            # Write all values directly into session state
            st.session_state["s2_key_input"]     = host_secrets.get("s2_key", "")
            st.session_state["zotero_id_input"]  = host_secrets.get("zotero_id", "")
            st.session_state["zotero_key_input"] = host_secrets.get("zotero_key", "")
            st.session_state["notion_tok_input"] = host_secrets.get("notion_tok", "")
            st.session_state["notion_db_input"]  = host_secrets.get("notion_db", "")
            for k in COLLECTION_KEY_LABELS:
                st.session_state[f"coll_{k}"] = host_colls.get(k, "")

    if st.session_state.get("prefill") and is_host:
        s2_key     = st.text_input("Semantic Scholar API Key", type="password",                    key="s2_key_input",     placeholder="Enter key…")
        zotero_id  = st.text_input("Zotero Library ID",                                            key="zotero_id_input",  placeholder="e.g. 10541129")
        zotero_key = st.text_input("Zotero API Key",           type="password",                    key="zotero_key_input")
        notion_tok = st.text_input("Notion Token",             type="password",                    key="notion_tok_input", placeholder="secret_…")
        notion_db  = st.text_input("Notion Database ID",                                           key="notion_db_input",  placeholder="32-char ID")
    else:
        s2_key     = st.text_input("Semantic Scholar API Key", type="password", placeholder="Enter key…")
        zotero_id  = st.text_input("Zotero Library ID",        placeholder="e.g. 10541129")
        zotero_key = st.text_input("Zotero API Key",           type="password")
        notion_tok = st.text_input("Notion Token",             type="password", placeholder="secret_…")
        notion_db  = st.text_input("Notion Database ID",       placeholder="32-char ID")

    with st.expander("📁 Zotero Collection Keys (optional)"):
        st.markdown('<p style="font-size:0.75rem;color:#aaa;margin-bottom:0.5rem">8-char key from each collection URL. Leave blank to save to root library.</p>', unsafe_allow_html=True)
        try:
            host_colls = dict(st.secrets["host_collections"]) if "host_collections" in st.secrets else {}
        except Exception:
            host_colls = {}
        collection_keys = {}
        for key, label in COLLECTION_KEY_LABELS.items():
            prefilled = host_colls.get(key, "") if st.session_state.get("prefill") else ""
            collection_keys[key] = st.text_input(label, value=prefilled, placeholder="e.g. ABC12345", key=f"coll_{key}")
        st.write("host_colls keys:", list(host_colls.keys())[:3])
        st.write("COLLECTION_KEY_LABELS keys:", list(COLLECTION_KEY_LABELS.keys())[:3])
    st.divider()
    st.markdown("### Search Settings")
    mode = st.selectbox("Mode", ["all","search","authors","journals"],
        format_func=lambda x: {"all":"All (keywords + scholars + journals)",
                                "search":"Keywords only","authors":"Scholars only","journals":"Journals only"}[x])
    target = st.selectbox("Save to", ["view","both","zotero","notion"],
        format_func=lambda x: {"view":"View only (no save)","both":"Zotero + Notion",
                                "zotero":"Zotero only","notion":"Notion only"}[x])
    days_back = st.slider("Look back (days)", 30, 365, 365, step=30)
    dry_run   = st.checkbox("Dry run (preview, don't save)", value=True)

    st.divider()
    st.markdown("### Stats")
    st.markdown(f'<div class="stat-box"><div class="stat-num">{saved_count()}</div>'
                f'<div class="stat-label">Saved all-time</div></div>', unsafe_allow_html=True)
    if st.button("🗑 Reset history"):
        if SAVED_PATH.exists(): SAVED_PATH.unlink()
        st.success("History cleared.")

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding: 2.5rem 0 1rem 0;">
    <div style="font-size:3.5rem; animation: bounce 2s ease infinite; display:inline-block;">🧇</div>
    <h1 style="font-family:Cambria,Georgia,serif; font-size:3.2rem; letter-spacing:-0.02em;
               background: linear-gradient(135deg, #d63d6e, #f5a623, #2aaa8a);
               -webkit-background-clip: text; -webkit-text-fill-color: transparent;
               background-clip: text; margin: 0.3rem 0 0.5rem 0;">
        Wise Waffle
    </h1>
    <p style="color:#9a9490; font-family:'DM Mono',monospace; font-size:0.85rem; letter-spacing:0.12em; text-transform:uppercase;">
        Weekly academic literature tracker &nbsp;·&nbsp; Semantic Scholar → Zotero & Notion
    </p>
</div>
""", unsafe_allow_html=True)

# ── Introduction ──────────────────────────────────────────────────────────────
with st.expander("👋 What is this?", expanded=True):
    st.markdown("""
<div class="intro-box">

Hi there. I'm a wandering waffle in the Netherlands — don't ask me why waffle, I don't even particularly like waffles. Or stroopwafels.

I'm a researcher in communication science. My work touches on things I genuinely find fascinating:

<span class="tier-pill" style="background:#fde0ea;color:#d63d6e">AI Fairness & Decolonial perspectives</span>
<span class="tier-pill" style="background:#fde0ea;color:#d63d6e">Sexual Behavior & Youth</span>
<span class="tier-pill" style="background:#fde0ea;color:#d63d6e">Social Media & Wellbeing</span>
<span class="tier-pill" style="background:#fde0ea;color:#d63d6e">Gender Studies</span>
<span class="tier-pill" style="background:#fde0ea;color:#d63d6e">Entertainment & Youth Media</span>

And because I refuse to stay in my lane, I also pull in crossover stuff from:

<span class="tier-pill" style="background:#d4f0e8;color:#1e8a6e">Biology</span>
<span class="tier-pill" style="background:#d4f0e8;color:#1e8a6e">Anthropology</span>
<span class="tier-pill" style="background:#d4f0e8;color:#1e8a6e">Sociology</span>
<span class="tier-pill" style="background:#d4f0e8;color:#1e8a6e">Public Health</span>
<span class="tier-pill" style="background:#d4f0e8;color:#1e8a6e">Political Psychology</span>

That's what this app is for — keeping tabs on the literature so I don't have to manually stalk every journal every week.
You're very welcome to check out the **[GitHub repo](https://github.com)** and fork it for your own research interests.

---

**How it works**

You need three API keys to run this:
- 🔑 **Semantic Scholar** — free, [request here](https://www.semanticscholar.org/product/api)
- 📚 **Zotero** — free, from [zotero.org/settings/security](https://www.zotero.org/settings/security)
- 📝 **Notion** — free, from [notion.so/my-integrations](https://notion.so/my-integrations)

**What the search tiers mean:**

| Tier | What it does |
|------|-------------|
| 🔴 **Core** | Keyword search across my main research topics |
| 🟢 **Crossover** | Interdisciplinary searches — limited results per keyword to avoid noise |
| 🟡 **Scholars** | Tracks recent publications from specific researchers I follow (ASCoR + global) |
| 🟣 **Journals** | Full sweep of journals I follow — all recent articles, no keyword filter |

Hit **▶ Run** to fetch papers, preview results here, then tick what you want and save selectively to Zotero and/or Notion.

</div>
""", unsafe_allow_html=True)

    # Journal list — as real Python code, NOT inside the markdown string
    with st.expander("📋 Journals we search (Tier 5)"):
        topics_data = load_json_safe(TOPICS_PATH) or {}
        tier5 = topics_data.get("tier5_journals", {})
        for group, journals in tier5.items():
            if group.startswith("_"):
                continue
            label = JOURNAL_GROUPS.get(group, group)
            st.markdown(f"**{label}**")
            cols = st.columns(3)
            for i, j in enumerate(journals):
                cols[i % 3].markdown(f"· {j}")
            st.markdown("")

st.divider()

# ── Config status ─────────────────────────────────────────────────────────────
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
    if not config_ok:
        st.warning("Enter your Semantic Scholar API key in the sidebar to start.")
    elif dry_run:
        st.info("Dry run — results shown but nothing saved.")

# ── Run ───────────────────────────────────────────────────────────────────────
if run_btn:
    st.session_state["results"]       = []
    st.session_state["saved_this"]    = 0
    st.session_state["selected_keys"] = set()
    st.session_state["page"]          = 1

    config = build_config(s2_key, zotero_id, zotero_key, notion_tok, notion_db, collection_keys)
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
                log_lines.append("\n── Tier 5: Journal sweep ──"); update_log()
                all_papers.extend(pf.run_journals(topics, since))
            if mode == "all":
                all_papers = pf.deduplicate(all_papers)

            # Only filter against saved history if we're actually going to save later
            # In view/dry-run mode we still want to show all results
            if not dry_run and target != "view":
                all_papers = pf.filter_new(all_papers)
                log_lines.append(f"\n{len(all_papers)} new papers (after dedup with history)")
            else:
                log_lines.append(f"\n{len(all_papers)} papers found (dry run / view mode)")
            update_log()

            st.session_state["results"] = all_papers

            # Auto-save only if not dry_run and not view and not using manual selection
            if all_papers and not dry_run and target != "view":
                if target in ("zotero", "both") and config.get("zotero"):
                    log_lines.append("\n── Saving to Zotero ──"); update_log()
                    pf.save_to_zotero(all_papers, config)
                if target in ("notion", "both") and config.get("notion"):
                    log_lines.append("\n── Saving to Notion ──"); update_log()
                    pf.save_to_notion(all_papers, config)
                pf.record_saved(all_papers)
                pf.clear_cache()
                st.session_state["saved_this"] = len(all_papers)
            else:
                log_lines.append("Results ready — select papers below to save manually.")

            log_lines.append("\n✓ Done."); update_log()

    except Exception as e:
        log_lines.append(f"\n[ERROR] {e}"); update_log()
        import traceback
        log_lines.append(traceback.format_exc()); update_log()
    finally:
        builtins.print = original_print

# ── Results ───────────────────────────────────────────────────────────────────
results = st.session_state.get("results", [])

if results:
    st.divider()

    # Summary stats
    tier_counts = Counter(pf._get_tier(p["tag"]) for p in results)
    r1, r2, r3, r4, r5 = st.columns(5)
    with r1: st.markdown(f'<div class="stat-box"><div class="stat-num">{len(results)}</div><div class="stat-label">Papers found</div></div>', unsafe_allow_html=True)
    with r2: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier1",0)}</div><div class="stat-label">Core</div></div>', unsafe_allow_html=True)
    with r3: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier2",0)}</div><div class="stat-label">Crossover</div></div>', unsafe_allow_html=True)
    with r4: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier3",0)}</div><div class="stat-label">Scholars</div></div>', unsafe_allow_html=True)
    with r5: st.markdown(f'<div class="stat-box"><div class="stat-num">{tier_counts.get("tier5",0)}</div><div class="stat-label">Journals</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    # Filters
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

    all_journals   = sorted(set(p["journal"] for p in results if p.get("journal")))
    journal_filter = st.multiselect("Filter by journal", all_journals, default=[],
                                    placeholder="All journals (select to narrow down…)")

    sc1, sc2 = st.columns([1, 4])
    with sc1:
        sort_by = st.selectbox("Sort by", ["date_desc","date_asc","journal"],
            format_func=lambda x: {"date_desc":"Newest first","date_asc":"Oldest first","journal":"Journal A–Z"}[x])

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
    if sort_by == "date_desc":
        filtered = sorted(filtered, key=lambda p: p.get("pub_date","") or p.get("year",""), reverse=True)
    elif sort_by == "date_asc":
        filtered = sorted(filtered, key=lambda p: p.get("pub_date","") or p.get("year",""))
    else:
        filtered = sorted(filtered, key=lambda p: p.get("journal","").lower())

    # Breakdown chart
    with st.expander("📊 Results breakdown", expanded=True):
        col_chart, col_journals_chart = st.columns(2)
        with col_chart:
            st.markdown("**Papers per topic** *(filtered)*")
            ftc = Counter(get_topic_key(p["tag"]) for p in filtered)
            sorted_t = sorted(ftc.items(), key=lambda x: -x[1])
            max_n = sorted_t[0][1] if sorted_t else 1
            for tk, n in sorted_t:
                label = TOPIC_LABELS.get(tk, tk)
                bar_w = int((n / max_n) * 100)
                color = "#d63d6e" if tk.startswith("tier1") else "#2aaa8a" if tk.startswith("tier2") else "#6b3a8f" if tk.startswith("tier5") else "#b87c0a"
                st.markdown(f"""<div style="margin-bottom:8px">
                  <div style="display:flex;justify-content:space-between;margin-bottom:2px">
                    <span style="font-size:0.78rem;color:#444">{label}</span>
                    <span style="font-family:'DM Mono',monospace;font-size:0.72rem;color:#8a8480">{n}</span>
                  </div>
                  <div style="background:#ede8e0;border-radius:2px;height:5px">
                    <div style="background:{color};width:{bar_w}%;height:5px;border-radius:2px"></div>
                  </div></div>""", unsafe_allow_html=True)
        with col_journals_chart:
            st.markdown("**Top journals** *(filtered)*")
            jlist = [p["journal"] for p in filtered if p.get("journal")]
            if jlist:
                top_j = Counter(jlist).most_common(8)
                max_j = top_j[0][1]
                for j, n in top_j:
                    bar_w = int((n / max_j) * 100)
                    st.markdown(f"""<div style="margin-bottom:8px">
                      <div style="display:flex;justify-content:space-between;margin-bottom:2px">
                        <span style="font-size:0.78rem;color:#444">{j[:40]}</span>
                        <span style="font-family:'DM Mono',monospace;font-size:0.72rem;color:#8a8480">{n}</span>
                      </div>
                      <div style="background:#ede8e0;border-radius:2px;height:5px">
                        <div style="background:#d63d6e;width:{bar_w}%;height:5px;border-radius:2px"></div>
                      </div></div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Pagination
    PAGE_SIZE = 20
    total_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
    if st.session_state.get("last_filtered_count") != len(filtered):
        st.session_state["page"] = 1
        st.session_state["last_filtered_count"] = len(filtered)
    page       = st.session_state["page"]
    start      = (page - 1) * PAGE_SIZE
    page_papers = filtered[start:start + PAGE_SIZE]

    st.markdown(
        f"### Results &nbsp;<small style='color:#9a9490;font-size:0.8rem;font-family:DM Mono,monospace'>"
        f"{len(filtered)} papers · page {page}/{total_pages}</small>",
        unsafe_allow_html=True)

    # Selection controls
    sel1, sel2, sel3 = st.columns([1, 1, 5])
    with sel1:
        if st.button("☑ Select page"):
            for p in page_papers:
                st.session_state["selected_keys"].add(paper_key(p))
    with sel2:
        if st.button("☐ Clear all"):
            st.session_state["selected_keys"] = set()

    n_selected = len(st.session_state["selected_keys"])
    if n_selected:
        st.markdown(f"**{n_selected} paper{'s' if n_selected > 1 else ''} selected**")

    # Paper cards with checkboxes
    for p in page_papers:
        pk      = paper_key(p)
        checked = pk in st.session_state["selected_keys"]
        col_chk, col_card = st.columns([0.04, 0.96])
        with col_chk:
            new_val = st.checkbox("", value=checked, key=f"chk_{pk[:60]}", label_visibility="collapsed")
            if new_val:
                st.session_state["selected_keys"].add(pk)
            else:
                st.session_state["selected_keys"].discard(pk)
        with col_card:
            render_paper_card(p)

    # Pagination controls
    if total_pages > 1:
        pc1, pc2, pc3, pc4, pc5 = st.columns([1, 1, 2, 1, 1])
        with pc1:
            if st.button("⟪ First") and page > 1:
                st.session_state["page"] = 1; st.rerun()
        with pc2:
            if st.button("← Prev") and page > 1:
                st.session_state["page"] = page - 1; st.rerun()
        with pc3:
            st.markdown(f'<div style="text-align:center;font-family:DM Mono,monospace;font-size:0.8rem;'
                        f'color:#9a9490;padding-top:0.5rem">Page {page} of {total_pages}</div>',
                        unsafe_allow_html=True)
        with pc4:
            if st.button("Next →") and page < total_pages:
                st.session_state["page"] = page + 1; st.rerun()
        with pc5:
            if st.button("Last ⟫") and page < total_pages:
                st.session_state["page"] = total_pages; st.rerun()

    # Manual save for selected papers
    st.markdown("---")
    selected_papers = [p for p in filtered if paper_key(p) in st.session_state["selected_keys"]]

    if selected_papers:
        st.markdown(f"### Save {len(selected_papers)} selected paper{'s' if len(selected_papers)>1 else ''}")
        config_now = build_config(s2_key, zotero_id, zotero_key, notion_tok, notion_db, collection_keys)
        sv1, sv2, sv3 = st.columns([1, 1, 4])
        with sv1:
            if st.button("💾 Save to Zotero", disabled=not (zotero_id and zotero_key)):
                try:
                    pf.S2_HEADERS = {"x-api-key": s2_key} if s2_key else {}
                    pf.save_to_zotero(selected_papers, config_now)
                    pf.record_saved(selected_papers)
                    st.session_state["selected_keys"] = set()
                    st.success(f"✓ {len(selected_papers)} papers saved to Zotero.")
                except Exception as e:
                    st.error(f"Zotero save failed: {e}")
        with sv2:
            if st.button("📝 Save to Notion", disabled=not (notion_tok and notion_db)):
                try:
                    pf.S2_HEADERS = {"x-api-key": s2_key} if s2_key else {}
                    pf.save_to_notion(selected_papers, config_now)
                    pf.record_saved(selected_papers)
                    st.session_state["selected_keys"] = set()
                    st.success(f"✓ {len(selected_papers)} papers saved to Notion.")
                except Exception as e:
                    st.error(f"Notion save failed: {e}")
    elif st.session_state["saved_this"] > 0:
        st.success(f"✓ {st.session_state['saved_this']} papers auto-saved.")
