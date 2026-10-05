#!/usr/bin/env python3
"""AI Analysis GitLab MR 的功能專屬定義。

只有「這個功能自己的東西」放在這裡 —— 通用能力（GitLab REST、檔案讀寫）都在
script_utils/ 之下，任何功能都能用。

這裡的三個 helper 服務同一件事：**讓同一支腳本同時服務 Qt 與 CI/CD 的 shell**。

    Qt   結果走信封的 data，內容直接放進下一步的 params。完全不碰檔案系統。
    CI   結果落檔，下一步以路徑讀進來。bash 的原生貨幣就是檔案。

因此每支腳本的契約是：
    輸出  data 一定有完整結果；params 給了 out_path 才**額外**落檔
    輸入  params 裡有內容就用內容；沒內容但有 <key>_path 就讀那個檔
"""

import json
import os
import re

from script_utils import logger

__all__ = [
    "MERGE_REQUEST_LIMIT",
    "AI_HEADING",
    "DESCRIPTION_HEADING",
    "split_description",
    "render_original_description",
    "render_description_section",
    "render_ai_section",
    "render_code_review_section",
    "COVERAGE_HEADING",
    "render_coverage_section",
    "as_list",
    "CODE_REVIEW_HEADING",
    "CODE_REVIEW_TABLE_HEADING",
    "CODE_REVIEW_SOURCE_HEADING",
    "CODE_REVIEW_SCHEMA_VERSION",
    "ACCEPTED_CODE_REVIEW_VERSIONS",
    "MAX_CODE_REVIEW_BYTES",
    "CodeReviewFormatError",
    "extract_risk_table",
    "RiskTableError",
    "code_review_body",
    "wrap_code_review",
    "validate_code_review",
    "ANALYSIS_SCHEMA_VERSION",
    "ACCEPTED_SCHEMA_VERSIONS",
    "AnalysisFormatError",
    "SCRIPT_NAME",
    "SCRIPT_VERSION",
    "render_footer",
    "JIRA_STATE_OK",
    "JIRA_STATE_NONE",
    "JIRA_STATE_INVALID",
    "JIRA_STATES",
    "validate_analysis",
    "wrap_analysis",
    "plain",
    "jira_url",
    "fence_for",
    "hunk_header_of",
    "hunk_of",
    "MAX_FINDING_DIFF_BYTES",
    "MAX_PROMPT_DIFF_BYTES",
    "MAX_COVERAGE_PATHS",
    "diff_coverage",
    "has_coverage_gap",
    "finding",
    "analysis_body",
    "CredentialError",
    "gitlab_credentials",
    "jira_credentials",
    "code_review_keyword",
    "ai_credentials",
    "ai_timeout",
    "ai_retries",
    "ai_reask",
    "ai_recheck",
    "DEFAULT_AI_TIMEOUT",
    "DEFAULT_AI_RETRIES",
    "DEFAULT_AI_REASK",
    "ai_verify_ssl",
    "describe_gitlab_error",
    "DEBUG_LOG_NAME",
    "write_artifact",
    "write_debug_log",
    "write_debug_file",
    "debug_writer",
    "resolve_text_input",
    "resolve_json_input",
]

# 除錯目錄下的日誌檔名。debug_dir 為空字串時整個機制關閉。
DEBUG_LOG_NAME = "debug.log"

# 單次查詢願意取回的 Merge Request 上限。
#
# 放在功能這一層而不是 gitlab_utils：這是「畫面一次要顯示多少筆」的產品決定，
# 不是 GitLab 的技術限制。共用模組不該替功能決定這個數字，換一個功能想看更多
# 時也不必去改共用模組。
#
# 100 是 GitLab 單頁的上限，取這個值代表「一次請求就拿得完」。
MERGE_REQUEST_LIMIT = 100


