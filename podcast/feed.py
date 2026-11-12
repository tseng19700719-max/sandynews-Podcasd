"""產生 Podcast 訂閱檔（RSS 2.0 + iTunes 標籤）與簡單的收聽網頁。"""
from __future__ import annotations

import html
from email.utils import format_datetime
from datetime import datetime
from xml.sax.saxutils import escape

import config


def _dur(sec: float) -> str:
    s = int(round(sec))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def build_feed(episodes: list[dict], site_url: str) -> str:
    base = site_url.rstrip("/")
    items = []
    for ep in episodes:
        url = f"{base}/episodes/{ep['file']}"
        items.append(f"""    <item>
      <title>{escape(ep['title'])}</title>
      <description>{escape(ep['description'])}</description>
      <itunes:summary>{escape(ep['description'])}</itunes:summary>
      <enclosure url="{escape(url)}" length="{ep['bytes']}" type="audio/mpeg"/>
      <guid isPermaLink="false">{escape(ep['file'])}</guid>
      <pubDate>{format_datetime(datetime.fromisoformat(ep['published']))}</pubDate>
      <itunes:duration>{_dur(ep['duration'])}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")
    now = format_datetime(datetime.now().astimezone())
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(config.PODCAST_TITLE)}</title>
    <link>{escape(base)}/</link>
    <atom:link href="{escape(base)}/feed.xml" rel="self" type="application/rss+xml"/>
    <description>{escape(config.PODCAST_DESCRIPTION)}</description>
    <language>zh-tw</language>
    <lastBuildDate>{now}</lastBuildDate>
    <itunes:author>{escape(config.PODCAST_AUTHOR)}</itunes:author>
    <itunes:image href="{escape(base)}/cover.png"/>
    <image><url>{escape(base)}/cover.png</url><title>{escape(config.PODCAST_TITLE)}</title><link>{escape(base)}/</link></image>
    <itunes:category text="Business"><itunes:category text="Investing"/></itunes:category>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
    <itunes:block>Yes</itunes:block>
{chr(10).join(items)}
  </channel>
</rss>
"""


def build_index(episodes: list[dict], site_url: str) -> str:
    base = site_url.rstrip("/")
    rows = "\n".join(
        f"<section><h2>{html.escape(ep['title'])}</h2>"
        f"<audio controls preload=\"none\" src=\"episodes/{ep['file']}\"></audio>"
        f"<details><summary>播報稿與參考新聞</summary><pre>{html.escape(ep['description'])}</pre></details></section>"
        for ep in episodes)
    return f"""<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>{html.escape(config.PODCAST_TITLE)}</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;max-width:720px;margin:2rem auto;padding:0 1rem;color:#1d1d1f}}
code{{background:#f2f2f2;padding:.2rem .4rem;border-radius:4px;word-break:break-all}}audio{{width:100%}}
section{{border-top:1px solid #ddd;padding:1rem 0}}pre{{white-space:pre-wrap;font-family:inherit;font-size:.9rem}}</style></head>
<body><h1>{html.escape(config.PODCAST_TITLE)}</h1>
<p>Podcast 訂閱網址：<code>{html.escape(base)}/feed.xml</code></p>
{rows}
</body></html>
"""
