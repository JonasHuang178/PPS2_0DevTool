# 文件 vs 程式碼 一致性檢查

範圍：`openspec/specs/` 五份 live spec（4791 行）、`README.md`（2263 行）、
`scripts/AUTHORING.md`（973 行）、各檔 docstring 與註解，對照
9 個 .cpp／10 個 .h／37 個 .py。

`openspec/changes/archive/` 底下的 28 份變更是歷史快照，不列入對照。

**結論：整體一致度很高。** 五份 spec 的絕大多數需求都逐條對得上程式碼，
不少「容易漂移」的地方（憑證注入的鍵名、報告版面、欄寬、重試界線、版號規則）
甚至是精確吻合。找到 14 處落差，其中 1 高、6 中、7 小。

高與中的那幾項集中在同一個成因：**2026-10-02 那輪「出處改成一行」刻意移除了
JIRA 與涵蓋標示，但只更新了一部分文件。**

---

## 一、必須改的（spec 與程式行為矛盾）

### F8［高］spec 仍要求出處帶「涵蓋標示」，程式已刻意移除

`openspec/specs/ai-analysis-gitlab-mr/spec.md:2982`（Requirement「報告中的涵蓋範圍」）：

> 出處資訊 SHALL 帶上一個簡短的涵蓋標示，說明回報的檔案數與送進分析的檔案數；
> 兩者與該 Merge Request 的檔案總數不一致時，SHALL 一併標出總數。

連帶三個 scenario 也錯：`:3001`（有缺口 → 出處有涵蓋標示）、
`:3007`（沒有缺口 → 出處仍有涵蓋標示）、`:3012`。

實際上 `render_footer()` 只產四行（Device/Type、腳本、AI、產生方式）。實測：

```
<sub>**Device** `default` `2.0` | **Type** `bug`<br>**腳本** AI Analysis GitLab MR `2.2`<br>**AI** Open AI | `gpt-4o`</sub>
```

餵進去的 coverage 是 21/21，輸出裡沒有任何涵蓋資訊。

**成因可完整追溯：**

| 時間 | 變更 | 做了什麼 |
|---|---|---|
| 10-01 | `report-diff-coverage` | 把這條需求寫進 spec（`tasks.md` 3.4） |
| 10-02 | `restyle-report-footer` | **刻意移除** JIRA 與涵蓋標示（`proposal.md:26`、`tasks.md` 2.5，並在 proposal 寫明代價） |

但 10-02 那次的 spec delta 只 `MODIFIED` 了「最終報告的組成」這一條需求，
沒去改「報告中的涵蓋範圍」裡關於出處的那一段。

對照組：JIRA 的移除**有**被反映進 live spec（「出處原本印的 JIRA 欄位已於較早的一輪移除」），
涵蓋標示沒有。

→ 程式是刻意的結果，spec 是漏改的那一份。

---

## 二、文件互相矛盾或會誤導使用者

### F13［中］README 教使用者設 `SSL_CERT_FILE`，但那個變數對本專案無效

`README.md:1535`：「自簽但想驗證的話改設 `SSL_CERT_FILE` 指向公司的 CA 憑證。」

本專案 REST 全走 `requests`，而它只讀 `REQUESTS_CA_BUNDLE` / `CURL_CA_BUNDLE`：

- `scripts/AUTHORING.md:371-374` 明文警告：「CA 憑證的變數是 `REQUESTS_CA_BUNDLE`，
  不是 `SSL_CERT_FILE`…`requests` 不理它。設錯的症狀是『憑證明明指過去了還是驗證失敗』」
- 程式給使用者看的錯誤訊息也這麼說（`ai_analysis_gitlab_mr/__init__.py:993-996`）

README 是整個 repo 唯一叫人設 `SSL_CERT_FILE` 的地方，照做不會生效。

### F12［中］README 三處仍描述已移除的出處欄位（與 F8 同源）

| 行 | 內容 | 問題 |
|---|---|---|
| `871` | 「常駐的訊號在末尾出處那一行的 `Coverage: 3/21 檔案（MR 共 90）`」 | 出處已不印 Coverage |
| `938` | 「出處也不帶 `Coverage`」 | 暗示版本 4/5 時會帶 |
| `926` | 「報告會印成 `JIRA: WIP (invalid)`」 | 出處已不印 JIRA |

README 自己在 `:676` 附近已寫「出處那一段曾經印過 `JIRA: <key>`，後來移除了」
且「`invalid` 在報告上目前完全不可見」—— 同一份文件前後矛盾。

`:655` 的報告版面範例（`<sub>` 那一行）則是**正確的**。

### F14［中］`ai_utils.py` 從三處「共用模組清單」裡缺席

538 行的 AI 服務客戶端，但：

