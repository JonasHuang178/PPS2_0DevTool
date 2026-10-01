#ifndef AIANALYSISGITLABMR_H
#define AIANALYSISGITLABMR_H

#include "PythonRunner.h"
#include "pps2_0devtool.h"

#include <QJsonObject>
#include <QList>
#include <QMap>
#include <QObject>
#include <QSet>
#include <QSharedPointer>
#include <QSortFilterProxyModel>
#include <QString>
#include <QStyledItemDelegate>
#include <QStringList>
#include <QTemporaryDir>

QT_BEGIN_NAMESPACE
class QCheckBox;
class QComboBox;
class QLineEdit;
class QListView;
class QPushButton;
class QRadioButton;
class QLabel;
class QSpinBox;
class QStandardItem;
class QStandardItemModel;
class QTableView;
class QToolButton;
class QWidget;
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

    // Filter 群組。兩個過濾器都作用於**已經取回的資料**，所以它們與
    // Merge Request Parameter 分屬兩個群組 —— 後者改動會使清單失效並需要
    // 重新取得，前者立即生效且不發出任何請求。放在同一個框裡的話，兩種
    // 行為不同的控件在外觀上無從區分。
    QToolButton  *filterToggleButton;
    QLabel       *filterStatusLabel;
    QPushButton  *filterClearButton;
    QWidget      *filterContentWidget;
    QListView    *authorView;
    QLineEdit    *skipStartsWithEdit;
    QLineEdit    *skipEndsWithEdit;
    QLineEdit    *skipContainsEdit;

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
        , analysisButton(Q_NULLPTR)
        , filterToggleButton(Q_NULLPTR)
        , filterStatusLabel(Q_NULLPTR)
        , filterClearButton(Q_NULLPTR)
        , filterContentWidget(Q_NULLPTR)
        , authorView(Q_NULLPTR)
        , skipStartsWithEdit(Q_NULLPTR)
        , skipEndsWithEdit(Q_NULLPTR)
        , skipContainsEdit(Q_NULLPTR) {}
};


// Merge Request 表格的過濾層：作者與標題排除。
//
// 兩個條件寫在同一個 filterAcceptsRow() 裡，不疊兩層 proxy —— 疊兩層的話
// 「各篩掉幾筆」這個統計要分別從兩層取，而兩層的先後會影響數字。
//
// 判定拆成兩支公開函式，是為了讓統計能用**同一份規則**走一遍來源模型：
// filterAcceptsRow() 由 Qt 依需要呼叫，次數與順序都不保證，在它裡面累加
// 計數器會得到一個看起來合理、實際上不對的數字。
// 標題欄的委派：讓連結色在**選取時**也留著。
//
// 項目的 ForegroundRole 只覆寫 QPalette::Text，而選取狀態下文字畫的是
// QPalette::HighlightedText —— 沒有這一手，選中的那一列標題會跟其餘欄位一樣是外殼
// 選取樣式的深藍，只剩底線還在，看不出它是可點的。這一點以實際像素量過，不是推論。
//
// 只掛在標題欄：其餘四欄本來就該跟著外殼的選取樣式走。
//
// **文字必須自己畫。** 只把顏色放進 option 的 palette 是不夠的 —— 外殼的選取樣式是
// 一條樣式表規則，而 QStyleSheetStyle 在畫項目時會用規則裡的 color 覆寫 palette，
// 覆寫發生在委派交出 option 之後。這一點是量過像素才確定的，不是推論。
class LinkColumnDelegate : public QStyledItemDelegate
{
    Q_OBJECT

public:
    explicit LinkColumnDelegate(QObject *parent = Q_NULLPTR);

    void paint(QPainter *painter, const QStyleOptionViewItem &option,
               const QModelIndex &index) const Q_DECL_OVERRIDE;

protected:
    void initStyleOption(QStyleOptionViewItem *option,
                         const QModelIndex &index) const Q_DECL_OVERRIDE;
};

class MrFilterProxyModel : public QSortFilterProxyModel
{
    Q_OBJECT

public:
    explicit MrFilterProxyModel(int authorColumn, int titleColumn,
                                QObject *parent = Q_NULLPTR);

