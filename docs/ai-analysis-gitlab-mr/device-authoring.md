# 寫自己的 device

> 怎麼讓一條產品線有自己的分析邏輯與報告版面：兩個產物的格式、AI 客戶端、prompt、
> 鉤子收到的素材、device 與 type 兩個軸，以及新增一個 device 的步驟。
>
> 功能本身的畫面與行為在 [README.md](README.md)。鉤子的**權威**輸入規格是
> [`scripts/ai_analysis_gitlab_mr/device/_template/`](../../scripts/ai_analysis_gitlab_mr/device/_template/)
> 各檔的 docstring —— 這份文件講的是為什麼，範本講的是確切的鍵名。

## `03_summary.json` 的格式

步驟 3 的產物是結構，不是排好版的文字；渲染由步驟 5 負責。

````json
{
  "schema_version": 7,
  "analysis": {
    "model": "gpt-4o",
    "mr_type": "bug",
    "jira_key": "PPS-1234",
    "jira_state": "ok",
    "jira_url": "https://jira.example.com/browse/PPS-1234",
    "overview": "本次修改把重試上限從 3 調高到 10。",
    "mrDiff": {
      "cpp/test.cpp": [
        { "title": "...", "reason": "...",
          "hunkHeader": "@@ -12,7 +12,7 @@",
          "diffCode": "@@ -12,7 +12,7 @@..." }
      ]
    },
    "coverage": {
      "files_changed": 90,
      "files_sent": 21,
      "files_reported": 3,
      "truncated": true,
      "bytes_total": 496320,
      "bytes_sent": 120000,
      "dropped": { "count": 69, "paths": ["cpp/big01.cpp"] },
      "empty":   { "count": 0,  "paths": [] },
      "missing": { "count": 18, "paths": ["cpp/a.cpp"] },
      "unknown": { "count": 0,  "paths": [] },
      "skipped": { "count": 2,  "paths": ["cfg/strings.json"] }
    }
  }
}
````

- 每個檔案**直接對一個 finding 清單**，中間沒有包一層。要講整個檔案就放清單的第一筆、
  不給 `diffCode`
- **清單可以是空的**，意思是「這個檔案看過了，沒有值得注意的地方」。它算**已回報**
  （不進 `coverage.missing`），而報告渲染時整個略過，編號也不跳號。這是「明說沒問題」與
  「根本沒提」唯一的區別方式
- `jira_state` 是 `ok` / `none` / `invalid` 三選一。`invalid` 時 `jira_key` 留的是
  **被拒絕的原值**（例如標題第一個方括號放的是 `WIP`），但它只留在產物的資料裡 ——
  `invalid` 時「詳細資料」那一節整個不出現，所以**報告上看不到**（出處也不印它，見 [README.md](README.md) 的「報告的版面」一節）
- `model` 留在資料裡供其他消費者使用，**不進報告**
- `mr_type` 是這一筆的種類，決定步驟 5 用哪一份版面；沒有種類時是空字串。它由**入口
  腳本蓋章**，device 的鉤子不必填（填了也會被覆蓋）
- 某個檔案的清單為空時，該檔案整個不出現，編號也只算實際出現的檔案
- `coverage` 是這次分析涵蓋了多少（見上一節）。四類缺口加上 `skipped`（版本 7 起）各自
  有精確的 `count` 與一份有長度上限的 `paths`。它同樣由**入口腳本蓋章**，鉤子填了會被覆蓋 —— 而且理由比
  `mr_type` 更強：這份數字就是用來檢查鉤子回報了多少的
- `hunkHeader` 是**模型原本指的那個位置**，原樣留著（版本 6 起）。它與 `diffCode` 是
  兩回事：`diffCode` 是解析成功後從差異切出來的那一段，解析不出來就是空的；`hunkHeader`
  則不論解析成不成功都在。報告靠它把「指向同一個位置的數筆發現」收成一組 —— 只留
  `diffCode` 的話，位置寫歪的那些全是空值就再也分不開
