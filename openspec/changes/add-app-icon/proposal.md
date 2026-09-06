## Why

目前這支工具沒有自己的圖示。`main.cpp` 從未呼叫 `setWindowIcon()`，`.pro` 也沒有任何圖示資源，結果有三處都在用預設圖示：

- 主視窗標題列與 Alt-Tab 切換器顯示 Qt 的預設圖示
- `setupTrayIcon()`（`pps2_0devtool.cpp:94`）因為 `windowIcon().isNull()` 恆為真，一路走 fallback 分支用 `QStyle::SP_ComputerIcon`（一台通用電腦圖案）
- `PPS2_0DevTool.exe` 在檔案總管、工作列與捷徑上是 MinGW 產出的無圖示執行檔

使用者提供了一張 256x256 的貓臉圖作為本工具的識別，這次把它接上以上三處。

## What Changes

**新增圖示資產**

- 以使用者提供的原圖為來源，將接近純白（#FEFEFE）的方形背景去除為透明 —— 原圖為 8-bit RGBA 但 alpha 全為 255，直接使用會在深色工作列與標題列出現一塊白方框
- 產生多尺寸 PNG（16 / 24 / 32 / 48 / 64 / 128 / 256）與一份多尺寸 `.ico`
- 原圖與產生腳本一併提交，讓資產可追溯、可重新產生

**接上 Qt 端**

- 新增 `resources.qrc`，把多尺寸 PNG 內嵌進執行檔
- `main.cpp` 在建立 `QApplication` 後立即 `setWindowIcon()`，早於任何 `QMessageBox` 與主視窗建立 —— 啟動失敗的錯誤訊息框也帶圖示
- 系統匣不需要改任何程式碼：`QWidget::windowIcon()` 在 widget 未自行設定時回傳應用程式圖示，`setupTrayIcon()` 的 `isNull()` 判斷自然改走正式分支，`SP_ComputerIcon` fallback 原樣保留作為安全網

**接上 Windows 執行檔**

- `.pro` 加入 `RC_ICONS`，由 qmake 產生資源檔並在連結期嵌入；同時補上 `VERSION` 與 `QMAKE_TARGET_*`，讓 qmake 一併產生的 VERSIONINFO 與 `version.h` 一致，而不是預設值

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `app-shell`: 新增「應用程式圖示」需求 —— 圖示以資源內嵌、多尺寸、背景透明，並套用至視窗、對話框、系統匣與 Windows 執行檔

## Impact

- **新增檔案**：`resources.qrc`、`resources/icons/`（多尺寸 PNG 與 `.ico`）、`resources/icons/src/`（原圖）、`tools/make_app_icon.py`（資產產生腳本）
- **修改檔案**：`PPS2_0DevTool.pro`（`RESOURCES`、`RC_ICONS`、`VERSION`、`QMAKE_TARGET_*`）、`main.cpp`（一行 `setWindowIcon()`）、`README.md`（目錄結構）
- **不修改**：`pps2_0devtool.cpp` 的 `setupTrayIcon()` 保持原樣
- **建置**：`RC_ICONS` 在非 Windows 平台由 qmake 忽略，不需要 `#ifdef`；macOS 端仍編得過
- **建置相依**：不新增。資產是提交進 repo 的產物，產生腳本只在需要換圖時手動執行（需 Python 3 + Pillow）
- **不做**：macOS bundle 的 `.icns`（macOS 非支援平台）；不更動圖案本身的構圖與配色

## Non-goals

- 不重繪或重新設計圖案 —— 只做去背與尺寸產生
- 不引入建置期的圖片處理步驟
- 不加入應用程式內的關於視窗圖示、啟動畫面或其他品牌元素
