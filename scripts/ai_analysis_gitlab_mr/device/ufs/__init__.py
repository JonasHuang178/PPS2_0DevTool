#!/usr/bin/env python3
"""UFS device —— UFS 產品線自己的 JIRA key 擷取規則。

設定檔的 `PPS_Device` 填 `ufs` 時選用這一份（CI 則是環境變數 `PPS_DEVICE`）。

這個 device **只覆寫一支擴充腳本**：

    jira_key.py     步驟 2：從 MR 描述第一行的網址取出 JIRA key

其餘四支（`mr_type`、`summary`、`parse_code_review`、`merge_to_md`）刻意**不放**，
逐支回退到 `device/default/` —— 回退是逐支的，所以沒放的那幾支拿到的是 default 當下的
實作，而不是一份會慢慢與 default 漂移的複本。

**沒有 MR 種類的需求**，所以：

- 不放 `mr_type.py`。default 的那一支一律回空字串，於是種類永遠是空的，步驟 3 與
  步驟 5 走這個 device 的通用版（也就是 default 的那兩支）
- 不宣告 `STRICT_TYPE`。宣告 True 的 device 必須自己提供 `mr_type.py`，否則每一筆 MR
  都會在步驟 2 失敗
- 不開任何種類子目錄

> JIRA key 的**有效性判定**不在這個 device 裡 —— 擷取規則與判定規則本該同屬一個
> device，但這裡沒有自己的 `summary.py`，所以判定沿用 default 的樣式
> （`^[A-Z][A-Z0-9]*-[0-9]+$`）。網址最後一段是正規的 issue key（`PPS-1234`）時剛好
> 相符；不相符時狀態是 `invalid`，報告的「詳細資料」那一節不出現，步驟 4 的程式碼
> 審閱也整段略過。要改判定規則就得連 `summary.py` 一起複製過來，而那份複本之後會與
> default 漂移 —— 目前不需要，所以不複製。
"""

# 這個 device 的版本，會印在報告末尾的出處資訊裡。**必填。**
#
# 版號 vA.B.C：前兩碼指出這個 device 照的是哪一代通用層，第三碼是它自己動過的次數。
# 完整規則見 docs/contributing.md 的「版號」一節 —— 那裡是唯一的來源，這裡只放值。
DEVICE_VERSION = "v2.0.0"

# 這裡**沒有宣告** STRICT_TYPE 與 CODE_REVIEW_SOURCE_HEADING，兩者都沿用預設值。
#
# 不要為了「寫清楚」先照抄一份與預設值相同的宣告 —— 日後通用層改了預設值，這裡抄的那
# 一份不會跟著動，而且不會有任何徵兆。
#
# 可宣告的項目及其預設值見 `device/_template/__init__.py` 的註解。