def write_artifact(out_path, content):
    """把內容寫到 out_path。out_path 為空就什麼都不做。

    回傳是否真的寫了檔案。

    「沒給路徑就不寫」是這個功能的核心行為之一：使用者沒有勾選產生除錯分析
    檔時，整條流程不應該在檔案系統留下任何東西。
    """
    if not out_path:
        return False

    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False, indent=2)

    directory = os.path.dirname(os.path.abspath(out_path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(content)

    logger.debug("寫出產物 %s（%d 字元）", out_path, len(content))
    return True


def write_debug_log(debug_dir, message):
    """把一行訊息追加到除錯目錄下的日誌。debug_dir 為空就什麼都不做。

    「有效的目錄」本身就是「要不要寫」的開關 —— 不另外設一個布林參數，
    也就不會出現「開關為真但路徑為空」這種矛盾狀態。
    """
    if not debug_dir:
        return False

    if not os.path.isdir(debug_dir):
        os.makedirs(debug_dir, exist_ok=True)

    path = os.path.join(debug_dir, DEBUG_LOG_NAME)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(str(message) + "\n")
    return True


def write_debug_file(debug_dir, name, content):
    """把一整份內容寫成除錯目錄下的獨立檔案。debug_dir 為空就什麼都不做。

    與 write_debug_log() 分開的理由是用途不同：那一支是一行一行追加的流水帳，這一支
    是「把這次實際送出／收到的東西整份留下來」。prompt 與 AI 的原始回覆都是幾千到幾萬
    字元、含換行的整塊文字，塞進流水帳只會把它淹掉。

    **只在除錯目錄有設定時才寫。** prompt 裡有整份 diff，也就是原始碼；預設就落到磁碟
    不是使用者要求的事。畫面上那個除錯輸出的勾選才是「我知道我在把這些寫出來」。

    回傳寫出的路徑，沒寫就回 False —— 呼叫端可以據此決定要不要在訊息裡提到它。
    """
    if not debug_dir:
        return False

    if not os.path.isdir(debug_dir):
        os.makedirs(debug_dir, exist_ok=True)

    path = os.path.join(debug_dir, name)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content if isinstance(content, str) else str(content))
    return path


def debug_writer(debug_dir):
    """做一個綁好除錯目錄的 write_debug_file。

    給 device 的鉤子用：它拿到的是一個「寫一份除錯檔」的能力，不必知道目錄在哪、
    也不必自己判斷除錯有沒有開 —— 沒開的時候這個函式什麼都不做。
    """
    def write(name, content):
        return write_debug_file(debug_dir, name, content)
    return write


def _read_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def resolve_text_input(params, key):
    """取一段文字輸入：params[key] 有值就用它，否則讀 params[key + '_path']。

    兩者都沒有時回傳空字串 —— 缺漏由腳本自己的必填宣告負責擋，不在這裡。
    """
    value = params.get(key)
    if isinstance(value, str) and value.strip():
        return value

    path = params.get("%s_path" % key)
    if isinstance(path, str) and path.strip():
        logger.debug("自 %s 讀取 %s", path, key)
        return _read_file(path)

    return ""


def resolve_json_input(params, key):
    """同 resolve_text_input，但值是一個物件。"""
    value = params.get(key)
    if isinstance(value, dict) and value:
        return value

    path = params.get("%s_path" % key)
    if isinstance(path, str) and path.strip():
        logger.debug("自 %s 讀取 %s", path, key)
        return json.loads(_read_file(path))

    return {}


# --- MR 描述的分段 ----------------------------------------------------------
#
# MR 的描述可能同時裝著兩樣東西：人寫的原始描述，以及先前某一輪的 AI 分析
#（這個工具只顯示報告、不寫回 GitLab，但那份報告可能被人自己貼回描述裡）。
# 步驟 1 只要前者，步驟 5 把前者接上這一輪的 AI 分析組成要顯示的報告。
#
# 原始描述**不冠任何標題** —— 它就是 GitLab 上那份描述的內容本身。因此 AI 分析
# 的標題是這裡唯一會被寫出去的標記，也是切段時唯一的邊界：它之前的都是原始描述。

# 報告裡兩個段落的標題。兩者都由**步驟 5** 在組報告時寫出。
#
# AI_HEADING 同時是切段的邊界：步驟 1 靠它把上一輪的分析從描述裡切掉。寫出與
# 切掉用同一個字串，所以只有這一份 —— 底下的比對式由它導出，不另外手寫一份
# 字面文字。改標題只要改這裡一行。
#
# DESCRIPTION_HEADING 不是邊界 —— 它永遠在 AI_HEADING 之前，切段時連同它之前的
# 內容一起被當成原始描述，再由 _DESCRIPTION_RE 把標題那一行本身去掉。
#
# 只認得「現在這一個」。改了標題之後，既有 MR 描述裡若還留著舊的那一行，它會
# 被當成描述的內容留下來，而報告又接上一段新的分析 —— 症狀是報告裡出現兩段
# AI 分析。要處理的話，在底下 _heading_pattern() 的呼叫多傳幾個舊字串即可：
#
#     _AI_RE = _heading_pattern(AI_HEADING, "# AI 分析")
#
# 本工具不寫回 GitLab，舊標題只可能來自「有人自己把報告貼回描述」，所以預設
# 不帶任何舊字串。真的撞到時，症狀在報告上看得見，補一個字串就好。
DESCRIPTION_HEADING = "# Original Description"
AI_HEADING = "# AI 分析結果"

# 涵蓋範圍那一段的標題。與 AI 分析**同層**，位置緊接在它之後。
#
# 不放進 AI 分析那一段**之內**，是因為那一段的內容由 device 的鉤子產生 —— 而涵蓋範圍
# 正是用來說「那支鉤子回報了多少」的。交給被檢查的一方渲染，它可以選擇不渲染。
#
# 它也不是切段的邊界：在 AI 分析之後，所以下一輪重新分析時會與分析一起被切掉，不會在
# Merge Request 的描述裡越疊越多。
COVERAGE_HEADING = "# 分析涵蓋範圍"

# 程式碼審閱那一段的標題。與 AI 分析**同層** —— 它在語意上是並列的一段，不是分析
# 的子節。由這一步寫出所有段落的標題，「報告有哪幾節、各在第幾層」就只有一個地方
# 決定；讓產生內容的步驟自帶標題的話，它無從知道自己會被放在哪一層。
#
# 它不是切段的邊界（那只有 AI_HEADING），因為它永遠在 AI 分析之後，切段時連同
# AI 分析一起被丟掉。
CODE_REVIEW_HEADING = "# Code Review 報告"

# 報告裡總表的小標題，低於 CODE_REVIEW_HEADING 一層。
CODE_REVIEW_TABLE_HEADING = "## 風險評估表"

# 在**別人的文件**裡找總表那一節時用的標題，也就是附件（工程師用 AI code review
# 工具產出的那份 markdown）裡的節名。
#
# **這一個與上面兩個是不同的東西，不要合成一份。** 上面兩個是我們報告的版面，這一個
# 是搜尋別人文件的依據；改我們的小標題不該影響去別人文件裡找什麼，反之亦然。名字裡
# 的 SOURCE_ 前綴就是在講這件事。
#
# 這與 AI_HEADING 的情況剛好**相反**：那一個同時是「寫出去」與「切回來」的同一個
# 邊界，所以必須只有一份來源。這兩者之間沒有那種關係，合成一個只會製造一條不存在
# 的耦合。
#
# 各條產品線的 code review 工具產出格式不同，那一節不一定叫同一個名字，所以這個值
# **可由 device 覆寫**（見 device.code_review_source_heading()）。會變的是別人工具
# 的產出格式，不是本工具的處理方式 —— 所以變的只有這個字串，擷取的演算法與報告的
# 版面都只有一份。
CODE_REVIEW_SOURCE_HEADING = "## 風險評估總表"


def _heading_pattern(*headings):
    """由標題常數**導出**寬鬆的比對式，不另外手寫一份字面文字。

    這件事非做不可：認得的規則若自己抄一份標題文字，改了常數而忘了改它時，寫出去
    的標題與切得掉的標題就是兩個不同的東西 —— 步驟 5 寫 A、步驟 1 找 B，於是切不到
    邊界，舊的 AI 分析被當成原始描述留下來，報告每跑一次多疊一段。而每一步都回報
    成功，沒有任何地方會喊。導出之後，常數就是唯一要改的地方。

    導出的比對式比常數本身寬鬆：階層 # 到 ###### 都收、大小寫不分、詞與詞之間與
    行首行尾的空白都容許。描述是人在 GitLab 網頁上編輯的東西，這些都會被動到，而
    動到不該讓邊界消失。

    整串以 ^...$ 錨定，所以「AI 分析結果」與「AI 分析」兩個 alternative 不會互相
    誤中 —— 前者不會被後者的規則吃掉半截。
    """
    alternatives = []
    for heading in headings:
        words = heading.lstrip("#").split()
        alternatives.append(r"\s*".join(re.escape(w) for w in words))
    return re.compile(r"^#{1,6}\s*(?:%s)\s*$" % "|".join(alternatives), re.I)


_DESCRIPTION_RE = _heading_pattern(DESCRIPTION_HEADING)
_AI_RE = _heading_pattern(AI_HEADING)

# CODE_REVIEW_HEADING 與 CODE_REVIEW_SOURCE_HEADING **刻意不在這裡**。
#
# 切段的邊界只有 AI_HEADING：程式碼審閱那一段永遠在 AI 分析之後，所以切在 AI 分析的
# 標題上時它連同被丟掉，貼回描述再重跑也不會累積。多認一個邊界只會讓「AI 分析之後、
# 程式碼審閱之前」那一段內容找不到歸屬。
#
# CODE_REVIEW_SOURCE_HEADING 更不屬於這裡 —— 它是拿去搜尋**別人的文件**的，與 MR 描述
# 的切段完全無關（見 extract_risk_table()）。


def _heading_positions(lines):
    """掃出兩個標題的行號，回傳 (原始描述, AI 分析)，沒找到的為 None。

    圍籬（``` 或 ~~~）內的內容一律不當標題看。描述裡的程式碼區塊剛好出現
    "# AI 分析" 的機會不高，但真的發生時，在那裡切下去會產出一份看起來正常、
    實際上被截斷的原始描述 —— 而被截掉的那一段會在寫回描述時真的消失。
    """
    fence = None
    description_at = None
    ai_at = None

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue

        if description_at is None and _DESCRIPTION_RE.match(stripped):
            description_at = index
        elif ai_at is None and _AI_RE.match(stripped):
            ai_at = index

    return description_at, ai_at


def split_description(text):
    """把 MR 描述切成 (原始描述, 上一次的 AI 分析)。

    兩段都**不含**標題那一行 —— 標題一律由 render_* 寫出，拼法因此只有一個來源。

    三種情況：

        有 AI 分析標題         原始描述 = 該標題之前那一段
        沒有 AI 分析標題       整份都是原始描述
        連原始描述標題也沒有   整份都是原始描述

    最後一種最重要：一筆從沒被這個工具處理過的 MR，描述就是純人寫的內容，沒有
    任何標題。若要求一定要找到標題才回傳內容，第一次跑的結果會是空的 —— 而空
    描述在下游是合法值（步驟 1 不視為失敗），症狀會是「AI 拿到一份空白去分析」，
    不是一個錯誤訊息。
    """
    lines = (text or "").splitlines()
    description_at, ai_at = _heading_positions(lines)

    # AI 分析的標題跑到原始描述標題前面是不該出現的順序（有人手動搬動過）。
    # 那種情況下不信任原始描述的標題，改當成「整份都是原始描述」—— 寧可多留
    # 一段給人看，也不要把人寫的內容切掉。
    if description_at is not None and ai_at is not None and ai_at < description_at:
        description_at = None

    start = description_at + 1 if description_at is not None else 0
    end = ai_at if ai_at is not None else len(lines)

    original = "\n".join(lines[start:end]).strip()
    previous_ai = ("\n".join(lines[ai_at + 1:]).strip()
                   if ai_at is not None else "")
    return original, previous_ai


def render_original_description(original):
    """步驟 1 的產物：原始描述本身，不冠任何標題。

    內容就是 GitLab 上那份描述扣掉上一輪的 AI 分析之後剩下的部分。不再加上
    "# Original description" —— 那一行是工具自己加的，對讀報告的人沒有意義，而且
    它會跟著報告被貼回描述，下一輪再被讀進來。

    原始描述是空的就回傳空字串，而不是一個只有標題的空區塊。
    """
    body = original.strip()
    return body + "\n" if body else ""


def render_description_section(original):
    """報告裡「原始描述」那一段：標題加上內容。原始描述為空就回傳空字串。

    與 render_original_description() 的差別是**有沒有標題**，兩者服務不同的消費者：

        render_original_description()  步驟 1 的產物（01_description.md）。
                                       就是 GitLab 上那份描述的內容本身，不冠標題。
        render_description_section()   報告裡的那一段。標題由這裡加上。

    分成兩支而不是共用一支，是因為標題屬於**報告**而不屬於描述。步驟 1 的產物冠上
    標題的話，那一行會跟著報告被貼回 MR 描述，下一輪再被讀進來 —— 雖然切得掉，但
    那是讓工具自己製造出要再清理的東西。
    """
    body = plain(original)
    if not body:
        return ""
    return "%s\n\n%s\n" % (DESCRIPTION_HEADING, body)


def render_ai_section(summary):
    """步驟 5 接在原始描述後面的那一段。"""
    return "%s\n\n%s\n" % (AI_HEADING, summary.strip())


# 總覽那一段的斷行 ---------------------------------------------------------
#
# 模型回來的總覽是一句接一句的**一整段**（prompt 要的就是「三到五句」）。那一段在結果
# 視窗會依寬度折成一片文字牆，貼到討論串則是一個段落 —— 兩邊都難以掃讀。
#
# 斷行放在渲染這一側，**不改產物裡的原文**：產物存的是來源說了什麼，版面由它推導。改掉
# 原文之後，想換一種版面就只能重新呼叫一次 AI；留在渲染端則連既有的產物重跑一次就能
# 受益。

# 句末標點。**只認全形。**
#
# 半形那三個幾乎都是誤切：`.` 出現在 v1.0 / 0.5 / e.g.，`!` 出現在 !7 這種 Merge Request
# 編號，`?` 出現在查詢字串 ?foo=bar。全形句號不會出現在數字或識別碼裡，所以這條規則的
# 誤切機會接近零 —— 整個方案能成立就是靠這一點。
_SENTENCE_END = u"。！？"

# 句末標點，連同後面緊跟的收尾符號。
#
# 收尾符號要留在**前**一段：`他說「要改」。`、`（見下）。` 把 `」`、`）` 留給下一段的話，
# 下一行會以一個孤立的右括號開頭。
_SENTENCE_RE = re.compile(u"[%s]+[」』”’）)〕】》〉]*" % _SENTENCE_END)

# 行內的有序編號。四種寫法都收：`1.` `1、` `1)` `(1)`。
#
# 三道守衛，少一道就會切壞正常的句子：
#
#   前面必須是開頭、空白或句末標點   `v1.` 的 1 前面是 v，排除；而 `1.調高。2.改逾時。`
#                                    的 2 前面是 `。`，要收 —— 模型不加空白是常態
#   後面不可緊跟數字                 `1.0` 的 1. 後面是 0，排除（版本號最可能的誤判來源）
#   必須由 1 起算、連續遞增、至少兩個  見 _ordered_points
_ORDER_RE = re.compile(u"(^|[\\s%s；;])\\(?(\\d{1,2})[.、)]\\s*(?![0-9])" % _SENTENCE_END)


def _ordered_points(text):
    """文字自帶的行內有序編號。切得出來回清單，否則回 None。

    **必須由 1 起算、連續遞增、至少兩個。** 這是整條規則最重要的守衛：文字裡偶然出現的
    數字加標點不會剛好構成 1,2,3 的遞增序列。只認單獨一個 `1.` 的話，「v1. 0 之後」這類
    寫法就會被切成兩段。
    """
    marks = []
    for match in _ORDER_RE.finditer(text):
        number = int(match.group(2))
        if number != len(marks) + 1:
            return None                     # 不是從 1 開始，或跳號
        # 內容的起點在整個標記之後；前一段的終點在分隔字元之前。
        marks.append((match.start() + len(match.group(1)), match.end(), number))

    if len(marks) < 2:
        return None

    points = []
    for index, (head, body_start, number) in enumerate(marks):
        tail = marks[index + 1][0] if index + 1 < len(marks) else len(text)
        content = text[body_start:tail].strip()
        if content:
            # 編號保留，但正規化成 `N. ` —— `1、`、`1)`、`(1)` 都不是 markdown 的清單
            # 語法，貼到討論串不會變成清單。換成 `N. ` 則數字與順序都還在。
            points.append(u"%d. %s" % (number, content))
    return points or None


def _sentence_points(text):
    """依全形句末標點把一段文字切開。標點留在前一段。"""
    points = []
    last = 0
    for match in _SENTENCE_RE.finditer(text):
        chunk = text[last:match.end()].strip()
        if chunk:
            points.append(chunk)
        last = match.end()
    tail = text[last:].strip()
    if tail:
        # 最後一句沒有標點也要算 —— 模型常常省略最後那一個句號。
        points.append(tail)
    return points


def as_list(text):
    """把一段總覽文字排成逐行的清單。切不動就原樣回傳。

    **這是 device 作者的公開 API。**

    依來源的形狀決定，三條互斥、先到先用：

        已有換行       原樣 —— 來源自己做過版面決定了，覆寫它才是真正的損失
        行內有序編號   保留編號，逐行排成 `N. `（用編號通常表示有順序）
        以上皆非       依全形句末標點斷開，逐行排成 `- `

    只斷得出一段時原樣回傳 —— 單項清單在視覺上是噪音，而「這份摘要只有一句話」本身就
    看得出來。

    不設點數上限：prompt 要的是三到五句，不會爆；設了上限反而會出現「有時是清單、有時是
    一整段」的不一致，那比條目多更難解釋。
    """
    body = plain(text)
    if not body:
        return ""

    if "\n" in body:
        return body

    points = _ordered_points(body)
    if points:
        return "\n".join(points)

    points = _sentence_points(body)
    if len(points) < 2:
        return body
    return "\n".join(u"- %s" % one for one in points)


def render_code_review_section(body):
    """報告裡「Code Review 報告」那一段，由步驟 4 的結構渲染。

    版面：段落標題、附件的日期／作者／連結三行、總表的小標題、表格本身。兩個標題都由
    **這裡**寫出 —— 產生內容的步驟不自帶標題，因為它無從知道自己會被放在哪一層。

    三行資訊中值為空的那一行整行不印。日期只取到日，不做時區換算 —— 印出的就是上傳者
    當時看到的那一天。

    取得失敗時（error 有值）三行**照樣印**，並在其後加一行說明。那時連結的價值最高：
    讀者點進去就能自己看全文，而這正是這一段設計的目的（報告只放總表，全文靠連結）。

    表格與 error 都沒有時回傳空字串 —— 一個只有標題的空區塊會讓人以為內容漏掉了。
    """
    if not isinstance(body, dict):
        return ""

    table = plain(body.get("risk_table"))
    error = plain(body.get("error"))
    if not table and not error:
        return ""

    parts = [CODE_REVIEW_HEADING, ""]

    # 三行各自是引言裡的一個**清單項目**，不是三行連著的文字。
    #
    # 連著寫的話 markdown 會把它們併成同一段 —— 換行在段落內是「軟換行」，轉譯後變成
    # 一個空白，三行於是擠成一行。以實際的轉譯器驗過，不是推論。
    #
    # 選清單而不是「行尾兩個空白」或「中間空一行」：行尾空白是看不見的，編輯器與
    # linter 會把它清掉，而這一段的正確性就靠那兩個空白；中間空一行則會變成三個段落，
    # 多出來的間距與「三行一組的註記」不符。清單本來就是這三個欄位的形狀。
    meta = []
    created = plain(body.get("created"))
    if created:
        meta.append("> - 日期: %s" % created[:10])
    author = plain(body.get("author"))
    if author:
        meta.append("> - 作者: %s" % author)
    filename = plain(body.get("filename"))
    url = plain(body.get("url"))
    if filename:
        meta.append("> - 連結: %s" % _link(_escape_link_text(filename), url))
    if meta:
        parts.extend(meta)
        parts.append("")

    if error:
        parts.append("⚠️ 無法取得程式碼審閱報告：%s" % error)
        parts.append("")

    if table:
        parts.append(CODE_REVIEW_TABLE_HEADING)
        parts.append("")
        parts.append(table)
        parts.append("")

    return "\n".join(parts).rstrip("\n") + "\n"


def _int_of(value):
    """讀成非負整數。讀不出來就是 0 —— 這一段是註解，不該為了一個壞掉的數字讓報告失敗。"""
    if isinstance(value, bool) or not isinstance(value, int):
        return 0
    return max(value, 0)


def _bytes_note(coverage):
    """截斷那一行後面的位元組說明。數字不全時整段不印。"""
    sent = _int_of(coverage.get("bytes_sent"))
    total = _int_of(coverage.get("bytes_total"))
    if not sent or not total or total <= sent:
        return ""
    return "（送出 %d / 原始 %d bytes）" % (sent, total)


def _coverage_list(title, bucket):
    """一類缺口的路徑清單。數量以 count 為準，清單可能只有前幾筆。"""
    count = _count_of(bucket)
    paths = (bucket or {}).get("paths")
    paths = [plain(one) for one in paths] if isinstance(paths, list) else []
    paths = [one for one in paths if one]
    if not paths:
        return []

    lines = ["**%s（%d）**" % (title, count), ""]
    lines.extend("- `%s`" % one for one in paths)
    rest = count - len(paths)
    if rest > 0:
        lines.append("")
        # 說出還有幾筆，而不是讓清單在這裡無聲地停住 —— 否則讀的人會把列出來的
        # 當成全部，而上面那個數字與它對不起來時只會被當成錯字。
        lines.append("…（其餘 %d 筆未列出）" % rest)
    lines.append("")
    return lines


def render_coverage_section(analysis):
    """報告裡「分析涵蓋範圍」那一段。沒有缺口時回傳空字串。

    這一段由**合併那一步**寫出，不由 device 的鉤子產生 —— 它說的正是「那支鉤子回報了
    多少」，交給被檢查的一方渲染，它可以選擇不渲染。

    四類缺口分開列，不合成一個比例：每一類的下一步完全不同（調上限、調 prompt、無能
    為力），合成一個數字就是把「要調什麼」重新藏起來。

    版面：

        # 分析涵蓋範圍

        這支 Merge Request 共有 90 個檔案變更，完整送進分析的有 21 個，AI 回報了其中 3 個。

        - ⚠️ 69 個檔案的差異超過送出上限，沒有送進分析（送出 120000 / 原始 496320 bytes）
        - ⚠️ 18 個檔案已送進分析，但 AI 沒有回報

        <details>

        **沒有送進分析（69）**

        - `src/a.cpp`

        </details>

    路徑清單包在 <details> 裡收合：缺口有幾十筆是常態，攤開來會把報告的可讀性吃掉，而
    讀的人多半先看數量、需要時才展開。<details> 之後必須空一行，否則 GitLab 不會把裡面
    的內容當 markdown 解析。
    """
    coverage = analysis.get("coverage") if isinstance(analysis, dict) else None
    if not has_coverage_gap(coverage):
        return ""

    parts = [COVERAGE_HEADING, ""]
    parts.append("這支 Merge Request 共有 %d 個檔案變更，完整送進分析的有 %d 個，"
                 "AI 回報了其中 %d 個。"
                 % (_int_of(coverage.get("files_changed")),
                    _int_of(coverage.get("files_sent")),
                    _int_of(coverage.get("files_reported"))))
    parts.append("")

    dropped = _count_of(coverage.get("dropped"))
    if dropped:
        parts.append("- ⚠️ %d 個檔案的差異超過送出上限，沒有送進分析%s"
                     % (dropped, _bytes_note(coverage)))
    empty = _count_of(coverage.get("empty"))
    if empty:
        parts.append("- ⚠️ %d 個檔案的差異內容是空的（二進位檔、只有模式變更，"
                     "或來源未提供）" % empty)
    missing = _count_of(coverage.get("missing"))
    if missing:
        parts.append("- ⚠️ %d 個檔案已送進分析，但 AI 沒有回報" % missing)
    unknown = _count_of(coverage.get("unknown"))
    if unknown:
        parts.append("- ⚠️ %d 筆回報的路徑在差異中找不到對應的檔案" % unknown)
    parts.append("")

    detail = []
    detail.extend(_coverage_list("沒有送進分析", coverage.get("dropped")))
    detail.extend(_coverage_list("差異內容是空的", coverage.get("empty")))
    detail.extend(_coverage_list("AI 沒有回報", coverage.get("missing")))
    detail.extend(_coverage_list("差異中找不到", coverage.get("unknown")))
    if detail:
        parts.append("<details>")
        parts.append("")
        parts.extend(detail)
        parts.append("</details>")
        parts.append("")

    return "\n".join(parts).rstrip("\n") + "\n"



# --- GitLab 憑證與錯誤分流 --------------------------------------------------
#
# 本功能有兩支腳本要連 GitLab，兩邊的憑證來源與錯誤訊息必須一致。各自寫一份的話
# 兩份會慢慢長歪，而使用者看到的差異（同樣是 401，一支說「請檢查權杖」、另一支說
# 「查詢失敗」）完全沒有道理。

class CredentialError(Exception):
    """憑證缺漏。

    帶著入口腳本回報時需要的三樣東西，讓它一行就能轉成 FAIL：

        except ai_analysis_gitlab_mr.CredentialError as exc:
            script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    這個模組**不自己呼叫 reply_fail** —— 那會讓一支看起來只是取值的函式把行程
    結束掉，而呼叫端從簽章上看不出來。
    """

    def __init__(self, message, detail, code):
        super(CredentialError, self).__init__(message)
        self.detail = detail
        self.code = code


def _truthy(text):
    return str(text).strip().lower() in ("true", "1", "yes")


def gitlab_credentials():
    """自環境變數取出 GitLab 的連線資訊，回傳 (server_url, token, verify_ssl)。

    憑證只從環境變數讀，不從 config 讀 —— 腳本端因此只有一條取值路徑，Qt 與 CI
    對它來說長得一模一樣。Qt 會把設定檔 Service 區塊的鍵以全大寫注入。

    GITLAB_VERIFY_SSL 未設定時視為**不驗證**（見 design.md 決策二十三）。這個預設
    是明確的取捨：目標環境是否使用自簽憑證尚不確定，而驗證失敗會讓功能完全無法
    使用。

    缺漏時拋出 CredentialError，由入口腳本轉成 FAIL。
    """
    server_url = os.environ.get("GITLAB_SERVER_URL", "").strip()
    token = os.environ.get("GITLAB_ACCESS_TOKEN", "").strip()
    verify_ssl = _truthy(os.environ.get("GITLAB_VERIFY_SSL", "false"))

    if not server_url:
        raise CredentialError(
            "未設定環境變數 GITLAB_SERVER_URL",
            "設定檔的 Service.Gitlab_Server_URL 會由工具注入為這個環境變數；"
            "以命令列執行時請自行設定。",
            "GITLAB_SERVER_URL_MISSING")

    if not token:
        raise CredentialError(
            "未設定環境變數 GITLAB_ACCESS_TOKEN",
            "設定檔的 Service.Gitlab_Access_Token 會由工具注入為這個環境變數；"
            "以命令列執行時請自行設定。",
            "GITLAB_ACCESS_TOKEN_MISSING")

    return server_url, token, verify_ssl


def jira_credentials():
    """自環境變數取出 JIRA 的連線資訊，回傳 (base_url, token)。

    與 gitlab_credentials() 同一套規則：只讀環境變數，Qt 會把設定檔 Service 區塊的
    鍵以全大寫注入。

    **缺漏不一定是錯誤**，所以這裡拋例外、由呼叫端決定要不要當成失敗：組 prompt 時
    JIRA 只是補充資料，沒設定就不放那一段；但要是有人專門去查一張 issue 卻沒有位址，
    那就是錯誤。這個函式不替呼叫端決定。
    """
    base_url = os.environ.get("JIRA_SERVER_URL", "").strip()
    token = os.environ.get("JIRA_ACCESS_TOKEN", "").strip()

    if not base_url:
        raise CredentialError(
            "未設定環境變數 JIRA_SERVER_URL",
            "設定檔的 Service.Jira_Server_URL 會由工具注入為這個環境變數；"
            "以命令列執行時請自行設定。",
            "JIRA_SERVER_URL_MISSING")

    if not token:
        raise CredentialError(
            "未設定環境變數 JIRA_ACCESS_TOKEN",
            "設定檔的 Service.Jira_Access_Token 會由工具注入為這個環境變數；"
            "以命令列執行時請自行設定。",
            "JIRA_ACCESS_TOKEN_MISSING")

    return base_url, token


def code_review_keyword():
    """自環境變數取出 code review 附件的檔名前綴。未設定時拋 CredentialError。

    **沒有預設值是刻意的。** 給它一個預設值會讓設定鍵變成裝飾 —— 使用者漏設時靜默套用
    一個他沒選的前綴，而症狀是「議題上明明有附件，報告裡卻沒有那一段」。與 device 的
    VERSION 同一個判斷：沒有合理預設值的項目就該必填。

    訊息同時點名環境變數與設定檔的鍵。只說環境變數沒設，使用者會去設系統環境變數，而
    真正該改的是執行檔旁那份 JSON。
    """
    keyword = os.environ.get("PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH", "").strip()
    if not keyword:
        raise CredentialError(
            "未設定環境變數 PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH",
            "設定檔 Function 底下本功能區塊的 "
            "PPS_Scripts_CodeReview_File_StartsWith 會由工具注入為這個環境變數"
            "（例如值為 \"CodeReview_\"）；以命令列或 CI 執行時請自行設定。\n"
            "這一項沒有預設值：若給了預設值，漏設時會靜默改用一個你沒選的前綴，而"
            "症狀是議題上明明有附件、報告裡卻沒有那一段。",
            "CODE_REVIEW_FILE_STARTSWITH_MISSING")
    return keyword


def ai_credentials(inputs):
    """自鉤子的 inputs 取出 AI 的連線資訊，回傳 (api_url, api_key, model)。

    與另外兩個不同，AI 的四項走 **params 而不是環境變數**（見步驟 3 的入口腳本）——
    因此它們從 inputs 進來，不從 os.environ 讀。

    只有 **api_url 是必要的**，另外兩項都可以是空的：

      金鑰    這個服務以 Api_URL 尾端的 shareCode 辨識呼叫者，沒有認證標頭。
              Api_Key 有填才會多送一個 Bearer（見 ai_utils._headers）。

      模型名  **不進請求。** 模型是由 shareCode 那一端決定的，這裡的 Model 只是
              報告出處要印的資訊。把它列為必填會讓一個純粹的顯示欄位擋住整個流程。

    shareCode 本身不在這裡檢查：那是 Api_URL 的一部分，怎麼拆、缺了算不算錯，都由
    ai_utils 決定 —— 檢查跟著解析走，才不會兩邊對格式的理解分岔。

    放在契約層而不是 ai_utils：認得 inputs 的形狀是這個功能的事，script_utils 底下的
    模組不該知道任何一個功能的參數長什麼樣。
    """
    api_url = plain(inputs.get("ai_api_url"))
    api_key = plain(inputs.get("ai_api_key"))
    model = plain(inputs.get("ai_model"))

    if not api_url:
        raise CredentialError(
            "未指定 AI 端點",
            "設定檔 Service.AI_Mode_List 裡所選模式的 Api_URL 是空的。",
            "AI_API_URL_MISSING")

    return api_url, api_key, model


# 問 AI 的三個等待相關設定，設定檔沒指定時用這幾個。
#
# 與 ai_utils 的同名常數目前同值，但**各自宣告**：那邊是「任何人用 ai_utils 問 AI 的
# 預設」，這邊是「這個功能的預設」。綁成同一個的話，之後想單獨調其中一個就得先拆開。
#
# 四個一起決定最壞情況的等待時間：
#
#     逾時 × (重試次數 + 1) × (重問次數 + 1) × (重查次數 + 1) ＋ 退避
#
# 預設值（120 / 3 / 1 / 0）算出來約 16 分鐘。使用者要把等待封頂，每一個都得調得動 ——
# 只開逾時的話，他把它設成 30 秒仍然可能等上四分半，而那會看起來像設定沒有生效。
#
# 三個次數各管一層，彼此不重疊：
#
#     Retry_Count    連線層  服務沒有回應（逾時、斷線、429、5xx）
#     Reask_Count    內容層  服務回了，但解析不開（不是 JSON、結構不認得）
#     Recheck_Count  涵蓋層  解析開了，但送進去的檔案有一部分沒被回報
#
# 三層的下一步完全不同，所以不合成一個數字：想關掉「服務很忙時不要再等」的人，不該
# 連同「模型漏了檔案就再問一次」一起關掉。
DEFAULT_AI_TIMEOUT = 120
DEFAULT_AI_RETRIES = 3
DEFAULT_AI_REASK = 1

# 重查預設 **0（關閉）**。
#
# 不預設打開，是因為「送進去卻沒被回報」在目前的 prompt 之下**常常是正確的結果** ——
# ROLE_PROMPT 與 OUTPUT_SPEC 都明著交代「沒有值得注意之處的檔案不要放進 code_changes」。
# 預設打開等於替所有部署在大部分的 Merge Request 上都多付一趟 AI 的錢與時間，而第二次
# 問回來的往往一模一樣（模型本來就在遵守指令）。
#
# 真的遇到模型漏回報的人把它設成 1 或 2 —— 那是他知道自己在換什麼。
DEFAULT_AI_RECHECK = 0


def _ai_number(inputs, key, default, setting, code, allow_zero, allow_float):
    """讀一個 AI 的數值設定。沒給就回 default，給了但不合法就丟 CredentialError。

    **不靜默退回預設**是刻意的：使用者會去調這幾個值，多半正是因為服務很忙、他不想
    再等那麼久。一個打錯的值若安靜地退回預設，症狀是「我明明改了，還是等一樣久」——
    而那個症狀指不出任何原因。寧可在這一步的一開始就失敗，訊息指名是哪一個鍵。

    數字與純數字字串都收（設定檔裡 120 與 "120" 都有人寫）。布林值明確擋掉 ——
    Python 的 True 是 1，不擋的話一個寫成 true 的值會變成「一秒逾時」或「只重試一次」。

    allow_zero 分開兩種設定：逾時 0 秒沒有意義（那不是「不要等」，是「立刻失敗」），
    而重試 0 次正是「服務很忙時不要再等」的那個值。
    """
    value = inputs.get(key)

    if value is None or (isinstance(value, str) and not value.strip()):
        return default

    rule = "0 或正整數" if allow_zero else ("正數（秒）" if allow_float else "正整數")
    where = ("設定檔 Service.AI_Mode_List 裡所選模式的 %s 應該是一個%s。"
             % (setting, rule))

    if isinstance(value, bool):
        raise CredentialError("%s 不是數字：%r" % (setting, value), where, code)

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CredentialError("%s 不是數字：%r" % (setting, value), where, code)

    # 條件寫成肯定式再取反，是為了把 NaN 一起擋掉 —— NaN 的所有比較都是 False。
    within = (number >= 0) if allow_zero else (number > 0)
    if not within:
        raise CredentialError(
            "%s 必須是%s，讀到的是 %r" % (setting, rule, value), where, code)

    if not allow_float and number != int(number):
        raise CredentialError(
            "%s 必須是整數，讀到的是 %r" % (setting, value), where, code)

    return int(number) if number == int(number) else number


def ai_timeout(inputs):
    """問 AI 的逾時秒數。沒給就是 DEFAULT_AI_TIMEOUT。

    **這是 device 作者的公開 API。** 交給 ai_utils.ask(timeout=...)。
    """
    return _ai_number(inputs, "ai_timeout", DEFAULT_AI_TIMEOUT,
                      "Timeout_Seconds", "AI_TIMEOUT_INVALID",
                      allow_zero=False, allow_float=True)


def ai_retries(inputs):
    """連線層的重試次數（逾時、斷線、429、5xx）。沒給就是 DEFAULT_AI_RETRIES。

    **這是 device 作者的公開 API。** 交給 ai_utils.ask(retries=...)。

    0 是合法的，而且正是「服務很忙時不要再等」的那個設定值。
    """
    return _ai_number(inputs, "ai_retries", DEFAULT_AI_RETRIES,
                      "Retry_Count", "AI_RETRIES_INVALID",
                      allow_zero=True, allow_float=False)


def ai_reask(inputs):
    """回覆格式不符時重問的次數。沒給就是 DEFAULT_AI_REASK。

    **這是 device 作者的公開 API。** 交給 ai_utils.ask(reask=...)。

    與 retries 是**不同層**的東西：那一個管連線（服務沒回應），這一個管內容（服務回了，
    但回來的東西解析不開）。兩個都會讓總等待時間翻倍，所以要封頂就得兩個一起調。
    """
    return _ai_number(inputs, "ai_reask", DEFAULT_AI_REASK,
                      "Reask_Count", "AI_REASK_INVALID",
                      allow_zero=True, allow_float=False)


def ai_recheck(inputs):
    """送進去的檔案沒被全部回報時，重問的次數。沒給就是 DEFAULT_AI_RECHECK（0）。

    **這一個不交給 ai_utils.ask()，由入口腳本自己跑迴圈。** 理由與涵蓋範圍由入口蓋章
    同一條：判斷「回報得夠不夠」要拿鉤子的輸出對照入口手上的差異，而那是 ask() 看不到
    的東西 —— 它只認得「服務有沒有回應」與「回來的東西解析得開不開」。

    與另外兩個是**不同層**的東西：

        ai_retries  連線層  服務沒有回應
        ai_reask    內容層  服務回了，但解析不開
        ai_recheck  涵蓋層  解析開了，但有檔案沒被回報

    只看 missing 那一類缺口。dropped（太大沒送進去）與 empty（差異本身是空的）再問
    幾次都不會變，unknown（回了一個不存在的路徑）則是另一種錯 —— 把它們一起算進來，
    就會為了永遠補不回來的東西反覆付錢。

    0 是合法值，而且是預設 —— 見 DEFAULT_AI_RECHECK 那一段的理由。
    """
    return _ai_number(inputs, "ai_recheck", DEFAULT_AI_RECHECK,
                      "Recheck_Count", "AI_RECHECK_INVALID",
                      allow_zero=True, allow_float=False)


def ai_verify_ssl():
    """要不要驗證 AI 服務的 TLS 憑證。

    **未設定時不驗證**，與 GitLab 的 GITLAB_VERIFY_SSL 同一個預設、同一個理由（見
    design.md 決策二十三）：地端服務常用自簽或內部 CA 簽發的憑證，驗證失敗會讓功能
    完全無法使用，而這個工具跑在內網、對著已知的位址。

    這是一個明著寫出來的取捨，不是疏忽。要開啟就設 AI_VERIFY_SSL=true。

    為什麼讀環境變數而不是設定檔：Qt 目前只把 Service 區塊裡列在 kServiceKey[] 的鍵
    注入成環境變數，加一個新鍵要動 C++ 並重新建置。放成環境變數的話，CI 想開就開，
    而工具端維持「不驗證」這個對地端服務唯一可用的預設。
    """
    return _truthy(os.environ.get("AI_VERIFY_SSL", "false"))


def describe_gitlab_error(exc, repo):
    """把 GitLabError 轉成 (message, detail, code)，供入口腳本回報。

    共用模組只拋一種例外，型別由 status_code 分流。訊息刻意分開寫：使用者的下一步
    完全不一樣 —— 一個去換權杖，一個去改設定檔的拼字，一個去處理憑證。
    """
    status = getattr(exc, "status_code", None)

    if status in (401, 403):
        return ("GitLab 拒絕了這次請求，請檢查存取權杖",
                "%s\n\n權杖來自環境變數 GITLAB_ACCESS_TOKEN"
                "（設定檔的 Service.Gitlab_Access_Token）。\n"
                "請確認它未過期、且對專案 %s 有讀取權限。" % (exc, repo),
                "GITLAB_AUTH_FAILED")

    if status == 404:
        return ("找不到專案 %s" % repo,
                "%s\n\n請檢查設定檔 Repo_List 中的專案名稱是否拼寫正確"
                "（namespace/project 形式）。\n"
                "注意：權杖若對該專案沒有權限，GitLab 也會回 404。" % exc,
                "GITLAB_PROJECT_NOT_FOUND")

    # TLS 失敗沒有 HTTP 狀態碼（連線根本沒建立起來），只能看訊息內容。
    # requests 把憑證問題包成 SSLError，訊息裡一定帶得到這些字樣。
    lowered = str(exc).lower()
    if status is None and ("ssl" in lowered or "certificate" in lowered):
        return ("TLS 憑證驗證失敗",
                "%s\n\n兩種解法：\n"
                "  1. 把受信任的 CA 憑證指給環境變數 REQUESTS_CA_BUNDLE\n"
                "  2. 把設定檔的 Service.Gitlab_Verify_SSL 設為 \"false\"\n"
                "第一種較安全 —— 關閉驗證時，存取權杖會暴露給連線中間人。\n"
                "注意是 REQUESTS_CA_BUNDLE 而不是 SSL_CERT_FILE：底層用的是 "
                "requests，只有前者會被讀取。" % exc,
                "GITLAB_TLS_FAILED")

    return ("GitLab 查詢失敗：%s" % exc, "", "GITLAB_REQUEST_FAILED")



# --- 步驟 3 的結構化分析 → markdown ------------------------------------------
#
# 步驟 3 產出的是**結構**（每個檔案、每筆發現的標題／理由／diff），不是排好版的
# 文字。渲染放在這裡而不是步驟 3：報告長什麼樣是「報告」這件事的決定，而步驟 3
# 之後還會長出 prompt 組裝、重試、計費 —— 把排版也塞進去會讓兩件事都更難改。
#
# 放這個模組而不是直接寫在步驟 5 裡面，是為了與寫入側（analysis_body()
# 等建構函式）待在同一個畫面：欄位名散在兩邊時，改名漏一邊的症狀是 KeyError，
# 或更糟，安靜地少一段。

# 認得的結構版本。收到別的版本明確失敗，不猜 —— 猜錯的結果是一份看起來正常、
# 實際上少了幾段的報告，而它會回報成功。
#
# 版本 3 相對於 2 多了三個 JIRA 欄位（jira_key / jira_state / jira_url）。
# 版本 4 相對於 3 多了 mr_type —— 那個值決定步驟 5 用哪一份版面，所以它必須跟著產物
# 一起走，不能只存在於當次執行的參數裡。
# 版本 5 相對於 4 多了 coverage —— 這次分析涵蓋了多少。同樣必須跟著產物走：報告要靠它
# 說出「這份分析少了哪些檔案」，而步驟 5 收到的只有檔案。
ANALYSIS_SCHEMA_VERSION = 5

# **讀**得懂的版本。寫出去的一律是 ANALYSIS_SCHEMA_VERSION。
#
# 規格要的是「依版本決定如何讀取」，而不是「只讀最新的一版」—— 版本 3、4 與 5 的差別都
# 只有多一個選填欄位，讀 3 的方式就是「視為沒有種類」，讀 3、4 的方式是「視為沒有涵蓋
# 範圍資訊」。那不是猜測，是兩條知道的讀法。
#
# 實際的好處很具體：開發時常常單獨拿昨天的 03_summary.json 重跑步驟 5 來看版面，
# 而那份檔案是舊版本寫的。只認最新版會讓那個迴路在每次改版時斷一次。
#
# 加一個版本進來之前先問：那一版的讀法真的知道嗎？不知道就不要加 —— 猜的下場是一份
# 看起來正常、實際上少了幾段的報告，而它會回報成功。
ACCEPTED_SCHEMA_VERSIONS = (3, 4, 5)


# 一次分析的 JIRA 狀態。
#
#   ok       抽到（或使用者給了）一個通過檢查的 key
#   none     這次不使用 JIRA
#   invalid  抽到東西，但沒通過檢查 —— 原值保留在 jira_key 供報告顯示
#
# 三種要分得開：把 invalid 併進 none 的話，標題寫成 [WIP] 的那種錯誤就再也看不見了。
JIRA_STATE_OK = "ok"
JIRA_STATE_NONE = "none"
JIRA_STATE_INVALID = "invalid"
JIRA_STATES = (JIRA_STATE_OK, JIRA_STATE_NONE, JIRA_STATE_INVALID)


class AnalysisFormatError(Exception):
    """AI 分析結果的結構不符。

    與 CredentialError 同一個形狀：帶著入口腳本回報時要用的三樣東西，讓它一行就能
    轉成 FAIL。這個模組**不自己呼叫 reply_fail** —— 那會讓一支看起來只是在組字串的
    函式把行程結束掉，而呼叫端從簽章上看不出來。
    """

    def __init__(self, message, detail, code):
        super(AnalysisFormatError, self).__init__(message)
        self.detail = detail
        self.code = code


def plain(value):
    """收斂成去掉頭尾空白的字串。None 與非字串都吃得下。

    **這是 device 作者的公開 API。** AI 回來的 JSON 常有 null，不收斂的話報告上會
    印出 "None"。device 自己寫渲染時請用這一支，不要自己 str()。
    """
    if value is None:
        return ""
    text = value if isinstance(value, str) else str(value)
    return text.strip()


# --- 建構（寫入側）----------------------------------------------------------
#
# 三個函式對應結構的三層。步驟 3 用它們組出要落檔與回傳的東西，而不是自己寫
# dict literal：欄位名散在「步驟 3 寫」與「這個模組讀」兩邊就是兩份字串，改名漏
# 一邊的症狀是 KeyError，或更糟，安靜地少一段。寫入側與讀取側因此放同一個檔案。

# 單一 finding 帶的 diff 上限（位元組）。
#
# 整份報告最後經 stdout 回到 Qt 再塞進結果視窗，一個大 MR 的所有 hunk 全帶進來是
# 幾百 KB 起跳。gitlab_utils.get_mr_plain_diff() 的 max_bytes 是同一個考量。
MAX_FINDING_DIFF_BYTES = 4000

# 送進 prompt 的 diff 上限。超過就截斷，並在 prompt 裡明講截斷了 —— 靜默截斷會讓
# 模型對著半份 diff 給出一份自信的分析。
#
# 這個數字是**起點，不是定論**：合適的值取決於實際使用的模型 context window 有多大。
# 落地模型的規格確定後應該重訂，改這一行即可。逐檔切開分批呼叫是之後的事。
MAX_PROMPT_DIFF_BYTES = 120000

_DIFF_TRUNCATED = "\n… （diff 已截斷）"


def _clip_diff(diff):
    """把過長的 diff 截斷，並在尾端明著說它被截斷了。

    不說的話，讀報告的人會以為那個 hunk 就到那裡為止 —— 而被截掉的往往正是後半段。
    以位元組計算（中文一個字三個位元組），errors="ignore" 丟掉切邊切破的半個字。
    """
    text = plain(diff)
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_FINDING_DIFF_BYTES:
        return text
    return (encoded[:MAX_FINDING_DIFF_BYTES].decode("utf-8", "ignore")
            + _DIFF_TRUNCATED)


# --- 從 diff 裡取出指定的 hunk ----------------------------------------------
#
# 步驟 3 讓 AI 只回 hunk 的**標頭**（那一行 @@），程式碼本身由這裡從入口備好的
# diff 切出來。三個理由，第三個是主要的：
#
#   1. AI 的回覆是一份 JSON，而 JSON 的字串必須跳脫換行與反斜線。讓模型把一段含
#      \n（C 的字串）、\d（正則）、C:\path（Windows 路徑）的 diff 塞進字串欄位，
#      是在要求它做一件它偶爾會做錯、而做錯就整份解析不開的事。標頭那一行沒有這
#      個問題。
#   2. 回程少掉整份 diff 的複本，省 token 也省時間。
#   3. **報告裡的程式碼保證與 GitLab 上的一致。** 讓模型複述 diff，它可以抄錯一個
#      字元而沒有任何一步會發現 —— 那份報告看起來是完整的。
#
# 對不上時回空字串，由呼叫端決定怎麼辦。**不回退成「用模型給的原文」** —— 那會把
# 上面三件事又放回來，而且是安靜地放回來。

# 一個 hunk 的標頭。git 會在 @@ 之後接上所在的函式名，比對時不看那一段。
_HUNK_HEAD_RE = re.compile(r"@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@")

# unified diff 的檔案分界。gitlab_utils.get_mr_plain_diff() 一定會寫出這一行
# （檔頭三行是它自己補的），所以認得它就夠了。
_DIFF_FILE_RE = re.compile(r"^diff --git a/(.*?) b/(.*)$")


def hunk_header_of(text):
    """從一段文字裡抽出第一個 hunk 標頭，正規化成 `@@ -a,b +c,d @@`。找不到回空字串。

    **這是 device 作者的公開 API。**

    收得寬是刻意的：模型可能只回那一行、可能連後面的函式名一起回、也可能把整個
    hunk 連內容一起回來。三種都取得到同一個標頭；只認第一種的話，另外兩種會變成
    「對不上」，而那個訊息指不到真正的原因 —— 模型其實指對了位置。
    """
    match = _HUNK_HEAD_RE.search(plain(text))
    return match.group(0) if match else ""


def _clean_path(value):
    return plain(value).replace("\\", "/").strip("\"'").strip("/")


def _strip_ab(path):
    """去掉 git 慣用的 a/ b/ 前綴。"""
    for prefix in ("a/", "b/", "./"):
        if path.startswith(prefix):
            return path[len(prefix):]
    return path


def _same_path(candidate, wanted):
    """兩個路徑指的是不是同一個檔案。

    先原樣比，再去掉 a/ b/ 前綴比，最後才以 / 為界比對結尾 —— 模型有時只寫檔名，
    有時多帶一層目錄。以 / 為界是關鍵：直接 endswith 的話 `b/x.cpp` 會對上
    `ab/x.cpp`。

    寬鬆比對的風險是對到另一個同名的檔案，那是可接受的：找到的標頭還必須在那個
    檔案裡真的存在（見 hunk_of），兩道一起錯的機會很低。
    """
    left, right = _clean_path(candidate), _clean_path(wanted)
    if not left or not right:
        return False
    if left == right:
        return True
    left, right = _strip_ab(left), _strip_ab(right)
    return (left == right
            or left.endswith("/" + right)
            or right.endswith("/" + left))


def _file_sections(diff_text):
    """把 unified diff 依檔案切開，逐段產生 ((舊路徑, 新路徑), 內容行)。"""
    head = None
    lines = []
    for line in plain(diff_text).splitlines():
        match = _DIFF_FILE_RE.match(line)
        if match:
            if head is not None:
                yield head, lines
            head, lines = (match.group(1), match.group(2)), []
        elif head is not None:
            lines.append(line)
    if head is not None:
        yield head, lines


def _hunks(lines):
    """把一個檔案的內容切成一個個 hunk（含標頭那一行）。"""
    current = None
    for line in lines:
        if line.startswith("@@"):
            if current is not None:
                yield current
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        yield current


def hunk_of(diff_text, path, hunk_header):
    """從 diff 裡取出 path 這個檔案中、標頭為 hunk_header 的那一個 hunk。

    **這是 device 作者的公開 API。** 檔名對不上、標頭對不上、或根本沒給標頭，一律
    回空字串 —— 呼叫端據此決定要不要記警告。

    **只在對上的那個檔案裡找標頭，不跨檔搜尋。** 同一行 `@@ -12,7 +12,7 @@` 在不同
    檔案裡各有一個是常態，跨過去取就是把另一個檔案的程式碼貼進這一筆發現，而每一步
    都會回報成功。
    """
    wanted = hunk_header_of(hunk_header)
    if not wanted:
        return ""

    for (old_path, new_path), lines in _file_sections(diff_text):
        if not (_same_path(new_path, path) or _same_path(old_path, path)):
            continue
        for hunk in _hunks(lines):
            if hunk_header_of(hunk[0]) == wanted:
                return "\n".join(hunk)
    return ""


def finding(title, reason, diff_code=""):
    """mrDiff 底下的一筆：標題、理由，以及（選配）相關的那段 diff。

    欄位名是 diffCode —— 與這個功能的既有產出一致。省略或給空字串都代表「這一筆
    沒有 diff」，渲染時不會留下一個空的程式碼區塊。
    """
    return {
        "title": plain(title),
        "reason": plain(reason),
        "diffCode": _clip_diff(diff_code),
    }


# 涵蓋範圍中每一類缺口最多列出幾個路徑。
#
# 數量與清單**分開存放**，而不是「清單的長度就是數量」：一支改了幾千個檔案的 MR，完整
# 清單會把產物與結果信封撐大，而那份信封要經 stdout 回到 Qt。先截清單再拿長度當數量的
# 話，報告會說「3 個檔案未回報」而實際上是 3000 個 —— 那比沉默更糟。
MAX_COVERAGE_PATHS = 50


def _coverage_bucket(paths):
    """一類缺口：數量精確，路徑清單截到 MAX_COVERAGE_PATHS。"""
    clean = [plain(one) for one in paths]
    clean = [one for one in clean if one]
    return {"count": len(clean), "paths": clean[:MAX_COVERAGE_PATHS]}


def diff_coverage(mr_diff=None, files_sent=(), files_dropped=(),
                  files_empty=(), file_count=None, truncated=False,
                  bytes_total=0, bytes_sent=0):
    """算出這次分析涵蓋了多少，以及缺口分別落在哪一類。

    **由入口腳本呼叫，不給鉤子用。** 這份數字是用來檢查鉤子回報了多少的 —— 讓被檢查的
    一方提供它，這個機制就等於不存在：一支宣稱自己涵蓋全部的鉤子不會有任何一步發現它
    說謊。入口腳本同時握有差異（呼叫鉤子之前就取得了）與鉤子的回傳，兩樣都在手上。

    缺口分四類，彼此獨立計數 —— 因為每一類的下一步完全不同：

        dropped  差異超過送出上限，整個檔案沒有送進去     → 要調上限或分批
        empty    差異內容是空的（二進位、僅模式變更、來源沒給）→ 無能為力，但要說出來
        missing  完整送進去了，但回報的發現裡沒有它        → 要調 prompt
        unknown  回報的路徑在差異中找不到對應的檔案        → 模型給了不存在的路徑

    合成單一個比例會把「要調什麼」重新藏起來，而那正是這份資料要解決的問題。

    empty 的那些**不算進 missing**：一個沒有內容的檔案，模型無從對它說任何話，把它算成
    「AI 沒回報」是記在錯的一方頭上。

    路徑比對沿用 hunk_of 那一套（見 _same_path）—— 回報的路徑可能帶 a/、b/ 前綴，也可能
    只有檔名。另寫一份的結果是兩份規則慢慢漂移，而症狀是涵蓋範圍憑空報出缺口。
    """
    sent = [plain(one) for one in files_sent]
    sent = [one for one in sent if one]
    empty = set(plain(one) for one in files_empty)
    # 形狀不對的 mrDiff 在這裡當成空的，不在這裡報錯 —— 型別由 validate_analysis()
    # 檢查，那裡的訊息指得出是哪一個 device 寫壞的。
    reported = [plain(one) for one in
                (mr_diff if isinstance(mr_diff, dict) else {})]
    reported = [one for one in reported if one]

    # 檔案總數沒給就等於「沒有被截掉的」。命令列直接餵一份差異時會是這種情況。
    total = len(sent) + len(list(files_dropped)) if file_count is None \
        else int(file_count)

    matched = set()
    unknown = []
    for key in reported:
        hit = [one for one in sent if _same_path(key, one)]
        if hit:
            matched.update(hit)
        else:
            unknown.append(key)

    missing = [one for one in sent
               if one not in matched and one not in empty]

    return {
        "files_changed": total,
        "files_sent": len(sent),
        "files_reported": len(reported),
        "truncated": bool(truncated),
        "bytes_total": int(bytes_total or 0),
        "bytes_sent": int(bytes_sent or 0),
        "dropped": _coverage_bucket(files_dropped),
        "empty": _coverage_bucket([one for one in sent if one in empty]),
        "missing": _coverage_bucket(missing),
        "unknown": _coverage_bucket(unknown),
    }


_COVERAGE_BUCKETS = ("dropped", "empty", "missing", "unknown")


def has_coverage_gap(coverage):
    """涵蓋範圍裡有沒有任何一類缺口。四類全空時報告不印那一段。

    每一份報告都加一段「涵蓋 21/21，沒有缺口」是噪音 —— 絕大多數的 Merge Request 不會
    有缺口。常駐的訊號留在出處資訊那一行就夠了。
    """
    if not isinstance(coverage, dict):
        return False
    for name in _COVERAGE_BUCKETS:
        bucket = coverage.get(name)
        if isinstance(bucket, dict) and _count_of(bucket) > 0:
            return True
    return False


def _count_of(bucket):
    """一類缺口的數量。count 不是整數時退回清單長度 —— 讀得出多少算多少。"""
    value = (bucket or {}).get("count")
    if isinstance(value, bool) or not isinstance(value, int):
        paths = (bucket or {}).get("paths")
        return len(paths) if isinstance(paths, list) else 0
    return max(value, 0)


def analysis_body(overview, model="", jira_key="", jira_state=JIRA_STATE_NONE,
                  jira_url="", mr_diff=None, mr_type="", coverage=None):
    """組出 analysis 的**內容**。

    刻意不含 schema_version —— 版本由入口腳本蓋章。讓鉤子自己填，遲早有人複製範本時
    忘了改，於是拿到一個聲稱是某版、實際是別的形狀的檔案。

    mrDiff 以檔案路徑為鍵，每個值是**那個檔案的 finding 清單**（沒有中間層）。想寫
    「對整個檔案的一句話」時，把它放在清單的第一筆、不給 diffCode 即可 —— 渲染出來與
    任何一筆 finding 相同，所以不需要為它另設一層。

    dict 在 Python 3.7+ 與 json 模組兩側都保留插入順序，所以檔案在報告中的先後就是
    這裡放進去的先後。

    jira_state 的三個值見 JIRA_STATES。invalid 時 jira_key 請保留**被拒絕的原值** ——
    報告要靠它告訴讀者「抽到的是 WIP」，只說「無效」等於要人自己猜。

    mr_type 由**入口腳本蓋章**，鉤子不必填（填了也會被覆蓋）—— 與 schema_version 同一個
    理由。它必須進到產物裡，因為步驟 5 要靠它決定用哪一份版面，而步驟 5 拿到的只有檔案。

    coverage 同樣由**入口腳本蓋章**（見 diff_coverage），而且理由更強：它是用來檢查這份
    mrDiff 回報了多少的。鉤子填了會被覆蓋。
    """
    return {
        "model": plain(model),
        "mr_type": plain(mr_type),
        "jira_key": plain(jira_key),
        "jira_state": plain(jira_state) or JIRA_STATE_NONE,
        "jira_url": plain(jira_url),
        "overview": plain(overview),
        "mrDiff": dict(mr_diff or {}),
        "coverage": dict(coverage or {}),
    }


def wrap_analysis(body):
    """把 analysis 的內容包成落檔與回傳用的完整結構，並蓋上版本號。

    入口腳本用這一支 —— 鉤子只交內容，版本永遠由這裡填。
    """
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis": body,
    }


