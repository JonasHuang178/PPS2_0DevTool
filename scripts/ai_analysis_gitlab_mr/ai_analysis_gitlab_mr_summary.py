#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 3/5：AI 分析。

JIRA key 的三種模式在**這裡**解析，不在 Qt 端：呼叫端一律把三個值原樣送來
（模式、手動指定的、上一步偵測到的），由這支腳本決定採用哪一個。判斷寫在
Qt 端的話，持續整合那一側就得再實作一次同樣的三個分支。

**本輪為 stub**：不呼叫任何 AI 供應商，回傳寫死的假分析。因此沒有金鑰也能跑完
整條流程。但**產出的結構是真的** —— 它用的是 ai_analysis_gitlab_mr 的建構函式，
與真實實作會產出的形狀完全一樣，步驟 5 的渲染因此驗得到。

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


def jira_url(jira_key):
    """把 JIRA key 組成可點的網址。沒有 key 或沒設伺服器位址時回空字串。

    伺服器位址走環境變數（Qt 會把設定檔 Service.Jira_Server_URL 以全大寫注入），
    與 GitLab 的憑證同一條路徑 —— 腳本端只有一種取值方式，命令列與 CI 長得一樣。

    結構裡只有 jira_url 沒有裸的 key，所以這一步要是組不出網址，那個 key 就不會
    出現在報告裡。組不出來的情況只有「沒設 JIRA_SERVER_URL」，而那是設定問題，
    不是這一步該失敗的理由。
    """
    if not jira_key:
        return ""
    server = os.environ.get("JIRA_SERVER_URL", "").strip().rstrip("/")
    if not server:
        logger.debug("未設定 JIRA_SERVER_URL，jira_url 留空")
        return ""
    return "%s/browse/%s" % (server, jira_key)


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
    #
    # 假的是內容，不是形狀：底下用的是與真實實作同一組建構函式，所以步驟 5 的渲染、
    # 圍籬處理與版本檢查全都被這條流程驗到。
    payload = ai_analysis_gitlab_mr.analysis_payload(
        overview=("這是 stub 產生的假分析，尚未呼叫任何 AI 供應商。\n"
                  "描述長度 %d 字元，處理方式 %s。"
                  % (len(description),
                     (script_info.get("ai_summary") or {}).get("handler")
                     or "(未指定)")),
        model=params["ai_model"] or "(未指定)",
        jira_url=jira_url(jira_key),
        mr_diff={
            "cpp/example.cpp": [
                ai_analysis_gitlab_mr.finding(
                    title="重試上限調高後可能超過呼叫端的逾時",
                    reason="單次逾時 30s、重試 10 次，最壞情況 300s。",
                    diff_code="@@ -12,7 +12,7 @@\n-    retry = 3\n+    retry = 10"),
                ai_analysis_gitlab_mr.finding(
                    title="競態修正只涵蓋讀取路徑",
                    reason="寫入路徑用的是同一個 cache，未一併加鎖。"),
            ],
            "tests/example_test.cpp": [
                # 清單的第一筆當「對整個檔案的一句話」用 —— 不需要為它另設一層。
                ai_analysis_gitlab_mr.finding(
                    title="新增的測試蓋不到這次修的問題",
                    reason="只有單執行緒的案例。"),
            ],
        },
    )
    # -----------------------------------------------------------

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], payload)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "summary repo=%s mr=%s jira_key=%s files=%d"
        % (repo, mr_iid, jira_key,
           len(payload["analysis"]["mrDiff"])))

    script_io.reply(
        message="AI 分析完成",
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data=payload,
    )


if __name__ == "__main__":
    script_io.run(main)
