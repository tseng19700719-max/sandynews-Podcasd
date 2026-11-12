"""Sandy Podcast — 設定檔（要調整來源、聲音、長度都改這裡）"""

# ── 節目資訊 ─────────────────────────────────────────────
PODCAST_TITLE = "Sandy Podcast"
PODCAST_AUTHOR = "Sandy"
PODCAST_DESCRIPTION = "每個交易日早上自動產生的台股與國際財經重點摘要（私人自用）。"
TIMEZONE = "Asia/Taipei"
KEEP_EPISODES = 30            # 訂閱檔只保留最近幾集（舊的 MP3 會自動刪掉）

# ── 新聞來源 ─────────────────────────────────────────────
# kind: "business" = 商業股市（主）、"intl" = 國際（次）
# 經濟日報、Yahoo股市 有官方 RSS；工商時報沒有公開 RSS，改用 Google 新聞的 site: 搜尋
FEEDS = [
    {"source": "經濟日報", "section": "證券", "kind": "business",
     "url": "https://money.udn.com/rssfeed/news/1001/5590?ch=money"},
    {"source": "經濟日報", "section": "產業", "kind": "business",
     "url": "https://money.udn.com/rssfeed/news/1001/5591?ch=money"},
    {"source": "經濟日報", "section": "要聞", "kind": "business",
     "url": "https://money.udn.com/rssfeed/news/1001/10846?ch=money"},
    {"source": "經濟日報", "section": "國際", "kind": "intl",
     "url": "https://money.udn.com/rssfeed/news/1001/5588?ch=money"},
    {"source": "Yahoo股市", "section": "台股", "kind": "business",
     "url": "https://tw.stock.yahoo.com/rss?category=tw-market"},
    {"source": "Yahoo股市", "section": "國際", "kind": "intl",
     "url": "https://tw.stock.yahoo.com/rss?category=intl-markets"},
    # {days} 會自動換成 1（平日）或 3（週一週末彙整）
    {"source": "工商時報", "section": "全部", "kind": "business",
     "url": "https://news.google.com/rss/search?q=site:ctee.com.tw+when:{days}d&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
]

# 每個來源分類最多取幾則（依時間由新到舊），避免 AI 輸入過長
MAX_PER_FEED = {"weekday": 60, "monday": 120}

# ── AI 摘要 ─────────────────────────────────────────────
# 在 GitHub 的 Variables 設定 LLM_PROVIDER=gemini 或 claude（預設 gemini）
GEMINI_MODELS = ["gemini-3.5-flash", "gemini-2.5-flash"]   # 第一個失敗會自動改用下一個
CLAUDE_MODEL = "claude-sonnet-5-5"

# 播報稿目標長度（中文字數；中文朗讀約每分鐘 280～320 字）
TARGET_CHARS = {"weekday": "1600 到 2000", "monday": "2400 到 3000"}

# ── 語音 ─────────────────────────────────────────────
# 台灣腔可選：zh-TW-HsiaoChenNeural（女）、zh-TW-HsiaoYuNeural（女）、zh-TW-YunJheNeural（男）
TTS_VOICE = "zh-TW-HsiaoChenNeural"
TTS_RATE = "+8%"              # 語速，+10% 會再快一點
