# 台積電 2330 追蹤系統 V2.1
## 架構：MacBook 本機測試 + GitHub Actions 雲端正式執行

### 執行分工
- **MacBook（local）**：開發、資料檢查、指標測試、Excel 預覽。預設不發 LINE / Web Push。
- **GitHub Actions（cloud）**：正式每日排程、更新 GitHub Pages Dashboard、產生 Excel、發送通知。
- **iPhone**：從 GitHub Pages 開啟 Dashboard；可加入主畫面並啟用 Web Push。

MacBook 不必整晚開機。即使 MacBook 關機或睡眠，雲端排程仍可獨立運作。

## 一、MacBook 第一次設定
建議 macOS 使用 Python 3.11 或更新版本，並安裝 Git。

1. 將專案下載或 clone 到 MacBook。
2. 在 Finder 找到 `run_local.command`，雙擊執行。若 macOS 阻擋，於終端機執行：
   ```bash
   chmod +x run_local.command
   ./run_local.command
   ```
3. 腳本會建立 `.venv` 虛擬環境、安裝套件並執行本機測試。
4. 本機結果放在 `local_test/`，不會覆蓋正式網站資料，也不會發通知。

### 手動執行
```bash
source .venv/bin/activate
python update_tsmc_tracker.py --mode local
```

### FinMind Token（可選）
若需要測試營收、財報與法人資料：
```bash
cp .env.example .env
```
編輯 `.env`，填入 `FINMIND_TOKEN=...`，再執行 `run_local.command`。
`.env` 已列入 `.gitignore`，不要把 Token 貼到聊天或 commit。

### 本機測試輸出
- `local_test/docs/latest.json`
- `local_test/output/2330_TSMC_Tracker.xlsx`
- `local_test/data/` 下的歷史資料與狀態檔

> 本機模式預設不推播。只有明確執行 `python update_tsmc_tracker.py --mode local --send-notifications` 才會嘗試推播；一般測試不要加此參數。

## 二、GitHub 雲端正式部署
1. 建立 GitHub repository，建議 `tsmc-stock-monitor`。
2. 將專案根目錄所有檔案推送至 `main` 分支。
3. Settings → Pages → Deploy from a branch → `main` / `/docs`。
4. Settings → Actions → General → Workflow permissions 設為 **Read and write permissions**。
5. Settings → Secrets and variables → Actions，設定所需 Secrets（見下方）。

### GitHub Secrets
| Secret | 用途 |
|---|---|
| `FINMIND_TOKEN` | FinMind 基本面/籌碼資料 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE Messaging API |
| `LINE_USER_ID` | 收件者 User ID |
| `VAPID_PUBLIC_KEY` | iPhone Web Push 公鑰 |
| `VAPID_PRIVATE_KEY` | Web Push 私鑰 |
| `VAPID_CLAIMS_SUB` | `mailto:你的電子郵件` |
| `WEB_PUSH_SUBSCRIPTIONS` | iPhone 訂閱 JSON |

所有憑證只放在 GitHub Secrets 或本機 `.env`，絕不可放入 Python、HTML、Git 或公開 Repository。

### 雲端排程
Workflow 使用 `15 13 * * 1-5` UTC，即台灣時間週一至週五 21:15。
GitHub 排程可能延遲，且週一至週五不等於台灣交易日；程式會依最新可用行情資料判斷，若資料過舊就停止通知。
可在 Actions → TSMC Daily Monitor → Run workflow 手動執行。

## 三、建議日常工作方式
1. 想修改指標、通知條件：在 MacBook 本機修改。
2. 執行 `./run_local.command`，檢查 `local_test/output/` Excel 與 `local_test/docs/latest.json`。
3. 測試正確後 `git add`、`git commit`、`git push`。
4. GitHub Actions 使用同一份程式碼，在雲端正式執行。
5. 到 Actions 檢查執行結果；iPhone 查看 Pages Dashboard。

### Git 操作
```bash
git status
git add .
git commit -m "Improve TSMC monitor"
git push
```
不要 `git add .` 前忽略 `.env`；雖然已加入 `.gitignore`，仍建議先檢查 `git status`。

## 四、LINE 與 iPhone 推播
LINE 使用 Messaging API（LINE Notify 已於 2025-03-31 停止服務）。需建立 LINE Official Account、Messaging API Channel、取得 Channel access token，並透過 Cloudflare Worker webhook 取得自己的 userId。Worker 設定請依 `cloudflare-line-webhook/` 內檔案與原部署步驟操作。
iPhone Web Push：iOS/iPadOS 16.4+，以 Safari 開啟 HTTPS 網站、加入主畫面，從主畫面 App 開啟並按下啟用推播。首次訂閱後，將 subscription JSON 放入 GitHub Secret。

