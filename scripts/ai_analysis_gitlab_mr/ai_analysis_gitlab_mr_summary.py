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
import traceback

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from ai_analysis_gitlab_mr import device
from script_utils import ai_utils
from script_utils import gitlab_utils
from script_utils import jira_utils
from script_utils import json_utils
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


def _fail(debug_dir, message, detail="", code=""):
    """回報失敗，並且在除錯目錄留下同一筆紀錄。

    成功才寫 log 的話，最需要那份紀錄的時候剛好沒有 —— 而「這次為什麼沒成功」正是
    事後唯一想查的事。detail 通常是 traceback，一併寫進去。
    """
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "FAIL [%s] %s%s" % (code or "-", message,
                                       ("\n" + detail) if detail else ""))
    script_io.reply_fail(message, detail=detail, code=code)


def _fail_hook(exc, where, debug_dir):
    """鉤子在第一輪就失敗 —— 這一步失敗。**這個函式一定會結束行程。**

    依型別分派，因為使用者的下一步完全不同。AiError 要排在通用那一條之前 —— 否則一個
    429 會被報成「device X 的 summary.py 執行失敗」，把限流講成腳本寫壞了。
    """
    if isinstance(exc, ai_analysis_gitlab_mr.CredentialError):
        # 設定沒填完，不是鉤子寫壞了。
        _fail(debug_dir, str(exc), exc.detail, exc.code)

    if isinstance(exc, ai_utils.AiError):
        _fail(debug_dir, str(exc),
              "端點：%s\n重試已經做過（見 stderr 的警告）。" % (exc.url or "(未知)"),
              exc.code)

    # 鉤子是使用者寫的，任何東西都可能從這裡冒出來。訊息要指得出是哪一支。
    #
    # detail 放完整的 traceback：鉤子裡出錯最常見的是改壞了 prompt 樣板或解析，而
    # 「哪一行」是唯一真正有用的資訊。一行 "KeyError: xxx" 指不出位置。
    _fail(debug_dir, "%s 執行失敗：%s" % (where, exc),
          traceback.format_exc(), "DEVICE_HOOK_RUNTIME_ERROR")


def _coverage_of(body, diff_info):
    """這一輪的涵蓋範圍。由入口算，不採用鉤子提供的任何數字。"""
    return ai_analysis_gitlab_mr.diff_coverage(
        mr_diff=body.get("mrDiff"),
        files_sent=diff_info["files"],
        files_dropped=diff_info["dropped_files"],
        files_empty=diff_info["empty_files"],
        file_count=diff_info["file_count"],
        truncated=diff_info["truncated"],
        bytes_total=diff_info["bytes_total"],
        bytes_sent=diff_info["bytes_sent"])


def _round_writer(base_write, round_no):
    """第二輪起把除錯檔名加上 `recheckN_` 前綴。

    不加的話，第二輪的 ai_prompt.txt 與 ai_reply_1.txt 會把第一輪的蓋掉 —— 而第一輪
    那一份正是「模型漏了什麼」的證據，也就是開著重查的人唯一想看的東西。

    包在入口這一側，鉤子因此完全不必知道自己被問了第幾次。
    """
    if round_no <= 1:
        return base_write

    def write(name, content):
        return base_write("recheck%d_%s" % (round_no - 1, name), content)
    return write


