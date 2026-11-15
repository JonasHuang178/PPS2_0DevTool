## Context

這個 repo 目前有七個版號，分屬四類，而命名無法區分它們：

| 現名 | 出現處 | 它版的是什麼 | 類別 |
|---|---|---|---|
| `TOOL_VERSION` | `version.h` | Qt 工具本身 | 工具 |
| `SCRIPT_VERSION` / `SCRIPT_NAME` | `ai_analysis_gitlab_mr/__init__.py`、`single_building/__init__.py` | 一個功能的通用層 | 功能 |
| `VERSION`（device） | `device/{default,sd,ssd,ufs}/__init__.py` | 一個 device 的實作 | 實作層 |
| `VERSION`（device 範本） | `device/_template/__init__.py` | device 範本 | 實作層範本 |
| `TEMPLATE_VERSION` | 十一支入口腳本、`_function_template.py` | 請求／回應信封的格式 | 協定 |
| `ANALYSIS_SCHEMA_VERSION` | `ai_analysis_gitlab_mr/__init__.py` | 分析產物的結構 | 相容性開關 |
| `CODE_REVIEW_SCHEMA_VERSION` | 同上 | 審閱產物的結構 | 相容性開關 |

「script」在這個 repo 裡至少有三個意思（功能的通用層、device 的擴充腳本、`scripts/` 底下任一個
`.py`），「template」有四個（請求信封、device 範本、種類範本、功能腳本範本）。兩個最常被讀到的
名字正好是這兩個。

規則本身散在九個 Python 檔案裡各抄一份，`docs/contributing.md` 是第十處。

此外，現行的兩碼規則答不出 device 最常被問的那個問題 —— 看到 `sd = 2.1` 與通用層 `2.0`，讀的人
無法判斷 sd 是不是還沒跟上。第二碼在 device 上的意思是「它自己改了幾次」，與通用層的第二碼
無關。

## Goals / Non-Goals

**Goals:**

- 每一個版號的名稱說出它版的是什麼，且沒有兩類版號共用一個名稱。
- 形狀統一為帶 `v` 前綴的三碼；device 的前兩碼回答「這份實作照的是哪一代」。
- 規則說明收斂為單一來源（`docs/contributing.md` 的「版號」一節）。
- 既有部署、既有產物與請求 JSON 的鍵完全不受影響。

**Non-Goals:**

- 版號一致性的自動檢查（使用者明確要求先不做；此 repo 目前沒有任何測試，也沒有提交前檢查或
  持續整合可以掛）。
- 還原歷史的修改次數。一律從現狀起算。
- 改動 `version.h`、兩個 `*_SCHEMA_VERSION` 的值或比對方式、`REQUEST_VERSION` 的值。
- 把 `script_utils/` 的改動歸屬規則寫成硬規定（見 Open Questions）。

## Decisions

### 一、`TEMPLATE_VERSION` 的語意採「請求／回應格式」，改名 `REQUEST_VERSION`

repo 裡對這個常數有兩種互相矛盾的說法：

- **程式註解 ×3 加 `docs/contributing.md`**：它是請求／回應格式的版本，全專案共用一個值。
- **`openspec/specs/script-envelope/spec.md` 的「功能腳本範本」與「設定模板傾印」兩條**：它是
  *功能腳本範本*的版本，「使日後能辨識某支腳本依據哪一版範本撰寫」。

採前者。理由是現況的行為站在前者這邊：十一支入口腳本全是 `2.0.0`，沒有任何一支反映自己是從
哪一代 `_function_template.py` 寫出來的，也沒有任何機制利用它做過那件事。規格那兩條是寫了但
未實現的意圖。

**連帶**：那兩條規格裡以「範本版本」指稱這個版本的措辭，改為「請求格式版本」—— 否則「範本」
這個詞同時指請求信封與功能腳本範本，而這次改名正是為了消除這類撞名。

考慮過但沒採的替代方案：讓每支入口腳本宣告自己依據哪一代範本（規格原意）。那是新增能力而非
改名，且需要十一支腳本各自維護一個新的數字 —— 成本落在現在，收益落在假想的未來。

### 二、`X` 取自工具主版號，而非契約相容性

使用者的決定。代價寫明在規格裡：工具升到 v4.0.0 時，即使 Python 一行都沒動，所有版號的第一碼
都要改成 4 並把右邊歸零 —— 一批說不出任何事情的提交。收益是「這份腳本屬於哪一代工具」一眼
可答，而這個 repo 的腳本確實是隨工具一起出貨的。

