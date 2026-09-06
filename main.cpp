#include "debug.h"
#include "json.h"
#include "pps2_0devtool.h"
#include "result_code.h"
#include "version.h"

#include <QApplication>
#include <QDateTime>
#include <QDir>
#include <QFile>
#include <QIcon>
#include <QList>
#include <QMessageBox>
#include <QProcess>
#include <QSharedMemory>
#include <QStringList>
#include <QTextStream>

#include <csignal>
#include <cstdlib>

namespace {

// --- crash handler ---------------------------------------------------------

void writeCrashLog(int signalNumber)
{
    const QString path = QDir(QCoreApplication::applicationDirPath())
            .absoluteFilePath("crash.log");

    QFile file(path);
    if (!file.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text))
        return;

    QTextStream out(&file);
    out << "----\n";
    out << QDateTime::currentDateTime().toString("yyyy-MM-dd HH:mm:ss.zzz")
        << " " << TOOL_NAME << " " << TOOL_VERSION
        << " signal " << signalNumber << "\n";

    const QStringList ring = Debug::ringBuffer();
    for (int i = 0; i < ring.size(); ++i)
        out << ring.at(i) << "\n";

    file.close();
}

extern "C" void crashHandler(int signalNumber)
{
    writeCrashLog(signalNumber);
    std::signal(signalNumber, SIG_DFL);
    std::raise(signalNumber);
}

// --- Python 3 檢查 ---------------------------------------------------------

bool detectPython3(QString *foundCommand)
{
    QStringList candidates;
#ifdef Q_OS_WIN
    candidates << "python" << "python3" << "py";
#else
    candidates << "python3" << "python";
#endif

    for (int i = 0; i < candidates.size(); ++i) {
        QProcess process;
        process.start(candidates.at(i), QStringList() << "--version");
        if (!process.waitForStarted(3000))
            continue;
        if (!process.waitForFinished(5000)) {
            process.kill();
            continue;
        }

        const QString output = QString::fromUtf8(process.readAllStandardOutput())
                + QString::fromUtf8(process.readAllStandardError());
        if (output.contains("Python 3")) {
            if (foundCommand)
                *foundCommand = candidates.at(i);
            return true;
        }
    }
    return false;
}

// --- 應用程式圖示 ----------------------------------------------------------

// 七個尺寸各自加入，讓 Qt 依顯示情境挑最接近的一張，而不是拿 256x256 即時
// 縮到 16x16 —— 貓臉的條紋與墨鏡在那樣縮圖後會糊成一團。
//
// 圖示內嵌在執行檔裡（見 resources.qrc），不讀外部檔案：執行檔旁已經必須放
// 設定檔與 scripts/，圖示不該再多一個掉了就出問題的部署項目。
QIcon buildAppIcon()
{
    QList<int> sizes;
    sizes << 16 << 24 << 32 << 48 << 64 << 128 << 256;

    QIcon icon;
    for (int i = 0; i < sizes.size(); ++i)
        icon.addFile(QString(":/icons/app_icon_%1.png").arg(sizes.at(i)));
    return icon;
}

} // namespace

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    app.setApplicationName(TOOL_NAME);
    app.setApplicationVersion(TOOL_VERSION);

    // 必須早於底下任何一個 QMessageBox —— 重複啟動、設定檔錯誤與缺少
    // Python 3 這三個訊息框都在主視窗建立之前顯示，而那正是使用者最可能
    // 第一次看到本程式的時機。
    app.setWindowIcon(buildAppIcon());

    // 關閉主視窗時隱藏到系統匣，所以不能讓最後一個視窗關閉就結束程式。
    app.setQuitOnLastWindowClosed(false);

    // --- 單一實例鎖 -------------------------------------------------------
    // Windows 上行程結束時由作業系統回收，不會留下 stale lock。
    QSharedMemory singleInstanceLock("PPS2_0DevTool_SingleInstance");
    if (!singleInstanceLock.create(1)) {
        QMessageBox::warning(Q_NULLPTR, TOOL_NAME,
                             QString("%1 已經在執行中。").arg(TOOL_NAME));
        return RC_OK;
    }

    // --- crash handler ----------------------------------------------------
    std::signal(SIGSEGV, crashHandler);
    std::signal(SIGABRT, crashHandler);

    // --- 設定檔 -----------------------------------------------------------
    const QString configPath = QDir(QCoreApplication::applicationDirPath())
            .absoluteFilePath(CONFIG_FILE_NAME);

    Config config;
    QString configError;
    const Config::LoadStatus status = config.load(configPath, &configError);
    if (status != Config::LoadOk) {
        // 每個功能區塊都必須提供 Program，沒有設定檔時所有功能都不能跑 ——
        // 讓程式帶著空設定啟動只會讓使用者在每個 tab 都撞牆。
        QMessageBox::critical(Q_NULLPTR, TOOL_NAME, configError);
        return (status == Config::LoadParseError) ? RC_CONFIG_PARSE_FAILED
                                                  : RC_CONFIG_FILE_NOT_FOUND;
    }

    // 讀完設定才知道 Debug_Mode，因此 console 在這裡才開。
    Debug::init(config.debugMode());
    QTDebug(QString("設定檔載入完成：%1").arg(configPath));

    // --- Python 3 檢查 ----------------------------------------------------
    QString pythonCommand;
    if (!detectPython3(&pythonCommand)) {
        QMessageBox::critical(Q_NULLPTR, TOOL_NAME,
                              QString("找不到可用的 Python 3。\n\n"
                                      "請安裝 Python 3 並確認它在 PATH 中，"
                                      "或在設定檔的 Program 欄位指定完整路徑。"));
        return RC_PROCESS_FAILED_TO_START;
    }
    QTDebug(QString("偵測到 Python 3：%1").arg(pythonCommand));

    PPS2_0DevTool window(config);
    window.show();

    return app.exec();
}
