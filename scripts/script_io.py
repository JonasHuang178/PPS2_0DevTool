#!/usr/bin/env python3
"""信封處理：收請求、回結果。

這個模組是 Qt 這條呼叫管線專用的東西，刻意放在 script_utils/ 外面 ——
別人拿 script_utils 去當函式庫用時不該碰到它。

兩種投遞方式：

    Qt   echo '{...}' | python my_action.py --request-stdin
    人   python my_action.py --dump-config > run.json
         （編輯 run.json）
         python my_action.py --request run.json

功能自訂的參數**不會**變成命令列旗標。命令列旗標只限框架用途：
--request-stdin / --request / --dump-config / -v / --help。

通道規則：
    stdout  只放結果，單一 JSON 物件
    stderr  診斷訊息、警告、進度
"""

import argparse
import json
import os
import sys
import traceback

from script_utils import logger

__all__ = ["arg", "cfg", "parse_request", "progress",
           "reply", "reply_fail", "run", "MASKED", "REQUEST_LOG_DIR_NAME"]


# 遮掉的值在參數紀錄裡長這樣。不是空字串 —— 空字串看起來像「這個欄位沒給」，
# 而那兩件事的下一步完全不同。
MASKED = "***"

# 參數紀錄放在紀錄目錄底下的這個子目錄。
REQUEST_LOG_DIR_NAME = "requests"

# 紀錄目錄的參數鍵名，parse_request() 的預設。
#
# script_io 是通用層，不該認得任何一個功能的參數形狀，所以這只是**預設值** ——
# 沒有紀錄目錄概念的腳本把 log_dir_param 傳空字串即可關閉參數紀錄。
DEFAULT_LOG_DIR_PARAM = "log_dir"


# --- 宣告 -------------------------------------------------------------------

class _Param(object):
    """一個參數的宣告。

    參數只宣告一次，由它同時產生 --help 的說明與 --dump-config 的模板。
    如果模板另外寫死一份，它一定會跟腳本實際讀的欄位漂移。
    """

    __slots__ = ("name", "type", "default", "required", "help", "mask")

    def __init__(self, name, type=str, default=None, required=False, help="",
                 mask=None):
        # 容許 "--created-after-days" 這種寫法，統一正規化成 params 的鍵名。
        key = name.lstrip("-").replace("-", "_")
        self.name = key
        self.type = type
        self.default = default
        self.required = required
        self.help = help
        self.mask = mask


class _ConfigKey(object):
    """一個設定鍵的宣告。

    required=True 會讓缺漏在**進入業務邏輯之前**就被擋下來。
    舊版設定鍵拼錯只會讓程式拿到空值繼續跑，帶著空 token 去打 API 拿到
    401，使用者於是去檢查 token 是否過期 —— 找錯方向。
    """

    __slots__ = ("name", "required", "help")

    def __init__(self, name, required=False, help=""):
        self.name = name
        self.required = required
        self.help = help


def arg(name, type=str, default=None, required=False, help="", mask=None):
    """宣告一個參數。

    `mask` 宣告「這個參數的值是不是憑證」，只影響寫出的參數紀錄（見
    write_request_log），不影響 --help、--dump-config，也不影響腳本實際拿到的值：

        None       原樣寫出
        True       整個值換成 MASKED
        callable   以 mask(原值) 的回傳值取代

    **有些參數整個就是憑證（金鑰），有些只有一部分是**（位址尾端附帶的識別碼）——
    後者的其餘部分正是診斷時最想看的東西，整個遮掉等於把有用的部分一起丟掉。所以這裡
    收一個函式而不是只有布林。

    遮罩宣告在參數旁邊，與型別、預設值同一處，因此它跟著參數一起被看見、一起被改。
    """
    return _Param(name, type=type, default=default, required=required, help=help,
                  mask=mask)


def cfg(name, required=False, help=""):
    """宣告一個設定鍵。"""
    return _ConfigKey(name, required=required, help=help)


# --- 型別轉換 ---------------------------------------------------------------

def _coerce(value, target_type, where, name):
    if target_type is None or isinstance(value, target_type):
        return value

    # bool("false") 是 True，所以布林要特別處理。
    if target_type is bool:
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no", ""):
                return False
        return bool(value)

    try:
        return target_type(value)
    except (TypeError, ValueError):
        raise ValueError("%s \"%s\" 的值無法轉為 %s：%r"
                         % (where, name, target_type.__name__, value))


