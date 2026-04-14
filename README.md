# Paper-Fetcher
# 📡 LitRadar

An academic literature tracker built for communication science researchers. It searches Semantic Scholar for new papers across your topics of interest, tracks what your favourite scholars are publishing, and saves everything straight to Zotero and/or Notion.

You can run it as a Python script from the terminal, or use the Streamlit web interface if you prefer something visual.

---

## What it does

Every time you run it, LitRadar:

1. Searches Semantic Scholar https://www.semanticscholar.org/ using your keywords (organised by topic)
2. Checks what your tracked scholars have published recently
3. Searches directly inside specific journals you care about
4. Filters out non-English papers, papers without abstracts, and anything you've already saved before
5. Saves the new stuff to Zotero (sorted into collections by topic) and/or Notion

It remembers what it's already saved, so running it weekly won't give you duplicates.

---

## Setup

**1. Install dependencies**

```bash
pip install requests pyzotero notion-client streamlit
```

**2. Copy the config file and fill in your credentials**

```bash
cp config.example.json config.json
```

Open `config.json` and fill in:

- `semantic_scholar.api_key` — get one at [semanticscholar.org/product/api](https://www.semanticscholar.org/product/api)
- `zotero.library_id` and `zotero.api_key` — find both at [zotero.org/settings/security](https://www.zotero.org/settings/security)
- `notion.token` and `notion.database_id` — set up at [notion.so/my-integrations](https://notion.so/my-integrations)

**3. Set up your Notion database**

Create a database with these columns:

| Column | Type |
|--------|------|
| Title | Title |
| Authors | Text |
| Year | Text |
| Journal | Text |
| DOI | Text |
| Abstract | Text |
| URL | URL |
| Source | Select |
| Tier | Select |

Then share the database with your Notion integration (open the database → `...` → Connections → add your integration).

**4. Set up Zotero collections (optional)**

Create collections in Zotero for each topic, then add their keys to `config.json` under `collection_keys`. The collection key is the 8-character string in the collection URL on zotero.org.

---

## Running it

**Option A: Terminal**

```bash
# Run everything (keywords + scholars + journals), save to both Zotero and Notion
py paper_fetcher.py --mode all --target both

# Preview results without saving anything
py paper_fetcher.py --mode all --dry-run

# Only search by keywords
py paper_fetcher.py --mode search

# Only track scholars
py paper_fetcher.py --mode authors

# Only search inside specific journals
py paper_fetcher.py --mode journals

# Clear the cache if something went wrong mid-run
py paper_fetcher.py --clear-cache
```

**Option B: Web interface**

```bash
py -m streamlit run app.py
```

Opens a browser tab where you can fill in your API keys, pick a mode, preview results, and save — all without touching the terminal again.

---

## How the search is organised

Papers are grouped into five tiers:

| Tier | What it searches |
|------|-----------------|
| **Tier 1** | Core topics: AI fairness, sexual behaviour & youth, social media & wellbeing, gender studies, entertainment & youth media |
| **Tier 2** | Interdisciplinary crossover: biology, anthropology, sociology, public health, political psychology |
| **Tier 3** | Specific scholars: ASCoR Youth & Media Entertainment group + global scholars in relevant fields |
| **Tier 4** | (included in Tier 3) Global scholars by research area |
| **Tier 5** | Direct journal search: your watchlist journals + high-impact comm/psychology/gender/interdisciplinary outlets |

You can edit all of this in `topics.json`. Keywords support wildcards (`effect*` matches effects, effective, effectiveness, etc.).

---

## Files in this project

```
paper_fetcher/
├── paper_fetcher.py     # Core script — all the search and save logic
├── app.py               # Streamlit web interface
├── topics.json          # Keywords, scholars, and journals to track
├── journals.json        # Journal reference list
├── config.json          # Your API keys (don't commit this to git!)
├── config.example.json  # Template for config.json
├── saved_dois.json      # Auto-generated: tracks what's already been saved
└── cache.json           # Auto-generated: temporary cache during a run
```

Keep `config.json` out of version control. Add it to `.gitignore`:

```
config.json
saved_dois.json
cache.json
```

---

## Customising topics and journals

Everything is in `topics.json`. The structure is straightforward:

- **Tier 1** (`tier1_core`): Add or remove keywords under each topic group. Use `*` for wildcards.
- **Tier 2** (`tier2_interdisciplinary`): Same structure, but these are searched with a lower result limit (5 per keyword).
- **Tier 3** (`tier3_ascor_scholars`): List of scholar names. LitRadar looks them up by name on Semantic Scholar.
- **Tier 4** (`tier4_global_scholars`): Same as Tier 3, grouped by research area.
- **Tier 5** (`tier5_journals`): Journal names, searched directly using the `venue` parameter.

---

## A few things to know

- The Semantic Scholar API allows 1 request per second with a personal key. A full run across all tiers takes around 20–40 minutes.
- If a run crashes halfway through, just run it again — the cache (`cache.json`) saves your progress so it won't re-request what it already fetched.
- `saved_dois.json` is your deduplication history. If you delete it, the next run will treat everything as new.
- The `fieldsOfStudy` filter is set to `Social Sciences,Psychology` to keep results relevant and filter out pure computer science papers.

---

## Built with

- [Semantic Scholar API](https://www.semanticscholar.org/product/api)
- [pyzotero](https://github.com/urschrei/pyzotero)
- [notion-client](https://github.com/ramnes/notion-sdk-py)
- [Streamlit](https://streamlit.io)