考慮過：`X` 代表擴充契約的相容性（device 必須重寫時才動）。那更貼近 `X` 在語意化版號裡的慣例，
但這個 repo 沒有獨立發佈的腳本 —— 腳本與工具同一包，契約破壞與工具升級實際上同時發生。

### 三、device 用 `vA.B.C`，字母不同純粹為了行文

`A`/`B`/`C` 與 `X`/`Y`/`Z` 是同一個位置，換字母只是為了讓文件能分別稱呼「通用層的 `Y`」與
「device 的 `B`」而不必每次都寫「第二碼」。`A` 恆等於 `X`；`B` 跟著通用層的 `Y`；`C` 是這個
device 自己動過的次數。

`C` 不分種類（新增、刪除、修正、錯字都算）是刻意的：device 的維護者未必是功能的維護者，而
**需要判斷的規則就是會被漏掉的規則**。這條理由原本是 repo 反對三碼的論據，這裡把它收窄到
最容易被漏掉的那一層。

`B` 要不要跟上由 device 維護者決定。這使版號落後成為事實陳述而非待辦 —— 讀報告的人看到
`sd = v2.5.8` 而通用層是 `v2.6.0`，就知道 sd 還在 2.5 那一代的邏輯上跑。

### 四、種類沒有自己的版號

種類的數量不固定，且與所屬 device 同一個維護者。各自一個版號會讓報告出處那幾行長到沒有人讀。
種類的改動累加所屬 device 的 `C`。

### 五、兩類版號明確排除在規則外

- `REQUEST_VERSION`：跟著格式走，不跟著任何功能走。若受本規則管，它就會隨某個功能一直往上跳
  而其他功能的停著不動，於是兩個本該相同的數字分岔，並被 `--dump-config` 傾印給呼叫端看。
- `ANALYSIS_SCHEMA_VERSION`、`CODE_REVIEW_SCHEMA_VERSION`：程式讀的整數。已驗證 `"v2.6.0"`
  會被 `_schema_version()` 與 `ACCEPTED_SCHEMA_VERSIONS` 擋下來 —— 產物會被自己的驗證拒絕。
  且 `schema_version` 在 `ai_analysis_gitlab_mr_merge_to_md.py` 裡兼任「結構化 vs 純文字」的
  判別依據。不帶 `v`，不改形狀。

### 六、`_template_version` 這個 JSON 鍵不改

常數改名 `REQUEST_VERSION`，但 `script_io._build_template()` 寫出的鍵維持 `_template_version`。
已發佈的請求檔會照它的名字寫。已確認無人讀取這個鍵（只被寫進 `--dump-config` 的輸出），所以
改名的唯一後果是破壞既有請求檔，沒有任何收益。規格裡補一條「承載版本的鍵不隨宣告改名」把這
件事固定下來。

### 七、名稱對照

| 現名 | 新名 | 它版的是什麼 |
|---|---|---|
| `SCRIPT_NAME` | `FEATURE_NAME` | 功能的名稱 |
| `SCRIPT_VERSION` | `FEATURE_VERSION` | 功能通用層的版號 |
| `VERSION`（device） | `DEVICE_VERSION` | 一個 device 的實作 |
| `VERSION`（device 範本） | `TEMPLATE_VERSION` | device 範本 |
| `TEMPLATE_VERSION`（入口腳本） | `REQUEST_VERSION` | 請求／回應信封的格式 |

`TEMPLATE_VERSION` 這個名字被回收給 device 範本 —— 它騰出來了，而在 `device/_template/` 裡
「template」只有一個意思。

### 八、數值

一律從現狀起算（歷史次數還原不了）。

| 宣告處 | 新值 |
|---|---|
| `ai_analysis_gitlab_mr` `FEATURE_VERSION` | `v2.1.0` |
| `single_building` `FEATURE_VERSION` | `v2.0.0` |
| `device/_template` `TEMPLATE_VERSION` | `v2.1.0` |
| `device/default` `DEVICE_VERSION` | `v2.1.0` |
| `device/sd` `DEVICE_VERSION` | `v2.1.0` |
| `device/ssd` `DEVICE_VERSION` | `v2.0.0` |
| `device/ufs` `DEVICE_VERSION` | `v2.0.0` |
| `_function_template.py` `FEATURE_VERSION` 範例 | `v2.0.0` |
| 所有 `REQUEST_VERSION` | `2.0.0`（不動，不帶 `v`） |