    // 空集合代表不過濾作者。
    void setAuthors(const QSet<QString> &authors);

    // 三種比對各自一份關鍵字清單；呼叫端負責先解析（去空白、丟掉空的）。
    void setSkipRules(const QStringList &startsWith,
                      const QStringList &endsWith,
                      const QStringList &contains);

    bool authorAccepts(const QString &author) const;
    bool titleAccepts(const QString &title) const;

protected:
    bool filterAcceptsRow(int sourceRow,
                          const QModelIndex &sourceParent) const Q_DECL_OVERRIDE;

private:
    int             m_authorColumn;
    int             m_titleColumn;
    QSet<QString>   m_authors;
    QStringList     m_startsWith;
    QStringList     m_endsWith;
    QStringList     m_contains;
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

    // 把一行逗號分隔的輸入解析成關鍵字清單：每筆去頭尾空白，**空的一律丟掉**。
    //
    // 公開是為了讓它驗得到。空字串是所有標題的子字串，一個多餘的逗號就會讓整張
    // 表格一筆不剩 —— 那是這次改動裡唯一「看起來正常卻完全壞掉」的失敗方式，
    // 不該只靠讀碼確認。純字串函式，沒有狀態，公開不增加任何耦合。
    static QStringList parseSkipKeywords(const QString &text);

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

    void onFilterToggled(bool expanded);
    void onAuthorItemChanged(QStandardItem *item);
    void onSkipRulesEdited();
    void onClearFilterClicked();
    void onMrDoubleClicked(const QModelIndex &index);
    void onMrEntered(const QModelIndex &index);
    void onMrViewportEntered();
    void onRepoDoubleClicked(const QModelIndex &index);

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
        QString debugDir;        // 空字串 = 未勾選除錯，不寫 debug.log

        // 每一步的產物都寫進這裡，第 5 步再以路徑把它們讀回來合併。
        //
        // **一定有值** —— 勾了除錯就是 debugDir，沒勾就是一個暫存目錄。
        // 中間產物落檔不再是「除錯才開啟」的選項，因為第 5 步的輸入就是檔案
        // 路徑；沒勾除錯時改走暫存目錄，使用者看得到的結果完全一樣。
        QString workDir;

        // 沒勾除錯時持有上面那個暫存目錄。它的生命週期綁在這份 context 上，
        // 而 context 由流程的決策函式持有 —— 流程一結束，決策函式連同這個
        // QTemporaryDir 一起消滅，目錄也就被刪掉了。不必在任何地方寫清理。
        QSharedPointer<QTemporaryDir> tempDir;

        QString aiModeName;
        QString aiApiUrl;
        QString aiApiKey;
        QString aiModel;
        QString aiTimeout;
        QString aiRetries;
        QString aiReask;
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

    // --- 顯示過濾 ---
    //
    // 候選作者自**來源模型**推導，不從過濾後的結果推導 —— 從結果推導的話，
    // 一勾選某位作者，其餘作者的候選就消失了，再也回不去。
    void rebuildAuthorCandidates();
    void clearAuthorCandidates();
    void applyFilters();
    void updateFilterStatus();
    QSet<QString> checkedAuthors() const;
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
    QStandardItemModel    *m_authorModel;
    MrFilterProxyModel    *m_mrProxy;

    MrTableState m_mrState;

    // 取回筆數是否達到單次上限。改以持續顯示的狀態行承載，不再跳一次性的
    // 訊息框 —— 那個框按掉就沒了，而使用者正是在按掉之後才開始在候選清單
    // 裡找人，也就是最需要那個提示的時刻它剛好不在。
    bool m_truncated;

    // 重建候選作者時，setCheckState() 會發出 itemChanged，而那不是使用者的
    // 勾選。少了這個旗標，重建過程中會重複套用過濾並清掉表格選取。
    bool m_rebuildingAuthors;

    // 手動編號的輸入框會自我修正（貼上 !123 或整條網址時取出其中的數字），
    // 而 setText() 會再次觸發 textChanged。這個旗標擋掉那一層遞迴。
    bool m_sanitizingManualMr;
};

#endif // AIANALYSISGITLABMR_H
