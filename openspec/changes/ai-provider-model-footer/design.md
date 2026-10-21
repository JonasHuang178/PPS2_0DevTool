## Context

動機見 proposal.md。現況與限制：

- `script_utils/ai_utils.py`：
  - `split_share_code(api_url)` 把 `位址:識別碼` 拆成兩段。
  - `ask(api_url, ...)` 在內部呼叫它。
  - 請求裡沒有模型欄位。
- `ai_analysis_gitlab_mr/__init__.py`：
  - `ai_credentials(inputs)` 回傳 `(api_url, api_key, model)`。
  - `analysis_body(..., model=...)` 由鉤子呼叫。
  - `ANALYSIS_SCHEMA_VERSION = 7`，可讀 3–7。
  - `render_footer(ai_mode=..., analysis=...)` 從參數取 mode、從結構取 model。
- 呼叫 `ask()` 的只有 `device/default/summary.py` 與 `device/_template/summary.py`。
- Qt：
  - `selectedAiMode()` 以選單文字比對 `AI_Mode_List[].Name`（改名前的現況）。
  - 外殼的 `notifyFunctionEntered()` 目前只通知 SingleBuilding。
  - 腳本一律以 `runFunctionScript()` 前景執行、顯示互斥的處理中對話框，一次一支
    （`script-execution` 規格）。工具沒有背景執行，所以「第一次進入時查詢」只能以處理中
    對話框呈現。
- 規格「鉤子的輸入與輸出邊界」：需要連線的東西 SHALL 以可呼叫的能力交給鉤子。鉤子已經
  直接呼叫 `ai_utils.ask()`，所以「鉤子呼叫 `ai_utils` 查模型」與既有模式一致。

## Goals / Non-Goals

**Goals:**

- 連線字串的拆解只有一份規則，問 AI、步驟 3 查模型、列出模型三處共用。
- 出處的兩個值只跟著分析結構走。

**Non-Goals:**

- 不相容舊設定檔（`Name`／`Model`）。
- 不新增背景執行能力。
- 不在 `Provider` 與 `Api_URL` 之外為選單另設顯示用的名稱。
- 不快取查到的模型清單；步驟 3 每次分析都重查。

## Decisions

### D1. 連線字串與 `split_connection()`

`ai_utils.split_connection(connection) -> (provider, url, share_code)` 取代
`split_share_code()`，後者移除。

- **provider**：用 `^([A-Za-z0-9._-]+):(?=https?://)` 比對開頭。比對不到時 provider 為空，
  整串交給下一步。
- **位址與識別碼**：沿用現行規則，即路徑中的第一個冒號是分隔符，邏輯原樣搬進來。
- **診斷**：記 provider、端點與識別碼長度，不記識別碼內容。

另一個做法是 provider 獨立成一個參數，不併進字串。不採用的理由：使用者決定以單一字串傳遞，
持續整合的變數名又不能改（`AI_API_URL`）。單一字串讓持續整合只需要改值。

### D2. `ask()` 改收拆好的值

簽章改為 `ask(url, prompt, share_code="", ...)`，`ask_json` 跟著改。

- 「缺少識別碼即失敗」的檢查留在 `ask()`。規格要求不送出沒有識別碼的請求，而那是送請求
  這一端的責任。
- 不保留舊的 `api_url` 形式。兩個呼叫端都在本 repo 內，一次改完。

### D3. 模型查詢

`ai_utils` 新增：

```python
API_ROOT        = "api/external/v1"
MODEL_LIST_PATH = "__FILL_IN_MODEL_LIST_PATH__"   # 部署者填入
MODEL_LOOKUP_TIMEOUT = 10                          # 秒

def model_list_url(url) -> str           # 找不到 API_ROOT 或佔位未填時回 ""
def fetch_model_list(list_url, api_key, timeout, verify_ssl) -> list | None
def find_model(models, share_code) -> str
def lookup_model(url, share_code, api_key, verify_ssl, timeout=MODEL_LOOKUP_TIMEOUT) -> str
```

