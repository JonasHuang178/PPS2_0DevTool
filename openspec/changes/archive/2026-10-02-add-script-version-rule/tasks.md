# Tasks

## 1. 規格

- [x] 1.1 `script-envelope` 新增「腳本的版號」—— 跨功能，未來每個功能都適用
- [x] 1.2 寫明兩碼的意義、每次修改都要更新、擴充層第一碼要一致
- [x] 1.3 寫明**不檢查、不強制、照實呈現**，並說出這是明知的取捨
- [x] 1.4 寫明 MUST NOT 與信封模板的版本共用同一個宣告
- [x] 1.5 `single-building` 新增該功能的宣告與「版號記入診斷」

## 2. Single Building

- [x] 2.1 `single_building/__init__.py` 新增 `SCRIPT_NAME` / `SCRIPT_VERSION = "2.0"`
- [x] 2.2 四支入口腳本在 `parse_request()` 之後記一行診斷
- [x] 2.3 `TEMPLATE_VERSION` 完全不動

## 3. 功能範本

- [x] 3.1 `_function_template.py` 宣告 `SCRIPT_NAME` / `SCRIPT_VERSION` 並示範診斷那一行
- [x] 3.2 註解寫明兩碼的規則、擴充層的規則，以及**與 `TEMPLATE_VERSION` 的差別**
- [x] 3.3 模組 docstring 的「必須遵守的事」加上第 4 點

## 4. 核對

- [x] 4.1 四支 Single Building 腳本都編譯得過
- [x] 4.2 實跑 `list_source`，確認診斷第一行是 `Single Building 2.0`
- [x] 4.3 確認 stdout 的結果信封完全沒變（版號只走 stderr）
- [x] 4.4 實跑功能範本，確認第一行是 `Example Function 2.0`

## 5. 文件

- [x] 5.1 `README.md` 新增「腳本的版號」一節，含與 `TEMPLATE_VERSION` 的對照表

## 6. 併入主規格

- [x] 6.1 兩份 delta 併入 `openspec/specs/`，`openspec validate --all --strict` 通過
