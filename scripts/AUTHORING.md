# 腳本撰寫手冊

這份文件的讀者可能是人，也可能是 AI。它把散在 `openspec/specs/script-envelope/`、
`README.md` 與 `_function_template.py` 註解裡的規則收攏成一份可以整份交出去的東西。

**要一起交出去的檔案**：

| 檔案 | 為什麼需要 |
|---|---|
| 這份文件 | 規則與禁令 |
| `scripts/_function_template.py` | 骨架，所有新腳本從它複製 |
| `scripts/script_io.py` | 信封處理層的實際 API |
| `scripts/script_utils/logger.py` | 診斷輸出的唯一入口 |
| 要改寫的舊腳本（如果是轉換） | 來源 |

---

## 1. 為什麼規則長這樣

每一支腳本都同時服務三種呼叫端：

```
   Qt 工具          信封走 stdin，結果從 stdout 整段解析，進度走 stderr
   命令列使用者     --dump-config 產生模板，填好之後 --request run.json
   CI/CD 的 shell   環境變數帶憑證，檔案在步驟之間傳遞，看 exit code
```

規則大多是為了讓這三者同時成立。破壞其中一條通常不會讓腳本當掉 —— 它會讓**某一種
呼叫端**安靜地壞掉，而那正是最難查的一類問題。

---

## 2. 三十秒版

一支合格的腳本長這樣。從 `_function_template.py` 複製，改三個常數、列宣告、填實作區。

```python
#!/usr/bin/env python3
"""一句話說明這支腳本做什麼。"""

import os
import sys

# 入口腳本在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進 sys.path。
# 少了這一行，命令列直接執行時 script_io 與 script_utils 都匯不到。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import script_io
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "do_something"
DESCRIPTION      = "做某件事"


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[
            script_io.arg("thing", required=True, help="要處理的東西"),
            script_io.arg("out_path", default="", help="給了才落檔"),
        ],
    )

    params = req["params"]

    logger.info("開始處理 %s", params["thing"])     # -> stderr
    script_io.progress("處理中…")                   # -> stderr，對話框會顯示

    result = {"value": 42}                          # ← 實作區

    script_io.reply(
        message="完成",
        detail="細節可以多行",
        data=result,
    )


if __name__ == "__main__":
    script_io.run(main)
```

---

## 3. 硬性規則

### 3.1 通道分離

| 通道 | 唯一用途 |
|---|---|
| **stdout** | 那一份結果 JSON，**其餘什麼都不准有** |
| **stderr** | 診斷訊息、警告、進度 |

呼叫端把 stdout **整段**當成一個 JSON 物件解析，沒有退回掃描。多印一行 `print("done")`
就會讓整次執行被判定為「腳本沒有回傳結果」。

診斷一律用 `logger`，它已經接到 stderr 了。

### 3.2 信封契約

**Request**（呼叫端送進來）：

```json
{
  "source_path": "",
  "config": { },
  "action": "do_something",
  "params": { }
}
```

`config` 是呼叫端決定的不透明物件，腳本不解析它的階層。信封裡**沒有工具身分欄位** ——
需要知道呼叫方是誰就讀 `TOOLNAME` / `TOOLVERSION` 環境變數（見第 4 章），而且要能在
它們不存在時正常運作。

**Response**（腳本印出來）：

| 欄位 | 必填 | 說明 |
|---|:--:|---|
| `result` | 是 | 固定 `"PASS"` 或 `"FAIL"`，全大寫 |
| `message` | 是 | **單行**，訊息框、命令列、CI 日誌都直接用它 |
| `detail` | 否 | 多行說明 |
| `data` | 否 | 結構化結果 |
| `error` | 否 | 含 `code` 的物件，供呼叫端分流 |

不要自己組這個 JSON，用 `script_io.reply()` / `reply_fail()`。

**協定是加法式的**：呼叫端多送欄位就忽略，腳本多讀欄位而呼叫端沒送就用預設值。
兩端因此不需要同步改版。

### 3.3 參數與設定只宣告一次

```python
script_io.arg(name, type=str, default=None, required=False, help="")
script_io.cfg(name, required=False, help="")
```

這份宣告同時產生 `--help` 的說明與 `--dump-config` 的模板。**不要另外維護一份模板** ——
兩份一定會漂移，而這個專案過去就是因為程式讀的鍵與設定檔寫的鍵不一致而讓功能靜默失效。

`required=True` 的缺漏會在**進入業務邏輯之前**被擋下，訊息直接指出缺哪一個。

### 3.4 結束碼

| 情況 | 結束碼 | stdout |
|---|:--:|---|
| 成功 | 0 | `result` 為 `PASS` |
| 業務失敗 | 1 | `result` 為 `FAIL` |
| 呼叫方式錯誤 | 2 | 通常沒有 JSON（argparse 的慣例） |
| 未預期崩潰 | 非 0 | 沒有 JSON，追蹤訊息在 stderr |

