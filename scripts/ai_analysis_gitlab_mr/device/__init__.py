#!/usr/bin/env python3
"""依 device 載入客製化的鉤子。

一個 MR 該怎麼分析，會因為它屬於哪一條產品線而不同。這個套件底下每一個目錄是一個
device，目錄名就是 device 名：

    device/
      default/          未指定 device 時用這一份
      ssd/              只放想覆寫的鉤子，缺的自動用 default 的
      _template/        底線開頭，不是 device

三個鉤子（缺一不可地對應到三個步驟）：

    jira_key.py     步驟 2：怎麼從 Merge Request 抽出 JIRA key
    summary.py      步驟 3：問 AI 什麼、怎麼解析、組出什麼分析內容
    merge_to_md.py  步驟 5：AI 分析那一段的版面

**這個模組只負責找到與載入鉤子，不決定何時呼叫。** 三種 JIRA 模式的分派、參數的組裝、
回傳的驗證都在入口腳本裡 —— 那些是政策，每個 device 重寫一次只會寫歪。
"""

import importlib
import os
import re

from script_utils import logger

__all__ = [
    "DEVICE_ENV",
    "DEFAULT_DEVICE",
    "HOOK_NAMES",
    "DeviceError",
    "resolve_name",
    "known_devices",
    "load_hook",
    "device_version",
]

# 指定 device 的環境變數。
#
# 工具端由 Qt 從設定檔注入，CI 由 runner 自行設定 —— 腳本端因此只有一條取值路徑，
# 兩個呼叫端對它來說長得一模一樣（與憑證的傳遞方式相同）。
DEVICE_ENV = "PPS_DEVICE"

# 未指定時用的 device。明著指定這個名稱也是合法的。
DEFAULT_DEVICE = "default"

# 三個鉤子的模組名。
HOOK_NAMES = ("jira_key", "summary", "merge_to_md")

# device 名稱只接受這個形狀。
#
# 名稱會被拿去 import，所以必須是合法的 Python 識別字 —— ssd_gen4 可以，ssd-gen4 不行。
# 這條檢查同時擋掉 "../../etc" 那類值：名稱從頭到尾不會被拿去組任何檔案路徑（見
# load_hook），這個檢查是第二道。
_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]*$")

# 這個套件所在的目錄，用來掃出有哪些 device。
_HERE = os.path.dirname(os.path.abspath(__file__))


class DeviceError(Exception):
    """device 的解析、載入或執行出了問題。

    與 CredentialError 同一個形狀：帶著入口腳本回報時要用的三樣東西，讓它一行就能
    轉成 FAIL。這個模組**不自己呼叫 reply_fail** —— 那會讓一支看起來只是在載入模組的
    函式把行程結束掉，而呼叫端從簽章上看不出來。
    """

    def __init__(self, message, detail, code):
        super(DeviceError, self).__init__(message)
        self.detail = detail
        self.code = code


def known_devices():
    """目前認得哪些 device，依名稱排序。

    掃目錄而不是維護一份名單：名單會與實際的目錄漂移，而失敗訊息裡那份清單一旦不準
    就比沒有更糟。掃目錄也讓「新增一個 device」不需要改任何程式碼。

    底線開頭的目錄不算（範本就是靠這個不被誤認為 device）。
    """
    names = []
    for entry in sorted(os.listdir(_HERE)):
        if entry.startswith("_"):
            continue
        if os.path.isdir(os.path.join(_HERE, entry)):
            names.append(entry)
    return names


def resolve_name(raw=None):
    """把環境變數的值收斂成一個確定存在的 device 名稱。

    空值（未設定、空字串、只有空白）用 DEFAULT_DEVICE —— 那代表「沒有特別需求」，
    用通用邏輯是對的。

    指定了但不存在則**失敗**，不退回 default。指定一個不存在的名字代表打錯字或忘記
    部署，靜默改用通用邏輯會產出一份用錯邏輯、而每一步都回報成功的報告。

    比對前一律小寫化，設定檔與 CI 因此可以寫任何大小寫。
    """
    value = os.environ.get(DEVICE_ENV, "") if raw is None else (raw or "")
    name = value.strip().lower()

    if not name:
        logger.debug("未指定 %s，使用 %s", DEVICE_ENV, DEFAULT_DEVICE)
        name = DEFAULT_DEVICE

    if not _NAME_RE.match(name):
        raise DeviceError(
            "device 名稱不合法：%r" % (value,),
            "名稱只能由小寫英數與底線組成，且不能以數字開頭 —— 它會被當成模組名載入。\n"
            "帶連字號的名字請改成底線（ssd-gen4 -> ssd_gen4）。",
            "DEVICE_NAME_INVALID")

    available = known_devices()

    if name not in available:
        if name == DEFAULT_DEVICE:
            # 與「打錯字」是兩件事：這是部署壞了。混用同一句話會讓人去翻設定檔。
            raise DeviceError(
                "找不到預設的 device 實作（%s）" % DEFAULT_DEVICE,
                "這不是設定的問題，是 scripts/ai_analysis_gitlab_mr/device/%s/ "
                "沒有被部署出來。請重新建置，或確認執行檔旁的 scripts/ 是完整的。"
                % DEFAULT_DEVICE,
                "DEVICE_DEFAULT_MISSING")
        raise DeviceError(
            "認不得的 device：%s" % name,
            "目前認得的是：%s。\n"
            "%s 由環境變數 %s 指定（工具端來自設定檔的 PPS_Device）。\n"
            "要新增一個 device，在 scripts/ai_analysis_gitlab_mr/device/ 底下建一個"
            "同名目錄即可。"
            % ("、".join(available) or "(無)", name, DEVICE_ENV),
            "DEVICE_UNKNOWN")

    return name


