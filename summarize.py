"""把新聞清單交給 AI，產生可直接朗讀的播報稿。支援 Gemini（預設）與 Claude。

做法：分成四個段落，每段各自請 AI 從新聞清單挑選並撰寫，輸出 JSON。
程式會實際計算每段則數，不足下限就自動再請 AI 補，確保新聞量與廣度。
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import config
from podcast.fetch import Story

log = logging.getLogger(__name__)
WEEKDAYS = "一二三四五六日"

# ── 四大段落定義 ─────────────────────────────────────────────
SECTIONS = {
    "macro": {
        "name": "總體經濟",
        "intro": "接著是總體經濟。",
        "scope": "各國央行與利率、通膨／就業／GDP／PMI 等經濟數據、美債殖利率、美元指數與新台幣等匯率、"
                 "油價、黃金與原物料、台灣出口／外銷訂單／景氣燈號、政府財經政策。",
        "breadth": "央行利率、經濟數據、匯率、債市、油價、黃金與原物料、台灣總經，每一類清單中有新聞就至少挑一則。"
                   "講數據時說清楚「公布值、預期或前值、代表什麼」（清單有提供才講）。",
    },
    "world": {
        "name": "國際重大新聞",
        "intro": "再來看國際重大新聞。",
        "scope": "地緣政治與戰爭衝突、美國政治與政策、中國與兩岸、日韓與亞太、歐洲、中東、俄烏、"
                 "國際峰會與外交、重大社會事件、天災、公共衛生、交通與資安重大事故等，非純財經的國際大事。",
        "breadth": "以下每一類，清單中有新聞就至少挑一則：美國政治與政策、中國與兩岸、日韓與亞太、歐洲、"
                   "中東、俄烏、國際峰會與外交、重大社會事件／天災／公共衛生／重大事故。"
                   "同一事件只講一則。若事件可能影響市場（能源、供應鏈、匯率、避險情緒），用一句話點出。",
    },
    "global_biz": {
        "name": "國際財經與企業",
        "intro": "接下來是國際財經與企業動態。",
        "scope": "美股與全球股市收盤、國際大型企業（科技、AI、半導體、金融、能源、消費、汽車、航空等）、"
                 "國際投資機構與知名投資人動向、國際併購、財報與產業研究報告。",
        "breadth": "涵蓋不同產業與不同公司；同一家公司最多兩則；美股收盤一則即可。",
    },
    "tw_biz": {
        "name": "台股與產業",
        "intro": "首先是台股與產業。",
        "scope": "台股大盤、法人與資金動向、ETF，以及台灣企業的營收、財報、法說、訂單、評等與產業趨勢。",
        "breadth": "大盤與法人動向一到兩則即可，其餘要涵蓋不同產業：半導體、AI 伺服器、電子零組件、"
                   "記憶體、網通、金融、航運、傳產、鋼鐵塑化、生技、營建、消費、能源等。"
                   "同一家公司最多一則、同一族群最多兩則，不要集中在少數熱門股。",
    },
}
# 呼叫順序（先挑範圍明確的段落，避免被其他段落搶走）
PICK_ORDER = ["macro", "world", "global_biz", "tw_biz"]
# 朗讀順序
READ_ORDER = {"weekday": ["tw_biz", "global_biz", "macro", "world"],
              "monday": ["world", "global_biz", "macro", "tw_biz"]}

WRITING_RULES = """【寫作規則——這是要「唸出來」的稿子】
1. 台灣慣用的繁體中文，口語、精簡，像專業新聞主播。純文字，不要 Markdown、條列符號、表情符號或網址。
2. 提到台股個股寫成「公司名(代號)」，例如「台積電(2330)」。
3. 漲跌用文字講方向，例如「上漲2.5%」，不要寫正負號。
4. 只能使用清單中出現的事實與數字，嚴禁自行補充或推測。不確定就不講。
5. 人事、法律、調查、傳聞類消息，必須照新聞原本的說法（「據報導」「傳出」），不可講得更確定或更嚴重。
6. 不給任何買賣建議。
7. 每則獨立成段：前三則重點各二到三句；其餘各一到兩句（約 40 到 80 字），節奏明快。"""


@dataclass
class Item:
    section: str
    ids: list[int]
    text: str


@dataclass
class Briefing:
    script: str
    items: list[Item] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)


def _candidates(stories: list[Story], now: datetime, exclude: set[int]) -> str:
    tag = {"intl": "國際", "macro": "總經", "business": "商業"}
    lines = []
    for n, s in enumerate(stories, 1):
        if n in exclude:
            continue
        t = s.published.astimezone(now.tzinfo).strftime("%m/%d %H:%M")
        line = f"{n}|{tag.get(s.kind, '商業')}|{s.coverage}家|{'、'.join(s.sources)[:30]}|{t}|{s.title}"
        if s.summary:
            line += f"｜{s.summary[:60]}"
        lines.append(line)
    return "\n".join(lines)


def build_section_prompt(key: str, need: int, stories: list[Story], now: datetime,
                         mode: str, exclude: set[int], chosen: list[str] | None = None) -> str:
    sec = SECTIONS[key]
    window = "上週五早上到現在（週末約三天）" if mode == "monday" else "過去二十四小時"
    others = "、".join(SECTIONS[k]["name"] for k in SECTIONS if k != key)
    already = ""
    if chosen:
        already = "\n【本段已選的新聞（不可重複）】\n" + "\n".join(f"- {c[:40]}" for c in chosen) + "\n"
    return f"""你是專業的台灣新聞主播，正在製作投資人每日語音晨間簡報中的「{sec['name']}」段落。