exit code 給 CI 用，JSON 給圖形介面與人用，**兩者都要正確**。
`script_io.run(main)` 已經把未攔截的例外轉成 `FAIL` + exit 1，不要自己包一層 try/except
把例外吃掉。

### 3.5 憑證走環境變數

```python
token = os.environ.get("GITLAB_ACCESS_TOKEN", "")
if not token:
    script_io.reply_fail("未設定環境變數 GITLAB_ACCESS_TOKEN",
                         code="GITLAB_ACCESS_TOKEN_MISSING")
```

Qt 會從設定檔的 `Service` 區塊注入，CI 自行設定同名變數。腳本端因此**只有一條取值
路徑**，兩個呼叫端對它來說長得一模一樣。完整清單見第 4 章。

- **不要**把憑證宣告成 `cfg()` —— 那會讓使用者以為該填進 request 檔案裡，而那個檔案會
  留在 CI runner 的工作目錄
- **不要**把憑證當成命令列參數 —— 它會出現在工作管理員的行程清單上
- **不要**整包 log 出 `config` —— 合併後的 `config` 含有憑證，而 `Debug_Mode` 開啟時
  那一行會直接出現在 console 上。要 log 就只印你真正需要的鍵

### 3.6 輸出入雙軌

**輸出**：結果一律放進 `data`；`params` 給了輸出路徑時**額外**落檔。

```python
data = {"summary": text}
if params["out_path"]:
    write(params["out_path"], text)
script_io.reply(message="完成", data=data)
```

**MUST NOT** 改成「寫檔之後回傳路徑」。Qt 端不開檔案 —— 使用者沒有勾選產生除錯檔時，
根本沒有檔案可以開。

**輸入**：`params` 裡有內容就用內容，沒內容但有 `<key>_path` 就讀那個檔。

前者是 Qt 的走法（步驟之間直接傳內容），後者是 CI 的走法（bash 的原生貨幣是檔案）。
兩條都支援，腳本只多一個判斷。

### 3.7 進度回報

```python
script_io.progress("解析 log (37/128)")
```

- 走 stderr，一行一個 JSON，`progress()` 內部已經 flush（不 flush 的話訊息會堆到腳本
  結束才一次噴出，對話框文字全程不動）
- **自己節流**：呼叫端收到就更新、不過濾，跑幾千筆時不要每筆都報
- 要讓使用者看到筆數就寫進文字裡，**不要**增加數值欄位 —— 進度一律是跑馬燈

### 3.8 共用模組的四條規則

放進 `script_utils/` 的東西必須遵守：

1. **不印 stdout** —— 要輸出訊息用 `logger`
2. **不結束行程** —— 錯誤以例外拋出，是否結束由入口腳本決定
3. **不自行讀設定檔或環境變數** —— 所需的值由呼叫端明著傳入
4. **回傳資料結構，不回傳 JSON 字串** —— 序列化是入口腳本的職責

違反任何一條，該模組就無法被當作函式庫使用。

`script_utils/` 依**技術領域**分組（`system_utils`、`gitlab_utils`），不依應用功能分組。
只服務單一功能的邏輯留在 `scripts/<功能>/` 底下。

### 3.9 目錄與 sys.path

```
scripts/
  AUTHORING.md                   這份文件
  _function_template.py          範本，留在這一層，不屬於任何功能
  script_io.py                   信封處理層
  script_utils/                  共用模組，依技術領域分組
    logger.py
    system_utils/
    gitlab_utils/
  <功能>/                        入口腳本依功能分組
    __init__.py                  這個功能自己的共用定義
    <功能>_<動作>.py
```

入口腳本開頭那行 `sys.path.insert(...)` **不能刪**。Qt 會注入指向 `scripts/` 的
`PYTHONPATH`，但那不能當成前提 —— 命令列與 CI 直接執行時沒有那個環境，而那是本專案
明確支援的用法。症狀：在 Qt 裡跑得好好的，你自己下指令跑就 `ModuleNotFoundError`。

### 3.10 跨平台

- 路徑用 `os.path.join()`，**不要**自己串 `\\` 或 `/`
- 開檔一律明著寫 `encoding="utf-8"`
- 外部執行檔名稱**不要**寫死副檔名
- `source_path` 由呼叫端決定風格，不要假設分隔符號

### 3.11 相依套件

| 套件 | 可用性 |
|---|---|
| 標準函式庫 | 一律可用，**優先** |
| `requests` | **可用** |
| 其他第三方套件 | 停下來問使用者，不要自己決定 |

本專案沒有相依清單檔（`requirements.txt` 之類），Windows 端的建置流程是「拿到專案用
Qt Creator 開啟即可」。因此每多一個套件，就是替部署與 CI 各多一個安裝步驟 —— 這不是
禁止，是要有人**知道**它發生了。用了 `requests` 以外的套件，在轉換報告裡明著列出來。

