#!/usr/bin/env python3
"""依 device 載入客製化的鉤子。

一個 MR 該怎麼分析，會因為它屬於哪一條產品線而不同。這個套件底下每一個目錄是一個
device，目錄名就是 device 名：

    device/
      default/          未指定 device 時用這一份
      ssd/              只放想覆寫的鉤子，缺的自動用 default 的
      _template/        底線開頭，不是 device

五個鉤子，分成兩類 —— 差別在**解析時要不要考慮種類**：

    不因種類而異
      jira_key.py            步驟 2：怎麼從 Merge Request 抽出 JIRA key
      mr_type.py             步驟 2：怎麼從 Merge Request 抽出種類
      parse_code_review.py   步驟 4：怎麼看懂別人的 code review 報告

    因種類而異
      summary.py      步驟 3：問 AI 什麼、怎麼解析、組出什麼分析內容
      merge_to_md.py  步驟 5：AI 分析那一段的版面

parse_code_review 不因種類而異是刻意的：那份報告的格式取決於**該產品線用哪一套 code
review 工具**，而不是這一筆 MR 是 bug 還是 feature。

種類（type）是第二個軸：同一個 device 底下，不同種類的 MR 可以走不同的 summary 與
merge_to_md。種類以子目錄表示：

    device/ssd/
      mr_type.py        取標題第二個方括號
      bug/summary.py    Bug 專用的 prompt，版面沿用 ssd 的
      newtestcase/      這個種類兩支都覆寫
        summary.py
        merge_to_md.py

**種類只在自己的 device 之內解析**（見 load_hook）。各 device 的字彙互相獨立 ——
認得哪些種類就是「有哪些子目錄」，不需要跨產品線的共識。

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
    "TYPED_HOOKS",
    "UNTYPED_HOOKS",
    "DeviceError",
    "resolve_name",
    "known_devices",
    "known_types",
    "normalize_type",
    "strict_type",
    "code_review_source_heading",
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

# 在種類被決定**之前**執行的鉤子。mr_type.py 就是決定它的那一支，所以種類這一層
# 對這兩支沒有意義 —— 它們維持兩段解析（<device>/ -> default/）。
UNTYPED_HOOKS = ("jira_key", "mr_type", "parse_code_review")

# 因種類而異的鉤子。三段解析（<device>/<type>/ -> <device>/ -> default/）。
TYPED_HOOKS = ("summary", "merge_to_md")

# 全部鉤子的模組名。分成上面兩組而不是在解析時用字串比對，是為了讓「這一支要不要
# 考慮種類」只有一個地方寫著 —— 散在各處的話，新增鉤子時一定會漏掉一處。
HOOK_NAMES = UNTYPED_HOOKS + TYPED_HOOKS

# device 與種類的名稱都只接受這個形狀。
#
# 名稱會被拿去 import，所以必須是合法的 Python 識別字 —— ssd_gen4 可以，ssd-gen4 不行。
# 這條檢查同時擋掉 "../../etc" 那類值。對種類而言這一點格外重要：種類的名字來自 MR
# 的標題，也就是任何能開 MR 的人打的字。通過這條檢查、且必須對應到一個已經部署的
# 目錄，兩者合起來使標題只能在既有的選項之間挑，帶不進任何新的程式碼。
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


def known_types(device=None):
    """某個 device 目前認得哪些種類，依名稱排序。

    掃該 device 底下的子目錄，與 known_devices() 同一個作法 —— **沒有中央的種類清單**。
    各 device 的字彙就是它有哪些目錄，兩條產品線不需要對彼此的字彙有任何共識。

    底線開頭的目錄不算，所以 __pycache__ 與種類範本都不會被誤認。

    一個沒有任何鉤子的空目錄仍算一個認得的種類。那是刻意的：搭配 STRICT_TYPE 時，
    建幾個空目錄正好可以宣告「這些種類我認得，但不需要客製」。
    """
    name = resolve_name() if device is None else device
    base = os.path.join(_HERE, name)
    if not os.path.isdir(base):
        return []

    names = []
    for entry in sorted(os.listdir(base)):
        if entry.startswith("_"):
            continue
        if os.path.isdir(os.path.join(base, entry)):
            names.append(entry)
    return names


def normalize_type(raw):
    """把鉤子抽出來的字串收斂成一個可用的種類名稱；不合用時回空字串。

    轉小寫是因為標題裡寫的是給人看的形式（`[NewTestCase]`），而目錄名一律小寫。

    **不合法的字串視同沒有種類，不報錯。** 那是 MR 作者打的字，不是部署者的錯誤，
    而兩者的後續處理相同（走通用版，或在嚴格模式下失敗）—— 分開回報只會多一種
    使用者無法行動的訊息。

    回傳非字串則是另一回事：那是鉤子寫壞了，所以明確失敗。把它當成「沒有種類」會讓
    一個壞掉的鉤子看起來像是這筆 MR 沒標種類。
    """
    if raw is None:
        return ""

    if not isinstance(raw, str):
        raise DeviceError(
            "mr_type 鉤子回傳的不是字串",
            "收到的型別是 %s。extract() 必須回傳一個字串；沒有種類就回空字串。"
            % type(raw).__name__,
            "DEVICE_HOOK_BAD_RETURN")

    name = raw.strip().lower()
    if not name:
        return ""

    if not _NAME_RE.match(name):
        logger.debug("種類 %r 不是合法的名稱，視同沒有種類", raw)
        return ""

    return name


def strict_type(device=None):
    """這個 device 是否要求每一筆 MR 都解析出認得的種類。未宣告時為 False。

    「MR 一定要標明種類」是一條團隊紀律，而紀律是各條產品線自己的事 —— 所以開關掛在
    device 上，不是全域的。字彙都不共用的兩條產品線，沒道理在這件事上必須一致。

    與 VERSION 不同，**這一項不是必填**：設成必填會讓每一個既有的 device 立刻失效，
    而它有一個明確且安全的預設值。

    型別不對時明確失敗，不做真值判斷 —— `STRICT_TYPE = "false"` 在 Python 裡是真，
    而寫成那樣的人想的是假。靜默照字串判斷會讓整條產品線在不知情的狀況下變嚴格。
    """
    name = resolve_name() if device is None else device
    module = _import("%s.%s" % (__name__, name), name, "__init__.py")

    value = getattr(module, "STRICT_TYPE", False)
    if not isinstance(value, bool):
        raise DeviceError(
            "device %s 的 STRICT_TYPE 不是布林值" % name,
            "收到的型別是 %s。請寫成 STRICT_TYPE = True 或 STRICT_TYPE = False"
            "（不要加引號）。" % type(value).__name__,
            "DEVICE_STRICT_TYPE_INVALID")
    return value


def code_review_source_heading(device=None, default=""):
    """這個 device 的 code review 報告裡，總表那一節叫什麼。未宣告時回 default。

    各條產品線的 code review 工具是各自的，產出格式不保證相同 —— 那一節不一定叫同一個
    名字。所以這個字串掛在 device 上。

    **這是一個宣告，不是鉤子。** 讀這個值本身不會載入或執行任何 device 的程式碼 ——
    變的只有「要找哪一節」這個字串，所以宣告寫壞了可以在任何網路往來之前就擋下來。

    步驟 4 本身**另外**會載入該 device 的 parse_code_review 鉤子（擷取與判定在那裡）。
    這個宣告的值由入口讀出來、當 heading 傳給那支鉤子 —— 既有 device 的宣告因此不必改，
    而「要找哪一節」仍然只有一個地方決定。

    default 由呼叫端明著傳入（入口腳本傳 ai_analysis_gitlab_mr.CODE_REVIEW_SOURCE_HEADING）
    而不是在這裡讀。這個模組是 ai_analysis_gitlab_mr 的子套件，反過來 import 母套件會
    形成一個沒必要的循環；而預設值屬於報告契約那一層，與另外兩個標題常數放在一起才不會
    走散。

    與 STRICT_TYPE 同樣**不是必填**：設成必填會讓每一個既有的 device 立刻失效，而它有
    一個明確的預設值。型別不對時明確失敗，不靜默 str() —— 一個寫錯成清單的宣告會讓比對
    永遠對不上，而那個症狀（報告說找不到那一節）指不出真正的原因。
    """
    name = resolve_name() if device is None else device
    module = _import("%s.%s" % (__name__, name), name, "__init__.py")

    value = getattr(module, "CODE_REVIEW_SOURCE_HEADING", None)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise DeviceError(
            "device %s 的 CODE_REVIEW_SOURCE_HEADING 不是非空字串" % name,
            "收到的型別是 %s。請寫成 CODE_REVIEW_SOURCE_HEADING = \"## 節名\"，"
            "或整行拿掉以沿用預設值。" % type(value).__name__,
            "DEVICE_CODE_REVIEW_HEADING_INVALID")
    return value.strip()


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


def _hook_file(owner, sub, hook):
    """某個候選位置的鉤子檔路徑。sub 為空字串代表 device 層。"""
    parts = [_HERE, owner] + ([sub] if sub else []) + ["%s.py" % hook]
    return os.path.join(*parts)


def load_hook(hook, device=None, mr_type=None):
    """載入鉤子模組，回傳 (模組, 實際提供它的 device 名稱)。

    **不因種類而異的鉤子**（見 UNTYPED_HOOKS）忽略 mr_type，兩段解析：

        <device>/   ->   default/

    **因種類而異的鉤子**（見 TYPED_HOOKS）三段解析：

        <device>/<type>/   ->   <device>/   ->   default/

    **刻意不找 default/<type>/。** 各 device 的種類字彙互相獨立且各自演化，同一個名稱
    在兩個 device 下不保證是同一件事 —— SD 的 tool 與 SSD 的 tool 若意思不同，跨過去
    取用就是套上另一條產品線的邏輯，而每一個步驟都會回報成功。那正是「未知的 device
    必須失敗」當初要避免的失敗形狀。

    少了那一段還有一個附帶的好處：**解析順序沒有任何模稜兩可之處**。四段的話就必須
    裁決「我自己的通用版」與「預設的種類版」孰先，而兩種答案都講得通 —— 講得通的兩種
    優先序，就是之後每個人都會搞錯的地方。

    種類目錄不需要 __init__.py（namespace package），所以「放一個目錄進去」字面上就是
    新增一個種類。

    逐鉤子回退：種類目錄只放 summary.py 是合法的，merge_to_md 會落到下一段。只想改
    prompt 的種類不該被迫複製版面，那份複本會漸漸漂移。

    回傳的第二個值是 **device 名稱**，不含種類 —— 呼叫端把它當成「這是哪一個 device」
    使用（含交給鉤子的 inputs）。錯誤訊息裡要指名種類的話，載入失敗由這裡處理（見下面
    的 what），執行期的例外由呼叫端自己組（它手上有 mr_type）。
    """
    assert hook in HOOK_NAMES, hook
    name = resolve_name() if device is None else device

    type_name = normalize_type(mr_type) if hook in TYPED_HOOKS else ""

    candidates = []
    if type_name:
        candidates.append((name, type_name))
    candidates.append((name, ""))
    if name != DEFAULT_DEVICE:
        candidates.append((DEFAULT_DEVICE, ""))

    for owner, sub in candidates:
        if not os.path.isfile(_hook_file(owner, sub, hook)):
            continue

        if (owner, sub) != (name, type_name):
            logger.debug("%s 取自 %s（原本要找 %s）", hook,
                         "%s/%s" % (owner, sub) if sub else owner,
                         "%s/%s" % (name, type_name) if type_name else name)

        parts = [__name__, owner] + ([sub] if sub else []) + [hook]
        what = "%s/%s.py" % (sub, hook) if sub else "%s.py" % hook
        return _import(".".join(parts), owner, what), owner

    raise DeviceError(
        "找不到 %s 鉤子" % hook,
        "找過這些位置都沒有 %s.py：%s。\n"
        "這是部署不完整，不是設定的問題。"
        % (hook, "、".join("%s/%s" % (o, sub) if sub else "%s/" % o
                           for o, sub in candidates)),
        "DEVICE_HOOK_MISSING")


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
