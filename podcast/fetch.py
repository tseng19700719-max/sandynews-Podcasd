"""抓取 RSS 新聞，依時間視窗過濾，並做跨來源去重。"""
from __future__ import annotations

import calendar
import html
import json
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import feedparser
import requests

log = logging.getLogger(__name__)

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


@dataclass
class NewsItem:
    source: str
    section: str
    kind: str
    title: str
    summary: str
    link: str
    published: datetime


@dataclass
class Story:
    """去重後的一則新聞（可能被多家報導）"""
    title: str
    summary: str
    kind: str
    published: datetime
    items: list[NewsItem] = field(default_factory=list)

    @property
    def sources(self) -> list[str]:
        return sorted({i.source for i in self.items})

    @property
    def coverage(self) -> int:
        return len(self.sources)


def _clean(text: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def _strip_source_suffix(title: str) -> str:
    # Google 新聞標題結尾會帶「 - 工商時報」
    return re.sub(r"\s+-\s+[^-]{1,12}$", "", title).strip()


def fetch_feed(cfg: dict, days: int, retries: int = 3, raw: bytes | None = None) -> list[NewsItem]:
    url = cfg["url"].format(days=days)
    if raw is None:
        for attempt in range(1, retries + 1):
            try:
                r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
                r.raise_for_status()
                raw = r.content
                break
            except Exception as e:  # noqa: BLE001
                log.warning("抓取失敗 %s %s（第 %d 次）：%s", cfg["source"], cfg["section"], attempt, e)
                time.sleep(3 * attempt)
        if raw is None:
            return []

    if cfg.get("type") == "cnyes":
        items = _parse_cnyes(raw, cfg)
    else:
        items = _parse_rss(raw, cfg)
    log.info("%s／%s：%d 則", cfg["source"], cfg["section"], len(items))
    return items


def _parse_rss(raw: bytes, cfg: dict) -> list[NewsItem]:
    parsed = feedparser.parse(raw)
    items = []
    for e in parsed.entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not t:
            continue
        pub = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
        raw_title = _clean(e.get("title", ""))
        title = _strip_source_suffix(raw_title)
        source = cfg["source"]
        if source == "Google新聞":   # 用實際媒體名稱，報導家數才算得準
            src = e.get("source") or {}
            source = (src.get("title") if hasattr(src, "get") else "") or \
                (raw_title[len(title):].lstrip(" -") or "Google新聞")
        summary = _clean(e.get("summary", ""))
        if summary.startswith(title[:10]) and len(summary) < len(title) + 30:
            summary = ""  # Google 新聞的 summary 只是標題重複
        if title:
            items.append(NewsItem(source, cfg["section"], _classify(title, cfg["kind"]), title,
                                  summary[:220], e.get("link", ""), pub))
    return items


MACRO_KEYWORDS = ("聯準會", "Fed", "FOMC", "降息", "升息", "利率決策", "通膨", "CPI", "PCE", "PPI", "非農",
                  "就業數據", "失業率", "GDP", "經濟成長", "央行", "美債", "殖利率", "美元指數", "匯率",
                  "新台幣", "日圓", "人民幣", "油價", "原油", "金價", "外銷訂單", "出口", "景氣燈號",
                  "PMI", "經濟數據", "衰退", "財政部", "主計")


def _classify(title: str, default: str) -> str:
    return "macro" if any(k in title for k in MACRO_KEYWORDS) else default


CNYES_INTL = ("美股", "國際", "歐", "亞股", "陸股", "港股", "外匯", "原物料", "期貨", "債")


def _parse_cnyes(raw: bytes, cfg: dict) -> list[NewsItem]:
    try:
        data = json.loads(raw)["items"]["data"]
    except Exception as e:  # noqa: BLE001
        log.warning("鉅亨網格式異常：%s", e)
        return []
    items = []
    for d in data:
        title = _clean(d.get("title", ""))
        if not title or not d.get("publishAt"):
            continue
        cat = d.get("categoryName") or cfg["section"]
        kind = _classify(title, "intl" if any(k in cat for k in CNYES_INTL) else cfg["kind"])
        items.append(NewsItem(
            cfg["source"], cat, kind, title,
            _clean(d.get("summary", ""))[:220],
            f"https://news.cnyes.com/news/id/{d.get('newsId')}",
            datetime.fromtimestamp(int(d["publishAt"]), tz=timezone.utc)))
    return items


def _norm(title: str) -> str:
    return re.sub(r"[\W_]+", "", title).lower()


def _bigrams(s: str) -> set[str]:
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def _similar(a: str, b: str) -> float:
    A, B = _bigrams(a), _bigrams(b)
    return len(A & B) / min(len(A), len(B))


def dedupe(items: list[NewsItem], threshold: float = 0.6) -> list[Story]:
    """相似標題歸為同一則；回傳依「報導家數、時間」排序的 Story 清單。"""
    stories: list[Story] = []
    keys: list[str] = []
    for it in sorted(items, key=lambda x: x.published, reverse=True):
        k = _norm(it.title)
        for idx, sk in enumerate(keys):
            if k == sk or _similar(k, sk) >= threshold:
                st = stories[idx]
                st.items.append(it)
                if len(it.summary) > len(st.summary):
                    st.summary = it.summary
                break
        else:
            stories.append(Story(it.title, it.summary, it.kind, it.published, [it]))
            keys.append(k)
    for st in stories:   # 分類：任一家判為總經就算總經；否則國際採多數決（平手算商業）
        kinds = [i.kind for i in st.items]
        if "macro" in kinds:
            st.kind = "macro"
        else:
            st.kind = "intl" if kinds.count("intl") * 2 > len(kinds) else "business"
    stories.sort(key=lambda s: (s.coverage, s.published), reverse=True)
    return stories


def collect(feeds: list[dict], since: datetime, max_per_feed: int, days: int,
            raw_map: dict[str, bytes] | None = None) -> list[Story]:
    all_items: list[NewsItem] = []
    for cfg in feeds:
        raw = raw_map.get(cfg["url"]) if raw_map else None
        items = [i for i in fetch_feed(cfg, days, raw=raw) if i.published >= since]
        items.sort(key=lambda x: x.published, reverse=True)
        all_items.extend(items[:max_per_feed])
    stories = dedupe(all_items)
    log.info("共 %d 則原始新聞，去重後 %d 則", len(all_items), len(stories))
    return stories
