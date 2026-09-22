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

    # 憑證與錯誤訊息都走功能套件的共用實作 —— 本功能有兩支腳本要連 GitLab，
    # 各自寫一份的話兩份會慢慢長歪，而使用者看到的差異（同樣是 401，一支說
    # 「請檢查權杖」、另一支說「查詢失敗」）完全沒有道理。
    try:
        server_url, token, verify_ssl = ai_analysis_gitlab_mr.gitlab_credentials()
    except ai_analysis_gitlab_mr.CredentialError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

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
        message, detail, code = ai_analysis_gitlab_mr.describe_gitlab_error(
            exc, repo)
        script_io.reply_fail(message, detail=detail, code=code)

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
