# PPS 2.0 DevTool

PPS 2.0 開發輔助工具。框架、腳本執行管線與兩個功能 tab 均已完成：

| 功能 tab | 做什麼 | 腳本 |
|---|---|---|
| **Single Building** | 從來源樹挑 `.cpp` 寫進暫存設定檔 | 4 支 |
| **AI Analysis GitLab MR** | 取 Merge Request、送 AI 分析、產出 markdown 報告 | 6 支，外加 device 機制 |

兩個功能走同一條管線（信封協定、處理中對話框、來源路徑掛勾），新增第三個功能
不必動外殼 —— 做法見 [`docs/contributing.md`](docs/contributing.md)。兩個功能也都能
脫離 Qt 在命令列或 CI 上跑，各自的 `cli.md` 有指令。

框架已在 Windows（Qt Creator + MinGW）與 macOS 上建置並驗證，應用程式圖示已內嵌
進執行檔。

> **逐項的驗收狀態不記在這裡。** 每一輪變更的驗法與逐項結果都在它自己的
> `openspec/changes/archive/<變更>/tasks.md` 第 6 節 —— 那裡是寫驗法的地方，
> 抄一份到 README 只會得到第二份會過期的紀錄。

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
├── ci/
│   └── pps-ai-analysis.gitlab-ci.yml  五步分析流程的 GitLab CI 範例
│                             （**不是**本專案的 pipeline，是給使用者的樣板）
│
├── scripts/
│   ├── AUTHORING.md          腳本撰寫手冊 ← 寫腳本之前先讀這份
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
│   │   └── device/           各產品線自己的分析邏輯
│   │                         （見 docs/ai-analysis-gitlab-mr/device-authoring.md）
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

└── docs/                     文件。不限單一功能的放這一層，功能自己的各一個資料夾
    ├── user-guide.md         給用這個工具的人
    ├── contributing.md       給要動這個專案的人
    ├── _doc.css              圖解頁共用的樣式（底線開頭，不是文件）
    ├── index.html            文件首頁（GitHub Pages 的站台根目錄）
    ├── single-building/
    │   ├── README.md         功能細節
    │   └── cli.{html,md}     不開 Qt 怎麼跑
    └── ai-analysis-gitlab-mr/
        ├── getting-started.html  入門圖解（第一次接觸先看這份）
        ├── README.md         功能細節
        ├── cli.{html,md}     不開 Qt 怎麼跑（命令列與 CI 是同一組指令）
        └── device-authoring.{html,md}  寫自己的 device
```

**每個功能資料夾裡的 `README.md` 與 `cli.md` 是固定的兩個名字**，新增功能時照這個
形狀建。同一個主題若另有圖解頁，**檔名相同、副檔名換成 `.html`** —— `.md` 是查得到
每個欄位的參考，`.html` 是看得懂整件事的圖。新增任何目錄或檔案時，這棵樹就是它的註冊處 —— 漏登記的症狀是它存在但沒人
找得到（`ci/` 就漏過一輪）。

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

## 文件導覽

這份 README 只講**整體架構**。細節依讀者分成三類，各自一份：

### 兩個功能，各自一個資料夾

| 功能 | 資料夾 | 裡面有什麼 |
|---|---|---|
| **Single Building** | [`docs/single-building/`](docs/single-building/) | [`README.md`](docs/single-building/README.md) 資料流、哪個操作觸發哪支腳本、已知行為<br>[`cli.html`](docs/single-building/cli.html)｜[`cli.md`](docs/single-building/cli.md) 四支腳本的介面與跑一次的指令 |
| **AI Analysis GitLab MR** | [`docs/ai-analysis-gitlab-mr/`](docs/ai-analysis-gitlab-mr/) | [`README.md`](docs/ai-analysis-gitlab-mr/README.md) 畫面、五步流程、報告版面、涵蓋範圍、憑證、已知行為<br>[`getting-started.html`](docs/ai-analysis-gitlab-mr/getting-started.html) **第一次接觸先看這份**<br>[`cli.html`](docs/ai-analysis-gitlab-mr/cli.html)｜[`cli.md`](docs/ai-analysis-gitlab-mr/cli.md) 在命令列或 CI 上跑五步流程<br>[`device-authoring.html`](docs/ai-analysis-gitlab-mr/device-authoring.html)｜[`device-authoring.md`](docs/ai-analysis-gitlab-mr/device-authoring.md) 讓一條產品線有自己的分析邏輯與報告版面 |

**每個功能資料夾裡都有 `README.md` 與 `cli.md`，名字固定。** 想知道這個功能怎麼用就看
`README.md`，想不開 Qt 跑就看 `cli.md` —— 不必每次先找檔名。多出來的那一份
（`device-authoring.md`）是該功能獨有的機制才會有。

### 不屬於任何單一功能

| 文件 | 給誰 | 裡面有什麼 |
|---|---|---|
| [`docs/user-guide.md`](docs/user-guide.md) | 用這個工具的人 | 設定檔每一個鍵的意思、設定檔與 git 的關係、怎麼打開診斷輸出 |
| [`docs/contributing.md`](docs/contributing.md) | 要動這個專案的人 | 外殼提供哪些服務、多步驟流程怎麼寫、信封格式、命令列用法、跨平台、圖示資產怎麼重新產生 |
| [`scripts/AUTHORING.md`](scripts/AUTHORING.md) | 要寫腳本的人 | 腳本的**硬性規則**。寫任何腳本之前先讀這一份 |

### 規格

每一條行為的規範條文與 scenario 在 [`openspec/specs/`](openspec/specs/)，
五份：`app-shell`、`script-envelope`、`script-execution`、`single-building`、
`ai-analysis-gitlab-mr`。文件講「為什麼這樣設計」，規格講「必須怎麼表現」——
兩者不一致時以規格為準。

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
