# PPS 2.0 DevTool

PPS 2.0 開發輔助工具。框架與腳本執行管線已完成，並帶有第一個功能 tab
**Single Building**。

框架已在 Windows（Qt Creator + MinGW）與 macOS 上建置並驗證。外殼交付時延後的
兩項驗收 —— 關閉 Debug console 時清理子行程、以及 Qt 與 Python 的訊息同時出現在
console 中 —— 在 Single Building 交付後才具備觸發腳本的入口，**尚待在 Windows
實機補驗**。

> **Single Building 的 Windows 實機驗收尚未完成，change 已先行歸檔。**
> 已在 Linux + Qt 5.15.13 完成 62 項自動化行為驗證；需要實機的部分共 46 項，
> 目前僅完成 4 項（取得程式碼、建置、部署、Python 可用），其中建置與部署兩項
> 因 `.pro` 加入自動部署規則而需重做。**其餘 42 項未驗證**，包含排序在 Windows
> 版 Qt 上的實際次序、設定檔的 Windows 絕對路徑往返，以及上述兩項延後驗收。
> 未完成的任務為 5.2、6.1、6.2、6.3、6.4。
> 逐項狀態與交接方式見
> [`openspec/changes/archive/2026-09-11-add-single-building-tab/tasks.md`](openspec/changes/archive/2026-09-11-add-single-building-tab/tasks.md)
> 第 6 節。

應用程式圖示已內嵌進執行檔，並在 Windows 上實機驗收通過（見 `openspec/changes/archive/2026-09-07-add-app-icon/tasks.md` 第 4 節）。

---

## 最高原則

> **Qt 只負責 GUI —— 讓使用者「選擇」。真正的實作寫在 Python。**

| 層 | 職責 | 不該做的事 |
|---|---|---|
| **Qt (C++)** | 顯示清單、接收選擇、組裝參數、呼叫腳本、**編排多步驟流程**、呈現結果 | 解析檔案格式、呼叫外部 API、產生報表、做 AI 分析 |
| **Python** | 單一步驟的全部業務邏輯 | 開視窗、管理 UI 狀態 |

「編排流程」是指決定執行哪一步、依前一步的結果組裝下一步的參數、判定流程
何時結束 —— 控制流在 Qt，運算在腳本。這條線一旦模糊（例如在 Qt 裡算出
「筆數超過門檻就改用另一種做法」），那段邏輯就再也無法從命令列測試，也無法
被其他 Python 呼叫端重用。

**每一個功能 = 一個 tab。** 功能之間互相獨立：各自讀自己的設定、決定自己顯示與否、
呼叫自己的腳本、**各自保有自己的來源路徑**。

畫面上方的來源路徑欄位是共用的，但它顯示的是**當前功能**的路徑：切換分頁時會還原成
該功能自己的值，在某個分頁改路徑不會牽動其他分頁。還原不算「變更」，不會觸發任何
功能重新載入。

```
                        ┌──────────── 別人 / CI ────────────┐
                        ↓                                   ↓
Qt ──信封(stdin)──→ 入口腳本 ──→ script_utils ──→ 外部世界（GitLab / Jira / 檔案）
   ←─結果(stdout)──   （很薄）      （業務邏輯）
   ←─進度(stderr)──
```

「給別人用」的正確介面是 `script_utils`，不是腳本 —— 別人要整合進自己的流程時，
`from script_utils import gitlab_utils` 遠比「開子行程、組參數、parse JSON」好用。

### 兩種分組軸

`scripts/` 底下有兩種東西，各用各的分組方式：

| | 分組依據 | 例子 |
|---|---|---|
| **入口腳本** | 應用**功能** | `scripts/single_building/` |
| **共用模組** | 技術**領域** | `script_utils/system_utils.py`、`file_utils.py`、`gitlab_utils.py` |

共用模組**不依功能分組** —— 那樣的話第二個功能需要同一個能力時就無處可放。
只服務單一功能的東西留在 `scripts/<功能>/` 之下。

一個分組**預設是單一 `.py` 檔案**，**不以行數為拆檔的理由**。唯一該拆成目錄的
情況是分組內出現**彼此不相依的獨立關切**；拆的時候由該目錄的 `__init__.py` 原樣
re-export。呼叫端一律寫 `from script_utils import <分組>`，兩種形式在 import 端
完全相同，拆與不拆都不必改任何一行呼叫 —— 所以**先全部寫在單一檔案裡，真的該拆
的時候一口氣拆開**。先拆換到的只有一份要跟著維護的再匯出清單，漏掉一筆的症狀是
「函式明明寫好了卻搆不到」。

行數不是判準：長度只是內聚性的代理指標，指錯方向的時候比指對的多。`jira_utils`
七百多行，但整份圍繞同一個 client、同一種認證、同一套錯誤處理 —— 照行數拆只會把
一件事切成三份。（Python 標準庫的 `argparse` 約 2500 行、`http/client.py` 約
1500 行，都是單檔。）

因為入口腳本放進了子目錄，每支頂部都有一行把 `scripts/` 插進 `sys.path` 的設定，
**不能刪**：Python 只把「腳本所在目錄」放進 `sys.path`，少了它，命令列直接執行時
`script_io` 與 `script_utils` 都匯不到。Qt 雖然會注入指向 `scripts/` 的 `PYTHONPATH`，
但命令列與 CI 沒有那個環境，而那是本專案明確支援的用法。

---

## 目錄結構

```
PPS2_0DevTool/
├── main.cpp                  啟動檢查、單一實例鎖、crash handler
├── pps2_0devtool.{h,cpp,ui}  應用程式外殼（含每個功能各自的來源路徑）
├── SingleBuilding.{h,cpp}    功能：Single Building
├── AIAnalysisGitLabMR.{h,cpp}  功能：AI Analysis GitLab MR
├── json.{h,cpp}              設定檔讀取（只讀工具層級）
├── PythonRunner.{h,cpp}      腳本執行管線
├── ProcessingDialog.{h,cpp}  處理中對話框
├── debug.{h,cpp}             QTDebug/QTWarn/QTError + 300 行 ring buffer
├── common.{h,cpp}            formatElapsedTime()
├── result_code.h             Qt 端錯誤碼
├── version.h                 版本與檔名常數
│
├── PPS2_0DevTool.json        設定檔（**不納入版本控制**，見下）
├── PPS2_0DevTool.example.json  設定檔範本（納入版本控制，憑證留空）
├── PPS2_0DevTool.pro         qmake 專案檔
├── requirements.txt          Python 第三方相依（requests）
│
├── resources.qrc             Qt 資源清單（應用程式圖示）
├── resources/icons/
│   ├── src/app_icon_original.png       來源圖（含白底，供重新產生用）
│   ├── app_icon_{16..256}.png          去背後的多尺寸圖（內嵌進執行檔）
│   └── PPS2_0DevTool.ico               多尺寸 ICO（給 RC_ICONS 用）
│
├── tools/
│   └── make_app_icon.py      圖示資產產生腳本（**不是**建置步驟）
│
├── scripts/
│   ├── _function_template.py 功能腳本範本 ← 複製這個開始寫新腳本
│   ├── script_io.py          信封處理
│   │
│   ├── single_building/      入口腳本依「功能」分組
│   │   ├── __init__.py       功能專屬：設定檔名、挑選的副檔名
│   │   ├── single_building_list_source.py       取得來源清單
│   │   ├── single_building_list_target.py       讀取設定
│   │   ├── single_building_modify_setting.py    寫入設定
│   │   └── single_building_recovery_setting.py  清空設定
│   │
│   ├── ai_analysis_gitlab_mr/
│   │   ├── __init__.py       功能專屬的契約：報告的標題常數與切段、憑證取得、
│   │   │                     分析結構的建構與驗證、出處、除錯檔
│   │   ├── ai_analysis_gitlab_mr_list_merge_requests.py  取得 MR 清單
│   │   ├── ai_analysis_gitlab_mr_description.py   1/5 取得 MR 描述
│   │   ├── ai_analysis_gitlab_mr_info.py          2/5 取得相關資訊（jira_key、mr_type）
│   │   ├── ai_analysis_gitlab_mr_summary.py       3/5 AI 分析
│   │   ├── ai_analysis_gitlab_mr_code_review.py   4/5 程式碼審閱（自 JIRA 附件）
│   │   ├── ai_analysis_gitlab_mr_merge_to_md.py   5/5 合併為 markdown
│   │   └── device/           各產品線自己的分析邏輯（見下面的 device 一節）
│   │       ├── __init__.py   解析 PPS_DEVICE 與種類、掃目錄、逐鉤子回退
│   │       ├── default/      未指定時用這一份，也是所有 device 的後備
│   │       │   └── <type>/   選用：某個種類專屬的 summary / merge_to_md
│   │       └── _template/    範本（底線開頭，不是 device）
│   │           └── _type_template/   種類目錄的範本
│   │
│   └── script_utils/         共用模組依「技術領域」分組
│       ├── logger.py         log（唯一設定 logging 的地方）
│       ├── system_utils.py   向作業系統要東西：環境變數、建立資料夾、
│       │                     依副檔名列檔案、暫存目錄、路徑轉 Windows 表示法
│       ├── file_utils.py     檔案內容：整檔讀寫、行號區間讀取與置換、
│       │                     尋找、複製、搬移、刪除、行式文字檔讀寫
│       ├── json_utils.py     JSON：讀檔、解析字串（可給預設值）、寫檔、序列化
│       ├── http_utils.py     REST 共用底層：session、逾時、重試、例外基底
│       ├── gitlab_utils.py   GitLab REST：通用呼叫、分頁、專案、分支、
│       │                     檔案內容、merge request
│       ├── jira_utils.py     Jira REST（Server/DC）：通用呼叫、分頁、JQL 搜尋、
│       │                     issue 查詢／建立／ensure、留言、描述更新、附件
│       └── ai_utils.py       AI 服務：提問、重試與退避、回覆解析與重問
│                             （為特定一家地端服務寫的，不是通用抽象）
│
└── openspec/                 規格與設計決策
    ├── specs/                現行行為契約（五個 capability）
    │   ├── app-shell/
    │   ├── script-execution/
    │   ├── script-envelope/
    │   ├── single-building/
    │   └── ai-analysis-gitlab-mr/
    └── changes/              進行中與已歸檔的變更
        └── archive/          已完成的變更（含當時的 proposal / design / tasks）
```

---

## 建置

**Windows（正式支援平台）**：Qt Creator + MinGW + Qt5 + qmake

```
開啟 PPS2_0DevTool.pro → 建置
```

**macOS**：只用來確認編得過（開發輔助，非支援平台）

```bash
qmake PPS2_0DevTool.pro && make
```

所有 Windows 專屬 API 都以 `#ifdef Q_OS_WIN` 隔離，兩邊都編得過。

### 執行前的準備

**設定檔與 `scripts/` 必須放在執行檔目錄旁**，否則會啟動失敗：

