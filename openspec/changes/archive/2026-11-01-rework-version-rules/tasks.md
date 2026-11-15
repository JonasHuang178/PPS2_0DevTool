## 1. 單一來源先寫好

- [x] 1.1 改寫 `docs/contributing.md` 的「腳本的版號」一節為「版號」，內容包含：名稱對照表
      （含每個名稱版的是什麼、宣告在哪裡、何時累加、範例值如 `v2.0.0`）、三碼 `vX.Y.Z` 的定義、
      `v` 前綴的規定、`X` 取自 `version.h` 的 `TOOL_VERSION` 主版號、進位歸零、以及「哪些版號
      不受本規則管」（`REQUEST_VERSION`、兩個 `*_SCHEMA_VERSION`）
- [x] 1.2 在同一節加「device 的例外」小節：明確引入 `vA.B.C` 的寫法與三碼各自的意思，
      `B` 跟著通用層 `FEATURE_VERSION` 的 `Y`、`C` 不分種類、`B` 是否跟上由 device 維護者決定、
      版號落後是事實陳述不是待辦、種類沒有自己的版號
- [x] 1.3 在同一節列出所有受本規則管的宣告處清單，供工具主版號升級時照表掃過
- [x] 1.4 更新 `docs/contributing.md:15-22` 的「改了常數或版號 → grep 那個數字」檢查，裡面
      舉的例子用新名稱

## 2. 功能層改名與改值

- [x] 2.1 `scripts/ai_analysis_gitlab_mr/__init__.py`：`SCRIPT_NAME`／`SCRIPT_VERSION` 改名為
      `FEATURE_NAME`／`FEATURE_VERSION`，值改 `"v2.1.0"`，同步 `__all__`（行 56、57）
- [x] 2.2 `scripts/ai_analysis_gitlab_mr/__init__.py:2591`：出處那一行的標籤「腳本」改為
      「功能」，並改用新常數名
- [x] 2.3 `scripts/single_building/__init__.py`：同樣改名，值改 `"v2.0.0"`，同步 `__all__`（行 14）
- [x] 2.4 `scripts/single_building/` 四支入口腳本：`logger.info` 那兩行改用新常數名
- [x] 2.5 `scripts/_function_template.py`：`SCRIPT_NAME`／`SCRIPT_VERSION` 改名，範例值改
      `"v2.0.0"`，行 112 的 `logger.info` 一併改

## 3. 請求信封版本改名

- [x] 3.1 `scripts/ai_analysis_gitlab_mr/` 七支入口腳本：`TEMPLATE_VERSION` 改名
      `REQUEST_VERSION`，值不動（`"2.0.0"`，不帶 `v`）
- [x] 3.2 `scripts/single_building/` 四支入口腳本與 `__init__.py`：同樣改名
- [x] 3.3 `scripts/_function_template.py`：同樣改名，並改寫行 75-78 那段註解（它仍要說明這與
      功能版號是兩個不同的東西，但指向 `docs/contributing.md`）
- [x] 3.4 `scripts/script_io.py`：`_build_template()` 與 `parse_request()` 的參數名
      `template_version` → `request_version`。**JSON 鍵 `_template_version` 不動**
- [x] 3.5 `grep -rn '_template_version'` 確認傾印出的鍵仍是 `_template_version`

## 4. device 層改名與改值

- [x] 4.1 `scripts/ai_analysis_gitlab_mr/device/__init__.py:424`：`getattr(module, "VERSION")`
      改讀 `DEVICE_VERSION`
- [x] 4.2 同檔 `DEVICE_VERSION_MISSING` 的訊息（行 429）改寫：不再說「第一碼要與通用層的
      `SCRIPT_VERSION` 一致，第二碼是這個 device 自己的修改次數」，改為 `vA.B.C` 的說法並指向
      `docs/contributing.md`
