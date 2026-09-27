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
    "DESCRIPTION_HEADING",
    "AI_HEADING",
    "LEGACY_DESCRIPTION_HEADINGS",
    "split_description",
    "render_description_section",
    "render_ai_section",
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
# 兩個標題常數只有這一份，因為它們是同一個邊界的兩側：步驟 5 用 AI_HEADING
# 寫出那一段，而步驟 1 就是靠同一個字串把它切掉。兩邊各寫一份而漂移的症狀是
#「報告裡的 AI 分析疊了兩段，舊的那段還在」—— 而每一步都會回報成功，沒有
# 任何地方會喊。

DESCRIPTION_HEADING = "# Original description"
AI_HEADING = "# AI 分析"

# 舊版寫出去過、現在仍需認得的標題。
#
# 改了上面的常數之後，舊的那個要搬進這裡 —— 既有 MR 的描述裡還留著它，不認得的話
# 那一行會突然變成「原始描述的內容」，而下一輪又接上一段新的 AI 分析，於是疊起來。
#
# oirignal 是早期版本寫出去的筆誤。寫出去的已經是正確拼法，帶著舊拼法的描述被處理
#
# AI 分析的標題沒有這樣一份清單，因為它還沒被改過。真要改的時候，照這裡的樣子
# 加一個 LEGACY_AI_HEADINGS 再展開進 _AI_RE 即可。
# 過一次之後就自己改正了；在確定沒有任何 MR 還帶著它之前，這一條不能拿掉。
LEGACY_DESCRIPTION_HEADINGS = ("# Oirignal description",)


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


_DESCRIPTION_RE = _heading_pattern(DESCRIPTION_HEADING,
                                   *LEGACY_DESCRIPTION_HEADINGS)
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


def render_description_section(original):
    """步驟 1 的產物：標題加上原始描述。原始描述是空的就回傳空字串。

    沒填描述的 MR 不該在報告裡留下一個只有標題、底下什麼都沒有的區塊 ——
    那個標題只會讓人以為內容漏掉了。整段不放，報告就只剩 AI 分析那一段。
    """
    body = original.strip()
    if not body:
        return ""
    return "%s\n\n%s\n" % (DESCRIPTION_HEADING, body)


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
