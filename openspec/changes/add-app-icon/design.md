## Context

見 [proposal.md](proposal.md) 的 Why。此處只記錄影響技術取捨的現況與限制。

**現況**：`main.cpp` 未呼叫 `setWindowIcon()`；`PPS2_0DevTool.pro` 沒有 `RESOURCES` 也沒有 `RC_ICONS`；`pps2_0devtool.cpp:94` 的系統匣圖示寫成「`windowIcon()` 為空就退回 `SP_ComputerIcon`」，因此目前恆走 fallback。

**來源圖檔**：256x256、8-bit RGBA、非交錯 PNG。經逐像素檢查，**alpha 通道全為 255**，四角為 `(253,254,254)` 至 `(254,254,254)`，也就是圖案被畫在一塊接近純白的不透明方形上。圖案本身包含**白色的閃光符號與墨鏡反光**，這一點決定了去背方法（見 D3）。原圖已隨本 change 一起提交於 `assets/app_icon_original.png`。

**技術限制**：Qt5 + qmake，Windows 端 Qt Creator + MinGW；macOS 僅用於確認編得過。Windows 專屬的建置設定不能讓 macOS 端編不過。

**使用者已確認的兩項決定**：背景去除為透明；圖示套用範圍包含 Windows 執行檔本身，而不只是執行中的視窗與系統匣。

## Goals / Non-Goals

**Goals:**

- 三處（視窗／對話框、系統匣、執行檔）用的是同一組圖示，換圖時只需重跑一次產生腳本
- 不新增建置期相依：Windows 端拿到 repo 用 Qt Creator 開啟即可建置，不需要安裝 Python 影像套件
- 圖示資產可追溯、可重新產生 —— 原圖與產生腳本都在 repo 裡

**Non-Goals:**

- 不重繪圖案、不調整構圖與配色
- 不做 macOS bundle 的 `.icns`（macOS 非支援平台）
- 不追求在 Windows XP 等已不支援的系統上顯示 256 尺寸

## Decisions

### 一、資產產生

**D1 去背後產生多尺寸點陣圖，不使用單張大圖縮放。**

Qt 在只有一個尺寸可用時會即時縮放，256 直接縮到 16x16 會讓貓臉的條紋與墨鏡糊成一團。改為在產生階段以高品質重採樣（Lanczos）產出 16 / 24 / 32 / 48 / 64 / 128 / 256 七個尺寸，各自存成獨立 PNG，由 `QIcon::addFile()` 逐一加入，Qt 便會依請求尺寸挑最接近者。

*替代方案*：改用 SVG 向量圖示。不採用 —— 手上只有點陣原圖，重新描邊等於重繪；且 Qt 的 SVG 支援需要額外模組，違反「不新增相依」。

**D2 資產是提交進 repo 的產物，不在建置期產生。**

產生腳本 `tools/make_app_icon.py` 需要 Pillow。若放進建置流程，Windows 端建置就必須先裝 Python 影像套件 —— 本專案的執行期已經要求使用者機器有 Python 3，建置期再加一層相依只會讓「開啟 .pro 就能建置」不再成立。

*作法*：腳本手動執行，產物（PNG 與 `.ico`）提交進 repo。腳本存在的意義是「換圖時可重現」，不是建置步驟。README 中註明它不是建置的一部分。

**D3 去背用四邊 flood fill，不用全域「白色即透明」。**

圖案內含白色的閃光符號與墨鏡反光。若以「亮度高於門檻就設為透明」的全域規則處理，這些白色區域會被打成透明破洞，在深色背景下直接漏底。

*作法*：從影像四邊的邊界像素開始，對「與背景色差異在容差內」的像素做連通區域填充，只有**與邊界連通**的白色才會被去掉；被圖案包圍的白色閃光因為不連通而完整保留。

*邊緣處理*：原圖的圖案外緣是抗鋸齒像素（介於橘色與白色之間）。硬性二值化會留下一圈白邊，在深色背景上非常明顯。因此對邊界區域依「與背景色的接近程度」換算出部分 alpha，並對已知不透明的圖案像素做反預乘還原，讓縮小後的邊緣仍然乾淨。

*驗收方式*：把產出的 16x16 與 32x32 分別疊在純黑與純白背景上目視檢查 —— 白邊與破洞在這兩個背景上一眼可見。

**D4 `.ico` 的內部格式：小尺寸用 BMP、256 用 PNG 壓縮。**

這是 Windows Vista 之後的標準作法，也是 Pillow 儲存 ICO 時的預設行為。256x256 若以未壓縮 BMP 存放，單一項目就要 256KB。

*取捨*：PNG 壓縮的項目在 Windows XP 上不顯示。XP 不在支援範圍，接受。

### 二、Qt 端接線

**D5 圖示以 `.qrc` 內嵌，不放外部檔案。**

外部圖檔會多一個「掉了就壞掉」的部署項目。本工具已經要求設定檔與 `scripts/` 必須放在執行檔旁，再加一項只會讓部署更脆。內嵌後圖示與執行檔同生共死。