- `schema_version` 比對時寬鬆：`7`、`"7"`、`"7.0"` 是同一個版本；`"7.5"` 與 `true` 不收
- **讀得懂版本 3 到 7**（寫出去的一律是 7）。版本 3 少的是 `mr_type`，讀法是「視為沒有
  種類」；3、4 少的是 `coverage`，讀法是「視為沒有涵蓋範圍資訊」，報告就不印那一段；
  3、4、5 少的是 `hunkHeader`，讀法是「每一筆沒有位置」，分組退回用 `diffCode`；3 到 6
  少的是 `coverage.skipped`，讀法是「視為沒有任何檔案被設定排除」—— 那正是那幾版的事實，
  當時還沒有排除機制。那不是猜測，是四條知道的讀法。實際的好處是開發時常常拿昨天的
  `03_summary.json` 單獨重跑步驟 5 看版面，只認最新版會讓那個迴路每次改版就斷一次
- 建構用 `ai_analysis_gitlab_mr` 的 `finding()` 與 `analysis_body()`，不要自己寫
  dict literal —— 欄位名散在寫入側與讀取側兩邊，改名漏一邊就是安靜地少一段
- `schema_version` **由入口腳本蓋章**，device 的鉤子只回 `analysis` 的內容。入口收到
  之後會立刻驗證，不符合就在**產生它的那一步**失敗，訊息點名是哪個 device

舊的 `{"summary": "一段文字"}` 仍然收得下，渲染時原樣接上。

## `04_code_review.json` 的格式

步驟 4 的產物同樣是結構、不是排好版的文字，渲染由步驟 5 負責 —— 與 `03_summary.json`
同一個理由。這裡多了一層必要性：報告要印出附件的日期、作者與連結，而那三個值**只有
步驟 4 拿得到**（步驟 5 收到的只是一個檔案路徑）。

```json
{
  "schema_version": 2,
  "code_review": {
    "filename": "CodeReview_20260910_092900.md",
    "created": "2026-09-10T09:29:00.000+0800",
    "author": "Jonas",
    "url": "https://jira.example.com/secure/attachment/12345/CodeReview_...md",
    "risk_table": "| 類別 | 風險等級 | 數量 |\n|---|---|---|\n| 記憶體 | 高 | 2 |",
    "review_result": "fail",
    "error": ""
  }
}
```

- 七個欄位都是字串。空字串合法（代表沒有那一項），但**型別不對就明確失敗** —— 一個
  dict 被 `str()` 起來會變成 `{'a': 1}` 然後原樣印進報告
- `risk_table` 是**原樣**的表格，不對齊、不排序、不改欄序。欄位名稱因 device 而異，
  任何正規化都可能弄壞某一個 device 的表格
- `review_result` 是**那份審閱的結論**（版本 2 起），由 `parse_code_review` 鉤子判定：
  `"pass"` / `"fail"` / `""`（判不出來）。另外檢查值域 —— 一個拼錯的 `"PASSED"` 印進
  報告比不印更糟，讀的人會以為那是真的結論
- **叫 `review_result` 而不是 `result`。** 回應信封最外層已經有 `result`（`PASS`/`FAIL`），
  那是「這一支腳本這一步成不成功」。兩者的值都是 pass/fail 的字樣而意思完全不同，前綴
  就是在講「這是那份審閱的結論，不是這一步的結果」
- **不是布林值。** 布林表達不了「判不出來」那個第三態，而這個專案明文擋掉布林
  （Python 的 `True == 1`）
- `error` 有值時 `risk_table` 通常是空的，但**前四個欄位照樣填** —— 報告要靠那三行
  讓讀者自己點連結去看全文。那時 `review_result` 是空字串，結果那一行不印：**不能印
  PASS 也不能印 FAIL**，兩個都是在說一件我們並不知道的事
- **讀得懂版本 1 到 2**（寫出去的一律是 2）。版本 1 少的是 `review_result`，讀法是
  「視為判不出來」—— 那正是那一版的事實