def _import(module_name, device, what):
    """載入一個模組，把失敗轉成說得出位置的 DeviceError。

    圖形介面的錯誤視窗只顯示結果訊息，不顯示診斷細節。而 device 腳本的開發者的迴路是
    「改腳本、按按鈕、看結果」—— 訊息裡沒有檔案與位置的話，那個迴路就轉不動。所以這裡
    自己攔下來，把 device 名、鉤子名與原始錯誤組進訊息。
    """
    # 剛建立的目錄要先讓 import 機制重新看一次。
    #
    # FileFinder 會快取每個目錄的內容，而它的失效判斷看的是目錄 mtime —— 在同一秒
    # 內新增一個 device 目錄時，那個快取可能還是舊的，於是「檔案明明在」卻得到
    # ModuleNotFoundError。這個功能的使用者正是「新增 device 目錄」的人，所以這一行
    # 值得。成本是微秒等級。
    importlib.invalidate_caches()
    try:
        return importlib.import_module(module_name)
    except SyntaxError as exc:
        raise DeviceError(
            "device %s 的 %s 有語法錯誤" % (device, what),
            "%s\n第 %s 行：%s" % (exc.filename or "(未知檔案)",
                                   exc.lineno or "?", exc.text or ""),
            "DEVICE_HOOK_SYNTAX_ERROR")
    except ImportError as exc:
        raise DeviceError(
            "device %s 的 %s 匯入失敗" % (device, what),
            "%s\n可能是它 import 了不存在的模組，或檔案本身不在。" % exc,
            "DEVICE_HOOK_IMPORT_ERROR")
    except Exception as exc:                        # noqa: BLE001
        # 模組層級的程式碼在 import 時就會執行，所以任何例外都可能從這裡冒出來。
        raise DeviceError(
            "device %s 的 %s 載入時發生錯誤" % (device, what),
            "%s: %s" % (exc.__class__.__name__, exc),
            "DEVICE_HOOK_LOAD_ERROR")


def load_hook(hook, device=None):
    """載入某個 device 的鉤子模組；該 device 沒有這個鉤子時用 default 的。

    **逐鉤子回退，不是逐 device。** 只想改報告版面的 device 不該被迫複製其他鉤子 ——
    那份複本會與 default 漸漸不同。device 本身不存在是另一回事，那在 resolve_name()
    就失敗了。

    模組以名稱載入（importlib），名稱從頭到尾不會被拿去組檔案路徑 —— 既有設計明文
    禁止「腳本輸出的字串變成被執行的路徑」。

    回傳 (模組, 實際提供這個鉤子的 device 名稱)。
    """
    assert hook in HOOK_NAMES, hook
    name = resolve_name() if device is None else device

    owner = name
    if not os.path.isfile(os.path.join(_HERE, name, "%s.py" % hook)):
        if name != DEFAULT_DEVICE:
            logger.debug("device %s 沒有 %s，改用 %s 的", name, hook, DEFAULT_DEVICE)
        owner = DEFAULT_DEVICE

    if not os.path.isfile(os.path.join(_HERE, owner, "%s.py" % hook)):
        raise DeviceError(
            "找不到 %s 鉤子" % hook,
            "device %s 與 %s 都沒有 %s.py。這是部署不完整，不是設定的問題。"
            % (name, DEFAULT_DEVICE, hook),
            "DEVICE_HOOK_MISSING")

    module = _import("%s.%s.%s" % (__name__, owner, hook), owner, "%s.py" % hook)
    return module, owner


def device_version(device=None):
    """讀出某個 device 自報的版本。沒有宣告視為錯誤。

    這個值會出現在報告末尾的出處資訊裡。若它可以是空的，那一行就無法說明報告是由哪
    一版邏輯產生的 —— 而那正是它存在的理由。
    """
    name = resolve_name() if device is None else device
    module = _import("%s.%s" % (__name__, name), name, "__init__.py")

    version = getattr(module, "VERSION", None)
    if not isinstance(version, str) or not version.strip():
        raise DeviceError(
            "device %s 沒有宣告 VERSION" % name,
            "請在 device/%s/__init__.py 加上 VERSION = \"1.0\"。\n"
            "報告末尾會標示這個版本；改了產出方式就把它往上加，否則新舊報告在外觀上"
            "分不出來。" % name,
            "DEVICE_VERSION_MISSING")
    return version.strip()