## 五、資料與策略限制
- Yahoo Finance/yfinance 非即時行情，可能延遲或缺漏。
- FinMind 財報工作表目前保留原始欄位，尚未完整映射成統一 EPS、毛利率、營業利益率分析。
- 本版主要提供技術指標狀態變化、每日摘要、營收 YoY 異常提醒；**尚未完成個人持倉停損價設定與完整買進候選評分**，不能把它視為已驗證的買賣策略。
- 第一輪執行建立狀態基準，不回報歷史交叉。
- 系統只提供研究提醒，不會自動下單；收盤後停損訊號不等於盤中即時停損。
- 正式啟用前，請先在本機測試資料，再於 GitHub Actions 手動執行一次，核對 Dashboard、Excel 與通知。

## 六、LINE Worker 部署補充
1. `npm install -g wrangler`，登入 `wrangler login`。
2. 在 `cloudflare-line-webhook` 目錄建立 KV namespace，將回傳 ID 填入 `wrangler.toml`。
3. `wrangler secret put LINE_CHANNEL_SECRET`、`wrangler secret put ADMIN_KEY`。
4. `wrangler deploy`，將 Worker URL 設成 LINE Webhook URL 並 Verify。
5. 加官方帳號好友並傳訊息，使用 Worker 的 `/user-id?key=...` 取得 User ID，存入 GitHub Secret。


## 七、V2.2 多人推播（2～5 人家庭群組）

### 架構
- GitHub Actions：分析 2330，向 Worker 管理 API 取得裝置訂閱，再依各裝置偏好發送 Web Push。
- Cloudflare Worker：公開註冊／偏好／取消 API；管理端點需 `PUSH_ADMIN_TOKEN`。
- Cloudflare D1：保存暱稱、裝置訂閱、通知偏好。
- 家庭邀請碼：限制熟人註冊，適合 2～5 人。

### Cloudflare 部署
1. 建立 D1 database，名稱 `tsmc-push-users`。
2. 將 database ID 填入 `cloudflare-multiuser/wrangler.toml`。
3. 在 `cloudflare-multiuser/` 執行 `npx wrangler d1 migrations apply tsmc-push-users --remote`。
4. 設定 Worker secrets：`INVITE_CODE`（家庭邀請碼）、`ADMIN_TOKEN`（獨立管理 token）、`ALLOWED_ORIGIN`（GitHub Pages 網站 origin）。
5. `npx wrangler deploy`，取得 Worker URL。
6. 將 `docs/config.js.example` 複製為 `docs/config.js`，填入 VAPID 公鑰及 Worker URL。

### GitHub Actions Secrets
新增 `PUSH_API_BASE`、`PUSH_ADMIN_TOKEN`；保留 `VAPID_PRIVATE_KEY`、`VAPID_CLAIMS_SUB`、`FINMIND_TOKEN` 和 LINE 相關 secrets。`WEB_PUSH_SUBSCRIPTIONS` 不再需要。VAPID 私鑰只放 GitHub Secrets。

### 使用方式
1. 每位使用者以 iOS 16.4+ Safari 開啟 HTTPS Dashboard，加入主畫面並從主畫面開啟。
2. 允許通知，填寫裝置暱稱與家庭邀請碼。
3. 各自選擇每日摘要、技術變化、營收異常、風險提醒偏好，按註冊。
4. 修改偏好按「儲存通知偏好」；取消按「取消這支手機的推播」。

### 限制與安全
- 目前採共享邀請碼，適合 2～5 人；公開服務需改為個別帳號／一次性邀請碼。
- `ADMIN_TOKEN` 僅存 Cloudflare Worker secret 與 GitHub Actions secret，不可放前端。
- `ALLOWED_ORIGIN` 限制網站來源；D1 不公開查詢。
- LINE 仍是 V2.1 單一 LINE_USER_ID，尚未做多人 LINE 個人偏好管理。
- `risk` 通知選項已預留，但個人持倉停損與買進候選策略尚未實作。
- 目前尚未做真實環境端到端測試；正式啟用前先用兩支手機測註冊、偏好、推播、取消與失效訂閱。


## Stock Monitor V3.0｜台股＋美股、多使用者自選股與持股損益

### V3.0 新增內容
- 台股與美股自選股；每個瀏覽器/裝置設定檔有獨立清單，每份清單最多 30 檔。
- 新增、移除自選股；總覽表可切換個股 K 線、成交量與 MA5/20/60/120。
- 持股登記：股數、平均成本；依最新發布行情估算未實現損益與報酬率。
- 每日 GitHub Actions 從 Cloudflare Worker 讀取所有設定檔的自選股，產生 `docs/stocks.json`。
- 原有 `update_tsmc_tracker.py`、2330 的 FinMind 基本面/法人資料、指標與通知仍保留；新多股行情由 `update_multi_stock.py` 擴充。