- `schema_version` 由**入口腳本蓋章**，與 `ANALYSIS_SCHEMA_VERSION` **各自獨立編號**
  （兩者是不同的產物，共用一個號碼會讓其中一邊改版莫名其妙地讓另一邊的舊檔失效）
- 比對與 `03_summary.json` 一樣寬鬆：`1` 與 `"1"` 是同一個版本，`"1.5"` 與 `true` 不收
- 建構用 `code_review_body()` 與 `wrap_code_review()`，不要自己寫 dict literal
- 這一步取不到東西時**整份檔案不會產生**（不是產生一份空的）。Qt 的
  `insertArtifactPath()` 檔案不存在就不放那個鍵，步驟 5 因此整段略過


## 呼叫 AI

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

拆解時**只有 path 裡的第一個冒號才算分隔符，其後整段都是 shareCode** —— 位址本身至少
有一個冒號（`https:`），還可能有連接埠，整串亂切會把路徑的一部分當成 shareCode 送出去，
而伺服器只回一個看不出原因的 400。先把 path 的起點找出來，scheme 與連接埠就一次排除了。
沒帶 shareCode 時直接失敗並講出正確寫法。

**shareCode 當成不透明字串，裡面有斜線或冒號都照樣整段取出：**

| `Api_URL` | 端點 | shareCode |
|---|---|---|
| `https://host:8443/v1/chat:ABC123` | `https://host:8443/v1/chat` | `ABC123` |
| `https://host:8443/v1/chat:ABC/123` | `https://host:8443/v1/chat` | `ABC/123` |
| `https://host:8443/v1/chat:A:B` | `https://host:8443/v1/chat` | `A:B` |
| `https://host:8443/v1/chat` | `https://host:8443/v1/chat` | 空 → 失敗 |

> 這條規則原本是「最後一個斜線之後的冒號才算分隔」。它擋得住 scheme 與連接埠，但同時
> 擋死了**含斜線的 shareCode** —— 那個斜線會變成「最後一個斜線」，真正的分隔冒號於是
> 落在它前面而被當成連接埠，症狀是明明填了卻回報「Api_URL 沒有帶 shareCode」。shareCode
> 是服務那端發的，本專案無權規定它不能含斜線。
>
> **代價：端點的 path 自己不能含冒號**（`/v1/models/foo:generate` 這種形狀會被切錯）。
> path 是部署者自己填的、固定不變，shareCode 是人家發的、換了就得照抄 —— 該讓哪一個
> 受限很清楚。

打開 `Debug_Mode` 時會印出拆解的結果，用來確認冒號切在你以為的地方：

```
Api_URL 拆解：端點 https://host:8443/v1/chat，shareCode 13 字元
```

**只印長度，不印值** —— 這個服務沒有認證標頭，shareCode 本身就是憑證，而這一行會進
debug console、崩潰時還會進 `crash.log`。端點印得出來是因為它是分隔冒號**之前**那一段，
不含 shareCode。完全沒帶時印的是另一行（`path 裡沒有分隔冒號`）。

設定檔的 `Model` **不進請求**（模型由 shareCode 那端決定），它只印在報告的出處那一行，
所以也不是必填。

### 等多久才放棄

四個設定決定使用者最多等多久，全部放在**每一個 AI 模式自己**的欄位裡：

```json
"AI_Mode_List": [
  { "Name": "Open AI", "Api_URL": "...", "Api_Key": "", "Model": "gpt-4o",
    "Timeout_Seconds": "30",
    "Retry_Count": "0",
    "Reask_Count": "0",
    "Recheck_Count": "0" }
]
```

| 鍵 | 預設 | 管什麼 |
|---|---:|---|
| `Timeout_Seconds` | 120 | 單次請求等多久 |
| `Retry_Count` | 3 | **連線層** —— 服務沒有回應（逾時、斷線、429、5xx）時重試幾次 |
| `Reask_Count` | 1 | **內容層** —— 服務回了但解析不開時，重問幾次 |
| `Recheck_Count` | **0** | **涵蓋層** —— 解析開了，但送進去的檔案有一部分沒被回報時，重問幾次 |