- `scripts/script_utils/__init__.py:6-12` 的模組清單列 7 個，沒有它
- `AUTHORING.md` 3.9 的目錄圖列 7 個，沒有它
- `AUTHORING.md` 5.1「先看 `script_utils/` 裡有什麼」也沒有它 ——
  而那一節開場正是「這一步最常被跳過，結果是同一個能力被實作第二次」
- `AUTHORING.md` 3.11「所有走 REST 的共用模組（`gitlab_utils`、`jira_utils`）」也漏了它

只有 `README.md:189` 的目錄樹列了它。grep 計數：README 6 次、AUTHORING 0 次、`__init__.py` 0 次。

---

## 三、程式沒照 spec 提供的機制走

### F7［中］Single Building 串接多支腳本沒用流程 API，處理中對話框被重建

`script-execution` spec 明訂：

> 對話框 SHALL 由整條流程共用：於流程啟動時建立、於流程結束時銷毀。
> 步驟之間 MUST NOT 關閉、重建或重新顯示對話框 —— 每步重建會造成視窗閃爍與焦點重奪

並為此提供 `runFunctionFlow()`。`AIAnalysisGitLabMR.cpp:1339` 用了它；
SingleBuilding 則在 callback 內再呼叫 `runFunctionScript` 串下一支：

```
enterFunction       -> runListSource(true)      -> runListTarget      兩支
onSourcePathChanged -> runRecoverySetting(true) -> runListSource       兩支
```

每支各是一條獨立的單步流程，`finishFlow()` 會先 `closeProcessingDialog()`
才呼叫 callback，下一支再 `new ProcessingDialog` + `show()`。
切進分頁或變更來源路徑時，對話框會關掉再開一次。

**精確性說明**：hide 與 show 在同一輪事件迴圈內，所以**不存在使用者真能點到主視窗的空窗**；
實際代價是 spec 點名的「視窗閃爍與焦點重奪」。

### F5［中］主視窗有一個永遠不動的 `QProgressBar`，沒有任何文件描述它

- `pps2_0devtool.ui:690` `QProgressBar name="progressBar"`
- `pps2_0devtool.cpp:114-115` 只在 `UI_Init()` 做 `setRange(0,100)` + `setValue(0)`，
  之後全專案再無任何引用
- app-shell spec 的「共用 UI 服務」沒列它，README 也沒提
- spec 明訂進度一律由處理中對話框以跑馬燈呈現、**MUST NOT 顯示百分比**，
  主視窗卻留著一條百分比模式、永遠停在 0 的進度條（bootstrap 時期遺留）

---

## 四、小落差

| # | 位置 | 問題 |
|---|---|---|
| F1 | `_function_template.py:107-109` | 把「記版號進診斷」寫成無條件規則。實際只有 single_building 四支這樣做，ai_analysis 六支改由報告頁尾承載 —— 而 README`:1983` 與兩份 spec 都正確地**限定**了條件（「沒有報告可以承載版號的功能」），只有範本的措辭沒限定 |
| F2 | `AUTHORING.md:504` vs `_function_template.py:75-77` | `TEMPLATE_VERSION` 一處說是「這支腳本依據哪一版範本寫的」，一處說是「信封模板的版本，全專案共用」。spec 兩種說法都有 |
| F3 | `script_io.py:24` | `import os` 沒用到（只在 docstring 提到 `os.environ`） |
| F4 | `ProcessingDialog.h:18` | 說「三處刻意的差異」卻列了四項（固定尺寸是後加的） |
| F6 | repo 根目錄 | `03_t.json`、`reqt.json` 兩個手測殘留檔被 git 追蹤，但 README／openspec／.pro／程式碼都沒引用。後者含 `"ai_api_key": "k"` 這類佔位憑證，正是 AUTHORING 3.5 警告的那種形狀 |
| F9 | `device/default/merge_to_md.py:156-162` | `render()` 的版面示意圖漏了 `<details>`。同檔 `_entry_block()` 的 docstring 與程式都有，實測輸出也有 |
| F10 | `device/__init__.py:405-408` | 錯誤訊息示範 `VERSION = "1.0"`，但規則要求第一碼與通用層 `SCRIPT_VERSION`（目前 2.2）一致，照抄會不一致 |
| F11 | `device/default/merge_to_md.py:24` | `_entry_block(item, path, position)` 的 `path` 與 `position` 完全沒被使用 |

---

## 五、已逐條確認一致的部分

抽樣相當廣，這些都對得上：