def validate_analysis(payload, source=""):
    """驗證分析結構，通過就回傳 analysis 的內容；不通過丟 AnalysisFormatError。

    兩個呼叫點共用這一份：AI 分析那一步**收到鉤子回傳的當下**，以及合併那一步渲染之前。
    共用的理由很具體 —— 曾經有一次 summary 欄位變成巢狀物件，根因在 AI 分析那一步，
    症狀卻爆在兩步之後的渲染，訊息是一句 "dict object has no attribute strip"，既沒說
    是哪個檔案也沒說是哪個欄位。驗在產生它的那一步，訊息才點得出是誰寫壞的。

    source 是給訊息用的前綴（例如 "device ssd 的 summary.py"）。AI 分析那一步知道是哪個
    device，合併那一步不知道，所以它是選用的。
    """
    where = ("%s：" % source) if source else ""

    if not isinstance(payload, dict):
        raise AnalysisFormatError(
            "%sAI 分析結果不是一個物件" % where,
            "讀到的型別是 %s。" % type(payload).__name__,
            "ANALYSIS_BAD_TYPE")

    raw_version = payload.get("schema_version")
    if _schema_version(raw_version) not in ACCEPTED_SCHEMA_VERSIONS:
        raise AnalysisFormatError(
            "%s認不得的 AI 分析結果版本：%r" % (where, raw_version),
            "這份實作讀得懂的是 schema_version %s —— 數字與純數字字串都收"
            "（%d、\"%d\"、\"%d.0\" 視為同一個版本）。\n"
            "版本不合時不做猜測 —— 猜錯的結果是一份看起來正常、實際上少了幾段的"
            "報告，而它會回報成功。"
            % ("、".join(str(v) for v in ACCEPTED_SCHEMA_VERSIONS),
               ANALYSIS_SCHEMA_VERSION, ANALYSIS_SCHEMA_VERSION,
               ANALYSIS_SCHEMA_VERSION),
            "ANALYSIS_SCHEMA_UNSUPPORTED")

    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        raise AnalysisFormatError(
            "%sAI 分析結果缺少 analysis 物件" % where,
            "analysis 的型別是 %s。這個檔案目前有的欄位：%s"
            % (type(analysis).__name__,
               "、".join(sorted(payload.keys())) or "(無)"),
            "ANALYSIS_MISSING_BODY")

    state = analysis.get("jira_state")
    if state not in JIRA_STATES:
        raise AnalysisFormatError(
            "%sAI 分析結果的 jira_state 不是認得的值：%r" % (where, state),
            "認得的是 %s。\n"
            "沒有要使用 JIRA 時填 \"%s\"；抽到東西但沒通過檢查時填 \"%s\"，"
            "並把原值留在 jira_key。"
            % ("、".join(JIRA_STATES), JIRA_STATE_NONE, JIRA_STATE_INVALID),
            "ANALYSIS_JIRA_STATE_BAD")

    # 種類可以是空字串（這筆 MR 沒有種類，或該 device 不用種類），但型別必須是字串。
    # 不是字串時明確失敗，不靜默轉換 —— 一個 dict 被 str() 起來會變成 "{'a': 1}"，
    # 然後被拿去當目錄名比對，永遠對不上而且看不出原因。
    mr_type = analysis.get("mr_type", "")
    if not isinstance(mr_type, str):
        raise AnalysisFormatError(
            "%sAI 分析結果的 mr_type 不是字串：%r" % (where, mr_type),
            "讀到的型別是 %s。沒有種類時請填空字串。" % type(mr_type).__name__,
            "ANALYSIS_MR_TYPE_BAD")

    # 涵蓋範圍是選填的：版本 3、4 的產物沒有這個欄位，讀法是「視為沒有涵蓋範圍資訊」。
    # 但給了就必須是物件 —— 一個被填成數字或字串的 coverage 會讓渲染那一步拿它去取鍵，
    # 而那裡只會得到一段指不出原因的 AttributeError。
    coverage = analysis.get("coverage")
    if coverage is not None and not isinstance(coverage, dict):
        raise AnalysisFormatError(
            "%sAI 分析結果的 coverage 不是物件" % where,
            "coverage 的型別是 %s。這個欄位由入口腳本蓋章（見 diff_coverage），"
            "鉤子不必填。" % type(coverage).__name__,
            "ANALYSIS_COVERAGE_BAD_TYPE")

    # 型別檢查要在「沒給就當空的」之前 —— 反過來寫的話，一個打錯成 [] 的
    # mrDiff 會因為空 list 是 falsy 而變成 {}，報告少了整批檔案卻回報成功。
    mr_diff = analysis.get("mrDiff")
    if mr_diff is None:
        mr_diff = {}
    if not isinstance(mr_diff, dict):
        raise AnalysisFormatError(
            "%sAI 分析結果的 mrDiff 不是物件" % where,
            "mrDiff 的型別是 %s。它應該是以檔案路徑為鍵的物件。"
            % type(mr_diff).__name__,
            "ANALYSIS_MRDIFF_BAD_TYPE")

    # 逐檔、逐筆走完。留到渲染才發現的話，訊息指的是合併那一步，而錯在上游。
    for path, findings in mr_diff.items():
        clean = plain(path)
        if not isinstance(findings, list):
            raise AnalysisFormatError(
                "%sAI 分析結果中 %s 的內容不是清單" % (where, clean),
                "讀到的型別是 %s。mrDiff 的每個值應該是一個 list，裡面每一筆是 "
                "{title, reason, diffCode}。" % type(findings).__name__,
                "ANALYSIS_FILE_BAD_TYPE")
        for position, item in enumerate(findings, start=1):
            if not isinstance(item, dict):
                raise AnalysisFormatError(
                    "%sAI 分析結果中 %s 的第 %d 筆不是物件"
                    % (where, clean, position),
                    "讀到的型別是 %s。每一筆應該是 {title, reason, diffCode} "
                    "這樣的物件。" % type(item).__name__,
                    "ANALYSIS_FINDING_BAD_TYPE")

    return analysis


