#include "pps2_0devtool.h"
#include "ui_pps2_0devtool.h"

#include "ProcessingDialog.h"
#include "SingleBuilding.h"
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
#include <QTimer>
#include <QSystemTrayIcon>
#include <QVBoxLayout>

PPS2_0DevTool::PPS2_0DevTool(const Config &config, QWidget *parent)
    : QMainWindow(parent)
    , ui(new Ui::PPS2_0DevTool)
    , m_config(config)
    , m_runner(new PythonRunner(this))
    , m_processingDialog(Q_NULLPTR)
    , m_trayIcon(Q_NULLPTR)
    , m_flowActive(false)
    , m_flowCancelled(false)
    , m_singleBuilding(Q_NULLPTR)
{
    ui->setupUi(this);

    setupToolService();
    UI_Init();
    UI_SetupSignal();

    // 初次進入功能不能靠 currentChanged。tab 寫在 .ui 裡時，分頁索引在
    // setupUi() 期間就已經從 -1 變成 0，那時訊號還沒接上 —— 等接上了，
    // 當前分頁早就定案，訊號永遠不會來。少了這一次明確的呼叫，使用者
    // 啟動後第一眼看到的會是空白畫面，得切走再切回才會載入。
    //
    // 延到事件迴圈啟動後才跑：載入會彈出 modal 對話框，而主視窗要等
    // main() 裡的 show() 之後才存在，在建構期間彈對話框沒有父視窗可依附。
    QTimer::singleShot(0, this, SLOT(onInitialFunctionEntry()));
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
    QTDebug(QString("%1 %2 啟動").arg(TOOL_NAME, TOOL_VERSION));

    // 功能實例在這裡建立。
    m_singleBuilding = new SingleBuilding(this, this);
}

// 通知功能它被進入了。
//
// 這裡沒有再開一個廣播訊號 —— 外殼本來就在 setupToolService() 建立每個功能
// 實例、在 UI_SetupSignal() 接它的元件，直接呼叫比多一條所有功能都收得到、
// 卻只有一個功能該理會的訊號單純。
void PPS2_0DevTool::notifyFunctionEntered(const QString &functionName)
{
    if (m_singleBuilding && functionName == SingleBuilding::functionName())
        m_singleBuilding->enterFunction();
}

void PPS2_0DevTool::UI_Init()
{
    setWindowTitle(QString("%1 %2").arg(TOOL_NAME, TOOL_VERSION));

    // 固定尺寸 1200x830。
    setFixedSize(1200, 830);

    ui->progressBar->setRange(0, 100);
    ui->progressBar->setValue(0);

    // 功能依 isFunctionVisible() 決定是否 removeTabByTitle()。
    if (!isFunctionVisible(SingleBuilding::functionName()))
        removeTabByTitle(SingleBuilding::functionName());

    // 記下開場的當前功能。移除分頁後索引可能已經變動，因此在這裡才讀。
    const int current = ui->functionTabWidget->currentIndex();
    m_currentFunctionName = (current >= 0)
            ? ui->functionTabWidget->tabText(current)
            : QString();

    setupTrayIcon();
}

void PPS2_0DevTool::UI_SetupSignal()
{
    connect(ui->sourcePathBrowseButton, SIGNAL(clicked()),
            this, SLOT(onBrowseSourcePath()));
    connect(ui->sourcePathLineEdit, SIGNAL(editingFinished()),
            this, SLOT(onSourcePathEdited()));
    connect(ui->functionTabWidget, SIGNAL(currentChanged(int)),
            this, SLOT(onFunctionTabChanged(int)));
    connect(ui->actionAbout, SIGNAL(triggered()),
            this, SLOT(onAbout()));

    // 功能的元件在這裡交給功能自己接。
    if (m_singleBuilding) {
        SingleBuildingWidgets widgets;
        widgets.filterEdit          = ui->sbFilterLineEdit;
        widgets.filterClearButton   = ui->sbFilterClearButton;
        widgets.sourceView          = ui->sbSourceListView;
        widgets.targetView          = ui->sbTargetListView;
        widgets.addButton           = ui->sbAddButton;
        widgets.removeButton        = ui->sbRemoveButton;
        widgets.targetClearButton   = ui->sbTargetClearButton;
        widgets.recoveryButton      = ui->sbRecoverySettingButton;
        widgets.modifyButton        = ui->sbModifySettingButton;
        m_singleBuilding->attachWidgets(widgets);

        connect(this, SIGNAL(sourcePathChanged(QString,QString)),
                m_singleBuilding, SLOT(onSourcePathChanged(QString,QString)));
    }

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
    // 單步執行就是「只有一步的流程」。對話框所有權、耗時起訖、取消語意三者
    // 因此只有一份實作 —— 兩條路徑各寫一次的話，修了流程那條，單步這條還
    // 留著同一個 bug。
    FlowStep step;
    step.label      = functionName;
    step.scriptPath = scriptPath;
    step.action     = action;
    step.params     = params;
    step.envVars    = envVars;

    // 第一次被問（還沒有任何結果）就給那一步，第二次被問就結束。
    FlowDecider decide =
            [step](const QList<PythonRunner::PythonRunnerResult> &done) -> FlowStep {
        return done.isEmpty() ? step : FlowStep::done();
    };

    FlowCallback finished =
            [onDone](const FlowResult &result) {
        if (onDone && !result.results.isEmpty())
            onDone(result.results.first());
    };

    return runFunctionFlow(functionName, decide, finished);
}

