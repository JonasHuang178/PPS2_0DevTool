#!/usr/bin/env python3
"""系統層面的共用 API：檔案系統、暫存目錄、環境變數與路徑表示法。

放這裡的東西不認得任何一個應用功能 —— 它們是「作業系統提供什麼」的薄封裝，
任何功能都能拿去用。只服務單一功能的邏輯不屬於這裡，應該留在該功能自己的
目錄下。

這一個分組刻意是**單一檔案**而不是套件目錄。呼叫端一律以
`from script_utils import system_utils` 取用，兩種形式在 import 端完全相同，
但套件目錄要多維護一份 `__init__.py` 的再匯出清單 —— 漏掉一筆的症狀是「函式
明明寫好了卻搆不到」。等這裡真的長到翻不動時再拆回目錄，`__init__.py` 照樣
re-export，呼叫端不必改。

分組本身仍依技術領域劃分（見 openspec/specs/script-envelope）：是檔案還是
目錄不影響那條規則，system_utils 就是「系統層面」那一組。
"""

import os
import re
import tempfile

from script_utils import logger

__all__ = [
    "create_folder",
    "list_files_by_suffix",
    "read_lines",
    "write_lines",
    "temp_file_path",
    "get_env_var",
    "to_windows_path_format",
]


# --- 檔案系統 --------------------------------------------------------------

def create_folder(folder_path):
    """建立資料夾，路徑中缺少的上層目錄一併建立。

    資料夾已經存在是**成功**而非錯誤：腳本必須可重入（同樣的輸入重跑不產生
    額外的副作用），把「已經在那裡了」當成失敗會讓重跑的流程在第二次就斷掉。

    路徑已存在但不是資料夾時拋出 ValueError —— 這種情況靜默通過的話，之後
    往裡面寫檔會在別的地方以難懂的錯誤爆開，離真正的成因很遠。

    回傳建立後的絕對路徑，供呼叫端記錄或往下組路徑用。

    權限不足等作業系統層級的失敗以 OSError 原樣拋出 —— 共用模組不結束行程，
    是否中止由入口腳本決定。
    """
    if not isinstance(folder_path, str) or not folder_path.strip():
        raise ValueError("資料夾路徑必須是非空字串：%r" % (folder_path,))

    absolute = os.path.abspath(folder_path)

    if os.path.exists(absolute) and not os.path.isdir(absolute):
        raise ValueError("路徑已存在但不是資料夾：%s" % absolute)

    existed = os.path.isdir(absolute)

    # exist_ok=True 連同上層目錄一起建立，且已存在時不拋例外。
    os.makedirs(absolute, exist_ok=True)

    if existed:
        logger.debug("資料夾已存在：%s", absolute)
    else:
        logger.debug("建立資料夾：%s", absolute)

    return absolute


def list_files_by_suffix(directory, suffix, recursive=False):
    """列出 directory 中副檔名為 suffix 的檔案。

    suffix 含點，例如 ".cpp"。比對**不分大小寫** —— Windows 的檔案系統本身
    就不分，只收小寫會讓使用者看不到自己明明放在那裡的 .CPP。

    預設不遞迴。需要整棵樹時明著傳 recursive=True，不要讓呼叫端在「只想要
    這一層」時意外收到幾千筆。

    回傳 [{"name": 檔名, "path": 絕對路徑}, ...]。

    目錄中沒有符合的檔案是正常結果，回傳空清單而不是拋出例外。
    """
    if not os.path.isdir(directory):
        raise ValueError("路徑不是一個目錄：%s" % directory)

    wanted = suffix.lower()
    entries = []

    if recursive:
        for root, _dirs, names in os.walk(directory):
            for name in names:
                if os.path.splitext(name)[1].lower() == wanted:
                    entries.append({"name": name,
                                    "path": os.path.abspath(os.path.join(root, name))})
    else:
        for name in os.listdir(directory):
            full = os.path.join(directory, name)
            if not os.path.isfile(full):
                continue
            if os.path.splitext(name)[1].lower() != wanted:
                continue
            entries.append({"name": name, "path": os.path.abspath(full)})

    logger.debug("在 %s 找到 %d 個 %s（recursive=%s）",
                 directory, len(entries), suffix, recursive)
    return entries


def read_lines(path):
    """讀出行式文字檔的內容，去掉空白行。

    檔案不存在時回傳空清單而不是拋出例外 —— 對呼叫端而言「還沒建立」與
    「內容是空的」是同一件事。
    """
    if not os.path.isfile(path):
        logger.debug("檔案尚不存在：%s", path)
        return []

    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read().splitlines()

    lines = []
    for line in raw:
        line = line.strip()
        if line:
            lines.append(line)

    logger.debug("自 %s 讀出 %d 行", path, len(lines))
    return lines


def write_lines(path, lines):
    """把每一行寫入檔案，覆蓋原有內容。空白行會被略過。

    lines 為空時寫入空內容 —— 那是有效的結果，不是錯誤。

    回傳實際寫入的行數。
    """
    cleaned = []
    for line in lines:
        line = str(line).strip()
        if line:
            cleaned.append(line)

    with open(path, "w", encoding="utf-8") as handle:
        for line in cleaned:
            handle.write(line + "\n")

    logger.debug("寫入 %s，共 %d 行", path, len(cleaned))
    return len(cleaned)