def jira_url(jira_key):
    """把 JIRA key 組成可點的網址。沒有 key 或沒設伺服器位址時回空字串。

    **這是 device 作者的公開 API。**

    伺服器位址走環境變數（工具端由 Qt 從設定檔的 Service.Jira_Server_URL 以全大寫
    注入），與 GitLab 的憑證同一條路徑 —— 腳本端只有一種取值方式。

    組不出網址時回空字串，而**不是**把這件事當成 key 無效：沒設 JIRA_SERVER_URL 是
    設定問題，與 key 對不對無關。混在一起的話，一個完全正確的 key 會因為別人沒設
    伺服器位址而被標成 invalid。
    """
    key = plain(jira_key)
    if not key:
        return ""
    server = os.environ.get("JIRA_SERVER_URL", "").strip().rstrip("/")
    if not server:
        logger.debug("未設定 JIRA_SERVER_URL，jira_url 留空")
        return ""
    return "%s/browse/%s" % (server, key)


# --- 渲染（讀取側）----------------------------------------------------------

def _schema_version(value):
    """把版本值收斂成整數；認不出來回 None。

    認得時寬鬆、寫出時正規 —— 與標題比對同一個原則。收整數、浮點數與純數字字串，
    因為 2、"2"、"2.0" 寫的是同一個版本，而產生這個檔案的可能是 AI、可能是人手寫的
    設定，三種寫法都會出現。擋在這裡的話，使用者看到的是「認不得的版本 '2'」，而
    那個錯誤與真正的版本不合長得一模一樣，只差一對引號。

    比對前一律轉成整數：版本要比大小，而字串比較會在 "10" 與 "9" 之間給出錯的答案。
    非整數的版本（"2.5"）不接受 —— 那代表一個我們沒有定義過的東西，猜它等於 2 只是
    把問題往下游丟。

    bool 特別排除：Python 的 True 是 int 的子類別而且等於 1，不擋的話
    schema_version 寫成 true 會被當成版本 1。
    """
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value) if value == int(value) else None

    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number == int(number) else None

    return None


