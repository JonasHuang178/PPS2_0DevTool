# 文件 vs 程式碼 一致性檢查

範圍：`openspec/specs/` 五份 live spec（5391 行、135 條需求）、`README.md`（2641 行）、
`scripts/AUTHORING.md`（992 行）、`scripts/ai_analysis_gitlab_mr/device/_template/`
`_type_template/README.md`、各檔 docstring 與註解，對照 9 個 .cpp／10 個 .h／36 個 .py。

（行數是**修完之後**的值 —— 這份報告描述的是修完的狀態，不是修之前。）

`openspec/changes/archive/` 底下的 27 份變更是歷史快照，不列入對照。

**結論：整體一致度很高。** 五份 spec 的絕大多數需求都逐條對得上程式碼，不少「容易漂移」
的地方（憑證注入的鍵名、報告版面、欄寬、重試界線、版號規則、排除機制的五類涵蓋）甚至是
精確吻合。

本輪（HEAD = `5ff2875`）共處理 **13 項**文件落差，另**列出 4 項**需要動程式或動 repo、
刻意不在這一輪處理的。

結構面另外量了兩件事，兩件都已補齊：**五份 spec 的 135 條需求現在全部至少有一個
scenario**（原本有一條沒有，見 N6），**全專案 md 的相對連結全部解析得到**（原本有一條
死的，見 N5）。

> **上一版這份報告寫在 `5423d63`，之後有 12 個 commit。** 它自己因此漂掉了三處：
> F11 已經被修掉（`_entry_block` 整支不存在了），而它引用的版號 `SCRIPT_VERSION 2.2`
> 與 `ANALYSIS_SCHEMA_VERSION=5` 現在是 **2.10** 與 **7**。這一版已重新逐條量過。
> 教訓寫在最後一節。

---

## 一、本輪已修

### 文件與程式行為矛盾

| # | 位置 | 問題 | 怎麼修 |
|---|---|---|---|
| **F8**［高］ | `specs/ai-analysis-gitlab-mr/spec.md` | spec 要求出處帶「涵蓋標示」，`render_footer()` 已刻意移除 | **改 spec**（程式是對的） |

成因可完整追溯：

| 時間 | 變更 | 做了什麼 |
|---|---|---|
| 10-01 | `report-diff-coverage` | 把這條需求寫進 spec |
| 10-02 | `restyle-report-footer` | **刻意移除** JIRA 與涵蓋標示，並在 proposal 寫明代價 |

10-02 那輪的 spec delta 只 `MODIFIED` 了「最終報告的組成」，沒去改「報告中的涵蓋範圍」
裡關於出處的那一段。對照組：JIRA 的移除**有**被反映進 live spec，涵蓋標示沒有。

實測（coverage 餵 21/21，完全沒有缺口）：

```
<sub>**Device** `default` `2.5`<br>**腳本** AI Analysis GitLab MR `2.10`<br>**AI** Open AI | `m`</sub>
```

輸出裡沒有 `Coverage`、沒有「涵蓋」、沒有任何檔案數 —— 程式是刻意的結果。
除了改掉那條需求與三個 scenario，另外**補了一個 scenario** 把「出處不帶涵蓋標示」
正面鎖住，避免下一輪再漂回去。

### 文件互相矛盾或會誤導使用者

