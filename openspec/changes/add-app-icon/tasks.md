## 1. 圖示資產產生

- [ ] 1.1 建立 `resources/icons/src/`，把本 change 的 `assets/app_icon_original.png` 複製進去作為來源圖，驗證：檔案為 256x256 RGBA PNG，與原圖位元組相同
- [ ] 1.2 撰寫 `tools/make_app_icon.py`：讀入來源圖，以四邊邊界像素為起點對「與背景色差異在容差內」的像素做連通區域填充並設為透明，驗證：圖案內部的白色閃光與墨鏡反光**未**被去掉（把結果疊在純黑背景上檢查，閃光仍為白色實心）
- [ ] 1.3 在腳本中加入邊緣處理：對邊界過渡像素依與背景色的接近程度換算部分 alpha，驗證：256 尺寸的結果疊在純黑背景上，圖案外緣無一圈白邊
- [ ] 1.4 以 Lanczos 重採樣輸出 `app_icon_{16,24,32,48,64,128,256}.png` 至 `resources/icons/`，驗證：七個檔案皆存在且尺寸正確，16x16 疊在黑底與白底上皆無白邊、無破洞
- [ ] 1.5 輸出多尺寸 `resources/icons/PPS2_0DevTool.ico`（含 16/24/32/48/64/128/256，256 為 PNG 壓縮項目），驗證：檔案標頭列出 7 個項目，且檔案大小遠小於未壓縮的 7 x 256KB
- [ ] 1.6 在腳本開頭以註解寫明它不是建置步驟、需要 Python 3 + Pillow、以及重新產生的執行方式，驗證：對照 README 的說明一致

## 2. 內嵌回退資源與專案檔

- [ ] 2.1 建立 `resources.qrc`，前綴 `/icons`，收錄七個 PNG（不含 `.ico`、不含來源圖），驗證：`qmake` 後產生 `qrc_resources.cpp` 且編譯通過
- [ ] 2.2 在 `PPS2_0DevTool.pro` 加入 `RESOURCES += resources.qrc`，驗證：Windows 與 macOS 兩端皆編譯通過
- [ ] 2.3 在 `PPS2_0DevTool.pro` 加入 `RC_ICONS = resources/icons/PPS2_0DevTool.ico`，驗證：macOS 端 qmake + make 仍成功（該變數在非 Windows 平台被忽略，不需 `#ifdef`）
- [ ] 2.4 加入 `VERSION = 2.0.0` 與 `QMAKE_TARGET_PRODUCT` / `QMAKE_TARGET_DESCRIPTION` / `QMAKE_TARGET_COMPANY`，內容與 `version.h` 的 `TOOL_NAME` / `TOOL_VERSION` 一致，驗證：Windows 上執行檔的「內容」頁顯示的產品名稱與版本與 About 對話框相同
- [ ] 2.5 把 `IconLoader.{h,cpp}` 加入 `.pro` 的 `SOURCES` / `HEADERS`，驗證：兩平台編譯通過
- [ ] 2.6 確認 `.gitignore` 無需修改（`qrc_*.cpp` 已在忽略清單，`resources/` 與 `tools/` 未被任何規則命中），驗證：`git status` 中七個 PNG、`.ico`、`.qrc`、腳本與新原始檔皆為待加入，無建置產物混入

## 3. IconLoader（執行期載入）

- [ ] 3.1 建立 `IconLoader.{h,cpp}`，公開單一函式回傳 `QIcon`，驗證：編譯通過
- [ ] 3.2 實作外部掃描：以 `QCoreApplication::applicationDirPath()` 為基準找 `icons/` 資料夾，取其中符合 `app_icon*.png` 的檔案，驗證：從三種不同的當前目錄啟動程式，掃到的是同一組檔案（與既有的腳本路徑解析規則一致）
- [ ] 3.3 實作全有全無取代：外部找到至少一個可用圖檔時，`QIcon` 只由外部檔案組成；一個都沒有才逐一加入內嵌的七個尺寸，驗證：外部只放一張 256 時，系統匣的 16x16 顯示的是縮小後的新圖，**不是**內嵌的舊圖
- [ ] 3.4 處理「檔案存在但不是合法圖檔」：`QIcon::addFile()` 對該檔無效時不計入可用數，全部無效等同一個都沒有，驗證：放一個改副檔名的文字檔，程式回退內嵌預設且正常啟動
- [ ] 3.5 記錄一筆診斷訊息說明本次來源與採用的檔案數，驗證：`Debug::write()` 一律寫入環形緩衝，因此該訊息即使早於 `Debug::init()` 仍可在 crash.log 中看到
- [ ] 3.6 確認外部資料夾缺失時不顯示任何訊息框、不影響結束碼，驗證：刪除 `icons/` 後啟動，程式正常執行且有內嵌圖示

