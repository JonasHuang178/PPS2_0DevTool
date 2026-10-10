#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 4/5：取得程式碼審閱報告。

來源是**別人的文件**：工程師用 AI code review 工具產出一份 markdown，以附件掛在該
Merge Request 標題所指的 JIRA 議題上。這一步取回最新的那一份，交給該 device 的
parse_code_review 鉤子擷取與判定，結果交給步驟 5。

**取得在這裡，看懂在鉤子裡。** 查附件、挑最新那一份、擋大小上限、下載、解碼都要 JIRA
權杖與統一的政策，所以留在入口；而「那份文件長什麼樣、怎麼算通過」因產品線而異，所以
在 device。鉤子失敗不會中斷流程（見 _parse_with_hook）。

報告裡只放總表，全文靠那個連結回去看 —— 所以這一步交出的結構除了表格，還帶著附件的
檔名、上傳時間、上傳者與網址。那四個值只有這一步拿得到（步驟 5 收到的只是一個檔案
路徑），因此它們必須進到產物裡。

這一步**永遠會被執行**，呼叫端不跳過任何步驟 —— 分支若寫在呼叫端，持續整合那一側就
成為第二份編排實作，兩份必然漂移。「要不要真的去抓」由 jira_key 與 jira_state 決定，
**不另設布林開關**：那樣會出現「開關為真但沒有 key」這種自相矛盾的狀態。

失敗分三類，只有第一類會結束整條流程：

    部署缺漏        不必發請求就知道（缺關鍵字、缺 JIRA 端點或權杖）  -> FAIL
    外部服務的回答  發了請求才知道（連不上、401、404、下載失敗）      -> PASS，訊息進結構
    別人文件不合約定 取得內容才知道（找不到那節、沒表格、解碼失敗）    -> PASS，訊息進結構

後兩類不結束流程，因為這一步跑在 AI 分析**之後** —— 讓它失敗會把一份已經完成、已經
付費的分析整份丟掉。而那時報告裡日期／作者／連結三行照樣印得出來，讀者點連結就能自己
看全文。

    python ai_analysis_gitlab_mr_code_review.py --help
    python ai_analysis_gitlab_mr_code_review.py --dump-config > run.json
    python ai_analysis_gitlab_mr_code_review.py --request run.json

憑證與關鍵字走環境變數，不放進 request 檔案 —— 那個檔案會留在 CI runner 的工作目錄：

    JIRA_SERVER_URL                          https://jira.example.com
    JIRA_ACCESS_TOKEN                        個人存取權杖
    PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH   附件檔名的前綴，例如 CodeReview_