**不要把既有模組改成 `requests`。** `script_utils/gitlab_utils/` 刻意用 `urllib` 寫成，
因為它只需要一個帶標頭的 GET，沒有理由讓那條路徑也長出相依。看到專案裡兩種寫法並存
是正常的，不要「統一」它們。

---

## 4. 可以使用的環境變數

腳本從自己的程式碼裡看不出呼叫端塞了什麼進來，所以這一章列出**你可以預期拿到什麼**。

### 4.1 外殼一定會注入的

每一支由 Qt 啟動的腳本都有這五個：

| 變數 | 值 | 你會用到它嗎 |
|---|---|---|
| `PYTHONPATH` | 原有值附加執行檔目錄下的 `scripts/` | **不要依賴它**（見 3.9） |
| `PYTHONUTF8` | `1` | 不用直接讀；它讓 Windows 上的中文輸出不亂碼 |
| `PYTHONUNBUFFERED` | `1` | 不用直接讀；它讓進度即時送達 |
| `TOOLNAME` | `PPS 2.0 DevTool` | 需要知道呼叫方身分時 |
| `TOOLVERSION` | `v2.0.0` | 同上 |

**命令列與 CI 執行時這五個都不存在。** 所以：

```python
tool_name = os.environ.get("TOOLNAME", "")      # ✓ 一定要給預設值
tool_name = os.environ["TOOLNAME"]              # ✗ 命令列執行時直接 KeyError
```

`PYTHONUTF8` 與 `PYTHONUNBUFFERED` 不存在也沒關係 —— `script_io` 在載入時會自己把
stdout / stderr 重設成 UTF-8，而 `progress()` 每次都自己 flush。

### 4.2 功能注入的服務設定

功能會把設定檔 `Service` 區塊裡的值注入為環境變數，**變數名是設定鍵名的全大寫形式**：

```
Gitlab_Access_Token   ->   GITLAB_ACCESS_TOKEN
Jira_Server_URL       ->   JIRA_SERVER_URL
```

目前已經約定的：

| 變數 | 內容 | 沒設定時 |
|---|---|---|
| `GITLAB_SERVER_URL` | GitLab 的位址，例如 `https://gitlab.example.com` | 腳本應回傳失敗並點名這個變數 |
| `GITLAB_ACCESS_TOKEN` | personal access token | 同上 |
| `GITLAB_VERIFY_SSL` | `true` / `false`，**未設定視為 `false`**（不驗證） | 視為不驗證 |
| `JIRA_SERVER_URL` | JIRA 的位址 | 需要時回傳失敗並點名 |
| `JIRA_ACCESS_TOKEN` | JIRA 的存取權杖 | 同上 |

布林值記得自己轉換 —— `bool("false")` 在 Python 裡是 `True`：

```python
def truthy(text):
    return str(text).strip().lower() in ("true", "1", "yes")

verify_ssl = truthy(os.environ.get("GITLAB_VERIFY_SSL", "false"))
```

**缺了要給可行動的訊息。** `script_io` 的必填檢查只看 `params` 與 `config`，看不到環境
變數，所以這一段要自己寫：

```python
if not token:
    script_io.reply_fail(
        "未設定環境變數 GITLAB_ACCESS_TOKEN",
        detail="設定檔的 Service.Gitlab_Access_Token 會由工具注入為這個環境變數；"
               "以命令列執行時請自行設定。",
        code="GITLAB_ACCESS_TOKEN_MISSING")
```

不寫的話，症狀會是拿著空字串去打 API 然後收到 401，而 401 的第一直覺是「權杖過期」——
使用者會去重發一把新的，找錯方向。

### 4.3 系統環境會原樣繼承

腳本行程繼承整個系統環境，所以這些照常有效，不需要任何特別處理：

| 變數 | 效果 |
|---|---|
| `SSL_CERT_FILE` | `urllib` 與 `requests` 會拿它當受信任的 CA 憑證 |
| `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY` | 兩者都會自動遵守 |
| `TEMP` / `TMPDIR` | `tempfile.gettempdir()` 的來源 |
| `PATH` | 呼叫外部執行檔時 |

### 4.4 詳細輸出旗標

`Debug_Mode` 為 true 時，外殼會在命令列附上 `-v`，`script_io` 收到之後把 logger 的等級
從 INFO 降到 DEBUG。這不是環境變數，但效果相同：**`logger.debug()` 的內容會出現在
使用者的 debug console 上**。憑證不要進 `logger.debug()`。

### 4.5 要新增一個環境變數

四個地方都要動，少一個就會變成「只有我的機器上能跑」：

1. `PPS2_0DevTool.example.json` 的 `Service` 區塊加鍵
2. 功能的 `serviceEnvVars()` 那張鍵名清單加一筆（C++ 端）
3. 這份文件 4.2 的表格補一列
4. CI/CD 的設定加同名變數