bool PPS2_0DevTool::runFunctionFlow(const QString &functionName,
                                    FlowDecider decide,
                                    FlowCallback onDone)
{
    if (m_flowActive || !m_runner->isIdle()) {
        // 忙碌時只記警告不跳訊息框 —— 執行期間主視窗被互斥遮罩鎖定，使用者
        // 觸發不了這條，能觸發的只有程式化的連續呼叫，那是程式缺陷而非使用者
        // 操作錯誤。警告要指出進行中的功能與步驟，否則從 console 看不出是
        // 哪一條流程還沒結束。
        QTWarn(QString("已有流程在執行中，忽略這次執行請求（進行中：%1 / %2）")
               .arg(m_flowFunctionName.isEmpty() ? QString("(未知功能)")
                                                 : m_flowFunctionName,
                    m_flowStepLabel.isEmpty()    ? QString("(未知步驟)")
                                                 : m_flowStepLabel));
        return false;
    }

    if (!decide) {
        // 沒有決策函式就沒有第一步。這是程式缺陷，不是使用者操作錯誤。
        QTError(QString("流程 %1 未提供決策函式，無法啟動").arg(functionName));
        return false;
    }

    m_flowActive       = true;
    m_flowCancelled    = false;
    m_flowFunctionName = functionName;
    m_flowStepLabel.clear();
    m_flowDecider      = decide;
    m_flowCallback     = onDone;
    m_flowResults.clear();

    // 計時器與對話框都由整條流程持有：這裡起算、這裡建立，步驟之間不動它們。
    m_runTimer.start();

    delete m_processingDialog;
    m_processingDialog = new ProcessingDialog(functionName, this);
    connect(m_processingDialog, SIGNAL(cancelRequested()),
            this, SLOT(onCancelRequested()));
    m_processingDialog->show();

    // 第一步同樣走決策函式 —— 「第一步是什麼」也是功能的決定。
    //
    // 第一步不走 advanceFlow()：它和後續步驟在「啟動前失敗」時的處理不同，
    // 而那個差異正是這裡要表達的東西。第一步沒跑成代表流程從未開始，同步
    // 回報 false 就好，與單步介面的既有語意一致；後續步驟沒跑成時流程已經
    // 產生過結果，得讓功能知道停在哪裡（見 advanceFlow）。
    const FlowStep first = m_flowDecider(m_flowResults);

    if (first.finish) {
        // 決策函式第一次就回答結束，是合法的空流程。
        finishFlow();
        return true;
    }

    QString failureMessage;
    if (!startFlowStep(first, &failureMessage)) {
        reportStepStartFailure(failureMessage);
        resetFlowState();   // 不呼叫任何 callback：流程從未開始
        return false;
    }

    return true;
}