```
<執行檔目錄>/
├── PPS2_0DevTool.exe
├── PPS2_0DevTool.json     ← 缺少會跳訊息框後結束
└── scripts/               ← 設定檔中的相對腳本路徑以執行檔目錄為基準
```

設定檔缺少或格式錯誤時程式會直接結束，這是刻意的 —— 每個功能都必須從設定檔取得
執行 Python 的指令，帶著空設定啟動只會讓使用者在每個 tab 都撞牆。

執行環境還需要系統上有可用的 **Python 3**（啟動時會檢查）。

用到 GitLab 的功能還需要 **requests**（本專案唯一的第三方相依）：

```bash
<設定檔 Program 指定的那個 python> -m pip install -r requirements.txt
```

裝在哪個直譯器裡是重點 —— Qt 是用設定檔 `Function/<功能>/Program` 指定的直譯器去
啟動腳本的。裝錯地方的症狀是命令列跑得好好的、從工具裡跑卻失敗。沒裝時不會在匯入
階段爆掉，`gitlab_utils` 會延到真正呼叫時才拋出一則說得清楚的錯誤（若在匯入階段拋，
結果信封根本來不及產生，Qt 端只會顯示「腳本沒有回傳結果」）。

圖示不在這個清單裡 —— 它內嵌在執行檔內，不需要也不會去讀外部圖檔。

---

## 應用程式圖示

圖示內嵌於執行檔，套用在四個地方：

| 顯示位置 | 來源 |
|---|---|
| 主視窗標題列、Alt-Tab、工作列按鈕 | `main.cpp` 的 `setWindowIcon()`，讀 `:/icons/app_icon_*.png` |
| 系統匣 | 同上（`QWidget::windowIcon()` 未自訂時回傳應用程式圖示） |
| 對話框（含啟動失敗的錯誤訊息框） | 同上 |
| `PPS2_0DevTool.exe` 本身（檔案總管、捷徑、開始功能表） | `.pro` 的 `RC_ICONS`，連結期由 windres 寫進 PE 資源區段 |

七個尺寸（16 / 24 / 32 / 48 / 64 / 128 / 256）各自以獨立檔案加入 `QIcon`，
讓 Qt 依情境挑最接近的一張 —— 拿 256x256 即時縮到 16x16，貓臉的條紋與墨鏡
會糊成一團。

### 換圖

圖示是編進執行檔的，**換圖一律要重新建置**（exe 本身的檔案圖示尤其如此：
執行中的程式無法改變自己在磁碟上的圖示資源）。步驟：

```bash
# 1. 換掉來源圖（256x256 PNG）
cp 新圖.png resources/icons/src/app_icon_original.png

# 2. 重新產生七個尺寸與 .ico
pip install pillow
python3 tools/make_app_icon.py

# 3. 重新建置
```

`tools/make_app_icon.py` **不是建置步驟** —— 產物已提交進 repo，Windows 端
拿到專案直接用 Qt Creator 開啟即可建置，不需要安裝 Python 影像套件。

腳本會把接近純白的方形背景去掉。它用的是「從影像四邊做連通區域填充」，
不是「夠亮就設為透明」的全域門檻 —— 後者會把圖案內部的白色高光打成透明
破洞，在深色工作列上直接漏底。換圖後值得把產出的 16x16 疊在黑底與白底上
各看一次：白邊與破洞在這兩個背景上一眼可見。

Windows 更新執行檔後，檔案總管有時仍顯示舊圖示，那是系統的圖示快取，
不是建置失敗 —— 把執行檔複製到新路徑再看即可確認。

---

## 功能：Single Building

從來源目錄挑出要處理的 `.cpp` 檔案，把選擇保存成一份設定。

```
+-[ Single Building ]---------------------------------------------------------+
|  +-- Source -------------------+          +-- Target -------------------+   |
|  | Filter [_______] [ Clear ]  |          |                  [ Clear ]  |   |
|  | +-------------------------+ |          | +-------------------------+ |   |
|  | |   來源池（唯讀）          | | [  ->  ] | |  結果集（可增可減）        | |   |
|  | |   來源路徑該層的 *.cpp    | | [  <-  ] | |  暫存設定檔的鏡子          | |   |
|  | +-------------------------+ |          | +-------------------------+ |   |
|  +-----------------------------+          +-----------------------------+   |
|                                [ Recovery Setting ]  [ Modify Setting ]     |
+-----------------------------------------------------------------------------+
```

### 資料流

真正的狀態儲存處是一個暫存 txt，四支腳本都繞著它轉：

```
   來源路徑（目錄）
        |  list_source        掃描該層的 *.cpp（不遞迴）
        v
   Source list  --[ -> ]-->  Target list
                 <--[ <- ]
                                  |          ^
                  modify_setting  |          |  list_target
                  寫入絕對路徑     v          |  讀出絕對路徑
                            +---------------------------+
                            |  %TEMP%/PPS2_0DevTool_     |
                            |  single_building.txt       |   <== 設定本體
                            +---------------------------+
                                       ^
                                       |  recovery_setting
                                       |  清空後回讀（結果必為空）
```

清單顯示的是**檔名**，設定檔存的是**絕對路徑** —— 完整路徑前綴完全相同又很長，
顯示出來只會撐爆清單寬度，但設定必須指向確切的檔案。

### 行為

| 觸發 | 執行 |
|---|---|
| 進入分頁（含啟動時本分頁即為當前分頁） | `list_source` → `list_target` |
| 進入分頁但來源路徑為空 | 只跑 `list_target`（不算失敗、不跳錯誤框） |
| **在本分頁**修改來源路徑 | `recovery_setting`（清空設定）→ `list_source` |
| 在**別的分頁**修改來源路徑 | 不受影響 |
| `->` / `<-` / 兩顆 Clear | 純畫面操作，不碰設定檔 |
| Modify Setting | 寫入設定檔 |
| Recovery Setting | 先跳確認框，再清空設定檔並回讀 |

- 過濾**區分**大小寫、排序**不分**大小寫 —— 過濾是使用者主動輸入，排序是被動看到的結果
- 排序為自然排序：`a2.cpp` 排在 `a10.cpp` 之前
- `->` 是複製，來源清單不會變短；已存在的項目靜默略過
- 過濾文字一有變動就清空來源的選取 —— 否則按下 `->` 會送出畫面上看不到的項目

### 已知行為

**未按 Modify Setting 的選擇，在切換分頁後會遺失。** 進入分頁時結果清單一律
自設定檔重新填入。要保留就先按 Modify Setting。

**暫存設定檔可能自己消失。** 它放在系統暫存目錄，Windows 的磁碟清理與「儲存空間
感知」會清理該處。若日後需要跨重啟保留，改 `scripts/single_building/__init__.py`
裡的 `setting_file_path()` 即可（`%LOCALAPPDATA%` 是正確的去處）。

---

## 功能：AI Analysis GitLab MR

在工具裡瀏覽某個 GitLab 專案的 Merge Request，挑一筆交給 AI 分析，結果以
markdown 呈現在結果視窗。

> **目前的狀態**：五個步驟都已連上真正的來源。第 1、2 步連 GitLab；第 3 步連
> GitLab（取差異）、JIRA（取議題內容）與 AI 服務；第 4 步連 JIRA（取附件）；
> 第 5 步沒有外部依賴。
>
> 沒設定 AI 端點時第 3 步不會失敗，而是產出替代內容，並在首行言明未經過 AI ——
> 開發期還沒有端點時整條流程仍要能跑完才驗得到。

> **第 4 步的 Windows 實機驗收尚未完成，change 已先行擱置。**
> 腳本側已在 Linux 上完整驗過：五步以命令列串接跑完一次（對著替身 GitLab 與 JIRA 走
> 真正的 HTTP）、附件選取、三類失敗、編碼、大小上限、貼回描述不累積，Qt 也以
> `qmake && make` 編過且零警告。**未驗證的是 Qt 那一側的三件事**：勾選除錯時工作目錄
> 的內容、未勾選時不留檔、以及缺設定鍵時錯誤訊息框的呈現。逐項驗法見
> [`openspec/changes/add-jira-code-review-report/tasks.md`](openspec/changes/add-jira-code-review-report/tasks.md)
> 第 6 節的 6.3～6.5。
>
> 其中 6.3 有個陷阱值得先知道：判定要看**附件檔名**這種「只有真的取得才會出現的字串」，
> 不能只看流程成不成功 —— Qt 沒轉送 `jira_key` 時會靜默走「沒有這一段」，與正常跑完
> 長得一模一樣（這個降級行為已在命令列側實際驗證過）。

### 畫面

```
+-- AI Mode -------------+  +-- Merge Requests -------------------+
| [Open AI          v]   |  | ( ) Manual Merge Request ID [____]  |
+-- Analysis Parameter --+  | (*) Get Merge Requests              |
| [x] Add Debug ...file  |  |  +-- Merge Request Parameter ----+  |
| Save path [____] [...] |  |  | [x]Only Open [x]Created after |  |
|  +-- JIRA Key -------+ |  |  |   [ 7] days            [refr] |  |
|  | ( )None ( )Manual | |  |  +-------------------------------+  |
|  |          (*)Auto  | |  |  MR |Status| Title  |Author|Created |
|  +-------------------+ |  |  ---+------+--------+------+------- |
+-- Repository ----------+  |                                     |
| Jonas_Huang/lw-os      |  +-------------------------------------+
| Jonas_Huang/Test_Sub.. |                        [ AI Analysis ]  
+------------------------+
```

分析單位是**一個 repo 的一個 MR** —— 兩個清單都是單選。

### 行為

**進入這個分頁不執行任何腳本。** Repository 清單來自設定檔，Merge Request 清單
一律由使用者按重新整理才取得。與 Single Building 的「進入即載入」相反：這裡每次
載入都是一次網路請求，照做的話每次切到這個分頁都會被一個互斥的對話框擋住。

**切換 repository 或改動查詢條件會清空 MR 清單。** 否則畫面上顯示的是前一個
repository 的 MR，而按下 AI Analysis 時採用的卻是當前選取的那一個。

**`AI Analysis` 在條件不足時停用，且不說明原因** —— 與 Single Building 的既有
作法一致。條件是：選了 repository、指定了 MR、（勾了除錯時）存放目錄非空、
（選了手動 JIRA 時）key 非空。

**手動輸入的 MR 編號會自我修正。** 貼上 `!123` 或一整條 MR 網址都會被收斂成
編號 —— 使用者最自然的動作就是從瀏覽器複製。

### 分析流程

按下 `AI Analysis` 啟動一條**固定五步**的流程：

| 步 | 腳本 | 產物 |
|---|---|---|
| 1 | `..._description.py` | MR 描述 |
| 2 | `..._info.py` | `jira_key` 與 `mr_type`（自行連 GitLab 取 MR 一次，兩個鉤子各自抽） |
| 3 | `..._summary.py` | AI 分析結果 |
| 4 | `..._code_review.py` | 風險評估總表（自 JIRA 議題的附件擷取） |
| 5 | `..._merge_to_md.py` | 合併後的 markdown |

