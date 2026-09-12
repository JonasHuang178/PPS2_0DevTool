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
| **共用模組** | 技術**領域** | `script_utils/system_utils/`、`script_utils/gitlab_utils/` |

共用模組**不依功能分組** —— 那樣的話第二個功能需要同一個能力時就無處可放。
只服務單一功能的東西留在 `scripts/<功能>/` 之下。

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
│   └── script_utils/         共用模組依「技術領域」分組
│       ├── logger.py         log（唯一設定 logging 的地方）
│       ├── system_utils/     系統層面：檔案系統、暫存目錄
│       │   ├── files.py      依副檔名列檔案、行式文字檔讀寫
│       │   └── temp.py       暫存目錄下的路徑
│       └── gitlab_utils/     GitLab REST（尚無內容）
│
└── openspec/                 規格與設計決策
    ├── specs/                現行行為契約（三個 capability）
    │   ├── app-shell/
    │   ├── script-execution/
    │   └── script-envelope/
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
感知」會清理該處。若日後需要跨重啟保留，改 `scripts/script_utils/single_building/paths.py`
裡那一個函式即可（`%LOCALAPPDATA%` 是正確的去處）。

---

## 功能：AI Analysis GitLab MR

在工具裡瀏覽某個 GitLab 專案的 Merge Request，挑一筆交給 AI 分析，結果以
markdown 呈現在結果視窗。

> **本次交付的範圍**：Qt 這一側整個是真的；六支腳本的**對外契約**也是真的；
> 但分析流程五步的業務內臟是 **stub**，回傳寫死的假資料，不連線 AI 或 JIRA。
> 唯一真的連線的是「取得 Merge Request 清單」那一支。

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
| 2 | `..._script_selector.py` | `script_info`（狀態、裝置、JIRA key、處理方式） |
| 3 | `..._summary.py` | AI 分析結果 |
| 4 | `..._code_review.py` | 程式碼審閱報告 |
| 5 | `..._merge_to_md.py` | 合併後的 markdown |

**五步全部執行，Qt 端不跳過任何一步。**「要不要真的做事」由腳本看參數決定
（例如第 4 步收到 `fetch_code_review=false` 就回空報告並成功）。這是為了讓同一批
腳本能被 CI/CD 的 shell 直接串接 —— 分支若寫在 Qt 端，CI 那側就成為第二份編排
實作，兩份必然漂移。

**腳本路徑固定寫死在 C++**，不取自任何步驟的回傳資料。第 2 步回傳的 `handler`
原樣往下傳，由第 3、5 步的腳本自己解讀。

**任一步失敗即停**，以一個錯誤訊息框指出第幾步與該步腳本寫的原因，畫面不變。

### 除錯分析檔

勾選 `Add Debug Analysis file` 時，Qt 在流程啟動**前**建立
`<Save_Analysis_File_Dir>/gitlab_mr_result_<repo>_<mr>_<時間戳>/`，並把路徑傳給
每一步。目錄建立失敗（路徑打錯、沒有寫入權限）會在按下按鈕的當下就跳錯誤框，
流程不啟動 —— 不會等到跑完前三步才發現寫不進去。

```
gitlab_mr_result_lw-os_123_20260912_143012/
  01_description.md
  02_script_info.json
  03_summary.json
  04_code_review.md
  05_report.md
  debug.log
```

**未勾選時整條流程不產生任何檔案。** 報告內容一律經由回應的 `data` 送回，
結果視窗從那裡取內容，Qt 從不開檔。

### 憑證

GitLab 與 JIRA 的端點與權杖放在設定檔的 `Service`，由功能注入為環境變數
（鍵名的全大寫形式）：

```
GITLAB_SERVER_URL    GITLAB_ACCESS_TOKEN    GITLAB_VERIFY_SSL
JIRA_SERVER_URL      JIRA_ACCESS_TOKEN
```

**腳本只從環境變數讀這些值，不從 `config` 讀。** 這樣 CI/CD 設定同名的環境變數
就能執行同一批腳本，腳本端只有一條取值路徑。AI 的端點、金鑰與模型名則走 `params`。
兩者都不會出現在行程的命令列上。

`GITLAB_VERIFY_SSL` **未設定時視為不驗證**。這是刻意的取捨：目標環境是否使用
自簽憑證尚不確定，而驗證失敗會讓功能完全無法使用。代價是關閉驗證時存取權杖
會暴露給連線中間人，且被攔截時沒有任何徵兆。確認伺服器有正規憑證之後，把
`Service.Gitlab_Verify_SSL` 設為 `"true"` 即可，不需要重新建置。自簽但想驗證的話
改設 `SSL_CERT_FILE` 指向公司的 CA 憑證。

### 已知行為

- 單次取回上限 100 筆，不翻頁。達到上限時會提示結果可能未完整 —— 表格是單選的，
  取回上千筆不會讓「挑一筆」更容易，範圍太大時該做的是調緊查詢條件。
- 流程被取消時，已經建立的除錯目錄不會被清掉（規格明文：流程不保證外部副作用的
  原子性）。目錄名含時間戳，不會互相覆蓋。
- 取消發生在 AI 那一步時，已送出的請求可能照樣計費，而畫面完全不變。

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

---

## 寫腳本

複製 `scripts/_function_template.py` 開始。範本原樣就能執行。

```python
#!/usr/bin/env python3
import os
import sys

# 入口腳本在 scripts/<功能>/ 底下，這一行不能刪（見下）。
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
            script_io.arg("created_after_days", type=int, default=7,
                          help="只抓最近 N 天的 MR"),
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
    result = gitlab_utils.list_merge_requests(
        server_url=server_url,
        token=token,
        project=req["params"]["repo"],
        created_after_days=req["params"]["created_after_days"],
    )

    script_io.reply(message="共 %d 筆" % len(result["merge_requests"]),
                    data=result)

if __name__ == "__main__":
    script_io.run(main)
```

**入口腳本依功能分組放在 `scripts/<功能>/` 底下**，範本本身留在 `scripts/` 這一層。

因為放進了子目錄，**開頭那一行 `sys.path.insert(...)` 不能刪** —— Python 只會把
入口腳本所在目錄放進 `sys.path`，少了它，`from script_utils import ...` 在沒設
`PYTHONPATH` 時就會失敗。Qt 會注入指向 `scripts/` 的 `PYTHONPATH`，但不能當成前提：
命令列與 CI 直接執行時沒有那個環境，而那是本專案明確支援的用法。

> 這條規則在加入 Single Building 時從「不准放子目錄」改成了「自己確保匯得到」。
> 可匯入性是入口腳本自己的責任，不是對它放在第幾層的限制。

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

**`openspec/specs/`** —— 現行的行為契約，這是**權威來源**。三個 capability：

| capability | 涵蓋範圍 |
|---|---|
| `app-shell` | 設定檔讀取與查詢、功能掛勾訊號、Debug console、共用 UI 服務、視窗與啟動行為 |
| `script-execution` | `runFunctionScript` 契約、通道分離、成敗判定、取消狀態機、處理中對話框、行程環境 |
| `script-envelope` | Request/Response 信封、`script_io` API、參數與設定宣告、logger、exit code、跨平台 |

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
