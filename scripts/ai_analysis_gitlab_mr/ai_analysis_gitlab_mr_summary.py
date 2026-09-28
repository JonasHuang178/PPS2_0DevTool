#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 3/5：AI 分析。

這一步的業務運算全部交給 device 的 summary 鉤子 —— 要問 AI 什麼、怎麼解析、組出什麼
分析內容，由該 device 決定。入口負責信封、參數、**把素材備好**、驗證與落檔。

「備好素材」指的是 MR 的 diff 與 JIRA issue 的內容：兩者都要連線、要憑證、要處理錯誤，
而寫 prompt 的人不該為了改一句話去面對 HTTP。鉤子收到的是現成的文字（見 inputs 的
mr_diff 與 jira_issue），它只決定怎麼把那些素材排進 prompt。

**鉤子回傳的結構在收到的當下就驗證。** 不驗的話，錯誤會在兩步之後的渲染才爆，而訊息
指的是合併那一步、不是寫壞的那個 device。

    python ai_analysis_gitlab_mr_summary.py --help
    python ai_analysis_gitlab_mr_summary.py --dump-config > run.json
    python ai_analysis_gitlab_mr_summary.py --request run.json

    PPS_DEVICE            sd / ssd / ...（未設定時用 default）
    GITLAB_SERVER_URL     取 diff 用，必要
    GITLAB_ACCESS_TOKEN   取 diff 用，必要
    GITLAB_VERIFY_SSL     未設定時視為不驗證
    AI_VERIFY_SSL         未設定時**不驗證** AI 服務的 TLS 憑證
    JIRA_SERVER_URL       取 issue 內容用，缺了就不放那一段
    JIRA_ACCESS_TOKEN     同上
