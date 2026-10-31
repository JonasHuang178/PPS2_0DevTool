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
# 版號兩碼：
#
#     2  .  0
#     │     └── 第二碼：這個 device 的任何修改都 +1，包含只改註解
#     └──────── 第一碼：**要與通用層的 SCRIPT_VERSION 一致**
#
# 第一碼一致，讀報告的人才看得出這份 device 是照哪一代的契約寫的。通用層升到 3.0 時，
# 這裡也該改成 3.0（第二碼歸零）。
#
# **不一致不會讓執行失敗**，也沒有任何機制強迫你更新第二碼 —— 忘了就是忘了，由開發者
# 自負。報告照實印出讀到的值，兩個版號都在眼前，對照得出來。
VERSION = "2.0"

# 這裡**沒有宣告** STRICT_TYPE 與 CODE_REVIEW_SOURCE_HEADING，兩者都沿用預設值。
#
# 不要為了「寫清楚」先照抄一份與預設值相同的宣告 —— 日後通用層改了預設值，這裡抄的那
# 一份不會跟著動，而且不會有任何徵兆。
#
# 可宣告的項目及其預設值見 `device/_template/__init__.py` 的註解。