# --- 暫存目錄 --------------------------------------------------------------

def temp_file_path(name):
    """回傳系統暫存目錄下某個檔名的絕對路徑。

    tempfile.gettempdir() 在各平台解析為：

        Windows        %TEMP%（通常是 C:\\Users\\<user>\\AppData\\Local\\Temp）
        Linux / macOS  $TMPDIR 或 /tmp

    每個使用者的暫存目錄互相獨立，多人共用同一台機器不會互相蓋掉。

    注意：Windows 的磁碟清理與「儲存空間感知」會清理 %TEMP%，放在這裡的
    檔案可能在重新開機或系統維護後消失。需要跨重啟保留的資料不該用這裡，
    正確的去處是 %LOCALAPPDATA%。
    """
    return os.path.join(tempfile.gettempdir(), name)


# --- 環境變數 --------------------------------------------------------------

def get_env_var(var_name, default_value=None):
    """讀出環境變數 var_name，未設定時回傳 default_value。

    這是給**入口腳本**用的薄封裝。共用模組不得拿它來自行取得自己需要的
    設定 —— 那條規則（見 openspec/specs/script-envelope）沒有因為這個函式
    存在而鬆動：所需的值仍然由呼叫端明著傳入，讀環境變數是入口腳本的職責。
    典型用法是入口腳本讀 TOOLNAME / TOOLVERSION，再把值當參數傳下去。

    「未設定」涵蓋三種情況：變數不存在、值為空字串、值只有空白。三者對呼叫端
    而言是同一件事 —— 拿不到可用的值 —— 分開處理只會讓每個呼叫端各寫一次
    同樣的判斷。判定與 script_io 的必填檢查一致。

    值本身原樣回傳，不做 strip：要不要去掉前後空白由呼叫端決定，這裡代為
    修剪會讓「刻意帶空白的值」無法傳遞。

    var_name 不是非空字串時拋出 ValueError —— 共用模組不結束行程，是否要
    中止由入口腳本決定。
    """
    if not isinstance(var_name, str) or not var_name.strip():
        raise ValueError("環境變數名稱必須是非空字串：%r" % (var_name,))

    value = os.environ.get(var_name)

    # 只記名稱與有無，不記值 —— 環境變數是權杖與密碼最常見的傳遞方式，
    # 而 Debug_Mode 開啟時這行會出現在 console 上。
    if value is None or value.strip() == "":
        logger.debug("環境變數 %s 未設定，使用預設值", var_name)
        return default_value

    logger.debug("環境變數 %s 已設定", var_name)
    return value


# --- 路徑表示法 ------------------------------------------------------------
#
# 底下的轉換**不碰檔案系統**，也不看自己跑在哪個作業系統上：純粹是字串轉換，
# 在 Windows 與 Linux 上得到完全相同的結果。腳本在 Linux 或 CI 上被直接執行、
# 而處理的是 Windows 風格的 source_path，是本專案明確支援的用法。
#
# 注意這不是「自行串接分隔符號」的許可（見 openspec/specs/script-envelope 的
# 跨平台要求）：組路徑一律用 os.path.join，只有在**確定要輸出成 Windows 樣子**
# 的那一刻才呼叫這裡 —— 寫進給 Windows 工具吃的檔案、或顯示給使用者看。

# 兩種分隔符號都收：來源可能是 Qt、Python、設定檔或使用者手打，混用很常見。
_SEPARATOR_RUN = re.compile(r"[\\/]+")


def to_windows_path_format(path_string):
    """把路徑字串轉成 Windows 表示法：分隔符號一律為反斜線。

    連續的分隔符號收斂成一個，但**開頭的兩個保留**（`\\\\server\\share` 的
    UNC 路徑與 `\\\\?\\C:\\...` 的長路徑前綴都靠那兩個反斜線辨識，收斂掉就
    指向別的地方了）。

    結尾的分隔符號保留（只收斂成一個）：`C:\\proj\\` 與 `C:\\proj` 在某些
    Windows 工具眼中是不同的輸入，代為刪掉會改變呼叫端的意思。

    相對路徑**不會**被轉成絕對路徑。在 Linux 上執行時，「絕對化」只能以
    Linux 的當前目錄為基準，那對一個要交給 Windows 用的路徑毫無意義。

    空字串原樣回傳，不視為錯誤 —— 信封的 `source_path` 允許為空，這裡
    拋例外的話每個呼叫端都得先寫一次 if。

    path_string 不是字串時拋出 ValueError。
    """
    if not isinstance(path_string, str):
        raise ValueError("路徑必須是字串：%r" % (path_string,))

    if not path_string:
        return ""

    leading = ""
    body = path_string

    match = _SEPARATOR_RUN.match(path_string)
    if match:
        # 開頭兩個以上 = UNC 或長路徑前綴，保留兩個；單一個就是根目錄。
        leading = "\\\\" if len(match.group(0)) >= 2 else "\\"
        body = path_string[match.end():]

    return leading + _SEPARATOR_RUN.sub(r"\\", body)
