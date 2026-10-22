## Context

動機與各項改動見 proposal.md。這裡只記實作上有選擇餘地的決定。

現況的關鍵事實：

- `script_io.py`
  - `_Param.__slots__ = ("name", "type", "default", "required", "help")`
  - `parse_request(action, description, config, params, template_version)` 回傳
    `{source_path, config, action, params}`。
  - `_is_missing("")` 為真，所以空字串的參數會套用宣告的預設值。
- `ai_analysis_gitlab_mr/__init__.py`
  - `DEBUG_LOG_NAME = "debug.log"`；`write_debug_log()` 以 `"a"` 開檔，只寫
    `message + "\n"`，不加時間戳也不加步驟。
  - `write_debug_file()` 以 `"w"` 開檔，檔名由呼叫端給。
  - `debug_writer(debug_dir)` 綁好目錄後交給鉤子（`inputs["debug_write"]`）。
- 呼叫點：`write_debug_log` 17 處、`debug_write` 18 處、`debug_dir` 79 處。
- `summary.py` 第二輪起以 `recheck%d_` 前綴包住 `debug_write`，所以重查不會互相覆蓋。
- Qt
  - `resolvedSaveDir()` 以 `applicationDirPath()` 為基準解析相對路徑。
  - 勾選時 `debugDir == workDir`；未勾選時 `debugDir` 留空、`workDir` 是 `QTemporaryDir`。
  - `showResultDialog(title, content, elapsedMs)` 是外殼的通用視窗，內容為
    `QPlainTextEdit` ＋ 一行 Elapsed ＋ OK。
  - `onFlowFinished()` 失敗時呼叫 `showUI_ErrorMessageBox()` 後直接 return。
  - `QDesktopServices` 已被 include（表格雙擊開 GitLab 頁面在用）。
- 持續整合：`W=$CI_PROJECT_DIR/pps-work`、`D=$CI_PROJECT_DIR/pps-work/debug`；
  `artifacts: when: always, paths: [pps-work/], expose_as`。

## Goals / Non-Goals

**Goals**

- 步驟身分成為**結構性**的保證（靠檔名），不靠呼叫端在訊息裡自己寫。
- 憑證遮罩只有一份規則，而且兩個呼叫端不必各自實作。
- 使用者在成功與失敗兩種情況下都能一步到達那一次的紀錄目錄。

**Non-Goals**

- 不改報告的內容與版面、不改分析結構的格式、不改任何一步的產物格式。
- 不碰 `Debug_Mode` 與 debug console。
- 不碰設定鍵 `Save_Analysis_File_Dir`。
- 不處理 runner 存取權或 TLS 層的暴露 —— 遮罩保護的是落檔那一份。
- 不加 CI 的 skip 開關（另一輪討論的題目，刻意不併進來）。

## Decisions

### D1. 紀錄檔名由 `out_path` 導出

```python
# log_dir = <工作目錄>/logs
# out_path = <工作目錄>/03_summary.json  ->  logs/03_summary.log
# out_path 為空                         ->  logs/<action>.log
```

**為什麼不讓呼叫端傳檔名**：腳本不知道自己是流程的第幾步 —— 步驟號是呼叫端的命名慣例
（Qt 的 `kStepArtifactName`、CI 的 yml），腳本只照 `out_path` 寫檔。從 `out_path` 的基底名
導出，等於「同名、換副檔名」，不需要解析那個慣例，也不需要新增參數。

**為什麼不讓腳本解析 `NN_` 前綴**：那會把腳本耦合到呼叫端的命名慣例上。導出整個基底名不會。

### D2. 時間戳由寫入那一支加，不由呼叫端加

`write_log()` 自己在每一行前面補 `[YYYY-MM-DD HH:MM:SS.mmm]`。17 個呼叫點的訊息內容不必改
（原本在訊息開頭自己寫的那個步驟名可以留著，只是不再是唯一的依據）。

格式與 `logger`／debug console 對齊，取 `datetime.now().strftime("%Y-%m-%d %H:%M:%S.") +
毫秒三位`。

### D3. 信封紀錄由 `parse_request()` 寫出

遮罩與寫出都發生在 `parse_request()` 的尾端 —— 它是唯一同時握有信封、宣告（含遮罩）與
解析後 `params`（含 `log_dir`）的地方。

`log_dir` 這個鍵名由 `script_io` 以約定取得。`script_io` 是通用層，不該認得某個功能的參數
形狀，所以：**`parse_request()` 多收一個選填的參數名**（預設 `"log_dir"`），讓沒有紀錄目錄
概念的腳本（例如 single_building）傳空值即可關閉這個行為。

替代方案是讓每支腳本在 `parse_request()` 之後自己呼叫一支 `write_request_log()`。不採用：
七支腳本各加一行，而漏掉的那一支不會有任何徵兆。

### D4. 遮罩的宣告形式

`_Param` 的 `__slots__` 加一個 `mask`：

| 值 | 行為 |
|---|---|
| `None`（預設） | 原樣寫出 |
| `True` | 整個值換成 `"***"` |
| callable | 以該函式的回傳值取代，函式收原值回字串 |

`ai_api_key` 用 `mask=True`。`ai_connection` 用 callable，實作放在 `ai_utils`（它已經有
`split_connection()`，拆法只有一份）：

```python
# openai:https://host/api/external/v1/chat:ABC123
#   -> openai:https://host/api/external/v1/chat:***
```

遮罩函式放 `ai_utils` 而不是 `script_io`：連線字串的形狀是那個服務的協定，`script_io` 不該
認得它。

### D5. Qt 的三層版面

```
<存放目錄>/gitlab_mr_result_<repo>_<iid>_<時間戳>/     ← workDir，產物
                                            ├── logs/      ← logDir
                                            └── requests/   ← 腳本自己建
```

