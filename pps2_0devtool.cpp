#include "pps2_0devtool.h"
#include "ui_pps2_0devtool.h"

#include "ProcessingDialog.h"
#include "common.h"
#include "debug.h"
#include "result_code.h"
#include "version.h"

#include <QAction>
#include <QCloseEvent>
#include <QDialog>
#include <QDialogButtonBox>
#include <QFileDialog>
#include <QLabel>
#include <QMenu>
#include <QMessageBox>
#include <QPlainTextEdit>
#include <QStyle>
#include <QSystemTrayIcon>
#include <QVBoxLayout>

PPS2_0DevTool::PPS2_0DevTool(const Config &config, QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::PPS2_0DevTool)
    , m_config(config)
    , m_runner(new PythonRunner(this))
    , m_processingDialog(Q_NULLPTR)
    , m_trayIcon(Q_NULLPTR)
{
    ui->setupUi(this);

    setupToolService();
    UI_Init();
    UI_SetupSignal();
}

PPS2_0DevTool::~PPS2_0DevTool()
{
    delete ui;
}

// ---------------------------------------------------------------------------
// 建置
// ---------------------------------------------------------------------------

void PPS2_0DevTool::setupToolService()
{
    // 功能實例在這裡建立。目前沒有任何功能。
    QTDebug(QString("%1 %2 啟動").arg(TOOL_NAME, TOOL_VERSION));
}

void PPS2_0DevTool::UI_Init()
{
    setWindowTitle(QString("%1 %2").arg(TOOL_NAME, TOOL_VERSION));

    // 固定尺寸 1200x830。
    setFixedSize(1200, 830);

    ui->progressBar->setRange(0, 100);
    ui->progressBar->setValue(0);

    // 功能依 isFunctionVisible() 決定是否 removeTabByTitle()。
    // 目前沒有任何功能，tab widget 是空的。

    setupTrayIcon();
}

void PPS2_0DevTool::UI_SetupSignal()
{
    connect(ui->sourcePathBrowseButton, SIGNAL(clicked()),
            this, SLOT(onBrowseSourcePath()));
    connect(ui->sourcePathClearButton, SIGNAL(clicked()),
            this, SLOT(onClearSourcePath()));
    connect(ui->sourcePathLineEdit, SIGNAL(editingFinished()),
            this, SLOT(onSourcePathEdited()));
    connect(ui->actionAbout, SIGNAL(triggered()),
            this, SLOT(onAbout()));

    connect(m_runner, SIGNAL(progressStage(QString)),
            this, SLOT(onScriptProgress(QString)));
    connect(m_runner, SIGNAL(runFinished()),
            this, SLOT(onScriptRunFinished()));
}

void PPS2_0DevTool::setupTrayIcon()
{
    if (!QSystemTrayIcon::isSystemTrayAvailable()) {
        QTWarn(QString("系統匣不可用，關閉視窗將直接結束程式"));
        return;
    }

    m_trayIcon = new QSystemTrayIcon(this);
    m_trayIcon->setIcon(windowIcon().isNull()
                        ? style()->standardIcon(QStyle::SP_ComputerIcon)
                        : windowIcon());
    m_trayIcon->setToolTip(QString("%1 %2").arg(TOOL_NAME, TOOL_VERSION));

    // 右鍵選單只有 Quit。
    QMenu *menu = new QMenu(this);
    QAction *quitAction = menu->addAction(QString("Quit"));
    connect(quitAction, SIGNAL(triggered()), qApp, SLOT(quit()));
    m_trayIcon->setContextMenu(menu);

    // 用新式 connect（指標式）而不是 SIGNAL/SLOT 字串：
    // 字串式是執行期用簽章比對，型別對不上只會印一行警告然後靜默失效
    // —— 這裡原本把 ActivationReason 寫成 int，雙擊就一直沒有反應。
    // 指標式由編譯器檢查，同一類錯誤會直接變成編譯錯誤。
    connect(m_trayIcon, &QSystemTrayIcon::activated,
            this, &PPS2_0DevTool::onTrayActivated);

    m_trayIcon->show();
}

// ---------------------------------------------------------------------------
// 設定查詢
// ---------------------------------------------------------------------------

QJsonObject PPS2_0DevTool::getFunctionConfig(const QString &functionName) const
{
    return m_config.getFunctionConfig(functionName);
}

bool PPS2_0DevTool::isFunctionVisible(const QString &functionName) const
{
    return m_config.isFunctionVisible(functionName);
}

// ---------------------------------------------------------------------------
// 腳本執行
// ---------------------------------------------------------------------------

bool PPS2_0DevTool::runFunctionScript(const QString &functionName,
                                      const QString &scriptPath,
                                      const QString &action,
                                      const QJsonObject &params,
                                      PythonRunner::ResultCallback onDone,
                                      const QMap<QString, QString> &envVars)
{
    const QJsonObject functionConfig = getFunctionConfig(functionName);

    const QString program = functionConfig.value("Program").toString(
                QString("python"));

    // 信封四個欄位。tool 身分不在這裡 —— 走 TOOLNAME / TOOLVERSION 環境變數。
    QJsonObject envelope;
    envelope.insert("source_path", getUI_sourcePathLineEditText());
    envelope.insert("config",      functionConfig);
    envelope.insert("action",      action);
    envelope.insert("params",      params);

    QString failureMessage;
    m_runTimer.start();

    const bool started = m_runner->start(program,
                                         scriptPath,
                                         envelope,
                                         envVars,
                                         m_config.debugMode(),   // Debug_Mode 連動 -v
                                         onDone,
                                         &failureMessage);
    if (!started) {
        // 忙碌時只記警告不跳訊息框（見 PythonRunner::start）。
        // 腳本不存在等啟動前失敗則要讓使用者看到。
        if (!m_runner->isIdle())
            return false;

        showUI_ErrorMessageBox(failureMessage);
        return false;
    }

    delete m_processingDialog;
    m_processingDialog = new ProcessingDialog(functionName, this);
    connect(m_processingDialog, SIGNAL(cancelRequested()),
            this, SLOT(onCancelRequested()));
    m_processingDialog->show();

    return true;
}

