## Context

見 [proposal.md](proposal.md) 的 Why。此處只記錄影響技術取捨的現況與限制。

**現況**：`main.cpp` 未呼叫 `setWindowIcon()`；`PPS2_0DevTool.pro` 沒有 `RESOURCES` 也沒有 `RC_ICONS`；`pps2_0devtool.cpp:94` 的系統匣圖示寫成「`windowIcon()` 為空就退回 `SP_ComputerIcon`」，因此目前恆走 fallback。

**來源圖檔**：256x256、8-bit RGBA、非交錯 PNG。經逐像素檢查，**alpha 通道全為 255**，四角為 `(253,254,254)` 至 `(254,254,254)` —— 圖案被畫在一塊接近純白的不透明方形上。原圖已隨本 change 提交於 `assets/app_icon_original.png`。

**技術限制**：Qt5 + qmake，Windows 端 Qt Creator + MinGW；macOS 僅用於確認編得過。Windows 專屬的建置設定不能讓 macOS 端編不過。

**使用者已確認的決定**：

1. 背景去除為透明。
2. 圖示套用範圍包含 Windows 執行檔本身。
3. 採**純內嵌**：圖示編進執行檔，不從外部檔案載入。中途曾規劃「外部優先、內嵌回退」讓換圖不必重建，使用者最終選擇純內嵌以換取專案簡單。換圖一律重新建置。

## Goals / Non-Goals

**Goals:**

- 三處（視窗／對話框、系統匣、執行檔）用的是同一組圖示，換圖時只需重跑一次產生腳本再重建
- 不新增部署項目 —— 執行檔旁不會多出圖檔
- 不新增建置期相依：Windows 端拿到 repo 用 Qt Creator 開啟即可建置，不需要安裝 Python 影像套件
- 圖示資產可追溯、可重新產生 —— 原圖與產生腳本都在 repo 裡

**Non-Goals:**

- 不重繪圖案、不調整構圖與配色
- 不做執行期載入或熱重載
- 不做 macOS bundle 的 `.icns`（macOS 非支援平台）

## Decisions

### 一、資產產生

**D1 去背後產生多尺寸點陣圖，不使用單張大圖縮放。**

Qt 在只有一個尺寸可用時會即時縮放，256 直接縮到 16x16 會讓貓臉的條紋與墨鏡糊成一團。改為在產生階段以 Lanczos 重採樣產出 16 / 24 / 32 / 48 / 64 / 128 / 256 七個尺寸，各自存成獨立 PNG，由 `QIcon::addFile()` 逐一加入，Qt 便會依請求尺寸挑最接近者。

*替代方案*：改用 SVG 向量圖示。不採用 —— 手上只有點陣原圖，重新描邊等於重繪；且 Qt 的 SVG 支援需要額外模組，違反「不新增相依」。

**D2 資產是提交進 repo 的產物，不在建置期產生。**

產生腳本 `tools/make_app_icon.py` 需要 Pillow。若放進建置流程，Windows 端建置就必須先裝 Python 影像套件 —— 本專案的執行期已經要求使用者機器有 Python 3，建置期再加一層相依只會讓「開啟 .pro 就能建置」不再成立。

*作法*：腳本手動執行，產物（PNG 與 `.ico`）提交進 repo。腳本存在的意義是「換圖時可重現」，不是建置步驟。

**D3 去背用四邊 flood fill，不用全域「白色即透明」。**

*作法*：從影像四邊的邊界像素開始，對「與背景色歐氏距離在容差內」的像素做連通區域填充，只有**與邊界連通**的近白色才會被去掉。被圖案包圍的淺色區域因為不連通而完整保留。

*原始理由與實測修正*：規劃時的理由是「圖案內含白色的閃光符號與墨鏡反光，全域門檻會把它們打成透明破洞」。**實作後量測推翻了這個前提** —— 原圖 30,573 個近白像素中，去背後只有 10 個是非邊界連通的；那顆閃光是黃色（不是白色），墨鏡也沒有白色反光。也就是說，這張圖用全域門檻其實也不會出事。

*決定維持 flood fill 的理由*：它對這張圖與全域門檻等價（成本相同、結果相同），但對「日後換一張含白色高光的圖」不會靜默出錯。保留的是安全邊際，不是對現況的修正。這條理由的變更已記錄在此，避免日後有人依原始理由誤判圖案內容。

*邊緣處理*：原圖圖案外緣是抗鋸齒像素（介於橘色與白色之間）。硬性二值化會留下一圈白邊，在深色背景上非常明顯。因此對距離落在 `TOL_INNER`(18) 與 `TOL_OUTER`(110) 之間的邊界像素依比例換算部分 alpha，並以 `C = a*F + (1-a)*BG` 反預乘還原前景色。實測結果：alpha 0 有 30,563 像素、alpha 255 有 34,652 像素、部分透明 321 像素 —— 那 321 個就是邊緣過渡帶。

*驗收方式*：把七個尺寸疊在純黑、純白與深藍背景上目視檢查。白邊與破洞在黑底上一眼可見。

**D4 `.ico` 的內部格式：小尺寸用 BMP、256 用 PNG 壓縮。**

這是 Windows Vista 之後的標準作法，也是 Pillow 儲存 ICO 時的預設行為。實測產出 101,737 bytes，遠小於 7 個未壓縮項目所需的數百 KB。

*取捨*：PNG 壓縮的項目在 Windows XP 上不顯示。XP 不在支援範圍，接受。

### 二、Qt 端接線

**D5 圖示以 `.qrc` 內嵌，不放外部檔案。**

外部圖檔會多一個「掉了就出問題」的部署項目。本工具已經要求設定檔與 `scripts/` 必須放在執行檔旁，再加一項只會讓部署更脆。內嵌後圖示與執行檔同生共死。