`logDir` 改成 `workDir + "/logs"`，不再等於 `workDir`。`requests/` 由腳本在需要時
`makedirs`，Qt 不必預先建立 —— 現有的 `write_debug_*` 本來就會自己建目錄。

未勾選時 `logDir` 仍為空字串，於是 `logs/` 與 `requests/` 都不會出現，產物照舊寫在
`QTemporaryDir`。

### D6. 持續整合的 req 檔移出 artifact 路徑

```yaml
    R: "$CI_PROJECT_DIR/pps-requests"   # 送進腳本的信封；不在 artifact 路徑之下
    D: "$CI_PROJECT_DIR/pps-work/logs"
```

`cat > "$R/req3.json"` 取代 `"$W/req3.json"`，兩行 `rm -f` 移除。真憑證從頭就不進
`pps-work/`，而 artifact 裡留下的是腳本寫出的遮罩版（`pps-work/requests/ai_summary.json`）。

代價：那個目錄在 git 的 checkout 之下，會留下未追蹤的檔案。對這個 job 無害（之後沒有任何
git 操作），而 runner 在 job 之間本來就會清掉未追蹤的檔案。

### D7. 結果視窗多收一個選填目錄

```cpp
void showResultDialog(const QString &title, const QString &content,
                      qint64 elapsedMs,
                      const QString &folder = QString());
```

`folder` 非空時，在 Elapsed 那一行旁邊加一個可選取的路徑標籤（`QLabel` 開
`Qt::TextSelectableByMouse`）與一顆按鈕，按下走
`QDesktopServices::openUrl(QUrl::fromLocalFile(folder))`。空的時候版面與現在完全相同。

**失敗改走同一個視窗**：`onFlowFinished()` 失敗時不再呼叫 `showUI_ErrorMessageBox()`，改用
同一個 `showResultDialog()`，標題標明失敗、內容是「第 N 步失敗」與失敗原因，`folder` 同樣
帶上。這樣成功與失敗的入口是同一套程式碼，不會有一邊有、一邊忘了加的情況。

`folder` 給的是 `context.logDir`（未勾選時為空字串，於是自動沒有入口），不是存放目錄 ——
存放目錄之下有許多帶時間戳的子目錄，給它等於要使用者自己認出剛才那一次。

### D8. 輸入框顯示絕對路徑

`attachWidgets()` 填入時改用 `resolvedSaveDir()` 的結果。`resolvedSaveDir()` 本身不動（它讀
輸入框、解析相對路徑），所以使用者改填相對路徑的行為完全不變。

### D9. 改名的範圍

| 現在 | 改成 |
|---|---|
| 參數 `debug_dir` | `log_dir` |
| `write_debug_log()` | `write_log()` |
| `write_debug_file()` | `write_log_file()` |
| `debug_writer()` | `log_writer()` |
| `inputs["debug_write"]` | `inputs["log_write"]` |
| `DEBUG_LOG_NAME` | 移除 |
| Qt `context.debugDir` | `logDir` |
| Qt `m_widgets.debugFileCheck` | `logFileCheck` |
| `.ui` `aiDebugFileCheckBox` | `aiLogFileCheckBox` |
| 勾選字樣 `Add Debug Analysis file` | `Save run log` |

不動：`Debug_Mode`、`debugMode`、`Save_Analysis_File_Dir`、`logger` 的等級名稱。

`inputs["log_write"]` 是這批裡唯一破壞樹外 device 的改名。樹內只有 `default` 與 `_template`
兩份，一併改；樹外的 device 需要改一個鍵名，寫進文件。

### D10. `list_models` 補齊共通參數

它目前只宣告 `modes`，所以寫不出 `logs/list_models.log`。補上 `log_dir` 與 `out_path`，與
其餘六支一致。

### D11. 版號

`SCRIPT_VERSION` 2.12 → 2.13；`default` 與 `_template` 的 `VERSION` 第二碼各加一（鉤子的
`inputs` 鍵名變了）。

## Risks / Trade-offs

- [遮過的信封不能直接拿去 `--request` 重跑那一步] → 補回被遮掉的值即可，一行的事；文件寫明。
- [`write_log()` 在 17 個呼叫點的訊息裡仍留著舊的步驟前綴字] → 不再是唯一依據，留著無害；
  逐一清掉會讓這一輪的 diff 變大而沒有實際收益。
- [失敗改走結果視窗，視覺上不再是「錯誤訊息框」] → 標題與內容明確標示失敗；換來的是失敗時
  也拿得到紀錄目錄，而那是這一輪的主要目的之一。
- [輸入框顯示絕對路徑之後，設定檔的值與畫面上的值不同] → 專案本來就規定畫面狀態不寫回設定
  檔，不算破例；文件寫明。
- [req 檔留在 git checkout 之下] → runner 在 job 之間清除未追蹤檔案；這個 job 之後沒有 git
  操作。
- [一個情境標題保留了舊用詞] → `結果呈現` 的「未勾選除錯時仍能看到結果」標題不動，因為
  delta 格式沒有「情境改名」這個操作，改標題會被驗證視為刪掉一個情境。其 WHEN 已改用新用詞。

## Migration Plan

1. 樹外自己寫的 device：把鉤子裡的 `inputs["debug_write"]` 改成 `inputs["log_write"]`。
2. 直接以命令列呼叫這些腳本的人：參數 `debug_dir` 改名為 `log_dir`。
3. 持續整合：換上新版 yml（變數 `R` 新增、`D` 改路徑、兩行 `rm -f` 移除）。

回復即還原這個 change 的 commit。產物格式沒有改變，所以舊的 `03_summary.json` 仍然讀得懂。
