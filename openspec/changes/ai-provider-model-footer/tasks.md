## 1. 共用 AI 模組（ai_utils）

- [ ] 1.1 以 `split_connection()` 取代 `split_share_code()`，回傳 `(provider, url, share_code)`，
  依 design D1 認定 provider。驗證：以 python 直接呼叫，下列五種輸入的結果都符合規格情境：
  - `openai:https://h:8443/p:X`
  - `https://h:8443/p:X`
  - `https://h:8443/p:A/B`
  - `open ai:https://h/p:X`
  - 空字串
- [ ] 1.2 `ask()`／`ask_json()` 改收 `url` 與 `share_code`，不再自行拆解；缺識別碼仍立即失敗。
  驗證：`grep split_` 確認 `ask` 內已無拆解；以空 `share_code` 呼叫時拋出原本的錯誤、未送出請求。
- [ ] 1.3 新增 `API_ROOT`、`MODEL_LIST_PATH`（佔位）、`MODEL_LOOKUP_TIMEOUT` 與四支函式：
  `model_list_url`、`fetch_model_list`、`find_model`、`lookup_model`。所有失敗都回 `""` 並記
  診斷。驗證：以本機 `http.server` 模擬服務，涵蓋下列情況：
  - 查得
  - 無相符
  - 非陣列
  - 404
  - 無 `API_ROOT`
  - 佔位未填
  
  六種情況的回傳與診斷都符合規格；佔位未填時不發請求。
- [ ] 1.4 更新 `ai_utils.py` 的模組說明與 `scripts/AUTHORING.md` 中 `ask`／`split_share_code`
  的用法。驗證：`grep -rn split_share_code scripts docs` 無結果。

## 2. 分析結構、契約與出處（ai_analysis_gitlab_mr/__init__.py）

- [ ] 2.1 `analysis_body()` 加 `provider`；`ANALYSIS_SCHEMA_VERSION` 升為 8；
  `ACCEPTED_SCHEMA_VERSIONS` 加 8；`validate_analysis` 接受選填的 provider；更新版本註解。
  驗證：v7 與 v8 的樣本都通過 `validate_analysis`。
- [ ] 2.2 `ai_credentials(inputs)` 改讀 `ai_connection`、回傳 `(connection, api_key)`，錯誤訊息
  改指 `Provider`／`Api_URL`。驗證：空連線字串時拋 `CredentialError`，代碼不變。
- [ ] 2.3 `render_footer()` 移除 `ai_mode`，從 `analysis` 讀 provider 與 model，輸出
  `**AI** **Provider** \`p\` | **Model** \`m\``，缺一半省略一半。驗證：四種組合各產出正確的一行：
  - 兩者皆有
  - 只有 provider
  - 只有 model
  - 兩者皆無
- [ ] 2.4 `SCRIPT_VERSION` 升為 `2.12`。驗證：出處的腳本那一行顯示 `2.12`。

## 3. 步驟 3（summary）與 device

- [ ] 3.1 `ai_analysis_gitlab_mr_summary.py`：參數改為 `ai_connection`，`ai_connection` 為空時
  退回讀舊名 `ai_api_url`；不再宣告 `ai_mode_name`、`ai_model`；`inputs` 同步；診斷那一行改記 provider（由 `split_connection` 取得，只用於
  log）。驗證：`--help` 與傾印模板中只有 `ai_connection`。
- [ ] 3.2 `device/default/summary.py`：拆連線字串、查模型、以新簽章呼叫 `ask`，把
  provider／model 寫入 `analysis_body`；替代內容路徑留空兩者。`VERSION` 加一碼。驗證：
  未設定端點時跑完步驟 3，產物為 v8、provider 與 model 為空。
- [ ] 3.3 `device/_template/summary.py` 與 `_type_template/summary.py`：示範同樣的兩個必要
  步驟，並註明「每一個 device 都必須做」；輸入說明移除 `ai_mode_name`、`ai_model`，加入
  `ai_connection`。`_template` 的 `VERSION` 加一碼。驗證：`python -m py_compile` 通過，
  且 `grep ai_mode_name scripts` 無結果。

## 4. 步驟 5（merge_to_md）

