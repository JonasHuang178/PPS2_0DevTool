#!/usr/bin/env python3
"""AI Analysis GitLab MR —— 步驟 5/5：合併為 markdown。

把前面各步落下的檔案合併成一份報告。**輸入一律是檔案路徑**，這一步不接收內容
本身 —— 它的工作就是「把這幾份檔案接起來」，命令列直接呼叫時的用法與 Qt 完全
相同。

產出是要顯示給人看的報告：原始描述那一段原樣保留，後面接上這一輪的 AI 分析，
再接上程式碼審閱那一段。不加報告標題、也不加產生時間 —— 使用者要看的就是這幾段
內容本身。工具不會把它寫回 GitLab。

AI 分析與程式碼審閱兩段收到的都是**結構**而不是排好版的 markdown，渲染在這一步。
程式碼審閱那一段因此印得出附件的日期、作者與連結 —— 那三個值只有步驟 4 拿得到，
而這一步收到的只是一個檔案路徑。**報告只放總表，全文靠那個連結回去看。**

    python ai_analysis_gitlab_mr_merge_to_md.py --help
    python ai_analysis_gitlab_mr_merge_to_md.py --dump-config > run.json
    python ai_analysis_gitlab_mr_merge_to_md.py --request run.json

每一個輸入路徑都可以是 null（或省略），代表那一段沒有內容、整段略過。但**路徑
給了就必須存在** —— 指名一個不存在的檔案是上一步沒寫成功，靜默略過只會產出一份
看起來正常、實際上少一段的報告。

完整的 markdown 一律放進 data，呼叫端不必開檔就能顯示結果；給了 out_path 才
**額外**寫一份檔案。
"""

import os
import sys

# 見其他入口腳本的說明：這一行不能刪。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ai_analysis_gitlab_mr
import script_io
from script_utils import file_utils
from script_utils import json_utils
from ai_analysis_gitlab_mr import device
from script_utils import logger

TEMPLATE_VERSION = "2.0.0"
ACTION           = "merge_to_md"
DESCRIPTION      = "把前面各步落下的檔案合併成新的 MR 描述 markdown"


def _is_given(path):
    """路徑是否真的給了。

    null、省略、空字串、只有空白都算沒給 —— 呼叫端可能送 null，也可能送空字串
    （script_io 對缺漏的參數回填預設值，而預設值是空字串），兩種都要收。
    """
    return isinstance(path, str) and path.strip() != ""


def _code_review_text(body):
    """給 device 鉤子的 code_review 值：總表的 markdown，沒有就是空字串。

    鉤子拿到的維持是**字串**（它原本就是），所以既有的鉤子簽章不因這次改動而失效。
    完整的結構另外以 code_review_info 交出去 —— 想印出附件檔名或連結的鉤子從那裡取。
    """
    if not isinstance(body, dict):
        return ""
    return ai_analysis_gitlab_mr.plain(body.get("risk_table"))


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