**不要自己發明名字然後只在腳本裡讀** —— 沒有人會知道要設它，而症狀是在別人的機器上
才出現的失敗。需要新變數就在轉換報告或 PR 說明裡提出來。

---

## 5. 建立一支新腳本：完整範例

假設要新增一個叫 `MR Report` 的功能，第一支腳本是「統計某個專案的 Merge Request，
依作者分組」。

> 底下的程式碼**實際跑過**，不是虛擬碼。它呼叫的 `gitlab_utils.list_merge_requests()`
> 是這個專案裡真實存在的函式。

### 5.1 先看 `script_utils/` 裡有什麼

**動手寫之前先翻一遍共用模組。** 這一步最常被跳過，結果是同一個能力被實作第二次，
而兩份實作的錯誤處理通常不一樣。

```
script_utils/
  system_utils/     列目錄、行式文字檔的讀寫、暫存檔路徑
  gitlab_utils/     GitLab REST
    list_merge_requests(server_url, token, project,
                        only_open=True, created_after_days=None,
                        verify_ssl=True, limit=PER_PAGE_LIMIT)
        -> {"merge_requests": [...], "truncated": bool}
        每一筆：iid / title / author / created_at / state / web_url
        失敗時拋出 GitLabAuthError / GitLabNotFoundError / GitLabTlsError /
                   GitLabHttpError / GitLabConnectionError
                   （都繼承自 GitLabError）
```

這次要的東西已經有了，所以這支腳本只做轉接：收信封 → 呼叫它 → 整理 → 回信封。

### 5.2 建立目錄與功能專屬定義

```
scripts/mr_report/
  __init__.py
  mr_report_summarise.py
```

`__init__.py` 放這個功能自己的東西。跨功能的能力不放這裡，放 `script_utils/`：

```python
#!/usr/bin/env python3
"""MR Report 的功能專屬定義。"""

import json
import os

__all__ = ["write_artifact"]


def write_artifact(out_path, content):
    """把內容寫到 out_path。out_path 為空就什麼都不做。"""
    if not out_path:
        return False

    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2)

    directory = os.path.dirname(os.path.abspath(out_path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    return True
```

### 5.3 複製範本，改三個常數

```bash
cp scripts/_function_template.py scripts/mr_report/mr_report_summarise.py
```

**複製，不要從零手寫，也不要從別的功能的腳本抄。** 範本裡有幾樣東西看起來可有可無，
其實不能少：那行 `sys.path.insert`、`TEMPLATE_VERSION` 常數、以及 `script_io.run(main)`
這個統一的錯誤處理入口。

```python
TEMPLATE_VERSION = "2.0.0"          # 保留範本原本的值，不要改
ACTION           = "summarise_merge_requests"
DESCRIPTION      = "統計指定專案的 Merge Request，依作者分組"
```

`TEMPLATE_VERSION` 是「這支腳本依據哪一版範本寫的」，日後範本改版時靠它辨識哪些腳本
需要跟進。它不是你這支腳本的版本號。

### 5.4 完整的腳本

