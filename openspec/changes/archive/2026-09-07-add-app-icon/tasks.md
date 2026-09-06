> **本容器沒有 Qt**（`qmake` 不存在），因此所有「編譯通過」與 Windows 實機
> 相關的項目都無法在此驗證，一律留白待你在 Qt Creator 上確認。
> 已勾選的項目都是實際跑過並檢查過輸出的。

## 1. 圖示資產產生

- [x] 1.1 建立 `resources/icons/src/`，把來源圖複製進去，驗證：256x256 RGBA PNG，md5 `a2df2017…` 與上傳原檔一致
- [x] 1.2 撰寫 `tools/make_app_icon.py`：以四邊邊界為起點做連通區域填充去背，驗證：原圖 30,573 個近白像素中，去背後僅 10 個非邊界連通者保留 —— 圖案內部沒有被打出破洞
- [x] 1.3 邊緣部分 alpha 與反預乘還原，驗證：alpha 0 共 30,563 像素、alpha 255 共 34,652 像素、部分透明 321 像素（即邊緣過渡帶）；256 尺寸疊在純黑上無白邊
- [x] 1.4 以 Lanczos 輸出 `app_icon_{16,24,32,48,64,128,256}.png`，驗證：七檔皆存在且尺寸正確；七個尺寸疊在黑底、白底、深藍底上各檢視一次，無白邊、無破洞，16x16 仍可辨識出戴墨鏡的貓臉
- [x] 1.5 輸出多尺寸 `PPS2_0DevTool.ico`，驗證：解析檔頭得 7 個項目，16–128 為 BMP（`biHeight` 為高度兩倍、32bpp、BI_RGB）、256 為 PNG；從 `.ico` 讀回七個尺寸疊在黑底上目視，方向正確、透明正常
- [x] 1.6 腳本開頭註明它不是建置步驟、需要 Pillow、以及重新產生方式，驗證：與 README 的說明一致

## 2. Qt 資源與專案檔

- [x] 2.1 建立 `resources.qrc`（前綴 `/icons`，以 alias 讓資源路徑為 `:/icons/app_icon_16.png`），驗證：XML 合法，且清單中七個檔案路徑逐一確認存在
- [ ] 2.2 驗證 `qmake` 產生 `qrc_resources.cpp` 且編譯通過 —— **待你在 Qt Creator 上確認**
- [x] 2.3 在 `.pro` 加入 `RESOURCES += resources.qrc`
- [x] 2.4 在 `.pro` 加入 `RC_ICONS = resources/icons/PPS2_0DevTool.ico`（非 Windows 平台由 qmake 忽略，不需 `#ifdef`）
- [x] 2.5 加入 `VERSION = 2.0.0`、`QMAKE_TARGET_PRODUCT`、`QMAKE_TARGET_DESCRIPTION`，與 `version.h` 的 `TOOL_NAME` / `TOOL_VERSION` 一致
  > `QMAKE_TARGET_COMPANY` 未設定 —— 不知道要填什麼公司名稱，不編造。要補的話在 `.pro` 加一行即可。
- [x] 2.6 確認 `.gitignore` 無需修改，驗證：`git check-ignore` 對 `.qrc`、七個 PNG、`.ico`、腳本、來源圖皆無命中

## 3. 程式碼接線

- [x] 3.1 在 `main.cpp` 匿名 namespace 加入 `buildAppIcon()`，七個尺寸各自 `addFile()`，驗證：括號配對平衡，資源路徑與 `.qrc` 的 alias 逐一對得上
- [x] 3.2 在 `setApplicationVersion()` 之後呼叫 `app.setWindowIcon(buildAppIcon())`，位置早於三個啟動用的 `QMessageBox`
- [x] 3.3 `pps2_0devtool.cpp` 的 `setupTrayIcon()` 未被修改，驗證：`git diff` 中該檔案無變更

## 4. 驗收（Windows —— 全部待你確認）

- [ ] 4.1 Windows 與 macOS 皆編譯通過
- [ ] 4.2 主視窗標題列顯示貓臉圖示
- [ ] 4.3 系統匣顯示的是貓臉圖示而非通用電腦圖示
  > 這一條是 design D7 的推論（`QWidget::windowIcon()` 未自訂時回傳應用程式圖示，
  > 因此 `setupTrayIcon()` 不需修改）。本專案先前正是在系統匣吃過「以為會動、
  > 其實靜默失效」的虧（archive 的 7.6），而 offscreen 平台的
  > `isSystemTrayAvailable()` 回 false，自動測試碰不到這段 —— **必須人眼確認**。
  > 若沒生效，退路是在 `setupTrayIcon()` 明確設定圖示。
- [ ] 4.4 刪除設定檔啟動，錯誤訊息框的標題列帶有應用程式圖示
- [ ] 4.5 `PPS2_0DevTool.exe` 在檔案總管中顯示貓臉圖示（「大圖示」與「詳細資料」兩種檢視各看一次）
  > 若仍顯示舊圖示，先複製執行檔到新路徑再看 —— 那是 Windows 的圖示快取，不是建置失敗。
- [ ] 4.6 執行檔內容頁顯示的產品名稱與版本，與 About 對話框一致
- [ ] 4.7 深色主題下工作列、標題列與系統匣的圖示外圍為透明，圖案四周無白色方框
- [ ] 4.8 Alt-Tab 切換器與工作列縮圖顯示應用程式圖示
- [ ] 4.9 既有行為未受影響：關閉主視窗隱藏至系統匣、雙擊還原、右鍵選單只有 Quit

## 5. 文件

- [x] 5.1 更新 `README.md` 目錄結構，加入 `resources.qrc`、`resources/icons/`、`tools/`
- [x] 5.2 新增「應用程式圖示」章節：四個顯示位置各自的來源、換圖步驟、以及「換圖一律要重新建置」與 Windows 圖示快取的說明
- [x] 5.3 在「執行前的準備」註明圖示內嵌、不需要放外部圖檔
