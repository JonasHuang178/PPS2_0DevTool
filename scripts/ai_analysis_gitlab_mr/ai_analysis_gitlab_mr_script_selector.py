#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 2/5：取得相關資訊。

回傳一份 script_info，內含狀態、裝置、JIRA key，以及後續兩步各自要用的
處理方式（handler / source / path）。

**handler 由後續步驟自己解讀**，Qt 端不依它決定要執行哪一支腳本 —— 腳本
路徑固定寫死在 C++ 裡。這樣持續整合那一側也只是照順序跑，不需要解析這份
JSON 再自己決定要 exec 什麼。

**本輪為 stub**：回傳寫死的假資訊。

    python ai_analysis_gitlab_mr_script_selector.py --help
    python ai_analysis_gitlab_mr_script_selector.py --dump-config > run.json
    python ai_analysis_gitlab_mr_script_selector.py --request run.json
"""

import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "script_selector"
DESCRIPTION      = "取得 Merge Request 的相關資訊與處理方式（本輪為 stub）"


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
            script_io.arg("description", default="",
                          help="上一步取得的描述；留空時改讀 description_path"),
            script_io.arg("description_path", default="",
                          help="描述檔的路徑（命令列與 CI 走這條）"),
            script_io.arg("device", default="",
                          help="裝置代號；來源尚未定案，本輪不使用"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把 script_info 寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    # 輸入雙軌：params 有內容就用內容（Qt 走這條），
    # 沒內容但有路徑就讀路徑（CI 走這條）。
    description = ai_analysis_gitlab_mr.resolve_text_input(params, "description")

    logger.info("解析 %s !%s 的相關資訊（描述 %d 字元）",
                repo, mr_iid, len(description))
    script_io.progress("解析 Merge Request 相關資訊…")

    # ---- stub：真實實作會在這裡從描述／分支名推出 JIRA key 與處理方式 ----
    script_info = {
        "status": "ok",
        "device": params["device"] or "PS5031",
        "jira_key": "PPS-1234",
        "ai_summary": {
            "handler": "default_summary",
            "source": "merge_request",
            "path": "",
        },
        "merge_to_md": {
            "handler": "default_merge",
            "source": "merge_request",
            "path": "",
        },
    }
    # ---------------------------------------------------------------------

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], script_info)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "script_selector repo=%s mr=%s jira_key=%s"
        % (repo, mr_iid, script_info["jira_key"]))

    script_io.reply(
        message="已取得相關資訊（handler=%s）"
                % script_info["ai_summary"]["handler"],
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data={"script_info": script_info},
    )


if __name__ == "__main__":
    script_io.run(main)