- [ ] 4.1 移除 `ai_mode` 參數，`render_footer` 呼叫改為不傳 mode。驗證：
  - 拿一份 v8 的 summary JSON 跑步驟 5，出處的 AI 那一行符合 2.3。
  - 拿一份 v7 的 summary JSON 跑步驟 5，只印 Model。

## 5. 列出模型的腳本

- [ ] 5.1 自 `_function_template.py` 複製出 `ai_analysis_gitlab_mr_list_models.py`，依 design
  D8 實作：參數 `modes: [{connection, api_key}]`，回傳 `modes: [{provider, model}]`，同一個
  `(list_url, api_key)` 只查一次。驗證：
  - 對 1.3 的模擬服務執行說明、傾印模板、檔案投遞、標準輸入投遞，四種操作都成功。
  - 兩個同服務的項目只產生一次請求。

## 6. Qt

- [ ] 6.1 `AIAnalysisGitLabMR`：選單讀 `Provider`；以 `currentIndex()` 取設定項目
  （取代 `selectedAiMode()` 的文字比對）；依索引存模型名稱並更新選項文字而不改變選取。
  驗證：編譯通過；設定兩筆同名 provider 時，選第二筆會送出第二筆的端點（看除錯輸出）。
- [ ] 6.2 分析參數：組 `ai_connection`（`Api_URL` 空則空字串），移除 `ai_mode_name`、
  `ai_model` 與步驟 5 的 `ai_mode`；`AnalysisContext` 的欄位同步。執行前檢查 `Provider`
  字元，不符時顯示訊息且不啟動流程。驗證：`Provider` 填 `open ai` 時跳出訊息、無腳本啟動。
- [ ] 6.3 新增 `enterFunction()`：以旗標保證每次啟動只執行一次列出模型；成功時更新選項，
  失敗或取消時全部標成「無法取得」、不跳錯誤框。外殼的 `notifyFunctionEntered()` 加上
  本功能。驗證：
  - 啟動後第一次切入時出現處理中對話框。
  - 切走再切回時不再出現。
  - 取消後選項顯示「無法取得」。
- [ ] 6.4 `pps2_0devtool.ui`：群組標題改為 `AI Provider`，並依 design D7 的表格改掉
  `.ui`、`pps2_0devtool.cpp`、`AIAnalysisGitLabMR.h/.cpp` 裡的內部名稱。驗證：編譯通過；
  `grep -rn "aiMode\|modeCombo\|selectedAiMode" *.cpp *.h *.ui` 無結果；畫面上的群組標題
  為 `AI Provider`。

## 7. 設定、持續整合與文件

- [ ] 7.1 `PPS2_0DevTool.example.json`：`AI_Mode_List` 改為 `AI_Provider_List`，`Name` 改為
  `Provider`（值 `openai`），移除 `Model`；Python 端錯誤訊息裡的設定鍵名同步改。
  驗證：工具載入範例設定後，選單顯示 `openai`。
- [ ] 7.2 確認 `ci/pps-ai-analysis.gitlab-ci.yml` 未被修改（design D9）。驗證：以該檔的 req3／req5
  形狀（`ai_api_url`、`ai_mode_name`、`ai_model`、`ai_mode`）實際跑步驟 3 與步驟 5，兩步都成功，
  且 `git diff --stat ci/` 為空。
- [ ] 7.3 更新以下文件中的參數表、範例與欄位說明：
  - `docs/user-guide.md`
  - `docs/ai-analysis-gitlab-mr/README.md`
  - `docs/ai-analysis-gitlab-mr/cli.md`
  - `docs/ai-analysis-gitlab-mr/cli.html`
  - `docs/ai-analysis-gitlab-mr/device-authoring.md`

  `device-authoring.md` 須寫明拆解與查模型是必要步驟，`user-guide.md` 須說明
  `MODEL_LIST_PATH` 需由部署者填入。驗證：`grep -rn "ai_mode\|AI_Mode_List\|\"Model\"" docs scripts *.cpp *.json`
  只剩刻意保留的歷史說明。

## 8. 整體驗證

- [ ] 8.1 以命令列依序跑步驟 3 與步驟 5（未設定端點的替代路徑，以及帶 provider 前綴、
  對模擬服務的路徑），確認報告出處符合規格；並執行 `openspec validate
  ai-provider-model-footer --strict`。