"""

import datetime
import os
import re
import shutil
import sys
import tempfile
import traceback

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from ai_analysis_gitlab_mr import device
from script_utils import jira_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "fetch_code_review"
DESCRIPTION      = "自 JIRA 議題的附件取得程式碼審閱報告的風險評估總表"

# 下載回來的原始附件存成這個名字。
#
# **固定，不取自附件本身的檔名。** 那是上傳者打的字，拿它組路徑與規格禁止「device 名稱
# 用來組成檔案路徑」是同一類風險。順帶也解決 JIRA 允許同名多筆附件的覆蓋問題。
SOURCE_ARTIFACT_NAME = "04_code_review_src.md"

# 只收這個副檔名，**寫死不可配置**。
#
# 這一步的產出要直接接進報告的一個段落，「必須是 markdown」是它的契約而非使用者偏好。
# 可配置的話有人會指到 .docx 或 .zip，於是二進位內容被貼進報告，而每一步都回報成功。
SOURCE_SUFFIX = ".md"

# JIRA 的 created 長這樣：2026-09-10T09:29:00.000+0800
#
# 自己解析而不用 datetime.fromisoformat()：後者要到 Python 3.11 才吃得下沒有冒號的
# 時區偏移（+0800），而這批腳本要能在較舊的直譯器上跑。
_CREATED_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
    r"(?:\.(\d+))?\s*(Z|[+-]\d{2}:?\d{2})?$")

# 解析不出上傳時間時用的排序值。比任何真實時間都早，所以那種附件只會在「全部都解析
# 不出來」時才被選中。
_OLDEST = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


class CodeReviewUnavailable(Exception):
    """取不到總表，但**不該結束流程**。

    外部服務的回答與別人文件的內容不合約定都走這一個 —— 兩者的共同點是「不是這次部署
    的錯誤」，而處理方式相同：訊息寫進結構、報告顯示那一段、流程繼續。

    部署缺漏不走這裡，它走 CredentialError 並變成 reply_fail。

    meta 帶著已經知道的附件資訊（檔名、上傳時間、作者、網址）。**失敗時那四項仍要進
    報告** —— 那時連結的價值最高，讀者點進去就能自己看全文，而那正是這一段設計的目的。
    已經挑到附件之前就失敗（例如連不上 JIRA）時它是空的。
    """

    def __init__(self, message, meta=None):
        super(CodeReviewUnavailable, self).__init__(message)
        self.meta = dict(meta or {})


def _parse_created(value):
    """把 JIRA 的 created 解析成可比較的 datetime；解析不出來回 _OLDEST。

    **必須真的解析，不能拿字串比字典序** —— 這個值帶時區，而 `2026-09-10T09:00+0800`
    的實際時間早於 `2026-09-10T08:00+0000`，字典序會給出相反的答案。
    """
    match = _CREATED_RE.match((value or "").strip())
    if not match:
        logger.debug("解析不出附件的上傳時間 %r，排序時視為最舊", value)
        return _OLDEST

    year, month, day, hour, minute, second, fraction, offset = match.groups()
    microsecond = int((fraction or "0").ljust(6, "0")[:6])

    if offset in (None, "Z"):
        tzinfo = datetime.timezone.utc
    else:
        sign = -1 if offset[0] == "-" else 1
        digits = offset[1:].replace(":", "")
        tzinfo = datetime.timezone(
            sign * datetime.timedelta(hours=int(digits[:2]),
                                      minutes=int(digits[2:4])))

    return datetime.datetime(int(year), int(month), int(day), int(hour),
                             int(minute), int(second), microsecond, tzinfo)


def _attachment_id(item):
    """附件的識別碼，取不到數字時回 -1。上傳時間相同時用它決定誰比較新。"""
    try:
        return int(str(item.get("id", "")).strip())
    except (TypeError, ValueError):
        return -1


def _matches(name, keyword):
    """檔名是否符合條件：以關鍵字**開頭**、副檔名為 .md。

    比對**區分大小寫，副檔名也一樣**。關鍵字是部署者刻意填進設定檔的值，與使用者主動
    輸入的過濾文字同一類（而排序那種被動看到的結果才不分大小寫）。副檔名不另開特例，
    是為了讓「檔名比對區分大小寫」這句話沒有例外 —— 一條有例外的規則，使用者得先知道
    例外在哪裡才預測得出結果。

    前綴而非子字串：子字串比對會讓 Old_CodeReview_backup.md 這類檔案參與競爭，而它
    多半正是不該被選中的那一份。
    """
    return name.startswith(keyword) and name.endswith(SOURCE_SUFFIX)


def _pick_attachment(attachments, keyword):
    """挑出要用的那一個附件；沒有符合的回 None。

    符合條件者有多筆時取**上傳時間最新**的一筆，同時間以識別碼較大者為新 —— 否則順序
    取決於 JIRA 回傳的先後，而那沒有任何保證。
    """
    candidates = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        name = ai_analysis_gitlab_mr.plain(item.get("filename"))
        if name and _matches(name, keyword):
            candidates.append(item)

    if not candidates:
        return None

    candidates.sort(key=lambda one: (_parse_created(one.get("created")),
                                     _attachment_id(one)))
    return candidates[-1]


def _describe_attachments(attachments, keyword, picked):
    """給除錯日誌的一行：看到哪些附件、依關鍵字篩掉哪些、最後挑了誰。

    不另存一個候選清單檔案，但這一行**不能省**：「為什麼挑到這一個」是這一步唯一會被
    質疑的判斷，而挑完之後那份清單就消失了。它同時是「檔名大小寫打錯」唯一的診斷路徑
    —— 那種情況下報告裡完全沒有這一段，也沒有任何訊息。
    """
    seen = []
    for item in attachments:
        if not isinstance(item, dict):
            continue
        name = ai_analysis_gitlab_mr.plain(item.get("filename"))
        seen.append("%s%s" % (name, "" if _matches(name, keyword) else "（篩掉）"))

    return ("code_review 附件 keyword=%r 共 %d 個：%s -> 選用 %s"
            % (keyword, len(seen), "、".join(seen) or "(無)",
               ai_analysis_gitlab_mr.plain((picked or {}).get("filename"))
               or "(無)"))


def _jira_reason(exc, key):
    """把 JiraError 轉成一句可讀的原因，供寫進結構的 error 欄位。

    分類與其他連線 JIRA / GitLab 的腳本一致：使用者的下一步不同，訊息就該不同。但這裡
    一律回**一句話**而不是 (message, detail, code) 三件組 —— 它要放進報告裡給人讀，
    不是拿去 reply_fail。
    """
    status = getattr(exc, "status_code", None)

    if status in (401, 403):
        return ("JIRA 拒絕了這次請求（%s），請檢查環境變數 JIRA_ACCESS_TOKEN 的權杖"
                "是否過期、或對 %s 是否有讀取權限" % (status, key))

    if status == 404:
        return ("JIRA 上找不到議題 %s —— 請確認 Merge Request 標題裡的編號正確" % key)

    lowered = str(exc).lower()
    if status is None and ("ssl" in lowered or "certificate" in lowered):
        return ("連線 JIRA 時 TLS 憑證驗證失敗：%s（可把受信任的 CA 憑證指給環境變數 "
                "REQUESTS_CA_BUNDLE）" % exc)

    return "無法向 JIRA 取得議題 %s 的附件：%s" % (key, exc)


def _read_attachment(item, token, out_path):
    """下載附件並讀出文字。回傳內容字串。

    不收 base_url：下載網址是附件自己帶的 item["content"]（JIRA 回的是絕對網址），
    所以這一支不需要知道伺服器在哪裡。

    存檔路徑固定為 <out_path 所在目錄>/04_code_review_src.md —— 勾選除錯分析檔時工作
    目錄**就是**除錯目錄，所以原始附件自動留在那裡；未勾選時工作目錄是流程結束後會被
    整個移除的暫存目錄，於是它自動消失。不需要任何分支判斷。

    out_path 為空（命令列只想看結果、不要落檔）時下載到暫存目錄並在讀完後刪掉 ——
    「沒給輸出路徑就不留下任何檔案」是這批腳本的契約。
    """
    directory = os.path.dirname(os.path.abspath(out_path)) if out_path else ""
    scratch = ""

    if directory:
        if not os.path.isdir(directory):
            os.makedirs(directory, exist_ok=True)
    else:
        scratch = tempfile.mkdtemp(prefix="code_review_")
        directory = scratch

    save_path = os.path.join(directory, SOURCE_ARTIFACT_NAME)

    try:
        jira_utils.download_issue_attachment(
            item["content"], token, save_path)

        # utf-8-sig 而不是 utf-8：它同時吃得下位元組順序記號與純 UTF-8。用 utf-8 的話，
        # 一份「UTF-8 含 BOM」的 md（Windows 記事本多年來的預設）會在開頭留一個
        # ﻿，落在總表小標題底下的第一個字元 —— 看不見，但會讓那一行的 markdown
        # 解析歪掉。
        #
        # **嚴格，不猜其他編碼、不用 errors="replace"。** 猜錯編碼會產出一份看起來正常
        # 的亂碼報告，替代字元會產出一份少了幾個字卻回報成功的報告 —— 兩者都比一個明確
        # 的訊息糟，而明確的訊息還能把問題推回源頭（請存成 UTF-8）。
        #
        # 有人把 zip 或 PDF 改名成 .md 掛上來時走的是**同一個例外**，所以這一段同時
        #蓋掉兩種情況。
        with open(save_path, "r", encoding="utf-8-sig") as handle:
            return handle.read()

    except jira_utils.JiraError as exc:
        raise CodeReviewUnavailable(
            "下載附件 %s 失敗：%s"
            % (ai_analysis_gitlab_mr.plain(item.get("filename")), exc))
    except UnicodeDecodeError:
        raise CodeReviewUnavailable(
            "附件 %s 不是 UTF-8 編碼，無法讀取 —— 請以 UTF-8 重新存檔後上傳"
            % ai_analysis_gitlab_mr.plain(item.get("filename")))
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)


def _gather(params, keyword, base_url, token, heading):
    """取得附件並擷取總表，回傳步驟 4 的結構內容。

    議題上沒有符合的附件時回 None（那一段沒有內容，不是出了錯）。取不到內容、或該
    device 的 parse_code_review 鉤子失敗時拋 CodeReviewUnavailable，並把已經知道的附件
    資訊掛在它的 meta 上。

    **擷取與判定本身不在這裡**，在該 device 的鉤子（見 _parse_with_hook）—— 各條產品線
    的 code review 工具不同，產出格式也就不同。這一支只負責把現成的全文交給它。
    """
    key = ai_analysis_gitlab_mr.plain(params["jira_key"])
    debug_dir = params["debug_dir"]

    script_io.progress("查詢 JIRA 議題的附件…")

    try:
        attachments = jira_utils.get_issue_attachments(base_url, token, key)
    except jira_utils.JiraError as exc:
        raise CodeReviewUnavailable(_jira_reason(exc, key))

    picked = _pick_attachment(attachments, keyword)
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, _describe_attachments(attachments, keyword, picked))

    if picked is None:
        # 這一段沒有內容，而不是出了錯 —— 不是每一張議題都掛著 code review。
        # 回空的結構，呼叫端據此不落檔，報告裡整段不出現。
        logger.info("議題 %s 上沒有以 %r 開頭的 %s 附件",
                    key, keyword, SOURCE_SUFFIX)
        return None

    filename = ai_analysis_gitlab_mr.plain(picked.get("filename"))
    meta = {
        "filename": filename,
        "created": ai_analysis_gitlab_mr.plain(picked.get("created")),
        "author": ai_analysis_gitlab_mr.plain(
            (picked.get("author") or {}).get("displayName")),
        "url": ai_analysis_gitlab_mr.plain(picked.get("content")),
    }

    # 從這裡開始的失敗都已經知道是哪一個附件，所以把 meta 掛上去 —— 報告要靠那三行
    # 讓讀者自己點連結去看全文。
    try:
        # 下載**之前**先擋過大的附件。JIRA 本來就回報 size，所以不必先傳進來再丟掉 ——
        # 有人把一份幾十 MB 的 log 改名掛上來時，這一行省下那趟傳輸。
        size = picked.get("size")
        limit = ai_analysis_gitlab_mr.MAX_CODE_REVIEW_BYTES
        if isinstance(size, int) and size > limit:
            raise CodeReviewUnavailable(
                "附件 %s 有 %d 位元組，超過上限 %d，未下載"
                % (filename, size, limit))

        script_io.progress("下載 %s…" % filename)
        text = _read_attachment(picked, token, params["out_path"])

        script_io.progress("解析程式碼審閱報告…")
        parsed = _parse_with_hook(text, heading, key, debug_dir)

    except CodeReviewUnavailable as exc:
        exc.meta = meta
        raise

    return ai_analysis_gitlab_mr.code_review_body(
        risk_table=parsed["risk_table"],
        review_result=parsed["review_result"],
        **meta)


def _parse_with_hook(text, heading, key, debug_dir):
    """載入該 device 的 parse_code_review 鉤子並執行它。

    回傳鉤子的結果；任何失敗都轉成 CodeReviewUnavailable —— 訊息進結構的 error 欄位、
    報告顯示那一段、**流程繼續**。這一步跑在 AI 分析之後，讓它失敗會把一份已經完成、
    已經付費的分析整份丟掉，而這一條對「鉤子壞了」與「文件不合約定」同樣成立。

    **訊息分三種，因為該去改的東西不同：**

        文件不合約定（RiskTableError）  去看那份附件，或覆寫這個 device 的鉤子
        鉤子載不進來（DeviceError）     語法錯誤或 import 失敗，訊息已帶檔名與行號
        其他任何例外                    那支鉤子的程式錯誤

    後兩種要**點名 device 與鉤子**。沿用第一種的句子的話，使用者會跑去查 JIRA、查權限、
    查附件在不在 —— 全都沒問題，真正該改的是那支腳本。

    攔 Exception 是刻意的，不只攔 RiskTableError：鉤子是使用者寫的，一個 KeyError 不該
    殺掉整條流程。代價是連 KeyboardInterrupt 以外的程式錯誤都被吞成「這一段沒有內容」，
    所以訊息裡帶上例外的類別名，而完整的 traceback 進除錯輸出。
    """
    try:
        hook, owner = device.load_hook("parse_code_review")
    except device.DeviceError as exc:
        ai_analysis_gitlab_mr.write_debug_log(
            debug_dir, "code_review 鉤子載入失敗 [%s] %s" % (exc.code, exc))
        raise CodeReviewUnavailable("%s（%s）" % (exc, exc.detail))

    try:
        parsed = hook.parse({
            "text": text,
            "heading": heading,
            "jira_key": key,
            "debug_write": ai_analysis_gitlab_mr.debug_writer(debug_dir),
        })
    except ai_analysis_gitlab_mr.RiskTableError as exc:
        # 文件不合約定。訊息原樣用 —— 它說的是那份附件的事，而使用者要去看的正是它。
        ai_analysis_gitlab_mr.write_debug_log(
            debug_dir, "code_review 解析失敗 [%s] %s" % (exc.code, exc))
        raise CodeReviewUnavailable(str(exc))
    except Exception as exc:                    # noqa: BLE001 - 見上面的說明
        trace = traceback.format_exc()
        logger.error("device %s 的 parse_code_review 執行失敗：\n%s", owner, trace)
        ai_analysis_gitlab_mr.write_debug_file(
            debug_dir, "code_review_hook_error.txt", trace)
        raise CodeReviewUnavailable(
            "device %s 的 parse_code_review 執行失敗：%s: %s"
            "（這是該 device 的腳本問題，不是來源文件的問題）"
            % (owner, exc.__class__.__name__, exc))

    # 鉤子是使用者寫的，回傳值不保證形狀對。在這裡擋住，訊息點名是哪一個 device ——
    # 讓一個缺鍵的 dict 流到下游，症狀會是報告裡那一段安靜地空白。
    if not isinstance(parsed, dict):
        raise CodeReviewUnavailable(
            "device %s 的 parse_code_review 回傳的不是物件，而是 %s"
            "（請用 contract.code_review_parsed() 組回傳值）"
            % (owner, type(parsed).__name__))

    return {
        "risk_table": ai_analysis_gitlab_mr.plain(parsed.get("risk_table")),
        "review_result": ai_analysis_gitlab_mr.plain(parsed.get("review_result")),
    }


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

            # 上一步抽出的 key 與 AI 分析那一步判定的狀態。兩者一起決定「要不要真的
            # 去抓」，所以不需要（也不該有）一個獨立的布林開關。
            script_io.arg("jira_key", default="",
                          help="步驟 2 抽出的 JIRA key；空字串代表這筆沒有 key"),
            script_io.arg("jira_state", default="ok",
                          help="步驟 3 判定的 key 狀態（ok / none / invalid）；"
                               "只有 ok 才會去取附件。預設 ok，讓命令列只給 "
                               "jira_key 就能執行"),

            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把結構寫到這個檔案；空字串代表不落檔"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    # --- 部署缺漏：**無條件**先擋 ---
    #
    # 不管這一筆有沒有 JIRA key 都檢查。只在「真的要去抓」時才檢查的話，一個設定錯誤
    # 只會在剛好遇到有效 key 的 MR 時浮現 —— 一個有時才出現的部署錯誤，比每次都出現
    # 的難查得多。
    #
    # 這是這一步唯一會結束整條流程的失敗，所以看到步驟 4 失敗，下一步永遠是去看設定檔。
    try:
        keyword = ai_analysis_gitlab_mr.code_review_keyword()
        base_url, token = ai_analysis_gitlab_mr.jira_credentials()
    except ai_analysis_gitlab_mr.CredentialError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    # 總表那一節叫什麼**可由 device 宣告** —— 各條產品線的 code review 工具產出格式
    # 不同。但那只是一個字串，所以宣告寫壞了可以在這裡、在任何網路往來之前就擋下來；
    # 擷取與判定本身在該 device 的 parse_code_review 鉤子裡（見 _parse_with_hook），
    # 這個值會當 heading 傳給它。
    #
    # 與上面兩項一起讀，理由相同：宣告寫壞了是部署問題，在任何網路往來之前就該擋下來。
    try:
        heading = device.code_review_source_heading(
            default=ai_analysis_gitlab_mr.CODE_REVIEW_SOURCE_HEADING)
    except device.DeviceError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    # --- 這一筆需不需要去抓 ---
    key = ai_analysis_gitlab_mr.plain(params["jira_key"])
    state = ai_analysis_gitlab_mr.plain(params["jira_state"])

    if not key or state != ai_analysis_gitlab_mr.JIRA_STATE_OK:
        # 沒有 key（標題裡抽不出來）或 key 被判定為無效時不發任何請求。
        #
        # 有效性是 device 的政策、在步驟 3 判定，這一步只是照它的結論行事 —— 自己
        # 重判就會有第二份規則，兩份必然漂移。不先擋的話，[WIP]、[Draft] 這類前綴
        # 每一筆都會白打一趟 JIRA 換回 404。
        logger.info("jira_key=%r state=%r，不取程式碼審閱報告", key, state)
        script_io.progress("略過程式碼審閱報告…")
        ai_analysis_gitlab_mr.write_debug_log(
            params["debug_dir"],
            "code_review skipped repo=%s mr=%s jira_key=%r state=%r"
            % (repo, mr_iid, key, state))
        script_io.reply(
            message="沒有可用的 JIRA key，未取得程式碼審閱報告",
            detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
            data={},
        )

    # --- 取得、擷取 ---
    try:
        body = _gather(params, keyword, base_url, token, heading)
    except CodeReviewUnavailable as exc:
        # 外部服務的回答，或別人的文件不合約定。**不結束流程** —— 這一步跑在 AI 分析
        # 之後，讓它失敗會把一份已經完成、已經付費的分析整份丟掉。
        #
        # 已經知道是哪一個附件時 meta 有值，於是報告裡日期／作者／連結三行照樣印得
        # 出來，讀者點連結就能自己看全文。
        logger.warn("取不到程式碼審閱報告：%s", exc)
        ai_analysis_gitlab_mr.write_debug_log(
            params["debug_dir"], "code_review unavailable: %s" % exc)
        body = ai_analysis_gitlab_mr.code_review_body(error=str(exc),
                                                      **exc.meta)

    if body is None:
        # 議題上沒有符合條件的附件：這一段沒有內容，不落檔，報告裡整段不出現。
        script_io.reply(
            message="議題 %s 上沒有以 %s 開頭的程式碼審閱報告" % (key, keyword),
            detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
            data={},
        )

    payload = ai_analysis_gitlab_mr.wrap_code_review(body)

    # 落檔前先驗一次。驗在**產生它的這一步**，訊息才點得出是哪個欄位 —— 留到步驟 5
    # 渲染前才發現的話，根因在這裡而症狀在兩步之後。
    try:
        ai_analysis_gitlab_mr.validate_code_review(payload, source="步驟 4")
    except ai_analysis_gitlab_mr.CodeReviewFormatError as exc:
        ai_analysis_gitlab_mr.write_debug_file(
            params["debug_dir"], "bad_code_review.json", payload)
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], payload)
    ai_analysis_gitlab_mr.write_debug_log(
        params["debug_dir"],
        "code_review repo=%s mr=%s file=%r table=%d error=%r"
        % (repo, mr_iid, body["filename"], len(body["risk_table"]),
           body["error"]))

    if body["error"]:
        message = "程式碼審閱報告取得失敗，報告中將顯示原因"
    else:
        message = "已取得程式碼審閱報告（%s）" % body["filename"]

    script_io.reply(
        message=message,
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data=payload,
    )


if __name__ == "__main__":
    script_io.run(main)
