#include "PythonRunner.h"

#include "debug.h"
#include "version.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QJsonValue>
#include <QProcessEnvironment>
#include <QTimer>

namespace {

const int kKillGraceMs = 3000;

} // namespace

PythonRunner::PythonRunner(QObject *parent)
    : QObject(parent)
    , m_process(Q_NULLPTR)
    , m_state(Idle)
    , m_failedToStart(false)
{
}

PythonRunner::~PythonRunner()
{
    if (m_process && m_process->state() != QProcess::NotRunning) {
        m_process->kill();
        m_process->waitForFinished(1000);
    }
    Debug::setChildProcessId(0);
}

QString PythonRunner::resolveScriptPath(const QString &scriptPath)
{
    if (scriptPath.isEmpty())
        return scriptPath;

    // 設定檔中的腳本路徑是相對路徑，一律相對於執行檔目錄解析。
    // 若改為繼承行程的當前目錄，同一份設定檔在不同啟動方式（雙擊捷徑、
    // 命令列、開發環境執行）下會解析出不同結果。
    const QString appDir = QCoreApplication::applicationDirPath();
    return QDir(appDir).absoluteFilePath(QDir::fromNativeSeparators(scriptPath));
}

bool PythonRunner::start(const QString &program,
                         const QString &scriptPath,
                         const QJsonObject &envelope,
                         const QMap<QString, QString> &envVars,
                         bool verbose,
                         ResultCallback onDone,
                         QString *failureMessage)
{
    if (m_state != Idle) {
        // 對話框是 application-modal，使用者不可能觸發這條 ——
        // 能觸發的只有程式化的連續呼叫，那是程式缺陷，不是使用者操作錯誤，
        // 所以只記警告，不跳訊息框。
        QTWarn(QString("已有腳本在執行中，忽略這次執行請求（state=%1）")
               .arg(m_state == Running ? "Running" : "Cancelling"));
        if (failureMessage)
            *failureMessage = QString("已有腳本正在執行");
        return false;
    }

    const QString resolved = resolveScriptPath(scriptPath);

    // 先檢查腳本存在。不檢查的話 Python 會以 exit code 2 結束、訊息在
    // stderr，而 stderr 內容不被收集，使用者只會看到「腳本沒有回傳結果」，
    // 完全查不出是路徑打錯。
    if (!QFileInfo(resolved).isFile()) {
        const QString msg = QString("找不到腳本：\n%1")
                .arg(QDir::toNativeSeparators(resolved));
        QTError(msg);
        if (failureMessage)
            *failureMessage = msg;
        return false;
    }

    m_callback       = onDone;
    m_stderrResidual.clear();
    m_program        = program;
    m_failedToStart  = false;

    m_process = new QProcess(this);

    // --- 行程環境 ---
    QProcessEnvironment env = QProcessEnvironment::systemEnvironment();

    const QString appDir     = QCoreApplication::applicationDirPath();
    const QString scriptsDir = QDir(appDir).absoluteFilePath(SCRIPTS_DIR_NAME);

    const QString existingPath = env.value("PYTHONPATH");
    if (existingPath.isEmpty()) {
        // 原有值為空時不要留下前導分隔符號 —— 空字串在某些 Python 版本
        // 會被當成當前目錄加進 sys.path。
        env.insert("PYTHONPATH", QDir::toNativeSeparators(scriptsDir));
    } else {
        env.insert("PYTHONPATH",
                   existingPath + QDir::listSeparator()
                   + QDir::toNativeSeparators(scriptsDir));
    }

    env.insert("PYTHONUTF8", "1");
    env.insert("PYTHONUNBUFFERED", "1");   // 確保進度即時送達
    env.insert("TOOLNAME", TOOL_NAME);
    env.insert("TOOLVERSION", TOOL_VERSION);

    // 功能可再疊加自己的環境變數。
    for (QMap<QString, QString>::const_iterator it = envVars.constBegin();
         it != envVars.constEnd(); ++it) {
        env.insert(it.key(), it.value());
    }

    m_process->setProcessEnvironment(env);
    m_process->setWorkingDirectory(appDir);

    connect(m_process, SIGNAL(readyReadStandardError()),
            this, SLOT(onReadyReadStandardError()));
    connect(m_process, SIGNAL(finished(int, QProcess::ExitStatus)),
            this, SLOT(onFinished(int, QProcess::ExitStatus)));
#if QT_VERSION >= QT_VERSION_CHECK(5, 6, 0)
    connect(m_process, SIGNAL(errorOccurred(QProcess::ProcessError)),
            this, SLOT(onErrorOccurred(QProcess::ProcessError)));
#else
    connect(m_process, SIGNAL(error(QProcess::ProcessError)),
            this, SLOT(onErrorOccurred(QProcess::ProcessError)));
#endif

    QStringList args;
    args << resolved << "--request-stdin";
    if (verbose)
        args << "-v";   // Debug_Mode 開啟時讓 Python 的 DEBUG 也一起出來

    m_state = Running;

    QTDebug(QString("執行腳本：%1 %2").arg(program, args.join(' ')));

    m_process->start(program, args);

    // start() 是非同步的；FailedToStart 會經由 errorOccurred 抵達。
    // 這裡不呼叫 waitForStarted()，否則會阻塞事件迴圈。

    const QByteArray payload =
            QJsonDocument(envelope).toJson(QJsonDocument::Compact);
    m_process->write(payload);

    // 寫入 stdin 之後必須關閉寫入通道，否則腳本會永遠卡在讀 stdin。
    m_process->closeWriteChannel();

    Debug::setChildProcessId(m_process->processId());

    return true;
}