`ai_analysis` 是 `v2.1.0` 而非 `v2.0.0`，因為上一次提交加了 `ANALYZES_CODE` 這個宣告 —— 那是
功能改動，`Y` 該累加。`default` 與 `sd` 已跟到那一代，`ssd` 與 `ufs` 還停在前一代，所以 `B`
是 `0`。這正是新規則要讓人一眼看出的那件事。

### 九、單一來源的做法

`docs/contributing.md` 的「版號」一節寫完整規則（含名稱對照表、三碼定義與 `v2.0.0` 這類範例、
device 的 `vA.B.C` 例外、哪些版號不受管）。其餘九個 Python 檔案的規則說明縮成兩行指標，形如：

```python
# 版號規則見 docs/contributing.md 的「版號」一節。這裡只放值。
FEATURE_VERSION = "v2.1.0"
```

`docs/*.html` 是手寫的平行副本，不是從 `.md` 產生的，要一併改。

### 十、改名的執行方式

逐處人工改，不用全域取代。`VERSION` 這個字串在 repo 裡是 `TOOL_VERSION`、`SCRIPT_VERSION`、
`ANALYSIS_SCHEMA_VERSION` 等名稱的子字串，全域取代會打到不該動的東西。每一處改完以
`grep -rn` 確認舊名已清零，再確認 `device/__init__.py` 的 `device_version()` 讀的是新名。

## Risks / Trade-offs

- **`DEVICE_VERSION` 改名後，既有的外部 device 會載入失敗** → `device_version()` 讀不到宣告會
  丟 `DEVICE_VERSION_MISSING`，訊息會指出是哪一個 device。repo 內四個 device 全在這次一起改；
  若有 repo 外的 device，失敗訊息明確且修法是改一個名字。不提供相容讀法（同時接受 `VERSION`）
  —— 那會讓舊名永久留存，而這次改動的目的正是消除撞名。
- **工具主版號升級時要掃一遍所有版號** → 規格裡寫明這是明知的取捨；`docs/contributing.md` 的
  「版號」一節會列出所有受管的宣告處，升級時照清單改。
- **`Y`／`Z` 的判斷沒有強制力** → 規格裡寫明「本規格 SHALL NOT 要求任何機制保證修改了就一定
  更新版號」。判斷錯的代價是版號說得不精確，不是執行失敗。這個 repo 上一次就漏過一次（加了
  `ANALYZES_CODE` 沒動版號），所以不假裝它不存在。
- **報告出處那一行的標籤由「腳本」變成「功能」** → 使用者可見的變化，已確認接受。
- **`openspec/specs/ai-analysis-gitlab-mr/spec.md` 裡有一句理由會過時**：「最終報告的組成」
  那條的理由寫「而第一碼是否一致也要兩個都在才看得出來」，新規則下該說的是「device 的前兩碼
  指出它是哪一代」。那條需求有 581 行，為一句非規範性的理由把整塊複製進 delta 會淹掉這份
  delta 的實際內容 → 列為 tasks 裡一項明確的編輯，直接改常駐規格的那一句，並在 tasks 裡標明
  它是理由措辭而非行為改動。

## Migration Plan

沒有資料遷移。改名只動 Python 模組層級的常數，沒有任何設定檔、產物或請求 JSON 的鍵隨之改變。

回退方式是還原這次提交。唯一不可逆的部分是已產出的報告 —— 它們的出處那一行會停在「腳本」
標籤與兩碼版號，而規格已寫明「呈現版號之處 SHALL 照實呈現讀到的值」，舊報告照舊能讀。

## Open Questions

- **出處那一行的 device 版號是在第五步即時讀 `device_version()` 取得的**，而 provider 與模型
  是刻意從產物讀的。單獨拿一份舊產物重跑合併，印出的 device 版號會是當下的、不是當時的。這
  與 provider／模型那一條規格的理由互相矛盾。本次不改（不屬於版號命名與規則的範圍），但記在
  這裡以免再次被遺忘。
- **`script_utils/` 由兩個功能共用，改動它該累加誰的 `FEATURE_VERSION`？** 建議兩個功能都累加，
  並在 `script_utils/` 的 `__init__.py` 放一行註解說明這件事。本次先不寫成規格要求 —— 需要
  先看幾次實際改動才知道這條規則會不會被遵守。