def fence_for(code):
    """挑一個不會被內容提前關掉的圍籬。

    **這是 device 作者的公開 API。** 自己寫渲染時務必用它算圍籬長度。

    diff 的內容若自己含有三個反引號（改到 markdown 檔就會），固定用 ``` 會讓程式碼
    區塊在半路結束，後面的內容變成一般文字 —— 而報告仍然「成功」產出。數出內容裡
    最長的一串反引號，用比它多一個。
    """
    longest = 0
    run = 0
    for char in code:
        if char == "`":
            run += 1
            if run > longest:
                longest = run
        else:
            run = 0
    return "`" * max(3, longest + 1)


# --- 步驟 4 的程式碼審閱：擷取、結構與渲染 ------------------------------------
#
# 來源是**別人的文件** —— 工程師用 AI code review 工具產出、以附件掛在 JIRA 議題上的
# 一份 markdown。我們只要其中的風險評估總表，全文靠報告裡那個連結回去看。
#
# 與步驟 3 同一套分工：步驟 4 交出**結構**，由步驟 5 渲染。那份結構必須帶著附件的
# 日期、作者與網址，因為只有步驟 4 拿得到它們 —— 步驟 5 收到的只是一個檔案路徑。

# 這份結構的版本。與 ANALYSIS_SCHEMA_VERSION 各自獨立編號：兩者是不同的產物，讓它們
# 共用一個號碼會使其中一邊的改版莫名其妙地讓另一邊的舊檔失效。
CODE_REVIEW_SCHEMA_VERSION = 1
ACCEPTED_CODE_REVIEW_VERSIONS = (1,)

