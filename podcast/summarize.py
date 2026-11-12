"""把新聞清單交給 AI，產生可直接朗讀的播報稿。支援 Gemini（預設）與 Claude。"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime

import config
from podcast.fetch import Story

log = logging.getLogger(__name__)
WEEKDAYS = "一二三四五六日"

RULES = """
【寫作規則——這是要「唸出來」的稿子】
1. 使用台灣慣用的繁體中文與財經用語，口語、精簡、像專業財經主播。
2. 純文字。不要使用任何 Markdown、星號、井字號、條列符號、表情符號或網址。
3. 提到個股時寫成「公司名(代號)」，例如「台積電(2330)」；只有第一次提到時加代號。
4. 漲跌直接用文字講方向，例如「上漲百分之二點五」或「上漲2.5%」，不要寫正負號。
5. 只能使用下方新聞清單中出現的事實與數字，嚴禁自行補充、推測或引用清單以外的數字。
   不確定的就不要講。標題與摘要不一致時，以保守說法處理。
6. 每則重點講清楚三件事：發生什麼事、影響哪些產業或個股、偏利多／利空／中性。
7. 「報導家數」越多代表越受市場關注，優先挑選；同一事件只講一次。
8. 不給任何買賣建議。
"""

WEEKDAY_STRUCTURE = """
【節目結構】
開場一句：「早安，今天是{date}，這是{title}。」
一、台股與市場焦點：大盤、資金面、匯率、法人動向（約四到六則）
二、產業與個股重點：營收、財報、法說、訂單、產業趨勢（約五到八則）
三、國際重大事件：美股收盤、美國經濟數據、央行、地緣政治、大宗商品（約三到五則）
四、今日留意：一到三個今天值得觀察的重點
結尾一句：「以上是今天的晨間簡報，祝您投資順利。」
"""

MONDAY_STRUCTURE = """
【節目結構——週一特別版：週末國際大事彙整】
開場一句：「早安，今天是{date}，這是{title}週一特別版，帶您回顧週末國際大事。」
一、週末國際大事彙整：上週五美股收盤、週末國際政經、地緣政治、央行與重要數據（約六到八則，這是本集重點）
二、台股與產業重點：週末發布的台股、產業、個股消息（約五到七則）
三、本週觀察重點：本週可能影響台股的事件或數據（二到四個，只講新聞清單中提到的）
結尾一句：「以上是週一特別版，祝您這週投資順利。」
"""


def build_prompt(stories: list[Story], now: datetime, mode: str) -> str:
    date = f"{now.month}月{now.day}日星期{WEEKDAYS[now.weekday()]}"
    structure = (MONDAY_STRUCTURE if mode == "monday" else WEEKDAY_STRUCTURE).format(
        date=date, title=config.PODCAST_TITLE)
    window = "上週五早上到現在（週末共約三天）" if mode == "monday" else "過去二十四小時"
    lines = []
    for n, s in enumerate(stories, 1):
        tag = "國際" if s.kind == "intl" else "商業股市"
        t = s.published.astimezone(now.tzinfo).strftime("%m/%d %H:%M")
        line = f"{n}. [{tag}｜報導家數{s.coverage}｜{'、'.join(s.sources)}｜{t}] {s.title}"
        if s.summary:
            line += f"\n   摘要：{s.summary}"
        lines.append(line)
    return f"""你是專業的台灣財經主播，要為投資人製作每日語音晨間簡報。
以下是{window}來自經濟日報、Yahoo股市、工商時報的新聞清單（已去重）。
商業股市新聞為主，國際重大事件為次。請從中挑出最重要的內容，寫成一份播報稿。
播報稿長度約 {config.TARGET_CHARS[mode]} 個中文字。
{RULES}
{structure}
【新聞清單】
{chr(10).join(lines)}

請直接輸出播報稿全文，不要任何前言或說明。"""


def _gemini(prompt: str) -> str:
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    last = None
    for model in config.GEMINI_MODELS:
        for attempt in range(1, 4):
            try:
                r = client.models.generate_content(model=model, contents=prompt)
                if r.text and r.text.strip():
                    log.info("摘要完成：%s", model)
                    return r.text.strip()
            except Exception as e:  # noqa: BLE001
                last = e
                log.warning("Gemini %s 失敗（第 %d 次）：%s", model, attempt, e)
                time.sleep(10 * attempt)
    raise RuntimeError(f"Gemini 全部失敗：{last}")


def _claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=4)
    r = client.messages.create(model=config.CLAUDE_MODEL, max_tokens=6000,
                               messages=[{"role": "user", "content": prompt}])
    log.info("摘要完成：%s（輸入 %s／輸出 %s tokens）", config.CLAUDE_MODEL,
             r.usage.input_tokens, r.usage.output_tokens)
    return "".join(b.text for b in r.content if b.type == "text").strip()


def summarize(stories: list[Story], now: datetime, mode: str) -> str:
    prompt = build_prompt(stories, now, mode)
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    log.info("AI 摘要：%s，輸入約 %d 字", provider, len(prompt))
    order = [_claude, _gemini] if provider == "claude" else [_gemini, _claude]
    keys = {_claude: "ANTHROPIC_API_KEY", _gemini: "GEMINI_API_KEY"}
    text, err = "", None
    for fn in order:
        if not os.environ.get(keys[fn]):
            continue
        try:
            text = fn(prompt)
            break
        except Exception as e:  # noqa: BLE001  主要供應商失敗就換另一家（若有設定金鑰）
            err = e
            log.error("%s 失敗：%s", fn.__name__, e)
    if not text:
        raise RuntimeError(f"AI 摘要失敗（請確認 API 金鑰）：{err}")
    if len(text) < 300:
        raise RuntimeError(f"播報稿太短（{len(text)} 字），可能出錯：{text[:200]}")
    return text