```python
#!/usr/bin/env python3
"""MR Report —— 統計指定專案的 Merge Request。

    python mr_report_summarise.py --help
    python mr_report_summarise.py --dump-config > run.json
    python mr_report_summarise.py --request run.json

憑證走環境變數，不放進 request 檔案 —— 那個檔案會留在 CI runner 的工作目錄：

    GITLAB_SERVER_URL    https://gitlab.example.com
    GITLAB_ACCESS_TOKEN  glpat-...
    GITLAB_VERIFY_SSL    true / false（未設定視為 false，即不驗證）
"""

import os
import sys

# 入口腳本放在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進 sys.path。
# 少了這一行，命令列直接執行時 script_io 與 script_utils 都匯不到。Qt 會注入指向
# scripts/ 的 PYTHONPATH，但那不能當成前提。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mr_report
import script_io
from script_utils import gitlab_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "summarise_merge_requests"
DESCRIPTION      = "統計指定專案的 Merge Request，依作者分組"


def truthy(text):
    """環境變數的布林轉換。bool("false") 在 Python 裡是 True，不能直接轉。"""
    return str(text).strip().lower() in ("true", "1", "yes")


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,

        # 憑證不在這裡宣告 —— 它們走環境變數。在 config 宣告會讓使用者以為
        # 該把權杖填進 request 檔案裡。
        config=[],

        params=[
            script_io.arg("repo", required=True,
                          help="專案，namespace/project 形式"),
            script_io.arg("only_open", type=bool, default=True,
                          help="只統計尚未關閉的 Merge Request"),
            script_io.arg("created_after_days", type=int, default=30,
                          help="只統計這麼多天內建立的"),
            script_io.arg("out_path", default="",
                          help="額外把統計結果寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]

    # --- 環境變數：憑證只從這裡讀 ---
    server_url = os.environ.get("GITLAB_SERVER_URL", "").strip()
    token      = os.environ.get("GITLAB_ACCESS_TOKEN", "").strip()
    verify_ssl = truthy(os.environ.get("GITLAB_VERIFY_SSL", "false"))

    if not server_url:
        script_io.reply_fail(
            "未設定環境變數 GITLAB_SERVER_URL",
            detail="設定檔的 Service.Gitlab_Server_URL 會由工具注入為這個環境"
                   "變數；以命令列執行時請自行設定。",
            code="GITLAB_SERVER_URL_MISSING")

    if not token:
        script_io.reply_fail(
            "未設定環境變數 GITLAB_ACCESS_TOKEN",
            detail="設定檔的 Service.Gitlab_Access_Token 會由工具注入為這個"
                   "環境變數；以命令列執行時請自行設定。",
            code="GITLAB_ACCESS_TOKEN_MISSING")

    # reply_fail() 內部會 sys.exit()，走到這裡代表兩個值都有。

    logger.info("查詢 %s 的 Merge Request（only_open=%s, days=%d）",
                repo, params["only_open"], params["created_after_days"])
    script_io.progress("向 GitLab 查詢 Merge Request…")

    # --- 呼叫共用模組 ---
    #
    # 權杖與 verify_ssl 都由這裡明著傳進去 —— 共用模組不自行讀環境變數，
    # 所以同一個函式在任何機器上以相同參數呼叫，行為都一樣。
    try:
        result = gitlab_utils.list_merge_requests(
            server_url=server_url,
            token=token,
            project=repo,
            only_open=params["only_open"],
            created_after_days=params["created_after_days"],
            verify_ssl=verify_ssl,
        )
    except gitlab_utils.GitLabAuthError as exc:
        # 權杖與專案的失敗訊息刻意不同：使用者的下一步完全不一樣，
        # 一個去換權杖，一個去改設定檔的拼字。
        script_io.reply_fail(
            "GitLab 拒絕了這次請求，請檢查存取權杖",
            detail="%s\n\n權杖來自環境變數 GITLAB_ACCESS_TOKEN。" % exc,
            code="GITLAB_AUTH_FAILED")
    except gitlab_utils.GitLabNotFoundError as exc:
        script_io.reply_fail(
            "找不到專案 %s" % repo,
            detail="%s\n\n請檢查專案名稱是否為正確的 namespace/project 形式。"
                   "\n注意：權杖若對該專案沒有權限，GitLab 也會回 404。" % exc,
            code="GITLAB_PROJECT_NOT_FOUND")
    except gitlab_utils.GitLabTlsError as exc:
        script_io.reply_fail(
            "TLS 憑證驗證失敗",
            detail="%s\n\n把受信任的 CA 憑證指給 SSL_CERT_FILE，或把設定檔的"
                   "Service.Gitlab_Verify_SSL 設為 \"false\"。" % exc,
            code="GITLAB_TLS_FAILED")
    except gitlab_utils.GitLabError as exc:
        # 其餘的 GitLab 錯誤（HTTP、連線）收在這裡。
        # 不要 except Exception —— 那會蓋掉 script_io.run() 的統一處理。
        script_io.reply_fail("GitLab 查詢失敗：%s" % exc,
                             code="GITLAB_REQUEST_FAILED")

    items = result["merge_requests"]

    # --- 業務邏輯：依作者分組 ---
    script_io.progress("整理統計…")

    by_author = {}
    for item in items:
        author = item["author"] or "(未知)"
        by_author[author] = by_author.get(author, 0) + 1

    summary = {
        "repo": repo,
        "total": len(items),
        "by_author": by_author,
        "truncated": result["truncated"],
    }

    logger.info("共 %d 筆，%d 位作者", len(items), len(by_author))

    # --- 輸出雙軌：data 必有，out_path 給了才額外落檔 ---
    mr_report.write_artifact(params["out_path"], summary)

    message = "共 %d 筆 Merge Request，%d 位作者" % (len(items), len(by_author))
    if result["truncated"]:
        message += "（已達單次取回上限 %d，結果可能未完整）" \
                   % gitlab_utils.PER_PAGE_LIMIT

    # 取回 0 筆是成功而非失敗 —— 條件太緊是正常結果。
    script_io.reply(
        message=message,
        detail="專案：%s" % repo,
        data=summary,
    )


if __name__ == "__main__":
    script_io.run(main)
```

### 5.5 這支腳本示範了什麼

