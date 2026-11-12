"""抓取 RSS 新聞，依時間視窗過濾，並做跨來源去重。"""
from __future__ import annotations

import calendar
import html
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

    parsed = feedparser.parse(raw)
    items = []
    for e in parsed.entries:
        t = e.get("published_parsed") or e.get("updated_parsed")
        if not t:
            continue
        pub = datetime.fromtimestamp(calendar.timegm(t), tz=timezone.utc)
        title = _strip_source_suffix(_clean(e.get("title", "")))
        summary = _clean(e.get("summary", ""))
        if summary.startswith(title[:10]) and len(summary) < len(title) + 20:
            summary = ""  # Google 新聞的 summary 只是標題重複
        if title:
            items.append(NewsItem(cfg["source"], cfg["section"], cfg["kind"], title,
                                  summary[:220], e.get("link", ""), pub))
    log.info("%s／%s：%d 則", cfg["source"], cfg["section"], len(items))
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
                if it.kind == "business":
                    st.kind = "business"
                break
        else:
            stories.append(Story(it.title, it.summary, it.kind, it.published, [it]))
            keys.append(k)
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