# 總表內容的位元組上限。
#
# 這一份會整段進報告 → 進回應的 data → 經 stdout 回到 Qt → 進結果視窗，所以要有界。
# 但它不進 prompt、不花 token，因此可以比 MAX_PROMPT_DIFF_BYTES 寬鬆。
#
# 一份人看得完的總表大約幾 KB，取十倍以上是刻意的：上限要大到**正常使用永遠不會觸發**，
# 因為一個經常出現的截斷記號會被讀者習慣性忽略，那時它就不再是警告了。
#
# 同一個數字用在兩個地方 —— 下載前依議題系統回報的大小先擋，以及讀進來之後再截斷。
# 兩道用不同的數字只會讓人問為什麼不一樣。
MAX_CODE_REVIEW_BYTES = 200000

_CODE_REVIEW_TRUNCATED = "\n\n… （內容已截斷）"

# 任何以 # 開頭、後面不是 # 的行都算一個 ATX 標題，因此都是擷取範圍的終點。
#
# 比 "#{1,6}\s" 寬：_heading_pattern() 容許 "##風險評估總表" 這種沒有空格的寫法，
# 所以範圍的終點也必須認得同樣的寫法，否則下一節的標題會被當成內容而讓範圍過長。
_ATX_RE = re.compile(r"^#{1,6}(?!#)")