**五步全部執行，Qt 端不跳過任何一步。**「要不要真的做事」由腳本看參數決定
（例如第 4 步收到的 `jira_key` 為空、或 `jira_state` 不是 `ok` 時就不發任何請求、
回報成功且不落檔）。這是為了讓同一批腳本能被 CI/CD 的 shell 直接串接 —— 分支若寫在
Qt 端，CI 那側就成為第二份編排實作，兩份必然漂移。

**第 4 步刻意沒有「要不要取」的布林開關。** 由 `jira_key` 與 `jira_state` 兩個值同時
承載「要不要做」與「對誰做」，就不會出現「開關為真但沒有 key」這種自相矛盾的狀態。
`jira_state` 來自第 3 步 —— key 的有效性是那個 device 的政策、由它的鉤子判定，Qt 只是
原樣轉送，不重判。

**腳本路徑固定寫死在 C++**，不取自任何步驟的回傳資料。哪一段運算因 device 而異，
由環境變數 `PPS_DEVICE` 決定（見下面的 device 一節），同樣不取自回傳資料。

**「種類」是這條規則的明確例外。** 它由第 2 步從 MR 解出來（多半是標題），再決定第 3、5
步用哪一份鉤子 —— 也就是說，MR 標題會影響載入哪個模組。範圍是收死的：名字必須通過
`^[a-z_][a-z0-9_]*$`（擋掉路徑穿越），而且必須對應到一個**已經部署在該 device 底下**的
目錄。所以標題只能在既有的選項之間挑，帶不進任何新的程式碼，也指不到別的位置。

**任一步失敗即停**，以一個錯誤訊息框指出第幾步與該步腳本寫的原因，畫面不變。

### 報告的版面

步驟 5 產出的 markdown 就是使用者在結果視窗看到的東西，也是可以貼進 MR 討論串的
東西。版面固定如下：

````markdown
# Original Description

<GitLab 上那份描述的內容>

# AI 分析結果

## Summary

<總覽>

## Code Changes

### 1. `cpp/test.cpp`

- <標題>
  <理由>
  <details>

  ```diff
  @@ -12,7 +12,7 @@
  -    retry = 3
  +    retry = 10
  ```
  </details>

# Code Review 報告

