# sd device

SD 產品線自己的 JIRA key 與 MR 種類擷取規則、prompt 與報告版面。覆寫
`jira_key`、`mr_type`、`summary`、`merge_to_md` 四支；`parse_code_review` 回退到
`default`。

底下有一個生效的種類：`new_test_case/`（標題寫 `[New Test Case]`）。**種類沒有自己的
版號** —— 種類目錄裡的改動累加這個 device 的第三碼。

## 版本記錄

`DEVICE_VERSION`（`__init__.py`）。版號規則見
[`docs/contributing.md`](../../../../docs/contributing.md) 的「版號」一節。

| 版號 | 日期 | 說明 |
|---|---|---|
| `v2.0.0` | 2026-11-03 | 首次發版 |