def _fetch_diff(repo, mr_iid, debug_dir):
    """取得這支 MR 的 unified diff，連同「取得過程中知道的事實」。

    失敗就讓整步失敗：沒有 diff 的「程式碼分析」只能靠描述瞎猜，而它會回報成功。

    取的是 detail 而不只是文字：截斷了幾個檔案、哪些檔案根本沒有內容，這些事實原本
    只留在送給模型的那份文字尾端與一筆除錯警告裡，兩個地方讀報告的人都看不到。而
    「這份分析少看了幾個檔案」正是他唯一想知道的事。回傳值的形狀見
    gitlab_utils.get_mr_diff_detail。
    """
    try:
        server_url, token, verify_ssl = ai_analysis_gitlab_mr.gitlab_credentials()
    except ai_analysis_gitlab_mr.CredentialError as exc:
        _fail(debug_dir, str(exc), exc.detail, exc.code)

    try:
        project_id = gitlab_utils.get_repo_id(server_url, token, repo,
                                              verify_ssl=verify_ssl)
        info = gitlab_utils.get_mr_diff_detail(
            server_url, token, project_id, mr_iid,
            max_bytes=ai_analysis_gitlab_mr.MAX_PROMPT_DIFF_BYTES,
            verify_ssl=verify_ssl)
    except gitlab_utils.GitLabError as exc:
        message, detail, code = ai_analysis_gitlab_mr.describe_gitlab_error(
            exc, repo)
        _fail(debug_dir, message, detail, code)

    _require_diff_content(info, repo, mr_iid, debug_dir)
    return info