- `lookup_model` 等於 `model_list_url` → `fetch_model_list` → `find_model`。任何一步取不到
  都回 `""` 並記一筆 `logger.info`。它不拋例外。
- 拆成三支，是因為列出模型的腳本要先依 `(list_url, api_key)` 合併請求，再逐項比對。
- **逾時用獨立的短常數，不用該項目的 `Timeout_Seconds`。**
  - `Timeout_Seconds` 是為「等模型生成一整份分析」調的，常見 120 秒。
  - 列清單是一個輕量的 GET。拿 120 秒去等它，連不上時使用者每次啟動都得被擋兩分鐘。
- **只試一次，不重試**。理由同上：它只是顯示用的值。
- 標頭沿用 `_headers(api_key)`，TLS 驗證沿用同一個環境變數。

### D4. 鉤子與契約

- 步驟 3 的參數：
  - 宣告 `ai_connection`。入口取值時 `ai_connection` 為空就退回讀 `ai_api_url`（v1.0 持續
    整合送的名字），只在入口做這一次，鉤子只看得到 `ai_connection`。
  - 不再宣告 `ai_mode_name`、`ai_model`。信封協定是加法式的，沒宣告的欄位照樣收下而不報錯，
    所以舊設定送來也不會失敗，只是沒有人讀。
  - `inputs` 同步改名與移除。
- `contract.ai_credentials(inputs)` 改為回傳 `(connection, api_key)`。
  - 空字串時照舊拋 `CredentialError`。「未設定 AI 端點」的替代內容路徑不變。
  - 不在這裡拆 provider。使用者要求拆解是鉤子明寫的必要步驟，範本要看得到它。
- `default/summary.py` 與兩份範本的寫法：

  ```python
  connection, key = contract.ai_credentials(inputs)
  provider, url, share_code = ai_utils.split_connection(connection)   # 必要
  model = ai_utils.lookup_model(url, share_code, key, verify_ssl)      # 必要
  ... ai_utils.ask(url, prompt, share_code=share_code, api_key=key, ...)
  return contract.analysis_body(..., provider=provider, model=model)
  ```

- 「未設定 AI 端點」的替代路徑（`default/summary.py:429` 一帶）沒有連線字串，provider 與
  model 都留空。

### D5. 分析結構第 8 版

- `analysis_body()` 新增 `provider` 參數與欄位。
- `ANALYSIS_SCHEMA_VERSION = 8`，`ACCEPTED_SCHEMA_VERSIONS` 加入 8。
- 讀 3–7 的讀法是「沒有 provider」，`.get("provider")` 取不到就是空字串。這是已知的讀法，
  不是猜測，符合該常數上方註解的加版條件。
- `validate_analysis` 視 provider 為選填字串。

### D6. 步驟 5 與出處

- `merge_to_md` 移除 `ai_mode` 參數。
- `render_footer()` 移除 `ai_mode` 參數，改從 `analysis` 讀 `provider` 與 `model`。
- 輸出為 `**AI** **Provider** \`p\` | **Model** \`m\``，缺哪一半就省略哪一半。

### D7. Qt

- **設定**：讀 `Service.AI_Provider_List[].Provider`。選單項目以索引對應清單，用 `currentIndex()` 取代文字
  比對。
- **選單文字**：`m_modelNames` 依索引存三種狀態：
  - 未查：只顯示 provider
  - 查到：`provider / model`
  - 查不到：`provider / 無法取得`
  
  更新文字時不改變 `currentIndex`。
- **分析**：組 `ai_connection`。
  - `Api_URL` 為空時給空字串。
  - 否則為 `Provider + ":" + Api_URL`。
  
  組之前檢查 `Provider` 的字元。不符時用既有的錯誤訊息框，不啟動流程。