### Cloudflare D1 升級
在 Cloudflare D1 Console 選取原本的資料庫，依序執行 `cloudflare-multiuser/migrations/0002_watchlists_holdings.sql` 和 `cloudflare-multiuser/migrations/0003_profiles.sql`。不要刪除原本 `devices` 資料表。
Worker 需要沿用既有 bindings/secrets：
- D1 binding：`DB`
- Variables/secrets：`ALLOWED_ORIGIN`、`INVITE_CODE`、`ADMIN_TOKEN`
- `ALLOWED_ORIGIN` 必須是 GitHub Pages 網址（含 https，無結尾斜線）
- GitHub Secrets 沿用 `PUSH_API_BASE`、`PUSH_ADMIN_TOKEN` 及原本通知/VAPID secrets。

將新版 `cloudflare-multiuser/worker.js` 部署到原 Worker。`wrangler.toml` 中的 D1 database_id 請保留你原本已建立的值，不要使用範例 placeholder。

### 管理 profile 與公用電腦清理
每個瀏覽器暱稱對應一個本機 `owner_id`；D1 會保存暱稱、自選股與持倉。管理者可在可信任的命令列使用管理工具，管理憑證不會放進公開網頁：

```bash
export PUSH_API_BASE="https://你的-worker.workers.dev"
python3 scripts/manage_profiles.py list
python3 scripts/manage_profiles.py delete 完整的_owner_id
```

工具會提示輸入 Worker 的 `ADMIN_TOKEN`（輸入時不會顯示）。刪除前必須再次輸入完整 `owner_id`；刪除會移除該 profile 的暱稱、自選股和持倉，不會移除推播裝置。舊 profile 尚未同步暱稱時，清單會以自選股／持倉摘要協助辨認。

公用電腦使用完畢時，先用管理工具刪除該 profile，再在瀏覽器設定中清除此網站的 Cookie 與網站資料。清除本機資料會移除暱稱、profile ID 和保存的邀請碼；如果只刪雲端資料而未清除本機資料，該瀏覽器再次連線時可能重新建立 profile。推播裝置需在網站的推播設定中另外取消；若邀請碼已被他人取得，請在 Cloudflare Worker 輪替 `INVITE_CODE`。

### 使用方式
1. 部署新版 Worker，並先執行 D1 migration。
2. 將新版專案更新到 GitHub Repository，保留 GitHub Secrets。
3. 手動執行 GitHub Actions `TSMC Daily Monitor` 一次；確認 `docs/stocks.json` 成功產生。
4. 開啟 GitHub Pages，在「我的自選股」輸入市場、股票代號與顯示名稱，並輸入原本家庭邀請碼。
5. 每新增/移除股票後，可手動執行一次 workflow；否則會等下一個排程更新行情。
6. 在持股區輸入市場、代號、股數及平均成本。台股請輸入實際股數（1 張 = 1,000 股）。

### 市場代號
- 台股上市：輸入 `2330`，程式會查詢 `2330.TW`。
- 台股上櫃：目前需在代號欄輸入 `XXXX.TWO` 才能指定 Yahoo Finance 上櫃代碼；若輸入純數字，預設視為上市 `.TW`。
- 美股：輸入 Yahoo Finance ticker，例如 `AAPL`、`NVDA`、`MSFT`。
- 多股票資料來源使用 Yahoo Finance/yfinance，可能延遲、缺漏或受交易日/時區影響。台積電的 FinMind 財務與法人資料仍只由原本 2330 流程更新，不會自動套用到其他股票。

### 重要限制與安全提醒
- 每位使用者的 profile ID 依照「使用者暱稱」儲存在該瀏覽器的 localStorage；同一瀏覽器可用不同暱稱切換清單，不同裝置/瀏覽器也會有獨立清單。暱稱同步到 D1 以便管理，但這仍不是具備帳密／忘記密碼功能的正式帳號系統。清除網站資料或更換瀏覽器會失去該 profile ID。
- 家庭邀請碼是共用存取憑證；持股與自選股 API 目前以邀請碼加 profile ID 區分，不應將 Worker 公開給不受信任對象。正式多人使用前建議升級為 Cloudflare Access / OAuth 或其他個別身份驗證。
- 持股損益目前只計算 `(最新價 - 平均成本) × 股數`，不包含手續費、交易稅、股利、匯率換算、複委託費用、分批交易與已實現損益。美股 USD 與台股 TWD 分開顯示，不直接合併成單一總資產。
- V3.0 是多股追蹤的初版，部署前須先執行 D1 migration；尚未進行實際 Cloudflare、Yahoo Finance、GitHub Actions、推播與多裝置端到端驗證。


### 台股與美股更新時間
- `daily_update.yml`：台灣時間 21:15，原本台積電流程完成後更新多股票快照；適合台股收盤後資料。
- `us_market_update.yml`：UTC 22:15（台灣時間約隔日 06:15），美股正常交易時段結束後再次更新多股票快照；此時間在美國夏令/冬令時間均晚於正常收盤。
- 美股休市日不會產生新交易日資料，儀表板會保留最近一個有效交易日。GitHub Actions 排程可能延遲，亦可手動執行 workflow。
