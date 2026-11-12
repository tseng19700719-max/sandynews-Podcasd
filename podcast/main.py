"""每日主程式：抓新聞 → AI 摘要 → 轉語音 → 更新 Podcast 訂閱檔。

用法：python -m podcast.main
環境變數：
  GEMINI_API_KEY / ANTHROPIC_API_KEY   至少一個
  LLM_PROVIDER   gemini（預設）或 claude
  SITE_URL       GitHub Pages 網址（由排程自動帶入）
  MODE           auto（預設）、weekday、monday
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from mutagen.mp3 import MP3

import config
from podcast import feed, fetch, speech, summarize

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "episodes.json"
SITE = ROOT / "site"
log = logging.getLogger("podcast")


def window(now: datetime, mode: str) -> tuple[datetime, int]:
    if mode == "monday":   # 上週五 05:00 起
        fri = (now - timedelta(days=(now.weekday() - 4) % 7 or 7)).replace(hour=5, minute=0, second=0, microsecond=0)
        return fri, 3
    return now - timedelta(hours=24), 1


def show_notes(script: str, stories: list[fetch.Story], n: int = 40) -> str:
    refs = "\n".join(f"・{s.title}（{'、'.join(s.sources)}）{s.items[0].link}" for s in stories[:n])
    return f"{script}\n\n——\n參考新聞（依報導家數排序，前 {n} 則）：\n{refs}"


def restore_previous(episodes: list[dict], site_url: str) -> list[dict]:
    """從現有的 GitHub Pages 把舊集數的 MP3 下載回來（Pages 每次部署會整站替換）。"""
    kept = []
    for ep in episodes:
        dst = SITE / "episodes" / ep["file"]
        try:
            r = requests.get(f"{site_url.rstrip('/')}/episodes/{ep['file']}", timeout=60)
            r.raise_for_status()
            dst.write_bytes(r.content)
            kept.append(ep)
        except Exception as e:  # noqa: BLE001
            log.warning("舊集數 %s 無法取回，從訂閱檔移除：%s", ep["file"], e)
    return kept


def run(now: datetime, mode: str, site_url: str, *, stories=None, script=None,
        synth=speech.synthesize, restore=restore_previous) -> dict:
    since, days = window(now, mode)
    if stories is None:
        stories = fetch.collect(config.FEEDS, since, config.MAX_PER_FEED[mode], days)
    if len(stories) < 10:
        raise RuntimeError(f"只抓到 {len(stories)} 則新聞，來源可能被擋或改版，請檢查 log")
    if script is None:
        script = summarize.summarize(stories, now, mode)

    (SITE / "episodes").mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "static" / "cover.png", SITE / "cover.png")
    episodes = json.loads(STATE.read_text("utf-8")) if STATE.exists() else []
    fname = f"{now:%Y-%m-%d}.mp3"
    episodes = [e for e in episodes if e["file"] != fname][: config.KEEP_EPISODES - 1]
    episodes = restore(episodes, site_url)

    out = SITE / "episodes" / fname
    engine = synth(script, out)
    label = "週一特別版：週末國際大事彙整" if mode == "monday" else "晨間簡報"
    ep = {
        "file": fname,
        "title": f"{now.month}/{now.day}（{summarize.WEEKDAYS[now.weekday()]}）{label}",
        "published": now.isoformat(),
        "bytes": out.stat().st_size,
        "duration": MP3(out).info.length,
        "description": show_notes(script, stories),
        "engine": engine,
        "provider": os.environ.get("LLM_PROVIDER", "gemini"),
        "stories": len(stories),
    }
    episodes.insert(0, ep)

    feed_xml = feed.build_feed(episodes, site_url)
    (SITE / "feed.xml").write_text(feed_xml, "utf-8")
    (SITE / "index.html").write_text(feed.build_index(episodes, site_url), "utf-8")
    (SITE / ".nojekyll").write_text("")
    (SITE / "script.txt").write_text(script, "utf-8")
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(episodes, ensure_ascii=False, indent=1), "utf-8")
    log.info("完成：%s，%.1f 分鐘，語音引擎 %s，訂閱檔共 %d 集，feed %d bytes",
             fname, ep["duration"] / 60, engine, len(episodes), len(feed_xml))
    return ep


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    now = datetime.now(ZoneInfo(config.TIMEZONE))
    mode = os.environ.get("MODE", "auto") or "auto"
    if mode == "auto":
        mode = "monday" if now.weekday() == 0 else "weekday"
    site_url = os.environ.get("SITE_URL", "").strip()
    if not site_url:
        sys.exit("缺少 SITE_URL（GitHub Pages 網址）")
    log.info("模式：%s，時間：%s", mode, now.isoformat())
    run(now, mode, site_url)


if __name__ == "__main__":
    main()
