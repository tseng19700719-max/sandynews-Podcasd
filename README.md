# Sandy Podcast（私人晨間財經簡報）

每個交易日（週一到週五）台灣時間大約 05:30，GitHub 會自動：

1. 抓經濟日報、Yahoo股市、工商時報、鉅亨網、自由財經、Google 新聞商業版、國際版與總經關鍵字搜尋過去 24 小時的新聞（週一抓上週五到現在，做成「週末國際大事彙整」）
2. 跨來源去重，同一事件被越多家報導，排序越前面
3. 交給 AI（預設 Google Gemini）寫成約 20 分鐘的播報稿，三大面向每天必講：台股與商業至少 20 則、總體經濟至少 8 則、國際動向至少 20 則（週一國際至少 25 則）
4. 修正數字唸法，例如股票代號 2330 唸成「二三三零」，再用 edge-tts 轉成台灣腔語音；edge-tts 失敗時改用 Google 語音備援
5. 更新 Podcast 訂閱檔，iPhone 的 Podcast App 會自動下載新的一集

**全部免費**：GitHub（公開程式庫）＋ Gemini 免費額度 ＋ edge-tts。

---

## 一次性設定（大約 15 分鐘）

### 步驟 1：申請 Gemini API 金鑰
1. 到 <https://aistudio.google.com/apikey>，用 Google 帳號登入
2. 按「Create API key」，複製那串金鑰（開頭通常是 `AIza`）
3. 不需要綁信用卡就能用免費額度

> ⚠️ 免費額度下，Google 會把送出的內容拿去改善產品。現在送的是公開新聞標題，沒有影響；但日後若要加入「持股清單過濾」，請改用付費額度或 Claude。

### 步驟 2：建立 GitHub 程式庫
1. 到 <https://github.com> 註冊或登入
2. 右上角「＋」→「New repository」
3. Repository name 自訂，例如 `morning-brief`，選 **Public**，按「Create repository」

### 步驟 3：上傳程式
1. 解壓縮 `news-podcast.zip`
2. 在剛建好的程式庫頁面，點「uploading an existing file」
3. 把資料夾裡的**全部內容**拖進去，包括 `.github` 資料夾。
   Mac 的 Finder 預設會隱藏點開頭的資料夾，按 `⌘ + Shift + .` 就會顯示出來
4. 按「Commit changes」
5. 確認程式庫裡有 `.github/workflows/daily.yml` 這個檔案。少了它就不會自動排程

### 步驟 4：開啟 GitHub Pages
程式庫上方「Settings」→ 左側「Pages」→「Build and deployment」的 Source 選 **GitHub Actions**

### 步驟 5：存入 API 金鑰
「Settings」→ 左側「Secrets and variables」→「Actions」→「New repository secret」
- Name：`GEMINI_API_KEY`
- Secret：貼上步驟 1 的金鑰

### 步驟 6：手動跑第一次（測試）
1. 上方「Actions」分頁。如果出現提示，按啟用 workflows
2. 左側點「每日晨間財經 Podcast」→ 右側「Run workflow」→ 綠色「Run workflow」
3. 等 3～5 分鐘，出現綠色勾勾就是成功；紅色叉叉請看下方「疑難排解」
4. 打開 `https://你的帳號.github.io/程式庫名稱/`，網頁上可以直接試聽，也會顯示**訂閱網址**

### 步驟 7：iPhone 訂閱
1. 打開 Apple Podcasts →「資料庫」→ 右上角「⋯」→「以 URL 追蹤節目」
2. 貼上 `https://你的帳號.github.io/程式庫名稱/feed.xml`
3. 進入節目 → 右上角「⋯」→ 設定 → 開啟**自動下載**

之後每天早上新的一集會自動出現。Mac 的 Podcast App 可以在選單「檔案 → 以 URL 追蹤節目」訂閱。

---

## 日常調整（都在 `config.py`）

| 想改什麼 | 改哪個設定 |
|---|---|
| 聲音：男聲／女聲 | `TTS_VOICE`：`zh-TW-YunJheNeural` 是男聲 |
| 語速 | `TTS_RATE`，例如 `+15%` |
| 播報長度、每段至少幾則 | `TARGET_CHARS`、`MIN_ITEMS` |
| 新增或刪除新聞來源 | `FEEDS` |
| 保留幾集 | `KEEP_EPISODES` |

在 GitHub 網頁上點檔案 → 鉛筆圖示，就能直接修改。

### 改用 Claude 寫摘要（選用）
1. 到 Claude Console 申請 API 金鑰，在 Secrets 新增 `ANTHROPIC_API_KEY`
2. 在「Secrets and variables → Actions → Variables」新增 `LLM_PROVIDER` = `claude`

只要兩把金鑰都設定了，主要那家失敗時會**自動改用另一家**。所以只加 Claude 金鑰、不改 `LLM_PROVIDER`，Claude 就會當 Gemini 的備援。

---

## 疑難排解

| 狀況 | 原因與處理 |
|---|---|
| 收到 GitHub 寄來的「Run failed」信 | 到 Actions 點那次執行，看紅色步驟的 log |
| log 顯示「只抓到 N 則新聞」 | 新聞網站擋了 GitHub 機房的 IP，或改版了。把 log 貼給 Claude 修正 |
| log 顯示「Gemini 全部失敗」 | 金鑰錯誤或額度用完。到 AI Studio 檢查 |
| 「存回集數紀錄」那步 push 失敗 | Settings → Actions → General → Workflow permissions 改成「Read and write permissions」 |
| 7:00 還沒看到新的一集 | 先在 Podcast App 節目頁往下拉，重新整理 |
| 某個數字唸錯 | 告訴 Claude 唸錯的寫法，在 `podcast/speech.py` 的 `normalize()` 加一條規則 |

## 注意事項
- **隱私**：程式庫和訂閱網址是公開的，但已設定不被 Apple 目錄和搜尋引擎收錄。內容只有公開新聞的摘要，請勿在這裡放持股資料。
- **版權**：內容是新聞摘要，僅限個人收聽，請勿公開散布。
- **準確度**：AI 只根據新聞標題和摘要撰寫，重要數字請以每集說明裡附的原始新聞連結為準。
- GitHub 會停用公開程式庫中超過 60 天沒有活動的排程。本程式每天會自動存一次紀錄，所以不會被停用。