以下是{window}多家媒體的新聞清單（已去重；格式：編號|標籤|報導家數|來源|時間|標題｜摘要）。

【本段範圍】{sec['scope']}
【廣度要求】{sec['breadth']}
【挑選原則】
- 請挑出「至少 {need} 則」屬於本段範圍的不同新聞，依重要性排列。報導家數多代表較受關注，優先挑選，但也要兼顧廣度。
- 屬於其他段落（{others}）的新聞不要選。標籤只是參考，請依內容判斷。
- 清單中本段範圍的新聞若真的不足 {need} 則，有幾則挑幾則，絕不可編造或重複。
{already}
{WRITING_RULES}

【輸出格式】只輸出 JSON，不要任何其他文字：
{{"items": [{{"ids": [新聞編號，可多個], "text": "這則新聞的播報稿"}}]}}

【新聞清單】
{_candidates(stories, now, exclude)}"""


def _parse_items(raw: str, key: str, valid: int, used: set[int]) -> list[Item]:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < 0:
        raise ValueError(f"AI 回傳不是 JSON：{raw[:200]}")
    data = json.loads(raw[start:end + 1])
    items = []
    for d in data.get("items", []):
        ids = [int(i) for i in d.get("ids", []) if str(i).isdigit() and 1 <= int(i) <= valid]
        text = str(d.get("text", "")).strip()
        new_ids = [i for i in ids if i not in used]
        if not text or not new_ids:
            continue   # 空白、沒有對應新聞編號（可能是編造）或整則重複
        used.update(new_ids)
        items.append(Item(key, new_ids, text))
    return items


# ── AI 呼叫 ─────────────────────────────────────────────
def _gemini(prompt: str) -> str:
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    last = None
    for model in config.GEMINI_MODELS:
        kw = dict(max_output_tokens=16000, response_mime_type="application/json")
        if model.startswith("gemini-2.5"):
            kw["thinking_config"] = types.ThinkingConfig(thinking_budget=0)   # 不需要深度思考，關掉以加速
        for attempt in range(1, 4):
            try:
                t0 = time.time()
                r = client.models.generate_content(model=model, contents=prompt,
                                                   config=types.GenerateContentConfig(**kw))
                if r.text and r.text.strip():
                    log.info("Gemini %s 回應 %.0f 秒", model, time.time() - t0)
                    return r.text.strip()
            except Exception as e:  # noqa: BLE001
                last = e
                msg = str(e)
                if "per day" in msg or "PerDay" in msg:
                    # 每日額度用完：重試也沒用（要等到隔天重置），直接換下一個模型
                    log.error("Gemini %s 今日免費額度已用完，改用下一個模型", model)
                    break
                limited = "429" in msg or "RESOURCE_EXHAUSTED" in msg
                wait = 40 if limited else 8 * attempt   # 每分鐘限速：等過這一分鐘再試
                log.warning("Gemini %s 失敗（第 %d 次，%d 秒後重試）：%s", model, attempt, wait, msg[:200])
                time.sleep(wait)
    raise RuntimeError(f"Gemini 全部失敗：{last}")


def _claude(prompt: str) -> str:
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], max_retries=4)
    r = client.messages.create(model=config.CLAUDE_MODEL, max_tokens=16000,
                               messages=[{"role": "user", "content": prompt}])
    return "".join(b.text for b in r.content if b.type == "text").strip()


def default_call(prompt: str) -> str:
    provider = os.environ.get("LLM_PROVIDER", "gemini").lower()
    order = [_claude, _gemini] if provider == "claude" else [_gemini, _claude]
    keys = {_claude: "ANTHROPIC_API_KEY", _gemini: "GEMINI_API_KEY"}
    err = None
    for fn in order:
        if not os.environ.get(keys[fn]):
            continue
        try:
            return fn(prompt)
        except Exception as e:  # noqa: BLE001  主要供應商失敗就換另一家（若有設定金鑰）
            err = e
            log.error("%s 失敗：%s", fn.__name__, e)
    raise RuntimeError(f"AI 摘要失敗（請確認 API 金鑰）：{err}")


# ── 主流程 ─────────────────────────────────────────────
def _watch_points(items: list[Item], mode: str, call: Callable[[str], str]) -> list[str]:
    what = "本週" if mode == "monday" else "今天"
    prompt = f"""以下是今天晨間簡報已播報的新聞。請根據這些內容，提出一到三個投資人{what}值得留意的觀察重點
