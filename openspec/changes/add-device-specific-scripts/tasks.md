## 1. 契約層：公開 API 與驗證

先做這一組：device 的載入器與三個鉤子都建立在它之上。

- [x] 1.1 `__init__.py` 把 device 作者需要的 helper 升格為公開 API：圍籬長度計算、字串正規化（`None` 收斂成空字串）、單筆 diff 的位元組上限。升格之後簽章不能再隨意改動（design 決策十五）
- [x] 1.2 `AI_HEADING` 對 device 作者是**唯讀**的：範本與文件要寫明它由入口腳本寫出，device 不得自行輸出該行
- [x] 1.3 把 `render_analysis()` 裡的型別檢查抽成獨立的 `validate_analysis()`，讓步驟 3（收到鉤子回傳時）與步驟 5（渲染前）共用同一份規則
- [x] 1.4 `validate_analysis()` 的訊息要能帶上「是哪一個 device」的資訊 —— 步驟 3 呼叫它時會有那個名稱，步驟 5 呼叫時不會
- [x] 1.5 分析結構升到 `schema_version = 3`，新增 `jira_key` / `jira_state` / `jira_url` 三個欄位；`validate_analysis()` 要求它們存在
- [x] 1.6 `jira_state` 只接受 `ok` / `none` / `invalid` 三個值，其餘視為結構錯誤
- [x] 1.7 步驟 5 對更舊的形狀（`{"summary": "一段文字"}`）維持既有的相容處理，不要一起改掉

## 2. device 載入器

- [x] 2.1 建立 `scripts/ai_analysis_gitlab_mr/device/__init__.py`
- [x] 2.2 讀 `PPS_DEVICE`：`.strip()` 後為空即視為未指定 → 用 `default`
- [x] 2.3 名稱小寫化後檢查只含英數與底線；不合格視為錯誤（決策五）
- [x] 2.4 以 `importlib.import_module()` 按名稱載入，**不從名稱組任何檔案路徑**
- [x] 2.5 列出目前認得的 device：掃 `device/` 底下不以 `_` 開頭的目錄，不維護註冊表（決策六）
- [x] 2.6 device 不存在時失敗，訊息列出 2.5 掃到的清單
- [x] 2.7 `device/default/` 不存在時給**另一種**訊息 —— 那是部署壞了，不是使用者打錯字。混用同一句會讓人去翻設定檔
- [x] 2.8 逐鉤子回退：device 存在但缺某個鉤子檔案時，用 `default` 的那一份（決策四）
- [x] 2.9 讀取 device 的 `VERSION`；未宣告時失敗並指出是哪一個 device
- [x] 2.10 攔住 import 與執行期的錯誤，組出帶 device 名與鉤子名的訊息（決策十）—— Qt 的錯誤框只顯示 `message`，`detail` 裡的 traceback 看不到
- [x] 2.11 `PPS_DEVICE=default` 明著指定為合法

## 3. 鉤子範本

- [x] 3.1 建立 `device/_template/`，底線開頭因此不會被 2.5 掃到
- [x] 3.2 三個鉤子各一份範本，寫明**收到什麼參數**與**必須回傳什麼**
- [x] 3.3 範本中列出可用的公開 helper（第 1 組升格的那些），並說明為什麼不該自己重寫 —— 寫死三個反引號的圍籬，遇到內容含反引號的 diff 就會提前關閉程式碼區塊
- [x] 3.4 範本寫明 device 名稱必須是合法的 Python 識別字（`ssd_gen4` 而非 `ssd-gen4`），以及 `AI_HEADING` 不得由 device 輸出
- [x] 3.5 範本含 `VERSION` 常數，並註明「改了產出方式就要往上加」

## 4. `default` device

把現有實作的**政策部分**搬進來，契約部分留在 `__init__.py`。

- [x] 4.1 建立 `device/default/`
- [x] 4.2 `jira_key.py`：從 Merge Request 標題的第一個方括號抽出 key
- [x] 4.3 `summary.py`：目前的 stub 內容搬進來（仍回假資料，真實 AI 呼叫不在本 change）
- [x] 4.4 `summary.py` 判定 JIRA key 的有效性：樣式為大寫專案碼 + 連字號 + 數字，藉此擋掉 `[WIP]`、`[Draft]` 這類常見前綴；無效時記一筆 warning、`jira_state` 設為 `invalid`，並把**原值**保留在 `jira_key`（決策十三）
- [x] 4.5 `merge_to_md.py`：目前 `render_analysis()` 的版面邏輯搬進來
- [x] 4.6 確認搬移後 `__init__.py` 只留契約（建構函式、驗證、圍籬、標題常數、footer），政策都在 `device/default/`
- [x] 4.7 `VERSION` 常數

