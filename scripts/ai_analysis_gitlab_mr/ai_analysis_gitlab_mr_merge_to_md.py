#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 5/5：合併為 markdown。

把前面各步落下的檔案合併成一份報告。**輸入一律是檔案路徑**，這一步不接收內容
本身 —— 它的工作就是「把這幾份檔案接起來」，命令列直接呼叫時的用法與 Qt 完全
相同。

    python ai_analysis_gitlab_mr_merge_to_md.py --help
    python ai_analysis_gitlab_mr_merge_to_md.py --dump-config > run.json
    python ai_analysis_gitlab_mr_merge_to_md.py --request run.json

每一個輸入路徑都可以是 null（或省略），代表那一段沒有內容、整段略過。但**路徑
給了就必須存在** —— 指名一個不存在的檔案是上一步沒寫成功，靜默略過只會產出一份
看起來正常、實際上少一段的報告。

完整的 markdown 一律放進 data，呼叫端不必開檔就能顯示結果；給了 out_path 才
**額外**寫一份檔案。
"""

import datetime
import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import file_utils
from script_utils import json_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "merge_to_md"
DESCRIPTION      = "把前面各步落下的檔案合併成一份 markdown 報告"


def _is_given(path):
    """路徑是否真的給了。

    null、省略、空字串、只有空白都算沒給 —— 呼叫端可能送 null，也可能送空字串
    （script_io 對缺漏的參數回填預設值，而預設值是空字串），兩種都要收。
    """
    return isinstance(path, str) and path.strip() != ""


def _read_required(path, what):
    """讀出指定路徑的檔案。路徑給了就必須存在。

    不存在時回 FAIL 而不是略過：指名一個不存在的檔案代表上一步沒有寫成功，
    略過只會產出一份看起來正常、實際上少一段的報告，而那份報告會被當成完整的
    交出去。
    """
    if not os.path.isfile(path):
        script_io.reply_fail(
            "找不到%s：%s" % (what, path),
            detail="路徑給了就必須存在。若這一段本來就沒有內容，"
                   "請把該參數傳成 null 而不是指向一個不存在的檔案。",
            code="MERGE_INPUT_NOT_FOUND")

    return file_utils.read_file(path)


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[
            script_io.arg("ori_md_file_path", default="",
                          help="MR 描述的 markdown 檔；null 表示沒有這一段"),
            script_io.arg("mr_summary_json_file_path", default="",
                          help="AI 分析結果的 JSON 檔（取其中的 summary 欄位）；"
                               "null 表示沒有這一段"),
            script_io.arg("code_review_md_file_path", default="",
                          help="程式碼審閱報告的 markdown 檔；null 表示沒有這一段"),
            script_io.arg("out_path", default="",
                          help="額外把報告寫到這個檔案；null 表示不落檔"),

            # 底下兩個只影響報告標題，不是內容來源。命令列只想合併檔案時可以不給。
            script_io.arg("repo", default="",
                          help="專案，namespace/project 形式；只用於報告標題"),
            script_io.arg("mr_iid", default="",
                          help="Merge Request 編號；只用於報告標題"),

            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    script_io.progress("合併為 markdown…")

    # --- 讀入三段內容 ---
    description = ""
    if _is_given(params["ori_md_file_path"]):
        description = _read_required(params["ori_md_file_path"], "MR 描述檔")

    summary = ""
    if _is_given(params["mr_summary_json_file_path"]):
        path = params["mr_summary_json_file_path"]
        raw = _read_required(path, "AI 分析結果檔")
        try:
            payload = json_utils.load_data(raw)
        except ValueError as exc:
            script_io.reply_fail(
                "AI 分析結果檔不是合法的 JSON：%s" % path,
                detail=str(exc), code="MERGE_SUMMARY_NOT_JSON")
        # 這個檔案是一個物件，markdown 在 summary 欄位裡。不是物件（例如整份就是
        # 一段文字）時原樣採用 —— 對合併而言「能接上去的文字」才是重點。
        summary = (payload.get("summary") or "") if isinstance(payload, dict) \
            else str(payload)

    code_review = ""
    if _is_given(params["code_review_md_file_path"]):
        code_review = _read_required(params["code_review_md_file_path"],
                                     "程式碼審閱報告檔")

    if not (description or summary or code_review):
        # 三段全空代表呼叫端什麼都沒給，或前面幾步全部沒有產出。產一份只有標題的
        # 報告等於把問題往下游丟。
        script_io.reply_fail(
            "沒有任何可合併的內容",
            detail="ori_md_file_path、mr_summary_json_file_path 與 "
                   "code_review_md_file_path 都沒有給，或內容都是空的。",
            code="MERGE_NOTHING_TO_DO")

    logger.info("合併報告：描述 %d、分析 %d、審閱 %d 字元",
                len(description), len(summary), len(code_review))

    # --- 組報告 ---
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    heading = "# AI Analysis"
    if repo and mr_iid:
        heading = "# AI Analysis — %s !%s" % (repo, mr_iid)
    elif repo:
        heading = "# AI Analysis — %s" % repo

    sections = [heading, "", "產生時間：%s" % stamp]

    # 空的段落整段不放 —— 一個只有分隔線沒有內容的區塊比沒有還糟。
    for part in (description, summary, code_review):
        if part.strip():
            sections += ["", "---", "", part.strip()]

    markdown = "\n".join(sections) + "\n"

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], markdown)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "merge_to_md repo=%s mr=%s len=%d" % (repo, mr_iid, len(markdown)))

    script_io.reply(
        message="報告已產生（%d 字元）" % len(markdown),
        detail="專案：%s\nMerge Request：!%s" % (repo or "(未指定)",
                                                mr_iid or "(未指定)"),
        data={"markdown": markdown},
    )


if __name__ == "__main__":
    script_io.run(main)
