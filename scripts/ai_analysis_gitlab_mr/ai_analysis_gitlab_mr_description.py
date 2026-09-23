#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 1/5：取得 Merge Request 描述。

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
DESCRIPTION      = "取得指定 Merge Request 的描述"


def _build_markdown(repo, mr_iid, mr):
    """把 GitLab 原樣的 MR 物件整理成一份 markdown 文件。

    為什麼不只回傳 description 欄位：這份內容要落成 01_description.md，也要當作
    後面 AI 分析那一步的輸入。標題、分支與作者是判讀一則描述時的必要背景 ——
    只給描述本文，AI 連「這是往哪個分支合」都不知道。

    欄位全部以 or "" 取值：GitLab 對沒填的欄位給的是 null，直接丟進字串格式化會
    變成 "None" 印在文件上。
    """
    title = (mr.get("title") or "").strip()
    author = (mr.get("author") or {}).get("name") \
        or (mr.get("author") or {}).get("username") or ""
    source_branch = mr.get("source_branch") or ""
    target_branch = mr.get("target_branch") or ""
    state = mr.get("state") or ""
    created_at = mr.get("created_at") or ""
    web_url = mr.get("web_url") or ""
    body = (mr.get("description") or "").strip()

    lines = ["# !%s %s" % (mr_iid, title) if title else "# !%s" % mr_iid, ""]

    facts = [("專案", repo)]
    if source_branch or target_branch:
        facts.append(("分支", "`%s` → `%s`" % (source_branch, target_branch)))
    if author:
        facts.append(("作者", author))
    if state:
        facts.append(("狀態", state))
    if created_at:
        facts.append(("建立時間", created_at))
    if web_url:
        facts.append(("網址", web_url))

    for name, value in facts:
        lines.append("- **%s**：%s" % (name, value))

    lines.extend(["", "## 描述", ""])

    if body:
        lines.append(body)
    else:
        # 沒有描述是正常狀態，不是錯誤。明著寫出來，後面的 AI 才不會把一份
        # 空白當成「取得失敗」而去猜內容。
        lines.append("> 這個 Merge Request 沒有填寫描述。")

    return "\n".join(lines) + "\n"


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
                          help="額外把描述寫到這個檔案；空字串代表不落檔"),
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

    description = _build_markdown(repo, mr_iid, mr or {})

    # 給了 out_path 才落檔。為空時一個檔案都不會產生。
    ai_analysis_gitlab_mr.write_artifact(params["out_path"], description)
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "description -> %d 字元" % len(description))

    logger.info("描述取得完成，共 %d 字元", len(description))

    # 描述是空的仍然是成功：那是 MR 本身沒填，不是取得失敗。回 FAIL 會讓整條
    # 五步流程因為一筆沒寫描述的 MR 而中斷。
    script_io.reply(
        message="已取得 Merge Request !%s 的描述" % mr_iid,
        detail="專案：%s" % repo,
        data={"description": description},
    )


if __name__ == "__main__":
    script_io.run(main)