// 只在一個步驟完成之後被呼叫，因此 m_flowResults 一定非空。第一步由
// runFunctionFlow() 直接處理 —— 兩者在「啟動前失敗」時的行為不同。
void PPS2_0DevTool::advanceFlow()
{
    // 取消後不再詢問決策函式 —— 取消路徑的收尾在 onScriptRunFinished()。
    if (!m_flowActive || m_flowCancelled)
        return;

    const FlowStep step = m_flowDecider(m_flowResults);

    if (step.finish) {
        finishFlow();
        return;
    }

    QString failureMessage;
    if (startFlowStep(step, &failureMessage))
        return;

    // 啟動前失敗（腳本不存在、找不到 Python）。不再詢問決策函式 —— 這類失敗
    // 是部署或設定問題，補救步驟解決不了，轉交只會讓每個功能各自重寫一次
    // 相同的處理。
    reportStepStartFailure(failureMessage);

    // 合成一筆失敗結果，讓功能知道流程停在哪一步、為什麼停。PythonRunner
    // 對「無法啟動 Python」也是這樣合成後走 callback。
    PythonRunner::PythonRunnerResult synthetic;
    synthetic.success  = false;
    synthetic.hasJson  = false;
    synthetic.exitCode = -1;
    synthetic.message  = failureMessage;
    m_flowResults.append(synthetic);

    finishFlow();
}

bool PPS2_0DevTool::startFlowStep(const FlowStep &step, QString *failureMessage)
{
    const QJsonObject functionConfig = getFunctionConfig(m_flowFunctionName);

    // 步驟可覆寫直譯器（兩步跑在不同 Python 環境時用）。覆寫值由功能自己從
    // 自己的設定區塊取出後填進步驟 —— 外殼不解讀 Function 底下的任何鍵。
    const QString program = step.program.isEmpty()
            ? functionConfig.value("Program").toString(QString("python"))
            : step.program;

    // 信封四個欄位。tool 身分不在這裡 —— 走 TOOLNAME / TOOLVERSION 環境變數。
    QJsonObject envelope;
    envelope.insert("source_path", getUI_sourcePathLineEditText());
    envelope.insert("config",      functionConfig);
    envelope.insert("action",      step.action);
    envelope.insert("params",      step.params);

    m_flowStepLabel = step.label.isEmpty() ? m_flowFunctionName : step.label;

    // 對話框不重建，只換標題列的步驟名稱，並把上一步殘留的階段文字蓋掉。
    if (m_processingDialog)
        m_processingDialog->setStep(m_flowStepLabel);

    PythonRunner::ResultCallback stepCallback =
            [this](const PythonRunner::PythonRunnerResult &result) {
        onStepResult(result);
    };

    QString message;
    const bool started = m_runner->start(program,
                                         step.scriptPath,
                                         envelope,
                                         step.envVars,
                                         m_config.debugMode(),   // Debug_Mode 連動 -v
                                         stepCallback,
                                         &message);
    if (failureMessage)
        *failureMessage = started ? QString() : message;

    return started;
}

// startFlowStep() 失敗時的共同收尾。
//
// 先收對話框再讓使用者看到原因：錯誤訊息框疊在 application-modal 的處理中
// 對話框上雖然可行（Qt 的 modal 是堆疊的，後顯示的在上層），但讓使用者同時
// 看到「處理中」和「失敗了」兩個視窗沒有意義。
void PPS2_0DevTool::reportStepStartFailure(const QString &failureMessage)
{
    closeProcessingDialog();

    // 忙碌時不跳訊息框（見 PythonRunner::start）—— 那是程式缺陷不是使用者
    // 操作錯誤，PythonRunner 已經記了警告。流程內走不到這條（只有前一步真的
    // 結束了才會啟動下一步），但守衛留著，免得日後有人繞過流程直接呼叫時
    // 靜默地變成一個訊息框。
    if (m_runner->isIdle())
        showUI_ErrorMessageBox(failureMessage);
}

void PPS2_0DevTool::onStepResult(const PythonRunner::PythonRunnerResult &result)
{
    // 取消時 PythonRunner 根本不呼叫 callback，所以這裡收到結果就代表流程
    // 還活著。守衛留著只是不信任未來的自己。
    if (!m_flowActive || m_flowCancelled)
        return;

    m_flowResults.append(result);
    advanceFlow();
}

void PPS2_0DevTool::finishFlow()
{
    FlowResult result;
    result.results   = m_flowResults;
    result.elapsedMs = m_runTimer.elapsed();

    for (int i = 0; i < m_flowResults.size(); ++i) {
        if (!m_flowResults.at(i).success) {
            result.success         = false;
            result.failedStepIndex = i;   // 第一個失敗的步驟
            break;
        }
    }

    QTDebug(QString("流程 %1 結束（%2 步，%3），耗時 %4")
            .arg(m_flowFunctionName)
            .arg(m_flowResults.size())
            .arg(result.success ? QString("全部成功")
                                : QString("第 %1 步失敗").arg(result.failedStepIndex + 1))
            .arg(formatElapsedTime(result.elapsedMs)));

    FlowCallback callback = m_flowCallback;

    closeProcessingDialog();
    resetFlowState();

    // callback 放在狀態清空之後，功能才能在 callback 裡直接啟動下一條流程。
    // 這與 PythonRunner::finish() 先歸零 m_state 再呼叫 callback 是同一個理由。
    if (callback)
        callback(result);
}

