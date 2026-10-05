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


def _details(code):
    """diff 的收合區塊。

    diff 包在 <details> 裡收合：一個 hunk 的 diff 可能幾十行，攤開來會把整份報告的
    可讀性吃掉，而讀的人多半先看標題與理由、需要時才展開。<details> 之後必須空一行，
    否則 GitLab 不會把裡面的內容當 markdown 解析，圍籬會原樣印出來。
    """
    fence = contract.fence_for(code)
    return "%s%sdiff\n%s\n%s%s" % ("<details>\n\n", fence, code, fence,
                                   "\n</details>")


def _finding_lines(item):
    """一筆 finding 的標題與理由。回傳行的清單，整筆都沒有內容時回空清單。

    形狀：

        - <標題>
          - <理由第一句>
          - <理由第二句>

    **理由與總覽用同一套斷行。** AI 回來的理由跟總覽一樣是一句接一句的一整段，在結果
    視窗會折成一片文字牆、貼到討論串則是一個段落。contract.as_list() 遇到句末標點就斷，
    逐行排成該筆之下的子清單；它會尊重來源已有的結構（自帶換行、自帶有序編號），只斷得出
    一段時原樣回傳，所以可以無條件套用 —— 單句的理由仍是縮排的一行。

    子清單縮排兩格。CommonMark（GitLab 用的那一套）據此把它收進該筆 bullet 之內。

    > python-markdown 在兩格縮排下不認巢狀，會把理由各句拉成與標題同層的項目；四格縮排
    > 則反過來把 <details> 吸進子項目裡、圍籬變成行內程式碼。兩格是對 GitLab 正確的那一邊，
    > 而報告的目的地就是 GitLab。
    """
    title = contract.plain(item.get("title"))
    reason = contract.plain(item.get("reason"))

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
    return lines


def _group_by_hunk(findings):
    """把指向**同一個 hunk** 的發現收成一組，回傳 [[item, ...], ...]。

    模型對同一段程式碼常常分成好幾個 JSON 節點講（「這裡調高了上限」、「這會拖長失敗
    時間」），而那幾筆的 diffCode 是同一段文字 —— 不分組的話，同一個 hunk 的收合區塊
    會一字不差地重複貼好幾次，讀的人得自己比對才知道那是同一段。

    鍵用 diffCode 本身而不是 hunk 標頭：那段文字由 contract.hunk_of() 從同一份 diff
    切出來，同一個 hunk 必然一字不差，而標頭要再解析一次才拿得到 —— 多一份解析就多一份
    會漂移的規則。

    **沒有 diffCode 的各自成組。** 它們的 diffCode 都是空字串，當成鍵的話所有「位置
    指不到」的發現會被併成一組，而它們之間毫無關係。

    分組保持**首次出現的順序**，組內保持模型原本的相對順序。模型若交錯著講
    （hunk A、hunk B、又回到 A），同一個 hunk 的幾筆會被收到一起 —— 必須如此，因為
    diff 只掛在該組第一筆，後續各筆是靠「緊跟在後面」表達它們講的是同一段。
    """
    groups = []
    by_code = {}
    for item in findings:
        code = contract.plain(item.get("diffCode"))
        if not code:
            groups.append([item])
            continue
        bucket = by_code.get(code)
        if bucket is None:
            bucket = [item]
            by_code[code] = bucket
            groups.append(bucket)       # 同一個 list 物件，後面 append 會一起長
        else:
            bucket.append(item)
    return groups


def _group_block(group):
    """一組（同一個 hunk）的發現，組成報告裡的條目。

    形狀：

        - <第一筆的標題>
          - <理由>
          <details>

          ```diff
          <diff>
          ```
          </details>
        - <第二筆的標題>
          - <理由>

    **diff 只掛在該組的第一筆。** 每一筆各貼一次的話，同一段程式碼會在報告裡出現 N 次。
    掛第一筆而不是最後一筆：讀的人先看到那段程式碼，接下來幾筆都是在講它；掛最後一筆則
    是規格警告過的那個形狀（收合區塊落在尾端，讀起來像只有那一筆有對應的程式碼）。

    整段縮排兩格是為了讓它留在該筆 bullet 之內；markdown 會把圍籬的縮排從內容行一併
    扣掉，所以 diff 本身不會多出兩格。
    """
    entries = [lines for lines in (_finding_lines(one) for one in group) if lines]
    code = contract.plain(group[0].get("diffCode"))

    if not entries:
        # 整組都沒有標題也沒有理由。維持既有行為：有程式碼就原樣放，不縮排 ——
        # 沒有 bullet 可以依附時，縮排只會變成一段無主的內容。
        return _details(code) if code else ""

    if code:
        entries[0].append(_indent(_details(code)))

    return "\n".join("\n".join(entry) for entry in entries)