*代價*：換圖需重新建置。使用者已明確接受。

*配套*：`.gitignore` 已忽略 `qrc_*.cpp`，不需修改。

*資源路徑*：`.qrc` 用 `prefix="/icons"` 搭配 `alias`，讓資源路徑是 `:/icons/app_icon_16.png` 而不是把整個 `resources/icons/` 目錄結構帶進資源系統。

**D6 在 `main.cpp` 呼叫 `QApplication::setWindowIcon()`，位置緊接 `setApplicationVersion()` 之後。**

`main.cpp` 在建立主視窗之前就可能顯示三個 `QMessageBox`（重複啟動、設定檔錯誤、找不到 Python 3）。圖示若晚於這些設定，這些訊息框會頂著預設圖示出現 —— 而它們正是使用者最可能第一次看到本程式的時機。

**D7 系統匣不改任何程式碼。**

`QWidget::windowIcon()` 在 widget 本身未設定圖示時回傳應用程式圖示。因此 D6 完成後，`setupTrayIcon()` 中 `windowIcon().isNull()` 自然為假，直接走正式分支。

*fallback 保留*：`SP_ComputerIcon` 那一支留著。它現在是死路，但成本為零，且未來若有人誤刪資源，系統匣仍有東西可顯示而不是空白。

*驗證重點*：這一條是「不改程式碼卻預期行為改變」的推論，**必須在 Windows 上實際看過系統匣圖示才算數** —— 本專案先前正是在系統匣這裡吃過一次「以為會動、其實靜默失效」的虧（見 `archive/2026-09-07-bootstrap-devtool-shell` 的 7.6），而 offscreen 平台的 `isSystemTrayAvailable()` 回 false，自動測試碰不到這段。

### 三、Windows 執行檔

**D8 用 qmake 的 `RC_ICONS`，不手寫 `.rc`。**

`RC_ICONS = resources/icons/PPS2_0DevTool.ico` 一行即可，qmake 會產生資源檔並交給 windres 嵌入。手寫 `.rc` 得自己管理資源 ID 與編碼，沒有好處。

*非 Windows 平台*：qmake 在非 Windows 平台忽略 `RC_ICONS`，因此**不需要條件式包裝**，macOS 端照樣編得過。

**D9 一併補上 `VERSION` 與 `QMAKE_TARGET_*`。**

一旦設定 `RC_ICONS`，qmake 產生的資源檔會同時帶入 VERSIONINFO 區塊。不設定的話版本會是 qmake 的預設值，與 `version.h` 的 `v2.0.0` 對不上 —— 使用者在檔案內容頁看到的版本會和 About 對話框顯示的不同。因此設定 `VERSION = 2.0.0`、`QMAKE_TARGET_PRODUCT`、`QMAKE_TARGET_DESCRIPTION`，與 `version.h` 的 `TOOL_NAME` / `TOOL_VERSION` 保持一致。

*`QMAKE_TARGET_COMPANY` 未設定*：不知道要填什麼公司名稱，不編造。留空即可，需要時再補。

*注意*：`VERSION` 只在函式庫專案影響輸出檔名；本專案 `TEMPLATE = app`，`TARGET` 不受影響。

### 四、檔案配置

```
resources.qrc                         Qt 資源清單（前綴 :/icons，含 alias）
resources/icons/
├── src/app_icon_original.png         使用者提供的原圖（含白底，保留供重新產生）
├── app_icon_{16,24,32,48,64,128,256}.png   去背後的多尺寸圖（進 .qrc）
└── PPS2_0DevTool.ico                 多尺寸 ICO（給 RC_ICONS，不進 .qrc）
tools/make_app_icon.py                資產產生腳本（非建置步驟）
```

`.ico` 不放進 `.qrc`：Qt 讀 ICO 要靠 `qico` 影像格式外掛，部署時得一併帶上 `imageformats/qico.dll`；PNG 則內建於 QtGui。Qt 端一律吃 PNG，`.ico` 只給 windres 用。

`buildAppIcon()` 放在 `main.cpp` 的匿名 namespace 而不是獨立檔案：純內嵌之後它只剩「把七個固定路徑加進 `QIcon`」這一件事，沒有值得獨立測試的邏輯。（外部載入方案下它有掃描與回退邏輯，當時規劃為獨立的 `IconLoader`；純內嵌後那個檔案沒有存在理由。）

## Risks / Trade-offs

- **去背容差抓錯會留白邊或咬掉圖案外緣**（D3）→ 已在黑、白、深藍三種背景上逐尺寸目視確認，無白邊、無破洞。這是本次唯一需要人眼判斷的環節。
- **Windows 圖示快取導致更新後仍顯示舊的 exe 圖示** → 已知的系統行為，非程式缺陷。驗證時若遇到，複製執行檔到新路徑再看。已寫進 README 與任務的驗證註記，避免被誤判為實作失敗。
- **D7 推論「不改程式碼即生效」** → 若 Qt 版本行為與預期不符，退路是在 `setupTrayIcon()` 明確設定圖示。實際驗證前不預先加，避免看不出是哪一條在生效。
- **換圖需重新建置**（D5）→ 使用者已明確接受此取捨。
- **`.ico` 的 256 項目在 Windows XP 不顯示**（D4）→ XP 非支援平台，接受。

## Migration Plan

無資料遷移。使用者重新取得建置後的執行檔即生效。既有部署目錄不需要調整。

Windows 端首次建置後若檔案總管仍顯示舊圖示，屬圖示快取，非需要處理的缺陷。

## Open Questions

- `QMAKE_TARGET_COMPANY` 要填什麼？目前留空（見 D9）。不影響任何行為，只影響執行檔內容頁的「公司」欄位。