>日期: 2026-09-10
>作者: Jonas
>連結: [CodeReview_20260910_092900.md](https://jira.example.com/secure/attachment/12345/CodeReview_20260910_092900.md)

## 風險評估表

| 類別 | 風險等級 | 數量 |
|---|---|---|
| 記憶體 | 高 | 2 |

---

Script: v1.0 | Device: ssd v1.2 | Type: bug | AI Mode: Open AI | JIRA: PPS-1234
PPS 2.0 DevTool v2.0.0
````

幾個不是隨手決定的地方：

**三個 `#` 標題都由步驟 5 寫出**，步驟 1 與步驟 4 的產物都不冠標題。標題屬於
報告不屬於描述 —— 冠在步驟 1 的產物上，那一行會跟著報告被貼回描述，下一輪再讀進來；
而步驟 4 自帶標題的話，它無從知道自己會被放在哪一層。

**`# Code Review 報告` 與 `# AI 分析結果` 同層。** AI 分析那一段的**內容**用的是 `##`
（`## Summary`、`## Code Changes`），所以 code review 若也用 `##`，在畫面上就會跟那些
內容並列，讀起來像是分析的一部分 —— 而它在語意上與分析並列，不從屬於它。

**Code Review 那一段刻意只放總表。** 全文留在 JIRA 上那份附件裡，靠 `>連結:` 那一行
回去看。三行資訊裡值為空的那一行整行不印；日期只取到日，不做時區換算（印出的就是
上傳者當時看到的那一天）。

**取不到總表時那一段仍然出現**，內容換成一行 `⚠️` 訊息，而日期／作者／連結**照樣印**
—— 那時連結的價值最高，讀者點進去就能自己看全文。只有「沒有 JIRA key」「key 無效」
「議題上沒有符合的附件」三種情況才整段不出現，因為那些是「這筆本來就沒有」而不是
「取失敗了」。

**搜尋用與渲染用是三個各自獨立的常數**（都在 `ai_analysis_gitlab_mr/__init__.py`）：

| 常數 | 用途 | device 可覆寫 |
|---|---|---|
| `CODE_REVIEW_SOURCE_HEADING` | 在**附件那份文件**裡找總表那一節（預設 `## 風險評估表總表`） | ✅ |
| `CODE_REVIEW_HEADING` | 寫進**報告**的段落標題 | ❌ |
| `CODE_REVIEW_TABLE_HEADING` | 寫進**報告**的總表小標題 | ❌ |

不合成一份是刻意的：改我們報告的小標題不該影響去別人文件裡搜尋什麼，反之亦然。
這與 `AI_HEADING` 剛好相反 —— 那一個同時是「寫出去」與「切回來」的同一個邊界，所以
**必須**只有一份來源。

**`# AI 分析結果` 同時是切段的邊界。** 步驟 1 靠它把上一輪的分析從描述裡切掉，所以
「寫出去的字串」與「切掉用的字串」只有一份來源（`__init__.py` 的 `AI_HEADING`），
比對式也是由它導出。改標題只要改那一行 —— 但既有描述裡若還留著舊標題就切不掉了，
代價與補救見 design.md 決策二十四。

**每次執行全部重新生成，只有原始描述被保留。** 把整份報告貼回 MR 描述再跑一次，
舊的分析與出處會一起被切掉重產，不會累積。

**末尾的出處永遠都在。** 報告脫離產生它的環境之後，那是唯一能回答「這是哪一版腳本
跑出來的」的東西。第二行依環境而定：CI 裡是 pipeline 與 commit（連回 GitLab），
從工具跑是工具名稱與版本。改了報告的產出方式，請把 `__init__.py` 的 `SCRIPT_VERSION`
往上加 —— 沒有任何機制強迫，忘了加新舊報告就分不出來。

**diff 收在 `<details>` 裡。** 一筆 finding 的 diff 可能幾十行，攤開會把報告的可讀性
吃掉。`<details>` 之後那個空行是必要的，少了它 GitLab 不會把裡面當 markdown 解析。

> 結果視窗是 `QPlainTextEdit`，**不渲染 markdown** —— `<details>` 與連結在工具裡都是
> 原樣的文字，收合也不會發生。這個排版是為了「貼到 GitLab」那一側。

### `03_summary.json` 的格式

步驟 3 的產物是結構，不是排好版的文字；渲染由步驟 5 負責。

````json
{
  "schema_version": 4,
  "analysis": {
    "model": "gpt-4o",
    "mr_type": "bug",
    "jira_key": "PPS-1234",
    "jira_state": "ok",
    "jira_url": "https://jira.example.com/browse/PPS-1234",
    "overview": "本次修改把重試上限從 3 調高到 10。",
    "mrDiff": {
      "cpp/test.cpp": [
        { "title": "...", "reason": "...", "diffCode": "@@ -12,7 +12,7 @@..." }
      ]
    }
  }
}
````

- 每個檔案**直接對一個 finding 清單**，中間沒有包一層。要講整個檔案就放清單的第一筆、
  不給 `diffCode`
- `jira_state` 是 `ok` / `none` / `invalid` 三選一。`invalid` 時 `jira_key` 留的是
  **被拒絕的原值**，報告會印成 `JIRA: WIP (invalid)` —— 一眼看出標題的第一個方括號
  放錯了東西
- `model` 留在資料裡供其他消費者使用，**不進報告**
- `mr_type` 是這一筆的種類，決定步驟 5 用哪一份版面；沒有種類時是空字串。它由**入口
  腳本蓋章**，device 的鉤子不必填（填了也會被覆蓋）
- 某個檔案的清單為空時，該檔案整個不出現，編號也只算實際出現的檔案
- `schema_version` 比對時寬鬆：`4`、`"4"`、`"4.0"` 是同一個版本；`"4.5"` 與 `true` 不收
- **讀得懂版本 3 與 4**（寫出去的一律是 4）。版本 3 少的就是 `mr_type`，讀法是「視為
  沒有種類」—— 那不是猜測，是一條知道的讀法。實際的好處是開發時常常拿昨天的
  `03_summary.json` 單獨重跑步驟 5 看版面，只認最新版會讓那個迴路每次改版就斷一次
- 建構用 `ai_analysis_gitlab_mr` 的 `finding()` 與 `analysis_body()`，不要自己寫
  dict literal —— 欄位名散在寫入側與讀取側兩邊，改名漏一邊就是安靜地少一段
- `schema_version` **由入口腳本蓋章**，device 的鉤子只回 `analysis` 的內容。入口收到
  之後會立刻驗證，不符合就在**產生它的那一步**失敗，訊息點名是哪個 device

舊的 `{"summary": "一段文字"}` 仍然收得下，渲染時原樣接上。

### `04_code_review.json` 的格式

步驟 4 的產物同樣是結構、不是排好版的文字，渲染由步驟 5 負責 —— 與 `03_summary.json`
同一個理由。這裡多了一層必要性：報告要印出附件的日期、作者與連結，而那三個值**只有
步驟 4 拿得到**（步驟 5 收到的只是一個檔案路徑）。

```json
{
  "schema_version": 1,
  "code_review": {
    "filename": "CodeReview_20260910_092900.md",
    "created": "2026-09-10T09:29:00.000+0800",
    "author": "Jonas",
    "url": "https://jira.example.com/secure/attachment/12345/CodeReview_...md",
    "risk_table": "| 類別 | 風險等級 | 數量 |\n|---|---|---|\n| 記憶體 | 高 | 2 |",
    "error": ""
  }
}
```

- 六個欄位都是字串。空字串合法（代表沒有那一項），但**型別不對就明確失敗** —— 一個
  dict 被 `str()` 起來會變成 `{'a': 1}` 然後原樣印進報告
- `risk_table` 是**原樣**的表格，不對齊、不排序、不改欄序。欄位名稱因 device 而異，
  任何正規化都可能弄壞某一個 device 的表格
- `error` 有值時 `risk_table` 通常是空的，但**前四個欄位照樣填** —— 報告要靠那三行
  讓讀者自己點連結去看全文
- `schema_version` 由**入口腳本蓋章**，與 `ANALYSIS_SCHEMA_VERSION` **各自獨立編號**
  （兩者是不同的產物，共用一個號碼會讓其中一邊改版莫名其妙地讓另一邊的舊檔失效）
- 比對與 `03_summary.json` 一樣寬鬆：`1` 與 `"1"` 是同一個版本，`"1.5"` 與 `true` 不收
- 建構用 `code_review_body()` 與 `wrap_code_review()`，不要自己寫 dict literal
- 這一步取不到東西時**整份檔案不會產生**（不是產生一份空的）。Qt 的
  `insertArtifactPath()` 檔案不存在就不放那個鍵，步驟 5 因此整段略過


### 呼叫 AI

`script_utils/ai_utils.py` 負責「問與等」。**組 prompt 不在它裡面** —— 那是各條產品線
要自己掌握的東西，收進共用模組等於把 device 機制的意義抵消掉。

```python
ask(api_url, prompt, history=None, file_ids=None, api_key="",
    timeout=120, retries=3, on_retry=None, verify_ssl=True,
    parse=None, reask=0)

ask_json(api_url, prompt, require=(), reask=1, **kwargs)
split_share_code(api_url) -> (url, share_code)
as_json(text, require=())   strip_fence(text)
```

**這是為特定一家地端服務寫的客戶端，不是通用的多供應商抽象。** 請求形狀集中在
`_build_payload()`、回應取值在 `_extract_reply()`、認證標頭在 `_headers()`。換服務
改這三支，重試那一段完全不用碰。

**shareCode 黏在 `Api_URL` 尾端**，以冒號分隔：

```
https://主機:8443/端點:SHARE_CODE
```

拆解時**只有最後一個斜線之後的冒號才算分隔符** —— 位址本身至少有一個冒號
（`https:`），還可能有連接埠，切錯會把整個路徑當成 shareCode 送出去，而伺服器只回
一個看不出原因的 400。沒帶 shareCode 時直接失敗並講出正確寫法。

設定檔的 `Model` **不進請求**（模型由 shareCode 那端決定），它只印在報告的出處那一行，
所以也不是必填。

#### 重試的界線

重點不在重試幾次，在**哪些不重試**：

| 情況 | 處理 |
|---|---|
| 逾時、連線中斷、限流、5xx | 重試（限流優先照 `Retry-After` 指定的秒數等） |
| 認證失敗、端點不存在、prompt 過長、**憑證驗證失敗** | **不重試** |
| 回應形狀與預期不符 | **不重試** |

「值不值得重試」由**拋出錯誤的那一處**決定，不由重試邏輯從狀態碼反推 —— 連線中斷與
「回應欄位不對」都沒有狀態碼，卻該分在兩邊。

`Retry-After` 指定的秒數超過上限（30 秒）時直接失敗，不照它等：一個卡五分鐘、最後仍然
失敗的對話框比立刻說明白糟得多。

逾時預設 120 秒，不沿用 `http_utils` 的 30 秒 —— 秒級逾時會把正常的長回答判成失敗，
然後重試，結果是等更久而且每次都計費。

### 改 prompt

Prompt 住在 device 的 `summary.py`，可改的東西集中在最上面四個字串常數：

| 常數 | 內容 | 改了要連動嗎 |
|---|---|---|
| `ROLE_PROMPT` | 角色與語氣，放在 prompt 最前面 | 不用 |
| `PROMPT_TEMPLATE` | 版面與各段順序 | 不用 |
| `JIRA_TEMPLATE` | JIRA 那一段（沒 issue 時整段不出現） | 不用 |
| `OUTPUT_SPEC` | 要求 AI 回什麼格式 | **要**，見下 |

`PROMPT_TEMPLATE` 可用的佔位符：`{role}` `{repo}` `{mr_iid}` `{description}` `{jira}`
`{diff}` `{output_spec}`。順序隨你排，不要的整段拿掉即可 —— `build_prompt()` 備妥的值
比樣板用到的多，`format()` 會忽略沒用到的。

> **⚠️ 樣板裡的大括號全部會被當成佔位符。** prompt 含 JSON 範例、C 片段或 `{變數}`
> 時要疊成兩層（`{{` `}}`），否則填值會失敗。**更省事的做法是搬進 `OUTPUT_SPEC`**
> —— 它是被代入的值、不是樣板，裡面的大括號原樣輸出。
>
> 真的寫壞了訊息會指名：`PROMPT_TEMPLATE 裡有認不得的佔位符 {"summary"}。可用的是：
> description、diff、jira、mr_iid、output_spec、repo、role。…請寫成兩層：{{ 與 }}。`

`build_prompt(inputs)` 可以單獨呼叫，**不打 AI 就能把 prompt 印出來看**：

```python
from ai_analysis_gitlab_mr.device import load_hook
print(load_hook('summary')[0].build_prompt({
    "repo": "group/proj", "mr_iid": "7", "description": "（假的）",
    "mr_diff": open("sample.diff", encoding="utf-8").read(),
    "jira_issue": None,
}))
```

#### AI 回覆的格式

`OUTPUT_SPEC` 要求什麼、`parse_reply()` 就讀什麼，**兩者是同一件事的兩面**，改了要
一起改。目前：

```json
{
  "summary": "整體變更的摘要",
  "code_changes": {
    "檔案路徑": [
      { "title": "...", "reason": "...", "hunkHeader": "相關的那幾行 diff" }
    ]
  }
}
```

對應到產出：`summary` → `overview`、`code_changes[檔名]` → `mrDiff[檔名]`、
`hunkHeader` → `diffCode`。兩邊各自命名是刻意的 —— 回覆格式是那個服務的事，產出格式
是報告的事。

`code_changes` **物件與「單鍵物件的陣列」兩種都收**。規格有歧義的時候模型也會兩種都產，
只認一種的話另一種會變成「缺少必要欄位」，而那訊息指不到真正的原因。

`hunkHeader` 即使已經交代不要加圍籬，解析時仍會**再剝一次** —— 模型對否定指令的服從度
不高，而多餘的圍籬會落在報告自己的 ```` ```diff ```` 裡面，把 markdown 弄壞，症狀出現
在報告上、離這裡很遠。

#### 重問

回覆不符預期時會在 prompt 尾端追加「只回覆結果本身」重問一次（`reask=1`）。

**JSON 解析與結構檢查要串成同一個 `parse` 傳給 `ask()`**，不能分成前後兩段 —— 分開寫
的話第二段跑在 `ask()` 之外，重問永遠觸發不到，而「JSON 合法但結構不對」恰好是模型最
常見的失手方式。

### 素材怎麼來

第 3 步在呼叫鉤子**之前**把素材備好，鉤子拿到的是現成的內容：

| inputs | 內容 |
|---|---|
| `mr_diff` | unified diff 純文字，上限 `MAX_PROMPT_DIFF_BYTES`（目前 120000），超過截斷並註明 |
| `fetch_jira` | `fetch_jira(key)` → dict 或 None，**函式而不是內容**，見下 |
| `progress` | `progress(text)`，在那個固定尺寸對話框上顯示一行字 |
| `debug_write` | `debug_write(檔名, 內容)`，除錯沒開時什麼都不做 |

連線、憑證、錯誤分類都留在入口 —— 改 prompt 的人不該為了一句話面對 HTTP。連線失敗也
因此不會被包裝成「device 的 summary.py 執行失敗」，那會把連線問題講成腳本寫壞了。

**JIRA 是函式而不是現成內容**，因為「key 有沒有效」是 device 的政策，入口不認得。先抓
的話，`[WIP]`、`[Draft]` 這種從標題方括號抽出來的字串每次都會白打一趟 JIRA 換回 404。
鉤子判定有效之後再呼叫它。查不到不會讓流程失敗，prompt 少那一段而已。

### device：讓每條產品線有自己的分析邏輯

一個 MR 該怎麼分析，會因為它屬於哪一條產品線而不同 —— SD 與 SSD 要問 AI 的問題不一樣，
報告要怎麼排也不一樣。所以流程中**三個步驟**的業務運算可以按 device 客製：

| 步驟 | 鉤子 | device 決定 | 因種類而異 |
|---|---|---|---|
| 2 | `jira_key.py` | 怎麼從 MR 抽出 JIRA key | 否 |
| 2 | `mr_type.py` | 怎麼從 MR 抽出**種類** | 否 |
| 3 | `summary.py` | 問 AI 什麼、怎麼解析、組出什麼分析內容 | **是** |
| 5 | `merge_to_md.py` | AI 分析那一段的版面 | **是** |

步驟 1（取得描述）不因 device 而異。

步驟 4（程式碼審閱）的**運算與版面**也不因 device 而異 —— 它只讀一個 device **宣告**：

| 宣告 | device 決定 |
|---|---|
| `CODE_REVIEW_SOURCE_HEADING` | 在附件那份文件裡找哪一節才找得到總表 |

**那是一個宣告，不是第五個鉤子。** 步驟 4 不會載入或執行任何 device 的程式碼，所以它
不會出現「哪一個 device 的鉤子壞了」這類失敗，擷取的演算法也只有一份、不會每個 device
各長一份慢慢漂移。會因產品線而異的是**別人的工具產出什麼格式**，不是本工具的處理方式。

「種類」是第二個軸，見下面的 type 一節。前兩支不因種類而異，因為它們在種類被決定
**之前**執行 —— `mr_type.py` 就是決定它的那一支。

```
scripts/ai_analysis_gitlab_mr/device/
  default/          未指定時用這一份，也是所有 device 的後備
  _template/        範本（底線開頭，不是 device）
    _type_template/ 種類目錄的範本
  ssd/              只放想覆寫的鉤子
    bug/            一個種類，一樣只放想覆寫的
```

**哪一個 device 由環境變數 `PPS_DEVICE` 決定。** 工具端由 Qt 從設定檔的 `PPS_Device`
注入，CI 由 runner 自行設定 —— 腳本端只有一條取值路徑，兩個呼叫端對它來說長得一模一樣
（跟憑證同一個作法）。

```
PPS_DEVICE 未設定或空白  ->  default
PPS_DEVICE = ssd         ->  device/ssd/ 必須存在
PPS_DEVICE = sdd         ->  失敗，訊息列出目前認得哪些
```

**未知的 device 是錯誤，不是退回 default。** 指定一個不存在的名字代表打錯字或忘記部署，
靜默改用通用邏輯會產出一份用錯邏輯、而每一步都回報成功的報告。

**回退是逐鉤子的，不是逐 device。** `device/ssd/` 只放 `merge_to_md.py` 是合法的，
缺的鉤子自動用 `default` 的 —— 只想改報告版面的 device 不必複製一整支 summary，
而那份複本會跟著 default 漂移。

認得哪些 device 由**掃目錄**決定，沒有註冊表：放一個目錄進去就是新增一個 device。

### type：同一個 device 底下再分種類

一筆修 bug 的 MR 與一筆新增測試案例的 MR，要問 AI 的問題不一樣，報告也不該長得一樣。
所以 `summary.py` 與 `merge_to_md.py` 可以再依**種類**分開 —— 以子目錄表示：

```
device/ssd/
  __init__.py       VERSION、STRICT_TYPE
  mr_type.py        怎麼從 MR 抽出種類
  bug/
    summary.py      Bug 專用的 prompt，版面沿用 ssd 或 default 的
  newtestcase/
    summary.py
    merge_to_md.py  這個種類兩支都覆寫
```

**種類不需要 `__init__.py`**（namespace package），放一個目錄進去字面上就是新增一個
種類。認得哪些種類同樣由掃目錄決定，沒有註冊表。

#### 誰決定種類

由該 device 的 `mr_type.py` 從 MR 抽出來，規則各自決定 —— SSD 可能看標題第二個方括號、
SD 看第三個：

```
mod:[PPS-1234][Bug] 修正重試上限
    ^^^^^^^^^^ jira_key.py 取這個
              ^^^^^ ssd/mr_type.py 取這個 -> "Bug" -> 轉小寫 -> bug/
```

抽出來的字一律轉小寫比對，所以 `[NewTestCase]` 對應到 `newtestcase/`。鉤子也可以做
**映射**：標題寫 `[FW-Update]`、回 `"fw_update"`，目錄名維持合法識別字。

它與 `jira_key.py` 在**同一步、同一次 GitLab 取得**裡跑完，不會多一次連線。

> ⚠️ 標題格式與 default 不同的 device，`jira_key.py` 與 `mr_type.py` **通常要一起寫**。
> 只寫一支的話另一支會沿用 default 的規則，安靜地抽到錯的東西 —— 症狀是報告印出
> `JIRA: Alpha (invalid)`，看得見，但要看報告才看得見。

#### 解析鏈：種類只在自己的 device 之內

```
  <device>/<type>/   ->   <device>/   ->   default/
```

例如 `PPS_DEVICE=ssd`、種類 `bug`：

| 鉤子 | 找的順序 | 上面那個例子的結果 |
|---|---|---|
| `summary` | `ssd/bug/` → `ssd/` → `default/` | `ssd/bug/summary.py` |
| `merge_to_md` | `ssd/bug/` → `ssd/` → `default/` | `default/merge_to_md.py` |

**不會去找 `default/bug/`。** 各 device 的種類字彙是各自演化的 —— SD 的 `tool` 與
SSD 的 `tool` 不保證是同一件事，跨過去取用就是套上另一條產品線的邏輯，而每一步都回報
成功。少了那一段還有一個好處：**沒有優先序需要裁決**。四段的話就得回答「我的通用版
與別人的種類版誰先」，而兩種答案都講得通。

真的要共用就**明著 import**，不要靠回退：

```python
# device/ssd/bug/summary.py
from ai_analysis_gitlab_mr.device.default.bug import summary as base
```

#### 認不得的種類 —— 與 device 相反

| | 未知時 | 為什麼 |
|---|---|---|
| **device** | **報錯** | 名字來自設定檔，打錯是操作者的責任。靜默改用通用邏輯會產出一份用錯邏輯、每一步卻都回報成功的報告 |
| **type** | **回退** | 名字來自 MR 標題，是任何能開 MR 的人打的字。為了一個沒照約定的標題讓整份分析做不出來，等於把工具的可用性綁在別人的打字習慣上 |

抽不到、名稱不合法（`[緊急]`、`[bug fix]`）、或這個 device 沒有那個目錄，三者都走回退。

要改成報錯，在該 device 的 `__init__.py` 宣告：

```python
VERSION = "1.2"
STRICT_TYPE = True
```

- 未宣告視為 `False`。它**不是必填** —— 設成必填會讓每一個既有的 device 立刻壞掉
- 必須寫成 `True` / `False`，不要加引號。字串 `"false"` 在 Python 裡是真值，寫成那樣會
  直接報錯而不是安靜地變嚴格
- **失敗發生在步驟 2**，也就是在任何 AI 花費之前。標題打錯不該先付一次錢才被告知
- 兩種情況的訊息分開（下一步不同）：

  ```
  這筆 Merge Request 沒有宣告 type
  device ssd 認不得 type：refactor    目前認得的是：bug、newtestcase
  ```

- **只管種類本身認不認得，不要求種類目錄放齊鉤子。** `bug/` 底下只有 `summary.py` 時，
  `merge_to_md` 照常回退，即使 `STRICT_TYPE = True`。否則開一個種類就得放齊四支

#### 種類怎麼傳下去

```
02_mr_info.json   { "jira_key": "PPS-1234", "mr_type": "bug" }
      |
      |  Qt 轉送（case 2 那一行）
      v
03_summary.json   { "schema_version": 4, "analysis": { "mr_type": "bug", ... } }
                                                            |
                                                            |  步驟 5 讀這份檔案
                                                            v
                                                      挑 merge_to_md
```

步驟 5 從**產物**讀而不是由 Qt 再轉送一次：Qt 只需要改一行，而且種類被記進產物，可以
印在報告出處（`Type: bug`），也留給其他消費者。種類由**入口腳本蓋章**，鉤子不填 ——
與 `schema_version` 同一個理由，讓鉤子填遲早有人複製範本時忘記。

### 新增一個 device

複製範本，改成你的 device 名稱：

```
cp -r scripts/ai_analysis_gitlab_mr/device/_template scripts/ai_analysis_gitlab_mr/device/ssd
```

**目錄名就是 device 名，而它會被當成模組名 import**，所以必須是合法的 Python 識別字：
小寫英數與底線、不以數字開頭。`ssd_gen4` 可以，`ssd-gen4` 不行。比對時不分大小寫，
設定檔寫 `SSD` 也找得到 `ssd`。

四個鉤子都是選用的，只放你要覆寫的；要再依種類分開就多開子目錄（見上面的 type 一節）。

但 `__init__.py` 的 `VERSION` **一定要有** —— 沒宣告會直接失敗。那個版本會印在報告末尾
（`Device: ssd v1.2`），**改了產出方式就把它往上加**；不加的話，用舊邏輯與新邏輯產生的
兩份報告會帶同一個版本號。

`__init__.py` 裡還有哪些可宣告的（目前是 `STRICT_TYPE` 與 `CODE_REVIEW_SOURCE_HEADING`），
範本已經以註解列好，不必翻文件。兩者都是選填，未宣告就落到預設值 —— 所以 `default/`
刻意兩個都不宣告（在那裡重複一次預設值，日後改預設值就有兩個地方要改）。

寫鉤子時請用這些共用函式，不要自己重寫：

| | |
|---|---|
| `contract.plain(value)` | `None` 與非字串收斂成字串。不用的話報告會印出 `None` |
| `contract.fence_for(code)` | 算程式碼圍籬的長度 |
| `contract.finding(...)` / `contract.analysis_body(...)` | 組分析結構 |
| `contract.jira_url(key)` | 組 JIRA 網址 |
| `contract.MAX_FINDING_DIFF_BYTES` | 單筆 diff 的位元組上限 |
| `contract.ai_credentials(inputs)` | 取出 AI 端點、金鑰與模型名 |
| `contract.ai_verify_ssl()` | 要不要驗 TLS 憑證（預設否） |
| `ai_utils.ask(...)` / `ask_json(...)` | 問 AI，含重試與重問 |
| `ai_utils.as_json(text)` / `strip_fence(text)` | 解析回覆、剝 markdown 圍籬 |

`fence_for()` 特別重要：寫死三個反引號的話，內容本身含反引號的 diff（改到 markdown 檔
就會）會讓程式碼區塊提前結束，而報告仍然「成功」產出。

**`# AI 分析結果` 那一行不歸 device 管。** `merge_to_md` 的鉤子只回傳「那個標題底下的
內容」，標題本身、原始描述那一段、分隔線與末尾的出處都由入口腳本寫出。原因是那一行
同時是下一輪切出原始描述的邊界 —— 某個 device 把它寫成別的字，下一輪就找不到邊界，
整份舊報告被當成原始描述，於是每跑一次疊一段，而每一步都回報成功。

> **`device/default/` 每次建置會被覆蓋。** 它在 repo 裡，而 `scripts/` 的複製是無條件
> 覆蓋。要客製就**新增自己的目錄**，不要改 default —— 你自己加的目錄因為 repo 裡沒有
> 同名檔案，不會被覆蓋也不會被刪除。

開發流程是：在執行檔旁的 `scripts/ai_analysis_gitlab_mr/device/` 寫、按按鈕測（每一步
都是獨立的 Python 行程，改完立刻生效，不必重建），完成後把目錄提交進 repo —— CI 也就
跟著有了。


### 除錯分析檔

勾選 `Add Debug Analysis file` 時，Qt 在流程啟動**前**建立
`<Save_Analysis_File_Dir>/gitlab_mr_result_<repo>_<mr>_<時間戳>/`，並把路徑傳給
每一步。目錄建立失敗（路徑打錯、沒有寫入權限）會在按下按鈕的當下就跳錯誤框，
流程不啟動 —— 不會等到跑完前三步才發現寫不進去。

```
gitlab_mr_result_lw-os_123_20260912_143012/
  01_description.md
  02_mr_info.json
  03_summary.json
  04_code_review.json
  04_code_review_src.md  自 JIRA 下載回來的原始附件（沒取到附件時不會有）
  05_report.md
  ai_prompt.txt        實際送給 AI 的完整 prompt
  ai_reply_1.txt       AI 的原始回覆（每次嘗試各一個檔）
  ai_reply_2.txt       重問過才會有
  bad_analysis.json    鉤子回傳的結構沒通過驗證時才會有
  bad_code_review.json 步驟 4 的結構沒通過驗證時才會有
  debug.log
```

`04_code_review_src.md` **是原始附件、不是擷取結果** —— 擷取到的總表在
`04_code_review.json` 裡。留著它的理由是「擷取對不對」只能拿原文比對；而它自動只在
勾選除錯時存在，因為工作目錄那時**就是**除錯目錄（未勾選時是流程結束後會被整個移除
的暫存目錄），不需要任何額外判斷。

它的檔名固定，**不取自附件本身的檔名** —— 那是上傳者打的字，拿它組路徑與規格禁止
「device 名稱用來組成檔案路徑」是同一類風險，順帶也解決 JIRA 允許同名多筆附件的
覆蓋問題。

**調 prompt 就是看 `ai_prompt.txt` 與 `ai_reply_1.txt`。** 這兩份都不進 log ——
prompt 含整份 diff（也就是原始碼），回覆動輒幾萬字元。除錯檔是唯一看得到它們的地方。

每一次回覆**寫在解析之前**，各自成檔：重問成功不會蓋掉失敗的那一次，而失敗的那次
才是線索。

`debug.log` **失敗時也會寫**，內容是該次失敗的訊息、代碼與細節；鉤子拋出例外時細節
是完整的 traceback。只在成功時記錄的話，最需要那份紀錄的時候剛好沒有。

**未勾選時整條流程不產生任何檔案。** 報告內容一律經由回應的 `data` 送回，
結果視窗從那裡取內容，Qt 從不開檔。

### 憑證

GitLab 與 JIRA 的端點與權杖放在設定檔的 `Service`，由功能注入為環境變數
（鍵名的全大寫形式）：

```
GITLAB_SERVER_URL    GITLAB_ACCESS_TOKEN    GITLAB_VERIFY_SSL
JIRA_SERVER_URL      JIRA_ACCESS_TOKEN
```

同一條注入路徑上還有兩個不是憑證的值（都在 `Function` 底下、不在 `Service`，因為它們
只屬於這個功能）：

```
PPS_DEVICE                               <- PPS_Device
PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH   <- PPS_Scripts_CodeReview_File_StartsWith
```

`PPS_Scripts_CodeReview_File_StartsWith` 是第 4 步用來篩選 JIRA 附件的**檔名前綴**
（例如 `CodeReview_`）。它**沒有預設值** —— 沒設定時第 4 步直接失敗並同時點名環境變數
與設定鍵，整條流程結束。給它預設值的話，漏設時會靜默改用一個部署者沒選的前綴，而症狀
是「議題上明明掛著附件，報告裡卻沒有那一段」。

比對**區分大小寫**、只認 `.md`、只認**開頭**（不是包含）。副檔名寫死在腳本裡不可配置：
可配置的話有人會指到 `.docx` 或 `.zip`，於是二進位內容被貼進報告，而每一步都回報成功。

> **注意這是每個部署只會撞一次的成本。** 第 4 步跑在第 3 步之後，所以設定檔少這個鍵時，
> 使用者是**付完 AI 費用、等完那兩分鐘之後**才看到錯誤訊息，而那一次沒有報告。檢查刻意
> 只留在腳本那一道（一個地方一個真相），代價寫在 design.md。

**腳本只從環境變數讀這些值，不從 `config` 讀。** 這樣 CI/CD 設定同名的環境變數
就能執行同一批腳本，腳本端只有一條取值路徑。AI 的端點、金鑰與模型名則走 `params`。
兩者都不會出現在行程的命令列上。

`GITLAB_VERIFY_SSL` **未設定時視為不驗證**。這是刻意的取捨：目標環境是否使用
自簽憑證尚不確定，而驗證失敗會讓功能完全無法使用。代價是關閉驗證時存取權杖
會暴露給連線中間人，且被攔截時沒有任何徵兆。確認伺服器有正規憑證之後，把
`Service.Gitlab_Verify_SSL` 設為 `"true"` 即可，不需要重新建置。自簽但想驗證的話
改設 `SSL_CERT_FILE` 指向公司的 CA 憑證。

**AI 服務的 TLS 驗證同樣預設關閉**，理由一樣（地端服務多半用自簽憑證）。它讀的是
環境變數 `AI_VERIFY_SSL`，設為 `true` 才驗證。不放設定檔是因為 Qt 只注入
`kServiceKey[]` 列出的 Service 鍵，加一個新鍵要動 C++ 並重新建置。

憑證驗證失敗**不重試** —— 一張不被信任的憑證不會在兩秒後變得被信任，重試三次只是
把註定的失敗等三倍。訊息會直接說是憑證驗證失敗。

### 已知行為

- 單次取回上限 100 筆，不翻頁。達到上限時會提示結果可能未完整 —— 表格是單選的，
  取回上千筆不會讓「挑一筆」更容易，範圍太大時該做的是調緊查詢條件。
- 流程被取消時，已經建立的除錯目錄不會被清掉（規格明文：流程不保證外部副作用的
  原子性）。目錄名含時間戳，不會互相覆蓋。
- 取消發生在 AI 那一步時，已送出的請求可能照樣計費，而畫面完全不變。
- device 的鉤子是使用者寫的，所以它可能壞掉。載入或執行失敗時訊息會指出是哪一個
  device 的哪一個鉤子（含語法錯誤的檔名與行號）；回傳的結構不對則在**產生它的那
  一步**就失敗，而不是兩步之後的渲染。
- **第 4 步取不到 code review 時不會讓流程失敗**，而是把原因寫成報告裡那一段的內容。
  只有「缺設定鍵」與「缺 JIRA 端點或權杖」這兩種部署缺漏才結束流程 —— 分界是「能不能
  在本機判定」，理由見 design.md 決策五。
- **附件檔名的大小寫打錯會安靜地沒有那一段。** 比對區分大小寫，而「沒有符合的附件」
  走的是「這筆本來就沒有」那條路（整段不出現、沒有訊息），所以它與「議題上真的沒掛
  review」在報告上長得一模一樣。唯一的診斷路徑是開啟 `Debug_Mode` 後看 `debug.log`
  裡那一行「看到哪些附件、篩掉哪些」。
- **人工上傳的附件可能與當前程式碼不同步。** 規則就是取最新一筆，不做時間差警告；
  報告印出上傳日期，讀者自行判斷。

---
## 設定檔

檔名 `PPS2_0DevTool.json`，根鍵 `PPS2_0DevTool`。

```jsonc
{
  "PPS2_0DevTool": {
    "Debug_Mode": "false",
    "User_Guide_Link": "",
    "Service": {                                       // 跨功能共用
      "Gitlab_Server_URL": "https://gitlab.example.com",
      "Gitlab_Access_Token": "",
      "Jira_Server_URL": "https://jira.example.com",
      "Jira_Access_Token": ""
    },
    "Function": {
      "Log_Info": {
        "Program": "python",                              // 必備
        "Visible": "true",                                // 必備
        "Get_Log_Info_Script_Path": "scripts\\get_log_info.py",
        "Jira_Server_URL": "https://jira.example.com",
        "Jira_Access_Token": ""
      }
    }
  }
}
```

外殼只讀 `Debug_Mode` / `User_Guide_Link` / `Service` / `Function` 四個欄位，
**`Service` 與 `Function` 整包都不解析**。

### `Service`：跨功能共用的服務設定

GitLab、JIRA 這類會被多個功能共用的端點與憑證放在 `Service`，不要抄進每個
功能區塊 —— 抄了之後使用者換憑證時漏改一處，那個功能就會回 401，而 401 的
第一直覺是「憑證過期」，於是去重發一把新的，找錯方向。

功能呼叫 `getFunctionConfig()` 拿到的是 **`Service` 併上自己區塊**的結果，
同名鍵以功能區塊為準（讓個別功能能指向不同的伺服器）。信封的 `config` 因此
也是合併後的物件 —— 腳本收到的仍是一個平坦的物件，不需要認得這個結構。

唯一的例外是 `Visible`：它只看 `Function` 底下的原始區塊。否則 `Service` 裡
一個誤放的 `Visible` 會讓所有沒設定它的功能從「預設隱藏」變成全部顯示。

> **不要把整包 `config` log 出來。** 合併後它含有權杖，而 `Debug_Mode` 開啟時
> 那一行會出現在 console 上。範本裡示範的 `logger.debug("設定 =%r", cfg)` 是
> 給沒有憑證的功能看的，有憑證時請只印出你真正需要的那幾個鍵。

**升級到含 code review 的版本後要手動補一個鍵。** 既有的設定檔不會被建置覆蓋，所以
`AI Analysis GitLab MR` 區塊底下不會自動長出
`PPS_Scripts_CodeReview_File_StartsWith`，而第 4 步會因此失敗並點名它。對照
`PPS2_0DevTool.example.json` 補上即可：

```json
"PPS_Scripts_CodeReview_File_StartsWith": "CodeReview_"
```

`AI_Mode_List` 是一個清單，畫面上的 AI Mode 下拉選單就是用每一筆的 `Name` 填的：

```json
"AI_Mode_List": [
  {
    "Name": "地端模型",
    "Api_URL": "https://主機:8443/端點:SHARE_CODE",
    "Api_Key": "送出時放進 X-Api-Key 標頭",
    "Model": "只印在報告出處，不進請求"
  }
]
```

**`Api_URL` 尾端要以冒號黏上 shareCode**（見「呼叫 AI」）。這四項走 `params` 而不是
環境變數 —— 它們隨使用者選的模式而變，屬於該次執行的參數。

選單是拿**選單上的文字回去比對 `Name`**。改了 `Name` 或那一筆不在清單裡，比對不到就
會拿到空的 `Api_URL`，於是掉回替代內容（報告首行會寫「未經過 AI」）。

### 命名風格

| 類型 | 風格 | 例 |
|---|---|---|
| 一般鍵名 | `Title_Case_With_Underscores` | `Debug_Mode` |
| 腳本路徑 | `<動作>_Script_Path` | `Get_Log_Info_Script_Path`（見下方註） |
| 目錄 | `*_Dir` | `Execute_Log_Script_Dir` |
| 網址 | `*_URL` | `Jira_Server_URL` |
| 憑證 | `*_Token` / `*_Key` | `Gitlab_Access_Token` |
| 布林 | **字串** `"true"` / `"false"` | `"Visible": "true"` |
| 清單 | JSON array | `"Repo_List": ["a/b"]` |

每個功能區塊必備 `Program`（執行 Python 的指令）與 `Visible`
（非 `"true"` 時該 tab 會被移除；未設定時預設隱藏並記一筆警告）。

> **腳本路徑實際上寫死在 C++ 裡**，不放設定檔。`SingleBuilding.cpp` 與
> `AIAnalysisGitLabMR.cpp` 都是這樣做的 —— 腳本是程式的一部分，不是使用者該調的
> 東西，放進設定檔只是多幾個能打錯的鍵，而打錯的症狀是「找不到腳本」。上表的
> `_Script_Path` 風格留著給真的需要由設定決定路徑的場合。

---

## 設定檔與 git

`PPS2_0DevTool.json` **不納入版本控制**（列在 `.gitignore`）。納入版本控制的是
`PPS2_0DevTool.example.json`，它結構相同、憑證欄位留空。

建置時的行為：

| 執行檔旁 | 建置後 |
|---|---|
| 已有 `PPS2_0DevTool.json` | **完全不動它** —— 你填的權杖不會被蓋掉 |
| 沒有 | 從 `PPS2_0DevTool.example.json` 生一份 |

（`scripts/` 則相反，每次建置無條件覆蓋。腳本是程式的一部分。）

**升級版本後看到「缺少必填項目：設定 XXX」是正常的。** 既有的設定檔不會被覆蓋，
所以新版本新增的鍵不會自動長出來 —— 對照 `PPS2_0DevTool.example.json` 補上即可。

**Windows 的 shadow build 有兩個目的地。** `debug/` 與 `release/` 各有自己的設定檔，
權杖要各填一次。

要重新取得一份乾淨的設定檔，把執行檔旁那份刪掉再建置。

---

## 新增一個功能

1. 建立 `<功能名>.{h,cpp}`，一個 `QObject` 子類別，建構子用 `getFunctionConfig()` 取設定
2. 在 `pps2_0devtool.ui` 加一個 tab，標題就是功能名稱
3. 在 `setupToolService()` 建立實例；`UI_Init()` 依 `isFunctionVisible()` 決定是否
   `removeTabByTitle()`；`UI_SetupSignal()` 連接該 tab 的元件
4. 在 `PPS2_0DevTool.example.json` 的 `Function` 加設定區塊（跨功能共用的端點
   與憑證放 `Service`，不要抄進功能區塊）
5. 在 `PPS2_0DevTool.pro` 的 `SOURCES` / `HEADERS` 加檔案
6. 建立 `scripts/<功能名>/`，把 `scripts/_function_template.py` 複製進去寫成入口腳本
   （範本本身留在 `scripts/` 這一層）；只服務這個功能的東西放這個目錄，跨功能的
   共用能力放進 `script_utils/` 底下對應的技術領域分組

**不需要修改 `json.cpp`。** 新增共用服務的鍵也不需要 —— 只有新增一整個工具層級
區塊才需要動它。

> 這份清單與 `pps2_0devtool.h` 開頭的類別註解是同一份，改一邊要記得改另一邊。

### 外殼提供的服務

```cpp
// 腳本執行（非同步，結果經由 callback 送達）
bool runFunctionScript(const QString &functionName,
                       const QString &scriptPath,
                       const QString &action,
                       const QJsonObject &params,
                       PythonRunner::ResultCallback onDone,
                       const QMap<QString, QString> &envVars = {});

// 設定查詢
QJsonObject getFunctionConfig(const QString &functionName) const;
bool        isFunctionVisible(const QString &functionName) const;

// 共用 UI
void    showUI_InfoMessageBox(const QString &text);
void    showUI_WarningMessageBox(const QString &text);
void    showUI_ErrorMessageBox(const QString &text);
void    showResultDialog(const QString &title, const QString &content, qint64 elapsedMs);
// 處理中對話框由外殼自動顯示／關閉，功能不需要（也無法）自己建立
QString getUI_sourcePathLineEditText() const;
bool    removeTabByTitle(const QString &title);

// 流程執行（非同步，一次操作依序跑多支腳本）
bool runFunctionFlow(const QString &functionName,
                     FlowDecider decide,
                     FlowCallback onDone);

// 掛勾訊號（不需要來源路徑的功能不連接即可）
//
// 附帶功能名稱：來源路徑是各功能私有的，但 Qt 的訊號會送達所有已連接的
// slot，功能端要比對自己的名稱後才決定要不要處理。
signals:
    void sourcePathChanged(const QString &sourceFilePath,
                           const QString &functionName);
```

呼叫的樣子：

```cpp
runFunctionScript("Log_Info", scriptPath, "get_log_info", params,
    [this](const PythonRunner::PythonRunnerResult &r) {
        if (!r.success) { showUI_ErrorMessageBox(r.message); return; }
        applyToUi(r.data);          // 只有這裡碰 UI
    });
```

### 多步驟流程

一個 button 要依序跑多支腳本時用 `runFunctionFlow()`。步驟**不預先列出**：
每完成一步，外殼把目前為止所有已完成結果交給你的決策函式，由它回答下一步
或結束。流程長度與路徑因此都可以依結果而定。

```cpp
runFunctionFlow("Log_Report",

    // 決策函式：每完成一步被問一次
    [this](const QList<PythonRunner::PythonRunnerResult> &done)
            -> PPS2_0DevTool::FlowStep {
        if (done.isEmpty()) {                       // 還沒跑過任何一步
            PPS2_0DevTool::FlowStep step;
            step.label      = "步驟 1/2：分析 log";
            step.scriptPath = "scripts/analyse_log.py";
            step.action     = "analyse";
            step.params     = buildAnalyseParams();
            return step;
        }

        const PythonRunner::PythonRunnerResult &first = done.first();
        if (!first.success)
            return PPS2_0DevTool::FlowStep::done();  // 第一步失敗就收工

        if (done.size() == 1) {
            PPS2_0DevTool::FlowStep step;
            step.label      = "步驟 2/2：產生報表";
            step.scriptPath = "scripts/make_report.py";
            step.action     = "report";
            step.params     = buildReportParams(first.data);   // 只挑欄位、改名
            return step;
        }

        return PPS2_0DevTool::FlowStep::done();
    },

    // 流程結束時呼叫一次。取消時不會被呼叫。
    [this](const PPS2_0DevTool::FlowResult &r) {
        if (!r.success) { showUI_ErrorMessageBox("流程失敗"); return; }
        applyToUi(r.results);            // 只有這裡碰 UI
    });
```

寫流程時要記得的五件事：

- **步驟序號自己寫進 `label`。** 流程長度不定，外殼無從得知總步數，所以不會
  幫你編號。`label` 顯示在處理中對話框的標題列，腳本回報的 `stage` 顯示在
  下面的標籤 —— 兩層文字，一個視窗，從頭到尾不重建。
- **決策函式裡不要有使用者互動。** 它在步驟之間同步執行，事件迴圈不會轉動；
  `QMessageBox::exec()`、`QFileDialog` 之類會開巢狀事件迴圈，把主視窗交給
  那個迴圈接管。要問使用者，就在流程開始前問完。
- **決策函式只搬資料，不做運算。** 挑欄位、改名、讀 UI 上的值、依成敗分支 ——
  可以。計算、過濾、聚合 —— 推進腳本。理由見上面的職責表。
- **資料量大時傳路徑，不要傳內容。** 前一步的 `data` 要進下一步的 `params`，
  就得在 Qt 這邊再序列化一次。上萬筆的話讓前一步把結果寫成檔案、`data` 只
  回傳路徑，下一步用路徑取用。
- **參與流程的腳本要可重入。** 取消或失敗時畫面完全不變，但**已完成步驟的
  副作用不會還原** —— 寫出去的檔案、送出去的請求都還在。以相同輸入重跑一次
  不該產生重複或不一致的結果。需要補償的話，自己在決策函式裡排補救步驟。

### 三條必須遵守的規則

- **UI 只在收到 `PASS` 之後才變更。** 執行過程中不做任何逐筆更新，
  一律等結果到齊才一次套用。所以取消或失敗時畫面完全不動，沒有東西需要回捲。
  多步驟流程的「結果到齊」是指**整條流程結束**，不是單一步驟結束 —— 中間
  步驟的結果自己留著，不要逐步套上畫面。
- **取消時 callback 不會被呼叫。** 這是「取消後畫面不動」的物理保證，
  呼叫端不需要寫取消分支。取消的對象是整條流程：後續步驟不會啟動，決策函式
  也不會再被問到。
- **一次只能執行一支腳本。** 執行期間主視窗被鎖定；程式化的連續呼叫會回 `false`。
  流程進行中（含步驟之間的間隔）同樣算執行中。

### 對話框一律固定尺寸

**工具彈出的對話框不讓使用者以滑鼠改變大小。** 這是整個工具的規則，不是某個
功能的選擇。

按下任何功能的執行鈕都會看到同一個處理中對話框 —— 它由外殼提供、自動顯示與關閉，
**功能端不需要做任何事，也無法各自決定**。新增功能時不必為它寫任何程式碼。

那是一個執行期間鎖住主視窗的互斥對話框，使用者在它身上唯一該做的決定是要不要取消。
可以拖大拖小只會讓它看起來像一個可以操作的視窗，而拖動本身不改變任何事情。

實作在 `ProcessingDialog.cpp`：`setFixedSize()` 加上 Windows 的
`Qt::MSWindowsFixedSizeDialogHint`。前者鎖住尺寸，後者把視窗邊框換成固定尺寸
對話框的細邊，邊緣不再是可拖曳的縮放區。尺寸由檔案開頭的 `kDialogWidth` /
`kDialogHeight` 兩個常數決定。

連帶效果：對話框不再隨標籤內容縮放（以前階段文字一長一短，視窗會在執行過程中
自己跳動）。代價是過長的階段文字放不下，因此顯示時截斷成「…」並把完整內容放進
tooltip —— 與 MR 表格的標題欄同一種處理。

> **寫腳本時順帶注意**：`script_io.progress()` 回報的階段文字是上面那個標籤的
> 內容。太長的句子會被截斷，寫短一點比較好讀。

---

---

## 寫腳本

複製 `scripts/_function_template.py` 開始。範本原樣就能執行。

```python
#!/usr/bin/env python3
import os
import sys

# 入口腳本在 scripts/<功能>/ 底下，這一行要在匯入 script_io / script_utils
# 之前執行。範本裡就有，不要刪（理由見底下）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import script_io
from script_utils import gitlab_utils      # 業務邏輯模組
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "get_gitlab_mr"
DESCRIPTION      = "取得指定 repo 的 merge request 清單"

def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        # 憑證不在 config 宣告 —— 它們走環境變數（見「憑證」一節）。
        config=[],
        params=[
            script_io.arg("repo", required=True, help="repo 完整路徑，例如 group/project"),
            script_io.arg("created_after", default="",
                          help="只抓這個時間之後建立的 MR，ISO 8601；留空表示不限"),
        ],
    )

    # 憑證只從環境變數讀。Qt 會自設定檔的 Service 區塊注入，CI 自行設定 ——
    # 腳本端因此只有一條取值路徑，兩個呼叫端對它來說長得一模一樣。
    server_url = os.environ.get("GITLAB_SERVER_URL", "")
    token      = os.environ.get("GITLAB_ACCESS_TOKEN", "")
    if not token:
        script_io.reply_fail("未設定環境變數 GITLAB_ACCESS_TOKEN")

    logger.info("查詢 %s", req["params"]["repo"])
    script_io.progress("呼叫 GitLab API")

    # 業務邏輯寫在 script_utils 裡，這裡只做轉接
    mrs = gitlab_utils.get_all_mr(
        cfg["Gitlab_Server_URL"], cfg["Gitlab_Access_Token"],
        req["params"]["repo"],
        created_after=req["params"]["created_after"],
    )

    # 挑欄位是入口腳本的事：共用模組回傳 GitLab 原樣的物件（一筆約 2～4 KB），
    # 整包塞進信封的話 100 筆就有幾百 KB 要經 stdout 送回 Qt。
    rows = [{"iid": m["iid"], "title": m["title"], "web_url": m["web_url"]}
            for m in mrs]

    script_io.reply(message="共 %d 筆" % len(rows), data={"merge_requests": rows})

if __name__ == "__main__":
    script_io.run(main)
```

**入口腳本放在 `scripts/<功能>/` 底下**，同一個功能的腳本收在一起（見上面的
「兩種分組軸」）。因為進了子目錄，每支頂部那行 `sys.path.insert(...)` **不能刪** ——
Python 只把「腳本所在目錄」放進 `sys.path`，少了它，`from script_utils import ...`
在沒設 `PYTHONPATH` 時會失敗，別人直接執行就壞掉。Qt 雖然會注入指向 `scripts/` 的
`PYTHONPATH`，但命令列與 CI 沒有那個環境，而那正是本專案明確支援的用法 ——
所以可匯入性是入口腳本自己的責任。

### 參數與設定只宣告一次

`cfg()` / `arg()` 的宣告同時產生 `--help` 的說明與 `--dump-config` 的模板。
**不要另外寫死一份模板**，它一定會跟腳本實際讀的欄位漂移。

`required=True` 的缺漏會在**進入業務邏輯之前**就被擋下來，訊息直接指出缺哪一個鍵 ——
而不是帶著空 token 去打 API、拿到 401、然後跑去檢查 token 是不是過期了。

### `script_utils` 的四條規則

違反任一條就無法被當函式庫使用：

1. 不可以 `print()` 到 stdout —— stdout 是結果通道
2. 不可以 `sys.exit()`，要 `raise` —— 否則 import 它的人會被整個打死
3. 不該自己讀設定檔或環境變數 —— 參數明著傳
4. 回傳資料結構，不回傳 JSON 字串 —— 序列化是入口腳本的責任

第 3 條約束的是「共用模組自己去拿設定」。`system_utils.get_env_var()` 不是它的例外，
而是給**入口腳本**用的薄封裝：由入口腳本讀出值，再當參數明著傳給共用模組。

### `script_io` API

| API | 用途 |
|---|---|
| `parse_request(action, description, config, params, template_version)` | 收信封 + 驗證必填 |
| `cfg(name, required, help)` | 宣告一個設定鍵 |
| `arg(name, type, default, required, help)` | 宣告一個參數 |
| `progress(stage)` | 往 stderr 印進度並 flush |
| `reply(message, detail, data)` | PASS + exit 0 |
| `reply_fail(message, detail, code)` | FAIL + exit 1 |
| `run(main_func)` | 統一錯誤處理入口 |

`script_utils.logger` 提供 `debug` / `info` / `warn` / `error` / `set_verbose`。
它是**唯一**設定 logging 的地方，全部等級一律走 stderr。

---

## 信封格式

### Request（Qt 經由 stdin 送入）

```json
{
  "source_path": "F:/work/pattern",
  "config":      { "…該功能在 PPS2_0DevTool.json 的整個區塊…" },
  "action":      "get_gitlab_mr",
  "params":      { "repo": "group/project", "created_after_days": 7 }
}
```

信封**不含工具身分**。需要知道呼叫方是誰的腳本自行讀取環境變數
（命令列直接執行時不存在，要能在缺少時正常運作）：

```python
tool_name = os.environ.get("TOOLNAME", "")
```

協定是**加法式**的：Qt 多送一個欄位，舊腳本忽略；腳本多讀一個欄位，沒送就用預設值。

### Response（腳本印在 stdout）

```json
{
  "result":  "PASS",
  "message": "解析完成，共 128 筆",
  "detail":  "…多行，選填…",
  "data":    { "…結構化結果，選填…" }
}
```

| 欄位 | 必填 | 說明 |
|---|:--:|---|
| `result` | ✓ | 固定寫 `"PASS"` / `"FAIL"`（全大寫） |
| `message` | ✓ | **一行**，GUI 訊息框 / CLI / CI log 都用它 |
| `detail` | | 多行 |
| `data` | | 結構化資料 |
| `error` | | `{"code": "..."}`，失敗時給 CI 分流用 |

失敗時：

```json
{
  "result":  "FAIL",
  "message": "GitLab 回應 401：token 無效或已過期",
  "error":   { "code": "GITLAB_401" }
}
```

**結果一律放在 `data` 裡**，不寫檔。腳本之間要接力，由 Qt 把前一支的 `data`
放進下一支的 `params`；信封走 stdin，沒有長度限制。

### 通道分離

| 通道 | 內容 |
|---|---|
| **stdout** | **只放結果**，單一 JSON 物件 |
| **stderr** | 診斷訊息、警告、進度 |

**腳本印任何額外內容到 stdout 都會讓該次執行失敗** —— Qt 端只做一次整段解析，
沒有退回掃描。這是刻意的：靜默救回違規腳本，那支腳本就永遠不會被修好。

### 進度

走 stderr，一行一個 JSON，只有 `stage` 一個欄位：

```json
{"progress": {"stage": "解析 log (37/128)"}}
```

GUI 一律顯示跑馬燈、不顯示百分比，所以不需要 `current` / `total`。
需要讓使用者看到筆數就寫進 `stage` 文字裡。

兩個坑：**一定要 flush**（`script_io.progress()` 已經處理），
以及**自己節流** —— Qt 端收到就更新、不做過濾，跑幾千筆時不要每筆都報。

### Exit code

| 情況 | exit code | stdout |
|---|:--:|---|
| 成功 | `0` | `{"result": "PASS", ...}` |
| 業務邏輯失敗 | `1` | `{"result": "FAIL", ...}` |
| 呼叫方式錯誤 | `2` | 通常沒有 JSON，訊息在 stderr |
| 未預期的崩潰 | 非 `0` | 沒有 JSON，traceback 在 stderr |

exit code 給 CI 用，JSON 給 GUI 與使用者用，兩者都要正確。
**Qt 不管 exit code 一律先解析 stdout** —— 腳本為了 CI 而 `exit 1` 時，
那份寫著失敗原因的 JSON 不會被丟掉。

---

## 命令列使用

腳本不只給 Qt 用。兩種投遞方式：

```bash
# 1) 信封走 stdin（Qt 走這條）
echo '{"action":"get_gitlab_mr","params":{"repo":"group/project"}}' \
  | python get_gitlab_mr.py --request-stdin

# 2) 產生模板、填完再跑（人走這條）
python get_gitlab_mr.py --dump-config > run.json
#   編輯 run.json
python get_gitlab_mr.py --request run.json
```

其他旗標：

```bash
python get_gitlab_mr.py --help      # 列出所有設定鍵與參數
python get_gitlab_mr.py ... -v      # 打開 DEBUG 等級的診斷輸出
```

走 stdin 而不是命令列有兩個理由：沒有長度限制、**token 不會出現在工作管理員的命令列裡**。

傾印出來的模板長這樣（`_` 開頭的鍵腳本一律忽略，是 JSON 沒有註解的替代做法）：

```json
{
  "_template_version": "2.0.0",
  "action": "get_gitlab_mr",
  "source_path": "",
  "config": {
    "Gitlab_Server_URL": "",
    "Gitlab_Access_Token": ""
  },
  "params": {
    "repo": "",
    "created_after_days": 7
  },
  "_help": {
    "config": { "Gitlab_Server_URL": "GitLab 伺服器網址（必填）" },
    "params": { "repo": "repo 完整路徑，例如 group/project（必填）" }
  }
}
```

因為 Qt 送的和人填的是同一個信封，失敗時可以把當次的信封存下來，
直接拿到命令列上原樣重現。

### 跨平台

**Qt 工具只跑 Windows，但 Python 腳本必須在 Windows 與 Linux 都能跑。**

- 路徑一律用 `pathlib`，不要自己接分隔符號
- 外部執行檔不要寫死 `.exe`
- 開檔一律明確指定 `encoding="utf-8"`

---

## Debug_Mode

設定檔的 `Debug_Mode` 設成 `"true"` 時：

1. Qt 開啟 console 視窗（UTF-8）
2. `QTDebug` / `QTWarn` / `QTError` 的輸出會出現在那裡
3. Qt 呼叫腳本時額外加上 `-v`，讓 Python 的 DEBUG 也一起出來

兩邊的 log 混在同一個視窗，格式刻意對齊（時間戳含毫秒、等級名稱固定寬度 10）：

```
[2026-09-06 14:30:12.345] [ QT DEBUG ] 來自 Qt
[2026-09-06 14:30:12.352] [ PY DEBUG ] 來自 Python
```

**關閉 console 會結束整個程式**（關閉前會先終止正在跑的腳本子行程）。
`Debug_Mode` 開啟時結束程式有兩條路：系統匣的 `Quit`、以及關掉 console。

> `Debug_Mode` 關閉時，腳本的 stderr 內容不會被收集。所以腳本崩潰時只看得到
> 「腳本沒有回傳結果」加 exit code —— 要追原因請開啟 `Debug_Mode` 重跑一次。

執行環境注入的環境變數：

| 變數 | 值 |
|---|---|
| `PYTHONPATH` | 原有值 + 執行檔目錄下的 `scripts` |
| `PYTHONUTF8` | `1` |
| `PYTHONUNBUFFERED` | `1`（確保進度即時送達） |
| `TOOLNAME` / `TOOLVERSION` | 來自 `version.h` |

---

## 其他行為

- **系統匣**：關閉主視窗時隱藏而非結束；雙擊還原；右鍵選單只有 `Quit`
- **視窗尺寸**：1200×830 固定
- **單一實例**：同時只能執行一個
- **崩潰**：SIGSEGV 時會在執行檔目錄寫出 `crash.log`（含最後 300 行診斷輸出）
- **不設執行逾時**：卡住由使用者按取消處理（terminate → 3 秒 → kill）

---

## 設計文件

規格與決策記錄在 `openspec/` 底下。

**`openspec/specs/`** —— 現行的行為契約，這是**權威來源**。五個 capability：

| capability | 涵蓋範圍 |
|---|---|
| `app-shell` | 設定檔讀取與查詢、來源路徑掛勾（各功能私有）、Debug console、共用 UI 服務、視窗與啟動行為、應用程式圖示 |
| `script-execution` | `runFunctionScript` 與 `runFunctionFlow` 契約、通道分離、成敗判定、取消狀態機、處理中對話框、行程環境、流程編排與業務運算的分工邊界 |
| `script-envelope` | Request/Response 信封、`script_io` API、參數與設定宣告、logger、exit code、跨平台、腳本目錄結構 |
| `single-building` | Single Building 功能：兩個清單的挑選與過濾、四支腳本的觸發與串接、暫存設定檔、失敗與取消的處理 |
| `ai-analysis-gitlab-mr` | AI Analysis GitLab MR 功能：畫面與查詢、五步流程、GitLab 與 JIRA 連線、AI 呼叫與重試、device 機制、報告版面、除錯輸出 |

**`openspec/changes/archive/`** —— 已完成的變更，保留當時的 `proposal.md`（為什麼要做）、
`design.md`（決策與取捨理由）與 `tasks.md`（實作與驗證記錄）。

建立這個外殼的變更是 `bootstrap-devtool-shell`，它的 `design.md` 記了 33 條決策，
每條都附上理由與被否決的替代方案。

---

**要改框架行為之前先看 `design.md`。** 很多看起來可以「順手簡化」的地方都是刻意的：

| 看起來像可以改進的 | 為什麼刻意這樣 |
|---|---|
| stdout 解析失敗時不試著撈一下 JSON | 靜默救回違規腳本，那支腳本就永遠不會被修好 |
| 處理中對話框立刻彈出、短腳本會閃一下 | `QProgressDialog` 預設延遲 4 秒，那 4 秒內主視窗沒被鎖住 |
| 取消時不呼叫 callback | 這是「取消後畫面不動」的物理保證，不必依賴每個功能作者都寫對取消分支 |
| `Debug_Mode` 關閉時不收集腳本的 stderr | 明確接受的取捨；代價寫在 `design.md` 的 Risks 段落 |
| 信封不帶工具身分欄位 | 同一份資料兩條通道，遲早會不一致而沒人發現 |

### 開發流程

這個專案用 [OpenSpec](https://github.com/Fission-AI/OpenSpec) 管理變更：先寫提案與規格，
再實作。常用指令：

```bash
openspec list                    # 進行中的變更
openspec show <change-name>      # 看某個變更的內容
openspec validate --changes <change-name> --strict
```