| 位置 | 規則 |
|---|---|
| 開頭的 `sys.path.insert` | 3.9 —— 不能刪 |
| `config=[]` | 3.5 —— 憑證不宣告成設定鍵 |
| `os.environ.get(..., "")` | 4.1 —— 一定要給預設值 |
| `truthy()` | 4.2 —— 環境變數的布林要自己轉 |
| 缺憑證時 `reply_fail` 並點名變數 | 4.2 —— 不寫的話症狀是 401，使用者會去查權杖有沒有過期 |
| 三個 `except` 分開處理 | 失敗訊息不同，因為使用者的下一步不同 |
| `except gitlab_utils.GitLabError` 收尾 | 6 —— **不要** `except Exception`，那會蓋掉 `script_io.run()` 的統一處理 |
| `write_artifact(params["out_path"], ...)` | 3.6 —— 沒給路徑就不寫檔 |
| `data=summary` | 3.6 —— 結果一律進 `data` |
| 0 筆回 `reply()` 而非 `reply_fail()` | 條件太緊是正常結果，不是錯誤 |

### 5.6 什麼時候該新增共用模組

上面沒有新增任何共用模組，因為要的能力已經有了。**判斷的問題是：第二個功能會不會
需要它？**

- 會 → 放 `script_utils/<技術領域>/`，並遵守 3.8 的四條規則
- 不會 → 留在 `scripts/<功能>/`

分組依**技術領域**（`system_utils`、`gitlab_utils`），不依應用功能。依功能分組的話，
第二個功能需要同一個能力時就無處可放。

新增共用模組時，錯誤要以**可區分的例外型別**拋出，不要全部塞進一個 `Exception` ——
入口腳本要靠型別給出不同的訊息（見 5.4 那三個 `except`）。

### 5.7 接進 Qt（由 C++ 那一側做）

腳本寫完之後，功能那一側要：

1. 在功能的 `.cpp` 裡加一個腳本路徑常數（**寫死，不放設定檔**）
2. 呼叫 `runFunctionScript()`，把參數放進 `QJsonObject`
3. **記得帶上 `serviceEnvVars()`** —— 它是帶預設值的參數，漏了不會有編譯錯誤，
   腳本會拿到空的憑證然後回報「未設定環境變數」，看起來像使用者沒設定

### 5.8 驗證

見第 10 章。上面那支腳本實際跑過這幾條：

```
--help                        成功
--dump-config                 模板含 _template_version 與四個參數
缺 GITLAB_SERVER_URL          FAIL，code = GITLAB_SERVER_URL_MISSING
缺必填的 repo                 FAIL，訊息為「缺少必填項目：參數 repo」
伺服器位址不存在              FAIL，code = GITLAB_REQUEST_FAILED
權杖無效（真的打 gitlab.com） FAIL，code = GITLAB_AUTH_FAILED
```

每一條的 stdout 都只有一個 JSON 物件，exit code 都是 1（除了前兩條）。

---

## 6. 禁止清單

每一條都附症狀。症狀比禁令重要 —— 知道會壞成什麼樣，就不會想繞過去。

| MUST NOT | 症狀 |
|---|---|
| `print()` 任何東西到 stdout | 整次執行被判定「腳本沒有回傳結果」，看不出原因 |
| 自訂命令列旗標承載功能參數 | Qt 這條管線不會傳它們，參數永遠是預設值 |
| `logging.basicConfig()` | 與 `script_utils/logger` 各設一次，訊息重複輸出 |
| 引入 `requests` 以外的第三方套件而未先詢問 | 部署與 CI 各多一個安裝步驟，而沒有人知道 |
| 把既有的 `gitlab_utils` 改寫成 `requests` | 替一條原本沒有相依的路徑長出相依 |
| 憑證進 `cfg()` 或命令列 | 明文留在 CI runner 的檔案裡，或出現在行程清單上 |
| `logger.debug("cfg=%r", cfg)` | 權杖被印進 debug console 與 `crash.log` |
| `os.environ["TOOLNAME"]` 不給預設值 | 命令列執行時 `KeyError` |
| 寫檔後回傳路徑取代 `data` | 未勾選除錯時呼叫端沒有東西可顯示 |
| 自己組 response JSON | 欄位大小寫或形狀對不上，解析失敗 |
| 用 try/except 包住 `main()` | 蓋掉 `script_io.run()` 的統一錯誤處理，exit code 變成 0 |
| 在 `script_utils/` 裡 `sys.exit()` | 當函式庫用時整個行程被拖走 |
| 在 `script_utils/` 裡讀環境變數 | 同一個函式在不同機器上行為不同，無法當函式庫用 |
| 刪掉 `sys.path.insert(...)` | 命令列與 CI 執行時匯不到模組 |
| 進度報告每筆資料一次 | 大量資料時 stderr 被灌爆，介面忙著重繪 |

---

## 7. AI 特別容易做錯的事

以下都是「看起來完全正常、而且是業界常見寫法」的東西，在這個專案裡是錯的。

**`reply()` 與 `reply_fail()` 不會回傳。** 它們內部呼叫 `sys.exit()`。所以：

```python
if not token:
    script_io.reply_fail("沒有權杖")
    return                          # ← 這行永遠不會執行，刪掉
```

反過來也成立 —— 你可以用它們做提前返回，不需要 `else`：