- [x] 4.3 `device/_template/__init__.py`：`VERSION` 改名 `TEMPLATE_VERSION`，值改 `"v2.1.0"`
- [x] 4.4 `device/default/__init__.py`：改名 `DEVICE_VERSION`，值 `"v2.1.0"`
- [x] 4.5 `device/sd/__init__.py`：改名 `DEVICE_VERSION`，值 `"v2.1.0"`
- [x] 4.6 `device/ssd/__init__.py`：改名 `DEVICE_VERSION`，值 `"v2.0.0"`
- [x] 4.7 `device/ufs/__init__.py`：改名 `DEVICE_VERSION`，值 `"v2.0.0"`

## 5. 收斂重複的規則說明

- [x] 5.1 五個 device 的 `__init__.py`（`_template`、`default`、`sd`、`ssd`、`ufs`）：各自那段
      版號哲學（含 ASCII 圖解與「第一碼要與通用層的 `SCRIPT_VERSION` 一致」）縮成兩行指標
- [x] 5.2 `device/__init__.py`、`ai_analysis_gitlab_mr/__init__.py`、`single_building/__init__.py`、
      `_function_template.py`：同樣縮成兩行指標
- [x] 5.3 `scripts/AUTHORING.md`：行 513-529 與行 943 改用新名稱；該檔已指向
      `docs/contributing.md`，把節名由「腳本的版號」改為「版號」

## 6. 文件與手寫 HTML

- [x] 6.1 `docs/ai-analysis-gitlab-mr/device-authoring.md`：行 638（宣告清單）、719（`VERSION = "1.2"`
      範例）、1048（VERSION 為必填那一段）改用 `DEVICE_VERSION` 與三碼範例值
- [x] 6.2 `docs/ai-analysis-gitlab-mr/README.md`：行 307 的範例報告頁尾、行 576 的頁尾表格、
      行 579（提到 `SCRIPT_VERSION` 第二碼）、行 582-584（兩個版號並列的理由改為「device 的前
      兩碼指出它是哪一代」）
- [x] 6.3 `docs/ai-analysis-gitlab-mr/device-authoring.html`：行 164、182、900 的 `VERSION` 改為
      `DEVICE_VERSION` 與三碼範例值（手寫平行副本，不是從 `.md` 產生）
- [x] 6.4 `grep -rn 'VERSION' docs/*.html docs/**/*.html` 確認沒有漏掉的 HTML 副本

## 7. 常駐規格的理由措辭

- [x] 7.1 `openspec/specs/ai-analysis-gitlab-mr/spec.md` 第 882 行：「而第一碼是否一致也要兩個
      都在才看得出來」改為「而 device 的前兩碼指出它照的是哪一代，只印其中一個就看不出來」。
      這是**理由措辭**，不是行為改動，所以不經 delta spec（該需求有 581 行，整塊複製進 delta
      會淹掉實際內容）

## 8. 驗收

- [x] 8.1 `grep -rn 'SCRIPT_VERSION\|SCRIPT_NAME'` 在 `scripts/`、`docs/` 與 `openspec/specs/`
      之下為零（`openspec/changes/` 底下的本次文件除外）
- [x] 8.2 `grep -rn '\bVERSION\b' scripts/ai_analysis_gitlab_mr/device/` 只剩 `DEVICE_VERSION`
      與 `TEMPLATE_VERSION`
- [x] 8.3 `grep -rn 'TEMPLATE_VERSION' scripts/` 只出現在 `device/_template/__init__.py`
- [x] 8.4 確認 `version.h` 的 `TOOL_VERSION`、`ANALYSIS_SCHEMA_VERSION`、
      `CODE_REVIEW_SCHEMA_VERSION` 與其 `ACCEPTED_*` 清單都未被動到
- [x] 8.5 對四個 device 各跑一次 `--dump-config`，確認傾印出的 JSON 仍含 `_template_version`
      且值為 `2.0.0`
- [ ] 8.6 跑一次完整的 MR 分析流程（或以既有產物重跑第五步），確認報告頁尾出現
      「**功能** AI Analysis GitLab MR `v2.1.0`」與「**Device** `sd` `v2.1.0`」
- [x] 8.7 把 `device/sd/__init__.py` 的 `DEVICE_VERSION` 暫時改名回 `VERSION`，確認得到
      `DEVICE_VERSION_MISSING` 且訊息指出是哪一個 device，再改回來
- [x] 8.8 `openspec validate rework-version-rules`
