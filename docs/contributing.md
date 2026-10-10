# 加一個功能、寫一支腳本

> 給要動這個專案的人：改完程式之後文件要跟著改哪裡、外殼提供哪些服務、
> 多步驟流程怎麼寫、信封長什麼樣、命令列怎麼跑、跨平台要注意什麼、
> 以及圖示資產怎麼重新產生。
>
> 腳本的**硬性規則**在 [`scripts/AUTHORING.md`](../scripts/AUTHORING.md)（992 行，
> 寫腳本之前先讀那一份）。這裡是它的 Qt 側對應物與摘要。
> 規格在 [`openspec/specs/`](../openspec/specs/)。

## 改完程式之後，文件要跟著改哪裡

四個檢查。每一條都是這個專案真的發生過的事，不是通則。

### ① 改了常數或版號 → grep 那個數字

```bash
grep -rn '2\.11' --include='*.md' .          # 改了 SCRIPT_VERSION 之後
```

文件裡抄了數字的地方不會自己更新。這個專案的文件已經因此過期三次
（`SCRIPT_VERSION`、`device/default` 的 `VERSION`、`CODE_REVIEW_SCHEMA_VERSION`）。

**寫文件時盡量不要抄數字。** 要抄就一併寫出它是哪個檔案的哪個常數，下一個人才知道
去哪裡對。

### ② 刪了一個欄位 → grep 那個欄位名

```bash
grep -rn 'Coverage' --include='*.md' .       # 移除了報告的涵蓋標示之後
```

只改「這一輪動到的檔案」會漏。那次移除漏掉了 README 三處與 live spec 一處，而它們
描述的是一個已經不存在的欄位。

### ③ 加了一個目錄或檔案 → 去最外層 README 的目錄樹登記

[最外層 README](../README.md) 的「目錄結構」那棵樹是新檔案的報到處。`ci/` 曾經漏登記
一輪，結果整份 README 沒有任何地方提到它存在。

### ④ 刻意「不做」某件事 → 寫一個 scenario 說它不做

規格只寫該做什麼的話，刻意的缺席看起來就只像是漏掉，下一輪有人就把它加回來了。

```
#### Scenario: 出處不帶涵蓋標示
- WHEN 報告產生出處那一段
- THEN 其中不含任何檔案數或涵蓋範圍的標示
```

正面寫下來之後，想改回去的人會先撞到這個 scenario。

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
        # 憑證不在 config 宣告 —— 它們走環境變數（見 AUTHORING 3.5）。
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

### 腳本的版號

**每一個功能都要宣告自己的名稱與版號**，放在該功能的套件裡（`scripts/<功能>/__init__.py`），
由該功能的所有入口腳本共用一份：

```python
SCRIPT_NAME    = "Single Building"
SCRIPT_VERSION = "2.0"
```

```
     2  .  0
     │     └── 第二碼：任何修改都 +1，包含只改註解或診斷文字
     └──────── 第一碼：重大修改才動，動的時候第二碼歸零
```

**兩碼而不是三碼**是刻意的：三碼的中間那一碼需要判斷「這算 minor 還是 patch」，而需要判斷
的規則就是會被漏掉的規則。兩碼沒有判斷餘地 —— 不是重大修改，就是 +1。

**各支腳本不各自宣告。** 同一個功能的入口腳本是同一次提交一起出去的，沒有「其中一支升級了
其他沒有」的情況；各自宣告的結果是數個數字要維護，而它們能回答的問題，一個已經回答了。

| | 回答什麼 | 範圍 | 什麼時候動 |
|---|---|---|---|
| `TEMPLATE_VERSION` | 請求與回應的信封長什麼樣 | **全專案**，所有功能同一個值 | 信封格式本身改了 |
| `SCRIPT_VERSION` | 這個功能的腳本是哪一版 | 單一功能 | 該功能每次修改 |

> ⚠️ **兩者不要共用一個宣告。** 把 `TEMPLATE_VERSION` 拿來當某個功能的版號，它就會隨那個
> 功能一直往上跳而其他功能停著不動 —— 兩個本該代表同一份信封格式的數字於是分岔，而它還會
> 被 `--dump-config` 印出去給呼叫端看。

**有擴充層的功能要多一個版號。** 例如 AI Analysis 的 device 機制：那一層由各產品線自己寫、
自己改，步調與通用層不同，所以它宣告自己的 `VERSION`，而**第一碼要與功能的通用版號一致** ——
讀的人一眼就看得出那份擴充是照哪一代的契約寫的。

**沒有任何機制強迫。** 改了但忘了更新版號，不會有任何東西擋你；第一碼不一致也不會讓執行
失敗（第一碼升級是功能維護者做的事，而擴充層可能由別人維護 —— 因為維護者升級就讓人家的環境
跑不起來，代價與收益不成比例）。呈現版號的地方一律**照實印出讀到的值**，不做驗證也不加標記。
這是明知的取捨。

**沒有報告可以承載版號的功能**（例如 Single Building，結果顯示在畫面上看完就關掉）**在每支
腳本開始時把它記進診斷輸出**：

```
[2026-10-02 11:28:17.805] [ PY INFO  ] Single Building 2.0
```

支援時問一句「console 第一行是什麼」就知道使用者手上跑的是哪一版。

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

`script_utils.logger` 提供 `debug` / `info` / `warn` / `error` / `set_verbose` /
`is_verbose`。它是**唯一**設定 logging 的地方，全部等級一律走 stderr。

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

- 路徑用 `os.path.join()`，**不要**自己串 `/` 或 `\\`
- 外部執行檔不要寫死 `.exe`
- 開檔一律明確指定 `encoding="utf-8"`
- `source_path` 由呼叫端決定風格，**不要假設分隔符號**

全專案用的是 `os.path`（`os.path.join` 15 處、`pathlib` 0 處）。兩套混用的話，
同一條路徑在不同模組裡會是字串與 `Path` 兩種型別，而接縫處的 bug 只在其中一個
平台出現。詳見 AUTHORING 3.10。

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