def _analysis_section(payload, path, inputs):
    """把 AI 分析結果變成報告裡「AI 分析結果」標題底下的那一段。

    吃兩種形狀：

        結構化（schema_version / analysis）  驗證後交給 device 的 merge_to_md 鉤子
        整份就是一段文字，或 summary 是字串  原樣採用

    第二種是相容用的：版本欄位存在的意義就是同時支援多種形狀，而不是改一邊就讓另一邊
    爆掉。

    回傳 (那一段的內容, analysis 或 None)。analysis 給 footer 用 —— JIRA 的狀態記在
    裡面，由產生它的那一步判定，這一步不重新判。

    取到的東西不是文字也不是認得的結構時**回 FAIL 而不是硬轉**。硬轉的下場是把 Python
    的 repr 原樣印進報告裡，那份報告看起來是成功產出的。
    """
    if isinstance(payload, str):
        return payload, None

    if not isinstance(payload, dict):
        script_io.reply_fail(
            "AI 分析結果檔的內容不是物件也不是文字：%s" % path,
            detail="讀到的型別是 %s。" % type(payload).__name__,
            code="MERGE_SUMMARY_BAD_TYPE")

    # 結構化的那一種。認出來的依據是這兩個鍵的存在，而不是「summary 不是字串」——
    # 後者會讓一個打錯的欄位名安靜地走進渲染路徑。
    if "schema_version" in payload or "analysis" in payload:
        try:
            analysis = ai_analysis_gitlab_mr.validate_analysis(payload)
        except ai_analysis_gitlab_mr.AnalysisFormatError as exc:
            script_io.reply_fail("%s（檔案：%s）" % (exc, path),
                                 detail=exc.detail, code=exc.code)

        # 種類自**產物**讀取，不由 Qt 再轉送一次。步驟 5 收到的只有檔案路徑，而那個值
        # 已經在分析結構裡 —— 少一個參數，Qt 也就只需要為這件事改一行。
        #
        # 沒有 mr_type 的舊結構（版本 3）視為沒有種類，走通用版面，不失敗。
        mr_type = ai_analysis_gitlab_mr.plain(analysis.get("mr_type"))

        try:
            hook, owner = device.load_hook("merge_to_md", mr_type=mr_type)
        except device.DeviceError as exc:
            script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

        try:
            section = hook.render(dict(inputs, analysis=analysis, device=owner,
                                       mr_type=mr_type))
        except Exception as exc:                    # noqa: BLE001
            # 訊息要指得出種類：改壞的往往是某個種類專屬的那一份。
            script_io.reply_fail(
                "device %s 的 %smerge_to_md.py 執行失敗"
                % (owner, ("%s/" % mr_type) if mr_type else ""),
                detail="%s: %s" % (exc.__class__.__name__, exc),
                code="DEVICE_HOOK_RUNTIME_ERROR")

        return ai_analysis_gitlab_mr.plain(section), analysis

    value = payload.get("summary")
    if value is None or value == "":
        return "", None
    if isinstance(value, str):
        return value, None

    script_io.reply_fail(
        "AI 分析結果檔的 summary 欄位不是文字：%s" % path,
        detail="summary 的型別是 %s，而報告需要一段可以直接接上去的 markdown。\n"
               "這個檔案目前有的欄位：%s\n"
               "若這是結構化的分析，請讓上一步加上 schema_version 與 analysis。"
               % (type(value).__name__,
                  "、".join(sorted(payload.keys())) or "(無)"),
        code="MERGE_SUMMARY_NOT_TEXT")


