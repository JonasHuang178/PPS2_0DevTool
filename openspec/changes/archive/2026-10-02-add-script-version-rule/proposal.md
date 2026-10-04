# Proposal

## Why

腳本沒有版號可言。

`TEMPLATE_VERSION = "2.0.0"` 在每一支入口腳本裡都有，但它是**信封模板的版本** —— 說的是
「請求與回應長什麼樣」，全專案共用一個值，只有信封格式本身改了才動。它不回答「使用者手上
跑的是哪一版的 Single Building」。

於是沒有任何東西回答得了這個問題。支援時問不出來，報告（有報告的功能）上也印不出來。

## What Changes

- **新增一條跨功能的需求**：每一個功能 SHALL 宣告自己的腳本名稱與版號，版號兩碼、同一個
  功能的所有入口腳本共用一份，且**每次修改都要更新**。
- 版號的第一碼留給重大修改，第二碼是修改計數；第一碼升級時第二碼歸零。
- **由功能擴充的實作**（例如以 device 之類的機制分出去的那一層）SHALL 另外宣告自己的版號，
  其第一碼**應與該功能的通用版號一致**。
- 規則**不強制、不檢查** —— 忘了更新由開發者自負，報告照實呈現讀到的值。
- `Single Building` 照這條規則宣告 `2.0`，並在每支腳本開始時把它記進診斷輸出。
- 功能範本一併補上宣告與規則說明，新功能照抄就會遵守。

不做：

- **不動 `TEMPLATE_VERSION`。** 它是全專案共用的信封模板版本（Single Building、AI Analysis
  與功能範本都是 `2.0.0`），把它拿來當某個功能的版號會讓兩個本該一致的數字分岔。
- **不做任何強制檢查。** 「改了但忘了更新版號」沒有機制擋，這是明知並接受的。
- **不把版號放進回應信封。** 那會動到跨功能的信封契約，屆時 `TEMPLATE_VERSION` 就該升 ——
  等真的需要在畫面上顯示版號時再一起做。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

- `script-envelope`: 新增「腳本的版號」需求 —— 跨功能，未來每一個功能都適用。
- `single-building`: 新增該功能依規則宣告版號的需求。

## Impact

**規格**

- `openspec/specs/script-envelope/spec.md` —— 新增一條需求
- `openspec/specs/single-building/spec.md` —— 新增一條需求

**腳本**

- `scripts/single_building/__init__.py` —— 新增 `SCRIPT_NAME` 與 `SCRIPT_VERSION`
- `scripts/single_building/*.py` ×4 —— 開始時記一行診斷
- `scripts/_function_template.py` —— 宣告與規則說明

**Qt**

- 無。

**相容性**

- 完全是加法式的。沒有任何既有行為改變，信封不動。
