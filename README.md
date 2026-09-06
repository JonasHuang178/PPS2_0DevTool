# PPS 2.0 DevTool

PPS 2.0 開發輔助工具。目前是 **v2.0.0 的外殼**：框架與腳本執行管線已完成，
**尚未包含任何功能 tab**，功能之後會逐一加上。

框架已在 Windows（Qt Creator + MinGW）與 macOS 上建置並驗證。有兩項驗收因為
「空外殼沒有觸發腳本的入口」而延後 —— 關閉 console 時清理子行程、以及 Qt 與
Python 的訊息同時出現在 console 中；兩者程式碼都已完成，待第一個功能 tab 做出來後補驗。

---

## 最高原則

> **Qt 只負責 GUI —— 讓使用者「選擇」。真正的實作寫在 Python。**

| 層 | 職責 | 不該做的事 |
|---|---|---|
| **Qt (C++)** | 顯示清單、接收選擇、組裝參數、呼叫腳本、呈現結果 | 解析檔案格式、呼叫外部 API、產生報表、做 AI 分析 |
| **Python** | 全部業務邏輯 | 開視窗、管理 UI 狀態 |

**每一個功能 = 一個 tab。** 功能之間互相獨立：各自讀自己的設定、決定自己顯示與否、
呼叫自己的腳本。**新增一個功能不需要修改任何框架程式碼。**

```
                        ┌──────────── 別人 / CI ────────────┐
                        ↓                                   ↓
Qt ──信封(stdin)──→ 入口腳本 ──→ script_utils ──→ 外部世界（GitLab / Jira / 檔案）
   ←─結果(stdout)──   （很薄）      （業務邏輯）
   ←─進度(stderr)──
```

「給別人用」的正確介面是 `script_utils`，不是腳本 —— 別人要整合進自己的流程時，
`from script_utils import gitlab_utils` 遠比「開子行程、組參數、parse JSON」好用。

---

## 目錄結構