**最壞情況 ＝ 逾時 ×（重試＋1）×（重問＋1）×（重查＋1）＋ 退避**

| 設定 | 最壞情況 |
|---|---:|
| 120 / 3 / 1 / 0（預設） | 約 16 分鐘 |
| 120 / 3 / 1 / 1 | 約 32 分鐘 |
| 60 / 1 / 1 / 0 | 約 4 分鐘 |
| 30 / 0 / 0 / 0 | **約 30 秒** |

放在模式裡而不是全域，是因為「多久算太久」取決於端點本身 —— 不同的服務與模型，正常回應
時間差好幾倍。沒有這些鍵就是用預設值；數字與純數字字串都收（`30` 與 `"30"`）。

**三層分開設定，不合成一個「重試次數」。** 三者的語意與下一步完全不同：連線層是服務沒
回應，內容層是服務回了但解析不開，涵蓋層是解析開了但模型漏了檔案。合成一個的話，想關掉
「服務很忙時不要再等」的人會連同「模型漏了檔案就再問一次」一起關掉。

### `Recheck_Count`：模型漏回報檔案時再問一次

送進 prompt 的檔案，模型沒有在 `code_changes` 裡提到的那幾個，會落進涵蓋範圍的
**`missing`** 那一類（報告裡那一行「N 個檔案已送進分析，但 AI 沒有回報」）。設成大於 0
時，入口腳本會**以原本那份 prompt 再問一次**，最多 `Recheck_Count` 次。

- 只看 `missing`。`dropped`（太大沒送進去）與 `empty`（差異本身是空的）再問幾次都不會
  變，`unknown`（回了一個不存在的路徑）是另一種錯 —— 把它們算進來只會為了永遠補不回來
  的東西反覆付錢
- **依設定排除的那些不在 `missing` 裡**（見 [README.md](README.md) 的「不必分析的檔案」一節），所以不會觸發重查。少了
  那一條，這個迴圈會為了一個你刻意排除的檔案一次又一次重問，而它永遠補不回來
- 補齊了就**提早停**，不會把次數用完
- 取**最好的那一輪**而不是最後一輪：原樣重問拿到的是另一個樣本，它可能更差，而把一份
  較完整的分析換成較殘缺的那一份比不重問還糟。平手時留早的那一輪
- 重問那幾輪若自己失敗（服務掛了、限流），**沿用已經拿到的那一輪**，不會把一份已經做出
  來的分析變成失敗。第一輪就失敗才是這一步失敗
- 每一輪的除錯檔各自留著：第二輪起檔名加上 `recheck1_`、`recheck2_` 前綴
  （`recheck1_ai_reply_1.txt`），不會蓋掉第一輪那份「模型漏了什麼」的證據

**預設是 0（關閉），這是刻意的。** 目前的 prompt 本身就交代模型「沒有值得注意之處的檔案
不要放進 `code_changes`」（見 `ROLE_PROMPT` 與 `OUTPUT_SPEC`），所以 `missing` 不為 0
**常常是正確的結果** —— 一個只改了空白的檔案被略過是合理的。預設打開等於替所有部署在
大部分的 MR 上都多付一趟 AI 的錢與時間，而第二次問回來的往往一模一樣。

真的遇到模型漏回報的人把它設成 1 或 2。那是明知的取捨：多等一倍的時間，換模型再抽一次
樣本的機會。

> **迴圈在入口腳本，不在 device 的鉤子裡。** 理由與涵蓋範圍由入口蓋章完全相同：判斷
> 「回報得夠不夠」要拿鉤子的輸出對照入口手上那份差異，而讓被檢查的一方決定自己要不要
> 重做，這個機制就等於不存在。放在入口同時讓**每一個 device 都免費得到這個行為**，鉤子
> 完全不知道自己被問了第幾次。
>
> 已知代價：每一輪都重新呼叫一次鉤子，所以有 JIRA issue 的那幾次會多打一趟 JIRA。要省
> 掉它得把鉤子拆成「準備」與「問」兩段，而那會改掉所有 device 的介面 —— 對一個預設關閉
> 的功能不值得。