def _require_diff_content(info, repo, mr_iid, debug_dir):
    """這支 MR 明明有變更，取回來的差異卻一行內容都沒有時，讓這一步失敗。

    GitLab 的 diff 大小限制比直覺低得多（patch 到門檻的 10%、預設約 20 KB 就收合），
    而被收合的檔案在 API 回來的 diff 欄位是空字串。組出來的差異於是只剩幾行
    `diff --git a/… b/…`，網頁上卻看得到內容。

    **這種時候要失敗，不能照樣送進 AI。** 送出去的話，模型對著幾行檔名給出一份自信的
    分析，而每一步都回報成功 —— 使用者拿到的是一份看起來正常、實際上沒看過任何程式碼的
    報告，還付了錢。這與「沒有 diff 的程式碼分析只能靠描述瞎猜」是同一條理由。

    訊息要指得出成因與**該找誰改**：這是伺服器端的設定，使用者自己改不動。
    """
    if not info["file_count"]:
        return                              # 這支 MR 本來就沒有變更，不是這裡的事
    if "@@" in info["text"]:
        return                              # 至少有一個 hunk，正常

    reasons = []
    if info.get("too_large_files"):
        reasons.append("GitLab 標示 %d 個檔案過大"
                       % len(info["too_large_files"]))
    if info.get("collapsed_files"):
        reasons.append("GitLab 標示 %d 個檔案被收合"
                       % len(info["collapsed_files"]))
    if info.get("overflow"):
        reasons.append("GitLab 表示大小限制影響了這次結果")

    _fail(debug_dir,
          "GitLab 沒有提供任何程式碼差異內容（%s !%s 共 %d 個檔案）"
          % (repo, mr_iid, info["file_count"]),
          "取回的差異只有檔名、沒有任何一段內容%s。\n\n"
          "最常見的成因是伺服器端的 diff 大小限制：單一 patch 到上限的 10%%"
          "（預設 200 KB 的 10%%，約 20 KB）就會被收合，API 取到的 diff 欄位因此是空的，"
          "而網頁上點開仍然看得到。本工具已經改以 access_raw_diffs 重取過一次，仍然沒有"
          "內容。\n\n"
          "請管理者調高 diff 大小限制（Admin → Settings → General → Diff limits），"
          "或改以較小的 Merge Request 進行分析。\n\n"
          "不送進 AI 是刻意的：對著幾行檔名做出的分析會看起來很正常，而它沒有看過任何"
          "程式碼。"
          % ("（%s）" % "、".join(reasons) if reasons else ""),
          "MR_DIFF_NO_CONTENT")


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
            script_io.arg("mr_type", default="",
                          help="上一步解出的種類；決定用哪一份 summary 鉤子，"
                               "空字串代表用該 device 的通用版"),
            script_io.arg("ai_mode_name", default="", help="AI 模式名稱"),
            script_io.arg("ai_api_url", default="", help="AI 端點"),
            script_io.arg("ai_api_key", default="", help="AI 金鑰"),
            script_io.arg("ai_model", default="", help="AI 模型名稱"),
            script_io.arg("ai_timeout", default="",
                          help="問 AI 的逾時秒數；空字串代表用預設值"),
            script_io.arg("ai_retries", default="",
                          help="連線失敗時的重試次數；空字串代表用預設值"),
            script_io.arg("ai_reask", default="",
                          help="回覆格式不符時的重問次數；空字串代表用預設值"),
            script_io.arg("ai_recheck", default="",
                          help="送進去的檔案沒被全部回報時的重問次數；"
                               "空字串代表用預設值（0，關閉）"),
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

    # 種類決定用哪一份 summary。上一步已經正規化過（去空白、轉小寫、檢查形狀），
    # 這裡再走一次是為了讓命令列直接執行時也一致 —— 那條路徑沒有經過上一步。
    mr_type = params["mr_type"]

    try:
        hook, owner = device.load_hook("summary", mr_type=mr_type)
        mr_type = device.normalize_type(mr_type)
    except device.DeviceError as exc:
        _fail(params["debug_dir"], str(exc), exc.detail, exc.code)

    # 訊息要指得出種類：改壞的往往是某個種類專屬的那一份，而不是通用的那一份。
    where = "device %s 的 %ssummary.py" % (owner,
                                           ("%s/" % mr_type) if mr_type else "")
    logger.info("AI 分析：device=%s type=%s mode=%s model=%s jira_key=%s",
                owner,
                mr_type or "(無)",
                params["ai_mode_name"] or "(未指定)",
                params["ai_model"] or "(未指定)",
                params["jira_key"] or "(無)")
    # 四個等待相關的設定在**取 diff 之前**就驗。打錯的話不該讓使用者先等完一趟 GitLab、
    # 再看到一個本來第一秒就能說的設定錯誤。
    #
    # 四個一起決定最壞情況的等待時間（逾時 ×(重試+1)×(重問+1)×(重查+1) ＋退避），所以
    # 也一起記進 log —— 事後問「為什麼等了十六分鐘」時，這一行就是答案。
    try:
        ai_seconds = ai_analysis_gitlab_mr.ai_timeout(params)
        ai_retries = ai_analysis_gitlab_mr.ai_retries(params)
        ai_reask = ai_analysis_gitlab_mr.ai_reask(params)
        ai_recheck = ai_analysis_gitlab_mr.ai_recheck(params)
    except ai_analysis_gitlab_mr.CredentialError as exc:
        _fail(params["debug_dir"], str(exc), exc.detail, exc.code)

    logger.info("AI 等待設定：逾時 %s 秒、重試 %d 次、重問 %d 次、重查 %d 次"
                "（最壞情況約 %d 秒，不含退避）",
                ai_seconds, ai_retries, ai_reask, ai_recheck,
                int(ai_seconds * (ai_retries + 1) * (ai_reask + 1)
                    * (ai_recheck + 1)))

    # 素材在呼叫鉤子**之前**備好。連線失敗要在這裡爆，而不是從使用者寫的鉤子裡
    # 冒出一個 GitLabError —— 那時訊息會被包成「device X 的 summary.py 執行失敗」，
    # 把一個連線問題講成腳本寫壞了。
    script_io.progress("取得程式碼差異…")
    diff_info = _fetch_diff(repo, mr_iid, params["debug_dir"])
    mr_diff = diff_info["text"]

    logger.info("素材：diff %d 字元，完整送出 %d / %d 個檔案%s",
                len(mr_diff), len(diff_info["files"]), diff_info["file_count"],
                "（已截斷）" if diff_info["truncated"] else "")

    # 這一行描述的是**當下**：素材備好了，正要把它交給鉤子。
    #
    # 它曾經寫成「送交 AI 分析…」，而那是錯的 —— 報這一行的時候 prompt 還不存在，鉤子
    # 接下來可能先去取 JIRA、也可能根本不呼叫 AI（端點沒設定時走替代內容）。真正送出去
    # 的那一行由鉤子自己報，因為只有它知道什麼時候送出去。
    #
    # 但這一行不能省：鉤子是使用者寫的，不保證報任何進度。什麼都不報的話，一支沉默的
    # 鉤子會讓「取得程式碼差異…」留在畫面上直到整步結束。
    script_io.progress("準備 AI 分析…")

    inputs = {
        "description": description,
        "mr_diff": mr_diff,
        "fetch_jira": _fetch_jira,
        "jira_key": params["jira_key"],
        "jira_mode": params["jira_mode"],

        # 唯讀轉送：讓鉤子知道自己是被哪一個種類選中的。通用的那一份可以據此微調，
        # 而種類專屬的那一份通常不需要看它。
        "mr_type": mr_type,
        "ai_mode_name": params["ai_mode_name"],
        "ai_api_url": params["ai_api_url"],
        "ai_api_key": params["ai_api_key"],
        "ai_model": params["ai_model"],

        # 已經正規化過，鉤子再呼叫一次那三支也只是原樣拿回去。
        #
        # **ai_recheck 刻意不在這裡。** 它是入口自己的迴圈次數（見底下那一段），鉤子
        # 不需要也不該看到它 —— 傳進去就等於邀請 device 作者自己再實作一次同樣的迴圈，
        # 而那會讓「回報得夠不夠」重新變成被檢查的一方自己說。
        "ai_timeout": ai_seconds,
        "ai_retries": ai_retries,
        "ai_reask": ai_reask,
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

    # 涵蓋層的重問（次數見 contract.ai_recheck，預設 0 = 關閉）。
    #
    # **迴圈在入口，不在鉤子裡。** 理由與涵蓋範圍由入口蓋章完全相同：判斷「回報得夠不
    # 夠」要拿鉤子的輸出對照入口手上的那份差異，而讓被檢查的一方決定自己要不要重做，
    # 這個機制就等於不存在。放在這裡同時讓每一個 device 都免費得到這個行為，不必各自
    # 實作一次 —— 鉤子完全不知道自己被問了第幾次。
    #
    # 只看 missing 那一類：dropped（太大沒送進去）與 empty（差異本身是空的）再問幾次
    # 都不會變，unknown（回了一個不存在的路徑）是另一種錯。把它們算進來就會為了永遠
    # 補不回來的東西反覆付錢。
    #
    # 已知代價：每一輪都重新呼叫 hook.analyze()，所以有 JIRA issue 的那幾次會多打一趟
    # JIRA。要省掉它得把鉤子拆成「準備」與「問」兩段，而那會改掉所有 device 的介面 ——
    # 對一個預設關閉的功能不值得。
    best = None          # (missing 數, 輪次, body, coverage)
    base_write = inputs["debug_write"]

    for round_no in range(1, ai_recheck + 2):
        if round_no > 1:
            # 這又是一段分鐘級的等待，要有屬於它自己的進度文字 —— 不報的話畫面上
            # 留著的會是上一段**已經做完**的工作。
            script_io.progress("AI 漏了 %d 個檔案，重新分析（第 %d 次）…"
                               % (best[0], round_no - 1))
            logger.info("重查第 %d 次：上一輪有 %d 個檔案沒被回報",
                        round_no - 1, best[0])

        # 第二輪起把除錯檔名加上前綴。覆寫的話，ai_reply_1.txt 會被下一輪蓋掉 ——
        # 而「模型第一次漏了什麼」正是這個功能存在的理由，那份檔案不能丟。
        round_inputs = dict(inputs,
                            debug_write=_round_writer(base_write, round_no))

        try:
            body = hook.analyze(round_inputs)
        except Exception as exc:                    # noqa: BLE001 - 分派見 _fail_hook
            if round_no == 1:
                # 第一輪失敗就是這一步失敗，行為與加入重查之前完全相同。
                _fail_hook(exc, where, params["debug_dir"])     # 必定結束行程
            # 重查那幾輪失敗**不該**把一份已經拿到的分析變成失敗 —— 那是把額外的
            # 嘗試變成新的失敗來源，而使用者沒有因此得到任何東西。
            logger.warn("重查第 %d 次失敗（%s），沿用第 %d 輪的結果：%s",
                        round_no - 1, exc.__class__.__name__, best[1], exc)
            break

        # 版本與種類都由入口蓋章，鉤子不填 —— 讓它自己填，遲早有人複製範本時忘了改。
        #
        # 種類覆寫而不是「沒有才補」：鉤子若回了一個與實際解析結果不同的種類，那份產物會
        # 讓步驟 5 挑到另一份版面，而兩步的說法互相矛盾卻都回報成功。
        body["mr_type"] = mr_type

        coverage = _coverage_of(body, diff_info)
        missing = coverage["missing"]["count"]

        # 取**最好的那一輪**而不是最後一輪：原樣重問拿到的是另一個樣本，它可能更差，
        # 而把一份較完整的分析換成較殘缺的那一份，比不重問還糟。平手時留早的那一輪。
        if best is None or missing < best[0]:
            best = (missing, round_no, body, coverage)

        if missing == 0:
            break

    missing, round_used, body, coverage = best
    if round_used > 1 or missing:
        logger.info("採用第 %d 輪的分析（共 %d 輪），仍有 %d 個檔案沒被回報",
                    round_used, round_no, missing)

    # 涵蓋範圍由入口蓋章，而且理由比種類更強：這份數字是用來檢查**鉤子回報了多少**的。
    # 讓被檢查的一方提供它，這個機制就等於不存在 —— 一支宣稱自己涵蓋全部的鉤子不會有
    # 任何一步發現它說謊。入口同時握有差異與鉤子的回傳，兩樣都在手上。
    body["coverage"] = coverage

    payload = ai_analysis_gitlab_mr.wrap_analysis(body)

    try:
        ai_analysis_gitlab_mr.validate_analysis(payload, source=where)
    except ai_analysis_gitlab_mr.AnalysisFormatError as exc:
        # 鉤子回了一個形狀不對的結構。把它整份寫進除錯目錄 —— 光看訊息說「某個欄位
        # 型別不對」，還是得看到實際長什麼樣才改得動。
        ai_analysis_gitlab_mr.write_debug_file(
            params["debug_dir"], "bad_analysis.json",
            json_utils.dump(payload))
        _fail(params["debug_dir"], str(exc), exc.detail, exc.code)

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], payload)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        # files 是「提到的檔案數／其中有發現的檔案數」。兩個都記，因為空的發現清單
        # 現在留在 mrDiff 裡（見 default/summary.py 的 parse_reply）—— 只記一個的話，
        # 「模型提了 20 個檔案但只有 2 個有話說」與「模型只提了 2 個」在 log 上長得
        # 一模一樣，而那正是調 prompt 時要分辨的事。
        "summary(%s) repo=%s mr=%s type=%r jira_state=%s files=%d/%d "
        "coverage=%d/%d/%d dropped=%d empty=%d missing=%d unknown=%d"
        % (owner, repo, mr_iid, mr_type, body.get("jira_state"),
           len(body.get("mrDiff") or {}),
           sum(1 for one in (body.get("mrDiff") or {}).values() if one),
           body["coverage"]["files_reported"],
           body["coverage"]["files_sent"],
           body["coverage"]["files_changed"],
           body["coverage"]["dropped"]["count"],
           body["coverage"]["empty"]["count"],
           body["coverage"]["missing"]["count"],
           body["coverage"]["unknown"]["count"]))

    script_io.reply(
        message="AI 分析完成（device：%s%s）"
                % (owner, ("，type：%s" % mr_type) if mr_type else ""),
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data=payload,
    )


if __name__ == "__main__":
    script_io.run(main)
