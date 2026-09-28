#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 2/5：取得相關資訊。

取得該 Merge Request 的後設資訊，並解出這次要用的 JIRA key 與**種類**。

種類（mr_type）決定步驟 3 與步驟 5 會用哪一份 summary.py 與 merge_to_md.py。它與
JIRA key 都是從同一份 MR 的同一個標題解出來的，所以在同一步進行 —— 分成兩步會讓
同一筆 MR 被取得三次。

**自己連線 GitLab。** 抽 JIRA key 的預設規則讀的是標題，而步驟 1 的產物只有描述本文；
畫面也不可靠 —— 使用者手動輸入編號時沒有標題。自己抓的代價是同一個 MR 被抓兩次，換到
的是這一步可以單獨執行，而且 Qt 與 CI 都不必多傳東西。

**三種 JIRA 模式的分派在這裡，抽取在 device。** 三選一是政策不是演算法；交給每個 device
各自實作，同一段判斷會出現多次並可能寫歪。

    python ai_analysis_gitlab_mr_info.py --help
    python ai_analysis_gitlab_mr_info.py --dump-config > run.json
    python ai_analysis_gitlab_mr_info.py --request run.json

憑證走環境變數，不放進 request 檔案：

    GITLAB_SERVER_URL    https://gitlab.example.com
    GITLAB_ACCESS_TOKEN  glpat-...
    GITLAB_VERIFY_SSL    true / false（未設定視為 false，即不驗證）
    PPS_DEVICE           sd / ssd / ...（未設定時用 default）