```python
if not params["fetch_data"]:
    script_io.reply(message="未要求取得資料", data={"content": ""})

# 走到這裡代表 fetch_data 為真
```

**`_is_missing()` 把空字串當成沒給。** `script_io` 判斷參數是否缺漏的規則是「`None`
或只有空白的字串」。所以一個預設值非空的參數，呼叫端傳空字串進來會拿到預設值而不是
空字串。需要「明確傳空」的語意時，預設值就設成空字串。

**布林的字串轉換是特別處理過的。** `"false"` / `"0"` / `"no"` / `""` 都會變成 `False`
（`bool("false")` 在 Python 裡是 `True`，所以不能直接轉）。宣告時寫 `type=bool` 就好。
但**環境變數要自己轉** —— `script_io` 碰不到它們。

**log 用 `%s` 佔位符，不要用 f-string。**

```python
logger.debug("讀取 %s", path)        # ✓ 等級沒開就不付出格式化成本
logger.debug(f"讀取 {path}")         # ✗ 不論如何都先組好字串
```

**不要「順手改善」。** 不要加重試邏輯、不要加快取、不要把同步改非同步、不要換掉 JSON
解析方式。這些改動會讓使用者的 review 變成「比對兩份不同的程式」，而不是「確認介面
換對了」。有想法就寫在報告裡，不要直接動手。

**不要自己發明新的環境變數名。** 用第 4 章列出的那些。需要新的就提出來（見 4.5）。

---

## 8. 轉換指引：從舊式命令列腳本改寫

### 8.1 步驟

1. **先讀舊腳本，把它的介面寫下來** —— 每個位置參數是什麼、輸出到哪、回應長什麼樣
2. **把業務邏輯那一塊整段圈出來** —— 那部分原則上原樣搬過去
3. 從 `_function_template.py` 複製出新檔案，改三個常數
4. 依 8.2 把每個位置參數分類，寫成 `arg()` 或環境變數
5. 依 8.3 把輸出改成 `reply()` / `reply_fail()`
6. 把 `print()` 改成 `logger` 或 `progress()`
7. 把寫檔改成「`data` 必有、`out_path` 給了才落檔」
8. 依第 9 章自我檢查
9. 依第 10 章實際跑一遍
10. **寫一份轉換報告**（見第 11 章）

### 8.2 位置參數 → 宣告式參數

每個舊參數問這幾個問題，依序套用第一個成立的：

```
   是憑證或服務端點，而且跨功能共用？       -> 環境變數，不宣告成參數（見 4.2）
   是「要不要寫檔」的布林，而旁邊就有路徑？ -> 刪掉，用路徑是否為空取代
   是輸出檔的路徑？                         -> arg("out_path") / arg("debug_dir")
   是這一次執行的輸入？                     -> script_io.arg()
```

三個比單純改名更需要注意的模式：

**合併字串要拆開。** 舊腳本常把兩個值用分隔符號塞進一個參數（例如 `名稱:網址`）。
拆成兩個參數 —— 值本身含有那個符號時就會壞掉，而 URL 裡本來就有 `:`。

**呼叫端先解析好的選擇，要把解析搬進腳本。** 舊架構常見這種寫法：呼叫端有三個模式，
它先選好其中一個值再傳進來。新架構要把**三個值原樣送進來**，由腳本決定：

```python
def resolve_key(mode, manual, detected):
    if mode == "manual":
        return manual
    if mode == "auto":
        return detected
    return ""
```

理由：判斷寫在呼叫端的話，CI 那條 shell 就得再實作一次同樣的分支，兩份必然漂移。

**與路徑並存的布林開關是多餘的。** 「要不要寫」與「寫到哪裡」用同一個參數承載
（路徑非空 = 要寫），就不會出現「布林為真但路徑為空」這種矛盾狀態。

### 8.3 回應格式

舊腳本常見的自訂格式（欄位名與大小寫各式各樣）：

```json
{ "Result": "Pass", "Content": "一大段文字……" }
```

對照到信封格式：

| 舊 | 新 | 注意 |
|---|---|---|
| 自訂的成功旗標 | `script_io.reply(...)` | 新的是 `result` 小寫鍵、`PASS` 大寫值 |
| 自訂的失敗旗標 | `script_io.reply_fail(message)` | 順帶把 exit code 變成 1 |
| 頂層的長文欄位 | `data={"<名稱>": "長文"}` | **不要**放進 `message`，它必須是單行 |
| 失敗原因塞進內容欄位 | `reply_fail(message, detail=長文)` | 單行原因給 `message`，細節給 `detail` |
| 自己寫檔再讓呼叫端讀 | `data` 必有，`out_path` 給了才額外寫 | 兩者都做，不是二選一 |

### 8.4 哪些東西不要動

轉換的目標是**換掉介面，不是改寫業務邏輯**。以下原樣保留：