void PPS2_0DevTool::closeProcessingDialog()
{
    if (!m_processingDialog)
        return;

    m_processingDialog->hide();
    m_processingDialog->deleteLater();
    m_processingDialog = Q_NULLPTR;
}

void PPS2_0DevTool::resetFlowState()
{
    m_flowActive    = false;
    m_flowCancelled = false;
    m_flowFunctionName.clear();
    m_flowStepLabel.clear();
    m_flowDecider  = FlowDecider();
    m_flowCallback = FlowCallback();
    m_flowResults.clear();
}

void PPS2_0DevTool::onScriptProgress(const QString &stage)
{
    if (m_processingDialog)
        m_processingDialog->setStage(stage);
}

void PPS2_0DevTool::onCancelRequested()
{
    // 先標記再要求終止：行程已經不在執行時，PythonRunner::cancel() 會同步
    // 走到 finish() 並發出 runFinished，旗標晚一步設就來不及被看到。
    m_flowCancelled = true;
    m_runner->cancel();
}

void PPS2_0DevTool::onScriptRunFinished()
{
    // PythonRunner::finish() 把 runFinished 排在 callback 之前，所以到這裡時
    // 外殼還不知道流程要不要繼續。正常結束的收尾一律留給 onStepResult() 之後
    // 的 advanceFlow() —— 這裡什麼都不做，對話框才不會在步驟之間閃掉。
    //
    // 取消是唯一的例外：那條路徑上 callback 不會被呼叫，runFinished 是外殼
    // 唯一會收到的通知。
    if (m_flowActive && m_flowCancelled) {
        QTDebug(QString("流程 %1 已取消，耗時 %2")
                .arg(m_flowFunctionName,
                     formatElapsedTime(m_runTimer.elapsed())));
        closeProcessingDialog();
        resetFlowState();
        return;
    }

    // 沒有流程在跑卻收到結束通知：不該發生，但別留下孤兒對話框。
    if (!m_flowActive)
        closeProcessingDialog();
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

// 來源路徑列上唯一的按鈕。
//
// 清除路徑沒有專屬按鈕：使用者把文字框清空即可，editingFinished 會走上
// 同一條變更路徑。
void PPS2_0DevTool::onBrowseSourcePath()
{
    const QString dir = QFileDialog::getExistingDirectory(
                this, QString("選擇來源路徑"), getUI_sourcePathLineEditText());
    if (dir.isEmpty())
        return;

    ui->sourcePathLineEdit->setText(dir);
    onSourcePathEdited();
}

void PPS2_0DevTool::onSourcePathEdited()
{
    if (m_currentFunctionName.isEmpty())
        return;

    const QString path = getUI_sourcePathLineEditText();
    if (path == m_functionSourcePaths.value(m_currentFunctionName))
        return;

    m_functionSourcePaths[m_currentFunctionName] = path;
    QTDebug(QString("[%1] 來源路徑變更：%2").arg(m_currentFunctionName, path));
    emit sourcePathChanged(path, m_currentFunctionName);
}

void PPS2_0DevTool::onFunctionTabChanged(int index)
{
    const QString name = (index >= 0)
            ? ui->functionTabWidget->tabText(index)
            : QString();
    if (name == m_currentFunctionName)
        return;

    m_currentFunctionName = name;

    // 還原成該功能自己的路徑。這是還原，不是使用者修改 —— 因為填回去的
    // 就是 m_functionSourcePaths 裡的值，稍後的 editingFinished 比對相同，
    // 不會發出變更訊號。
    ui->sourcePathLineEdit->setText(m_functionSourcePaths.value(name));

    if (name.isEmpty())
        return;

    QTDebug(QString("進入功能：%1").arg(name));
    notifyFunctionEntered(name);
}

void PPS2_0DevTool::onInitialFunctionEntry()
{
    if (m_currentFunctionName.isEmpty())
        return;

    ui->sourcePathLineEdit->setText(
                m_functionSourcePaths.value(m_currentFunctionName));

    QTDebug(QString("初次進入功能：%1").arg(m_currentFunctionName));
    notifyFunctionEntered(m_currentFunctionName);
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