- **進入分頁**：
  - 外殼的 `notifyFunctionEntered()` 加上 `m_aiAnalysisGitLabMR->enterFunction()`。
  - 功能內以 `m_modelsQueried` 旗標保證每次啟動只查一次。
  - 呼叫前就設旗標，所以失敗或取消也不重查。
- **列出模型**：
  - 參數：`modes: [{connection, api_key}]`。
  - 回傳：`modes: [{provider, model}]`，順序與輸入相同。
  - 腳本失敗或取消時，每一項標成「無法取得」，**不跳錯誤框**。這是顯示用的資訊，
    不值得打斷使用者，原因留在診斷輸出。
- **介面**：`.ui` 的群組標題改為 `AI Provider`。內部名稱一併改掉，讓程式裡不再有 mode
  這個概念：

  | 現在 | 改成 |
  |---|---|
  | `aiModeGroupBox` | `aiProviderGroupBox` |
  | `aiModeLayout` | `aiProviderLayout` |
  | `aiModeComboBox` | `aiProviderComboBox` |
  | `m_widgets.modeCombo` | `m_widgets.providerCombo` |
  | `selectedAiMode()` | `selectedProviderEntry()`，以索引取 |
  | `AnalysisContext::aiModeName`、`aiModel`、`aiApiUrl` | `aiConnection` |

  設定鍵 `AI_Mode_List` 一併改名為 `AI_Provider_List`。Python 端錯誤訊息中提到的設定鍵也跟著改。

### D8. 列出模型的腳本

新增 `ai_analysis_gitlab_mr_list_models.py`，自功能腳本範本複製。

- 每一項先 `split_connection`，再 `model_list_url`。
- 依 `(list_url, api_key)` 分組，每組 `fetch_model_list` 一次，再各自 `find_model`。
- 整支腳本只在契約錯誤（參數形狀不對）時失敗。個別查不到就是空字串。

### D9. 持續整合

`ci/pps-ai-analysis.gitlab-ci.yml` **不改**。v1.0 已經定案，相容由腳本端負責（見 D4 的
別名與加法式信封）。

- `AI_API_URL` 的值加上 `provider:` 前綴即可在出處看到 provider，這只是值的變更。
- `AI_MODE_NAME`、`AI_MODEL` 與 `ai_mode` 照樣送出，腳本不讀。
- 文件（`cli.md`）說明新的參數名 `ai_connection` 與舊名 `ai_api_url` 的關係。

### D10. 版號

- `SCRIPT_VERSION` 改為 `2.12`。
- `default` device 與範本的 `VERSION` 第二碼加一，因為它們的鉤子寫法變了。

## Risks / Trade-offs

- [`MODEL_LIST_PATH` 未填前，所有報告都沒有模型] → 診斷訊息明說「尚未設定」，報告仍完整；
  部署者填入後即生效。
- [每次啟動第一次進入本功能會被擋一次] → 逾時 10 秒、只試一次、可取消。同一個服務的多個
  項目合併成一次請求。
- [鉤子沒照範本做時，出處少了 provider 或 model，但不會報錯] → 範本與
  `device-authoring.md` 標明它是必要步驟；規格有依範本新增 device 的情境。
- [provider 前綴只認 `http(s)://`] → 若有其他協定的端點會被當成沒有 provider。目前的服務
  都是 HTTP(S)。
- [不相容舊設定] → 工具尚未發布，`PPS2_0DevTool.example.json` 與 `docs/user-guide.md`
  同步更新。

## Migration Plan

1. 部署者把設定檔每一項的 `Name` 改為 `Provider`，刪除 `Model`。
2. 持續整合不必修改。想在出處看到 provider 時，把 `AI_API_URL` 的值加上 `provider:` 前綴。
3. 部署者在 `ai_utils.py` 填入 `MODEL_LIST_PATH`。

回復：還原這個 change 的 commit 即可。新版產生的第 8 版分析結構，舊版程式不認得，要重跑
步驟 3。
