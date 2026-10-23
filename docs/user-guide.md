# 使用這個工具

> 不限於任何單一功能的部分：設定檔每個鍵的意思、設定檔與 git 的關係、
> 診斷輸出怎麼打開。
>
> 功能本身怎麼用 → [Single Building](single-building/README.md)、
> [AI Analysis GitLab MR](ai-analysis-gitlab-mr/README.md)。
> 整體架構與建置 → [最外層 README](../README.md)。

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

`Skip_Title_*_List` 三個鍵是 `Filter` 群組裡標題排除的**預設值**，分別對應三個欄位：

```json
"Skip_Title_StartsWith_List": ["Revert"],
"Skip_Title_EndsWith_List":   ["(DNM)"],
"Skip_Title_Contains_List":   ["[WIP]", "[Draft]"]
```

三個都**選填**，缺了就是那一種比對為空（不排除任何項目），所以既有的設定檔不補也不會壞。
Qt 以 `", "` 串接後填進欄位，JSON 裡寫什麼畫面就長什麼樣，中間沒有任何轉換。

**這是預設值，不是記憶。** 使用者在畫面上改過的內容不寫回任何地方，重新啟動就回到這裡的值
—— 本工具沒有任何介面狀態的持久化（來源路徑甚至是明文規定不得寫入設定檔的）。

因為逗號是分隔符，**關鍵字本身不能含逗號**；這條限制在設定檔與輸入框兩邊都成立。

`AI_Provider_List` 是一個清單，畫面上的 AI Provider 下拉選單每一筆對應一個選項：

```json
"AI_Provider_List": [
  {
    "Provider": "openai",
    "Api_URL": "https://主機:8443/api/external/v1/端點:SHARE_CODE",
    "Api_Key": "送出時放進 X-Api-Key 標頭"
  }
]
```

- **`Provider`** 只能用英文字母、數字與 `. _ -`，不可為空 —— 它會被接在 `Api_URL` 前面組成
  連線字串 `openai:https://...:SHARE_CODE` 交給腳本。不合法時按下 AI Analysis 會跳出訊息、
  不啟動流程。
- **`Api_URL` 尾端要以冒號黏上 shareCode**（見 [AI Analysis 的 device-authoring.md](ai-analysis-gitlab-mr/device-authoring.md) 的「呼叫 AI」一節）。
- **沒有 `Model` 欄位。** 模型由 shareCode 那一端決定，名稱向 AI 服務查（見下）。

連線資訊走 `params` 而不是環境變數 —— 它們隨使用者選的項目而變，屬於該次執行的參數。

選單的每一項顯示為 `provider / 模型名稱`。模型名稱在工具每次啟動後**第一次**進入 AI Analysis
GitLab MR 時查一次（會出現處理中對話框，可取消）；查不到的項目顯示 `無法取得`，仍可選取與分析。
選項以**位置**對應設定項目，所以兩筆 `Provider` 相同也不會選錯。

**模型名稱的查詢路徑要由部署者填入。** 查詢網址是把 `Api_URL` 中 `api/external/v1` 之前的
部分接上 `api/external/v1/` 與 `scripts/script_utils/ai_utils.py` 的 `MODEL_LIST_PATH`。
那個常數出貨時是佔位值 `__FILL_IN_MODEL_LIST_PATH__`；沒填之前不送任何查詢，選單與報告出處
都沒有模型名稱，其餘照常。

### 執行紀錄

畫面上的 `Save run log` 勾選方塊決定這一次的紀錄要不要留下來。勾選時，Qt 在
`Save_Analysis_File_Dir` 底下建一個帶時間戳的目錄，分三層：產物在上層、執行紀錄在
`logs/`、各步實際收到的參數在 `logs/requests/`。**未勾選時一個檔案都不會留下** ——
中間產物改走暫存目錄，流程一結束就連目錄一起移除。

結果視窗（成功與失敗都一樣）會顯示那一次紀錄目錄的完整路徑，可以選取複製，旁邊有一顆
`Open log folder` 直接開啟它。未勾選紀錄時那顆按鈕不出現。

三件要知道的代價：

- **參數紀錄只記送進腳本的 `params`，而且憑證是遮掉的**（`ai_api_key` 整個遮成 `***`，
  連線字串只遮尾端的 shareCode）。所以它**不能直接拿去 `--request` 重跑那一步**，要自己
  補上動作、所需的設定與被遮掉的值。換來的是它可以安全地留在紀錄裡，不需要任何清理步驟。
- **`Save path` 欄位顯示的是解析後的絕對路徑**，方便直接複製貼上。設定檔裡的值不會被
  改寫 —— 填相對路徑的話，設定檔裡仍然是相對路徑，而畫面上顯示它相對**執行檔目錄**
  解析後的結果。
- **自己寫過 device 的人要改一行**：鉤子收到的 `inputs["debug_write"]` 改名為
  `inputs["log_write"]`，參數 `debug_dir` 改名為 `log_dir`。

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