- prompt 的組法與內容
- 對外部服務的請求格式（headers、body、端點路徑）
- 回應的解析方式
- 報告的排版與章節順序
- 任何演算法、門檻值、重試次數

使用者會拿舊輸出與新輸出比對。業務邏輯被「順手改善」過的話，差異就無法歸因了。

例外：業務邏輯裡如果有 `print()`、`sys.exit()` 或直接讀設定檔，那幾行必須改（見第 6
章）。改的時候只改那幾行，不要重構周邊。

### 8.5 不確定就問，不要猜

以下情況**停下來問使用者**：

| 情況 | 要問什麼 |
|---|---|
| 舊腳本寫出多個輸出檔 | 哪一個是主要結果（進 `data`）？其餘是除錯產物嗎？ |
| 舊腳本用了 `requests` 以外的第三方套件 | 能不能用標準函式庫或 `requests` 替代？不能的話部署端怎麼安裝？ |
| 某個位置參數看不出用途 | 它是什麼？從哪來？ |
| 舊腳本讀了未列在 4.2 的環境變數 | 保留原名還是改成新約定？ |
| 業務邏輯裡有 `sys.exit()` | 那個結束是「業務失敗」還是「呼叫方式錯誤」？ |
| 舊腳本會寫入外部狀態（發 API、改檔案） | 重複執行同樣的輸入會不會產生重複的副作用？ |

最後一項尤其重要：這條管線的流程**不保證外部副作用的原子性**，中途失敗或取消時已經
發生的副作用不會被還原。所以參與流程的腳本必須可重入。

---

## 9. 自我檢查清單

- [ ] `sys.path.insert(...)` 那一行在，而且在 `import script_io` 之前
- [ ] `TEMPLATE_VERSION` 保留
- [ ] `ACTION` 與 `DESCRIPTION` 改成這支腳本的
- [ ] 整份檔案搜尋 `print(` —— 應該一個都沒有
- [ ] 整份檔案搜尋 `sys.exit` —— 只有 `script_io` 內部該有，你的程式碼裡不該有
- [ ] 整份檔案搜尋 `basicConfig` —— 應該沒有
- [ ] `import` 區只有標準函式庫、`requests`、`script_io`、`script_utils`、本功能的 `__init__`
- [ ] 用到 `requests` 以外的第三方套件時，已在報告中列出
- [ ] 沒有任何自訂的 `argparse` 旗標
- [ ] 憑證都從 `os.environ` 讀，而且缺了會給出點名該變數的失敗訊息
- [ ] 所有 `os.environ` 的讀取都有預設值
- [ ] 環境變數的布林值有自己轉換，沒有直接當成 `bool`
- [ ] 沒有任何一行把整包 `config` 傳給 logger
- [ ] 結果完整地放在 `data` 裡
- [ ] 沒給 `out_path` 時不寫任何檔案
- [ ] `message` 是單行
- [ ] 路徑都用 `os.path.join()`，開檔都有 `encoding="utf-8"`
- [ ] 進度有節流
- [ ] `if __name__ == "__main__": script_io.run(main)`

---

## 10. 怎麼驗證

四種操作都要成功：

```bash
python scripts/<功能>/<腳本>.py --help
python scripts/<功能>/<腳本>.py --dump-config > run.json
python scripts/<功能>/<腳本>.py --request run.json
echo '{"action":"x","params":{...}}' | python scripts/<功能>/<腳本>.py --request-stdin
```

**刻意不要設定 `PYTHONPATH`** —— 可匯入性是入口腳本自己的責任，設了就測不出 3.9 那條
規則有沒有被遵守。

三個容易漏掉的檢查：

```bash
# stdout 必須是單一 JSON：這行應該印出 True
python <腳本> --request-stdin < req.json | python -c "import json,sys; json.load(sys.stdin); print(True)"

# 缺必填參數時要指名道姓
echo '{"params":{}}' | python <腳本> --request-stdin

# 缺憑證時要點名環境變數，而不是報一個看不懂的錯
GITLAB_ACCESS_TOKEN= python <腳本> --request run.json
```

最後跑一次完整的端到端：在 Qt 工具裡按下對應的按鈕，確認結果視窗有內容、進度文字
會動、取消鈕有效。

---

## 11. 報告

新增或轉換完成之後產出一份報告給使用者 review，包含：

1. **參數對照表** —— 每個輸入從哪來（`params` / 環境變數），轉換的話再加上它原本是什麼
2. **業務邏輯的改動** —— 理想上是「無」；有的話逐項列出原因（通常是為了移除 `print`
   或 `sys.exit`）
3. **無法判斷而做了假設的地方** —— 這一節最重要，使用者會優先看它
4. **新增的環境變數或第三方套件** —— 有的話一定要列，它們是部署端要跟著做的事
5. **建議但沒有動手的改善** —— 留給使用者決定
6. **驗證結果** —— 第 10 章那些指令的實際輸出
