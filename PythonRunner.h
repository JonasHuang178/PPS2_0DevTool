#ifndef PYTHONRUNNER_H
#define PYTHONRUNNER_H

#include <QJsonObject>
#include <QMap>
#include <QObject>
#include <QProcess>
#include <QString>

#include <functional>

// 腳本執行的 QProcess 封裝。
//
// 通道分離：
//   stdout  只有結果，單一 JSON object
//   stderr  除錯訊息與進度
//
// 一次只執行一支腳本，以「閒置 / 執行中 / 取消中」單一狀態管理。
// 用一堆布林旗標處理「腳本結束的同一瞬間使用者按取消」這個競態一定會出漏洞。

class PythonRunner : public QObject
{
    Q_OBJECT

public:
    struct PythonRunnerResult
    {
        bool        success;     // hasJson 且 result 等於 PASS（不分大小寫）
        bool        hasJson;     // 有沒有收到結果信封
        QString     result;      // "PASS" / "FAIL"
        QString     message;     // 一行，可直接顯示
        QString     detail;      // 多行
        QJsonObject data;        // 結構化結果
        QString     errorCode;   // error.code
        int         exitCode;

        PythonRunnerResult()
            : success(false), hasJson(false), exitCode(-1) {}
    };

    typedef std::function<void(const PythonRunnerResult &)> ResultCallback;

    enum State {
        Idle,
        Running,
        Cancelling
    };

    explicit PythonRunner(QObject *parent = Q_NULLPTR);
    ~PythonRunner();

    State state() const { return m_state; }
    bool  isIdle() const { return m_state == Idle; }

    // 啟動腳本。回傳是否成功啟動，不阻塞。
    //
    // scriptPath 可以是相對路徑，會相對於執行檔目錄解析。
    // 失敗時（忙碌、腳本不存在）回傳 false，並透過 failureMessage 說明原因。
    bool start(const QString &program,
               const QString &scriptPath,
               const QJsonObject &envelope,
               const QMap<QString, QString> &envVars,
               bool verbose,
               ResultCallback onDone,
               QString *failureMessage = Q_NULLPTR);

    // 使用者取消。terminate() 之後 3 秒仍在執行才 kill()，等待期間不阻塞
    // 事件迴圈。取消後不論收到什麼結果都不會呼叫 callback。
    void cancel();

    // 把相對腳本路徑解析為絕對路徑（相對於執行檔目錄）。
    static QString resolveScriptPath(const QString &scriptPath);

signals:
    // 腳本回報的階段文字。
    void progressStage(const QString &stage);

    // 這次執行結束（成功、失敗或取消都會發出），供外殼收掉處理中對話框。
    // 功能的 callback 在取消時不會被呼叫，但對話框仍必須關閉。
    void runFinished();

private slots:
    void onReadyReadStandardError();
    void onFinished(int exitCode, QProcess::ExitStatus exitStatus);
    void onErrorOccurred(QProcess::ProcessError error);
    void onKillTimeout();

private:
    void processStderrLine(const QString &line);
    void drainStderr(bool flushResidual);
    void finish(const PythonRunnerResult &result);
    void teardownProcess();

    QProcess       *m_process;
    State           m_state;
    ResultCallback  m_callback;
    QByteArray      m_stderrResidual;   // 跨讀取邊界的殘餘（可能斷在行中間）
    QString         m_program;
    bool            m_failedToStart;
};

#endif // PYTHONRUNNER_H