| # | 位置 | 問題 |
|---|---|---|
| **F13**［中］ | `README.md` | 教使用者設 `SSL_CERT_FILE`，但 `requests` 只讀 `REQUESTS_CA_BUNDLE`／`CURL_CA_BUNDLE`，照做不會生效。AUTHORING 3.11 與程式的錯誤訊息都是對的，只有 README 錯 —— 已改正並補上「設錯的症狀」 |
| **F12**［中］ | `README.md` 三處 | 仍描述已移除的出處欄位（與 F8 同源）：`Coverage: 3/21 檔案（MR 共 90）`、`JIRA: WIP (invalid)`、`JIRA: Alpha (invalid)`。README 自己在別處已寫「出處曾經印過 JIRA，後來移除了」且「`invalid` 目前完全不可見」—— 同一份文件前後矛盾 |
| **F14**［中］ | 三處共用模組清單 | 538 行的 `ai_utils.py` 從 `script_utils/__init__.py` 的清單、AUTHORING 3.9 的目錄圖、3.11 的 REST 模組、5.1「先看裡面有什麼」全部缺席 —— 而 5.1 的開場正是「這一步最常被跳過，結果是同一個能力被實作第二次」。已四處補上，5.1 連簽章一起列 |
| **N1**［中］ | `README.md` 開頭 | 仍寫「帶有**第一個**功能 tab Single Building」，但專案已有兩個功能且都完成。已改成兩個功能的對照表，並把三則「實機驗收未完成」的告示收在一句話底下 —— 功能完成不等於驗收完成，這個區別值得講明 |
| **N2**［中］ | `README.md` 跨平台 | 寫「路徑一律用 `pathlib`」，但全專案 `os.path.join` **15 處**、`pathlib` **0 處**，而 AUTHORING 3.10 要求的是 `os.path.join()`。README 是錯的那一份，已改正並補上「兩套混用的代價」 |
| **F2**［小］ | `AUTHORING.md` 5.3 | 把 `TEMPLATE_VERSION` 說成「這支腳本依據哪一版範本寫的」。`script-envelope` spec 明訂它是「信封模板的版本，全專案共用一個值」，README 與範本都照 spec 寫 —— AUTHORING 是唯一的例外，已改正 |

### 文件自己對不上程式的現況

| # | 位置 | 問題 |
|---|---|---|
| **N3**［中］ | `README.md` 目錄樹 | `ci/pps-ai-analysis.gitlab-ci.yml`（168 行，上一輪新增）不在樹裡，整份 README 也沒有任何一處提到它 —— 只有一份待辦的 openspec change 引用得到。已加進目錄樹，並新增「在 CI 上跑五步流程」一節（投遞方式對照表、四個要設成 Masked + Protected 的變數、範例刻意處理掉的五個坑），另從「分析流程」那一節指過去 |
| **N4**［中］ | `README.md` 三處版號 | 出處範例寫 `AI Analysis GitLab MR 2.2`（實際 `SCRIPT_VERSION = 2.10`）；`03_summary.json` 的兩處範例寫 `"schema_version": 6`（入口蓋的是 `ANALYSIS_SCHEMA_VERSION = 7`，而 README 自己另一處已正確寫 7）。三處都已對齊程式 |
| **N5**［小］ | `README.md` | 連到 `openspec/changes/add-jira-code-review-report/tasks.md` 的連結是死的 —— 那個 change 已歸檔成 `archive/2026-09-30-add-jira-code-review-report/`。已修正。**全專案 md 連結現已全數解析得到**（C++ lambda 的 `[this](const T &r)` 會被連結檢查誤判，那三筆是假陽性） |
| **F1**［小］ | `_function_template.py` | 把「把版號記進診斷」寫成無條件規則。實際只有 single_building 四支這樣做，ai_analysis 六支改由報告頁尾承載 —— 而 README 與兩份 spec 都正確地**限定**了條件，只有範本的措辭沒限定。已改成「不是無條件的規則」，並說明兩種功能各屬哪一種 |
| **F4**［小］ | `ProcessingDialog.h` | 說「三處刻意的差異」卻列了四項（固定尺寸是後加的）。已改成四處 |
| **F9**［小］ | `device/default/merge_to_md.py` | `render()` 的版面示意圖漏了 `<details>`，也沒反映「同一位置的多筆收成一組、diff 只貼一次」。同檔 `_details()`／`_group_block()` 與實測輸出都有。已補上並指向 `_group_block` |
| **F10**［小］ | `device/__init__.py` | 錯誤訊息示範 `VERSION = "1.0"`，但規則要求第一碼與通用層 `SCRIPT_VERSION`（目前 **2.10**）一致，照抄會不一致。已改成 `"2.0"` 並把第一碼規則寫進訊息 |
| **N6**［中］ | `specs/ai-analysis-gitlab-mr/spec.md` | Requirement「AI 分析的素材備置」有四條 SHALL／MUST NOT 與完整理由，但**一個 scenario 都沒有** —— `openspec validate --strict` 要求每條需求至少一個，所以這份 spec 當時是驗不過的。已依它自己的四條規範條文補上 6 個 scenario（鉤子前取得、取得失敗、收合後重取、重取沒更多內容、重取本身失敗、重取後仍然空），逐條對照 `ai_analysis_gitlab_mr_summary.py` 的 `_require_diff_content()` 與 `gitlab_utils._raw_entries()` 確認過行為 |

