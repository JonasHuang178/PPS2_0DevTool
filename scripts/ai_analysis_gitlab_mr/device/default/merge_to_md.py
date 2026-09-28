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
          <理由>
          <details>

          ```diff
          <diff>
          ```
          </details>

    理由緊接在 bullet 下一行、縮排兩格。GitLab 會把它併進同一段（markdown 的清單
    延續），結果視窗是純文字則如實顯示成兩行縮排 —— 兩邊都讀得下去。

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
        # 沒有標題時理由自己當 bullet —— 否則會是一段縮排卻沒有歸屬的文字。
        lines.append(_indent(reason) if title else "- %s" % reason)

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
        <overview>

        ## Code Changes
        ### 1. <檔案路徑>
        - <標題>
        <理由>
        <理由>
        ```diff
        <diff>
        ```

    空的欄位整段不放：一個只有標題、底下什麼都沒有的區塊會讓人以為內容漏掉了。
    整個 mrDiff 為空時連 "## Code Changes" 都不出現。
    """
    analysis = inputs["analysis"]

    blocks = []

    overview = contract.plain(analysis.get("overview"))
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
