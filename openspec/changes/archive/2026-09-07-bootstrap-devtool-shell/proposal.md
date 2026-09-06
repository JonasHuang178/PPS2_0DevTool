## Why

PPS 2.0 DevTool 要從 v1.4.0 重新起步。舊版把業務邏輯散在 Qt 與 Python 兩邊，累積了幾類會反覆咬人的缺陷：`json.cpp` 把每個功能的每個設定欄位寫死解析，導致程式讀的鍵與設定檔實際的鍵長期不一致而沒人發現；stdout 同時承載結果與除錯訊息，逼出「由後往前掃 `{` 逐一嘗試」的 O(N x k) 解析法；Qt 在 exit code 非 0 時丟棄整份結果 JSON，使用者只看得到「找不到 JSON」。

這個 repo 目前只有 LICENSE 與 README，沒有任何原始碼。因此這次是**從零建立應用程式外殼與腳本執行管線**，把上述缺陷在框架層一次性擋掉，之後的功能才能安全地一個一個長出來。

## What Changes

**建立 Qt 外殼（全新）**

- `main.cpp`：啟動檢查（Python 3、設定檔）、單一實例鎖、crash handler
- `pps2_0devtool.{h,cpp,ui}`：主視窗、來源路徑列、空的 tab widget、系統匣、About
- `json.cpp`：只讀 `Debug_Mode` / `User_Guide_Link` / `Function` 三個工具層級欄位；`Function` 整包不解析
- `debug.{h,cpp}`：`QTDebug` / `QTWarn` / `QTError` + 300 行 ring buffer + Debug console
- `common.{h,cpp}`、`result_code.h`、`version.h`（版號 **v2.0.0**）

**建立腳本執行管線（全新）**

- `PythonRunner.{h,cpp}`：`QProcess` 封裝，stdout 只收結果、stderr 收 log 與進度
- `runFunctionScript()`：**非同步 callback** 介面，取代同步 out-param 形式
- processing 對話框：application-modal、跑馬燈、可取消、不開 nested event loop

**建立 Python 層（全新）**

- `scripts/script_io.py`：信封處理，公開 `parse_request` / `cfg` / `arg` / `progress` / `reply` / `reply_fail` / `run`
- `scripts/script_utils/logger.py`：唯一設定 logging 的地方，全部等級走 stderr
- `scripts/_function_template.py`：功能腳本範本，原樣可執行，用於端到端驗證

**與既有設計文件不一致之處**（`IMPLEMENTATION.md` / `PYTHON.md` 需同步更新，理由記於 design.md）

- **BREAKING** 信封移除 `tool` 欄位；工具身分改走 `TOOLNAME` / `TOOLVERSION` 環境變數
- **BREAKING** `--dump-config` 模板移除 `config_file`，改為內嵌 `config` 物件
- **BREAKING** 投遞方式從三種減為兩種：移除「直接下旗標」路徑
- 移除 stdout 解析的 fallback 掃描；整段 parse 失敗即視為失敗
- 移除 `stderrTail` / `stdoutTail`；`Debug_Mode` 關閉時不收集 stderr 內容

**明確不做的**

- 不實作任何功能 tab（五個舊功能全部移除，未來逐一重新設計）
- 不寫業務腳本、不建 CI、不做打包、不升級 Qt6

## Capabilities

### New Capabilities

- `app-shell`: 應用程式外殼 — 設定檔讀取與功能查詢介面、功能掛勾訊號、Debug console、共用 UI 服務、視窗與啟動行為
- `script-execution`: Qt 端腳本執行管線 — `runFunctionScript` callback 契約、通道分離、成敗判定、取消狀態機、processing 對話框、行程環境
- `script-envelope`: Python 端契約 — Request/Response 信封 schema、`script_io` 公開 API、參數與設定宣告、`--dump-config` 模板、logger、exit code、跨平台規則

### Modified Capabilities

（無 — `openspec/specs/` 目前是空的，這是第一個 change）

## Impact

- **新增原始碼**：整個 repo 的 C++ 與 Python 檔案；`PPS2_0DevTool.pro`、`PPS2_0DevTool.json`
- **建置環境**：Windows 為 Qt Creator + MinGW + Qt5 + qmake；macOS 僅用於確認編得過，Windows 專屬 API 一律包 `#ifdef Q_OS_WIN`
- **設定檔**：`PPS2_0DevTool.json` 的 `Function` 物件初始為空；每個功能區塊必備 `Program` 與 `Visible`
- **外部相依**：使用者機器需有 Python 3；Python 腳本必須在 Windows 與 Linux 都能執行
- **文件**：`IMPLEMENTATION.md` 與 `PYTHON.md` 有 12 處與本 change 的決策不一致，需另行同步（不在本 change 範圍）
