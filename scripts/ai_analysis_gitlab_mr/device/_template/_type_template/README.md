# 種類目錄的範本

同一個 device 底下，不同種類的 Merge Request 可以走不同的 prompt 與報告版面。
種類以**子目錄**表示：

```
device/ssd/
  __init__.py       VERSION、STRICT_TYPE
  mr_type.py        怎麼從標題等欄位抽出種類
  summary.py        通用的 prompt（選用）
  merge_to_md.py    通用的版面（選用）
  bug/              <- 一個種類
    summary.py      Bug 專用的 prompt，版面沿用上面的
  newtestcase/      <- 另一個種類
    summary.py
    merge_to_md.py  這個種類兩支都覆寫
```

複製這個目錄、改成你的種類名稱即可：

```
cp -r device/_template/_type_template device/ssd/bug
```

**不需要 `__init__.py`。** 放一個目錄進去，字面上就是新增一個種類。

## 只有兩支會因種類而異

```
  summary.py      步驟 3：問 AI 什麼、怎麼解析、組出什麼分析內容
  merge_to_md.py  步驟 5：AI 分析那一段的版面
```

`jira_key.py` 與 `mr_type.py` **不會**。它們在種類被決定之前執行（後者就是決定它的
那一支），所以種類對它們沒有意義 —— 放進種類目錄不會有任何作用。

兩支都是選用的，只放你要覆寫的那一支。

## 解析順序

```
  <device>/<type>/   ->   <device>/   ->   default/
```

例如 `PPS_DEVICE=ssd`、種類是 `bug`，要找 `merge_to_md`：

```
  ssd/bug/merge_to_md.py     有就用這支
  ssd/merge_to_md.py         再找這支
  default/merge_to_md.py     最後的後備
```

**不會去找 `default/bug/`。** 各 device 的種類字彙是各自的 —— 你的 `bug` 與別人的
`bug` 不保證是同一件事，跨過去取用就是套上另一條產品線的邏輯，而每一步都會回報成功。

想用別人寫好的那一份，就**明著 import**：

```python
# device/ssd/bug/summary.py
from ai_analysis_gitlab_mr.device.default.bug import summary as base
```

明著寫的話，是你自己決定要用那一份。

## 名稱規則

目錄名會被當成模組名 import，所以：小寫英數與底線、不以數字開頭。`fw_update` 可以，
`fw-update` 不行。

抽出來的字串一律轉小寫後比對，所以標題寫 `[NewTestCase]` 對應到 `newtestcase/`。

底線開頭的目錄不算種類（這份範本就是靠這個不被誤認）。

## 認不得的種類會怎樣

抽不到、名稱不合法、或這裡沒有對應目錄時，**預設回退到通用版**，流程照常完成 ——
種類來自 MR 標題，也就是別人打的字，不該為了一個沒照約定的標題讓分析做不出來。

要改成報錯，在 device 的 `__init__.py` 宣告 `STRICT_TYPE = True`。那時失敗發生在
**步驟 2**，也就是在任何 AI 花費之前。

`STRICT_TYPE` **不要求種類目錄放齊鉤子** —— `bug/` 底下只有 `summary.py` 時，
`merge_to_md` 照常回退。
