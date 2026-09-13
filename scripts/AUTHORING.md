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
| 要改寫的舊腳本 | 來源 |

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
需要知道呼叫方是誰就讀 `TOOLNAME` / `TOOLVERSION` 環境變數，而且要能在它們不存在時
正常運作（命令列執行時沒有）。

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
路徑**，兩個呼叫端對它來說長得一模一樣。

- **不要**把憑證宣告成 `cfg()` —— 那會讓使用者以為該填進 request 檔案裡，而那個檔案會
  留在 CI runner 的工作目錄
- **不要**把憑證當成命令列參數 —— 它會出現在工作管理員的行程清單上
- **不要**整包 log 出 `config` —— 合併後的 `config` 含有憑證，而 `Debug_Mode` 開啟時
  那一行會直接出現在 console 上。要 log 就只印你真正需要的鍵

目前約定的環境變數（鍵名的全大寫形式）：

```
GITLAB_SERVER_URL   GITLAB_ACCESS_TOKEN   GITLAB_VERIFY_SSL
JIRA_SERVER_URL     JIRA_ACCESS_TOKEN
```

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

```python
description = ai_analysis_gitlab_mr.resolve_text_input(params, "description")
```

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

## 4. 禁止清單

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
| 寫檔後回傳路徑取代 `data` | 未勾選除錯時呼叫端沒有東西可顯示 |
| 自己組 response JSON | 欄位大小寫或形狀對不上，解析失敗 |
| 用 try/except 包住 `main()` | 蓋掉 `script_io.run()` 的統一錯誤處理，exit code 變成 0 |
| 在 `script_utils/` 裡 `sys.exit()` | 當函式庫用時整個行程被拖走 |
| 刪掉 `sys.path.insert(...)` | 命令列與 CI 執行時匯不到模組 |
| 進度報告每筆資料一次 | 大量資料時 stderr 被灌爆，介面忙著重繪 |

---

## 5. AI 特別容易做錯的事

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

**log 用 `%s` 佔位符，不要用 f-string。**

```python
logger.debug("讀取 %s", path)        # ✓ 等級沒開就不付出格式化成本
logger.debug(f"讀取 {path}")         # ✗ 不論如何都先組好字串
```

**不要「順手改善」。** 轉換時不要加重試邏輯、不要加快取、不要把同步改非同步、不要
換掉 JSON 解析方式。這些改動會讓使用者的 review 變成「比對兩份不同的程式」，而不是
「確認介面換對了」。有想法就寫在轉換報告裡，不要直接動手。

**不要自己發明新的環境變數名。** 用第 3.5 節列出的那幾個。需要新的就在轉換報告裡提出。

---

## 6. 轉換指引：從舊式命令列腳本改寫

### 6.1 步驟

1. **先讀舊腳本，把它的介面寫下來** —— 每個位置參數是什麼、輸出到哪、回應長什麼樣
2. **把業務邏輯那一塊整段圈出來** —— 那部分原則上原樣搬過去
3. 從 `_function_template.py` 複製出新檔案，改三個常數
4. 依 6.2 把每個位置參數分類，寫成 `arg()` / 環境變數
5. 依 6.3 把輸出改成 `reply()` / `reply_fail()`
6. 把 `print()` 改成 `logger` 或 `progress()`
7. 把寫檔改成「`data` 必有、`out_path` 給了才落檔」
8. 依第 7 節自我檢查
9. 依第 8 節實際跑一遍
10. **寫一份轉換報告**（見 6.5）

### 6.2 位置參數 → 宣告式參數

每個舊參數問三個問題：

```
   是憑證或服務端點，而且跨功能共用？   -> 環境變數，不宣告成參數
   是這一次執行的輸入？                 -> script_io.arg()
   是輸出檔的路徑？                     -> arg("out_path") 或 arg("debug_dir")
   是「要不要寫檔」的布林，而且旁邊就有路徑參數？  -> 刪掉，用路徑是否為空取代
```

本專案已知的舊呼叫端簽章（取自 Qt 端 `AI_Analysis_Gitlab_MR_Summary` 的
`processARGs`），與它們各自的去處：

| # | 舊的位置參數 | 新的去處 |
|:--:|---|---|
| 1 | `_gitlabServerURL` | 環境變數 `GITLAB_SERVER_URL` |
| 2 | `_gitlabAccessToken` | 環境變數 `GITLAB_ACCESS_TOKEN` |
| 3 | `_jiraServerURL` | 環境變數 `JIRA_SERVER_URL` |
| 4 | `_jiraAccessToken` | 環境變數 `JIRA_ACCESS_TOKEN` |
| 5 | `AIModeName + ":" + AIModeURL` | **拆成兩個** `arg("ai_mode_name")`、`arg("ai_api_url")` |
| 6 | `AIAPI_Key` | `arg("ai_api_key")` |
| 7 | `_gitlabProjectID` | `arg("repo")`，改用 `namespace/project` 字串，腳本自己 URL-encode |
| 8 | `iid` | `arg("mr_iid")` |
| 9 | `gitlabJiraKeyInfo`（呼叫端已解析好 AUTO） | **拆成三個**：`arg("jira_mode")`、`arg("jira_key_manual")`、`arg("jira_key_detected")`，**解析搬進腳本** |
| 10 | `"True"` / `"False"`（要不要寫除錯檔） | **刪掉** —— 用 `debug_dir` 是否為空字串取代 |
| 11 | `saveAnalysisFilePath` | `arg("debug_dir", default="")` |
| 12 | `saveSummaryJsonFilePath` | `arg("out_path", default="")` |

三個要特別注意的：

**第 5 項的 `name:url` 合併字串要拆開。** 用分隔符號把兩個值塞進一個參數，遇到值本身
含有該符號時就會壞掉 —— 而 URL 裡本來就有 `:`。