> 改 F10 時一度想把 `SCRIPT_VERSION` 插進訊息裡，但 `device/__init__.py` 沒有匯入它
> （而且它是母套件，匯入會有循環風險）—— 那樣會在「device 忘了宣告 VERSION」這條路徑上
> 丟 `NameError`，把一個清楚的錯誤換成一個看不懂的。已改回靜態字串，並實際觸發該路徑確認
> 訊息印得出來。

---

## 二、仍未處理（需要動程式或動 repo，刻意留到獨立一輪）

### F7［中］Single Building 串接多支腳本沒用流程 API，處理中對話框被重建

`script-execution` spec 明訂：

> 對話框 SHALL 由整條流程共用：於流程啟動時建立、於流程結束時銷毀。
> 步驟之間 MUST NOT 關閉、重建或重新顯示對話框 —— 每步重建會造成視窗閃爍與焦點重奪

並為此提供 `runFunctionFlow()`。`AIAnalysisGitLabMR.cpp:1349` 用了它；SingleBuilding
四處全是 `runFunctionScript()`，在 callback 內再呼叫下一支：

```
enterFunction       -> runListSource(true)      -> runListTarget      兩支
onSourcePathChanged -> runRecoverySetting(true) -> runListSource       兩支
```

每支各是一條獨立的單步流程，`finishFlow()` 會先 `closeProcessingDialog()` 才呼叫
callback，下一支再 `new ProcessingDialog` + `show()`。

**精確性說明**：hide 與 show 在同一輪事件迴圈內，所以**不存在使用者真能點到主視窗的空窗**；
實際代價是 spec 點名的「視窗閃爍與焦點重奪」。

兩條路都可以：改走 `runFunctionFlow()`，或在 spec 說明這個功能刻意不走流程 API。
**別留現狀** —— 現狀是 spec 有一條規則、程式有一個例外，而兩邊都沒寫下來。

### F5［中］主視窗有一個永遠不動的 `QProgressBar`，沒有任何文件描述它

- `pps2_0devtool.ui:690` `QProgressBar name="progressBar"`
- `pps2_0devtool.cpp:114-115` 只在 `UI_Init()` 做 `setRange(0,100)` + `setValue(0)`，
  之後全專案再無任何引用
- app-shell spec 的「共用 UI 服務」沒列它，README 也沒提
- spec 明訂進度一律由處理中對話框以跑馬燈呈現、**MUST NOT 顯示百分比**，主視窗卻留著
  一條百分比模式、永遠停在 0 的進度條（bootstrap 時期遺留）

刪掉最省事；要留就得在 app-shell spec 說它為什麼在那裡。

### F6［小］兩個手測殘留檔被 git 追蹤

`03_t.json`、`reqt.json` 在 repo 根目錄，README／openspec／`.pro`／程式碼都沒引用。
`reqt.json` 含 `"ai_api_key": "k"` 這類佔位憑證，正是 AUTHORING 3.5 警告的那種形狀
（即使是假值，那個形狀會被複製）。

> 這一輪拿 `03_t.json` 當 fixture 驗了 F8 與 F9 的實際輸出 —— 它確實有用，但那個用途
> 屬於 `tests/` 或 fixture 目錄，不是 repo 根目錄；而 `reqt.json` 沒有任何用途。