"""

import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from ai_analysis_gitlab_mr import device
from script_utils import ai_utils
from script_utils import gitlab_utils
from script_utils import jira_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "ai_summary"
DESCRIPTION      = "以 AI 分析 Merge Request（內容由 device 的鉤子決定）"

# 從 JIRA 取哪些欄位。只取組 prompt 用得到的 —— 整張 issue 回來會有幾十個欄位，
# 絕大多數是工作流程的內部狀態，塞進 prompt 只是浪費 context。
_JIRA_FIELDS = ("summary", "description", "status", "issuetype")

# issue 描述送進 prompt 的長度上限。與 diff 的上限（contract.MAX_PROMPT_DIFF_BYTES）
# 是同一個道理，只是這一段通常小得多，所以另訂一個比較緊的值。
_JIRA_DESCRIPTION_LIMIT = 8000


def _fetch_diff(repo, mr_iid):
    """取得這支 MR 的 unified diff。

    失敗就讓整步失敗：沒有 diff 的「程式碼分析」只能靠描述瞎猜，而它會回報成功。
    """
    try:
        server_url, token, verify_ssl = ai_analysis_gitlab_mr.gitlab_credentials()
    except ai_analysis_gitlab_mr.CredentialError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    try:
        project_id = gitlab_utils.get_repo_id(server_url, token, repo,
                                              verify_ssl=verify_ssl)
        return gitlab_utils.get_mr_plain_diff(
            server_url, token, project_id, mr_iid,
            max_bytes=ai_analysis_gitlab_mr.MAX_PROMPT_DIFF_BYTES,
            verify_ssl=verify_ssl)
    except gitlab_utils.GitLabError as exc:
        message, detail, code = ai_analysis_gitlab_mr.describe_gitlab_error(
            exc, repo)
        script_io.reply_fail(message, detail=detail, code=code)


def _fetch_jira(jira_key):
    """取得 JIRA issue 的內容，回傳 dict；取不到時回 None。

    **這一支是交給鉤子按需呼叫的，不是入口自己先跑。** 「這個 key 有沒有效」是 device
    的政策（見各 device 的 summary.py），而入口不認得那個政策 —— 先抓的話，`[WIP]`、
    `[Draft]` 這種從標題方括號抽出來的東西每次都會去打一次 JIRA，換回一個 404。

    交出去的是函式而不是 HTTP 的零件：憑證、錯誤分類、截斷都留在這裡，鉤子拿到的仍然
    只是「呼叫一下就有內容」的能力，改 prompt 的人不必面對這些。

    **取不到不讓流程失敗。** JIRA 在這裡是補充資料，查不到的原因多半無害。為了一張查
    不到的 issue 讓整份分析做不出來，代價與收益不成比例 —— 記一筆警告，prompt 就少
    那一段。
    """
    jira_key = (jira_key or "").strip()
    if not jira_key:
        return None

    script_io.progress("取得 JIRA %s…" % jira_key)

    try:
        base_url, token = ai_analysis_gitlab_mr.jira_credentials()
    except ai_analysis_gitlab_mr.CredentialError as exc:
        logger.warn("未設定 JIRA 連線資訊，prompt 不放 issue 內容：%s", exc)
        return None

    try:
        issue = jira_utils.get_issue_info(base_url, token, jira_key,
                                          fields=_JIRA_FIELDS)
    except jira_utils.JiraError as exc:
        logger.warn("取不到 JIRA issue %s，prompt 不放那一段：%s", jira_key, exc)
        return None

    fields = (issue or {}).get("fields") or {}
    status = fields.get("status") or {}
    issue_type = fields.get("issuetype") or {}

    return {
        "key": (issue or {}).get("key") or jira_key,
        "summary": fields.get("summary") or "",
        "description": _clip(fields.get("description") or ""),
        "status": status.get("name") or "",
        "type": issue_type.get("name") or "",
        "url": ai_analysis_gitlab_mr.jira_url(jira_key),
    }


def _clip(text):
    """把過長的 issue 描述截短，並在結尾註明。

    JIRA 的描述沒有長度上限，實務上有人把整份規格書貼進去。原樣送進 prompt 會把
    diff 擠出 context window —— 而使用者要的是程式碼的分析，不是規格書的讀後感。

    截斷一定要留下記號：沒有記號的話，模型會對著半句話往下推論，而讀報告的人看不出
    它只看到一半。
    """
    if len(text) <= _JIRA_DESCRIPTION_LIMIT:
        return text
    logger.warn("JIRA 描述有 %d 字元，截斷為 %d",
                len(text), _JIRA_DESCRIPTION_LIMIT)
    return text[:_JIRA_DESCRIPTION_LIMIT] + "\n…（描述已截斷）"


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
    # 素材在呼叫鉤子**之前**備好。連線失敗要在這裡爆，而不是從使用者寫的鉤子裡
    # 冒出一個 GitLabError —— 那時訊息會被包成「device X 的 summary.py 執行失敗」，
    # 把一個連線問題講成腳本寫壞了。
    script_io.progress("取得程式碼差異…")
    mr_diff = _fetch_diff(repo, mr_iid)

    logger.info("素材：diff %d 字元", len(mr_diff))

    script_io.progress("送交 AI 分析…")

    inputs = {
        "description": description,
        "mr_diff": mr_diff,
        "fetch_jira": _fetch_jira,
        "jira_key": params["jira_key"],
        "jira_mode": params["jira_mode"],
        "ai_mode_name": params["ai_mode_name"],
        "ai_api_url": params["ai_api_url"],
        "ai_api_key": params["ai_api_key"],
        "ai_model": params["ai_model"],
        "repo": repo,
        "mr_iid": mr_iid,
        "device": owner,

        # 回報進度用。AI 的呼叫是分鐘級的，而那個對話框是固定尺寸、只有一行字 ——
        # 一個兩分鐘沒動靜的視窗看起來就是當掉了。
        #
        # 傳函式進來而不是讓鉤子自己 import script_io：鉤子是使用者寫的，它拿到的
        # 應該是一個「報進度」的能力，而不是一個可以自行結束行程的模組。
        "progress": script_io.progress,

        # 寫一份除錯檔的能力。除錯目錄沒設定時它什麼都不做，所以鉤子可以無條件
        # 呼叫，不必自己判斷除錯有沒有開。
        #
        # prompt 與 AI 的原始回覆是調 prompt 時唯一真正需要看的兩份東西，而它們
        # 都不進 log（prompt 含原始碼，回覆動輒幾萬字元）。
        "debug_write": ai_analysis_gitlab_mr.debug_writer(params["debug_dir"]),
    }

    try:
        body = hook.analyze(inputs)
    except ai_analysis_gitlab_mr.CredentialError as exc:
        # 設定沒填完，不是鉤子寫壞了。
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)
    except ai_utils.AiError as exc:
        # AI 服務那一端的問題。這一條要在通用的 except 之前 —— 否則一個 429 會被
        # 報成「device X 的 summary.py 執行失敗」，把限流講成腳本寫壞了，而使用者
        # 的下一步（稍後再試 vs 去改腳本）完全不同。
        script_io.reply_fail(
            str(exc),
            detail="端點：%s\n重試已經做過（見 stderr 的警告）。"
                   % (exc.url or "(未知)"),
            code=exc.code)
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