## 5. 步驟 2：改名並改為連線 GitLab

- [x] 5.1 `ai_analysis_gitlab_mr_script_selector.py` 改名為 `ai_analysis_gitlab_mr_info.py`；action `script_selector` 改為 `mr_info`（檔名不重複前綴已有的 `mr`，action 自己完整 —— 與 `..._description.py` / `mr_description` 同一個慣例）
- [x] 5.2 產物 `02_script_info.json` 改名為 `02_mr_info.json`
- [x] 5.3 以 `gitlab_utils.get_mr_info()` 自行取得 Merge Request（決策十二）
- [x] 5.4 失敗時重用 `describe_gitlab_error()`，讓四種指引與步驟 1 一致，然後結束流程
- [x] 5.5 交給鉤子的是**整理過的欄位**（標題、來源分支、目標分支、描述、repo、編號），不是 GitLab 原樣的物件
- [x] 5.6 三種模式的分派寫在入口：`none` 不呼叫鉤子、`manual` 用使用者輸入的值、`auto` 呼叫鉤子（決策十一）
- [x] 5.7 `jira_mode` 的預設值改為 `auto` —— 現在宣告的 `none` 與 UI 預設（Auto）和 CI 的唯一模式都不一致
- [x] 5.8 回傳攤平：移除 `handler` / `source` / `path` / `status` / `device`，只留 JIRA 相關的值
- [x] 5.9 移除 `device` 參數的宣告 —— device 現在從環境變數來，留著會是第二個來源

## 6. 步驟 3：AI 分析改為呼叫鉤子

- [x] 6.1 載入 device 的 `summary` 鉤子並呼叫
- [x] 6.2 鉤子的輸入包含描述、JIRA key 與狀態、`jira_mode`（唯讀）、AI 的端點／金鑰／模型／模式名、repo、編號、device 名稱
- [x] 6.3 鉤子只回傳分析內容；`schema_version` 由入口腳本蓋章（決策九）
- [x] 6.4 收到回傳後**立刻**呼叫 `validate_analysis()`，失敗訊息指出是哪一個 device、哪一個欄位與讀到的型別
- [x] 6.5 移除讀 `script_info.ai_summary.handler` 的那段 log

## 7. 步驟 5：版面改為呼叫鉤子，並補上程式碼審閱的標題

- [x] 7.1 載入 device 的 `merge_to_md` 鉤子並呼叫
- [x] 7.2 鉤子的輸入包含描述、分析結構、程式碼審閱、repo、編號、device 名稱（輸入給滿，決策八）
- [x] 7.3 鉤子**只回傳 AI 分析標題底下那一段**；`# Original Description`、`# AI 分析結果` 那一行、分隔線與 footer 都由入口腳本寫出
- [x] 7.4 渲染前仍呼叫 `validate_analysis()`
- [x] 7.5 程式碼審閱那一段的標題改由步驟 5 寫出（與 AI 分析那一段同層），步驟 4 只負責內容（決策十七）
- [x] 7.6 步驟 4 的 stub 產出移除自帶的 `##` 標題

## 8. 報告末尾的出處

- [x] 8.1 形狀改為 `Script: v1.0 | Device: ssd v1.2 | AI Mode: Open AI | JIRA: ...`，每個值都有標示（決策十四）
- [x] 8.2 device 名稱與版本由步驟 5 自己讀 `PPS_DEVICE` 與該 device 的 `VERSION` 取得，不必經參數或改 schema
- [x] 8.3 JIRA 依 `jira_state` 呈現：`ok` 印 key（`jira_url` 有值時做成連結）、`none` 印 `NONE`、`invalid` 印**被拒絕的原值**加 `(invalid)`
- [x] 8.4 `jira_state` 由結構帶過來，步驟 5 **不得**重新判定有效性
- [x] 8.5 出處仍不計入「是否有可合併的內容」的判斷

## 9. Qt 與設定

- [x] 9.1 `AIAnalysisGitLabMR.cpp` 的 `kServiceKey[]` 新增一筆 `PPS_Device`，使設定值注入為 `PPS_DEVICE`（機械化全大寫，不維護對照表）
- [x] 9.2 步驟 2 的腳本路徑常數與 action 字串跟著 5.1 改名
- [x] 9.3 `PPS2_0DevTool.example.json` 的 `AI Analysis GitLab MR` 區塊新增 `PPS_Device`，值留空（代表用 default）
- [x] 9.4 確認 Qt 側其餘不變：固定五步、腳本路徑寫死、決策函式、`02_`~`05_` 的產物名對應

