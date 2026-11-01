#!/usr/bin/env python3
"""sd device 的步驟 2 擴充腳本：擷取出 Merge Request 的種類。

種類決定步驟 3 與步驟 5 會用哪一份 `summary.py` 與 `merge_to_md.py`。

SD 的規則是標題的**第二個**方括號。第一個留給 JIRA key（見 `jira_key.py`）：

    mod:[PPS-1234][Bug] 修正重試上限
        ^^^^^^^^^^ 第一個：JIRA key
                  ^^^^^ 第二個：種類  ->  "Bug"  ->  正規化成 bug

**這一支只負責讀出來。** 認不認得、要不要報錯都不在這裡：

- 回傳值由入口腳本正規化（去頭尾空白、轉小寫、檢查形狀），所以這裡不處理大小寫
- 不合法的字串（`[緊急]`、`[bug fix]`、含路徑分隔字元的東西）視同沒有種類，不報錯 ——
  那是 MR 作者打的字，不是部署的問題
- 擷取不到就回空字串，後果是走該 device 的通用版；除非 `__init__.py` 宣告了
  `STRICT_TYPE = True`，那時入口腳本會在**步驟 2**失敗，也就是在任何 AI 花費之前

SD 目前有兩個種類，各對應一個子目錄：

    [Pattern Issue]   ->  pattern_issue/    沿用 sd 的通用版（空目錄，逐支回退）
    [New Test Case]   ->  new_test_case/    不看程式碼，只總結 JIRA 單的內容

> **標題的寫法必須與 `_TYPE_BY_LABEL` 的鍵一字不差**（區分大小寫、空白也算）。對照表
> 存在的原因是目錄名不能有空白與大寫 —— 入口腳本要求種類名稱符合 `^[a-z_][a-z0-9_]*$`，
> 所以 `Pattern Issue` 這種給人看的寫法必須由這一支對到 `pattern_issue`。
>
> 寫法不是一字不差（`[pattern issue]`、`[PatternIssue]`、`[ Pattern Issue ]`，連目錄名
> 本身 `[pattern_issue]` 也算）時**一律回空字串**，當成這筆 MR 沒有宣告種類，走 sd 的
> 通用版。

種類沒有對應目錄時，入口腳本會把它回退成空字串（不嚴格模式），產物與報告出處的 `Type`
都會是空的，只有 `Debug_Mode` 開啟時 console 看得到「認不得種類 …」那一行。

這一支是 **sd 自己的規則**，不是任何人的後備：default 不擷取種類，所以沒寫這一支的
device 拿到的一律是空字串。
"""

import re

from script_utils import logger

# 標題裡所有的方括號內容，依出現順序。
#
# [^][]* 而不是 .*? ：巢狀或未閉合的括號不該被當成一組。標題是人手打的，`[a[b]c]`
# 這種東西出現得比想像中多。
_BRACKET_RE = re.compile(r"\[([^\[\]]*)\]")

# 取第幾個方括號（0 起算）。擷取成常數是因為這是這一份規則唯一的可變之處 ——
# 改取第三個的話只動這一行。
_BRACKET_INDEX = 1

# 認得的寫法 -> 種類目錄名。**一字不差地比對，區分大小寫、空白也算。**
#
# 標題要寫 `[Pattern Issue]`；`[pattern issue]`、`[PATTERN ISSUE]`、`[Pattern-Issue]`、
# `[PatternIssue]`、`[ Pattern Issue ]` 一概**不認**，一律當成「這筆 MR 沒有宣告種類」。
#
# 這是刻意的嚴格：這張表就是 SD 的標題約定本身，而約定要有約束力才有意義。放寬成「空白
# 換底線、轉小寫」那種通用規則的話，同一個種類會有七八種寫法都通，於是沒有人需要照約定
# 寫 —— 而種類決定的是用哪一份 prompt 與版面，寫法一旦各憑喜好，哪一筆走了哪一份就只能
# 逐筆去查。
#
# ⚠️ **新增一個種類要動兩個地方**：這張表加一列，並在 `device/sd/` 底下建同名目錄。
# 只加表沒建目錄的話，入口腳本會判定「認不得」而回退（console 有一行）；只建目錄沒加表
# 的話，這一支永遠不會回出那個名字（console 有一行 debug）。兩者都沒有徵兆會寫在報告上。
_TYPE_BY_LABEL = {
    u"Pattern Issue": u"pattern_issue",
    u"New Test Case": u"new_test_case",
}


def _canonical(raw):
    """把標題裡的寫法對到種類目錄名；**不是一字不差就回空字串**。

        "Pattern Issue"  ->  "pattern_issue"
        "New Test Case"  ->  "new_test_case"
        "pattern issue"  ->  ""      大小寫不符
        "pattern_issue"  ->  ""      那是目錄名，不是標題的寫法
        "PatternIssue"   ->  ""      少了空格
        " Pattern Issue "->  ""      前後多了空白

    **一個都不放寬。** 連目錄名本身（`pattern_issue`）寫在標題裡都不認 —— 認了就等於有
    兩套合法寫法，而兩套寫法遲早變成「大家各寫一套」。

    回空字串＝「這筆 MR 沒有宣告種類」，後果是走 sd 的通用版，不失敗（`STRICT_TYPE` 未開）。

    寫法不符時這裡自己記一行 debug：回空字串之後入口腳本就分不出「標題根本沒有第二個方括號」
    與「有寫但寫法不對」，而後者是使用者唯一能自己修的那一種。
    """
    name = _TYPE_BY_LABEL.get(raw)
    if name:
        return name

    logger.debug("sd/mr_type：%r 不是認得的種類寫法（認得的是：%s），視為沒有宣告種類",
                 raw, "、".join(sorted(_TYPE_BY_LABEL)))
    return ""


def extract(mr):
    """自 Merge Request 的欄位擷取出種類。回傳字串；沒有就回空字串。

    收到的 mr 是整理過的欄位（不是 GitLab 原樣的物件），與 jira_key 擴充腳本相同：

        title / source_branch / target_branch / description / repo / mr_iid
    """
    title = mr.get("title") or ""
    found = _BRACKET_RE.findall(title)

    # 方括號不夠多（只有 JIRA key、或一個都沒有）。那不是錯誤：回 "" 就是「這一筆沒有
    # 宣告種類」。
    if len(found) <= _BRACKET_INDEX:
        return ""

    return _canonical(found[_BRACKET_INDEX])
