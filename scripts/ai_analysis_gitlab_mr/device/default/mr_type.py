#!/usr/bin/env python3
"""default device 的步驟 2 擴充腳本：**不擷取**種類。

種類決定步驟 3 與步驟 5 會用哪一份 summary.py 與 merge_to_md.py。

**這是所有 device 的後備** —— 沒有自己 mr_type.py 的 device 都用這一份，而 default 刻意
不猜種類寫在標題的哪個位置：方括號的順序是各產品線自己的約定，猜錯會安靜地對應到錯的
種類目錄。所以這裡一律回空字串，等於「這筆 MR 沒有種類」。

回空字串不是錯誤，後果是走該 device 的通用版 summary.py 與 merge_to_md.py；除非該 device
在 __init__.py 宣告了 STRICT_TYPE = True，那時入口腳本會失敗 —— 宣告了 STRICT_TYPE 就
必須自己寫一份 mr_type.py，不能靠這裡。

要依種類分流的 device 自己寫一份（規則見 `device/_template/mr_type.py`）。順帶提醒：種類
的位置通常也意味著 JIRA key 有自己的位置，**兩支擴充腳本多半要一起寫**。
"""


def extract(mr):
    """一律回空字串 —— default 不擷取種類。

    收到的 mr 是整理過的欄位，與 jira_key 擴充腳本相同：

        title / source_branch / target_branch / description / repo / mr_iid

    這裡刻意不看。
    """
    return ""
