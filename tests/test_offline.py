"""離線測試：不連網、不呼叫 AI，驗證抓取解析、去重、數字唸法、訂閱檔。
執行：python -m pytest tests -q
"""
import shutil
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from zoneinfo import ZoneInfo

import config
from podcast import fetch, main, speech, summarize

TW = ZoneInfo("Asia/Taipei")
NOW = datetime(2026, 11, 12, 5, 30, tzinfo=TW)


def rss(items, title="feed"):
    body = "".join(
        f"<item><title><![CDATA[{t}]]></title><link>https://ex.com/{i}</link>"
        f"<description><![CDATA[{d}]]></description><pubDate>{format_datetime(p)}</pubDate></item>"
        for i, (t, d, p) in enumerate(items))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>{title}</title>{body}</channel></rss>'.encode()


def fixtures():
    h = lambda n: NOW - timedelta(hours=n)
    udn = rss([("外資賣超7.66億元連10賣　敲進主動式台股ETF", "外資今日賣超...", h(2)),
               ("台積電10月營收創同期新高　年增逾三成", "台積電(2330)公布10月營收...", h(5)),
               ("三天前的舊聞不該出現", "舊聞", h(30))])
    yahoo = rss([("台積電10月營收創同期新高 年增逾3成", "晶圓代工龍頭台積電公布...", h(4)),
                 ("美股四大指數收紅　費半漲2%", "美股週三...", h(1))])
    ctee = rss([("台積電10月營收創同期新高 年增逾三成 - 工商時報", "台積電10月營收創同期新高 年增逾三成 工商時報", h(3)),
                ("鴻海AI伺服器出貨大增 - 工商時報", "鴻海AI伺服器出貨大增 工商時報", h(6))])
    raw = {}
    for f in config.FEEDS:
        raw[f["url"]] = ctee if f["source"] == "工商時報" else (udn if f["source"] == "經濟日報" else yahoo)
    return raw


def test_collect_and_dedupe():
    raw = fixtures()
    since, days = main.window(NOW, "weekday")
    stories = fetch.collect(config.FEEDS, since, 60, days, raw_map=raw)
    titles = [s.title for s in stories]
    assert not any("舊聞" in t for t in titles), "超過 24 小時的新聞應被排除"
    tsmc = [s for s in stories if "台積電10月營收" in s.title]
    assert len(tsmc) == 1, f"三家同一則應合併：{titles}"
    assert tsmc[0].coverage == 3 and stories[0] is tsmc[0], "報導家數最多的應排第一"
    assert all(" - 工商時報" not in t for t in titles)
    prompt = summarize.build_prompt(stories, NOW, "weekday")
    assert "11月12日星期四" in prompt and "報導家數3" in prompt


def test_monday_window():
    mon = datetime(2026, 11, 16, 5, 30, tzinfo=TW)
    since, days = main.window(mon, "monday")
    assert since == datetime(2026, 11, 13, 5, 0, tzinfo=TW) and days == 3


def test_normalize():
    n = speech.normalize
    assert n("台積電(2330)上漲") == "台積電，代號二三三零，上漲"
    assert n("騰輝電子-KY（6672）") == "騰輝電子-KY，代號六六七二，"
    assert n("2026年Q3 EPS 4.25元") == "二零二六年第三季 每股盈餘 4.25元"
    assert n("漲2.5%，跌-1.2%") == "漲百分之2.5，跌負百分之1.2"
    assert n("11/12盤前") == "11月12日盤前"
    assert n("指數13,394~13,684點") == "指數13394到13684點"
    assert n("**重點** \n- 第一則") == "重點 \n第一則"
    assert n("3Q26營收") == "二零二六年第三季營收"


def test_full_run(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "SITE", tmp_path / "site")
    monkeypatch.setattr(main, "STATE", tmp_path / "episodes.json")
    raw = fixtures()
    since, days = main.window(NOW, "weekday")
    stories = fetch.collect(config.FEEDS, since, 60, days, raw_map=raw) * 4  # 湊滿 10 則

    def fake_synth(script, out):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440:d=5",
                        "-b:a", "48k", str(out), "-y"], check=True)
        return "fake"

    script = "早安，今天是11月12日星期四。台積電(2330)10月營收創同期新高。" * 20
    for day in (NOW - timedelta(days=1), NOW):   # 連跑兩天，確認集數累積
        ep = main.run(day, "weekday", "https://sandy.github.io/news-podcast",
                      stories=stories, script=script, synth=fake_synth,
                      restore=lambda eps, url: eps)
    xml = (tmp_path / "site" / "feed.xml").read_text("utf-8")
    root = ET.fromstring(xml)
    items = root.findall("./channel/item")
    assert len(items) == 2
    enc = items[0].find("enclosure")
    assert enc.get("url") == "https://sandy.github.io/news-podcast/episodes/2026-11-12.mp3"
    assert int(enc.get("length")) > 1000
    assert ep["duration"] > 4
    assert "參考新聞" in items[0].find("description").text
    assert (tmp_path / "site" / "cover.png").exists()
