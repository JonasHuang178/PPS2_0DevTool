#ifndef PPS2_0DEVTOOL_H
#define PPS2_0DEVTOOL_H

#include "PythonRunner.h"
#include "json.h"

#include <QElapsedTimer>
#include <QJsonObject>
#include <QList>
#include <QMainWindow>
#include <QMap>
#include <QString>
#include <QSystemTrayIcon>

#include <functional>

QT_BEGIN_NAMESPACE
namespace Ui { class PPS2_0DevTool; }
QT_END_NAMESPACE

class ProcessingDialog;

// 應用程式外殼。
//
// 最高原則：Qt 只負責 GUI —— 讓使用者「選擇」。真正的實作寫在 Python。
// 外殼本身不含任何業務邏輯。
//
// 分工邊界（多步驟流程把這條線畫得更清楚）：
//
//   Qt 端  流程編排 —— 決定執行哪一步、依已完成結果組裝下一步的參數、
//          判定流程何時結束
//   腳本   單一步驟的業務運算 —— 解析檔案格式、呼叫外部服務、產生報表、
//          資料聚合與轉換，一律在這裡
//
// 「外殼不含業務邏輯」在有了流程之後依然成立：判斷寫在功能提供的決策函式
// 裡，不在外殼。外殼只是把步驟依序跑完的排程器。
//
// 已知代價：流程的分支判斷寫在 C++，因此整條流程無法從命令列重現，只能
// 開圖形介面驗證。個別步驟的腳本仍然可以獨立以 --request-stdin 執行 ——
// 所以「單步做錯了什麼」查得到，查不到的只有步驟之間的接線。把接線壓到
// 最薄（只挑欄位、改名、讀 UI 值與分支）就是在控制這個代價。
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
    //
    // 內部實作為「只有一步的流程」，因此對話框、耗時、取消三者與多步流程
    // 共用同一份實作。
    bool runFunctionScript(const QString &functionName,
                           const QString &scriptPath,
                           const QString &action,
                           const QJsonObject &params,
                           PythonRunner::ResultCallback onDone,
                           const QMap<QString, QString> &envVars =
                               QMap<QString, QString>());

    // --- 流程執行 API ---
    //
    // 一次使用者操作依序執行一支以上的腳本。步驟 MUST NOT 預先列出：每完成
    // 一步，外殼把目前為止所有已完成結果交給決策函式，由它回答「執行下一步」
    // 或「流程結束」。流程長度與路徑因此都可以依結果而定。
    //
    // 外殼不判斷成敗 —— 步驟回傳失敗結果時同樣詢問決策函式，由功能決定要
    // 結束還是執行補救步驟。判斷邏輯全在功能這一側，外殼只是排程器。
    //
    // 分工邊界：決定執行哪一步、依已完成結果組裝下一步的參數、判定流程何時
    // 結束，屬於 Qt 端；單一步驟的業務運算（解析檔案格式、呼叫外部服務、
    // 產生報表、資料聚合與轉換）一律在腳本內完成。
    //
    // 決策函式在步驟之間同步執行，事件迴圈不會轉動 —— 裡面 MUST NOT 有任何
    // 使用者互動（QMessageBox::exec()、QFileDialog 等會開巢狀事件迴圈）。

    struct FlowStep
    {
        QString     label;        // 顯示在對話框標題列。序號自己寫進去（例如
                                  // "步驟 2/2：產生報表"），外殼不解讀也不編號
        QString     scriptPath;
        QString     action;
        QJsonObject params;
        QMap<QString, QString> envVars;

        // 空字串 = 用功能設定區塊的 Program。兩步要跑在不同 Python 環境時
        // 才填 —— 值由功能自己從自己的設定區塊取出，外殼不解讀 Function
        // 底下的任何鍵。
        QString     program;

        // true = 流程結束，其餘欄位一律忽略。用 FlowStep::done() 建立。
        bool        finish;

        FlowStep() : finish(false) {}

        static FlowStep done()
        {
            FlowStep step;
            step.finish = true;
            return step;
        }
    };

    struct FlowResult
    {
        bool    success;           // 所有已執行的步驟都成功
        int     failedStepIndex;   // 第一個失敗的步驟；全成功為 -1
        QList<PythonRunner::PythonRunnerResult> results;   // 依執行順序
        qint64  elapsedMs;         // 整條流程的耗時，不是最後一步的

        FlowResult()
            : success(true), failedStepIndex(-1), elapsedMs(0) {}
    };

    // 帶入目前為止所有已完成步驟的結果（依執行順序），回傳下一步或 done()。
    typedef std::function<FlowStep(const QList<PythonRunner::PythonRunnerResult> &)>
            FlowDecider;

    // 流程結束時呼叫一次。取消時不會被呼叫。
    typedef std::function<void(const FlowResult &)> FlowCallback;

    // 非同步：立即回傳流程是否成功啟動，MUST NOT 阻塞至流程結束。
    bool runFunctionFlow(const QString &functionName,
                         FlowDecider decide,
                         FlowCallback onDone);

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

    // --- 流程狀態機 ---
    //
    // 建在 PythonRunner 之上，不改寫它 —— 它的單步語意（取消時不呼叫
    // callback）是「取消後畫面完全不動」的來源，改它風險最高。
    void advanceFlow();
    bool startFlowStep(const FlowStep &step, QString *failureMessage);
    void reportStepStartFailure(const QString &failureMessage);
    void onStepResult(const PythonRunner::PythonRunnerResult &result);
    void finishFlow();
    void closeProcessingDialog();
    void resetFlowState();

    Ui::PPS2_0DevTool *ui;

    Config             m_config;
    PythonRunner      *m_runner;
    ProcessingDialog  *m_processingDialog;
    QSystemTrayIcon   *m_trayIcon;
    QElapsedTimer      m_runTimer;      // 整條流程一個，不是每步一個
    QString            m_lastSourcePath;

    bool               m_flowActive;
    bool               m_flowCancelled;
    QString            m_flowFunctionName;
    QString            m_flowStepLabel;     // 目前步驟，忙碌警告要指出來
    FlowDecider        m_flowDecider;
    FlowCallback       m_flowCallback;
    QList<PythonRunner::PythonRunnerResult> m_flowResults;
};

#endif // PPS2_0DEVTOOL_H
