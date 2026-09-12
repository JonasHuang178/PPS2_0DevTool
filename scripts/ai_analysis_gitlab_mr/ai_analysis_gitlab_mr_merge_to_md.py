#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 5/5：合併為 markdown。

把前四步的產出合併成一份報告。**完整的 markdown 內容一律放進 data**，
呼叫端因此不需要開啟任何檔案就能顯示結果 —— 使用者沒有勾選產生除錯分析檔
時，根本沒有檔案可以開。

給了 out_path 才**額外**寫一份檔案。

**本輪為 stub**：合併邏輯是真的，但被合併的內容來自前面幾步的假資料。

    python ai_analysis_gitlab_mr_merge_to_md.py --help
    python ai_analysis_gitlab_mr_merge_to_md.py --dump-config > run.json
    python ai_analysis_gitlab_mr_merge_to_md.py --request run.json
"""

import datetime
import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "merge_to_md"
DESCRIPTION      = "把前面各步的產出合併成一份 markdown 報告"


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
                          help="MR 描述；留空時改讀 description_path"),
            script_io.arg("description_path", default="",
                          help="描述檔的路徑（命令列與 CI 走這條）"),
            script_io.arg("script_info", type=dict, default={},
                          help="相關資訊；留空時改讀 script_info_path"),
            script_io.arg("script_info_path", default="",
                          help="script_info 檔的路徑"),
            script_io.arg("summary", default="",
                          help="AI 分析結果；留空時改讀 summary_path"),
            script_io.arg("summary_path", default="",
                          help="分析結果檔的路徑"),
            script_io.arg("code_review", default="",
                          help="程式碼審閱報告；留空時改讀 code_review_path"),
            script_io.arg("code_review_path", default="",
                          help="審閱報告檔的路徑"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把報告寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    description = ai_analysis_gitlab_mr.resolve_text_input(params, "description")
    script_info = ai_analysis_gitlab_mr.resolve_json_input(params, "script_info")
    summary     = ai_analysis_gitlab_mr.resolve_text_input(params, "summary")
    code_review = ai_analysis_gitlab_mr.resolve_text_input(params, "code_review")

    logger.info("合併報告：描述 %d、分析 %d、審閱 %d 字元",
                len(description), len(summary), len(code_review))
    script_io.progress("合併為 markdown…")

    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    sections = [
        "# AI Analysis — %s !%s" % (repo, mr_iid),
        "",
        "產生時間：%s" % stamp,
    ]

    jira_key = script_info.get("jira_key")
    if jira_key:
        sections.append("JIRA：%s" % jira_key)

    if description:
        sections += ["", "---", "", description]
    if summary:
        sections += ["", "---", "", summary]

    # 空的審閱報告就整段不放 —— 一個只有標題沒有內容的區塊比沒有還糟。
    if code_review:
        sections += ["", "---", "", code_review]

    markdown = "\n".join(sections)

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], markdown)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "merge_to_md repo=%s mr=%s len=%d" % (repo, mr_iid, len(markdown)))

    script_io.reply(
        message="報告已產生（%d 字元）" % len(markdown),
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data={"markdown": markdown},
    )


if __name__ == "__main__":
    script_io.run(main)