void PPS2_0DevTool::onScriptProgress(const QString &stage)
{
    if (m_processingDialog)
        m_processingDialog->setStage(stage);
}

void PPS2_0DevTool::onCancelRequested()
{
    m_runner->cancel();
}

void PPS2_0DevTool::onScriptRunFinished()
{
    // 不論成功、失敗或取消都要收掉對話框。
    if (m_processingDialog) {
        m_processingDialog->hide();
        m_processingDialog->deleteLater();
        m_processingDialog = Q_NULLPTR;
    }

    QTDebug(QString("腳本執行結束，耗時 %1")
            .arg(formatElapsedTime(m_runTimer.elapsed())));
}

// ---------------------------------------------------------------------------
// 共用服務
// ---------------------------------------------------------------------------

void PPS2_0DevTool::showUI_InfoMessageBox(const QString &text)
{
    QMessageBox::information(this, TOOL_NAME, text);
}

void PPS2_0DevTool::showUI_WarningMessageBox(const QString &text)
{
    QMessageBox::warning(this, TOOL_NAME, text);
}

void PPS2_0DevTool::showUI_ErrorMessageBox(const QString &text)
{
    QMessageBox::critical(this, TOOL_NAME, text);
}

void PPS2_0DevTool::showResultDialog(const QString &title,
                                     const QString &content,
                                     qint64 elapsedMs)
{
    QDialog dialog(this);
    dialog.setWindowTitle(title);
    dialog.resize(800, 500);

    QVBoxLayout *layout = new QVBoxLayout(&dialog);

    QPlainTextEdit *view = new QPlainTextEdit(&dialog);
    view->setReadOnly(true);
    view->setPlainText(content);
    layout->addWidget(view);

    QLabel *elapsed = new QLabel(
                QString("Elapsed: %1").arg(formatElapsedTime(elapsedMs)), &dialog);
    layout->addWidget(elapsed);

    QDialogButtonBox *buttons =
            new QDialogButtonBox(QDialogButtonBox::Ok, &dialog);
    connect(buttons, SIGNAL(accepted()), &dialog, SLOT(accept()));
    layout->addWidget(buttons);

    dialog.exec();
}

QString PPS2_0DevTool::getUI_sourcePathLineEditText() const
{
    return ui->sourcePathLineEdit->text();
}

bool PPS2_0DevTool::removeTabByTitle(const QString &title)
{
    for (int i = 0; i < ui->functionTabWidget->count(); ++i) {
        if (ui->functionTabWidget->tabText(i) == title) {
            ui->functionTabWidget->removeTab(i);
            return true;
        }
    }
    return false;
}

// ---------------------------------------------------------------------------
// 來源路徑
// ---------------------------------------------------------------------------

void PPS2_0DevTool::onBrowseSourcePath()
{
    const QString dir = QFileDialog::getExistingDirectory(
                this, QString("選擇來源路徑"), getUI_sourcePathLineEditText());
    if (dir.isEmpty())
        return;

    ui->sourcePathLineEdit->setText(dir);
    onSourcePathEdited();
}

void PPS2_0DevTool::onClearSourcePath()
{
    ui->sourcePathLineEdit->clear();
    m_lastSourcePath.clear();
    emit workingDataCleared();
}

void PPS2_0DevTool::onSourcePathEdited()
{
    const QString path = getUI_sourcePathLineEditText();
    if (path == m_lastSourcePath)
        return;

    m_lastSourcePath = path;
    QTDebug(QString("來源路徑變更：%1").arg(path));
    emit sourcePathChanged(path);
}

// ---------------------------------------------------------------------------
// 視窗行為
// ---------------------------------------------------------------------------

void PPS2_0DevTool::onAbout()
{
    QString text;
    text += QString("%1\n").arg(TOOL_NAME);
    text += QString("Version: %1\n").arg(TOOL_VERSION);
    text += QString("Qt: %1\n").arg(qVersion());
    text += QString("Build: %1\n").arg(BUILD_DATE);

    const QString link = m_config.userGuideLink();
    if (!link.isEmpty())
        text += QString("\nUser Guide: %1").arg(link);

    QMessageBox::about(this, QString("About"), text);
}

void PPS2_0DevTool::onTrayActivated(QSystemTrayIcon::ActivationReason reason)
{
    // DoubleClick 是 Windows 的還原手勢；Trigger（單擊）在部分平台上
    // 是唯一會送出的事件，一併接受比較不會有「點了沒反應」的情況。
    if (reason == QSystemTrayIcon::DoubleClick
            || reason == QSystemTrayIcon::Trigger) {
        showNormal();
        raise();
        activateWindow();
    }
}

void PPS2_0DevTool::closeEvent(QCloseEvent *event)
{
    // 關閉視窗時隱藏而非結束。要結束程式請用系統匣的 Quit，
    // 或（Debug_Mode 開啟時）關閉 console。
    if (m_trayIcon) {
        hide();
        event->ignore();
        return;
    }
    QMainWindow::closeEvent(event);
}
