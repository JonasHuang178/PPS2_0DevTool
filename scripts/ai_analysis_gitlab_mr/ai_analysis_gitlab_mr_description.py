#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 1/5：取得 Merge Request 的原始描述。

MR 的描述可能同時裝著兩樣東西：人寫的原始描述，以及先前某一輪的 AI 分析。這一
步只取前者。切法與標題常數都在 ai_analysis_gitlab_mr 裡，與步驟 5 共用同一份
—— 步驟 5 寫出那一段用的標題，就是這裡用來切的那一刀。

沒填描述的 MR 會得到空字串，而且仍然是成功：那是 MR 本身沒填，不是取得失敗。

    python ai_analysis_gitlab_mr_description.py --help
    python ai_analysis_gitlab_mr_description.py --dump-config > run.json
    python ai_analysis_gitlab_mr_description.py --request run.json

憑證走環境變數，不放進 request 檔案 —— 那個檔案會留在 CI runner 的工作目錄：

    GITLAB_SERVER_URL    https://gitlab.example.com
    GITLAB_ACCESS_TOKEN  glpat-...
    GITLAB_VERIFY_SSL    true / false（未設定視為 false，即不驗證）
"""

import os
import sys

# 入口腳本放在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進
# sys.path —— 少了下面這一行，命令列直接執行時 script_io 與 script_utils
# 都匯不到。Qt 會注入指向 scripts/ 的 PYTHONPATH，但那不能當成前提。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import gitlab_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "mr_description"
DESCRIPTION      = "取得指定 Merge Request 的原始描述（不含上一輪的 AI 分析）"


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
            script_io.arg("mr_iid", required=True,
                          help="Merge Request 編號（畫面上的 !123，不是全域 id）"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把原始描述寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]
    debug_dir = params["debug_dir"]

    try:
        server_url, token, verify_ssl = ai_analysis_gitlab_mr.gitlab_credentials()
    except ai_analysis_gitlab_mr.CredentialError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    logger.info("取得 %s 的 Merge Request !%s 描述（verify_ssl=%s）",
                repo, mr_iid, verify_ssl)
    script_io.progress("取得 Merge Request 描述…")
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "description repo=%s mr=%s" % (repo, mr_iid))

    try:
        mr = gitlab_utils.get_mr_info(server_url, token, repo, mr_iid,
                                      verify_ssl=verify_ssl)
    except gitlab_utils.GitLabError as exc:
        message, detail, code = ai_analysis_gitlab_mr.describe_gitlab_error(
            exc, repo)
        # 這一步指名了某一筆 MR，所以 404 的成因多一種：iid 不存在。
        if code == "GITLAB_PROJECT_NOT_FOUND":
            message = "找不到 %s 的 Merge Request !%s" % (repo, mr_iid)
            detail = ("%s\n\n可能是專案名稱拼錯、!%s 這個編號不存在，"
                      "或權杖對該專案沒有讀取權限（後者 GitLab 也回 404）。\n"
                      "注意編號用的是畫面上的 !%s，不是 MR 的全域 id。"
                      % (exc, mr_iid, mr_iid))
            code = "GITLAB_MR_NOT_FOUND"
        script_io.reply_fail(message, detail=detail, code=code)

    # 描述裡可能已經有先前某一輪的 AI 分析。只留人寫的那一段 —— 不切的話，舊
    # 的分析會被當成原始描述往下傳，步驟 5 再接上一段新的，報告裡於是有兩段 AI
    # 分析，而舊的那段還在。
    original, _ = ai_analysis_gitlab_mr.split_description(
        (mr or {}).get("description") or "")
    description = ai_analysis_gitlab_mr.render_original_description(original)

    # 給了 out_path 才落檔。為空時一個檔案都不會產生。
    #
    # 原始描述是空的時候**仍然要寫出那個檔案**（內容為零位元組）。它是這一步確實
    # 跑過的證據：勾了除錯分析檔的人打開目錄，看到 01_description.md 在那裡但是空
    # 的，知道的是「這筆 MR 沒填描述」；檔案整個不在，看起來像這一步沒跑或掛了。
    # 步驟 5 也吃得下空檔案 —— 它讀到空內容就整段略過。
    #
    # 這個行為現在是 write_artifact() 照寫不誤得來的。若哪天有人在那裡加一句
    # 「內容為空就不寫」，這裡會安靜地不再產生檔案，所以把意圖寫在這裡。
    ai_analysis_gitlab_mr.write_artifact(params["out_path"], description)
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "description -> %d 字元" % len(description))

    logger.info("描述取得完成，共 %d 字元", len(description))

    # 描述是空的仍然是成功：那是 MR 本身沒填，不是取得失敗。回 FAIL 會讓整條
    # 五步流程因為一筆沒寫描述的 MR 而中斷。
    message = (("已取得 Merge Request !%s 的原始描述" % mr_iid)
               if description
               else ("Merge Request !%s 沒有填寫描述" % mr_iid))

    script_io.reply(
        message=message,
        detail="專案：%s" % repo,
        data={"description": description},
    )


if __name__ == "__main__":
    script_io.run(main)