**script-envelope** — 信封四欄、加法式協定、必填檢查在業務邏輯之前、`--dump-config`
模板、`_` 開頭鍵被忽略、通道分離、進度 flush、exit code 0/1/2、logger 唯一設定點且
等級名稱固定寬度 10、共用模組四條規則（`print`/`sys.exit`/`basicConfig` 全檔 grep 乾淨）、
`system_utils.get_env_var` 的例外在註解裡與 spec 對齊、入口腳本自備 `sys.path.insert`、
`requirements.txt` 只有 `requests` 且延到呼叫時才報缺套件。

**script-execution** — `config` 合併（`json.cpp:88` Service 鋪底、功能區塊覆蓋）、
五個環境變數注入、寫完關閉 stdin、只做整段解析不退回掃描、成敗不看 exit code、
對話框整條流程共用、兩層文字、Escape 在 `event()` 與 `keyPressEvent()` 雙重攔截、
3 秒寬限強制終止、耗時整條流程起算、忙碌警告含功能名與步驟名、不設逾時。

**app-shell** — 只讀四個工具層級欄位、`isFunctionVisible` 讀原始區塊、設定檔缺失中止啟動、
來源路徑各功能私有且還原不觸發變更、ring buffer 300 行、console 關閉先殺子行程、
固定 1280x830、選取樣式含 `:!active`、`01h 23m 45s`、七尺寸圖示內嵌 qrc、`RC_ICONS`、
`.pro` 的設定檔只在不存在時複製而 scripts 無條件覆蓋、`.gitignore` 排除設定檔。

**single-building** — tab 標題與設定鍵同名、`ExtendedSelection`、只顯示檔名但保存絕對路徑、
自然排序自寫 `lessThan`（不靠 `QCollator` numericMode）、過濾 `setFilterFixedString`
且 CaseSensitive、清除鈕只清過濾文字、0 個 `.cpp` 視為成功、四個 action 名稱與 C++ 常數一致、
Recovery Setting 先確認、寫入後不重讀、四支腳本都記版號。

**ai-analysis-gitlab-mr** — 五步流程與腳本路徑寫死、產物 `01_`..`05_` 兩位數前綴、
`kServiceKey` 七個鍵的全大寫注入（與 AUTHORING 4.2 的表完全對上）、AI 四項走 params
不上命令列、`AI_VERIFY_SSL` 不在 `kServiceKey`、工作目錄先建後跑（勾除錯用時間戳目錄、
沒勾用 `QTemporaryDir` 且 autoRemove）、失敗即停並指出第幾步、結果取自 `data` 不開檔、
表格五欄順序與欄寬 60/85/伸縮/150/115、天數 1~365 預設 7、`MERGE_REQUEST_LIMIT=100`、
Filter 預設收合且狀態在收合範圍外、過濾統計不在 `filterAcceptsRow` 累加、
`AI_HEADING` 單一來源且比對式由常數導出、`split_description` 的圍籬保護、
`as_list` 四條斷行規則（只認全形句末標點、收尾符號留前段、有序編號須從 1 連續）、
理由與總覽共用 `as_list`、`fence_for` 依內容加長圍籬、`ANALYSIS_SCHEMA_VERSION=5`
且接受 `(3,4,5)`、`_schema_version` 容許 `"5"`/`5.0` 但擋 `bool` 與 `2.5`、
`ai_utils` retryable 由拋出端決定、`Retry-After` 超上限立即失敗、
`DEFAULT_TIMEOUT=120`、重試與重問分開且 `0` 合法、等待設定在取 diff 之前驗並記 log、
附件前綴比對區分大小寫且限 `.md`、下載前先用 `size` 擋、`utf-8-sig` 嚴格解碼、
本地檔名由工具決定、未設 AI 端點產生替代內容且首行言明未經過 AI、
`normalize_type` 不合法視同沒有種類、底線開頭目錄不算 device/種類。

**README** — 目錄結構樹、報告版面範例（含 `<details>`、`## 詳細資料`、`# 分析涵蓋範圍`、
四欄出處、`SCRIPT_VERSION 2.2`）與實際渲染一致、`MAX_COVERAGE_PATHS=50`、
`MAX_PROMPT_DIFF_BYTES=120000`、AI 三個預設 120/3/1、最壞情況公式、
`ask()`/`ask_json()` 簽章、`script_io` API 表、設定檔鍵全數有說明。

---

## 建議處理順序

1. **F8** — 唯一的 spec 與行為矛盾，改 spec（程式是對的）
2. **F13** — 會讓使用者白做工，一行字
3. **F12** — 與 F8 同源，刪三處殘留敘述
4. **F14** — 補三處 `ai_utils`
5. **F5 / F6** — 刪掉 dead widget 與兩個殘留檔（或補文件）
6. **F7** — 要動程式，獨立一輪比較妥；也可以選擇在 spec 說明這個功能刻意不走流程 API
7. **F1~F4、F9~F11** — 註解與訊息的小修，可以併成一次
