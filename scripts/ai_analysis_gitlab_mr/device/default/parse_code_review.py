#!/usr/bin/env python3
"""default device 的步驟 4 鉤子：看懂別人的 code review 報告。

這是所有 device 的起點 —— 沒有自己 parse_code_review.py 的 device 都用這一份。

**只負責「看懂已經拿到的那份文件」。** 查議題附件、依前綴挑最新那一份、擋大小上限、
下載、解碼都在入口腳本：那些要 JIRA 權杖，而權杖不該交給 device 的程式碼；附件的挑選
規則與大小上限也不該每個 device 重寫一次。

輸入與輸出見 parse()。
"""

import re

import ai_analysis_gitlab_mr as contract


# 把「沒有」寫成文字的幾種寫法，一律當 0。
#
# 中文文件很常用 `-` 或 `N/A` 表示這一列沒有項目。不收的話，一張完全正常的表會因為一個
# 破折號而整份判不出結論 —— 而那個結論其實就是 0。
_ZERO_WORDS = ("-", "–", "—", "n/a", "na", "none", "無", "")

# markdown 表格的分隔列：`|---|:--:|` 這種。
#
# 只認「全部儲存格都是分隔樣式」的那一行，不是「有破折號就算」—— 一列內容剛好只有破折號
# （見 _ZERO_WORDS）的話，後者會把那一列當成分隔列整列丟掉。
_SEP_CELL_RE = re.compile(r":?-+:?$")


def _cells(line):
    """把一行 markdown 表格切成儲存格。去掉頭尾的管線與每一格的前後空白。"""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [one.strip() for one in text.split("|")]


def _is_separator(cells):
    """這一行是不是表格的分隔列。"""
    filled = [one for one in cells if one]
    return bool(filled) and all(_SEP_CELL_RE.match(one) for one in filled)


def _count_of(value):
    """一個儲存格的數量。不是數量就回 None（由呼叫端報錯，不猜）。"""
    text = contract.plain(value).strip()
    if text.lower() in _ZERO_WORDS:
        return 0
    # 只收純數字。`3 件`、`~5`、`>10` 一律不收 —— 收了就得猜那個修飾詞是什麼意思，
    # 而猜錯會讓一筆有風險的審閱被判成通過。
    if re.fullmatch(r"\d+", text):
        return int(text)
    return None


def parse(inputs):
    """從 code review 報告的全文裡擷取風險評估總表，並判定這份審閱的結論。

    **這是 device 作者要覆寫的那一支。**

    inputs：

        text          報告全文（字串，一定有值）
        heading       要找的那一節的標題（該 device 的 CODE_REVIEW_SOURCE_HEADING）
        jira_key      這一筆的 JIRA key，只用於診斷訊息
        debug_write   寫除錯檔的函式；除錯沒開時什麼都不做，所以可以無條件呼叫

    回傳 contract.code_review_parsed(risk_table, review_result)。

    擷取不到、或結論判不出來時 raise contract.RiskTableError —— 入口會把訊息寫進結構的
    error 欄位、報告顯示那一段、流程繼續（這一步跑在 AI 分析之後，讓它失敗會把一份已經
    完成、已經付費的分析整份丟掉）。

    **判定規則：最後一欄是數量，全部列加總為 0 就是 pass。**

    加總而不是逐列檢查，是因為「有沒有任何項目」正是那張表要回答的事；而**合計列不必
    偵測** —— 數量不會是負的，所以重複計算不可能翻轉結論：全 0 時重複加還是 0，有非 0
    時重複加還是非 0。

    **不檢查最後一欄的標題文字。** 各 device 的報告連欄位名都不保證相同（數量／Count／
    件數／個數），而這一份是 default —— 寫一張字彙表的結果是某個沒列到的詞被誤判成「不是
    數量欄」。真正要的是「能不能加總」，那直接看值就知道；而錯誤訊息會印出實際讀到的
    標題與那一格的內容，使用者一看就知道是哪一欄錯了。

    **判不出來時 raise，不是回空結論。** 代價是那時候表格也不會進報告（入口收到例外就
    不落檔），這是明知的取捨：報告上只會有一行 ⚠️ 說明原因。
    """
    table = contract.extract_risk_table(inputs["text"], inputs["heading"])

    rows = [one for one in table.splitlines() if one.strip().startswith("|")]
    header = _cells(rows[0]) if rows else []
    if len(header) < 2:
        raise contract.RiskTableError(
            "風險評估總表只有 %d 欄，看不出哪一欄是數量" % len(header),
            "讀到的表頭是 %r。這一份判定規則需要「最後一欄是數量」。" % (header,),
            "CODE_REVIEW_TABLE_TOO_NARROW")

    title = header[-1]
    total = 0
    counted = 0

    # 列號**只數資料列**，不含分隔列 —— 錯誤訊息要指得到人眼看得到的那一列。把分隔列
    # 也數進去的話，訊息會說「第 2 列」而使用者數到的是第 1 列。
    for line in rows[1:]:
        cells = _cells(line)
        if _is_separator(cells):
            continue
        index = counted + 1

        # 欄數不符就報錯，不拿 cells[-1] 將就 —— 那一格可能根本是別的欄位的內容，
        # 而把它當成數量會讓結論建立在錯的一欄上。
        if len(cells) != len(header):
            raise contract.RiskTableError(
                "風險評估總表的第 %d 列有 %d 欄，表頭有 %d 欄"
                % (index, len(cells), len(header)),
                "那一列的內容是 %r。欄數不符時無法確定哪一格是數量。" % (cells,),
                "CODE_REVIEW_TABLE_RAGGED")

        count = _count_of(cells[-1])
        if count is None:
            raise contract.RiskTableError(
                "風險評估總表最後一欄「%s」的第 %d 列是 %r，不是數量"
                % (title, index, cells[-1]),
                "這一份判定規則把最後一欄當數量，全部列加總為 0 判定通過。\n"
                "若該 device 的總表不是這個形狀，請提供自己的 parse_code_review 鉤子。",
                "CODE_REVIEW_COUNT_NOT_A_NUMBER")

        total += count
        counted += 1

    # 一列資料都沒有（只有表頭與分隔列）也是 0，也就是 pass —— 那張表的意思就是
    # 「沒有需要列出來的項目」。
    verdict = (contract.REVIEW_RESULT_PASS if total == 0
               else contract.REVIEW_RESULT_FAIL)

    inputs["debug_write"]("code_review_verdict.txt",
                          "最後一欄：%s\n資料列：%d\n加總：%d\n結論：%s\n"
                          % (title, counted, total, verdict))

    return contract.code_review_parsed(risk_table=table, review_result=verdict)