**第 9 項的判斷要搬進腳本。** 舊的呼叫端做了這件事：

```cpp
gitlabJiraKeyInfo = (_gitlabJiraKeyInfo == "AUTO") ? scriptInfo.jiraKey : _gitlabJiraKeyInfo;
```

新架構把三個值原樣送進來，由腳本決定：

```python
def resolve_jira_key(mode, manual, detected):
    if mode == "manual":
        return manual
    if mode == "auto":
        return detected
    return ""
```

理由：判斷寫在呼叫端的話，CI 那條 shell 就得再實作一次同樣的分支，兩份必然漂移。

**第 10 項的布林是多餘的。** 「要不要寫」與「寫到哪裡」用同一個參數承載，就不會出現
「布林為真但路徑為空」這種矛盾狀態。

### 6.3 回應格式

舊的（呼叫端用 `outputObj["Result"]` 與 `outputObj["AI_Analysis"]` 讀）：

```json
{ "Result": "Pass", "AI_Analysis": "分析內容……" }
```

新的：

```python
script_io.reply(
    message="AI 分析完成",                      # 單行，給訊息框看
    detail="專案：%s\nMR：!%s" % (repo, iid),    # 多行，可有可無
    data={"summary": text},                     # 結構化結果，下一步從這裡取
)
```

對照：

| 舊 | 新 | 注意 |
|---|---|---|
| `"Result": "Pass"` | `reply()` | 新的是 `result` 小寫鍵、`PASS` 大寫值 |
| `"Result": "Fail"` | `reply_fail(message)` | 順帶把 exit code 變成 1 |
| `"AI_Analysis": "長文"` | `data={"summary": "長文"}` | **不要**放進 `message`，它必須是單行 |
| 失敗原因塞進 `AI_Analysis` | `reply_fail(message, detail=長文)` | 單行原因給 `message`，細節給 `detail` |
| 自己寫 `summary.json` 再讓呼叫端讀 | `data` 必有，`out_path` 給了才額外寫 | 兩者都做，不是二選一 |

### 6.4 哪些東西不要動

轉換的目標是**換掉介面，不是改寫業務邏輯**。以下原樣保留：

- prompt 的組法與內容
- 對 AI 供應商的請求格式（headers、body、端點路徑）
- 回應的解析方式
- 報告的排版與章節順序
- 任何演算法、門檻值、重試次數

使用者會拿舊輸出與新輸出比對。業務邏輯被「順手改善」過的話，差異就無法歸因了。

例外：如果業務邏輯裡有 `print()`、`sys.exit()` 或直接讀環境變數／設定檔，那幾行必須改
（見第 4 節）。改的時候只改那幾行，不要重構周邊。

### 6.5 不確定就問，不要猜

以下情況**停下來問使用者**，不要自己決定：

| 情況 | 要問什麼 |
|---|---|
| 舊腳本寫出多個輸出檔 | 哪一個是主要結果（進 `data`）？其餘是除錯產物嗎？ |
| 舊腳本用了 `requests` 以外的第三方套件 | 能不能用標準函式庫或 `requests` 替代？不能的話，部署端要怎麼安裝？ |
| 某個位置參數看不出用途 | 它是什麼？從哪來？ |
| 舊腳本讀了未列在 3.5 的環境變數 | 保留原名還是改成新約定？ |
| 業務邏輯裡有 `sys.exit()` | 那個結束是「業務失敗」還是「呼叫方式錯誤」？ |
| 舊腳本會寫入外部狀態（發 API、改檔案） | 重複執行同樣的輸入會不會產生重複的副作用？（流程可能重跑） |

最後一項尤其重要：這條管線的流程**不保證外部副作用的原子性**，中途失敗或取消時已經
發生的副作用不會被還原。所以參與流程的腳本必須可重入。

---

## 7. 自我檢查清單

改完之後逐項確認：

- [ ] `sys.path.insert(...)` 那一行在，而且在 `import script_io` 之前
- [ ] `TEMPLATE_VERSION` 保留
- [ ] `ACTION` 與 `DESCRIPTION` 改成這支腳本的
- [ ] 整份檔案搜尋 `print(` —— 應該一個都沒有
- [ ] 整份檔案搜尋 `sys.exit` —— 只有 `script_io` 內部該有，你的程式碼裡不該有
- [ ] 整份檔案搜尋 `basicConfig` —— 應該沒有
- [ ] `import` 區只有標準函式庫、`requests`、`script_io`、`script_utils`、以及本功能的 `__init__`
- [ ] 用到 `requests` 以外的第三方套件時，已在轉換報告中列出
- [ ] 沒有任何自訂的 `argparse` 旗標
- [ ] 憑證都從 `os.environ` 讀，而且缺了會給出點名該變數的失敗訊息
- [ ] 沒有任何一行把整包 `config` 傳給 logger
- [ ] 結果完整地放在 `data` 裡
- [ ] 沒給 `out_path` 時不寫任何檔案
- [ ] `message` 是單行
- [ ] 路徑都用 `os.path.join()`，開檔都有 `encoding="utf-8"`
- [ ] 進度有節流
- [ ] `if __name__ == "__main__": script_io.run(main)`

---

## 8. 怎麼驗證

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

## 9. 轉換報告

改完之後產出一份報告給使用者 review，包含：

1. **參數對照表** —— 每個舊的位置參數去了哪裡
2. **業務邏輯的改動** —— 理想上是「無」；有的話逐項列出原因（通常是為了移除 `print`
   或 `sys.exit`）
3. **無法判斷而做了假設的地方** —— 這一節最重要，使用者會優先看它
4. **建議但沒有動手的改善** —— 留給使用者決定
5. **驗證結果** —— 第 8 節那些指令的實際輸出