def _file_body(findings):
    """一個檔案底下的內容（不含 `### N. 路徑` 那一行）。

    回傳空清單代表這個檔案沒有任何可呈現的內容 —— 呼叫端據此整個略過它，不留下一個
    底下什麼都沒有的標題，編號也不會跳號。
    """
    body = []
    for group in _group_by_hunk(findings):
        block = _group_block(group)
        if block:
            body.append(block)
    return body


def _jira_entry(analysis):
    """JIRA 指引那一節的內容（不含 `## 詳細資料` 那一行）。

    沒有採用有效的 key 時回空字串，呼叫端據此整節不放。

    **這一節是報告裡唯一提到那張單子的地方。** 出處那一段曾經印過 `JIRA: <key>`，後來
    移除了（見 `contract.render_footer`），所以 key 現在只存在於產物的資料裡 —— 讀報告
    的人看不到，而那張單子正是這份分析的前提。

    **狀態不在這裡重新判定。** `jira_state` 由步驟 3 的 summary 鉤子判定並隨結構帶過來；
    規格明文要求這一步沿用它。自己再認一次 key 的樣式就有第二份規則，而兩份必然漂移。

    只有 `ok` 會出現這一節：

        ok       採用了這張單子 -> 出現
        none     沒有要用       -> 不出現
        invalid  抽到但不是 key -> 不出現

    `invalid` 不出現是因為那個字串不是 key（例如標題第一個方括號放的是 `WIP`），為它產生
    一行「想知道更多請看這裡」會把讀者送向一個不存在的議題。**也因此這一節不負責「抽錯了」
    那個訊號** —— 該訊號在出處移除 JIRA 那一輪即已失去，本輪不恢復（見 design 風險二）。

    另外要求 key 非空：`validate_analysis()` 不保證狀態與 key 一致，少了這個條件，一份
    「狀態說有效、key 卻是空的」結構會印出一行指向空字串的指引。

    網址取現成的 `jira_url`，不呼叫 `contract.jira_url()` —— 步驟 3 已經填好，而那一支讀
    的是環境變數；這一步重算一次就多一個可能與產物不一致的來源。組不出網址（沒設
    `JIRA_SERVER_URL`）時只印 key 的文字：那是部署的設定問題，與 key 對不對無關，而知道是
    哪一張單子比因為做不成連結就整節消失有用。
    """
    if contract.plain(analysis.get("jira_state")) != contract.JIRA_STATE_OK:
        return ""

    key = contract.plain(analysis.get("jira_key"))
    if not key:
        return ""

    url = contract.plain(analysis.get("jira_url"))
    target = "[%s](%s)" % (key, url) if url else key
    return "- For more information, please refer to %s" % target


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

        ## 詳細資料
        - For more information, please refer to [<JIRA key>](<網址>)

    空的欄位整段不放：一個只有標題、底下什麼都沒有的區塊會讓人以為內容漏掉了。
    整個 mrDiff 為空時連 "## Code Changes" 都不出現。

    詳細資料那一節排在最後，而且只在採用了有效的 JIRA key 時出現（見 _jira_entry）。
    放最後是因為它是「要更多就往這裡去」的指引、不是分析的內容 —— 排在總覽之前的話，
    一份報告的開頭就先告訴讀者他要的東西在別處。
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
    # 每一筆 finding 的理由用的是同一個函式（見 _finding_lines）—— 兩處都是「AI 回來的
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
        body = _file_body(findings)
        if not body:
            continue
        index += 1
        files.append("### %d. `%s`" % (index, clean))
        files.extend(body)
    if files:
        blocks.append("## Code Changes")
        blocks.extend(files)

    # 指引放最後：它不是分析的內容，是看完之後要往哪裡去。
    #
    # **沒有任何分析內容時連它也不放**（`blocks` 為空）。它是對其他內容的註解，與涵蓋範圍
    # 那一段同一個理由：單獨存在時，產出的是一份只說「詳情請看別處」、而本身什麼都沒說的
    # 報告。而這一節若自己撐起了那一段，入口腳本的「是否有可合併的內容」就會判定為有，
    # 於是那份報告會被當成成功的產出交出去。
    jira = _jira_entry(analysis)
    if blocks and jira:
        blocks.append("## 詳細資料")
        blocks.append(jira)

    return "\n\n".join(blocks)
