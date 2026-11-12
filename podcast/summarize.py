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
   每段的則數下限一定要達到；寧可每則講精簡一點，也不要只講少數幾則。
   但若清單中某類新聞真的不足，有幾則講幾則，絕不可編造或重複湊數。
   清單上的「商業股市／總經／國際」標籤僅供參考，請依內容判斷：利率、通膨、經濟數據、匯率、油價等放總經段；
   海外市場、外國企業、各國政經放國際段；台股、台灣產業與企業放台股與商業段。同一事件只能出現在其中一段。
   涉及人事、法律、調查、傳聞的消息，必須照新聞原本的說法（例如「據報導」「傳出」），不可講得比新聞更確定或更嚴重。
8. 不給任何買賣建議。
"""

WEEKDAY_STRUCTURE = """
【節目結構】
開場一句：「早安，今天是{date}，這是{title}。」
一、台股與商業焦點（至少 {biz} 則，依重要性排列）
   先講大盤、資金面、法人動向，再講產業與個股：營收、財報、法說、訂單、評等、產業趨勢。
二、總體經濟（至少 {macro} 則，每天必講）
   各國央行與利率動向、通膨／就業／GDP／PMI 等經濟數據、美債殖利率、美元與新台幣匯率、
   油價與原物料、台灣出口／外銷訂單／景氣燈號。講數據時要說清楚「公布值、預期或前值、代表什麼」（清單有提供才講）。
三、國際動向（至少 {intl} 則，每天必講）
   美股收盤、國際大型企業動態、地緣政治、各國政經大事、國際重大事件。
四、今日留意：一到三個今天值得觀察的重點（含今天將公布的重要經濟數據，清單有提到才講）
結尾一句：「以上是今天的晨間簡報，祝您投資順利。」
每一段：前三到五則重點每則二到三句，其餘每則一到兩句，節奏明快。
"""

MONDAY_STRUCTURE = """
【節目結構——週一特別版：週末國際大事彙整】
開場一句：「早安，今天是{date}，這是{title}週一特別版，帶您回顧週末國際大事。」
一、週末國際動向彙整（至少 {intl} 則，本集重點）
   上週五美股收盤、週末國際政經、地緣政治、國際大型企業動態、國際重大事件。
二、總體經濟（至少 {macro} 則）
   央行與利率、經濟數據、美債殖利率、匯率、油價與原物料、台灣出口與景氣。
三、台股與商業焦點（至少 {biz} 則）：週末發布的台股、產業、個股消息。
四、本週觀察重點：本週重要經濟數據、央行會議、法說會等（二到四個，只講新聞清單中提到的）
結尾一句：「以上是週一特別版，祝您這週投資順利。」
每一段：前三到五則重點每則二到三句，其餘每則一到兩句，節奏明快。
"""


def build_prompt(stories: list[Story], now: datetime, mode: str) -> str:
    date = f"{now.month}月{now.day}日星期{WEEKDAYS[now.weekday()]}"
    structure = (MONDAY_STRUCTURE if mode == "monday" else WEEKDAY_STRUCTURE).format(
        date=date, title=config.PODCAST_TITLE,
        biz=config.MIN_ITEMS[mode]["business"], macro=config.MIN_ITEMS[mode]["macro"],
        intl=config.MIN_ITEMS[mode]["intl"])
    window = "上週五早上到現在（週末共約三天）" if mode == "monday" else "過去二十四小時"
    lines = []
    for n, s in enumerate(stories, 1):
        tag = {"intl": "國際", "macro": "總經"}.get(s.kind, "商業股市")
        t = s.published.astimezone(now.tzinfo).strftime("%m/%d %H:%M")
        line = f"{n}. [{tag}｜報導家數{s.coverage}｜{'、'.join(s.sources)}｜{t}] {s.title}"
        if s.summary:
            line += f"\n   摘要：{s.summary}"
        lines.append(line)
    return f"""你是專業的台灣財經主播，要為投資人製作每日語音晨間簡報。
以下是{window}來自經濟日報、Yahoo股市、工商時報、鉅亨網、自由財經及 Google 新聞商業版各家媒體的新聞清單（已去重）。
台股與商業、總體經濟、國際動向三大面向都要充分涵蓋，請從中挑出最重要的內容，寫成一份播報稿。
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
                r = client.models.generate_content(
                    model=model, contents=prompt,
                    config=genai.types.GenerateContentConfig(max_output_tokens=32000))
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
    r = client.messages.create(model=config.CLAUDE_MODEL, max_tokens=16000,
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
    if len(text) < 1500:
        raise RuntimeError(f"播報稿太短（{len(text)} 字），可能出錯：{text[:200]}")
    return text