def _is_missing(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


# --- 傾印模板 ---------------------------------------------------------------

def _build_template(action, params, config_keys, template_version):
    config_block = {}
    config_help = {}
    for key in config_keys:
        config_block[key.name] = ""
        text = key.help or ""
        if key.required:
            text = (text + "（必填）") if text else "必填"
        config_help[key.name] = text

    params_block = {}
    params_help = {}
    for param in params:
        # 已有預設值的欄位直接填好，必填欄位留空。
        params_block[param.name] = "" if param.required else param.default
        text = param.help or ""
        if param.required:
            text = (text + "（必填）") if text else "必填"
        params_help[param.name] = text

    template = {}
    if template_version:
        template["_template_version"] = template_version
    template["action"] = action
    template["source_path"] = ""
    template["config"] = config_block
    template["params"] = params_block
    # JSON 沒有註解，"_" 開頭的鍵是最不彆扭的替代做法 —— 腳本一律忽略。
    template["_help"] = {"config": config_help, "params": params_help}
    return template


def _format_declarations(params, config_keys):
    lines = []
    if config_keys:
        lines.append("設定鍵（信封的 config，或 --dump-config 產生的模板）:")
        for key in config_keys:
            flag = " (必填)" if key.required else ""
            lines.append("  %-28s %s%s" % (key.name, key.help or "", flag))
    if params:
        if lines:
            lines.append("")
        lines.append("參數（信封的 params）:")
        for param in params:
            flag = " (必填)" if param.required else ""
            default = "" if param.required or param.default is None \
                else "  [預設 %r]" % (param.default,)
            lines.append("  %-28s %s%s%s"
                         % (param.name, param.help or "", flag, default))
    return "\n".join(lines)


# --- 收信封 -----------------------------------------------------------------

def _mask_value(value, mask):
    """依宣告遮掉一個值。遮罩函式自己壞掉時退回整個遮掉，不讓紀錄壞掉整支腳本。"""
    if mask is True:
        return MASKED
    try:
        return mask(value)
    except Exception:                               # noqa: BLE001
        logger.debug("遮罩函式失敗，整個值改為 %s", MASKED)
        return MASKED


def mask_params(params, param_defs):
    """回傳一份把憑證遮掉的參數副本。原本那一份不動。

    只動宣告了 mask 的鍵，其餘原樣帶過 —— 包含腳本沒宣告但呼叫端有送的欄位
    （協定是加法式的），那些照樣要留著，它們常常正是「呼叫端送錯東西」的證據。
    """
    masked = dict(params or {})

    for param in param_defs:
        if param.mask is None or param.name not in masked:
            continue
        masked[param.name] = _mask_value(masked[param.name], param.mask)

    return masked


def write_request_log(log_dir, action, params, param_defs):
    """把**實際收到的參數**遮罩後寫進 <log_dir>/requests/<action>.json。

    寫出的形狀是 `{"params": {...}}` —— 一個可以直接 --request 投遞回去的信封。

    `log_dir` 為空就什麼都不做 —— 與其他紀錄同一個開關，所以不會出現「開關為真但路徑
    為空」這種矛盾狀態。

    **只記 params，不記信封的其餘欄位。** 這份紀錄要回答的是「這一步被餵了什麼參數」，而
    `source_path`、`action`、`config` 都不是參數：action 已經是檔名，config 是呼叫端
    那一整個功能區塊、這些腳本一律宣告 `config=[]` 根本不讀它，寫進來只會把真正要看的
    那幾個鍵淹掉。而且遮罩規則只宣告在參數上，少記一個不受遮罩管的區塊，也就少一條
    憑證外流的路。

    **但是放在 `params` 這個鍵之下，而不是裸的一個物件。** 多這一層使整份檔案本身就是
    一個合法的請求信封，可以直接 `--request` 投遞回同一支腳本（action 由腳本自己的預設
    補上，config 這些腳本不讀）—— 一個**只差補回被遮掉的值**就能重跑的檔案，比一份
    只能讀的參數清單有用得多，而代價只是一層括號。

    **這份紀錄由腳本寫，不由呼叫端寫。** 腳本是唯一同時握有參數、紀錄目錄與「哪些參數
    是憑證」這三件事的地方。交給呼叫端，遮罩規則就得在每個呼叫端各實作一次，而圖形介面
    與持續整合的投遞方式本來就不同（一個走 stdin、一個走檔案），兩份實作必然漂移。

    **為什麼要留這份**：逐行紀錄說的是「發生了什麼」，參數說的是「它被要求做什麼」。
    參數打錯、呼叫端送錯欄位這一類問題，只有後者看得出來。

    **為什麼是遮罩而不是寫完再刪**：刪除要靠每一條失敗路徑都執行到，而這份紀錄的用途
    正是在失敗時被讀。遮過之後它可以安全地留著，不需要任何清理步驟。

    代價寫明白兩件事：一是被遮掉的值要自己補回去才重跑得動；二是裡面的 `out_path` 與
    `log_dir` 指的是**那一次**的目錄，原地重跑會覆寫那一次的產物、並往那一份逐行紀錄
    後面繼續追加 —— 要留著原樣就先把檔案複製出去，或改掉那兩個值。

    寫檔失敗不讓腳本失敗 —— 一份診斷紀錄寫不出來，不該讓一次已經在進行的工作中斷。
    """
    if not log_dir:
        return False

    folder = os.path.join(log_dir, REQUEST_LOG_DIR_NAME)
    path = os.path.join(folder, "%s.json" % (action or "request"))

    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"params": mask_params(params, param_defs)}, handle,
                      ensure_ascii=False, indent=2)
            handle.write("\n")
    except OSError as exc:
        logger.warn("寫出參數紀錄失敗（%s）：%s", path, exc)
        return False

    logger.debug("參數紀錄：%s", path)
    return path


