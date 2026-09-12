#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 1/5：取得 Merge Request 描述。

**本輪為 stub**：不連線 GitLab，回傳寫死的假描述。對外契約（stdout 只有結果
JSON、進度走 stderr、結束碼、必填檢查、兩種投遞方式）則完全是真的。

    python ai_analysis_gitlab_mr_description.py --help
    python ai_analysis_gitlab_mr_description.py --dump-config > run.json
    python ai_analysis_gitlab_mr_description.py --request run.json
"""

import os
import sys

# 入口腳本放在 scripts/<功能>/ 底下，而 Python 只把「腳本所在目錄」放進
# sys.path —— 少了下面這一行，命令列直接執行時 script_io 與 script_utils
# 都匯不到。Qt 會注入指向 scripts/ 的 PYTHONPATH，但那不能當成前提。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "mr_description"
DESCRIPTION      = "取得指定 Merge Request 的描述（本輪為 stub）"


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
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把描述寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    logger.info("取得 %s 的 Merge Request !%s 描述", repo, mr_iid)
    script_io.progress("取得 Merge Request 描述…")

    # ---- stub：真實實作會在這裡呼叫 gitlab_utils 取回 MR 的描述 ----
    description = "\n".join([
        "# Merge Request !%s" % mr_iid,
        "",
        "專案：`%s`" % repo,
        "",
        "## 變更摘要",
        "",
        "- 修正讀取路徑在多執行緒下的競態",
        "- 調整重試次數的上限",
        "",
        "> 這是 stub 產生的假描述，尚未連線至 GitLab。",
    ])
    # ----------------------------------------------------------------

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], description)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "description repo=%s mr=%s len=%d" % (repo, mr_iid, len(description)))

    script_io.reply(
        message="已取得 Merge Request !%s 的描述" % mr_iid,
        detail="專案：%s" % repo,
        data={"description": description},
    )


if __name__ == "__main__":
    script_io.run(main)