## 4. 接線

- [ ] 4.1 在 `main.cpp` 的 `setApplicationVersion()` 之後呼叫 `app.setWindowIcon(IconLoader::appIcon())`，驗證：程式啟動後主視窗標題列顯示貓臉圖示
- [ ] 4.2 確認圖示設定早於所有 `QMessageBox`：刪除設定檔啟動，驗證：錯誤訊息框的標題列帶有應用程式圖示
- [ ] 4.3 確認 `pps2_0devtool.cpp` 的 `setupTrayIcon()` 未被修改，驗證：`git diff` 中該檔案無變更

## 5. 驗收（Windows）

- [ ] 5.1 系統匣顯示的是貓臉圖示而非通用電腦圖示，驗證：Windows 上實機檢視系統匣（offscreen 平台的 `isSystemTrayAvailable()` 回 false，自動測試碰不到這段，必須人眼確認）
- [ ] 5.2 執行檔目錄旁只放設定檔與 `scripts/`（無 `icons/`）時，視窗與系統匣顯示內嵌預設圖示，驗證：以乾淨的部署目錄啟動
- [ ] 5.3 放入 `icons/app_icon.png`（換一張明顯不同的圖）後重啟，視窗與系統匣改顯示新圖，驗證：**未重新建置**，僅重啟程式
- [ ] 5.4 承上，同時確認檔案總管中的 `PPS2_0DevTool.exe` 仍顯示建置時嵌入的圖示，驗證：這是預期行為（見 design 的 D10），非缺陷
- [ ] 5.5 `PPS2_0DevTool.exe` 在檔案總管中顯示貓臉圖示，驗證：以「大圖示」與「詳細資料」兩種檢視各看一次；若仍顯示舊圖示，先複製執行檔到新路徑再看以排除圖示快取
- [ ] 5.6 深色主題下工作列、標題列與系統匣的圖示外圍為透明，驗證：切換至深色主題逐一檢視，圖案四周無白色方框
- [ ] 5.7 Alt-Tab 切換器與工作列縮圖顯示的是應用程式圖示，驗證：實機操作確認
- [ ] 5.8 最終確認：Windows 與 macOS 皆編譯通過，且既有行為未受影響（關閉主視窗隱藏至系統匣、雙擊還原、右鍵選單只有 Quit），驗證：兩平台建置成功，三項系統匣行為逐一操作正確

## 6. 文件

- [ ] 6.1 更新 `README.md` 的目錄結構，加入 `IconLoader.{h,cpp}`、`resources.qrc`、`resources/`、`tools/`，驗證：結構圖與實際檔案一致
- [ ] 6.2 更新 README 的「執行前的準備」部署圖，加入選用的 `icons/`，並明確寫出它缺少時的行為（回退內嵌預設，不像設定檔那樣會結束程式），驗證：說明與 3.6 的實測結果一致
- [ ] 6.3 在 README 加入換圖說明，以表格區分「換檔即改」（視窗、系統匣、Alt-Tab、工作列按鈕）與「需重新建置」（檔案總管中的 exe、捷徑、內嵌預設），並註明只放單一尺寸時小尺寸會由 Qt 縮放，驗證：依說明各走一次流程，結果與表格一致
- [ ] 6.4 在 README 說明重新產生資產的流程（換掉 `resources/icons/src/` 的來源圖 → 執行 `tools/make_app_icon.py` → 重新建置），並註明該腳本不是建置步驟，驗證：依說明走一次流程可重現目前的產物
