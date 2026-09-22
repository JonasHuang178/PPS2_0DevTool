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

from script_utils import logger

__all__ = [
    "MERGE_REQUEST_LIMIT",
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
