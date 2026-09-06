#ifndef DEBUG_H
#define DEBUG_H

#include <QString>
#include <QStringList>
#include <QtGlobal>

// Qt 端的診斷輸出。
//
// 格式與 Python 端的 script_utils/logger.py 對齊，因為兩邊的訊息會混在
// 同一個 debug console 裡：
//
//   [2026-09-06 14:30:12.345] [ QT DEBUG ] 來自 Qt
//   [2026-09-06 14:30:12.352] [ PY DEBUG ] 來自 Python
//
// 等級名稱一律補成固定寬度 10。

namespace Debug {

enum Level {
    LevelDebug,
    LevelWarn,
    LevelError
};

// 依 Debug_Mode 決定是否開啟 console。應在讀完設定檔後盡早呼叫。
void init(bool debugMode);

bool isDebugMode();

// 輸出一則 Qt 訊息：一律寫入環形緩衝，Debug_Mode 開啟時另外印到 console。
void write(Level level, const QString &message);

// 輸出一行已經格式化好的訊息（來自腳本的 stderr，已帶 [ PY XXXX ] 前綴）。
// 呼叫端負責判斷 Debug_Mode —— 關閉時腳本的診斷行直接丟棄，不進緩衝。
void writeRaw(const QString &line);

// 最近 300 行的環形緩衝內容。
QStringList ringBuffer();

// 登記目前執行中的腳本子行程 ID，供 console 關閉時清理；0 表示沒有。
// 這個值會被 console 控制處理常式（另一個執行緒）讀取，因此以原子操作存取。
void setChildProcessId(qint64 pid);

} // namespace Debug

#define QTDebug(msg) Debug::write(Debug::LevelDebug, (msg))
#define QTWarn(msg)  Debug::write(Debug::LevelWarn,  (msg))
#define QTError(msg) Debug::write(Debug::LevelError, (msg))

#endif // DEBUG_H
