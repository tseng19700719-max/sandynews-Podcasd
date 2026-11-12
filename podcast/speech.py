"""播報稿 → 語音。先把數字、代號轉成正確唸法，再用 edge-tts；失敗改用 gTTS。"""
from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

import config

log = logging.getLogger(__name__)
DIGIT = dict(zip("0123456789", "零一二三四五六七八九"))
QUARTER = {"1": "一", "2": "二", "3": "三", "4": "四"}


def _digits(s: str) -> str:
    return "".join(DIGIT.get(c, c) for c in s)


def normalize(text: str) -> str:
    """修正 TTS 常唸錯的財經寫法。"""
    t = text
    # 清掉 Markdown／條列符號
    t = re.sub(r"[*#`>_]+", "", t)
    t = re.sub(r"^\s*[-•・●▪]\s*", "", t, flags=re.M)
    # 股票代號：台積電(2330)、F-貿聯(3665)、騰輝電子-KY(6672) → 「，代號二三三零，」
    t = re.sub(r"[（(]\s*(\d{4,6})\s*[A-Z]?\s*[)）]", lambda m: f"，代號{_digits(m.group(1))}，", t)
    # 年份：2026年 → 二零二六年
    t = re.sub(r"(?<!\d)((?:19|20)\d{2})(?=年)", lambda m: _digits(m.group(1)), t)
    # 季度：Q3、3Q26、第3季
    t = re.sub(r"(?<![A-Za-z])Q([1-4])(?![0-9])", lambda m: f"第{QUARTER[m.group(1)]}季", t)
    t = re.sub(r"(?<!\d)([1-4])Q(\d{2})(?!\d)", lambda m: f"二零{_digits(m.group(2))}年第{QUARTER[m.group(1)]}季", t)
    t = re.sub(r"第([1-4])季", lambda m: f"第{QUARTER[m.group(1)]}季", t)
    # 日期：11/12 → 11月12日
    t = re.sub(r"(?<![\d/])(1[0-2]|0?[1-9])/([12]\d|3[01]|0?[1-9])(?![\d/])", r"\1月\2日", t)
    # 百分比：+2.5% / 2.5% → 百分之2.5；-2.5% → 負百分之2.5
    t = re.sub(r"\+\s*(\d+(?:\.\d+)?)\s*%", r"百分之\1", t)
    t = re.sub(r"[-−－]\s*(\d+(?:\.\d+)?)\s*%", r"負百分之\1", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*[%％]", r"百分之\1", t)
    # 範圍：13,394~13,684 → 13394到13684
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)
    t = re.sub(r"(\d)\s*[~～]\s*(\d)", r"\1到\2", t)
    # 常見縮寫
    for k, v in {"EPS": "每股盈餘", "YoY": "年增", "MoM": "月增", "QoQ": "季增",
                 "Fed": "聯準會", "FOMC": "聯準會利率會議"}.items():
        t = re.sub(rf"(?<![A-Za-z]){k}(?![A-Za-z])", v, t)
    t = re.sub(r"，\s*，", "，", t)
    t = re.sub(r"，([。、；])", r"\1", t)
    return re.sub(r"[ \t]+", " ", t).strip()


async def _edge(text: str, out: Path) -> None:
    import edge_tts
    await edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE).save(str(out))


def synthesize(script: str, out: Path) -> str:
    """回傳實際使用的語音引擎名稱"""
    text = normalize(script)
    for attempt in range(1, 4):
        try:
            asyncio.run(_edge(text, out))
            if out.exists() and out.stat().st_size > 50_000:
                return "edge-tts"
        except Exception as e:  # noqa: BLE001
            log.warning("edge-tts 失敗（第 %d 次）：%s", attempt, e)
    log.warning("edge-tts 無法使用，改用 gTTS 備援")
    from gtts import gTTS
    gTTS(text, lang="zh-TW").save(str(out))
    return "gTTS"