*代價*：換圖需重新建置。可接受 —— 圖示不是設定項。

*配套*：`.gitignore` 已忽略 `qrc_*.cpp`，不需修改。

**D6 在 `main.cpp` 呼叫 `QApplication::setWindowIcon()`，位置緊接 `setApplicationName()` 之後。**

`main.cpp` 在建立主視窗之前就可能顯示三個 `QMessageBox`（重複啟動、設定檔錯誤、找不到 Python 3）。圖示若晚於這些設定，這些訊息框會頂著預設圖示出現 —— 而它們正是使用者最可能第一次看到本程式的時機。

**D7 系統匣不改任何程式碼。**

`QWidget::windowIcon()` 在 widget 本身未設定圖示時回傳應用程式圖示。因此 D6 完成後，`setupTrayIcon()` 中 `windowIcon().isNull()` 自然為假，直接走正式分支。

*fallback 保留*：`SP_ComputerIcon` 那一支留著。它現在是死路，但成本為零，且未來若有人誤刪資源，系統匣仍有東西可顯示而不是空白。

*驗證重點*：這一條是「不改程式碼卻預期行為改變」的推論，必須在 Windows 上實際看過系統匣圖示才算數 —— 本專案先前正是在系統匣這裡吃過一次「以為會動、其實靜默失效」的虧（見 `archive/2026-09-07-bootstrap-devtool-shell` 的 7.6），而 offscreen 平台的 `isSystemTrayAvailable()` 回 false，自動測試碰不到這段。

### 三、Windows 執行檔

**D8 用 qmake 的 `RC_ICONS`，不手寫 `.rc`。**

`RC_ICONS = resources/icons/PPS2_0DevTool.ico` 一行即可，qmake 會產生資源檔並交給 windres 嵌入。手寫 `.rc` 得自己管理資源 ID 與編碼，沒有好處。

*非 Windows 平台*：qmake 在非 Windows 平台忽略 `RC_ICONS`，因此**不需要條件式包裝**，macOS 端照樣編得過。

**D9 一併補上 `VERSION` 與 `QMAKE_TARGET_*`。**

一旦設定 `RC_ICONS`，qmake 產生的資源檔會同時帶入 VERSIONINFO 區塊。不設定的話版本會是 qmake 的預設值，與 `version.h` 的 `v2.0.0` 對不上 —— 使用者在檔案內容頁看到的版本會和 About 對話框顯示的不同。因此設定 `VERSION = 2.0.0`、`QMAKE_TARGET_PRODUCT`、`QMAKE_TARGET_DESCRIPTION`、`QMAKE_TARGET_COMPANY`，與 `version.h` 的 `TOOL_NAME` / `TOOL_VERSION` 保持一致。

*注意*：`VERSION` 只在函式庫專案影響輸出檔名；本專案 `TEMPLATE = app`，`TARGET` 不受影響。

### 四、檔案配置

```
resources.qrc                         Qt 資源清單（前綴 :/icons）
resources/icons/
├── src/app_icon_original.png         使用者提供的原圖（含白底，保留供重新產生）
├── app_icon_{16,24,32,48,64,128,256}.png   去背後的多尺寸圖（進 .qrc）
└── PPS2_0DevTool.ico                 多尺寸 ICO（給 RC_ICONS，不進 .qrc）
tools/make_app_icon.py                資產產生腳本（非建置步驟）
```

`.ico` 不放進 `.qrc`：Qt 讀 ICO 要靠 `qico` 影像格式外掛，部署時得一併帶上 `imageformats/qico.dll`；PNG 則是內建於 QtGui。Qt 端一律吃 PNG，`.ico` 只給 windres 用。

## Risks / Trade-offs

- **去背容差抓錯會留白邊或咬掉圖案外緣**（D3）→ 以「與邊界連通」為條件而非全域門檻，並在 16x16 與 32x32 上分別疊黑底與白底目視檢查。這是本次唯一需要人眼判斷的環節。
- **Windows 圖示快取導致更新後仍顯示舊圖示** → 已知的系統行為，非程式缺陷。驗證時若遇到，複製執行檔到新路徑再看，或清 icon cache。此點寫進任務的驗證註記，避免被誤判為實作失敗。
- **D7 推論「不改程式碼即生效」** → 若 Qt 版本行為與預期不符，退路是在 `setupTrayIcon()` 明確寫 `QIcon(":/icons/app")`。實際驗證前不預先加這行，避免加了看不出是哪一條在生效。
- **`.ico` 的 256 項目在 Windows XP 不顯示**（D4）→ XP 非支援平台，接受。
- **換圖需重新建置**（D5）→ 圖示不是設定項，接受。

## Migration Plan

無資料遷移。使用者重新取得建置後的執行檔即生效。

Windows 端首次建置後若檔案總管仍顯示舊圖示，屬圖示快取，非需要處理的缺陷。

## Open Questions

無。背景處理方式與套用範圍已由使用者確認。
