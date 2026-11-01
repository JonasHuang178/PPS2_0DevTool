## 1. 載入器：認得種類

- [x] 1.1 `device/__init__.py` 的 `HOOK_NAMES` 加入 `mr_type`
- [x] 1.2 區分兩類鉤子：不因種類而異（`jira_key`、`mr_type`）與因種類而異
      （`summary`、`merge_to_md`），以常數表示，不要在解析時用字串比對散落各處
- [x] 1.3 種類名稱沿用 device 的 `_NAME_RE`；抽出的字串一律轉小寫後比對
- [x] 1.4 `known_types(device)`：掃該 device 底下的子目錄，跳過底線開頭的
- [x] 1.5 `load_hook(hook, device=None, mr_type=None)` 依三段順序解析因種類而異的鉤子；
      不因種類而異的鉤子忽略 `mr_type`
- [x] 1.6 **確認不會去找 `default/<type>/`** —— 這是決策二，寫一則註解說明為什麼
- [x] 1.7 `strict_type(device)`：讀該 device `__init__.py` 的 `STRICT_TYPE`，未宣告回
      `False`；型別不是 bool 時明確失敗，不要靜默當真值判斷
- [x] 1.8 載入失敗的錯誤訊息要指出是哪一個 device 的**哪一個種類**的哪一個檔

## 2. 步驟 2：抽出種類

- [x] 2.1 `ai_analysis_gitlab_mr_info.py` 載入並執行 `mr_type` 鉤子，
      輸入與 `jira_key` 鉤子相同（`_mr_fields()` 的結果）
- [x] 2.2 鉤子拋出例外時的訊息指名是哪一個 device 的 `mr_type.py`，與 `jira_key` 一致
- [x] 2.3 抽出的字串正規化：去頭尾空白、轉小寫；不合法時視同沒有種類（**不另外報錯**）
- [x] 2.4 嚴格模式的檢查在此進行：解析不出認得的種類時失敗，
      兩種情況（沒宣告 / 認不得）分開寫訊息，後者列出目前認得哪些
- [x] 2.5 `mr_type` 加入 `02_mr_info.json` 的產出
- [x] 2.6 `--dump-config` 的說明更新

## 3. 步驟 3：收下並蓋章

- [x] 3.1 `ai_analysis_gitlab_mr_summary.py` 新增 `mr_type` 參數
- [x] 3.2 以 `mr_type` 解析 `summary` 鉤子
- [x] 3.3 `inputs` 加入 `mr_type`，讓鉤子知道自己是被哪一個種類選中的
- [x] 3.4 入口蓋章 `mr_type` 進分析結構（**鉤子不自己填**，與 `schema_version` 同理）

## 4. 契約層：結構版本與驗證

- [x] 4.1 `ANALYSIS_SCHEMA_VERSION` 3 → 4
- [x] 4.2 `analysis_body()` 接受 `mr_type`
- [x] 4.3 `validate_analysis()` 檢查 `mr_type`：可以是空字串，但型別必須是字串
- [x] 4.4 `render_footer()` 加入種類；沒有種類時**整段不印**，不要印「無」
- [x] 4.5 確認版本 3 的舊產物仍讀得進來（視為沒有種類）

## 5. 步驟 5：自產物讀取種類

- [x] 5.1 `ai_analysis_gitlab_mr_merge_to_md.py` 自分析結構讀 `mr_type`
- [x] 5.2 以該種類解析 `merge_to_md` 鉤子
- [x] 5.3 分析結構沒有 `mr_type` 時走通用版，不失敗
- [x] 5.4 出處那一行的種類同樣自分析結構取得，不另外傳參數

## 6. Qt

- [x] 6.1 `AIAnalysisGitLabMR.cpp` 的 `case 2` 加一行，把步驟 2 的 `mr_type` 轉送給步驟 3
- [x] 6.2 確認編譯通過

## 7. default 與範本

- [x] 7.1 `device/default/mr_type.py`：取標題第二個方括號，抽不到回空字串
- [x] 7.2 `device/_template/mr_type.py`：說明輸入、輸出、映射與大小寫規則
- [x] 7.3 `device/_template/__init__.py`：以註解列出所有可宣告項目與預設值
      （`VERSION` 必填、`STRICT_TYPE` 選填）
- [x] 7.4 `device/_template/_type_template/`：種類目錄的範本，含 `summary.py` 與
      `merge_to_md.py` 的說明，並講明**只有這兩支會因種類而異**
- [x] 7.5 範本中提醒：標題格式與 default 不同的 device，`jira_key.py` 與 `mr_type.py`
      通常要一起寫（見 design 的風險一節）
- [x] 7.6 範本中說明跨 device 共用要明著 import，不會自動回退

## 8. 文件

- [x] 8.1 README 的 device 一節加入種類：目錄長相、三段解析鏈、字彙各自獨立
- [x] 8.2 README 說明 `STRICT_TYPE`：預設、範圍（只管種類本身）、失敗時機（AI 之前）
- [x] 8.3 README 的 `03_summary.json` 一節更新為版本 4，加上 `mr_type`
- [x] 8.4 README 的報告版面一節更新出處那一行的樣子
- [x] 8.5 README 的目錄樹加入種類子目錄
- [x] 8.6 README 明講「未知的 device 報錯、未知的 type 回退」這個相反的設計及其理由

## 9. 驗證

- [x] 9.1 種類有專屬 `summary.py`、沒有 `merge_to_md.py` → 前者用種類的、後者回退
- [x] 9.2 種類目錄兩支都有 → 兩支都用種類的
- [x] 9.3 認不得的種類、未宣告嚴格 → 走通用版，流程成功
- [x] 9.4 標題完全沒有種類 → 走通用版，流程成功
- [x] 9.5 `STRICT_TYPE = True` + 認不得的種類 → **在步驟 2** 失敗，訊息列出認得哪些
- [x] 9.6 `STRICT_TYPE = True` + 完全沒有種類 → 在步驟 2 失敗，訊息不同
- [x] 9.7 `STRICT_TYPE = True` + 種類目錄只有一支鉤子 → 照常回退，流程成功
- [x] 9.8 預設 device 有 `bug/`、目標 device 沒有 → **確認不會跨過去用**
- [x] 9.9 兩個 device 的 `mr_type.py` 抽不同位置的方括號 → 同一份標題得到不同種類
- [x] 9.10 標題含 `../` 或路徑分隔字元 → 視同沒有種類，不載入任何其他位置的東西
- [x] 9.11 舊的版本 3 `03_summary.json` 交給步驟 5 → 走通用版，渲染成功
- [x] 9.12 沒有任何種類目錄的既有 device → 行為與改動前完全相同
- [x] 9.13 步驟 2 單獨以 `--request-stdin` 執行 → 產出含 `mr_type`
- [x] 9.14 報告出處那一行：有種類時印出、沒有時整段不印
- [x] 9.15 一次分析中 GitLab 取得 MR 的次數沒有增加
- [x] 9.16 ~~**需 Windows 實機**：Qt 轉送 `mr_type` 有到步驟 3~~
      **未驗證，依使用者決定先行歸檔。** 驗法：執行檔旁建 `device/ssd/`
      （`VERSION = "9.9"`）與 `ssd/bug/summary.py`，設定 `PPS_Device = "ssd"`，
      跑一筆標題含 `[XXX-1][Bug]` 的 MR，報告出處應出現 `Type: bug`。
      要用「只有種類版本才會出現的字串」判定，不能看流程成不成功 —— 轉送沒到時
      會靜默走通用版，與正常跑完長得一樣。
- [x] 9.17 `openspec validate --strict` 與 `--specs` 皆通過
