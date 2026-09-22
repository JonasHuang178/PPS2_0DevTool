#!/usr/bin/env python3
"""檔案內容的讀寫。

跟**檔案內容**打交道的東西放這裡：讀進來、寫出去。向作業系統要東西的
（環境變數、建立目錄、列出目錄內容、暫存目錄位置、路徑格式）在 system_utils.py。

與其他共用模組遵守同一組規則（見 openspec/specs/script-envelope）：不印任何東西
到 stdout、不結束行程、不自行讀取設定檔或環境變數、回傳資料結構。
"""

import os
import shutil
import tempfile

from script_utils import logger

__all__ = ["read_file", "write_file", "get_lines", "replace_lines",
           "find_file_path", "copy_file", "move_file", "delete_file",
           "read_lines", "write_lines"]


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


def read_file(file_path):
    """讀出整個檔案的內容，回傳字串。

    以 UTF-8 解碼，內容原樣回傳 —— 不去空白行、不 strip、換行保留。要逐行處理
    且想略過空白行的，用 read_lines()。

    **檔案不存在時拋出 FileNotFoundError**，這點與 read_lines() 刻意不同。
    read_lines() 回空清單是因為它服務的情境裡「還沒建立」與「內容是空的」是
    同一件事（例如尚未存過的暫存設定檔）。read_file() 是通用讀取，路徑打錯時
    回空字串會讓錯誤裝成「檔案是空的」，而那個誤會會一路帶到很下游才爆開。

    非 UTF-8 的內容拋出 UnicodeDecodeError，不靜默替換 —— 共用模組不替呼叫端
    決定「壞掉的位元組可以忽略」。

    共用模組不結束行程：上述例外原樣拋出，是否中止由入口腳本決定。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()

    logger.debug("自 %s 讀出 %d 個字元", file_path, len(content))
    return content


def write_file(file_path, data):
    """把內容寫入檔案，覆蓋原有內容，回傳實際寫入的位元組數。

    data 為字串時以 UTF-8 編碼寫入；為 bytes 時原樣寫入二進位。兩種型別都收是
    因為呼叫端拿到的東西本來就兩種都有（文字報表 / 下載回來的檔案），而規則
    一句話講得完：字串當文字、bytes 當二進位。

    **覆蓋**既有檔案，不先問。理由是腳本必須可重入（見 openspec/specs/
    script-execution）：同樣的輸入重跑一次要得到同樣的結果，而不是第二次就因為
    「檔案已存在」而失敗。

    **不自動建立上層目錄**，目錄不存在時拋出 FileNotFoundError。自動建立會讓
    打錯的路徑靜默生出一棵沒人要的目錄樹，而使用者要等到「檔案怎麼不在我以為的
    地方」才發現。需要的話先呼叫 system_utils.create_folder()。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    if isinstance(data, bytes):
        with open(file_path, "wb") as handle:
            handle.write(data)
        written = len(data)
    elif isinstance(data, str):
        payload = data.encode("utf-8")
        with open(file_path, "wb") as handle:
            handle.write(payload)
        written = len(payload)
    else:
        raise ValueError("data 必須是字串或 bytes，收到 %s"
                         % type(data).__name__)

    logger.debug("寫入 %s，共 %d bytes", file_path, written)
    return written


