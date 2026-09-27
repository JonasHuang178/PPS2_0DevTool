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
    "LEGACY_DESCRIPTION_HEADINGS",
    "split_description",
    "render_original_description",
    "render_ai_section",
    "ANALYSIS_SCHEMA_VERSION",
    "AnalysisFormatError",
    "render_analysis",
    "MAX_FINDING_DIFF_BYTES",
    "finding",
    "file_entry",
    "analysis_payload",
    "CredentialError",
    "gitlab_credentials",
    "describe_gitlab_error",
    "DEBUG_LOG_NAME",
    "write_artifact",
    "write_debug_log",
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

# 唯一會被寫出去的標題。步驟 5 用它寫出那一段，步驟 1 用它切掉上一輪的分析 ——
# 同一個邊界的兩側，所以只有這一份。改它只要改這一行，底下的比對式是導出的。
AI_HEADING = "# AI 分析"

# 只用來**認得**，不會被寫出去。
#
# 早期版本的步驟 1 會在原始描述前面加一行 "# Original description"（更早還有一個
# Oirignal 的筆誤）。現在不加了，但既有的 MR 描述裡還留著那一行 —— 認得它才能在
# 下一輪把它清掉；不認得的話它會被當成描述的內容一直留在報告裡。
#
# 確定沒有任何 MR 還帶著這兩行之前，不能拿掉。
LEGACY_DESCRIPTION_HEADINGS = (
    "# Original description",
    "# Oirignal description",
)


def _heading_pattern(*headings):
    """由標題常數**導出**寬鬆的比對式，不另外手寫一份字面文字。

    這件事非做不可：認得的規則若自己抄一份標題文字，改了常數而忘了改它時，寫出去
    的標題與切得掉的標題就是兩個不同的東西 —— 步驟 5 寫 A、步驟 1 找 B，於是切不到
    邊界，舊的 AI 分析被當成原始描述留下來，報告每跑一次多疊一段。而每一步都回報
    成功，沒有任何地方會喊。導出之後，常數就是唯一要改的地方。

    導出的比對式比常數本身寬鬆：階層 # 到 ###### 都收、大小寫不分、詞與詞之間的
    空白多寡不拘、行首行尾的空白容許。描述是人在 GitLab 網頁上編輯的東西，這些都
    會被動到，而動到不該讓邊界消失。
    """
    alternatives = []
    for heading in headings:
        words = heading.lstrip("#").split()
        alternatives.append(r"\s*".join(re.escape(w) for w in words))
    return re.compile(r"^#{1,6}\s*(?:%s)\s*$" % "|".join(alternatives), re.I)


_DESCRIPTION_RE = _heading_pattern(*LEGACY_DESCRIPTION_HEADINGS)
_AI_RE = _heading_pattern(AI_HEADING)


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


def render_ai_section(summary):
    """步驟 5 接在原始描述後面的那一段。"""
    return "%s\n\n%s\n" % (AI_HEADING, summary.strip())


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
# 放這個模組而不是直接寫在步驟 5 裡面，是為了與寫入側（日後的 analysis_payload()
# 等建構函式）待在同一個畫面：欄位名散在兩邊時，改名漏一邊的症狀是 KeyError，
# 或更糟，安靜地少一段。

# 認得的結構版本。收到別的版本明確失敗，不猜 —— 猜錯的結果是一份看起來正常、
# 實際上少了幾段的報告，而它會回報成功。
ANALYSIS_SCHEMA_VERSION = 2


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


def _plain(value):
    """收斂成去掉頭尾空白的字串。None 與非字串都吃得下 —— AI 回來的 JSON 常有
    null，直接丟進報告會印出 "None"。"""
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

_DIFF_TRUNCATED = "\n… （diff 已截斷）"


def _clip_diff(diff):
    """把過長的 diff 截斷，並在尾端明著說它被截斷了。

    不說的話，讀報告的人會以為那個 hunk 就到那裡為止 —— 而被截掉的往往正是後半段。
    以位元組計算（中文一個字三個位元組），errors="ignore" 丟掉切邊切破的半個字。
    """
    text = _plain(diff)
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_FINDING_DIFF_BYTES:
        return text
    return (encoded[:MAX_FINDING_DIFF_BYTES].decode("utf-8", "ignore")
            + _DIFF_TRUNCATED)


def finding(title, reason, diff=""):
    """diffCode 裡的一筆：標題、理由，以及相關的那段 diff。"""
    return {
        "title": _plain(title),
        "reason": _plain(reason),
        "diff": _clip_diff(diff),
    }


def file_entry(title="", reason="", findings=None):
    """mrDiff 底下的一個檔案：檔案層級的標題與理由，加上每一筆 finding。

    title / reason 留空時渲染端整段略過，不會留下一個空標題。
    """
    return {
        "title": _plain(title),
        "reason": _plain(reason),
        "diffCode": list(findings or []),
    }


