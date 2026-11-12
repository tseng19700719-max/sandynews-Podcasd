"""Sandy Podcast — 設定檔（要調整來源、聲音、長度都改這裡）"""

# ── 節目資訊 ─────────────────────────────────────────────
PODCAST_TITLE = "Sandy Podcast"
PODCAST_AUTHOR = "Sandy"
PODCAST_DESCRIPTION = "每個交易日早上自動產生的台股與國際財經重點摘要（私人自用）。"
TIMEZONE = "Asia/Taipei"
KEEP_EPISODES = 30            # 訂閱檔只保留最近幾集（舊的 MP3 會自動刪掉）

# ── 新聞來源 ─────────────────────────────────────────────
# kind: "business" = 台股與商業、"macro" = 總體經濟、"intl" = 國際動向
# （標題含總經關鍵字的新聞，不論來源都會自動歸到 macro，見 podcast/fetch.py 的 MACRO_KEYWORDS）
# type: "rss"（預設）或 "cnyes"（鉅亨網 JSON）
# source 設為 "Google新聞" 時，會自動改用每則新聞的實際媒體名稱（自由財經、中時、ETtoday…）
from urllib.parse import quote
GN = "hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
MACRO_QUERY = quote("聯準會 OR 降息 OR 升息 OR 通膨 OR CPI OR PCE OR 非農 OR 就業數據 OR GDP OR 央行 "
                    "OR 美債殖利率 OR 美元指數 OR 新台幣 OR 油價 OR 外銷訂單 OR 出口 OR 景氣燈號 OR PMI")
FEEDS = [
    # 經濟日報（官方 RSS）
    {"source": "經濟日報", "section": "證券", "kind": "business",
     "url": "https://money.udn.com/rssfeed/news/1001/5590?ch=money"},
    {"source": "經濟日報", "section": "產業", "kind": "business",
     "url": "https://money.udn.com/rssfeed/news/1001/5591?ch=money"},
    {"source": "經濟日報", "section": "要聞", "kind": "business",
     "url": "https://money.udn.com/rssfeed/news/1001/10846?ch=money"},
    {"source": "經濟日報", "section": "國際", "kind": "intl",
     "url": "https://money.udn.com/rssfeed/news/1001/5588?ch=money"},
    # Yahoo股市（官方 RSS）
    {"source": "Yahoo股市", "section": "台股", "kind": "business",
     "url": "https://tw.stock.yahoo.com/rss?category=tw-market"},
    {"source": "Yahoo股市", "section": "國際", "kind": "intl",
     "url": "https://tw.stock.yahoo.com/rss?category=intl-markets"},
    # 工商時報（無公開 RSS，用 Google 新聞 site: 搜尋；{days} 自動換成 1 或 3）
    {"source": "工商時報", "section": "全部", "kind": "business",
     "url": "https://news.google.com/rss/search?q=site:ctee.com.tw+when:{days}d&" + GN},
    # Google 新聞「商業」版面：涵蓋自由財經、中時、ETtoday、鉅亨、今周刊等各家
    {"source": "Google新聞", "section": "商業", "kind": "business",
     "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?" + GN},
    # 總體經濟：Google 新聞關鍵字搜尋（央行、利率、通膨、就業、GDP、匯率、油價、台灣出口與景氣）
    {"source": "Google新聞", "section": "總經", "kind": "macro",
     "url": "https://news.google.com/rss/search?q=" + MACRO_QUERY + "+when:{days}d&" + GN},
    # Google 新聞「國際」版面：國際重大事件（政經、地緣政治、天災等）
    {"source": "Google新聞", "section": "國際", "kind": "intl",
     "url": "https://news.google.com/rss/headlines/section/topic/WORLD?" + GN},
    # 鉅亨網（頭條 + 台股 + 美股）
    {"source": "鉅亨網", "section": "頭條", "kind": "business", "type": "cnyes",
     "url": "https://api.cnyes.com/media/api/v1/newslist/category/headline?limit=100"},
    {"source": "鉅亨網", "section": "台股", "kind": "business", "type": "cnyes",
     "url": "https://api.cnyes.com/media/api/v1/newslist/category/tw_stock?limit=100"},
    {"source": "鉅亨網", "section": "美股", "kind": "intl", "type": "cnyes",
     "url": "https://api.cnyes.com/media/api/v1/newslist/category/wd_stock?limit=100"},
    # 自由財經（官方 RSS；若被擋會自動略過，Google 新聞商業版仍會帶到）
    {"source": "自由財經", "section": "財經", "kind": "business",
     "url": "https://news.ltn.com.tw/rss/business.xml"},
]

# 每個來源分類最多取幾則（依時間由新到舊），避免 AI 輸入過長
MAX_PER_FEED = {"weekday": 60, "monday": 120}

# ── AI 摘要 ─────────────────────────────────────────────
# 在 GitHub 的 Variables 設定 LLM_PROVIDER=gemini 或 claude（預設 gemini）
GEMINI_MODELS = ["gemini-3.5-flash", "gemini-2.5-flash"]   # 第一個失敗會自動改用下一個
CLAUDE_MODEL = "claude-sonnet-5-5"

# 每集至少要講幾則（商業股市、國際各自計算）
MIN_ITEMS = {"weekday": {"business": 20, "macro": 8, "intl": 20},
             "monday": {"business": 20, "macro": 8, "intl": 25}}
# 播報稿目標長度（中文字數；中文朗讀約每分鐘 280～320 字）
TARGET_CHARS = {"weekday": "5500 到 6500", "monday": "6000 到 7000"}

# ── 語音 ─────────────────────────────────────────────
# 台灣腔可選：zh-TW-HsiaoChenNeural（女）、zh-TW-HsiaoYuNeural（女）、zh-TW-YunJheNeural（男）
TTS_VOICE = "zh-TW-HsiaoChenNeural"
TTS_RATE = "+8%"              # 語速，+10% 會再快一點
