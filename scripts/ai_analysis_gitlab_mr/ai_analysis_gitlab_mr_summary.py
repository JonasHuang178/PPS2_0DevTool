#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 3/5：AI 分析。

JIRA key 的三種模式在**這裡**解析，不在 Qt 端：呼叫端一律把三個值原樣送來
（模式、手動指定的、上一步偵測到的），由這支腳本決定採用哪一個。判斷寫在
Qt 端的話，持續整合那一側就得再實作一次同樣的三個分支。

**本輪為 stub**：不呼叫任何 AI 供應商，回傳寫死的假分析結果。因此沒有金鑰
也能跑完整條流程。

    python ai_analysis_gitlab_mr_summary.py --help
    python ai_analysis_gitlab_mr_summary.py --dump-config > run.json
    python ai_analysis_gitlab_mr_summary.py --request run.json
"""

import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "ai_summary"
DESCRIPTION      = "以 AI 分析 Merge Request（本輪為 stub）"


def resolve_jira_key(mode, manual, detected):
    """三選一。這段判斷屬於腳本，不屬於呼叫端。"""
    if mode == "manual":
        return manual
    if mode == "auto":
        return detected
    return ""


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
                          help="上一步的相關資訊；留空時改讀 script_info_path"),
            script_io.arg("script_info_path", default="",
                          help="script_info 檔的路徑（命令列與 CI 走這條）"),
            script_io.arg("ai_mode_name", default="",
                          help="AI 模式名稱"),
            script_io.arg("ai_api_url", default="",
                          help="AI 端點"),
            script_io.arg("ai_api_key", default="",
                          help="AI 金鑰"),
            script_io.arg("ai_model", default="",
                          help="AI 模型名稱"),
            script_io.arg("jira_mode", default="none",
                          help="none / manual / auto"),
            script_io.arg("jira_key_manual", default="",
                          help="使用者手動指定的 JIRA key"),
            script_io.arg("jira_key_detected", default="",
                          help="上一步偵測到的 JIRA key"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把分析結果寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    description = ai_analysis_gitlab_mr.resolve_text_input(params, "description")
    script_info = ai_analysis_gitlab_mr.resolve_json_input(params, "script_info")

    jira_key = resolve_jira_key(params["jira_mode"],
                                params["jira_key_manual"],
                                params["jira_key_detected"])

    # 金鑰不進 log。
    logger.info("AI 分析：mode=%s model=%s jira_mode=%s jira_key=%s",
                params["ai_mode_name"] or "(未指定)",
                params["ai_model"] or "(未指定)",
                params["jira_mode"], jira_key or "(無)")
    script_io.progress("送交 AI 分析…")

    # ---- stub：真實實作會在這裡組 prompt 並呼叫 ai_api_url ----
    summary = "\n".join([
        "## AI 分析結果",
        "",
        "- 模式：%s" % (params["ai_mode_name"] or "(未指定)"),
        "- 模型：%s" % (params["ai_model"] or "(未指定)"),
        "- JIRA：%s" % (jira_key or "(未使用)"),
        "- 裝置：%s" % (script_info.get("device") or "(未知)"),
        "",
        "### 風險",
        "",
        "1. 重試上限調高後，失敗路徑的總等待時間可能超過呼叫端的逾時。",
        "2. 競態修正只涵蓋讀取路徑，寫入路徑未一併檢查。",
        "",
        "### 建議",
        "",
        "- 補一個涵蓋並行讀寫的測試。",
        "",
        "> 這是 stub 產生的假分析，尚未呼叫任何 AI 供應商。",
        "> 描述長度 %d 字元，處理方式 %s。"
        % (len(description),
           (script_info.get("ai_summary") or {}).get("handler") or "(未指定)"),
    ])
    # -----------------------------------------------------------

    payload = {"summary": summary, "jira_key": jira_key}

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], payload)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "summary repo=%s mr=%s jira_key=%s len=%d"
        % (repo, mr_iid, jira_key, len(summary)))

    script_io.reply(
        message="AI 分析完成",
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data=payload,
    )


if __name__ == "__main__":
    script_io.run(main)
