#include "debug.h"
#include "version.h"

#include <QAtomicInteger>
#include <QDateTime>
#include <QMutex>
#include <QMutexLocker>

#include <cstdio>

#ifdef Q_OS_WIN
#include <windows.h>
#endif

namespace {

const int kRingCapacity = 300;

QMutex      g_mutex;
QStringList g_ring;
bool        g_debugMode = false;

QAtomicInteger<qint64> g_childPid(0);

const char *levelName(Debug::Level level)
{
    // 固定寬度 10，與 Python 端對齊。
    switch (level) {
    case Debug::LevelDebug: return " QT DEBUG ";
    case Debug::LevelWarn:  return " QT WARN  ";
    case Debug::LevelError: return " QT ERROR ";
    }
    return " QT ????? ";
}

QString timestamp()
{
    return QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz");
}

// 呼叫前必須已持有 g_mutex。
void appendToRing(const QString &line)
{
    g_ring.append(line);
    while (g_ring.size() > kRingCapacity)
        g_ring.removeFirst();
}

// 呼叫前必須已持有 g_mutex。
void printToConsole(const QString &line)
{
    if (!g_debugMode)
        return;

    const QByteArray utf8 = line.toUtf8();
    std::fwrite(utf8.constData(), 1, static_cast<size_t>(utf8.size()), stdout);
    std::fputc('\n', stdout);
    std::fflush(stdout);
}

#ifdef Q_OS_WIN
// console 被關閉時，先終止腳本子行程再讓行程結束，避免留下孤兒行程。
//
// 這個處理常式在獨立的執行緒上執行，因此不碰任何 Qt 物件，
// 只以 Win32 API 直接終止已登記的行程 ID。
BOOL WINAPI consoleCtrlHandler(DWORD ctrlType)
{
    if (ctrlType == CTRL_CLOSE_EVENT
            || ctrlType == CTRL_C_EVENT
            || ctrlType == CTRL_BREAK_EVENT
            || ctrlType == CTRL_LOGOFF_EVENT
            || ctrlType == CTRL_SHUTDOWN_EVENT) {

        const qint64 pid = g_childPid.loadAcquire();
        if (pid != 0) {
            HANDLE h = OpenProcess(PROCESS_TERMINATE, FALSE, static_cast<DWORD>(pid));
            if (h != NULL) {
                TerminateProcess(h, 1);
                CloseHandle(h);
            }
        }
    }

    // 回傳 FALSE 讓預設處理常式接手並結束行程 —— 關閉 console 就關閉工具。
    return FALSE;
}
#endif // Q_OS_WIN

} // namespace

namespace Debug {

void init(bool debugMode)
{
    QMutexLocker locker(&g_mutex);
    g_debugMode = debugMode;

    if (!debugMode)
        return;

#ifdef Q_OS_WIN
    if (AllocConsole()) {
        SetConsoleOutputCP(CP_UTF8);
        SetConsoleCP(CP_UTF8);

        // AllocConsole() 建立的 console 沒有接上本行程的標準輸出控制代碼，
        // 不重導向的話所有輸出都會消失。
        // MinGW 未保證提供 freopen_s，使用標準 freopen。
        (void)std::freopen("CONOUT$", "w", stdout);
        (void)std::freopen("CONOUT$", "w", stderr);
        (void)std::freopen("CONIN$",  "r", stdin);

        SetConsoleCtrlHandler(consoleCtrlHandler, TRUE);
        SetConsoleTitleA(TOOL_NAME " - Debug Console");
    }
#endif
}

bool isDebugMode()
{
    QMutexLocker locker(&g_mutex);
    return g_debugMode;
}

void write(Level level, const QString &message)
{
    const QString line = QString("[%1] [%2] %3")
            .arg(timestamp())
            .arg(QString::fromLatin1(levelName(level)))
            .arg(message);

    QMutexLocker locker(&g_mutex);
    appendToRing(line);      // 環形緩衝一律寫入，與 Debug_Mode 無關
    printToConsole(line);    // console 只在 Debug_Mode 開啟時輸出
}

void writeRaw(const QString &line)
{
    QMutexLocker locker(&g_mutex);
    appendToRing(line);
    printToConsole(line);
}

QStringList ringBuffer()
{
    QMutexLocker locker(&g_mutex);
    return g_ring;
}

void setChildProcessId(qint64 pid)
{
    g_childPid.storeRelease(pid);
}

} // namespace Debug
