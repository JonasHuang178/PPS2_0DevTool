#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 3/5：AI 分析。

這一步的業務運算全部交給 device 的 summary 鉤子 —— 要問 AI 什麼、怎麼解析、組出什麼
分析內容，由該 device 決定。入口只負責信封、參數、驗證與落檔。

**鉤子回傳的結構在收到的當下就驗證。** 不驗的話，錯誤會在兩步之後的渲染才爆，而訊息
指的是合併那一步、不是寫壞的那個 device。

    python ai_analysis_gitlab_mr_summary.py --help
    python ai_analysis_gitlab_mr_summary.py --dump-config > run.json
    python ai_analysis_gitlab_mr_summary.py --request run.json

    PPS_DEVICE   sd / ssd / ...（未設定時用 default）
"""

import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from ai_analysis_gitlab_mr import device
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "ai_summary"
DESCRIPTION      = "以 AI 分析 Merge Request（內容由 device 的鉤子決定）"


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
            script_io.arg("jira_key", default="",
                          help="上一步解出的 JIRA key；有效性由 device 的鉤子判定"),
            script_io.arg("jira_mode", default="auto",
                          help="none / manual / auto；唯讀傳給鉤子，讓它分辨 key 的來源"),
            script_io.arg("ai_mode_name", default="", help="AI 模式名稱"),
            script_io.arg("ai_api_url", default="", help="AI 端點"),
            script_io.arg("ai_api_key", default="", help="AI 金鑰"),
            script_io.arg("ai_model", default="", help="AI 模型名稱"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把分析結果寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    # 輸入雙軌：params 有內容就用內容（Qt 走這條），沒內容但有路徑就讀路徑（CI 走這條）。
    description = ai_analysis_gitlab_mr.resolve_text_input(params, "description")

    try:
        hook, owner = device.load_hook("summary")
    except device.DeviceError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    where = "device %s 的 summary.py" % owner
    logger.info("AI 分析：device=%s mode=%s model=%s jira_key=%s",
                owner,
                params["ai_mode_name"] or "(未指定)",
                params["ai_model"] or "(未指定)",
                params["jira_key"] or "(無)")
    script_io.progress("送交 AI 分析…")

    inputs = {
        "description": description,
        "jira_key": params["jira_key"],
        "jira_mode": params["jira_mode"],
        "ai_mode_name": params["ai_mode_name"],
        "ai_api_url": params["ai_api_url"],
        "ai_api_key": params["ai_api_key"],
        "ai_model": params["ai_model"],
        "repo": repo,
        "mr_iid": mr_iid,
        "device": owner,
    }

    try:
        body = hook.analyze(inputs)
    except Exception as exc:                        # noqa: BLE001
        # 鉤子是使用者寫的，任何東西都可能從這裡冒出來。訊息要指得出是哪一支。
        script_io.reply_fail(
            "%s 執行失敗" % where,
            detail="%s: %s" % (exc.__class__.__name__, exc),
            code="DEVICE_HOOK_RUNTIME_ERROR")

    # 版本由入口蓋章，鉤子不填 —— 讓它自己填，遲早有人複製範本時忘了改。
    payload = ai_analysis_gitlab_mr.wrap_analysis(body)

    try:
        ai_analysis_gitlab_mr.validate_analysis(payload, source=where)
    except ai_analysis_gitlab_mr.AnalysisFormatError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], payload)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "summary(%s) repo=%s mr=%s jira_state=%s files=%d"
        % (owner, repo, mr_iid, body.get("jira_state"),
           len(body.get("mrDiff") or {})))

    script_io.reply(
        message="AI 分析完成（device：%s）" % owner,
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data=payload,
    )


if __name__ == "__main__":
    script_io.run(main)