**`0` 對兩個次數都是合法值**，那正是「服務很忙時不要再等」的那一個。但逾時不能是 0 —— 那不是
「不要等」，是「立刻失敗」。

**值打錯時明確失敗，不退回預設。** 這與專案裡多數「取不到就降級」的決定相反，理由是：會去
調這幾個值的人多半正是因為服務很忙、不想再等那麼久；一個打錯的值若安靜地退回預設，症狀是
「我明明改了，還是等一樣久」—— 那指不出任何原因。失敗發生在**取 diff 之前**，所以不必先等完
一趟 GitLab。

打開 `Debug_Mode` 時，步驟 3 會在**開始等之前**印出這一行：

```
AI 等待設定：逾時 30 秒、重試 0 次、重問 0 次、重查 0 次（最壞情況約 30 秒，不含退避）
```

事後最常問的是「為什麼這次等了那麼久」，而那時使用者手上通常已經沒有當時的設定了。

### 重試的界線

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

## 改 prompt

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

### AI 回覆的格式

`OUTPUT_SPEC` 要求什麼、`parse_reply()` 就讀什麼，**兩者是同一件事的兩面**，改了要
一起改。目前：

```json
{
  "summary": "整體變更的摘要",
  "code_changes": {
    "檔案路徑": [
      { "title": "...", "reason": "...", "hunkHeader": "@@ -12,7 +12,7 @@" }
    ]
  }
}
```

對應到產出：`summary` → `overview`、`code_changes[檔名]` → `mrDiff[檔名]`、
`hunkHeader` → **在 diff 裡定位**，切出來的那個 hunk 成為 `diffCode`。兩邊各自命名是
刻意的 —— 回覆格式是那個服務的事，產出格式是報告的事。

**模型只回位置，不回程式碼。** `hunkHeader` 要的是 diff 裡那一行 `@@` 標頭，程式碼由
`contract.hunk_of()` 從入口備好的那份 diff 切出來。三個理由，第三個是主要的：

1. AI 的回覆是一份 JSON，而 JSON 的字串必須跳脫換行與反斜線。要模型把一段含 `\n`、
   `\d`、`C:\path` 的 diff 塞進字串欄位，是在要求它做一件它偶爾會做錯、而做錯就**整份
   解析不開**的事 —— 標頭那一行沒有這個問題。
2. 回程少掉整份 diff 的複本，省 token 也省時間。
3. **報告裡的程式碼保證與 GitLab 上的一致。** 讓模型複述 diff，它可以抄錯一個字元而
   沒有任何一步會發現，而那份報告看起來是完整的。

標頭的比對收得寬：只回那一行、連後面的函式名一起回、把整個 hunk 連內容一起回來，三種
都取得到同一個標頭。但**只在該檔案之內找**，不跨檔搜尋 —— 同一行 `@@ -12,7 +12,7 @@`
在不同檔案裡各有一個是常態，跨過去取就是把別的檔案的程式碼貼進這一筆發現。

在該檔案之內依序**三層**，前一層找到就不往下走：

| 層 | 條件 | 救的是 |
|---|---|---|
| 1 | 標頭正規化後完全相同 | 模型照抄成功（絕大多數） |
| 2 | 回報的**新側起點**落在某一個 hunk 的新側範圍裡，而且只對上一個 | 標頭抄歪了、或模型指向 hunk 中間它想講的那一行 |
| 3 | 這個檔案**只有一個** hunk | 位置寫得完全不成形，但那個檔案本來就只改了一段 |

第二、三層是為新增檔案加的。模型對新增檔案常回 `@@ -0,0 +1,433` —— **掉了結尾那對
`@@`**，行號其實是對的。嚴格讀法會把它當成「沒給位置」，於是那一筆沒有 diff。第二層用
`contract.hunk_range_of()` 的寬鬆讀法（不要求結尾的 `@@`，省略的行數補成 1）把它認回來。