"""

import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from ai_analysis_gitlab_mr import device
from script_utils import gitlab_utils
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "mr_info"
DESCRIPTION      = "取得 Merge Request 的相關資訊並解出 JIRA key 與種類"


def _mr_fields(repo, mr_iid, mr):
    """把 GitLab 原樣的 MR 物件收斂成交給鉤子的欄位。

    不直接把原樣物件丟過去：那會讓 GitLab 回應的四十幾個欄位成為對 device 作者的契約，
    日後想換取得方式就動不了。
    """
    mr = mr or {}
    return {
        "title": mr.get("title") or "",
        "source_branch": mr.get("source_branch") or "",
        "target_branch": mr.get("target_branch") or "",
        "description": mr.get("description") or "",
        "repo": repo,
        "mr_iid": mr_iid,
    }


def _resolve_jira_key(mode, manual, fields, repo, mr_iid, debug_dir):
    """依模式決定這次的 JIRA key。只有 auto 會呼叫 device 的鉤子。

    這裡**不判定有效性** —— 判定在步驟 3 的 summary 鉤子，與抽取規則同屬一個 device，
    放在一起才不會各自漂移。
    """
    if mode == "none":
        logger.info("JIRA 模式為 none，不抽取")
        return ""

    if mode == "manual":
        logger.info("JIRA 模式為 manual，採用使用者輸入的值")
        return ai_analysis_gitlab_mr.plain(manual)

    hook, owner = device.load_hook("jira_key")
    logger.info("JIRA 模式為 auto，使用 device %s 的 jira_key 鉤子", owner)

    try:
        key = hook.extract(fields)
    except Exception as exc:                        # noqa: BLE001
        raise device.DeviceError(
            "device %s 的 jira_key.py 執行失敗" % owner,
            "%s: %s" % (exc.__class__.__name__, exc),
            "DEVICE_HOOK_RUNTIME_ERROR")

    key = ai_analysis_gitlab_mr.plain(key)
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "jira_key(%s) repo=%s mr=%s -> %r" % (owner, repo, mr_iid, key))
    return key


def _resolve_mr_type(fields, device_name):
    """解出這次的種類。回傳正規化過的字串；沒有就是空字串。

    嚴格模式的檢查也在這裡 —— 也就是在**任何 AI 花費之前**。一個沒照約定的標題不該先
    付一次錢才被告知。
    """
    # device 明著傳進去，不讓 load_hook 自己再去讀一次環境變數 —— 這一支的其餘判斷
    # （認得哪些種類、嚴不嚴格）都以 device_name 為準，載入卻用另一個來源的話，兩者
    # 一旦不同就會「載入 A 的鉤子、卻拿 B 的種類清單去檢查」，而且不會有任何徵兆。
    hook, owner = device.load_hook("mr_type", device=device_name)

    try:
        raw = hook.extract(fields)
    except Exception as exc:                        # noqa: BLE001
        raise device.DeviceError(
            "device %s 的 mr_type.py 執行失敗" % owner,
            "%s: %s" % (exc.__class__.__name__, exc),
            "DEVICE_HOOK_RUNTIME_ERROR")

    # 正規化在入口，不在鉤子：去空白、轉小寫、檢查形狀。不合法的字串視同沒有種類 ——
    # 那是 MR 作者打的字，不是部署者的錯誤。
    mr_type = device.normalize_type(raw)

    known = device.known_types(device_name)

    if mr_type and mr_type not in known:
        logger.info("device %s 認不得種類 %r（認得的是：%s）",
                    device_name, mr_type, "、".join(known) or "(無)")
        if device.strict_type(device_name):
            raise device.DeviceError(
                "device %s 認不得 type：%s" % (device_name, mr_type),
                "目前認得的是：%s。\n"
                "這個 device 宣告了 STRICT_TYPE = True，所以認不得的 type 是錯誤"
                "而不是回退。\n"
                "要新增一個 type，在 device/%s/ 底下建一個同名目錄即可。"
                % ("、".join(known) or "(無)", device_name),
                "DEVICE_TYPE_UNKNOWN")
        # 不嚴格：回退到通用版。回空字串讓後面幾步不必再判斷一次。
        return ""

    if not mr_type and device.strict_type(device_name):
        # 與「認不得」分開：使用者的下一步不同 —— 一個是去補標題，一個是去確認名稱。
        raise device.DeviceError(
            "這筆 Merge Request 沒有宣告 type",
            "device %s 宣告了 STRICT_TYPE = True，要求每一筆 Merge Request 都標明"
            "種類。\n"
            "抽取規則見 device/%s/mr_type.py（沒有的話是 device/%s/mr_type.py）。\n"
            "目前認得的 type：%s。"
            % (device_name, device_name, device.DEFAULT_DEVICE,
               "、".join(known) or "(無)"),
            "DEVICE_TYPE_MISSING")

    return mr_type


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,

        # 憑證與 device 不在這裡宣告 —— 它們走環境變數。在 config 宣告會讓使用者
        # 以為該把它們填進 request 檔案裡。
        config=[],

        params=[
            script_io.arg("repo", required=True,
                          help="專案，namespace/project 形式"),
            script_io.arg("mr_iid", required=True,
                          help="Merge Request 編號"),
            script_io.arg("jira_mode", default="auto",
                          help="none / manual / auto"),
            script_io.arg("jira_key_manual", default="",
                          help="使用者手動指定的 JIRA key（僅 manual 模式使用）"),
            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
            script_io.arg("out_path", default="",
                          help="額外把結果寫到這個檔案；空字串代表不落檔"),

            # 種類沒有對應的參數：它完全由 device 的鉤子自標題等欄位解出，
            # 呼叫端不能指定。可指定的話，兩個呼叫端就會各自長出一套判斷。
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]
    debug_dir = params["debug_dir"]

    try:
        server_url, token, verify_ssl = ai_analysis_gitlab_mr.gitlab_credentials()
    except ai_analysis_gitlab_mr.CredentialError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    script_io.progress("取得 Merge Request 相關資訊…")
    logger.info("取得 %s 的 Merge Request !%s（verify_ssl=%s）",
                repo, mr_iid, verify_ssl)

    try:
        mr = gitlab_utils.get_mr_info(server_url, token, repo, mr_iid,
                                      verify_ssl=verify_ssl)
    except gitlab_utils.GitLabError as exc:
        message, detail, code = ai_analysis_gitlab_mr.describe_gitlab_error(exc, repo)
        # 這一步指名了某一筆 MR，所以 404 的成因多一種：iid 不存在。
        if code == "GITLAB_PROJECT_NOT_FOUND":
            message = "找不到 %s 的 Merge Request !%s" % (repo, mr_iid)
            detail = ("%s\n\n可能是專案名稱拼錯、!%s 這個編號不存在，"
                      "或權杖對該專案沒有讀取權限（後者 GitLab 也回 404）。"
                      % (exc, mr_iid))
            code = "GITLAB_MR_NOT_FOUND"
        script_io.reply_fail(message, detail=detail, code=code)

    fields = _mr_fields(repo, mr_iid, mr)

    try:
        jira_key = _resolve_jira_key(params["jira_mode"], params["jira_key_manual"],
                                     fields, repo, mr_iid, debug_dir)
        mr_type = _resolve_mr_type(fields, device.resolve_name())
    except device.DeviceError as exc:
        ai_analysis_gitlab_mr.write_debug_log(
            debug_dir, "FAIL [%s] %s" % (exc.code, exc))
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    result = {"jira_key": jira_key, "mr_type": mr_type}

    ai_analysis_gitlab_mr.write_artifact(params["out_path"], result)
    ai_analysis_gitlab_mr.write_debug_log(
        debug_dir, "mr_info repo=%s mr=%s jira_key=%r mr_type=%r"
        % (repo, mr_iid, jira_key, mr_type))

    script_io.reply(
        message="已取得相關資訊（JIRA key：%s，type：%s）"
                % (jira_key or "(無)", mr_type or "(無)"),
        detail="專案：%s\nMerge Request：!%s" % (repo, mr_iid),
        data=result,
    )


if __name__ == "__main__":
    script_io.run(main)
