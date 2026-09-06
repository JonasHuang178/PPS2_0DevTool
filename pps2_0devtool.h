#ifndef PPS2_0DEVTOOL_H
#define PPS2_0DEVTOOL_H

#include "PythonRunner.h"
#include "json.h"

#include <QElapsedTimer>
#include <QJsonObject>
#include <QMainWindow>
#include <QMap>
#include <QString>
#include <QSystemTrayIcon>

QT_BEGIN_NAMESPACE
namespace Ui { class PPS2_0DevTool; }
QT_END_NAMESPACE

class ProcessingDialog;

// 應用程式外殼。
//
// 最高原則：Qt 只負責 GUI —— 讓使用者「選擇」。真正的實作寫在 Python。
// 外殼本身不含任何業務邏輯。
//
// 新增一個功能的步驟：
//   1. 建立 <功能名>.{h,cpp}，一個 QObject 子類別，建構子用 getFunctionConfig() 取設定
//   2. 在 pps2_0devtool.ui 加一個 tab，標題就是功能名稱
//   3. 在 setupToolService() 建立實例；UI_Init() 依 isFunctionVisible() 決定是否
//      removeTabByTitle()；UI_SetupSignal() 連接該 tab 的元件
//   4. 在 PPS2_0DevTool.json 的 Function 加設定區塊
//   5. 在 PPS2_0DevTool.pro 的 SOURCES / HEADERS 加檔案
//   6. 複製 scripts/_function_template.py 寫對應的腳本
//
// 不需要修改 json.cpp。

class PPS2_0DevTool : public QMainWindow
{
    Q_OBJECT

public:
    explicit PPS2_0DevTool(const Config &config, QWidget *parent = Q_NULLPTR);
    ~PPS2_0DevTool();

    // --- 腳本執行 API ---
    //
    // 非同步：立即回傳是否成功啟動，結果經由 onDone 送達。
    // 取消時 onDone 不會被呼叫 —— 這是「取消後畫面完全不動」的物理保證。
    //
    // tool 身分不放進信封，改由環境變數 TOOLNAME / TOOLVERSION 傳遞。
    // source_path 與 config 由外殼自動填入，功能不需傳。
    bool runFunctionScript(const QString &functionName,
                           const QString &scriptPath,
                           const QString &action,
                           const QJsonObject &params,
                           PythonRunner::ResultCallback onDone,
                           const QMap<QString, QString> &envVars =
                               QMap<QString, QString>());

    // --- 設定查詢（功能自己取自己的區塊）---
    QJsonObject getFunctionConfig(const QString &functionName) const;
    bool        isFunctionVisible(const QString &functionName) const;

    // --- 共用服務 ---
    void showUI_InfoMessageBox(const QString &text);
    void showUI_WarningMessageBox(const QString &text);
    void showUI_ErrorMessageBox(const QString &text);
    void showResultDialog(const QString &title, const QString &content,
                          qint64 elapsedMs);
    QString getUI_sourcePathLineEditText() const;
    bool    removeTabByTitle(const QString &title);

signals:
    // 功能唯一的掛勾。不需要來源路徑的功能不連接即可。
    void sourcePathChanged(const QString &sourceFilePath);
    void workingDataCleared();

protected:
    void closeEvent(QCloseEvent *event) Q_DECL_OVERRIDE;

private slots:
    void onBrowseSourcePath();
    void onClearSourcePath();
    void onSourcePathEdited();
    void onAbout();
    void onTrayActivated(QSystemTrayIcon::ActivationReason reason);
    void onScriptProgress(const QString &stage);
    void onScriptRunFinished();
    void onCancelRequested();

private:
    void setupToolService();
    void UI_Init();
    void UI_SetupSignal();
    void setupTrayIcon();

    Ui::PPS2_0DevTool *ui;

    Config             m_config;
    PythonRunner      *m_runner;
    ProcessingDialog  *m_processingDialog;
    QSystemTrayIcon   *m_trayIcon;
    QElapsedTimer      m_runTimer;
    QString            m_lastSourcePath;
};

#endif // PPS2_0DEVTOOL_H