兩條界線刻意保守：

- **第二層對上一個以上就放棄**，不猜。猜錯是把別的 hunk 的程式碼貼到這一筆底下，而那
  份報告看起來是完整的
- **第三層要求整個檔案只有一個 hunk**，而且要求模型至少給了讀得出行號或湊得出標頭的
  東西 —— 否則「模型根本沒提位置」會變成「拿該檔唯一的 hunk」

走了第二或第三層時 stderr 會記一筆警告，寫明回報的是什麼、對上的是哪一個。那是要觀察
的東西（模型抄標頭的準度），不能安靜地發生。

三層都對不上時那一筆**沒有 diff、但標題與理由照常呈現**，並在 stderr 記一筆警告點名是
哪一筆。刻意不回退成「用模型給的原文」—— 那會把上面三件事又放回來，而且是安靜地放回來。

`code_changes` **物件與「單鍵物件的陣列」兩種都收**。規格有歧義的時候模型也會兩種都產，
只認一種的話另一種會變成「缺少必要欄位」，而那訊息指不到真正的原因。

`hunkHeader` 即使已經交代不要加圍籬，解析時仍會**再剝一次** —— 模型對否定指令的服從度
不高，而一行 ```` ```diff\n@@ …\n``` ```` 抽不出標頭，會白白變成「對不上」。

### 重問

回覆不符預期時會在 prompt 尾端追加「只回覆結果本身」重問一次（`reask=1`）。

**JSON 解析與結構檢查要串成同一個 `parse` 傳給 `ask()`**，不能分成前後兩段 —— 分開寫
的話第二段跑在 `ask()` 之外，重問永遠觸發不到，而「JSON 合法但結構不對」恰好是模型最
常見的失手方式。

## 素材怎麼來

第 3 步在呼叫鉤子**之前**把素材備好，鉤子拿到的是現成的內容：

完整的 `inputs`（權威版本是 `device/_template/summary.py` 的 docstring，範本就在手邊，
不必翻這份文件）：

**素材**

| inputs | 內容 |
|---|---|
| `description` | MR 的原始描述，已扣掉上一輪的 AI 分析 |
| `mr_diff` | unified diff 純文字，**已扣掉依設定排除的檔案**（見 [README.md](README.md) 的「不必分析的檔案」一節），上限 `MAX_PROMPT_DIFF_BYTES`（目前 120000），超過截斷並註明 |
| `fetch_jira` | `fetch_jira(key)` → dict 或 None，**函式而不是內容**，見下 |

**這次是誰、哪一筆**

| inputs | 內容 |
|---|---|
| `repo` | 專案，`namespace/project` |
| `mr_iid` | Merge Request 編號 |
| `device` | 選中這一份的 device 名稱 |
| `mr_type` | 選中這一份的種類；沒有種類時是空字串 |
| `jira_key` | 該次採用的 key；沒有就是空字串 |
| `jira_mode` | `none` / `manual` / `auto` —— 讓你分辨 key 是抽的還是使用者填的 |

**AI 連線與等待**（都來自使用者選的那個 AI 模式）

| inputs | 內容 |
|---|---|
| `ai_mode_name` | 使用者選的模式名稱 |
| `ai_api_url` | 端點；用 `contract.ai_credentials(inputs)` 取比較省事 |
| `ai_api_key` | 金鑰，可以是空的 |
| `ai_model` | 模型名稱。**不進請求**，只印在報告出處 |
| `ai_timeout` | 單次請求的逾時秒數 |
| `ai_retries` | 連線層的重試次數 |
| `ai_reask` | 內容層的重問次數 |

> **後三個要直接交給 `ai_utils.ask()`，不要自己寫死數字。** 它們是使用者為這個模式填的
> `Timeout_Seconds` / `Retry_Count` / `Reask_Count`，而他會去調多半正是因為服務很忙。
> 寫死的話那些設定對你這一支毫無效果，症狀是「我明明改了，還是等一樣久」。沒設定時這裡
> 拿到的已經是預設值。