def analysis_payload(overview, model="", jira_url="", mr_diff=None):
    """組出步驟 3 要落檔與回傳的完整結構。

    mrDiff 以檔案路徑為鍵。dict 在 Python 3.7+ 與 json 模組兩側都保留插入順序，
    所以檔案在報告中的先後就是這裡放進去的先後。
    """
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "analysis": {
            "model": _plain(model),
            "jira_url": _plain(jira_url),
            "overview": _plain(overview),
            "mrDiff": dict(mr_diff or {}),
        },
    }


# --- 渲染（讀取側）----------------------------------------------------------

def _fence_for(code):
    """挑一個不會被內容提前關掉的圍籬。

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


def _render_finding(item, path):
    """diffCode 裡的一筆。"""
    if not isinstance(item, dict):
        raise AnalysisFormatError(
            "AI 分析結果中 %s 的 diffCode 有一筆不是物件" % path,
            "讀到的型別是 %s。diffCode 的每一筆應該是 "
            "{title, reason, diff} 這樣的物件。" % type(item).__name__,
            "ANALYSIS_FINDING_BAD_TYPE")

    out = []
    title = _plain(item.get("title"))
    if title:
        out.append("### %s" % title)

    reason = _plain(item.get("reason"))
    if reason:
        out.append(reason)

    diff = _plain(item.get("diff"))
    if diff:
        fence = _fence_for(diff)
        out.append("%sdiff\n%s\n%s" % (fence, diff, fence))

    return out


def _render_file(path, entry):
    """mrDiff 底下的一個檔案。"""
    if not isinstance(entry, dict):
        raise AnalysisFormatError(
            "AI 分析結果中 %s 的內容不是物件" % path,
            "讀到的型別是 %s。mrDiff 的每個值應該是 "
            "{title, reason, diffCode} 這樣的物件。" % type(entry).__name__,
            "ANALYSIS_FILE_BAD_TYPE")

    # 檔案路徑用 H2：整段最後會被放在 AI_HEADING（H1）底下，所以檔案是第二層、
    # 每一筆發現是第三層。檔案層級的標題改用粗體而不是 H3，才不會與發現撞階層。
    out = ["## %s" % path]

    title = _plain(entry.get("title"))
    if title:
        out.append("**%s**" % title)

    reason = _plain(entry.get("reason"))
    if reason:
        out.append(reason)

    for item in entry.get("diffCode") or []:
        out.extend(_render_finding(item, path))

    return out


def render_analysis(payload):
    """把步驟 3 的結構化分析渲染成 markdown（不含 AI 分析那一行標題）。

    回傳的是「接在 AI_HEADING 底下的那一段」—— 標題由 render_ai_section() 加上，
    因為那個字串同時是下一輪切段的邊界，只能有一個來源。

    空的欄位整段不放：一個只有標題、底下什麼都沒有的區塊會讓人以為內容漏掉了。
    """
    if not isinstance(payload, dict):
        raise AnalysisFormatError(
            "AI 分析結果不是一個物件",
            "讀到的型別是 %s。" % type(payload).__name__,
            "ANALYSIS_BAD_TYPE")

    version = payload.get("schema_version")
    if version != ANALYSIS_SCHEMA_VERSION:
        raise AnalysisFormatError(
            "認不得的 AI 分析結果版本：%r" % (version,),
            "這份實作認得的是 schema_version %d。\n"
            "版本不合時不做猜測 —— 猜錯的結果是一份看起來正常、實際上少了幾段的"
            "報告，而它會回報成功。" % ANALYSIS_SCHEMA_VERSION,
            "ANALYSIS_SCHEMA_UNSUPPORTED")

    analysis = payload.get("analysis")
    if not isinstance(analysis, dict):
        raise AnalysisFormatError(
            "AI 分析結果缺少 analysis 物件",
            "analysis 的型別是 %s。這個檔案目前有的欄位：%s"
            % (type(analysis).__name__,
               "、".join(sorted(payload.keys())) or "(無)"),
            "ANALYSIS_MISSING_BODY")

    blocks = []

    overview = _plain(analysis.get("overview"))
    if overview:
        blocks.append(overview)

    meta = []
    model = _plain(analysis.get("model"))
    if model:
        meta.append("- 模型：%s" % model)
    jira_url = _plain(analysis.get("jira_url"))
    if jira_url:
        meta.append("- JIRA：%s" % jira_url)
    if meta:
        blocks.append("\n".join(meta))

    # 型別檢查要在「沒給就當空的」之前 —— 反過來寫的話，一個打錯成 [] 的
    # mrDiff 會因為空 list 是 falsy 而變成 {}，報告少了整批檔案卻回報成功。
    mr_diff = analysis.get("mrDiff")
    if mr_diff is None:
        mr_diff = {}
    if not isinstance(mr_diff, dict):
        raise AnalysisFormatError(
            "AI 分析結果的 mrDiff 不是物件",
            "mrDiff 的型別是 %s。它應該是以檔案路徑為鍵的物件。"
            % type(mr_diff).__name__,
            "ANALYSIS_MRDIFF_BAD_TYPE")

    for path, entry in mr_diff.items():
        blocks.extend(_render_file(_plain(path), entry))

    return "\n\n".join(blocks)