# 表格的分隔列：每一格只有連字號，前後可有對齊用的冒號。
_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


class RiskTableError(Exception):
    """總表擷取不到。

    與 AnalysisFormatError 同一個形狀（message / detail / code），但**用途不同**：
    這一個不會變成 reply_fail，而是被寫進結構的 error 欄位、顯示在報告裡。

    理由：擷取不到屬於「別人的文件不合約定」，而這一步跑在 AI 分析之後 —— 讓它結束
    流程會把一份已經完成、已經付費的分析整份丟掉。
    """

    def __init__(self, message, detail="", code="CODE_REVIEW_TABLE_NOT_FOUND"):
        super(RiskTableError, self).__init__(message)
        self.detail = detail
        self.code = code


class CodeReviewFormatError(Exception):
    """程式碼審閱結構不符。這一個**會**變成 reply_fail。

    與 RiskTableError 的分界即失敗三分類的分界：結構壞掉是我們自己寫壞的（或讀到一份
    不認得版本的產物），不是別人的文件的問題。
    """

    def __init__(self, message, detail, code):
        super(CodeReviewFormatError, self).__init__(message)
        self.detail = detail
        self.code = code


def _is_separator_row(line):
    """這一行是不是表格的分隔列（|---|---|）。"""
    cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(c) for c in cells)


def _clip_code_review(text):
    """把過長的總表截斷，並在尾端明著說它被截斷了。

    與 _clip_diff() 同一個作法：不說的話，讀報告的人會以為表格就到那裡為止。
    """
    body = plain(text)
    encoded = body.encode("utf-8")
    if len(encoded) <= MAX_CODE_REVIEW_BYTES:
        return body
    return (encoded[:MAX_CODE_REVIEW_BYTES].decode("utf-8", "ignore")
            + _CODE_REVIEW_TRUNCATED)


def extract_risk_table(text, heading):
    """自 code review 報告中擷取風險評估總表，回傳表格的 markdown。

    只回傳**表格本身**，不含任何標題 —— 標題由步驟 5 寫出（與其他段落一致，產生內容
    的步驟無從知道自己會被放在哪一層）。

    heading 是要找的那一節的標題，由呼叫端傳入（預設值是 CODE_REVIEW_SOURCE_HEADING，
    但 device 可以宣告自己的）。比對式由它導出，不另外手寫字面文字。

    擷取不到時丟 RiskTableError —— 呼叫端把它寫進結構的 error 欄位，不結束流程。

    演算法有三個地方是刻意的：

    1. **範圍限定在下一個標題之前。** 這是整支函式最重要的一條。若只是「從標題往下找
       第一個表格」，那一節恰好沒有總表時會抓到**下一節的表格** —— 於是一張看起來完全
       合理的錯誤表格被貼進報告，標題還寫著風險評估表。抓不到必須是抓不到。

    2. **圍籬區塊內的標題與表格都不算。** AI 產出的報告裡出現程式碼區塊的機率很高，
       區塊內若有假標題或假表格，不追蹤圍籬就會抓錯。

    3. **形狀檢查（表頭 + 分隔列）而不檢查欄位名稱。** 各 device 的報告連欄位名稱都
       不保證相同，所以沒有可用的預設值；但「是不是一張 markdown 表格」不因 device
       而異。這道檢查擋掉「那一節只有散文」與「來源少了分隔列」—— 後者原樣貼進報告
       不會被渲染成表格。
    """
    wanted = plain(heading)
    if not wanted:
        raise RiskTableError(
            "沒有指定總表那一節的標題",
            "這是呼叫端的問題，不是來源文件的問題。",
            "CODE_REVIEW_HEADING_NOT_GIVEN")

    pattern = _heading_pattern(wanted)
    lines = (text or "").splitlines()

    # --- 第一趟：找標題，並定出範圍的終點 ---
    fence = None
    start = None
    end = len(lines)

    for index, line in enumerate(lines):
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            continue
        if fence is not None:
            continue

        if start is None:
            if pattern.match(stripped):
                start = index
            continue

        # 標題之後的第一個 ATX 標題就是範圍的終點。
        if _ATX_RE.match(stripped):
            end = index
            break

    if start is None:
        raise RiskTableError(
            "來源文件中找不到「%s」這一節" % wanted,
            "認得的標題是「%s」（階層與行首行尾空白可以不同）。\n"
            "若該 device 的 code review 報告用的是別的節名，請在 device 的 "
            "__init__.py 宣告 CODE_REVIEW_SOURCE_HEADING。" % wanted,
            "CODE_REVIEW_SECTION_NOT_FOUND")

    # --- 第二趟：範圍內找表格 ---
    fence = None
    rows = []

    for line in lines[start + 1:end]:
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            # 表格已經開始又遇到圍籬，那張表格到此為止。
            if rows:
                break
            continue
        if fence is not None:
            continue

        if stripped.startswith("|"):
            rows.append(stripped)
            continue

        # 表格開始之後的第一個非表格行就是終點；還沒開始的話繼續找
        # （標題與表格之間可能有空行或一兩句說明）。
        if rows:
            break

    if not rows:
        raise RiskTableError(
            "「%s」這一節底下沒有表格" % wanted,
            "找過該節到下一個標題之間的每一行，沒有以 | 開頭的表格。\n"
            "注意沒有前後 | 的表格寫法不被支援 —— 那種偵測會把說明文字裡的任何一個 "
            "| 當成表格的開始。",
            "CODE_REVIEW_TABLE_NOT_FOUND")

    if len(rows) < 2 or not _is_separator_row(rows[1]):
        raise RiskTableError(
            "「%s」這一節底下的內容不是一張完整的表格" % wanted,
            "一張 markdown 表格至少要有表頭與分隔列（|---|---|）兩行；讀到的是 %d 行，"
            "而第二行不是分隔列。\n"
            "缺分隔列的內容原樣貼進報告不會被渲染成表格。" % len(rows),
            "CODE_REVIEW_TABLE_MALFORMED")

    return "\n".join(rows)