def main():
    req = script_io.parse_request(
        action=ACTION,
        description=DESCRIPTION,
        template_version=TEMPLATE_VERSION,
        config=[],
        params=[
            script_io.arg("ori_md_file_path", default="",
                          help="MR 原始描述的 markdown 檔；null 表示沒有這一段"),
            script_io.arg("mr_summary_json_file_path", default="",
                          help="AI 分析結果的 JSON 檔（取其中的 summary 欄位）；"
                               "null 表示沒有這一段"),
            script_io.arg("code_review_json_file_path", default="",
                          help="程式碼審閱結果的 JSON 檔（步驟 4 的產物）；"
                               "null 表示沒有這一段"),
            script_io.arg("out_path", default="",
                          help="額外把報告寫到這個檔案；null 表示不落檔"),

            # 底下兩個**不進報告內容**，只用於診斷訊息與除錯日誌。命令列只想
            # 合併檔案時可以不給。
            script_io.arg("repo", default="",
                          help="專案，namespace/project 形式；只用於診斷訊息"),
            script_io.arg("mr_iid", default="",
                          help="Merge Request 編號；只用於診斷訊息"),

            # 出處資訊用。使用者在畫面上選的那個 AI 模式名稱，原樣印在報告末尾，
            # 讓讀的人知道這份分析是哪一種模式產生的。
            script_io.arg("ai_mode", default="",
                          help="AI 模式名稱；只用於報告末尾的出處資訊"),

            script_io.arg("debug_dir", default="",
                          help="除錯輸出目錄；空字串代表不寫任何檔案"),
        ],
    )

    params = req["params"]
    repo = params["repo"]
    mr_iid = params["mr_iid"]

    script_io.progress("合併為 markdown…")

    # --- 讀入三段內容 ---
    #
    # 順序有意義：AI 分析那一段交給 device 的鉤子渲染，而鉤子的輸入包含描述與
    # 審閱報告（唯讀參考），所以那兩段要先讀好。
    description = ""
    if _is_given(params["ori_md_file_path"]):
        description = _read_required(params["ori_md_file_path"], "MR 描述檔")

    # 程式碼審閱是一份**結構**而不是排好版的 markdown，渲染由這一步負責 —— 與
    # 03_summary.json 同一套。報告要印出附件的日期、作者與連結，而那三個值只有步驟 4
    # 拿得到；這一步收到的只是一個檔案路徑。
    code_review = None
    if _is_given(params["code_review_json_file_path"]):
        path = params["code_review_json_file_path"]
        raw = _read_required(path, "程式碼審閱結果檔")
        try:
            payload = json_utils.load_data(raw)
        except ValueError as exc:
            script_io.reply_fail(
                "程式碼審閱結果檔不是合法的 JSON：%s" % path,
                detail=str(exc), code="MERGE_CODE_REVIEW_NOT_JSON")
        try:
            code_review = ai_analysis_gitlab_mr.validate_code_review(
                payload, source="檔案 %s" % path)
        except ai_analysis_gitlab_mr.CodeReviewFormatError as exc:
            script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    summary = ""
    analysis = None
    if _is_given(params["mr_summary_json_file_path"]):
        path = params["mr_summary_json_file_path"]
        raw = _read_required(path, "AI 分析結果檔")
        try:
            payload = json_utils.load_data(raw)
        except ValueError as exc:
            script_io.reply_fail(
                "AI 分析結果檔不是合法的 JSON：%s" % path,
                detail=str(exc), code="MERGE_SUMMARY_NOT_JSON")
        summary, analysis = _analysis_section(payload, path, {
            "description": description,
            # 維持既有的型別（字串，沒有就是空字串）—— device 作者的鉤子簽章不因這次
            # 改動而變。完整的結構另外以 code_review_info 給出去，是加法式的。
            "code_review": _code_review_text(code_review),
            "code_review_info": code_review,
            "repo": repo,
            "mr_iid": mr_iid,
        })

    code_review_section = ai_analysis_gitlab_mr.render_code_review_section(
        code_review)

    if not (description or summary or code_review_section):
        # 三段全空代表呼叫端什麼都沒給，或前面幾步全部沒有產出。產一份只有標題的
        # 報告等於把問題往下游丟。
        script_io.reply_fail(
            "沒有任何可合併的內容",
            detail="ori_md_file_path、mr_summary_json_file_path 與 "
                   "code_review_json_file_path 都沒有給，或內容都是空的。",
            code="MERGE_NOTHING_TO_DO")

    logger.info("合併報告：描述 %d、分析 %d、審閱 %d 字元",
                len(description), len(summary), len(code_review_section))

    # --- 組報告 ---
    #
    # 不加報告標題、不加產生時間：使用者要看的就是「原始描述」與「AI 分析」這
    # 兩段內容本身，多一層框架只是噪音。
    #
    # AI 分析那一段的標題由 render_ai_section() 寫出，與步驟 1 用來切的是同一
    # 個常數 —— 這樣一份被人貼回 MR 描述的報告，下一次跑的時候切得掉。
    #
    # 空的段落整段不放 —— 一個只有標題沒有內容的區塊會讓人以為內容漏掉了。
    sections = []

    if description.strip():
        sections.append(
            ai_analysis_gitlab_mr.render_description_section(
                description).strip())

    if summary.strip():
        sections.append(
            ai_analysis_gitlab_mr.render_ai_section(summary).strip())

    if code_review_section.strip():
        # 段落標題與總表的小標題都由這一步寫出，步驟 4 只負責內容 —— 讓它自帶標題的
        # 話，它無從知道自己會被放在哪一層，結果是縮在 AI 分析底下。
        sections.append(code_review_section.strip())

    # 出處資訊永遠都在：報告被貼到 MR 討論串之後就脫離了產生它的環境，這一段是
    # 「這份分析是哪一版腳本、在哪裡跑出來的」唯一的答案。
    #
    # 種類不必在這裡取得 —— 它在 analysis 裡，render_footer 自己會讀。多傳一次的話
    # 就有兩個來源，而它們可以不一致。
    # device 的名稱與版本由這一步自己讀環境變數取得 —— 它本來就要讀那個變數來
    # 載入自己的鉤子，不必經參數、也不必動 schema。
    device_name = ""
    device_ver = ""
    try:
        device_name = device.resolve_name()
        device_ver = device.device_version(device_name)
    except device.DeviceError as exc:
        script_io.reply_fail(str(exc), detail=exc.detail, code=exc.code)

    sections.append(ai_analysis_gitlab_mr.render_footer(
        ai_mode=params["ai_mode"],
        device_name=device_name,
        device_version=device_ver,
        analysis=analysis))

    markdown = "\n\n".join(sections) + "\n"

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