```
PPS2_0DevTool/
├── main.cpp                  啟動檢查、單一實例鎖、crash handler
├── pps2_0devtool.{h,cpp,ui}  應用程式外殼
├── json.{h,cpp}              設定檔讀取（只讀工具層級）
├── PythonRunner.{h,cpp}      腳本執行管線
├── ProcessingDialog.{h,cpp}  處理中對話框
├── debug.{h,cpp}             QTDebug/QTWarn/QTError + 300 行 ring buffer
├── common.{h,cpp}            formatElapsedTime()
├── result_code.h             Qt 端錯誤碼
├── version.h                 版本與檔名常數
│
├── PPS2_0DevTool.json        設定檔（Function 目前是空的）
├── PPS2_0DevTool.pro         qmake 專案檔
│
├── scripts/
│   ├── _function_template.py 功能腳本範本 ← 複製這個開始寫新腳本
│   ├── script_io.py          信封處理
│   └── script_utils/
│       ├── __init__.py
│       └── logger.py         log（唯一設定 logging 的地方）
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

---

## 設定檔

檔名 `PPS2_0DevTool.json`，根鍵 `PPS2_0DevTool`。

```jsonc
{
  "PPS2_0DevTool": {
    "Debug_Mode": "false",
    "User_Guide_Link": "",
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

外殼只讀 `Debug_Mode` / `User_Guide_Link` / `Function` 三個欄位，
**`Function` 整包不解析** —— 功能自己取自己的區塊。

### 命名風格

| 類型 | 風格 | 例 |
|---|---|---|
| 一般鍵名 | `Title_Case_With_Underscores` | `Debug_Mode` |
| 腳本路徑 | `<動作>_Script_Path` | `Get_Log_Info_Script_Path` |
| 目錄 | `*_Dir` | `Execute_Log_Script_Dir` |
| 網址 | `*_URL` | `Jira_Server_URL` |
| 憑證 | `*_Token` / `*_Key` | `Gitlab_Access_Token` |
| 布林 | **字串** `"true"` / `"false"` | `"Visible": "true"` |
| 清單 | JSON array | `"Repo_List": ["a/b"]` |

每個功能區塊必備 `Program`（執行 Python 的指令）與 `Visible`
（非 `"true"` 時該 tab 會被移除；未設定時預設隱藏並記一筆警告）。

> **Token 直接放設定檔**，由每位使用者在自己電腦上填自己的值。
> 注意 `PPS2_0DevTool.json` 目前是被 git 追蹤的，加功能時小心不要把自己的 token commit 上去。

---

## 新增一個功能

1. 建立 `<功能名>.{h,cpp}`，一個 `QObject` 子類別，建構子用 `getFunctionConfig()` 取設定
2. 在 `pps2_0devtool.ui` 加一個 tab，標題就是功能名稱
3. 在 `setupToolService()` 建立實例；`UI_Init()` 依 `isFunctionVisible()` 決定是否
   `removeTabByTitle()`；`UI_SetupSignal()` 連接該 tab 的元件
4. 在 `PPS2_0DevTool.json` 的 `Function` 加設定區塊
5. 在 `PPS2_0DevTool.pro` 的 `SOURCES` / `HEADERS` 加檔案
6. 複製 `scripts/_function_template.py` 寫對應的腳本

**不需要修改 `json.cpp`。**

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

// 掛勾訊號（不需要來源路徑的功能不連接即可）
signals:
    void sourcePathChanged(const QString &sourceFilePath);
    void workingDataCleared();
```

呼叫的樣子：

```cpp
runFunctionScript("Log_Info", scriptPath, "get_log_info", params,
    [this](const PythonRunner::PythonRunnerResult &r) {
        if (!r.success) { showUI_ErrorMessageBox(r.message); return; }
        applyToUi(r.data);          // 只有這裡碰 UI
    });
```

### 三條必須遵守的規則

- **UI 只在收到 `PASS` 之後才變更。** 執行過程中不做任何逐筆更新，
  一律等結果到齊才一次套用。所以取消或失敗時畫面完全不動，沒有東西需要回捲。
- **取消時 callback 不會被呼叫。** 這是「取消後畫面不動」的物理保證，
  呼叫端不需要寫取消分支。
- **一次只能執行一支腳本。** 執行期間主視窗被鎖定；程式化的連續呼叫會回 `false`。

---

## 寫腳本

複製 `scripts/_function_template.py` 開始。範本原樣就能執行。

```python
#!/usr/bin/env python3
import script_io
from script_utils import logger
from script_utils import gitlab_utils      # 業務邏輯模組

TEMPLATE_VERSION = "2.0.0"
ACTION           = "get_gitlab_mr"
DESCRIPTION      = "取得指定 repo 的 merge request 清單"

def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[
            script_io.cfg("Gitlab_Server_URL",   required=True, help="GitLab 伺服器網址"),
            script_io.cfg("Gitlab_Access_Token", required=True, help="個人存取權杖"),
        ],
        params=[
            script_io.arg("repo", required=True, help="repo 完整路徑，例如 group/project"),
            script_io.arg("created_after_days", type=int, default=7,
                          help="只抓最近 N 天的 MR，-1 表示不限"),
        ],
    )

    cfg = req["config"]
    logger.info("查詢 %s", req["params"]["repo"])
    script_io.progress("呼叫 GitLab API")

    # 業務邏輯寫在 script_utils 裡，這裡只做轉接
    mrs = gitlab_utils.get_merge_requests(
        cfg["Gitlab_Server_URL"], cfg["Gitlab_Access_Token"],
        req["params"]["repo"],
        created_after_days=req["params"]["created_after_days"],
    )

    script_io.reply(message="共 %d 筆" % len(mrs), data={"merge_requests": mrs})

if __name__ == "__main__":
    script_io.run(main)
```

**入口腳本必須放在 `scripts/` 這一層，不能放子目錄** —— Python 只會把入口腳本
所在目錄放進 `sys.path`，放子目錄的話 `from script_utils import ...` 在沒設
`PYTHONPATH` 時會失敗，別人直接執行就壞掉。

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