**能力**（函式，可無條件呼叫）

| inputs | 內容 |
|---|---|
| `progress` | `progress(text)`，在那個固定尺寸對話框上顯示一行字 |
| `debug_write` | `debug_write(檔名, 內容)`，除錯沒開時什麼都不做 |

**送出之前自己報一行 `progress`。** 入口腳本在呼叫鉤子前只報「準備 AI 分析…」—— 它不知道
你接下來要做什麼，也不知道你什麼時候真的送出去。不報的話，等回覆那幾分鐘畫面上留著的會是
你做完的上一件事，而盯著它看兩分鐘，合理的結論是程式當掉了。

連線、憑證、錯誤分類都留在入口 —— 改 prompt 的人不該為了一句話面對 HTTP。連線失敗也
因此不會被包裝成「device 的 summary.py 執行失敗」，那會把連線問題講成腳本寫壞了。

**JIRA 是函式而不是現成內容**，因為「key 有沒有效」是 device 的政策，入口不認得。先抓
的話，`[WIP]`、`[Draft]` 這種從標題方括號抽出來的字串每次都會白打一趟 JIRA 換回 404。
鉤子判定有效之後再呼叫它。查不到不會讓流程失敗，prompt 少那一段而已。

## device：讓每條產品線有自己的分析邏輯

一個 MR 該怎麼分析，會因為它屬於哪一條產品線而不同 —— SD 與 SSD 要問 AI 的問題不一樣，
報告要怎麼排也不一樣。所以流程中**四個步驟**的業務運算可以按 device 客製：

| 步驟 | 鉤子 | device 決定 | 因種類而異 |
|---|---|---|---|
| 2 | `jira_key.py` | 怎麼從 MR 抽出 JIRA key | 否 |
| 2 | `mr_type.py` | 怎麼從 MR 抽出**種類** | 否 |
| 4 | `parse_code_review.py` | 怎麼看懂別人的 code review 報告、怎麼判定通過 | 否 |
| 3 | `summary.py` | 問 AI 什麼、怎麼解析、組出什麼分析內容 | **是** |
| 5 | `merge_to_md.py` | AI 分析那一段的版面 | **是** |

步驟 1（取得描述）不因 device 而異。

步驟 4 另外讀一個 device **宣告**：

| 宣告 | device 決定 |
|---|---|
| `CODE_REVIEW_SOURCE_HEADING` | 在附件那份文件裡找哪一節才找得到總表 |

那是一個**宣告**，不是鉤子：讀它本身不會執行任何 device 的程式碼，所以宣告寫壞了可以
在任何網路往來之前就擋下來。它的值由入口讀出來、當 `heading` 傳給 `parse_code_review`
鉤子 —— 既有 device 的宣告因此不必改，而「要找哪一節」仍然只有一個地方決定。

**步驟 4 的分工是「取得在入口，看懂在鉤子」。** 查議題附件、依前綴挑最新那一份、擋大小
上限、下載、解碼都留在入口：那些要 JIRA 權杖，而權杖不交給 device 的程式碼；附件的挑選
規則與大小上限也不該每個 device 重寫一次。鉤子拿到的是現成的全文。

`parse_code_review` 不因種類而異，但它的理由與前兩支**不一樣**，值得分開講：

| 鉤子 | 看得到種類嗎 | 為什麼不依種類解析 |
|---|---|---|
| `jira_key`、`mr_type` | **否** | 它們在步驟 2 執行，種類那時候還不存在（`mr_type.py` 正是產生它的那一支） |
| `parse_code_review` | **是** | 它在步驟 4 執行，看得到種類 —— 但**刻意不用** |

刻意的理由是:**審閱報告的格式是 device 的屬性**。一個 device 底下只有一種審閱報告格式，
不會因為這一筆 MR 是 bug 還是 feature 而不同。做成依種類而異，等於替一個不存在的需求多
加一層解析，而那一層之後每個讀載入器的人都要先理解一次，才能確定自己不需要它。

**需要支援第二種審閱報告格式時，另開一個 device** —— 那正是 device 這一軸存在的意義。

