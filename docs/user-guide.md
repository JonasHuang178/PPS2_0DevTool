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

**`Api_URL` 尾端要以冒號黏上 shareCode**（見 [AI Analysis 的 device-authoring.md](ai-analysis-gitlab-mr/device-authoring.md) 的「呼叫 AI」一節）。這四項走 `params` 而不是
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