def parse_request(action, description="", config=None, params=None,
                  template_version="", log_dir_param=DEFAULT_LOG_DIR_PARAM):
    """收信封並驗證，回傳含四個鍵的 dict：

        source_path / config / action / params

    信封裡沒有工具身分 —— 需要知道呼叫方是誰的腳本自行讀取
    os.environ.get("TOOLNAME") 與 os.environ.get("TOOLVERSION")，
    這兩個變數在命令列直接執行時不存在，腳本要能在缺少時正常運作。

    `log_dir_param` 指出哪一個參數是紀錄目錄；該參數有值時，這裡會把收到的 params
    遮罩後寫一份出去（見 write_request_log）。傳空字串即關閉這個行為 —— 沒有紀錄目錄
    概念的腳本不必為此多宣告一個參數。
    """
    config_keys = list(config or [])
    param_defs = list(params or [])

    epilog = _format_declarations(param_defs, config_keys)
    parser = argparse.ArgumentParser(
        description=description,
        epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # 只有框架旗標，沒有功能自訂參數的旗標。
    parser.add_argument("--request-stdin", action="store_true",
                        help="從 stdin 讀取請求信封（Qt 走這條）")
    parser.add_argument("--request", metavar="FILE",
                        help="從 JSON 檔案讀取請求信封")
    parser.add_argument("--dump-config", action="store_true",
                        help="傾印一份可填寫的請求模板到 stdout")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="打開 DEBUG 等級的診斷輸出")

    args = parser.parse_args()

    logger.set_verbose(args.verbose)

    if args.dump_config:
        template = _build_template(action, param_defs, config_keys,
                                   template_version)
        # 這是 --dump-config 這個模式的產出，本身就是它的結果。
        sys.stdout.write(json.dumps(template, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        sys.stdout.flush()
        sys.exit(0)

    if args.request_stdin and args.request:
        parser.error("--request-stdin 與 --request 不能同時使用")

    if args.request_stdin:
        raw = sys.stdin.read()
        source = "stdin"
    elif args.request:
        try:
            with open(args.request, "r", encoding="utf-8") as handle:
                raw = handle.read()
        except OSError as exc:
            parser.error("無法讀取請求檔案 %s：%s" % (args.request, exc))
        source = args.request
    else:
        # 直接下旗標的投遞方式不支援。argparse 的慣例是 exit 2。
        parser.error("請指定投遞方式：--request-stdin 或 --request FILE"
                     "（用 --dump-config 產生可填寫的模板）")

    try:
        envelope = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        raise ValueError("請求信封不是合法的 JSON（來源 %s）：%s" % (source, exc))

    if not isinstance(envelope, dict):
        raise ValueError("請求信封必須是 JSON 物件（來源 %s）" % source)

    logger.debug("收到請求信封，來源 %s", source)

    incoming_config = envelope.get("config") or {}
    incoming_params = envelope.get("params") or {}
    if not isinstance(incoming_config, dict):
        raise ValueError("信封的 config 必須是物件")
    if not isinstance(incoming_params, dict):
        raise ValueError("信封的 params 必須是物件")

    # --- 必填檢查與預設值回填 ---
    missing = []

    resolved_config = dict(incoming_config)
    for key in config_keys:
        if _is_missing(resolved_config.get(key.name)):
            if key.required:
                missing.append("設定 %s" % key.name)

    resolved_params = {}
    for param in param_defs:
        value = incoming_params.get(param.name)
        if _is_missing(value):
            if param.required:
                missing.append("參數 %s" % param.name)
                continue
            value = param.default
        else:
            value = _coerce(value, param.type, "參數", param.name)
        resolved_params[param.name] = value

    # 協定是加法式的：腳本沒宣告但呼叫端有送的欄位照樣留著。
    for name, value in incoming_params.items():
        resolved_params.setdefault(name, value)

    if missing:
        reply_fail("缺少必填項目：%s" % "、".join(missing))

    resolved_action = envelope.get("action", action)

    # 必填檢查**之後**才寫：缺了必填項目時這一步根本不會開始工作，而那個失敗訊息
    # 已經說得完整。寫在檢查之前只會為一個沒跑的步驟留下一份紀錄。
    #
    # 寫的是 **incoming_params**，不是 resolved_params：這份紀錄要回答「呼叫端送了
    # 什麼」。回填過預設值的那一份看不出「這個鍵是對方沒給、由腳本補的」，而那正是
    # 參數類問題最常見的成因。
    if log_dir_param:
        write_request_log(resolved_params.get(log_dir_param),
                          resolved_action, incoming_params, param_defs)

    return {
        "source_path": envelope.get("source_path", "") or "",
        "config": resolved_config,
        "action": resolved_action,
        "params": resolved_params,
    }


# --- 進度 -------------------------------------------------------------------

def progress(stage):
    """回報一個處理階段。走 stderr，一行一個 JSON。

    一定要 flush —— 否則進度訊息會堆積到腳本結束才一次噴出，
    對話框上的文字從頭到尾不會變。

    自己節流：Qt 端收到就更新、不做過濾，所以跑幾千筆時不要每筆都報。
    """
    line = json.dumps({"progress": {"stage": str(stage)}}, ensure_ascii=False)
    sys.stderr.write(line + "\n")
    sys.stderr.flush()


# --- 回信封 -----------------------------------------------------------------

def _emit(envelope, exit_code):
    sys.stdout.write(json.dumps(envelope, ensure_ascii=False))
    sys.stdout.write("\n")
    sys.stdout.flush()
    sys.exit(exit_code)


def reply(message="", detail="", data=None):
    """成功。印出結果信封並以 exit code 0 結束。"""
    envelope = {"result": "PASS", "message": message or "執行完成"}
    if detail:
        envelope["detail"] = detail
    if data is not None:
        envelope["data"] = data
    _emit(envelope, 0)


def reply_fail(message, detail="", code=""):
    """業務邏輯失敗。印出結果信封並以 exit code 1 結束。"""
    envelope = {"result": "FAIL", "message": message or "執行失敗"}
    if detail:
        envelope["detail"] = detail
    if code:
        envelope["error"] = {"code": code}
    _emit(envelope, 1)


def run(main_func):
    """統一的錯誤處理入口，讓所有腳本行為一致。

    exit code 給 CI 用，JSON 給 GUI 與使用者用，兩者都要正確。
    """
    try:
        main_func()
    except SystemExit:
        raise                       # reply() / reply_fail() / argparse 的正常結束
    except KeyboardInterrupt:
        reply_fail("使用者中斷")
    except Exception as exc:        # noqa: BLE001 - 這裡就是要攔全部
        trace = traceback.format_exc()
        logger.error("未攔截的例外：\n%s", trace)
        # traceback 同時放進 detail：Qt 端不收集 stderr，這是使用者
        # 在 Debug_Mode 關閉時唯一能把錯誤內容帶出來的地方。
        reply_fail(str(exc) or exc.__class__.__name__, detail=trace)


# --- 編碼 -------------------------------------------------------------------

# Qt 會注入 PYTHONUTF8=1，但人在命令列直接執行時不會有。
# 明確設定，避免 Windows 上輸出中文時炸掉。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError, OSError):
        pass
