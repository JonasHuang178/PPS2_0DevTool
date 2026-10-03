#!/usr/bin/env python3
"""default device 的步驟 5 鉤子：AI 分析那一段的版面。

這是所有 device 的起點 —— 沒有自己 merge_to_md.py 的 device 都用這一份。

**只負責「AI 分析標題底下那一段」。** 標題那一行、原始描述那一段、分隔線與末尾的出處
都由入口腳本寫出。那一行標題不歸這裡管，是因為它同時是下一輪切出原始描述的邊界。

輸入已經過 contract.validate_analysis() 驗證，所以這裡不再檢查型別。
"""

import ai_analysis_gitlab_mr as contract


_ENTRY_INDENT = "  "


def _indent(text):
    """把每一行縮排。空行不補空白 —— 那只會留下看不見的行尾空格。"""
    return "\n".join(_ENTRY_INDENT + line if line else ""
                      for line in text.split("\n"))


def _entry_block(item, path, position):
    """一筆 finding，組成報告裡的一個條目。

    形狀：

        - <標題>
          - <理由第一句>
          - <理由第二句>
          <details>

          ```diff
          <diff>
          ```
          </details>

    **理由與總覽用同一套斷行。** AI 回來的理由跟總覽一樣是一句接一句的一整段，在結果
    視窗會折成一片文字牆、貼到討論串則是一個段落。contract.as_list() 遇到句末標點就斷，
    逐行排成該筆之下的子清單；它會尊重來源已有的結構（自帶換行、自帶有序編號），只斷得出
    一段時原樣回傳，所以可以無條件套用 —— 單句的理由仍是縮排的一行，與先前相同。

    子清單縮排兩格。CommonMark（GitLab 用的那一套）據此把它收進該筆 bullet 之內，而
    <details> 成為子清單的兄弟、仍掛在該筆之下 —— 也就是 diff 屬於這一筆 finding，不屬於
    理由的最後一句。量過。

    > python-markdown 在兩格縮排下不認巢狀，會把理由各句拉成與標題同層的項目；四格縮排
    > 則反過來把 <details> 吸進子項目裡、圍籬變成行內程式碼。兩格是對 GitLab 正確的那一邊，
    > 而報告的目的地就是 GitLab。

    diff 包在 <details> 裡收合：一筆 finding 的 diff 可能幾十行，攤開來會把整份報告
    的可讀性吃掉，而讀的人多半先看標題與理由、需要時才展開。<details> 之後必須空一行，
    否則 GitLab 不會把裡面的內容當 markdown 解析，圍籬會原樣印出來。

    整段縮排兩格是為了讓它留在該筆 bullet 之內；markdown 會把圍籬的縮排從內容行一併
    扣掉，所以 diff 本身不會多出兩格。
    """
    title = contract.plain(item.get("title"))
    reason = contract.plain(item.get("reason"))
    code = contract.plain(item.get("diffCode"))

    lines = []
    if title:
        lines.append("- %s" % title)
    if reason:
        points = contract.as_list(reason)
        if title:
            lines.append(_indent(points))
        elif points == reason:
            # 沒有標題又切不動時理由自己當 bullet —— 否則會是一段縮排卻沒有歸屬的文字。
            lines.append("- %s" % points)
        else:
            # 沒有標題但切得動：各句直接當這一筆的條目，不必多一層。
            lines.append(points)

    if code:
        fence = contract.fence_for(code)
        block = "%s%sdiff\n%s\n%s%s" % (
            "<details>\n\n", fence, code, fence, "\n</details>")
        # 有 bullet 才縮排；沒有的話縮排會變成一段無主的內容。
        lines.append(_indent(block) if lines else block)

    return "\n".join(lines)


def _file_body(path, findings):
    """一個檔案底下的內容（不含 `### N. 路徑` 那一行）。

    回傳空清單代表這個檔案沒有任何可呈現的內容 —— 呼叫端據此整個略過它，不留下一個
    底下什麼都沒有的標題，編號也不會跳號。
    """
    body = []
    for position, item in enumerate(findings, start=1):
        block = _entry_block(item, path, position)
        if block:
            body.append(block)
    return body


def render(inputs):
    """把步驟 3 的結構化分析渲染成報告裡「AI 分析結果」底下的內容。

    回傳的是接在 AI 分析標題底下的那一段 —— 標題本身由入口腳本寫出，因為那個字串
    同時是下一輪切段的邊界，只能有一個來源。

    版面：

        ## Summary
        - <總覽第一句>
        - <總覽第二句>

        ## Code Changes
        ### 1. <檔案路徑>
        - <標題>
          - <理由第一句>
          - <理由第二句>
          ```diff
          <diff>
          ```

    空的欄位整段不放：一個只有標題、底下什麼都沒有的區塊會讓人以為內容漏掉了。
    整個 mrDiff 為空時連 "## Code Changes" 都不出現。
    """
    analysis = inputs["analysis"]

    blocks = []

    # 總覽排成逐行的清單。AI 回來的是一句接一句的**一整段**，在結果視窗會折成一片
    # 文字牆、貼到討論串則是一個段落 —— 兩邊都難以掃讀。
    #
    # 斷行在這裡做而不是在步驟 3 改掉 overview：產物存的是 AI 說了什麼，版面由它推導。
    # 改掉原文之後，想換一種版面就只能重新呼叫一次 AI。
    #
    # as_list() 會尊重來源已有的結構（自帶換行、自帶有序編號），切不動就原樣回傳。
    #
    # 每一筆 finding 的理由用的是同一個函式（見 _entry_block）—— 兩處都是「AI 回來的
    # 一整段」，沒有理由一邊斷行一邊不斷。
    overview = contract.as_list(analysis.get("overview"))
    if overview:
        blocks.append("## Summary")
        blocks.append(overview)

    # 型別已由 contract.validate_analysis() 在入口檢查過，這裡不重複。
    mr_diff = analysis.get("mrDiff") or {}

    files = []
    index = 0
    for path, findings in mr_diff.items():
        clean = contract.plain(path)
        body = _file_body(clean, findings)
        if not body:
            continue
        index += 1
        files.append("### %d. `%s`" % (index, clean))
        files.extend(body)
    if files:
        blocks.append("## Code Changes")
        blocks.extend(files)

    return "\n\n".join(blocks)
