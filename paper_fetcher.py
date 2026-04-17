"""
paper_fetcher.py
----------------
搜索学术论文并保存到 Zotero 和 Notion。
基于 Semantic Scholar 官方 Tutorial 最佳实践重写：
  - 使用 /paper/search/bulk（推荐，资源消耗更低）
  - 使用 /author/batch POST（批量查询，减少请求数）
  - Exponential backoff（官方要求）
  - 精确短语搜索语法

运行模式：
    python paper_fetcher.py --mode search    # 按主题关键词（过去一个月）
    python paper_fetcher.py --mode authors   # 追踪 ASCoR 学者最新发表
    python paper_fetcher.py --mode all       # 两者都跑

可选参数：
    --target zotero / notion / both   保存目标（默认 both）
    --dry-run                         只打印，不保存
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ─────────────────────────────────────────
# 路径配置
# ─────────────────────────────────────────

BASE_DIR      = Path(__file__).parent
CONFIG_PATH   = BASE_DIR / "config.json"
TOPICS_PATH   = BASE_DIR / "topics.json"
JOURNALS_PATH = BASE_DIR / "journals.json"
CACHE_PATH    = BASE_DIR / "cache.json"   # 搜索结果缓存

# 全局 API headers，main() 中赋值
S2_HEADERS: dict = {}

# ─────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────

S2_BASE          = "https://api.semanticscholar.org/graph/v1"
S2_BULK_SEARCH   = f"{S2_BASE}/paper/search/bulk"   # 推荐搜索端点
S2_AUTHOR_SEARCH = f"{S2_BASE}/author/search"
S2_AUTHOR_BATCH  = f"{S2_BASE}/author/batch"        # 批量作者查询（POST）

# 只请求需要的字段（减少响应体，提升速度）
PAPER_FIELDS  = "title,authors,year,abstract,externalIds,venue,publicationDate,url,openAccessPdf,publicationTypes"
AUTHOR_FIELDS = "name,authorId,paperCount,hIndex"

# ─────────────────────────────────────────
# 配置加载
# ─────────────────────────────────────────

def load_json(path: Path) -> dict:
    if not path.exists():
        print(f"[ERROR] 找不到文件：{path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# ─────────────────────────────────────────
# 缓存（防止崩溃后重复请求 API）
# ─────────────────────────────────────────

def load_cache() -> dict:
    """读取缓存文件，返回 {mode: [papers]} 结构"""
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(data: dict) -> None:
    """保存缓存到文件"""
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clear_cache() -> None:
    if CACHE_PATH.exists():
        CACHE_PATH.unlink()
        print("[缓存] 已清除")

# ─────────────────────────────────────────
# 已保存记录（防止每周重复保存）
# ─────────────────────────────────────────

SAVED_PATH = BASE_DIR / "saved_dois.json"

def load_saved() -> set:
    """读取已保存的论文标识符（DOI 或标题小写）"""
    if SAVED_PATH.exists():
        with open(SAVED_PATH, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def record_saved(papers: list) -> None:
    """把本次保存的论文标识符追加到 saved_dois.json"""
    existing = load_saved()
    for p in papers:
        key = p["doi"].strip().lower() if p["doi"] else p["title"].strip().lower()
        if key:
            existing.add(key)
    with open(SAVED_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(existing), f, ensure_ascii=False, indent=2)
    print(f"[记录] saved_dois.json 现有 {len(existing)} 条记录")

def filter_new(papers: list) -> list:
    """过滤掉已保存过的论文，只保留新的"""
    saved = load_saved()
    new, skipped = [], 0
    for p in papers:
        key = p["doi"].strip().lower() if p["doi"] else p["title"].strip().lower()
        if key and key in saved:
            skipped += 1
        else:
            new.append(p)
    if skipped:
        print(f"[去重] 过滤掉 {skipped} 篇已保存的论文，剩余 {len(new)} 篇新论文")
    return new

# ─────────────────────────────────────────
# HTTP 请求（含 exponential backoff）
# ─────────────────────────────────────────

def _request(method: str, url: str, retries: int = 5, **kwargs) -> dict | None:
    """
    带 exponential backoff 的 HTTP 请求。
    官方要求：遇到 429 必须使用指数退避策略。
    """
    kwargs.setdefault("headers", S2_HEADERS)
    kwargs.setdefault("timeout", 20)

    for attempt in range(retries):
        try:
            if method == "GET":
                r = requests.get(url, **kwargs)
            else:
                r = requests.post(url, **kwargs)

            if r.status_code == 200:
                return r.json()

            if r.status_code == 429:
                wait = (2 ** attempt) * 5   # 5, 10, 20, 40, 80 秒
                print(f"  [限速 429] 等待 {wait}s 后重试（第 {attempt+1}/{retries} 次）...")
                time.sleep(wait)
                continue

            if r.status_code in (500, 502, 503, 504):
                wait = (2 ** attempt) * 3
                print(f"  [服务器错误 {r.status_code}] 等待 {wait}s 后重试（第 {attempt+1}/{retries} 次）...")
                time.sleep(wait)
                continue

            print(f"  [警告] HTTP {r.status_code}：{url}")
            return None

        except requests.RequestException as e:
            wait = (2 ** attempt) * 3
            print(f"  [网络错误] {e}，{wait}s 后重试...")
            time.sleep(wait)

    print(f"  [失败] 已达最大重试次数：{url}")
    return None

# ─────────────────────────────────────────
# 日期工具
# ─────────────────────────────────────────

def _date_one_month_ago() -> str:
    return (datetime.today() - timedelta(days=31)).strftime("%Y-%m-%d")

def _is_recent(paper: dict, since: str) -> bool:
    pub = paper.get("publicationDate")
    if pub:
        return pub >= since
    year = paper.get("year")
    return str(year) >= since[:4] if year else False

# ─────────────────────────────────────────
# 搜索论文（bulk endpoint + token 翻页）
# ─────────────────────────────────────────

def _is_english(paper: dict) -> bool:
    """
    简单英语检测：检查标题和摘要是否主要由 ASCII 字符组成。
    Semantic Scholar 没有 language 字段，用字符集比例作为代理指标。
    """
    text = (paper.get("title") or "") + " " + (paper.get("abstract") or "")
    if not text.strip():
        return True  # 无文本时不过滤
    ascii_ratio = sum(1 for c in text if ord(c) < 128) / len(text)
    return ascii_ratio > 0.85


def _has_abstract(paper: dict) -> bool:
    """过滤掉没有摘要或摘要太短的条目（通常是会议摘要、短通讯等）"""
    abstract = paper.get("abstract") or ""
    return len(abstract.strip()) > 100


def search_bulk(query: str, since: str, max_results: int = 100) -> list:
    """
    使用 /paper/search/bulk 搜索论文。
    支持布尔语法（tutorial 示例）：
      - 精确短语用引号：'"social media" +adolescents'
      - 必须包含：+keyword
      - 排除：-keyword
    """
    params = {
        "query":               query,
        "fields":              PAPER_FIELDS,
        "publicationTypes":    "JournalArticle",        # 只要期刊文章
        "publicationDateOrYear": f"{since}:",           # 从 since 至今
        "sort":                "publicationDate:desc",  # 最新的排前面
    }

    results = []
    url     = S2_BULK_SEARCH

    while len(results) < max_results:
        data = _request("GET", url, params=params)
        if not data:
            break

        batch = [p for p in data.get("data", []) if _is_english(p)]
        results.extend(batch)

        # token 翻页（bulk search 的分页方式）
        token = data.get("token")
        if not token or len(results) >= max_results:
            break

        # 翻下一页：只传 token，其他参数沿用
        params = {"token": token, "fields": PAPER_FIELDS}
        time.sleep(1.2)

    return results[:max_results]

# ─────────────────────────────────────────
# 作者查询（batch endpoint，一次请求多位作者）
# ─────────────────────────────────────────

def resolve_author_ids(names: list[str]) -> dict[str, str]:
    """
    逐一用 /author/search 查找姓名对应的 authorId。
    返回 {name: authorId} 字典。
    """
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


def get_papers_for_authors(author_ids: list[str], since: str, papers_per_author: int = 15) -> list:
    """
    逐一调用 /author/{id}/papers 拉取每位作者的近期论文。
    /author/batch 不支持嵌套的 papers.fields 写法，所以分开请求。
    """
    if not author_ids:
        return []

    all_papers = []
    for author_id in author_ids:
        url  = f"{S2_BASE}/author/{author_id}/papers"
        data = _request("GET", url, params={"fields": PAPER_FIELDS, "limit": 50})
        if not data:
            time.sleep(1.2)
            continue
        papers = data.get("data", [])
        recent = [p for p in papers if _is_recent(p, since) and _is_english(p)]
        recent = sorted(recent, key=lambda p: p.get("publicationDate") or "", reverse=True)
        all_papers.extend(recent[:papers_per_author])
        time.sleep(1.2)

    return all_papers

# ─────────────────────────────────────────
# 数据规范化与去重
# ─────────────────────────────────────────

def normalize(paper: dict, tag: str = "") -> dict:
    authors = [a.get("name", "") for a in paper.get("authors", [])]
    doi     = (paper.get("externalIds") or {}).get("DOI", "") or ""
    pdf_url = ""
    if paper.get("openAccessPdf"):
        pdf_url = paper["openAccessPdf"].get("url", "") or ""
    return {
        "title":    paper.get("title", "Untitled"),
        "authors":  authors,
        "year":     str(paper.get("year", "")),
        "pub_date": paper.get("publicationDate", ""),
        "abstract": paper.get("abstract", "") or "",
        "journal":  paper.get("venue", "") or "",
        "doi":      doi,
        "url":      paper.get("url", "") or pdf_url,
        "tag":      tag,
    }


def deduplicate(papers: list) -> list:
    seen, result = set(), []
    for p in papers:
        key = p["doi"].strip().lower() if p["doi"] else p["title"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            result.append(p)
    return result

# ─────────────────────────────────────────
# 搜索模式（Tier 1 + Tier 2）
# ─────────────────────────────────────────

def run_search(topics: dict, since: str) -> list:
    collected = []

    print("\n[Tier 1] 核心主题搜索")
    for group, keywords in topics["tier1_core"].items():
        if group.startswith("_"):
            continue
        print(f"  {group}")
        for kw in keywords:
            papers = search_bulk(kw, since=since, max_results=10)
            collected.extend(normalize(p, tag=f"tier1:{group}") for p in papers)
            time.sleep(1.2)

    print("\n[Tier 2] 跨学科补充（每组限 5 篇）")
    for group, keywords in topics["tier2_interdisciplinary"].items():
        if group.startswith("_"):
            continue
        print(f"  {group}")
        for kw in keywords:
            papers = search_bulk(kw, since=since, max_results=5)
            collected.extend(normalize(p, tag=f"tier2:{group}") for p in papers)
            time.sleep(1.2)

    deduped = deduplicate(collected)
    print(f"\n[搜索] 去重前 {len(collected)} 篇 → 去重后 {len(deduped)} 篇")
    return deduped

# ─────────────────────────────────────────
# 学者追踪模式（Tier 3）
# ─────────────────────────────────────────

def run_authors(topics: dict, since: str) -> list:
    # 合并 tier3（ASCoR）和 tier4（全球学者）
    scholar_names = list(topics["tier3_ascor_scholars"]["scholars"])

    tier4 = topics.get("tier4_global_scholars", {})
    for group, names in tier4.items():
        if group.startswith("_"):
            continue
        scholar_names.extend(names)

    # 去重（防止同一学者出现在多个列表）
    scholar_names = list(dict.fromkeys(scholar_names))

    print(f"\n[Tier 3+4] 解析 {len(scholar_names)} 位学者 ID（ASCoR + 全球）...")
    name_to_id = resolve_author_ids(scholar_names)

    if not name_to_id:
        print("  未找到任何学者，跳过")
        return []

    print(f"\n[Tier 3] 批量拉取 {len(name_to_id)} 位学者近期论文...")
    raw_papers  = get_papers_for_authors(list(name_to_id.values()), since=since)

    # 为每篇论文标注来源学者（通过 authorId 反查）
    id_to_name = {v: k for k, v in name_to_id.items()}
    collected   = []
    journal_log = []

    for p in raw_papers:
        # 找出论文作者中属于追踪学者的那位
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

    # 高频期刊统计
    if journal_log:
        print("\n" + "="*52)
        print("ASCoR 近期高频期刊 Top 10")
        print("="*52)
        for j, n in Counter(journal_log).most_common(10):
            print(f"  {n:3d}  {j}")
        print("="*52)

    return deduped

# ─────────────────────────────────────────
# 期刊直接搜索（Tier 5）
# ─────────────────────────────────────────

def run_journals(topics: dict, since: str) -> list:
    """
    Tier 5 期刊搜索。
    venue 作为独立参数，query 用通配符 * 不限关键词。
    全量抓取时间段内所有文章，自动翻页。
    """
    tier5 = topics.get("tier5_journals", {})
    if not tier5:
        return []

    collected = []
    print("\n[Tier 5] 期刊全量搜索")

    for group, journals in tier5.items():
        if group.startswith("_"):
            continue
        print(f"  {group}")

        for journal in journals:
            base_params = {
                "query":                 "*",
                "fields":                PAPER_FIELDS,
                "publicationTypes":      "JournalArticle",
                "publicationDateOrYear": f"{since}:",
                "sort":                  "publicationDate:desc",
                "venue":                 journal,
            }

            all_results = []
            params = base_params.copy()

            while True:
                data = _request("GET", S2_BULK_SEARCH, params=params)
                if not data:
                    break
                batch = [p for p in data.get("data", []) if _is_english(p) and _has_abstract(p)]
                all_results.extend(batch)
                token = data.get("token")
                if not token:
                    break
                # Keep base params, only add token for next page
                params = {**base_params, "token": token}
                time.sleep(1.0)

            print(f"    {journal[:50]}: {len(all_results)} 篇")
            collected.extend(normalize(p, tag=f"tier5:{group}") for p in all_results)
            time.sleep(1.0)

    deduped = deduplicate(collected)
    print(f"\n[期刊] 去重后 {len(deduped)} 篇")
    return deduped

# ─────────────────────────────────────────
# Tier 解析工具
# ─────────────────────────────────────────

def _get_tier(tag: str) -> str:
    if tag.startswith("tier1"): return "tier1"
    if tag.startswith("tier2"): return "tier2"
    if tag.startswith("ascor"): return "tier3"
    if tag.startswith("tier5"): return "tier5"
    return "tier1"


def _get_topic_key(tag: str) -> str:
    """
    从 tag 中提取完整 topic key，用于 Zotero collection 映射。
    例如：
      'tier1:ai_fairness_decolonial'  → 'tier1:ai_fairness_decolonial'
      'tier2:biology_crossover'       → 'tier2:biology_crossover'
      'ascor:Patti Valkenburg'        → 'tier3:ascor'
      'tier4:ai_fairness_decolonial'  → 'tier4:ai_fairness_decolonial'
    """
    if tag.startswith("ascor"):
        return "tier3:ascor"
    return tag.split(":")[0] + ":" + tag.split(":")[1] if ":" in tag else tag


# ─────────────────────────────────────────
# 保存到 Zotero（按 tier 存入不同 collection）
# ─────────────────────────────────────────

def save_to_zotero(papers: list, config: dict, dry_run: bool = False) -> None:
    """
    按 topic 将论文存入不同的 Zotero collection。
    config.json 中配置：
      "zotero": {
        "collection_keys": {
          "tier1:ai_fairness_decolonial":      "XXXXXXXX",
          "tier1:sexual_behavior_youth":       "YYYYYYYY",
          "tier1:social_media_wellbeing":      "ZZZZZZZZ",
          "tier1:gender_studies":              "AAAAAAAA",
          "tier1:entertainment_youth_media":   "BBBBBBBB",
          "tier2:biology_crossover":           "CCCCCCCC",
          "tier2:anthropology_crossover":      "DDDDDDDD",
          "tier2:sociology_crossover":         "EEEEEEEE",
          "tier2:public_health_crossover":     "FFFFFFFF",
          "tier2:political_psychology_crossover": "GGGGGGGG",
          "tier3:ascor":                       "HHHHHHHH"
        }
      }
    未配置的 topic 存入根目录。
    """
    if dry_run:
        topic_counts = Counter(_get_topic_key(p["tag"]) for p in papers)
        print(f"\n[Dry-run] Zotero：{len(papers)} 篇（未执行）")
        for topic, count in sorted(topic_counts.items()):
            print(f"  {topic}: {count} 篇")
        return
    try:
        from pyzotero import zotero
    except ImportError:
        print("[ERROR] 请先运行：pip install pyzotero")
        sys.exit(1)

    cfg       = config.get("zotero", {})
    zot       = zotero.Zotero(cfg["library_id"], cfg.get("library_type", "user"), cfg["api_key"])
    coll_keys = cfg.get("collection_keys", {})

    # 按 topic 分组
    topic_groups: dict[str, list] = {}
    for p in papers:
        topic = _get_topic_key(p["tag"])
        topic_groups.setdefault(topic, []).append(p)

    total_saved = 0
    for topic, topic_papers in sorted(topic_groups.items()):
        coll = coll_keys.get(topic, "")
        items = []
        for p in topic_papers:
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
        total_saved += len(items)
        coll_label = f"collection {coll}" if coll else "根目录（未配置）"
        print(f"[Zotero] {topic}：{len(items)} 篇 → {coll_label}")

    print(f"[Zotero] 共保存 {total_saved} 篇")

# ─────────────────────────────────────────
# 保存到 Notion（Tier 字段用 Select 类型）
# ─────────────────────────────────────────

def save_to_notion(papers: list, config: dict, dry_run: bool = False) -> None:
    """
    保存到 Notion。Tier 信息写入 Select 字段 'Tier'，便于筛选过滤。
    Notion database 需要新增一列：'Tier'，类型选 Select。
    """
    if dry_run:
        tier_counts = Counter(_get_tier(p["tag"]) for p in papers)
        print(f"\n[Dry-run] Notion：{len(papers)} 篇（未执行）")
        for tier, count in sorted(tier_counts.items()):
            print(f"  {tier}: {count} 篇")
        return
    try:
        from notion_client import Client
    except ImportError:
        print("[ERROR] 请先运行：pip install notion-client")
        sys.exit(1)

    cfg    = config.get("notion", {})
    notion = Client(auth=cfg["token"])
    db_id  = cfg["database_id"]
    saved  = skipped = 0

    for p in papers:
        tier = _get_tier(p["tag"])
        props = {
            "Title":    {"title":     [{"text": {"content": p["title"][:2000]}}]},
            "Authors":  {"rich_text": [{"text": {"content": "; ".join(p["authors"])[:2000]}}]},
            "Year":     {"rich_text": [{"text": {"content": p["year"]}}]},
            "Journal":  {"rich_text": [{"text": {"content": p["journal"][:500]}}]},
            "DOI":      {"rich_text": [{"text": {"content": p["doi"][:500]}}]},
            "Abstract": {"rich_text": [{"text": {"content": p["abstract"][:2000]}}]},
            "Source":   {"rich_text": [{"text": {"content": p["tag"]}}]},
            "Tier":     {"select":    {"name": tier}},   # Select 字段，可直接筛选
        }
        if p["url"]:
            props["URL"] = {"url": p["url"]}
        try:
            notion.pages.create(parent={"database_id": db_id}, properties=props)
            saved += 1
            time.sleep(0.35)
        except Exception as e:
            print(f"  [Notion 警告] '{p['title'][:50]}' 失败：{e}")
            skipped += 1

    print(f"[Notion] 已保存 {saved} 篇，跳过 {skipped} 篇")

# ─────────────────────────────────────────
# 主程序
# ─────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(description="学术论文月度追踪脚本")
    p.add_argument("--mode",        "-m", choices=["search", "authors", "journals", "all"], default="all")
    p.add_argument("--target",      "-t", choices=["zotero", "notion", "both"], default="both")
    p.add_argument("--dry-run",     action="store_true", help="只打印，不保存")
    p.add_argument("--clear-cache", action="store_true", help="清除缓存，强制重新请求 API")
    return p.parse_args()


def main():
    global S2_HEADERS

    args   = parse_args()
    config = load_json(CONFIG_PATH)
    topics = load_json(TOPICS_PATH)

    if args.clear_cache:
        clear_cache()

    # 加载 Semantic Scholar API key
    s2_key = config.get("semantic_scholar", {}).get("api_key", "")
    if s2_key:
        S2_HEADERS = {"x-api-key": s2_key}
        print("[API] Semantic Scholar API key 已加载 ✓")
    else:
        print("[API] 未找到 API key，使用匿名访问（限速更严格）")

    since = (datetime.today() - timedelta(days=365)).strftime("%Y-%m-%d")
    print(f"追踪范围：{since} 至今\n")

    cache = load_cache()
    all_papers = []

    if args.mode in ("search", "all"):
        if "search" in cache:
            print(f"[缓存] 读取搜索结果（{len(cache['search'])} 篇），跳过 API 请求")
            all_papers.extend(cache["search"])
        else:
            papers = run_search(topics, since)
            cache["search"] = papers
            save_cache(cache)
            all_papers.extend(papers)

    if args.mode in ("authors", "all"):
        if "authors" in cache:
            print(f"[缓存] 读取学者结果（{len(cache['authors'])} 篇），跳过 API 请求")
            all_papers.extend(cache["authors"])
        else:
            papers = run_authors(topics, since)
            cache["authors"] = papers
            save_cache(cache)
            all_papers.extend(papers)

    if args.mode in ("journals", "all"):
        if "journals" in cache:
            print(f"[缓存] 读取期刊结果（{len(cache['journals'])} 篇），跳过 API 请求")
            all_papers.extend(cache["journals"])
        else:
            papers = run_journals(topics, since)
            cache["journals"] = papers
            save_cache(cache)
            all_papers.extend(papers)

    if args.mode == "all":
        all_papers = deduplicate(all_papers)

    # 过滤掉历史上已保存过的论文
    all_papers = filter_new(all_papers)

    print(f"\n共 {len(all_papers)} 篇新论文待保存")
    if not all_papers:
        print("没有新论文，退出。")
        return

    if args.target in ("zotero", "both"):
        save_to_zotero(all_papers, config, dry_run=args.dry_run)

    if args.target in ("notion", "both"):
        save_to_notion(all_papers, config, dry_run=args.dry_run)

    if not args.dry_run:
        record_saved(all_papers)  # 记录本次保存，下次自动跳过
        clear_cache()

    print("\n完成。")


if __name__ == "__main__":
    main()