## 10. 文件

- [x] 10.1 `README.md` 新增 device 機制一節：名稱來源、空值與未知的差別、兩層 fallback、三個鉤子
- [x] 10.2 `README.md` 新增「如何新增一個 device」：複製範本、命名約束、`VERSION`、哪些 helper 可用
- [x] 10.3 `README.md` 寫明 `device/default/` 每次建置會被覆蓋 —— 要客製就新增自己的目錄，不要改 default
- [x] 10.4 `README.md` 的 `03_summary.json` 格式更新到版本 3，含三個 JIRA 欄位
- [x] 10.5 `README.md` 的報告版面與出處形狀更新
- [x] 10.6 `README.md` 的分析流程表更新步驟 2 的名稱與職責

## 11. 驗收

> 實作環境沒有 qmake / make / g++，第 9 組的 C++ 改動**無法編譯**，一律留給 Windows 端補驗。

- [x] 11.1 `PPS_DEVICE` 未設定、空字串、只有空白 → 三者都用 `default`
- [x] 11.2 `PPS_DEVICE=default` 明著指定 → 與未設定的行為相同
- [x] 11.3 `PPS_DEVICE` 大小寫混用（`SSD` / `ssd` / `sSd`）→ 解析到同一個 device
- [x] 11.4 `PPS_DEVICE` 指向不存在的名稱 → 失敗，訊息列出掃到的清單
- [x] 11.5 `PPS_DEVICE` 含非法字元（`../etc`、`ssd-gen4`）→ 失敗，且**沒有任何檔案路徑被組出來**
- [x] 11.6 臨時建一個只有 `merge_to_md.py` 的 device → 版面用它的、其餘鉤子用 `default` 的（逐鉤子回退）。測完刪掉，不進版控
- [x] 11.7 臨時建一個沒有 `VERSION` 的 device → 失敗並指出是哪一個
- [x] 11.8 臨時建一個有語法錯誤的鉤子 → 訊息指出是哪一個 device 的哪一個鉤子
- [x] 11.9 臨時建一個回傳錯誤結構的 `summary` 鉤子 → **步驟 3** 就失敗（不是步驟 5），訊息點名 device 與欄位
- [x] 11.10 三種 `jira_mode` 各跑一次：`none` 不呼叫鉤子、`manual` 用輸入值、`auto` 呼叫鉤子
- [x] 11.11 標題為 `[WIP] [PPS-1234] ...` → `jira_state=invalid`、`jira_key=WIP`、footer 印 `JIRA: WIP (invalid)`
- [x] 11.12 標題為 `[PPS-1234] ...` → `jira_state=ok`、footer 印 key（有 `JIRA_SERVER_URL` 時為連結）
- [x] 11.13 有效的 key 但 `JIRA_SERVER_URL` 未設定 → 仍為 `ok`，只是不做連結（不可因此判成 invalid）
- [x] 11.14 把報告貼回描述再跑一次：原始描述逐字保留、AI 分析只有一段、footer 不疊 —— 換不同 device 也要成立
- [x] 11.15 開啟 `fetch_code_review` → 程式碼審閱那一段的標題與 AI 分析同層，沒有縮進去
- [x] 11.16 六支腳本的四種投遞操作（`--help` / `--dump-config` / `--request FILE` / `--request-stdin`）全部通過
- [x] 11.17 步驟 2 單獨以 `--request-stdin` 執行可取得 MR 並抽出 key（驗證它不依賴其他步驟）
  - 以只含自己參數的信封單獨執行並成功抽出 key，證明它不依賴任何前一步的產物。GitLab 的呼叫在實作環境是 stub 的 —— 對真實伺服器的那一半與封存 change 的 10.3 同屬一類，等接 CI/CD 時一併驗。
- [ ] 11.18 **需 Windows 實機**：設定檔填入 `PPS_Device` 後，腳本確實收到 `PPS_DEVICE`
- [ ] 11.19 **需 Windows 實機**：乾淨重建後，執行檔旁自行新增的 device 目錄仍然存在（`scripts/` 的複製只覆蓋與新增）
- [x] 11.20 `openspec validate add-device-specific-scripts --strict` 通過