### F3 與其他 dead code［小］

本輪另外做了一次全專案的未使用匯入／參數掃描，7 筆裡 **3 筆是真的**：

| 位置 | 問題 |
|---|---|
| `script_io.py:24` | `import os` 沒用到（只在 docstring 提到 `os.environ`）= 原 F3 |
| `script_utils/gitlab_utils.py:46` | `import time` 沒用到（全檔沒有 `time.`） |
| `ai_analysis_gitlab_mr_code_review.py:215` | `_read_attachment(item, base_url, token, out_path)` 的 `base_url` 完全沒被使用（網址來自 `item["content"]`） |

另 4 筆是刻意的，不必動：`logger.formatTime(datefmt)` 要對齊
`logging.Formatter` 的簽章；`device/_template/` 的 `jira_key.extract(mr)` 是給作者填的
樁，`mr_type.py` 的 `contract` 匯入已標 `# noqa: F401（需要時使用）`。

> 小不一致一筆：`_template/summary.py` 的 `ai_utils` 匯入**沒有**它姐妹檔那個
> `# noqa: F401` 註記，所以 linter 設定一變它就會被當成錯誤。

---

## 三、已逐條確認一致的部分

抽樣相當廣，這些都對得上。

> **這一節的來源要講清楚。** 它大部分承接上一版報告的逐條核對結果；本輪**重新實測**的是
> 所有帶數字的項目（版號、schema 版本與接受範圍、常數、計數、行數）以及與本輪改動相關的
> 部分（出處的實際輸出、`<details>` 的實際渲染、`_schema_version` 的收與擋、md 連結、
> 未使用匯入與參數的全專案掃描）。其餘純行為敘述（例如 Escape 的雙重攔截、3 秒寬限、
> `.pro` 的複製規則）**沿用上一版的結論，本輪未重跑**。
>
> 會這樣切是因為上一版漂掉的三處**全是數字** —— 數字會過期，行為敘述不太會。

**script-envelope** — 信封四欄、加法式協定、必填檢查在業務邏輯之前、`--dump-config`
模板、`_` 開頭鍵被忽略、通道分離、進度 flush、exit code 0/1/2、logger 唯一設定點且
等級名稱固定寬度 10、共用模組四條規則（`print`/`sys.exit`/`basicConfig` 全檔 grep 乾淨）、
`system_utils.get_env_var` 的例外在註解裡與 spec 對齊、入口腳本自備 `sys.path.insert`、
`requirements.txt` 只有 `requests` 且延到呼叫時才報缺套件、`TEMPLATE_VERSION = "2.0.0"`
全專案 11 處宣告、值全部相同。

**script-execution** — `config` 合併（Service 鋪底、功能區塊覆蓋）、五個環境變數注入、
寫完關閉 stdin、只做整段解析不退回掃描、成敗不看 exit code、對話框整條流程共用
（AI Analysis 側）、兩層文字、Escape 在 `event()` 與 `keyPressEvent()` 雙重攔截、
3 秒寬限強制終止、耗時整條流程起算、忙碌警告含功能名與步驟名、不設逾時。

**app-shell** — 只讀四個工具層級欄位、`isFunctionVisible` 讀原始區塊、設定檔缺失中止啟動、
來源路徑各功能私有且還原不觸發變更、ring buffer 300 行、console 關閉先殺子行程、
固定 1280x830、選取樣式含 `:!active`、`01h 23m 45s`、七尺寸圖示內嵌 qrc、`RC_ICONS`、
`.pro` 的設定檔只在不存在時複製而 scripts 無條件覆蓋、`.gitignore` 排除設定檔。

**single-building** — tab 標題與設定鍵同名、`ExtendedSelection`、只顯示檔名但保存絕對路徑、
自然排序自寫 `lessThan`（不靠 `QCollator` numericMode）、過濾 `setFilterFixedString`
且 CaseSensitive、清除鈕只清過濾文字、0 個 `.cpp` 視為成功、四個 action 名稱與 C++ 常數一致、
Recovery Setting 先確認、寫入後不重讀、四支腳本都記版號（`SCRIPT_VERSION = 2.0`）。

