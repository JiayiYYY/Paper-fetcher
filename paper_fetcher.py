"""
paper_fetcher.py — Wise Waffle backend
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests

BASE_DIR      = Path(__file__).parent
CONFIG_PATH   = BASE_DIR / "config.json"
TOPICS_PATH   = BASE_DIR / "topics.json"
JOURNALS_PATH = BASE_DIR / "journals.json"
CACHE_PATH    = BASE_DIR / "cache.json"
SAVED_PATH    = BASE_DIR / "saved_dois.json"

S2_HEADERS: dict = {}
S2_BASE        = "https://api.semanticscholar.org/graph/v1"
S2_BULK_SEARCH = f"{S2_BASE}/paper/search/bulk"
S2_AUTHOR_SEARCH = f"{S2_BASE}/author/search"
PAPER_FIELDS   = "title,authors,year,abstract,externalIds,venue,publicationDate,url,openAccessPdf,publicationTypes"

# ── Config ────────────────────────────────────────────────────────────────────

def load_json(path):
    if not path.exists():
        print(f"[ERROR] 找不到文件：{path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ── Cache ─────────────────────────────────────────────────────────────────────

def load_cache():
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(data):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clear_cache():
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()
        print("[缓存] 已清除")

# ── Saved history ─────────────────────────────────────────────────────────────

def load_saved():
    if SAVED_PATH.exists():
        with open(SAVED_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def record_saved(papers):
    existing = load_saved()
    for p in papers:
        key = p["doi"].strip().lower() if p.get("doi") else p.get("title","").strip().lower()
        if key:
            existing.add(key)
    with open(SAVED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(existing), f, ensure_ascii=False, indent=2)
    print(f"[记录] saved_dois.json 现有 {len(existing)} 条记录")

def filter_new(papers):
    saved = load_saved()
    new, skipped = [], 0
    for p in papers:
        key = p["doi"].strip().lower() if p.get("doi") else p.get("title","").strip().lower()
        if key and key in saved:
            skipped += 1
        else:
            new.append(p)
    if skipped:
        print(f"[去重] 过滤掉 {skipped} 篇已保存的论文，剩余 {len(new)} 篇新论文")
    return new

# ── HTTP ──────────────────────────────────────────────────────────────────────

def _request(method, url, retries=5, **kwargs):
    kwargs.setdefault("headers", S2_HEADERS)
    kwargs.setdefault("timeout", 20)
    for attempt in range(retries):
        try:
            r = requests.get(url, **kwargs) if method == "GET" else requests.post(url, **kwargs)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = (2 ** attempt) * 5
                print(f"  [限速 429] 等待 {wait}s…")
                time.sleep(wait)
                continue
            if r.status_code in (500, 502, 503, 504):
                wait = (2 ** attempt) * 3
                print(f"  [服务器错误 {r.status_code}] 等待 {wait}s…")
                time.sleep(wait)
                continue
            print(f"  [警告] HTTP {r.status_code}：{url}")
            return None
        except requests.RequestException as e:
            wait = (2 ** attempt) * 3
            print(f"  [网络错误] {e}，{wait}s 后重试…")
            time.sleep(wait)
    print(f"  [失败] 已达最大重试次数：{url}")
    return None

# ── Filters ───────────────────────────────────────────────────────────────────

def _is_english(paper):
    text = (paper.get("title") or "") + " " + (paper.get("abstract") or "")
    if not text.strip():
        return True
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / len(text)
    return ascii_ratio > 0.85

def _has_abstract(paper):
    abstract = paper.get("abstract") or ""
    return len(abstract.strip()) > 100

def _is_recent(paper, since):
    pub = paper.get("publicationDate") or paper.get("pub_date", "")
    if pub:
        return pub >= since
    year = paper.get("year") or paper.get("publication_year", "")
    return str(year) >= since[:4] if year else False

# ── Normalize ─────────────────────────────────────────────────────────────────

def normalize(paper, tag=""):
    """Normalize a paper dict from S2 or OpenAlex into a standard format."""
    raw_authors = paper.get("authors", [])
    # Handle both S2 format (list of dicts with "name") and already-normalized (list of strings)
    if raw_authors and isinstance(raw_authors[0], dict):
        authors = [a.get("name", "") or a.get("display_name", "") for a in raw_authors]
    else:
        authors = [str(a) for a in raw_authors]
    authors = [a for a in authors if a]  # remove empty

    doi = (paper.get("externalIds") or {}).get("DOI", "") or paper.get("doi", "") or ""
    if doi.startswith("https://doi.org/"):
        doi = doi[len("https://doi.org/"):]

    pdf_url = ""
    if paper.get("openAccessPdf"):
        pdf_url = paper["openAccessPdf"].get("url", "") or ""

    # pub_date: try both S2 and OpenAlex field names
    pub_date = (paper.get("publicationDate") or paper.get("publication_date") or "")

    return {
        "title":    paper.get("title", "Untitled") or "Untitled",
        "authors":  authors,
        "year":     str(paper.get("year") or paper.get("publication_year") or ""),
        "pub_date": pub_date,
        "abstract": paper.get("abstract", "") or "",
        "journal":  paper.get("venue") or paper.get("journal", "") or "",
        "doi":      doi,
        "url":      paper.get("url", "") or pdf_url,
        "tag":      tag,
    }

def deduplicate(papers):
    seen, result = set(), []
    for p in papers:
        key = p["doi"].strip().lower() if p.get("doi") else p.get("title","").strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(p)
    return result

# ── S2 bulk search ────────────────────────────────────────────────────────────

def search_bulk(query, since, max_results=100):
      params = {
        "query":                 query,
        "fields":                PAPER_FIELDS,
        "publicationTypes":      "JournalArticle",
        "publicationDateOrYear": f"{since}:",
        "sort":                  "publicationDate:desc",
        "fieldsOfStudy":         "Sociology,Psychology,Art,History,Political Science,Education,Linguistics,Law,Agricultural and Food Sciences",
    }
    results = []
    while len(results) < max_results:
        data = _request("GET", S2_BULK_SEARCH, params=params)
        if not data:
            break
        batch = [p for p in data.get("data", []) if _is_english(p) and _has_abstract(p)]
        results.extend(batch)
        token = data.get("token")
        if not token or len(results) >= max_results:
            break
        params = {**params, "token": token}
        time.sleep(1.2)
    return results[:max_results]

# ── Authors ───────────────────────────────────────────────────────────────────

def resolve_author_ids(names):
    name_to_id = {}
    for name in names:
        data = _request("GET", S2_AUTHOR_SEARCH,
                        params={"query": name, "limit": 1, "fields": "name,authorId"})
        if data:
            hits = data.get("data", [])
            if hits:
                name_to_id[name] = hits[0]["authorId"]
                print(f"    ✓ {name} → {hits[0]['authorId']}")
            else:
                print(f"    ✗ {name}：未找到")
        time.sleep(1.2)
    return name_to_id

def get_papers_for_authors(author_ids, since, papers_per_author=15):
    all_papers = []
    for author_id in author_ids:
        url  = f"{S2_BASE}/author/{author_id}/papers"
        data = _request("GET", url, params={"fields": PAPER_FIELDS, "limit": 50})
        if not data:
            time.sleep(1.2)
            continue
        papers = data.get("data", [])
        recent = [p for p in papers if _is_recent(p, since) and _is_english(p) and _has_abstract(p)]
        recent = sorted(recent, key=lambda p: p.get("publicationDate") or "", reverse=True)
        all_papers.extend(recent[:papers_per_author])
        time.sleep(1.2)
    return all_papers

# ── Run search (Tier 1+2) ─────────────────────────────────────────────────────

def run_search(topics, since):
    collected = []
    print("\n[Tier 1] 核心主题搜索")
    for group, keywords in topics["tier1_core"].items():
        if group.startswith("_"): continue
        print(f"  {group}")
        for kw in keywords:
            papers = search_bulk(kw, since=since, max_results=10)
            collected.extend(normalize(p, tag=f"tier1:{group}") for p in papers)
            time.sleep(1.2)

    print("\n[Tier 2] 跨学科补充")
    for group, keywords in topics["tier2_interdisciplinary"].items():
        if group.startswith("_"): continue
        print(f"  {group}")
        for kw in keywords:
            papers = search_bulk(kw, since=since, max_results=5)
            collected.extend(normalize(p, tag=f"tier2:{group}") for p in papers)
            time.sleep(1.2)

    deduped = deduplicate(collected)
    print(f"\n[搜索] 去重前 {len(collected)} 篇 → 去重后 {len(deduped)} 篇")
    return deduped

# ── Run authors (Tier 3+4) ────────────────────────────────────────────────────

def run_authors(topics, since):
    scholar_names = list(topics["tier3_ascor_scholars"]["scholars"])
    for group, names in topics.get("tier4_global_scholars", {}).items():
        if not group.startswith("_"):
            scholar_names.extend(names)
    scholar_names = list(dict.fromkeys(scholar_names))

    print(f"\n[Tier 3+4] 解析 {len(scholar_names)} 位学者 ID…")
    name_to_id = resolve_author_ids(scholar_names)
    if not name_to_id:
        return []

    print(f"\n[Tier 3] 批量拉取 {len(name_to_id)} 位学者近期论文…")
    raw_papers = get_papers_for_authors(list(name_to_id.values()), since=since)

    id_to_name = {v: k for k, v in name_to_id.items()}
    collected, journal_log = [], []
    for p in raw_papers:
        author_tag = "ascor"
        for a in p.get("authors", []):
            aid = a.get("authorId", "")
            if aid in id_to_name:
                author_tag = f"ascor:{id_to_name[aid]}"
                break
        norm = normalize(p, tag=author_tag)
        collected.append(norm)
        if norm["journal"]:
            journal_log.append(norm["journal"])

    deduped = deduplicate(collected)
    print(f"\n[学者] 去重后 {len(deduped)} 篇")
    if journal_log:
        print("\n" + "="*52)
        for j, n in Counter(journal_log).most_common(10):
            print(f"  {n:3d}  {j}")
        print("="*52)
    return deduped

# ── Run journals (Tier 5) via OpenAlex ───────────────────────────────────────

def _openalex_rebuild_abstract(inv):
    if not inv:
        return ""
    words = []
    for word, positions in inv.items():
        for pos in positions:
            words.append((pos, word))
    words.sort(key=lambda x: x[0])
    return " ".join(w for _, w in words)

def run_journals(since):
    journal_cfg = load_json(JOURNALS_PATH)
    collected = []
    print("\n[Tier 5] OpenAlex journal sweep")

    for group, journals in journal_cfg.items():
        if group.startswith("_"): continue
        print(f"  {group}")

        for item in journals:
            journal   = item["name"]
            source_id = item["id"]
            if not source_id:
                print(f"    {journal[:50]}: skipped (no id)")
                continue

            all_results, page = [], 1
            while True:
                params = {
                    "filter":   f"primary_location.source.id:{source_id},from_publication_date:{since},type:article",
                    "per-page": 100,
                    "page":     page,
                    "select":   "title,authorships,publication_date,publication_year,doi,abstract_inverted_index,primary_location,open_access,id",
                }
                try:
                    r = requests.get("https://api.openalex.org/works", params=params, timeout=20)
                except requests.RequestException as e:
                    print(f"    {journal[:50]}: network error {e}")
                    break
                if r.status_code != 200:
                    print(f"    {journal[:50]}: HTTP {r.status_code}")
                    break

                data    = r.json()
                results = data.get("results", [])
                if not results:
                    break

                for p in results:
                    # authors as list of dicts with "name" key
                    authors = []
                    for a in p.get("authorships", []):
                        name = (a.get("author") or {}).get("display_name", "")
                        if name:
                            authors.append({"name": name})

                    doi = p.get("doi", "") or ""
                    if doi.startswith("https://doi.org/"):
                        doi = doi[len("https://doi.org/"):]

                    loc    = p.get("primary_location") or {}
                    src    = loc.get("source") or {}
                    landing = loc.get("landing_page_url", "") or ""
                    oa     = p.get("open_access") or {}
                    pdf    = oa.get("oa_url", "") or ""
                    pub_date = p.get("publication_date", "") or ""

                    # Only keep papers within the time window
                    if pub_date and pub_date < since:
                        continue

                    paper = {
                        "title":           p.get("title", "") or "Untitled",
                        "authors":         authors,
                        "year":            str(p.get("publication_year", "") or ""),
                        "publicationDate": pub_date,
                        "abstract":        _openalex_rebuild_abstract(p.get("abstract_inverted_index")),
                        "venue":           src.get("display_name", "") or journal,
                        "externalIds":     {"DOI": doi},
                        "doi":             doi,
                        "url":             landing or pdf or p.get("id", ""),
                        "openAccessPdf":   {"url": pdf} if pdf else None,
                    }
                    all_results.append(paper)

                print(f"    {journal[:50]}: page {page}, kept={len(all_results)}")
                if len(results) < 100:
                    break
                page += 1
                time.sleep(0.8)

            print(f"    {journal[:50]}: {len(all_results)} total")
            collected.extend(normalize(p, tag=f"tier5:{group}") for p in all_results)
            time.sleep(0.5)

    deduped = deduplicate(collected)
    print(f"\n[期刊] 去重后 {len(deduped)} 篇")
    return deduped

# ── Tier helpers ──────────────────────────────────────────────────────────────

def _get_tier(tag):
    if tag.startswith("tier1"): return "tier1"
    if tag.startswith("tier2"): return "tier2"
    if tag.startswith("ascor"): return "tier3"
    if tag.startswith("tier5"): return "tier5"
    return "tier1"

def _get_topic_key(tag):
    if tag.startswith("ascor"): return "tier3:ascor"
    return ":".join(tag.split(":")[:2]) if ":" in tag else tag

# ── Save to Zotero ────────────────────────────────────────────────────────────

def save_to_zotero(papers, config, dry_run=False):
    if dry_run:
        print(f"\n[Dry-run] Zotero：{len(papers)} 篇（未执行）")
        return
    try:
        from pyzotero import zotero
    except ImportError:
        print("[ERROR] pip install pyzotero")
        return

    cfg       = config.get("zotero", {})
    zot       = zotero.Zotero(cfg["library_id"], cfg.get("library_type", "user"), cfg["api_key"])
    coll_keys = cfg.get("collection_keys", {})

    topic_groups: dict = {}
    for p in papers:
        topic_groups.setdefault(_get_topic_key(p["tag"]), []).append(p)

    total = 0
    for topic, ps in sorted(topic_groups.items()):
        coll  = coll_keys.get(topic, "")
        items = []
        for p in ps:
            item = zot.item_template("journalArticle")
            item["title"]            = p["title"]
            item["abstractNote"]     = p["abstract"]
            item["publicationTitle"] = p["journal"]
            item["date"]             = p["pub_date"] or p["year"]
            item["DOI"]              = p["doi"]
            item["url"]              = p["url"]
            item["extra"]            = f"source_tag: {p['tag']}"
            item["creators"]         = [
                {"creatorType": "author", "firstName": "", "lastName": n}
                for n in p["authors"]
            ]
            if coll:
                item["collections"] = [coll]
            items.append(item)
        for i in range(0, len(items), 50):
            zot.create_items(items[i:i+50])
        total += len(items)
        print(f"[Zotero] {topic}：{len(items)} 篇 → {'collection ' + coll if coll else '根目录'}")
    print(f"[Zotero] 共保存 {total} 篇")

# ── Save to Notion ────────────────────────────────────────────────────────────

def save_to_notion(papers, config, dry_run=False):
    if dry_run:
        print(f"\n[Dry-run] Notion：{len(papers)} 篇（未执行）")
        return
    try:
        from notion_client import Client
    except ImportError:
        print("[ERROR] pip install notion-client")
        return

    cfg    = config.get("notion", {})
    notion = Client(auth=cfg["token"])
    db_id  = cfg["database_id"]
    print(f"[Notion] db: {db_id}")
    saved = skipped = 0

    for p in papers:
        # authors is always list of strings after normalize()
        authors_str = "; ".join(str(a) for a in p.get("authors", []))[:2000]
        tier = _get_tier(p["tag"])
        props = {
            "Title":    {"title":     [{"text": {"content": (p.get("title") or "")[:2000]}}]},
            "Authors":  {"rich_text": [{"text": {"content": authors_str}}]},
            "Year":     {"rich_text": [{"text": {"content": str(p.get("year") or "")}}]},
            "Journal":  {"rich_text": [{"text": {"content": (p.get("journal") or "")[:500]}}]},
            "DOI":      {"rich_text": [{"text": {"content": (p.get("doi") or "")[:500]}}]},
            "Abstract": {"rich_text": [{"text": {"content": (p.get("abstract") or "")[:2000]}}]},
            "Source":   {"rich_text": [{"text": {"content": p.get("tag", "")}}]},
            "Tier":     {"select":    {"name": tier}},
        }
        url = p.get("url", "")
        if url:
            props["URL"] = {"url": url}
        try:
            result = notion.pages.create(parent={"database_id": db_id}, properties=props)
            saved += 1
            print(f"  [✓] {p['title'][:60]} → {result.get('id','')}")
            time.sleep(0.35)
        except Exception as e:
            print(f"  [✗] {type(e).__name__}: {e}")
            skipped += 1

    print(f"[Notion] 已保存 {saved} 篇，跳过 {skipped} 篇")

# ── CLI main ──────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode",        "-m", choices=["search","authors","journals","all"], default="all")
    p.add_argument("--target",      "-t", choices=["zotero","notion","both"], default="both")
    p.add_argument("--dry-run",     action="store_true")
    p.add_argument("--clear-cache", action="store_true")
    return p.parse_args()

def main():
    global S2_HEADERS
    args   = parse_args()
    config = load_json(CONFIG_PATH)
    topics = load_json(TOPICS_PATH)

    if args.clear_cache:
        clear_cache()

    s2_key = config.get("semantic_scholar", {}).get("api_key", "")
    if s2_key:
        S2_HEADERS = {"x-api-key": s2_key}
        print("[API] S2 key loaded ✓")
    else:
        print("[API] no key, using anonymous")

    since = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    print(f"追踪范围：{since} 至今\n")

    cache, all_papers = load_cache(), []

    if args.mode in ("search","all"):
        if "search" in cache:
            all_papers.extend(cache["search"])
        else:
            papers = run_search(topics, since)
            cache["search"] = papers; save_cache(cache)
            all_papers.extend(papers)

    if args.mode in ("authors","all"):
        if "authors" in cache:
            all_papers.extend(cache["authors"])
        else:
            papers = run_authors(topics, since)
            cache["authors"] = papers; save_cache(cache)
            all_papers.extend(papers)

    if args.mode in ("journals","all"):
        if "journals" in cache:
            all_papers.extend(cache["journals"])
        else:
            papers = run_journals(since)
            cache["journals"] = papers; save_cache(cache)
            all_papers.extend(papers)

    if args.mode == "all":
        all_papers = deduplicate(all_papers)

    all_papers = filter_new(all_papers)
    print(f"\n共 {len(all_papers)} 篇新论文待保存")
    if not all_papers:
        print("没有新论文，退出。")
        return

    if args.target in ("zotero","both"):
        save_to_zotero(all_papers, config, dry_run=args.dry_run)
    if args.target in ("notion","both"):
        save_to_notion(all_papers, config, dry_run=args.dry_run)
    if not args.dry_run:
        record_saved(all_papers)
        clear_cache()
    print("\n完成。")

if __name__ == "__main__":
    main()
