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
    "CODE_REVIEW_HEADING",
    "ANALYSIS_SCHEMA_VERSION",
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
    "MAX_FINDING_DIFF_BYTES",
    "finding",
    "analysis_body",
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

# 程式碼審閱那一段的標題。與 AI 分析**同層** —— 它在語意上是並列的一段，不是分析
# 的子節。由這一步寫出所有段落的標題，「報告有哪幾節、各在第幾層」就只有一個地方
# 決定；讓產生內容的步驟自帶標題的話，它無從知道自己會被放在哪一層。
#
# 它不是切段的邊界（那只有 AI_HEADING），因為它永遠在 AI 分析之後，切段時連同
# AI 分析一起被丟掉。
CODE_REVIEW_HEADING = "# 程式碼審閱"


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


def render_code_review_section(text):
    """報告裡「程式碼審閱」那一段：標題加上內容。內容為空就回傳空字串。"""
    body = plain(text)
    if not body:
        return ""
    return "%s\n\n%s\n" % (CODE_REVIEW_HEADING, body)


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
# 放這個模組而不是直接寫在步驟 5 裡面，是為了與寫入側（analysis_body()
# 等建構函式）待在同一個畫面：欄位名散在兩邊時，改名漏一邊的症狀是 KeyError，
# 或更糟，安靜地少一段。

# 認得的結構版本。收到別的版本明確失敗，不猜 —— 猜錯的結果是一份看起來正常、
# 實際上少了幾段的報告，而它會回報成功。
#
# 版本 3 相對於 2 多了三個 JIRA 欄位（jira_key / jira_state / jira_url）。
ANALYSIS_SCHEMA_VERSION = 3


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


def analysis_body(overview, model="", jira_key="", jira_state=JIRA_STATE_NONE,
                  jira_url="", mr_diff=None):
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
    """
    return {
        "model": plain(model),
        "jira_key": plain(jira_key),
        "jira_state": plain(jira_state) or JIRA_STATE_NONE,
        "jira_url": plain(jira_url),
        "overview": plain(overview),
        "mrDiff": dict(mr_diff or {}),
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
    if _schema_version(raw_version) != ANALYSIS_SCHEMA_VERSION:
        raise AnalysisFormatError(
            "%s認不得的 AI 分析結果版本：%r" % (where, raw_version),
            "這份實作認得的是 schema_version %d —— 數字與純數字字串都收"
            "（%d、\"%d\"、\"%d.0\" 視為同一個版本）。\n"
            "版本不合時不做猜測 —— 猜錯的結果是一份看起來正常、實際上少了幾段的"
            "報告，而它會回報成功。"
            % (ANALYSIS_SCHEMA_VERSION, ANALYSIS_SCHEMA_VERSION,
               ANALYSIS_SCHEMA_VERSION, ANALYSIS_SCHEMA_VERSION),
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


# 條目內的縮排。理由與 diff 都縮在 bullet 底下，讓它們在視覺上屬於那一筆，而不是
# 平鋪在檔案標題下的另一段。兩格是 markdown 認得的清單延續縮排。
# --- 報告末尾的出處資訊 ------------------------------------------------------
#
# 一份報告被貼到 MR 討論串之後就脫離了產生它的環境。半年後有人問「這段分析是哪來的、
# 為什麼跟現在跑出來的不一樣」，footer 是唯一答得出來的東西。

# 這支腳本的名稱與版本。**改了報告的產出方式就把版本往上加** —— 那是這一行存在的
# 唯一理由，不加的話舊報告與新報告在外觀上分不出來。
SCRIPT_NAME = "MR Summary Script"
SCRIPT_VERSION = "1.0"


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


def _jira_label(analysis):
    """出處資訊裡 JIRA 的那一段。

    依狀態而異：

        ok       印 key；有網址就做成連結
        none     印 NONE
        invalid  印**被拒絕的原值**加 (invalid)

    印原值而不是 NONE 是刻意的：看到 `JIRA: WIP (invalid)` 就知道標題的第一個方括號放
    的是 WIP，直接指出怎麼修；只印 NONE 的話只知道失敗了。

    狀態由產生分析的那一步判定並隨結構帶過來，**這裡不重新判定** —— 重判就會有第二份
    規則，兩份必然漂移。
    """
    if not isinstance(analysis, dict):
        return ""

    state = plain(analysis.get("jira_state")) or JIRA_STATE_NONE
    key = plain(analysis.get("jira_key"))

    if state == JIRA_STATE_OK and key:
        return "JIRA: %s" % _link(key, plain(analysis.get("jira_url")))
    if state == JIRA_STATE_INVALID:
        return "JIRA: %s (invalid)" % (key or "(空值)")
    return "JIRA: NONE"


def render_footer(ai_mode="", device_name="", device_version="", analysis=None):
    """報告最後那一段出處資訊。

    形狀：

        ---

        Script: v1.0 | Device: ssd v1.2 | AI Mode: Open AI | JIRA: WIP (invalid)
        Gitlab Pipeline #1000 | Commit e456d23

    每個值前面都有名字。沒有標籤的話（例如 `(Open AI / ssd v1.2)`）兩個版本號並列時
    讀的人分不出哪一個是腳本的、哪一個是 device 的。

    `Script` 是入口腳本與契約的版本，`Device` 是那個 device 自己的。分開標示的理由是
    同一份 MR 用不同 device 跑出來的報告不一樣 —— 只有一個全域版本號的話，兩份不同的
    報告會帶同一個版本。

    第二行依環境而定：CI 裡是 pipeline 與 commit，從工具跑是工具名稱與版本，兩者都沒有
    （命令列直接執行）就整行不出現。**第一行永遠都在** —— 它是這整段存在的理由。

    分隔線之前必須空一行，否則 markdown 會把上一行文字當成 setext 標題。
    """
    parts = ["Script: v%s" % SCRIPT_VERSION]

    name = plain(device_name)
    if name:
        version = plain(device_version)
        parts.append("Device: %s" % (("%s v%s" % (name, version)) if version else name))

    mode = plain(ai_mode)
    if mode:
        parts.append("AI Mode: %s" % mode)

    jira = _jira_label(analysis)
    if jira:
        parts.append(jira)

    lines = [" | ".join(parts)]
    origin = _ci_origin() or _tool_origin()
    if origin:
        lines.append(origin)

    return "---\n\n" + "\n".join(lines)