為了讓這個決定不會被下一個人當成疏漏改掉，spec 把它寫成了正面的禁令（`SHALL NOT` 依種類
解析、`MUST NOT` 收到種類），並以 scenario 鎖住：種類目錄裡放了一份解析鉤子也**不會**被
載入。

「種類」是第二個軸，見下面的 type 一節。

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

## type：同一個 device 底下再分種類

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

### 誰決定種類

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
> 只寫一支的話另一支會沿用 default 的規則，安靜地抽到錯的東西 —— 而且**報告上看不出來**：
> 抽錯 key 會讓 `jira_state` 變成 `invalid`，「詳細資料」那一節於是整個不出現，被拒絕的
> 原值只留在 `02_mr_info.json` 與 log 裡；抽錯種類則是直接套上另一份版面，而每一步都回報
> 成功。要查就看那兩個產物或 debug console，不要期待報告會告狀。

### 解析鏈：種類只在自己的 device 之內

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

### 認不得的種類 —— 與 device 相反

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

### 種類怎麼傳下去

```
02_mr_info.json   { "jira_key": "PPS-1234", "mr_type": "bug" }
      |
      |  Qt 轉送（case 2 那一行）
      v
03_summary.json   { "schema_version": 7, "analysis": { "mr_type": "bug", ... } }
                                                            |
                                                            |  步驟 5 讀這份檔案
                                                            v
                                                      挑 merge_to_md
```

步驟 5 從**產物**讀而不是由 Qt 再轉送一次：Qt 只需要改一行，而且種類被記進產物，可以
印在報告出處（`Type: bug`），也留給其他消費者。種類由**入口腳本蓋章**，鉤子不填 ——
與 `schema_version` 同一個理由，讓鉤子填遲早有人複製範本時忘記。

## 新增一個 device

複製範本，改成你的 device 名稱：

```
cp -r scripts/ai_analysis_gitlab_mr/device/_template scripts/ai_analysis_gitlab_mr/device/ssd
```

**目錄名就是 device 名，而它會被當成模組名 import**，所以必須是合法的 Python 識別字：
小寫英數與底線、不以數字開頭。`ssd_gen4` 可以，`ssd-gen4` 不行。比對時不分大小寫，
設定檔寫 `SSD` 也找得到 `ssd`。

五個鉤子都是選用的，只放你要覆寫的；要再依種類分開就多開子目錄（見上面的 type 一節）。

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
| `contract.hunk_of(diff, path, header)` | 依 AI 給的 `@@` 標頭，從 diff 切出那個 hunk |
| `contract.hunk_header_of(text)` | 從一段文字裡抽出 `@@` 標頭並正規化（嚴格：要求結尾的 `@@`） |
| `contract.hunk_range_of(text)` | 從一段文字裡抽出 hunk 的行號 `(舊起點, 舊行數, 新起點, 新行數)`（寬鬆：不要求結尾的 `@@`） |
| `contract.extract_risk_table(text, heading)` | 擷取某一節裡的第一張表格（`parse_code_review` 鉤子用） |
| `contract.code_review_parsed(...)` | 組 `parse_code_review` 鉤子的回傳值 |
| `contract.REVIEW_RESULT_PASS` / `_FAIL` / `_UNKNOWN` | 審閱結論的三個值 |
| `contract.finding(...)` / `contract.analysis_body(...)` | 組分析結構 |
| `contract.jira_url(key)` | 組 JIRA 網址 |
| `contract.MAX_FINDING_DIFF_BYTES` | 單筆 diff 的位元組上限 |
| `contract.ai_credentials(inputs)` | 取出 AI 端點、金鑰與模型名 |
| `contract.ai_timeout(inputs)` | 逾時秒數，交給 `ai_utils.ask(timeout=...)` |
| `contract.ai_retries(inputs)` | 連線層重試次數，交給 `ask(retries=...)` |
| `contract.ai_reask(inputs)` | 內容層重問次數，交給 `ask(reask=...)` |
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
