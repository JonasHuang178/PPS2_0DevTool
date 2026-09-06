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
           "reply", "reply_fail", "run"]


# --- 宣告 -------------------------------------------------------------------

class _Param(object):
    """一個參數的宣告。

    參數只宣告一次，由它同時產生 --help 的說明與 --dump-config 的模板。
    如果模板另外寫死一份，它一定會跟腳本實際讀的欄位漂移。
    """

    __slots__ = ("name", "type", "default", "required", "help")

    def __init__(self, name, type=str, default=None, required=False, help=""):
        # 容許 "--created-after-days" 這種寫法，統一正規化成 params 的鍵名。
        key = name.lstrip("-").replace("-", "_")
        self.name = key
        self.type = type
        self.default = default
        self.required = required
        self.help = help


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


def arg(name, type=str, default=None, required=False, help=""):
    """宣告一個參數。"""
    return _Param(name, type=type, default=default, required=required, help=help)


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

def parse_request(action, description="", config=None, params=None,
                  template_version=""):
    """收信封並驗證，回傳含四個鍵的 dict：

        source_path / config / action / params

    信封裡沒有工具身分 —— 需要知道呼叫方是誰的腳本自行讀取
    os.environ.get("TOOLNAME") 與 os.environ.get("TOOLVERSION")，
    這兩個變數在命令列直接執行時不存在，腳本要能在缺少時正常運作。
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

    return {
        "source_path": envelope.get("source_path", "") or "",
        "config": resolved_config,
        "action": envelope.get("action", action),
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
