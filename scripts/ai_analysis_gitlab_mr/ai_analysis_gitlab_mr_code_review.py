#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 4/5：取得程式碼審閱報告。

這一步**永遠會被執行**。「要不要真的去抓」由 fetch_code_review 這個參數決定，
呼叫端不跳過任何步驟 —— 分支若寫在呼叫端，持續整合那一側就成為第二份編排
實作，兩份必然漂移。不需要抓的時候，回一份空報告並回報成功。

**本輪為 stub**：不連線任何服務。

    python ai_analysis_gitlab_mr_code_review.py --help
    python ai_analysis_gitlab_mr_code_review.py --dump-config > run.json
    python ai_analysis_gitlab_mr_code_review.py --request run.json
"""

import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "fetch_code_review"
DESCRIPTION      = "取得 Merge Request 的程式碼審閱報告（本輪為 stub）"


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[
            script_io.arg("repo", required=True,
                          help="專案，namespace/project 形式"),
            script_io.arg("mr_iid", required=True,
                          help="Merge Request 編號"),
            script_io.arg("fetch_code_review", type=bool, default=False,
                          help="是否真的取得報告；為假時回一份空報告並成功"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把報告寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    if not params["fetch_code_review"]:
        # 不做事也是成功。回空報告，後面的合併步驟自己決定要不要放進去。
        logger.info("未要求取得程式碼審閱報告，略過")
        script_io.progress("略過程式碼審閱報告…")
        ai_analysis_gitlab_mr.write_debug_log(
            params["debug_dir"], "code_review skipped repo=%s mr=%s"
                                 % (repo, mr_iid))
        script_io.reply(
            message="未要求取得程式碼審閱報告",
            detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
            data={"code_review": ""},
        )

    logger.info("取得 %s !%s 的程式碼審閱報告", repo, mr_iid)
    script_io.progress("取得程式碼審閱報告…")

    # ---- stub：真實實作會在這裡取回審閱報告 ----
    code_review = "\n".join([
        "## 程式碼審閱報告",
        "",
        "- 檢查項目：12",
        "- 待處理：2",
        "",
        "> 這是 stub 產生的假報告。",
    ])
    # --------------------------------------------

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], code_review)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "code_review repo=%s mr=%s len=%d" % (repo, mr_iid, len(code_review)))

    script_io.reply(
        message="已取得程式碼審閱報告",
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data={"code_review": code_review},
    )


if __name__ == "__main__":
    script_io.run(main)
