#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 取得 Merge Request 清單。

這一支是**真實實作**：它真的連線到 GitLab。流程五步是 stub，這一支不是。

    python ai_analysis_gitlab_mr_list_merge_requests.py --help
    python ai_analysis_gitlab_mr_list_merge_requests.py --dump-config > run.json
    python ai_analysis_gitlab_mr_list_merge_requests.py --request run.json

憑證走環境變數，不放進 request 檔案 —— 那個檔案會留在 CI runner 的工作目錄：

    GITLAB_SERVER_URL    https://gitlab.example.com
    GITLAB_ACCESS_TOKEN  glpat-...
    GITLAB_VERIFY_SSL    true / false（未設定視為 false，即不驗證）
"""

import datetime
import os
import sys

# 入口腳本放在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進
# sys.path —— 少了下面這一行，命令列直接執行時 script_io 與 script_utils
# 都匯不到。Qt 會注入指向 scripts/ 的 PYTHONPATH，但那不能當成前提：
# 命令列與 CI 直接執行時沒有那個環境，而那是本專案明確支援的用法。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import gitlab_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "list_merge_requests"
DESCRIPTION      = "列出指定 GitLab 專案的 Merge Request"


def _truthy(text):
    return str(text).strip().lower() in ("true", "1", "yes")


def _row(raw):
    """把 GitLab 原樣的 MR 物件收斂成畫面需要的六個欄位。

    共用模組回傳的是 GitLab 原樣的資料（一筆約 2～4 KB、四十幾個欄位），挑欄位
    是入口腳本的職責 —— 整包塞進結果信封的話，一百筆就有幾百 KB 要經 stdout
    送回 Qt，而畫面只用得到這幾個。

    author 攤平成字串：Qt 端讀的是 data.merge_requests[].author，巢狀物件會讓
    那邊得認得 GitLab 的 schema。
    """
    author = raw.get("author") or {}
    return {
        "iid": raw.get("iid"),
        "title": raw.get("title") or "",
        "author": author.get("name") or author.get("username") or "",
        "created_at": raw.get("created_at") or "",
        "state": raw.get("state") or "",
        "web_url": raw.get("web_url") or "",
    }


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,

        # 憑證不在這裡宣告 —— 它們走環境變數。在 config 宣告會讓使用者以為
        # 該把權杖填進 request 檔案裡。
        config=[],

        params=[
            script_io.arg("repo", required=True,
                          help="專案，namespace/project 形式"),
            script_io.arg("only_open", type=bool, default=True,
                          help="只取尚未關閉的 Merge Request"),
            script_io.arg("created_after_enabled", type=bool, default=True,
                          help="是否套用「N 天內建立」的條件"),
            script_io.arg("created_after_days", type=int, default=7,
                          help="只取這麼多天內建立的（1-365）"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把結果寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    debug_dir = params["debug_dir"]

    # 憑證只從環境變數讀，不從 config 讀 —— 腳本端因此只有一條取值路徑，
    # Qt 與 CI 對它來說長得一模一樣。
    #
    # 也別把整包 config log 出來：合併後的 config 含有權杖。
    server_url = os.environ.get("GITLAB_SERVER_URL", "").strip()
    token      = os.environ.get("GITLAB_ACCESS_TOKEN", "").strip()

    # 未設定視為不驗證（見 design.md 決策二十三）。這個預設是明確的取捨：
    # 目標環境是否使用自簽憑證尚不確定，而驗證失敗會讓功能完全無法使用。
    verify_ssl = _truthy(os.environ.get("GITLAB_VERIFY_SSL", "false"))

    if not server_url:
        script_io.reply_fail(
            "未設定環境變數 GITLAB_SERVER_URL",
            detail="設定檔的 Service.Gitlab_Server_URL 會由工具注入為這個環境"
                   "變數；以命令列執行時請自行設定。",
            code="GITLAB_SERVER_URL_MISSING")

    if not token:
        script_io.reply_fail(
            "未設定環境變數 GITLAB_ACCESS_TOKEN",
            detail="設定檔的 Service.Gitlab_Access_Token 會由工具注入為這個"
                   "環境變數；以命令列執行時請自行設定。",
            code="GITLAB_ACCESS_TOKEN_MISSING")

    days = params["created_after_days"] if params["created_after_enabled"] else None

    logger.info("查詢 %s 的 Merge Request（only_open=%s, days=%s, verify_ssl=%s）",
                repo, params["only_open"], days, verify_ssl)
    script_io.progress("向 GitLab 查詢 Merge Request…")
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "list_merge_requests repo=%s only_open=%s days=%s"
                   % (repo, params["only_open"], days))

    # gitlab_utils 的 created_after 收 ISO 8601 或 date/datetime，不收「幾天前」
    # 的數字 —— 同一個參數有時是日期有時是天數，呼叫端讀簽章讀不出來該傳什麼。
    # 「N 天內」是這個功能自己的說法，因此換算寫在這裡。
    created_after = None
    if days is not None:
        created_after = (datetime.datetime.now(datetime.timezone.utc)
                         - datetime.timedelta(days=int(days)))

    limit = ai_analysis_gitlab_mr.MERGE_REQUEST_LIMIT

    try:
        # max_items 剛好等於上限，不多要一筆。多要一筆雖然能精確分辨「正好這麼
        # 多」與「被截斷了」，但 GitLab 每頁上限就是 100，第 101 筆必然要再打一次
        # 請求 —— 而規格明文要求不得為了取回其餘筆數發出額外的請求。
        #
        # 代價是剛好 100 筆時也會說「可能未完整」。那是規格接受的不精確：使用者
        # 的下一步（調緊查詢條件）在兩種情況下都一樣。
        raw = gitlab_utils.get_all_mr(
            server_url, token, repo,
            created_after=created_after,
            status=("opened",) if params["only_open"] else ("all",),
            max_items=limit,
            verify_ssl=verify_ssl,
        )
    except gitlab_utils.GitLabError as exc:
        # 共用模組只拋一種例外，型別由 status_code 分流。訊息刻意分開寫：
        # 使用者的下一步完全不一樣 —— 一個去換權杖，一個去改設定檔的拼字。
        status = exc.status_code

        if status in (401, 403):
            script_io.reply_fail(
                "GitLab 拒絕了這次請求，請檢查存取權杖",
                detail="%s\n\n權杖來自環境變數 GITLAB_ACCESS_TOKEN"
                       "（設定檔的 Service.Gitlab_Access_Token）。\n"
                       "請確認它未過期、且對專案 %s 有讀取權限。" % (exc, repo),
                code="GITLAB_AUTH_FAILED")

        if status == 404:
            script_io.reply_fail(
                "找不到專案 %s" % repo,
                detail="%s\n\n請檢查設定檔 Repo_List 中的專案名稱是否拼寫正確"
                       "（namespace/project 形式）。\n"
                       "注意：權杖若對該專案沒有權限，GitLab 也會回 404。"
                       % exc,
                code="GITLAB_PROJECT_NOT_FOUND")

        # TLS 失敗沒有 HTTP 狀態碼（連線根本沒建立起來），只能看訊息內容。
        # requests 把憑證問題包成 SSLError，訊息裡一定帶得到這些字樣。
        lowered = str(exc).lower()
        if status is None and ("ssl" in lowered or "certificate" in lowered):
            script_io.reply_fail(
                "TLS 憑證驗證失敗",
                detail="%s\n\n兩種解法：\n"
                       "  1. 把受信任的 CA 憑證指給環境變數 REQUESTS_CA_BUNDLE\n"
                       "  2. 把設定檔的 Service.Gitlab_Verify_SSL 設為 \"false\"\n"
                       "第一種較安全 —— 關閉驗證時，存取權杖會暴露給連線中間人。\n"
                       "注意是 REQUESTS_CA_BUNDLE 而不是 SSL_CERT_FILE："
                       "底層改用 requests 之後，只有前者會被讀取。"
                       % exc,
                code="GITLAB_TLS_FAILED")

        script_io.reply_fail("GitLab 查詢失敗：%s" % exc,
                             code="GITLAB_REQUEST_FAILED")

    truncated = len(raw) >= limit
    items = [_row(one) for one in raw]
    result = {"merge_requests": items, "truncated": truncated}

    logger.info("取回 %d 筆%s", len(items), "（已達上限）" if truncated else "")

    # 勾了除錯才落檔。out_path 為空時一個檔案都不會產生。
    ai_analysis_gitlab_mr.write_artifact(params["out_path"], result)
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "list_merge_requests -> %d 筆, truncated=%s"
                   % (len(items), truncated))

    message = "取得 %d 筆 Merge Request" % len(items)
    if truncated:
        message += "（已達單次取回上限 %d，結果可能未完整）" % limit

    # 取回 0 筆是成功而非失敗 —— 條件太緊是正常結果，回 FAIL 會讓使用者
    # 每次收斂條件都看到一個錯誤訊息框。
    script_io.reply(
        message=message,
        detail="專案：%s" % repo,
        data=result,
    )


if __name__ == "__main__":
    script_io.run(main)