void PythonRunner::cancel()
{
    if (m_state != Running)
        return;

    m_state = Cancelling;
    QTDebug(QString("使用者取消，要求腳本行程終止"));

    if (m_process && m_process->state() != QProcess::NotRunning) {
        m_process->terminate();
        // 不能用 waitForFinished() —— 那會凍住事件迴圈，跑馬燈停轉。
        QTimer::singleShot(kKillGraceMs, this, SLOT(onKillTimeout()));
    } else {
        PythonRunnerResult ignored;
        finish(ignored);
    }
}

void PythonRunner::onKillTimeout()
{
    if (m_state == Cancelling && m_process
            && m_process->state() != QProcess::NotRunning) {
        QTWarn(QString("腳本行程 3 秒內未結束，強制終止"));
        m_process->kill();
    }
}

void PythonRunner::onReadyReadStandardError()
{
    drainStderr(false);
}

void PythonRunner::drainStderr(bool flushResidual)
{
    if (!m_process)
        return;

    m_stderrResidual += m_process->readAllStandardError();

    // 只處理到最後一個換行為止 —— readyRead 的資料可能斷在行中間。
    int newlineIndex = m_stderrResidual.lastIndexOf('\n');
    if (newlineIndex >= 0) {
        const QByteArray complete = m_stderrResidual.left(newlineIndex);
        m_stderrResidual.remove(0, newlineIndex + 1);

        // Python 端注入了 PYTHONUTF8=1，因此一律以 UTF-8 解碼。
        // 用系統地區編碼（Windows 繁中是 cp950）會讓所有中文變亂碼。
        const QStringList lines =
                QString::fromUtf8(complete).split('\n');
        for (int i = 0; i < lines.size(); ++i)
            processStderrLine(lines.at(i));
    }

    if (flushResidual && !m_stderrResidual.isEmpty()) {
        processStderrLine(QString::fromUtf8(m_stderrResidual));
        m_stderrResidual.clear();
    }
}