（例如將公布的經濟數據、會議、法說、事件後續），每點一句話。只能根據下列內容，不可編造日期或數字。
只輸出 JSON：{{"watch": ["第一點", "第二點"]}}

""" + "\n".join(f"- {i.text}" for i in items)
    try:
        raw = call(prompt)
        raw = raw[raw.find("{"): raw.rfind("}") + 1]
        return [str(w).strip() for w in json.loads(raw).get("watch", []) if str(w).strip()][:3]
    except Exception as e:  # noqa: BLE001  觀察重點失敗不影響整集
        log.warning("今日留意產生失敗：%s", e)
        return []


def summarize(stories: list[Story], now: datetime, mode: str,
              call: Callable[[str], str] = default_call, pause: float = 2.0) -> Briefing:
    stories = stories[: config.MAX_CANDIDATES[mode]]   # 已依報導家數排序，取前 N 則
    deadline = time.time() + config.AI_TIME_BUDGET_MIN * 60
    used: set[int] = set()
    by_sec: dict[str, list[Item]] = {}
    for key in PICK_ORDER:
        need = config.MIN_ITEMS[mode][key]
        got: list[Item] = []
        for round_ in range(3):   # 第一次 + 最多補兩次（付費版沒有每日次數限制）
            missing = need - len(got)
            if missing <= 0 or len(used) >= len(stories):
                break
            if round_ > 0 and time.time() > deadline:
                log.warning("AI 摘要已超過 %d 分鐘，停止追加", config.AI_TIME_BUDGET_MIN)
                break
            ask = need if round_ == 0 else missing
            prompt = build_section_prompt(key, ask, stories, now, mode, used,
                                          [i.text for i in got] if got else None)
            time.sleep(pause)   # 避免短時間大量呼叫觸發 Gemini 免費額度的速率限制
            try:
                new = _parse_items(call(prompt), key, len(stories), used)
            except Exception as e:  # noqa: BLE001
                log.warning("%s 第 %d 次失敗：%s", SECTIONS[key]["name"], round_ + 1, str(e)[:200])
                if "全部失敗" in str(e) or "AI 摘要失敗" in str(e):
                    raise   # 所有 AI 都無法使用，不必再試其他段落
                continue
            got.extend(new)
            log.info("%s：第 %d 次取得 %d 則，累計 %d／%d", SECTIONS[key]["name"],
                     round_ + 1, len(new), len(got), need)
            if not new:
                break   # AI 表示沒有更多符合的新聞
        # 保底：AI 補了還不夠，就用同類新聞的標題補成一句快訊，確保則數
        fill_kind = {"macro": "macro", "world": "intl", "tw_biz": "business"}.get(key)
        if len(got) < need and fill_kind:
            for n, s in enumerate(stories, 1):
                if len(got) >= need:
                    break
                if n not in used and s.kind == fill_kind:
                    used.add(n)
                    got.append(Item(key, [n], f"另外，{s.title}。"))
            log.info("%s：以標題快訊補足至 %d 則", SECTIONS[key]["name"], len(got))
        by_sec[key] = got

    ai_count = sum(1 for v in by_sec.values() for i in v if not i.text.startswith("另外，"))
    if ai_count < 10:
        raise RuntimeError(f"AI 只寫出 {ai_count} 則（可能是額度用完），不發布只有標題的節目")
    counts = {k: len(v) for k, v in by_sec.items()}
    total = sum(counts.values())
    if total < 15:
        raise RuntimeError(f"AI 只產出 {total} 則新聞，可能出錯：{counts}")

    date = f"{now.month}月{now.day}日星期{WEEKDAYS[now.weekday()]}"
    title = config.PODCAST_TITLE + ("週一特別版，帶您回顧週末國際大事" if mode == "monday" else "")
    parts = [f"早安，今天是{date}，這是{title}。今天為您整理 {total} 則重點新聞。"]
    ordered: list[Item] = []
    for key in READ_ORDER[mode]:
        if by_sec.get(key):
            parts.append(SECTIONS[key]["intro"])
            parts.extend(i.text for i in by_sec[key])
            ordered.extend(by_sec[key])
    watch = _watch_points(ordered, mode, call) if time.time() < deadline + 300 else []
    if watch:
        parts.append(("本週觀察重點：" if mode == "monday" else "今日留意：") + "".join(
            f"第{'一二三'[k]}，{w}" for k, w in enumerate(watch)))
    parts.append("以上是今天的晨間簡報，祝您投資順利。" if mode != "monday"
                 else "以上是週一特別版，祝您這週投資順利。")
    log.info("各段則數：%s，共 %d 則", {SECTIONS[k]["name"]: c for k, c in counts.items()}, total)
    return Briefing("\n\n".join(parts), ordered, counts)
