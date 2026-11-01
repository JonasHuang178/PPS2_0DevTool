## Why

這個 repo 有七個版號，而它們的名字互相撞：`SCRIPT_VERSION` 指通用層，但 device 那幾支在
文件裡叫「擴充腳本」、`scripts/` 底下每個 `.py` 也都是腳本；`TEMPLATE_VERSION` 指請求／回應
格式，與 `device/_template/`、`_function_template.py`、`_type_template/` 三個不相干的「範本」
毫無關係。光看名字說不出它版的是什麼。

更要緊的是現行的兩碼規則**答不出 device 最常問的那個問題**。第二碼是「這個 device 自己改了
幾次」，所以看到 `sd = 2.1` 與通用層 `2.0`，讀的人無法判斷 sd 是不是還沒跟上新的通用層 ——
而那正是這個 repo 上一次實際遇到的問題（新增 `ANALYZES_CODE` 宣告之後，要逐個 device 去查
有沒有跟上）。

規則本身也散在**九個檔案**裡各抄一份（五個 device 的 `__init__.py`、`device/__init__.py`、
兩個功能的 `__init__.py`、`_function_template.py`），加上 `docs/contributing.md` 是第十處。
改一次規則要同步十處，而讀 `device/sd/__init__.py` 的人要先讀十五行版號哲學才看到自己要改
的那一行。

## What Changes

- **BREAKING（識別字改名）**：`SCRIPT_VERSION`／`SCRIPT_NAME` → `FEATURE_VERSION`／
  `FEATURE_NAME`；device 的 `VERSION` → `DEVICE_VERSION`；device 範本的 `VERSION` →
  `TEMPLATE_VERSION`；入口腳本的 `TEMPLATE_VERSION`（請求／回應信封）→ `REQUEST_VERSION`。
  改完之後每個名字都說出自己版的是什麼。
- **版號形狀從兩碼改為三碼 `vX.Y.Z`，值帶 `v` 前綴**。`X` 來自 `version.h` 的
  `TOOL_VERSION` 主版號（工具自己的次版與修訂不往下傳）；`Y` = 改／加功能；`Z` = 改文字、
  註解、錯字；進位時右邊歸零。
- **device 的前兩碼不屬於自己**（寫成 `vA.B.C`）：`A` ＝ `X`，`B` 跟著通用層
  `FEATURE_VERSION` 的 `Y`，指出這個 device 是哪一代的；`C` ＝ 它自己動過幾次（新增、刪除、
  修正、錯字**都算**，不分種類）。`B` 要不要跟上**由該 device 的負責人決定**，版號落後是
  事實陳述而非待辦。種類（type）沒有自己的版號，改動算進所屬 device 的 `C`。
- **兩類版號明確排除在規則外**：`REQUEST_VERSION`（跨功能的通訊協定版本，全專案一個值）、
  `ANALYSIS_SCHEMA_VERSION` 與 `CODE_REVIEW_SCHEMA_VERSION`（程式讀的相容性開關，整數比對，
  不帶 `v`）。
- **報告出處的標籤「腳本」改為「功能」**，與 `FEATURE_VERSION` 同名。
- **規則說明收斂成單一來源**：`docs/contributing.md` 的「版號」一節，其餘九處縮成兩行指標。
- `--dump-config` 傾印出的 JSON 鍵 `_template_version` **不改**（已發佈的請求檔會照它寫）。

不在這次範圍內：版號一致性的自動檢查（使用者明確要求先不做；此 repo 目前沒有任何測試，
沒有現成的執行點）。

## Capabilities

### New Capabilities

無。這次改的是既有規格的要求內容與命名，沒有新增能力。

### Modified Capabilities

- `script-envelope`：「腳本的版號」整條改寫 —— 兩碼改三碼、`v` 前綴、`X` 取自工具主版號、
  device 那一層改為「前兩碼跟著通用層、第三碼是自己的」、新增「由實作層負責人決定是否跟上」、
  新增「哪些版號不受本規則管」。連帶「功能腳本範本」與「設定模板傾印」兩條裡以「範本版本」
  指稱請求／回應格式版本的措辭，改為「請求格式版本」以消除撞名。
- `ai-analysis-gitlab-mr`：出處那一段改以「功能」稱呼通用層那一行；兩個版號並列的理由由
  「第一碼是否一致」改為「device 的前兩碼指出它是哪一代」。
- `single-building`：「腳本版號的宣告」改用新名稱與新形狀。

## Impact

**程式（約 41 處）**

- `scripts/ai_analysis_gitlab_mr/__init__.py` —— `FEATURE_NAME`／`FEATURE_VERSION` 的宣告、
  `__all__`、出處那一行的標籤與值
- `scripts/ai_analysis_gitlab_mr/` 七支入口腳本 —— `REQUEST_VERSION`
- `scripts/ai_analysis_gitlab_mr/device/__init__.py` —— `getattr(module, "VERSION")` 與
  `DEVICE_VERSION_MISSING` 的訊息
- `scripts/ai_analysis_gitlab_mr/device/{_template,default,sd,ssd,ufs}/__init__.py` —— 宣告改名、
  值改三碼、重複的規則說明縮成指標
- `scripts/single_building/` —— `__init__.py` 與四支入口腳本
- `scripts/_function_template.py` —— 範例值與整段規則說明
- `scripts/script_io.py` —— `parse_request()` 的參數名 `template_version` → `request_version`
  （JSON 鍵不動）

**不受影響**：`version.h`、兩個 schema 版號與其 `ACCEPTED_*` 清單、`REQUEST_VERSION` 的值、
`_template_version` 這個 JSON 鍵、`device_version()` 這個函式名、任何執行邏輯。

**文件**：`docs/contributing.md`（唯一來源）、`docs/ai-analysis-gitlab-mr/device-authoring.md`、
`docs/ai-analysis-gitlab-mr/README.md`、`docs/ai-analysis-gitlab-mr/device-authoring.html`
（手寫的平行副本，不是從 `.md` 產生的，要一併改）。

**相容性**：改名只動 Python 模組層級的常數，沒有任何設定檔、產物或請求 JSON 的鍵隨之改變，
因此對既有部署與既有產物沒有影響。唯一的使用者可見變化是報告出處那一行的標籤由「腳本」
變成「功能」，以及所有版號多了 `v` 前綴。