void PythonRunner::processStderrLine(const QString &rawLine)
{
    QString line = rawLine;
    if (line.endsWith('\r'))
        line.chop(1);
    if (line.isEmpty())
        return;

    // fast path：行首不是 '{' 就不必嘗試 JSON 解析。
    // 幾千行 log 每行都 parse 是浪費。
    if (line.startsWith('{')) {
        QJsonParseError err;
        const QJsonDocument doc =
                QJsonDocument::fromJson(line.toUtf8(), &err);
        if (err.error == QJsonParseError::NoError && doc.isObject()) {
            const QJsonObject obj = doc.object();
            if (obj.contains("progress")) {
                const QString stage =
                        obj.value("progress").toObject().value("stage").toString();
                emit progressStage(stage);
                return;
            }
        }
    }

    // 其餘視為診斷訊息。Debug_Mode 關閉時直接丟棄 —— 不收集、不進緩衝。
    if (Debug::isDebugMode())
        Debug::writeRaw(line);
}

void PythonRunner::onErrorOccurred(QProcess::ProcessError error)
{
    if (error != QProcess::FailedToStart)
        return;   // 其他錯誤（含 Crashed）仍會走 finished

    if (m_failedToStart)
        return;
    m_failedToStart = true;

    PythonRunnerResult result;
    result.hasJson  = false;
    result.success  = false;
    result.exitCode = -1;
    result.message  = QString("無法啟動 Python：找不到 '%1'。"
                              "請檢查設定檔的 Program 欄位").arg(m_program);
    QTError(result.message);

    finish(result);
}

void PythonRunner::onFinished(int exitCode, QProcess::ExitStatus exitStatus)
{
    if (m_failedToStart)
        return;   // 已在 onErrorOccurred 處理完畢

    drainStderr(true);   // 處理殘餘的最後一行

    PythonRunnerResult result;
    result.exitCode = exitCode;

    const QByteArray stdoutData =
            m_process ? m_process->readAllStandardOutput() : QByteArray();

    // 不管 exit code，一律先 parse stdout。
    // 腳本會為了 CI 而在失敗時 exit 1，那份寫著失敗原因的 JSON 不能因為
    // exit code 非 0 就被丟掉。
    //
    // 只做整段解析，沒有退回掃描：硬性限制已規定腳本不得印任何東西到
    // stdout，退回掃描的作用是在違規時靜默救回，而靜默救回的結果就是
    // 違規腳本永遠不會被修好。
    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(stdoutData, &parseError);

    if (parseError.error == QJsonParseError::NoError && doc.isObject()) {
        const QJsonObject obj = doc.object();

        result.hasJson   = true;
        result.result    = obj.value("result").toString();
        result.message   = obj.value("message").toString();
        result.detail    = obj.value("detail").toString();
        result.data      = obj.value("data").toObject();
        result.errorCode = obj.value("error").toObject().value("code").toString();

        // 比對不分大小寫。
        result.success =
                (result.result.compare(QString("PASS"), Qt::CaseInsensitive) == 0);

        if (result.message.isEmpty()) {
            result.message = result.success ? QString("執行完成")
                                            : QString("執行失敗");
        }
    } else {
        result.hasJson = false;
        result.success = false;

        if (exitStatus == QProcess::CrashExit) {
            result.message = QString("腳本異常終止 (exit code: %1)").arg(exitCode);
        } else {
            result.message = QString("腳本沒有回傳結果 (exit code: %1)").arg(exitCode);
        }
        QTError(result.message);
    }

    finish(result);
}

void PythonRunner::finish(const PythonRunnerResult &result)
{
    const bool wasCancelled = (m_state == Cancelling);

    ResultCallback callback = m_callback;
    m_callback = ResultCallback();

    teardownProcess();
    m_state = Idle;

    // 不論成敗或取消都要通知外殼收掉對話框。
    emit runFinished();

    if (wasCancelled) {
        // 取消後不呼叫 callback，不論收到什麼結果。
        // 這是「取消後畫面完全不動」的物理保證 —— 功能根本沒有機會碰 UI，
        // 不必依賴每個功能作者都正確地寫出取消分支。
        QTDebug(QString("該次執行已取消，結果丟棄"));
        return;
    }

    if (callback)
        callback(result);
}

void PythonRunner::teardownProcess()
{
    Debug::setChildProcessId(0);

    if (m_process) {
        m_process->disconnect(this);
        m_process->deleteLater();
        m_process = Q_NULLPTR;
    }
    m_stderrResidual.clear();
}