**ai-analysis-gitlab-mr** — 五步流程與腳本路徑寫死、產物 `01_`..`05_` 兩位數前綴、
`kServiceKey` 七個鍵的全大寫注入（與 AUTHORING 4.2 的表完全對上）、AI 四項走 params
不上命令列、`AI_VERIFY_SSL` 不在 `kServiceKey`、工作目錄先建後跑、失敗即停並指出第幾步、
結果取自 `data` 不開檔、表格五欄順序與欄寬 60/85/伸縮/150/115、天數 1~365 預設 7、
`MERGE_REQUEST_LIMIT=100`、Filter 預設收合且狀態在收合範圍外、過濾統計不在
`filterAcceptsRow` 累加、`AI_HEADING` 單一來源且比對式由常數導出、`split_description`
的圍籬保護、`as_list` 四條斷行規則（只認全形句末標點、收尾符號留前段、有序編號須從 1
連續）、理由與總覽共用 `as_list`、`fence_for` 依內容加長圍籬、
**`ANALYSIS_SCHEMA_VERSION = 7` 且 `ACCEPTED_SCHEMA_VERSIONS = (3,4,5,6,7)`**、
`_schema_version` 實測容許 `7`/`"7"`/`"7.0"` 但擋 `True`／`2.5`／`"2.5"`、
`CODE_REVIEW_SCHEMA_VERSION = 1`、`ai_utils` retryable 由拋出端決定、`Retry-After`
超上限立即失敗、`DEFAULT_TIMEOUT=120`、重試與重問分開且 `0` 合法、等待設定在取 diff
之前驗並記 log、附件前綴比對區分大小寫且限 `.md`、下載前先用 `size` 擋、`utf-8-sig`
嚴格解碼、未設 AI 端點產生替代內容且首行言明未經過 AI、`normalize_type` 不合法視同
沒有種類、底線開頭目錄不算 device/種類、排除三鍵任一命中即排除且排除發生在位元組上限
之前、被排除的檔案收在第五類 `skipped` 且**不**算進 `missing`（否則重查會為刻意排除的
檔案一直重問）、全部被排除時這一步失敗並點名三個環境變數。

**README** — 目錄結構樹（本輪補上 `ci/`）、報告版面範例（含 `<details>`、`## 詳細資料`、
`# 分析涵蓋範圍`、四欄出處）與實測渲染一致、`MAX_COVERAGE_PATHS=50`、
`MAX_PROMPT_DIFF_BYTES=120000`、AI 三個預設 120/3/1、最壞情況公式、`ask()`/`ask_json()`
簽章、`script_io` API 表、設定檔鍵全數有說明。

**device/_type_template/README.md** — 解析鏈三層、不會去找 `default/<type>/`、
只有 `summary` 與 `merge_to_md` 因種類而異、`STRICT_TYPE` 不要求種類目錄放齊鉤子、
名稱規則（小寫英數底線、不以數字開頭、底線開頭不算種類）—— 全部對得上
`device/__init__.py`。

---

## 四、下次怎麼不要再漂

這份報告自己在 12 個 commit 內就漂掉三處，所以：

1. **版號、schema 版本、常數不要抄進敘述。** 要提就連「怎麼量的」一起寫，或指向單一來源。
   本輪所有數字都附了量法。
2. **移除一個欄位時，grep 它的名字，不要只改當輪的 spec delta。** F8／F12 是同一次移除
   漏掉的兩群殘留；`Coverage` 與 `JIRA: ` 各 grep 一次就全找得到。
3. **新增一個目錄或檔案時，README 的目錄樹是它的註冊處。** `ci/` 漏了一輪（N3）。
4. **spec 的 scenario 用來正面鎖住「不做什麼」。** F8 之所以能漂，是因為沒有任何
   scenario 說「出處不帶涵蓋標示」；補上之後下一輪想改回去就會先撞到它。