def code_review_body(risk_table="", filename="", created="", author="",
                     url="", error=""):
    """組出程式碼審閱結構的**內容**。

    刻意不含 schema_version —— 版本由入口腳本蓋章，與 analysis_body() 同一個理由。

    error 與 risk_table 可以同時有值也可以只有一邊：取得失敗時 error 有值而表格為空，
    而**附件資訊仍然要填** —— 那時連結的價值最高，讀者點進去就能自己看全文。
    """
    return {
        "filename": plain(filename),
        "created": plain(created),
        "author": plain(author),
        "url": plain(url),
        "risk_table": _clip_code_review(risk_table),
        "error": plain(error),
    }


def wrap_code_review(body):
    """把內容包成落檔與回傳用的完整結構，並蓋上版本號。"""
    return {
        "schema_version": CODE_REVIEW_SCHEMA_VERSION,
        "code_review": body,
    }


def validate_code_review(payload, source=""):
    """驗證程式碼審閱結構，通過就回傳內容；不通過丟 CodeReviewFormatError。

    與 validate_analysis() 同一個形狀與同一個理由：驗在讀得到它的每一個邊界，訊息才
    指得出是哪個欄位。版本的比對共用 _schema_version()，所以「數字或純數字字串都收、
    非整數不收」的規則只有一份。
    """
    where = ("%s：" % source) if source else ""

    if not isinstance(payload, dict):
        raise CodeReviewFormatError(
            "%s程式碼審閱結果不是一個物件" % where,
            "讀到的型別是 %s。" % type(payload).__name__,
            "CODE_REVIEW_BAD_TYPE")

    raw_version = payload.get("schema_version")
    if _schema_version(raw_version) not in ACCEPTED_CODE_REVIEW_VERSIONS:
        raise CodeReviewFormatError(
            "%s認不得的程式碼審閱結果版本：%r" % (where, raw_version),
            "這份實作讀得懂的是 schema_version %s —— 數字與純數字字串都收。\n"
            "版本不合時不做猜測：猜錯的結果是一份看起來正常、實際上少了一段的報告。"
            % "、".join(str(v) for v in ACCEPTED_CODE_REVIEW_VERSIONS),
            "CODE_REVIEW_SCHEMA_UNSUPPORTED")

    body = payload.get("code_review")
    if not isinstance(body, dict):
        raise CodeReviewFormatError(
            "%s程式碼審閱結果缺少 code_review 物件" % where,
            "code_review 的型別是 %s。這個檔案目前有的欄位：%s"
            % (type(body).__name__,
               "、".join(sorted(payload.keys())) or "(無)"),
            "CODE_REVIEW_MISSING_BODY")

    # 六個欄位都必須是字串。空字串是合法的（沒有那一項），但型別不對就明確失敗 ——
    # 一個 dict 被 str() 起來會變成 "{'a': 1}" 然後原樣印進報告。
    for key in ("filename", "created", "author", "url", "risk_table", "error"):
        value = body.get(key, "")
        if not isinstance(value, str):
            raise CodeReviewFormatError(
                "%s程式碼審閱結果的 %s 不是字串：%r" % (where, key, value),
                "讀到的型別是 %s。沒有這一項時請填空字串。"
                % type(value).__name__,
                "CODE_REVIEW_FIELD_BAD_TYPE")

    return body


def _escape_link_text(text):
    """把檔名轉義成安全的 markdown 連結文字。

    檔名是**上傳者打的字**，其中的方括號或圓括號會讓那一行的連結失效。
    """
    out = plain(text)
    for char in ("\\", "[", "]", "(", ")"):
        out = out.replace(char, "\\" + char)
    return out


# --- 報告末尾的出處資訊 ------------------------------------------------------
#
# 一份報告被貼到 MR 討論串之後就脫離了產生它的環境。半年後有人問「這段分析是哪來的、
# 為什麼跟現在跑出來的不一樣」，footer 是唯一答得出來的東西。

# 這個功能的名稱與版號。五支入口腳本與這份契約共用這一份。
#
# 版號兩碼：第一碼留給重大修改，第二碼是修改計數。**這個功能每改一次就把第二碼加一**
# ——包含只改註解或診斷文字；第一碼更新時第二碼歸零。沒有判斷餘地是刻意的：需要判斷
# 「這算大改還是小改」的規則，就是會被漏掉的規則。
#
# **不要與 TEMPLATE_VERSION 搞混。** 那一個是信封模板的版本，全專案共用一個值，只有
# 信封格式本身改了才動。改這個功能不要動它。
#
# device 那一層另外宣告自己的 VERSION，**第一碼要與這裡一致** —— 讀報告的人看第一碼
# 就知道那份 device 是照哪一代的契約寫的。不一致不會讓執行失敗（見 device 模組）。
SCRIPT_NAME = "AI Analysis GitLab MR"
SCRIPT_VERSION = "2.4"


def _link(text, url):
    """有網址就做成連結，沒有就只留文字。

    CI_PROJECT_URL 沒設時仍然把編號印出來 —— 知道是哪一個 pipeline，比因為做不成
    連結就整段消失有用。
    """
    return "[%s](%s)" % (text, url) if url else text


def _ci_origin():
    """CI 環境的出處：pipeline 編號與 commit，各自連回 GitLab。

    三個變數都是 GitLab Runner 自動注入的，不需要在設定檔裡宣告。不在 CI 裡跑時
    它們不存在，回空字串，由呼叫端改用工具端的出處。
    """
    project = os.environ.get("CI_PROJECT_URL", "").strip().rstrip("/")
    pipeline = os.environ.get("CI_PIPELINE_ID", "").strip()
    sha = os.environ.get("CI_COMMIT_SHORT_SHA", "").strip()

    parts = []
    if pipeline:
        parts.append("Gitlab Pipeline %s" % _link(
            "#" + pipeline,
            "%s/-/pipelines/%s" % (project, pipeline) if project else ""))
    if sha:
        parts.append("Commit %s" % _link(
            sha, "%s/-/commit/%s" % (project, sha) if project else ""))

    return " | ".join(parts)


def _tool_origin():
    """工具端的出處：工具名稱與版本。

    TOOLNAME / TOOLVERSION 由 PythonRunner 對每一次執行注入，所以從工具跑的報告
    一定有這兩個值；命令列直接執行時沒有，那時 footer 就只剩腳本版本那一行。
    """
    name = os.environ.get("TOOLNAME", "").strip()
    version = os.environ.get("TOOLVERSION", "").strip()
    if not name:
        return ""
    return ("%s %s" % (name, version)).strip()


def render_footer(ai_mode="", device_name="", device_version="", analysis=None):
    """報告最後那一段出處資訊。

    形狀（整段是一個 <sub>，行與行之間用 <br> 斷開）：

        ---

        <sub>**Device** `ssd` `2.1` | **Type** `bug`<br>**腳本** AI Analysis GitLab MR `2.0`<br>**AI** Open AI | `gpt-4o`<br>**產生方式** PPS 2.0 DevTool v2.0.0</sub>

    四行各回答一個問題：用哪一套邏輯、哪一版骨架、哪個模型、誰在哪裡產生的。

    **斷行用 <br> 而不是真的換行**：段落內的換行在 markdown 是軟換行，轉譯後會變成一個
    空白，四行會擠成一行。<br> 是明確的斷行，在任何轉譯器下都成立（量過）。

    **<sub> 包住整段，不是每一行各包一個**：這一段轉譯出來是單一個 `<p>`，<sub> 是
    inline 標籤，包得住 `<p>` 裡的內容，<br> 也是 inline，巢狀合法（量過）。先前用清單
    時每一個項目都得自己包一次，是因為 <sub> 包不住清單那種 block 元素。

    **只用 ASCII 的分隔**：欄位之間一個半形空白，同一行內的兩組值之間 ` | `。全形空白
    與全形斜線在等寬字型下寬度不定，貼到 GitLab 也不見得照原樣保留。

    兩個版號都在：`Device` 那一組是該 device 的，`腳本` 那一組是通用層的。第一碼一致代表
    同一代；不一致時讀的人自己對照得出來，程式不擋也不標記。

    最後一行依環境而定：CI 裡是 pipeline 與 commit，從工具跑是工具名稱與版本，兩者都沒有
    （命令列直接執行）就整行不出現。

    分隔線之前必須空一行，否則 markdown 會把上一行文字當成 setext 標題。
    """
    lines = []

    # 一、用哪一套邏輯。種類沒有時整段不印 —— 不用種類的 device 每份報告都多一個
    # 「Type: 無」只是噪音。
    name = plain(device_name)
    if name:
        bits = ["**Device** `%s`" % name]
        version = plain(device_version)
        if version:
            bits.append("`%s`" % version)
        mr_type = plain((analysis or {}).get("mr_type"))
        if mr_type:
            bits.append("| **Type** `%s`" % mr_type)
        lines.append(" ".join(bits))

    # 二、哪一版骨架。**這一行永遠都在** —— 它是這整段存在的理由。
    lines.append("**腳本** %s `%s`" % (SCRIPT_NAME, SCRIPT_VERSION))

    # 三、哪個模型。模式是「使用者選了哪一組設定」，模型是「實際跑的是誰」；在 CI 上
    # 只有後者有意義，所以兩個都印。
    mode = plain(ai_mode)
    model = plain((analysis or {}).get("model"))
    if mode or model:
        lines.append("**AI** %s" % ("%s | `%s`" % (mode, model) if mode and model
                                    else (mode or "`%s`" % model)))

    # 四、誰在哪裡產生的。
    origin = _ci_origin() or _tool_origin()
    if origin:
        lines.append("**產生方式** %s" % origin)

    return "---\n\n<sub>%s</sub>" % "<br>".join(lines)