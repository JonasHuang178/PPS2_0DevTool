#ifndef AIANALYSISGITLABMR_H
#define AIANALYSISGITLABMR_H

#include "PythonRunner.h"
#include "pps2_0devtool.h"

#include <QJsonObject>
#include <QList>
#include <QMap>
#include <QObject>
#include <QString>

QT_BEGIN_NAMESPACE
class QCheckBox;
class QComboBox;
class QLineEdit;
class QListView;
class QPushButton;
class QRadioButton;
class QSortFilterProxyModel;
class QSpinBox;
class QStandardItemModel;
class QTableView;
QT_END_NAMESPACE

// 功能要用到的元件。由外殼在 UI_SetupSignal() 填好後交過來。
//
// 與 SingleBuildingWidgets 同一個理由：不直接傳整包 Ui::PPS2_0DevTool，
// 讓一個功能看得到所有其他功能的元件是不必要的耦合。
struct AIAnalysisGitLabMRWidgets
{
    QComboBox    *modeCombo;
    QCheckBox    *debugFileCheck;
    QLineEdit    *saveDirEdit;
    QPushButton  *saveDirBrowseButton;
    QLineEdit    *jiraKeyEdit;
    QRadioButton *jiraNoneRadio;
    QRadioButton *jiraManualRadio;
    QRadioButton *jiraAutoRadio;
    QListView    *repoView;
    QRadioButton *manualMrRadio;
    QLineEdit    *manualMrEdit;
    QRadioButton *getMrRadio;
    QCheckBox    *onlyOpenCheck;
    QCheckBox    *createdAfterCheck;
    QSpinBox     *createdAfterSpin;
    QPushButton  *refreshButton;
    QTableView   *mrView;
    QPushButton  *analysisButton;

    AIAnalysisGitLabMRWidgets()
        : modeCombo(Q_NULLPTR)
        , debugFileCheck(Q_NULLPTR)
        , saveDirEdit(Q_NULLPTR)
        , saveDirBrowseButton(Q_NULLPTR)
        , jiraKeyEdit(Q_NULLPTR)
        , jiraNoneRadio(Q_NULLPTR)
        , jiraManualRadio(Q_NULLPTR)
        , jiraAutoRadio(Q_NULLPTR)
        , repoView(Q_NULLPTR)
        , manualMrRadio(Q_NULLPTR)
        , manualMrEdit(Q_NULLPTR)
        , getMrRadio(Q_NULLPTR)
        , onlyOpenCheck(Q_NULLPTR)
        , createdAfterCheck(Q_NULLPTR)
        , createdAfterSpin(Q_NULLPTR)
        , refreshButton(Q_NULLPTR)
        , mrView(Q_NULLPTR)
        , analysisButton(Q_NULLPTR) {}
};

// AI Analysis GitLab MR 功能。
//
// 分析單位是「一個 repo 的一個 MR」—— 兩個清單都是單選。畫面上的兩條取得
// 路徑（手動輸入編號 / 取得清單）產出的是同一種輸入，所以後面的流程只需要
// 處理一種情況。
//
// 進入這個功能**不執行任何腳本**：Repository 清單來自設定檔，MR 清單一律
// 由使用者按重新整理才取得。與 Single Building 的「進入即載入」相反，理由是
// 這裡每次載入都是一次網路請求，照做的話每次切到這個分頁都會被一個
// application-modal 的對話框擋住並等待 GitLab 回應。
//
// 按下 AI Analysis 啟動一條固定五步的流程。五步全部執行，Qt 端不依條件跳過
// 任何一步 —— 「要不要真的做事」由該步的腳本看參數自行決定。這是為了讓同一批
// 腳本能被 CI/CD 的 shell 直接串接：分支判斷若寫在這裡，CI 那一側就成為第二份
// 編排實作，兩份必然漂移。
class AIAnalysisGitLabMR : public QObject
{
    Q_OBJECT

public:
    // 功能名稱。同時是 tab 標題與設定檔 Function 底下的鍵名，三處必須同字。
    static QString functionName();

    explicit AIAnalysisGitLabMR(PPS2_0DevTool *shell, QObject *parent = Q_NULLPTR);

    // 接上元件並建立訊號連接。外殼在 UI_SetupSignal() 呼叫一次。
    void attachWidgets(const AIAnalysisGitLabMRWidgets &widgets);

private slots:
    void onRepoSelectionChanged();
    void onMrSelectionChanged();
    void onSourceModeToggled();
    void onDebugFileToggled();
    void onJiraModeToggled();
    void onSaveDirBrowseClicked();
    void onManualMrTextChanged(const QString &text);
    void onQueryParameterChanged();
    void onRefreshClicked();
    void onAnalysisClicked();
    void updateButtonStates();

private:
    // MR 表格的三種狀態。空白畫面在「還沒抓」與「抓了但沒有符合的」之間
    // 完全相同，但使用者該做的下一步不同 —— 前者按重新整理，後者放寬條件。
    enum MrTableState {
        MrNotFetched,
        MrEmptyResult,
        MrLoaded
    };

    // 一次分析所需的全部輸入。在按下按鈕的當下一次取齊，之後流程的每一步
    // 都從這裡取值 —— 流程進行中使用者碰不到畫面，但把輸入凍結成一份快照
    // 仍然比每步回頭讀元件清楚。
    struct AnalysisContext
    {
        QString repo;
        QString mrIid;
        QString debugDir;        // 空字串 = 未勾選除錯，腳本據此不寫任何檔案
        QString aiModeName;
        QString aiApiUrl;
        QString aiApiKey;
        QString aiModel;
        QString jiraMode;        // none / manual / auto
        QString jiraKeyManual;
        QMap<QString, QString> envVars;
    };

    // --- 設定 ---
    QJsonObject config() const;
    QString     resolvedSaveDir() const;
    QMap<QString, QString> serviceEnvVars() const;
    QJsonObject selectedAiMode() const;

    // --- 畫面狀態 ---
    void applyMrHeaderLayout();
    void setMrTableState(MrTableState state, const QString &message);
    void invalidateMrTable();
    QString selectedRepo() const;
    QString selectedMrIid() const;
    QString effectiveMrIid() const;
    QString jiraMode() const;

    // --- 流程 ---
    PPS2_0DevTool::FlowStep buildStep(
            int index,
            const AnalysisContext &context,
            const QList<PythonRunner::PythonRunnerResult> &done) const;
    void onFlowFinished(const PPS2_0DevTool::FlowResult &result);

    PPS2_0DevTool *m_shell;
    AIAnalysisGitLabMRWidgets m_widgets;

    QStandardItemModel    *m_repoModel;
    QStandardItemModel    *m_mrModel;
    QSortFilterProxyModel *m_mrProxy;

    MrTableState m_mrState;

    // 手動編號的輸入框會自我修正（貼上 !123 或整條網址時取出其中的數字），
    // 而 setText() 會再次觸發 textChanged。這個旗標擋掉那一層遞迴。
    bool m_sanitizingManualMr;
};

#endif // AIANALYSISGITLABMR_H