def copy_file(source_path, target_path):
    """複製檔案，回傳複製後的絕對路徑。

    target_path 是**目的檔案的路徑**；若它是一個已存在的目錄，則複製進該目錄
    並沿用來源檔名（與 shutil 的慣例一致）。

    以 shutil.copy2 複製，連同修改時間與權限一併保留 —— 少了這些，複製出來的
    檔案在「比對哪份比較新」時會全部看起來像剛產生的。

    目的檔案已存在時**直接覆蓋**，與 write_file() 同一個理由：腳本要可重入，
    重跑不能因為「上一次已經複製過」而失敗。

    來源不存在、目的目錄不存在、來源與目的是同一個檔案，都以例外拋出
    （FileNotFoundError / shutil.SameFileError），由入口腳本決定怎麼回報。
    """
    for name, value in (("來源路徑", source_path), ("目的路徑", target_path)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("%s必須是非空字串：%r" % (name, value))

    if not os.path.isfile(source_path):
        # 先擋掉最常見的情況，錯誤訊息才指得出是哪一個路徑有問題 ——
        # 讓 shutil 自己去撞的話，訊息裡不會說那是「來源」還是「目的」。
        raise FileNotFoundError("來源檔案不存在：%s" % source_path)

    result = shutil.copy2(source_path, target_path)
    absolute = os.path.abspath(result)

    logger.debug("複製 %s -> %s", source_path, absolute)
    return absolute


def get_lines(file_path, start_line, end_line=None):
    """讀出檔案中某個行號區間的內容，回傳字串清單。

    行號**自 1 起算，且頭尾都包含** —— 「第 10 到 20 行」就是編輯器與編譯器
    訊息裡的那 10 行，不必在呼叫端自己 +1 / -1。end_line 傳 None 表示讀到檔尾。

    每一行都**去掉行尾換行**，但**空白行會保留**。保留空白行是必要的：這支函式
    的意義建立在「第幾行」上，一旦略過空白行，回傳的內容就對不上原始行號，而
    那種錯位在拿去比對編譯錯誤訊息時特別難查。要「略過空白行的清單」請用
    read_lines()。

    區間超出檔尾時取到檔尾為止，不視為錯誤；start_line 已經超過總行數時回傳
    空清單。讀取時逐行串流並在 end_line 就停，不把整個檔案拉進記憶體。

    檔案不存在拋 FileNotFoundError，非 UTF-8 拋 UnicodeDecodeError，與
    read_file() 一致。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    # bool 是 int 的子類別，True 會被當成 1 —— 明著擋掉，那一定是呼叫端寫錯了。
    if isinstance(start_line, bool) or not isinstance(start_line, int):
        raise ValueError("start_line 必須是整數：%r" % (start_line,))
    if start_line < 1:
        raise ValueError("start_line 自 1 起算，收到 %d" % start_line)

    if end_line is not None:
        if isinstance(end_line, bool) or not isinstance(end_line, int):
            raise ValueError("end_line 必須是整數或 None：%r" % (end_line,))
        if end_line < start_line:
            raise ValueError("end_line (%d) 不可小於 start_line (%d)"
                             % (end_line, start_line))

    lines = []
    with open(file_path, "r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if number < start_line:
                continue
            if end_line is not None and number > end_line:
                break          # 不讀完整個檔案，大檔時差很多
            lines.append(line.rstrip("\n").rstrip("\r"))

    logger.debug("自 %s 讀出第 %s~%s 行，共 %d 行",
                 file_path, start_line,
                 end_line if end_line is not None else "EOF", len(lines))
    return lines


def move_file(source_path, target_path):
    """搬移（或改名）檔案，回傳搬移後的絕對路徑。

    target_path 是目的檔案的路徑；若它是一個已存在的目錄，則搬進該目錄並沿用
    來源檔名。

    目的檔案已存在時**先刪掉再搬**，這一步是跨平台的關鍵：shutil.move 內部走
    os.rename，而 os.rename 在 POSIX 上會直接覆蓋、在 Windows 上卻會丟
    FileExistsError。不先刪的話，同一段程式在開發用的 Linux 上跑得好好的，
    部署到 Windows 就失敗 —— 而本專案的正式平台正是 Windows。

    覆蓋而非報錯的理由與 copy_file() 相同：腳本要可重入，重跑不能因為「上一次
    已經搬過」而失敗。

    來源不存在、目的目錄不存在都以例外拋出，由入口腳本決定怎麼回報。
    """
    for name, value in (("來源路徑", source_path), ("目的路徑", target_path)):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("%s必須是非空字串：%r" % (name, value))

    if not os.path.isfile(source_path):
        raise FileNotFoundError("來源檔案不存在：%s" % source_path)

    # 目的是既有目錄時，實際落點是該目錄下的同名檔案。要先算出來，
    # 底下「已存在就先刪」才知道該檢查哪一個路徑。
    destination = target_path
    if os.path.isdir(target_path):
        destination = os.path.join(target_path, os.path.basename(source_path))

    if os.path.isfile(destination) and not os.path.samefile(source_path,
                                                            destination):
        logger.debug("目的檔案已存在，先移除：%s", destination)
        os.remove(destination)

    shutil.move(source_path, destination)
    absolute = os.path.abspath(destination)

    logger.debug("搬移 %s -> %s", source_path, absolute)
    return absolute


def delete_file(file_path):
    """刪除檔案。回傳 True 表示真的刪掉了，False 表示它本來就不在。

    **檔案不存在不是錯誤** —— 與 system_utils.create_folder() 對「已經存在」的
    處理是同一個原則：腳本必須可重入，重跑一次「刪掉暫存檔」不該因為上一次已經
    刪過而失敗。回傳布林而不是一律回 True，是為了在「本來就不在」有意義的場合
    （例如統計真正清掉幾個）仍然分得出來。

    路徑是目錄時**拋出 ValueError**，不刪。這支函式叫 delete_file，讓它順手刪掉
    整棵目錄樹是災難等級的意外 —— 要刪目錄請明著用別的方式。

    權限不足等作業系統層級的失敗以 OSError 原樣拋出。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    if os.path.isdir(file_path):
        raise ValueError("路徑是目錄，delete_file 只刪檔案：%s" % file_path)

    if not os.path.exists(file_path):
        logger.debug("檔案本來就不存在：%s", file_path)
        return False

    os.remove(file_path)
    logger.debug("已刪除 %s", file_path)
    return True


def find_file_path(directory, file_name):
    """在 directory 底下遞迴尋找名為 file_name 的檔案，回傳絕對路徑。

    參數名是 directory 而不是 dir —— dir 會遮蔽 Python 內建的 dir()，而且與
    system_utils.list_files_by_suffix() 的第一個參數不一致。

    **找不到時回傳 None**，不拋例外。這與 read_file() 的「不存在就拋」刻意不同：
    read_file 的呼叫端已經認定那個檔案該在那裡，而「找找看」本來就包含「不在」
    這個正常答案。呼叫端要把「找不到」當失敗的話，自己判斷 None 後回報即可。

    **比對不分大小寫**，理由與 list_files_by_suffix() 相同：Windows 的檔案系統
    本身就不分，只收完全相符會讓使用者看不到自己明明放在那裡的檔案。

    同名檔案存在於多個子目錄時回傳**第一個**，並記一筆警告指出共有幾個 ——
    靜默挑一個而不說，之後「怎麼讀到別的檔案」會查很久。走訪次序經過排序，
    因此同一棵目錄樹每次跑都得到同一個結果；不排序的話 os.walk 的次序由檔案
    系統決定，同一份輸入可能回傳不同的檔案。

    走訪會把整棵樹掃完，不是找到第一個就停 —— 上面那筆「共有幾個」的警告需要
    完整的數量。代價是大目錄樹上會多花時間；換來的是「明明有兩個同名檔案」這件
    事一定被說出來，而不是靜默地挑一個。
    """
    if not isinstance(directory, str) or not directory.strip():
        raise ValueError("目錄路徑必須是非空字串：%r" % (directory,))
    if not isinstance(file_name, str) or not file_name.strip():
        raise ValueError("檔案名稱必須是非空字串：%r" % (file_name,))

    if not os.path.isdir(directory):
        raise ValueError("路徑不是一個目錄：%s" % directory)

    wanted = file_name.lower()
    matches = []

    for root, dirs, names in os.walk(directory):
        # 就地排序，讓走訪次序可重現（os.walk 的預設次序由檔案系統決定）。
        dirs.sort()
        for name in sorted(names):
            if name.lower() == wanted:
                matches.append(os.path.abspath(os.path.join(root, name)))

    if not matches:
        logger.debug("在 %s 底下找不到 %s", directory, file_name)
        return None

    if len(matches) > 1:
        logger.warn("在 %s 底下找到 %d 個 %s，回傳第一個：%s",
                    directory, len(matches), file_name, matches[0])

    logger.debug("找到 %s：%s", file_name, matches[0])
    return matches[0]


def replace_lines(file_path, start_line, end_line, new_content):
    """把檔案中某個行號區間換成新的內容，回傳置換後的總行數。

    行號語意與 get_lines() 完全一致：**自 1 起算、頭尾都包含**。兩支函式常常
    成對使用（先讀出來看、再換掉），語意若不一致，呼叫端一定會在某次差一行。

    new_content 收字串或字串清單。字串會依換行切開；清單的每一筆是一行，其中
    的換行字元會被去掉，不會產生半行。傳空字串或空清單表示**刪掉那個區間**，
    那是有效操作而非錯誤。

    檔案原本的換行風格（CRLF / LF）會被偵測並沿用於整個檔案，檔尾原本有沒有
    換行也維持原樣。不這麼做的話，在 Windows 編輯過的檔案被這支函式改過之後
    會變成混合換行，而 diff 會顯示整個檔案都變動了。

    start_line 超過總行數時拋出 ValueError —— 那通常代表呼叫端的行號來自另一
    個版本的檔案，靜默接受只會把新內容接到不相干的位置。end_line 超過檔尾則
    取到檔尾為止。

    寫入採「先寫暫存檔再原子置換」：中途失敗時原檔完好，不會留下半份被截斷的
    檔案。用 os.replace 而不是 os.rename，因為 rename 在 Windows 上遇到已存在
    的目的檔會失敗。
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("檔案路徑必須是非空字串：%r" % (file_path,))

    for name, value in (("start_line", start_line), ("end_line", end_line)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("%s 必須是整數：%r" % (name, value))
    if start_line < 1:
        raise ValueError("start_line 自 1 起算，收到 %d" % start_line)
    if end_line < start_line:
        raise ValueError("end_line (%d) 不可小於 start_line (%d)"
                         % (end_line, start_line))

    if isinstance(new_content, str):
        replacement = new_content.splitlines()
    elif isinstance(new_content, (list, tuple)):
        replacement = [str(line).rstrip("\n").rstrip("\r")
                       for line in new_content]
    else:
        raise ValueError("new_content 必須是字串或字串清單，收到 %s"
                         % type(new_content).__name__)

    # newline="" 讓換行字元原樣保留，才能看出原檔用的是 CRLF 還是 LF。
    with open(file_path, "r", encoding="utf-8", newline="") as handle:
        original = handle.read()

    newline = "\r\n" if "\r\n" in original else "\n"
    ends_with_newline = original.endswith(("\n", "\r"))
    lines = original.splitlines()

    if start_line > len(lines):
        raise ValueError("start_line (%d) 超過檔案總行數 (%d)：%s"
                         % (start_line, len(lines), file_path))

    updated = lines[:start_line - 1] + replacement + lines[end_line:]

    payload = newline.join(updated)
    if payload and ends_with_newline:
        payload += newline

    # 暫存檔建在同一個目錄：跨檔案系統時 os.replace 不是原子操作，
    # 而 %TEMP% 與目標檔常常不在同一顆磁碟。
    folder = os.path.dirname(os.path.abspath(file_path))
    handle_fd, temp_path = tempfile.mkstemp(dir=folder, suffix=".tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8", newline="") as temp:
            temp.write(payload)
        os.replace(temp_path, file_path)
    except BaseException:
        # 失敗時不要留下暫存垃圾；原檔此時尚未被動過。
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    logger.debug("%s 第 %d~%d 行換成 %d 行，總行數 %d -> %d",
                 file_path, start_line, end_line, len(replacement),
                 len(lines), len(updated))
    return len(updated)
