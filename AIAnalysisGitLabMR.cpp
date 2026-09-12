#include "AIAnalysisGitLabMR.h"

#include "debug.h"

#include <QCheckBox>
#include <QComboBox>
#include <QDateTime>
#include <QDir>
#include <QFileDialog>
#include <QHeaderView>
#include <QItemSelectionModel>
#include <QJsonArray>
#include <QLineEdit>
#include <QListView>
#include <QPushButton>
#include <QRadioButton>
#include <QSortFilterProxyModel>
#include <QSpinBox>
#include <QStandardItem>
#include <QStandardItemModel>
#include <QStyle>
#include <QTableView>

#include <QCoreApplication>

namespace {

// 入口腳本依功能分組收在 scripts/<功能>/ 之下。
//
// 路徑寫死在這裡，MUST NOT 取自任何步驟的回傳資料 —— 腳本是程式的一部分，
// 不是使用者或資料該決定的東西。（既有工具的做法是「設定給了就用設定的，
// 留空才用步驟回傳的」，那兩行後備邏輯已經寫錯過一次，而且錯的時候症狀是
// 「找不到腳本」，直覺會去查設定檔。）
const char *kListMergeRequestsScript =
        "scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_list_merge_requests.py";
const char *kDescriptionScript =
        "scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_description.py";
const char *kScriptSelectorScript =
        "scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_script_selector.py";
const char *kSummaryScript =
        "scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py";
const char *kCodeReviewScript =
        "scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_code_review.py";
const char *kMergeToMdScript =
        "scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_merge_to_md.py";

// 流程共五步，固定。
const int kFlowStepCount = 5;

// 中間產物的檔名。序號前綴讓目錄的列出順序就是流程的執行順序 ——
// 出問題時一眼看得出停在哪一步。
const char *kStepArtifactName[kFlowStepCount] = {
    "01_description.md",
    "02_script_info.json",
    "03_summary.json",
    "04_code_review.md",
    "05_report.md"
};

// 共用服務的設定鍵。注入為環境變數時一律取鍵名的全大寫形式 ——
// 機械化的對應規則，不另外維護一張對照表。
const char *kServiceKey[] = {
    "Gitlab_Server_URL",
    "Gitlab_Access_Token",
    "Gitlab_Verify_SSL",
    "Jira_Server_URL",
    "Jira_Access_Token"
};
const int kServiceKeyCount =
        static_cast<int>(sizeof(kServiceKey) / sizeof(kServiceKey[0]));

// MR 表格的欄。只有標題欄伸縮，其餘固定寬。
//
// 這個 enum 是欄位順序的唯一來源：表頭文字、欄寬設定與填列都依它的索引走，
// 所以要調整欄序只改這裡。
enum MrColumn {
    ColumnIid = 0,
    ColumnState,
    ColumnTitle,
    ColumnAuthor,
    ColumnCreated,
    MrColumnCount
};

// 排序用的值與顯示用的文字分開存：建立日期顯示 yyyy-MM-dd，排序卻要依實際
// 的時間先後。兩者同一個 role、每一欄各自填入自己該有的可比較值。
const int kSortRole = Qt::UserRole + 1;

const char *const kNotFetchedText   = "按下重新整理以取得 Merge Requests";
const char *const kEmptyResultText  = "沒有符合條件的 Merge Request";

// 腳本失敗時給使用者看的原因。腳本連結果信封都沒回傳時 message 會是空的，
// 那種情況下顯示空字串等於什麼都沒說。
QString failureReason(const PythonRunner::PythonRunnerResult &result)
{
    if (!result.message.isEmpty())
        return result.message;
    if (!result.hasJson)
        return QString("腳本沒有回傳結果（exit code %1）").arg(result.exitCode);
    return QString("未提供失敗原因");
}

// 從使用者輸入中取出 Merge Request 編號。
//
// 刻意不用 QIntValidator：validator 會在「貼上」那一刻就整串拒絕，
// !123 與完整網址因此連進到輸入框的機會都沒有，也就沒有東西可以取出。
// 改成收下之後自我修正 —— 鍵入字母同樣會被立刻清掉，對使用者而言效果相同。
//
// 取最後一段數字：網址結尾是 iid（.../merge_requests/123），!123 也是。
QString extractMergeRequestIid(const QString &text)
{
    if (text.isEmpty())
        return text;

    QString last;
    QString current;
    for (int i = 0; i < text.size(); ++i) {
        if (text.at(i).isDigit()) {
            current.append(text.at(i));
        } else if (!current.isEmpty()) {
            last = current;
            current.clear();
        }
    }
    if (!current.isEmpty())
        last = current;

    return last;
}

} // namespace

// ---------------------------------------------------------------------------
// 建置
// ---------------------------------------------------------------------------

QString AIAnalysisGitLabMR::functionName()
{
    return QString("AI Analysis GitLab MR");
}

AIAnalysisGitLabMR::AIAnalysisGitLabMR(PPS2_0DevTool *shell, QObject *parent)
    : QObject(parent)
    , m_shell(shell)
    , m_repoModel(new QStandardItemModel(this))
    , m_mrModel(new QStandardItemModel(this))
    , m_mrProxy(new QSortFilterProxyModel(this))
    , m_mrState(MrNotFetched)
    , m_sanitizingManualMr(false)
{
    m_mrProxy->setSourceModel(m_mrModel);
    m_mrProxy->setSortRole(kSortRole);
    m_mrProxy->setDynamicSortFilter(true);
}

void AIAnalysisGitLabMR::attachWidgets(const AIAnalysisGitLabMRWidgets &widgets)
{
    m_widgets = widgets;

    // --- Repository 清單 ---
    m_widgets.repoView->setModel(m_repoModel);
    m_widgets.repoView->setSelectionMode(QAbstractItemView::SingleSelection);
    m_widgets.repoView->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_widgets.repoView->setUniformItemSizes(true);

    // --- MR 表格 ---
    m_widgets.mrView->setModel(m_mrProxy);
    m_widgets.mrView->setSelectionMode(QAbstractItemView::SingleSelection);
    m_widgets.mrView->setSelectionBehavior(QAbstractItemView::SelectRows);
    m_widgets.mrView->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_widgets.mrView->setSortingEnabled(true);
    m_widgets.mrView->verticalHeader()->setVisible(false);

    // 標題過長時截斷；完整標題由整列的 tooltip 提供（填資料時設 ToolTipRole）。
    m_widgets.mrView->setTextElideMode(Qt::ElideRight);
    m_widgets.mrView->setWordWrap(false);

    // 欄寬與伸縮模式不在這裡設 —— 此刻 model 還是 0 欄，header 一個 section
    // 都沒有。底下「初始狀態」的 setMrTableState() 會在建立欄位之後設好。

    // 重新整理鈕用 Qt 內建圖示，不新增任何圖示資產。
    m_widgets.refreshButton->setIcon(
                m_widgets.refreshButton->style()->standardIcon(
                    QStyle::SP_BrowserReload));

    // --- 設定填入畫面 ---
    const QJsonObject cfg = config();

    const QJsonArray repos = cfg.value(QString("Repo_List")).toArray();
    for (int i = 0; i < repos.size(); ++i) {
        const QString name = repos.at(i).toString();
        if (name.isEmpty())
            continue;
        QStandardItem *item = new QStandardItem(name);
        m_repoModel->appendRow(item);
    }

    const QJsonArray modes = cfg.value(QString("AI_Mode_List")).toArray();
    for (int i = 0; i < modes.size(); ++i) {
        const QString name = modes.at(i).toObject().value(QString("Name")).toString();
        if (!name.isEmpty())
            m_widgets.modeCombo->addItem(name);   // 順序即設定的順序，第一項為預設
    }

    m_widgets.saveDirEdit->setText(
                cfg.value(QString("Save_Analysis_File_Dir")).toString());

    // --- 訊號 ---
    connect(m_widgets.repoView->selectionModel(),
            SIGNAL(selectionChanged(QItemSelection,QItemSelection)),
            this, SLOT(onRepoSelectionChanged()));
    connect(m_widgets.mrView->selectionModel(),
            SIGNAL(selectionChanged(QItemSelection,QItemSelection)),
            this, SLOT(onMrSelectionChanged()));

    connect(m_widgets.manualMrRadio, SIGNAL(toggled(bool)),
            this, SLOT(onSourceModeToggled()));
    connect(m_widgets.manualMrEdit, SIGNAL(textChanged(QString)),
            this, SLOT(onManualMrTextChanged(QString)));

    connect(m_widgets.onlyOpenCheck, SIGNAL(toggled(bool)),
            this, SLOT(onQueryParameterChanged()));
    connect(m_widgets.createdAfterCheck, SIGNAL(toggled(bool)),
            this, SLOT(onQueryParameterChanged()));
    connect(m_widgets.createdAfterSpin, SIGNAL(valueChanged(int)),
            this, SLOT(onQueryParameterChanged()));

    connect(m_widgets.refreshButton, SIGNAL(clicked()),
            this, SLOT(onRefreshClicked()));
    connect(m_widgets.analysisButton, SIGNAL(clicked()),
            this, SLOT(onAnalysisClicked()));

    connect(m_widgets.debugFileCheck, SIGNAL(toggled(bool)),
            this, SLOT(onDebugFileToggled()));
    connect(m_widgets.saveDirEdit, SIGNAL(textChanged(QString)),
            this, SLOT(updateButtonStates()));
    connect(m_widgets.saveDirBrowseButton, SIGNAL(clicked()),
            this, SLOT(onSaveDirBrowseClicked()));

    connect(m_widgets.jiraNoneRadio, SIGNAL(toggled(bool)),
            this, SLOT(onJiraModeToggled()));
    connect(m_widgets.jiraManualRadio, SIGNAL(toggled(bool)),
            this, SLOT(onJiraModeToggled()));
    connect(m_widgets.jiraKeyEdit, SIGNAL(textChanged(QString)),
            this, SLOT(updateButtonStates()));

    // --- 初始狀態 ---
    setMrTableState(MrNotFetched, QString(kNotFetchedText));
    onSourceModeToggled();
    onDebugFileToggled();
    onJiraModeToggled();
    updateButtonStates();
}

// ---------------------------------------------------------------------------
// 設定
// ---------------------------------------------------------------------------

QJsonObject AIAnalysisGitLabMR::config() const
{
    // 回傳的是「Service 併上本功能區塊」的結果 —— 合併發生在外殼的查詢介面
    // 裡，這裡拿到的已經是平坦的物件。
    return m_shell->getFunctionConfig(functionName());
}

// 設定中的存放目錄可以是相對路徑。相對於執行檔目錄解析，與腳本路徑的處理
// 一致（見 PythonRunner::resolveScriptPath）—— 若改為繼承行程的當前目錄，
// 同一份設定檔在不同啟動方式下會解析出不同結果。
QString AIAnalysisGitLabMR::resolvedSaveDir() const
{
    const QString raw = m_widgets.saveDirEdit->text().trimmed();
    if (raw.isEmpty())
        return raw;

    const QString appDir = QCoreApplication::applicationDirPath();
    return QDir(appDir).absoluteFilePath(QDir::fromNativeSeparators(raw));
}

QMap<QString, QString> AIAnalysisGitLabMR::serviceEnvVars() const
{
    const QJsonObject cfg = config();

    QMap<QString, QString> env;
    for (int i = 0; i < kServiceKeyCount; ++i) {
        const QString key = QString::fromLatin1(kServiceKey[i]);
        env.insert(key.toUpper(), cfg.value(key).toString());
    }
    return env;
}

QJsonObject AIAnalysisGitLabMR::selectedAiMode() const
{
    const QString name = m_widgets.modeCombo->currentText();
    const QJsonArray modes = config().value(QString("AI_Mode_List")).toArray();
    for (int i = 0; i < modes.size(); ++i) {
        const QJsonObject mode = modes.at(i).toObject();
        if (mode.value(QString("Name")).toString() == name)
            return mode;
    }
    return QJsonObject();
}

// ---------------------------------------------------------------------------
// 畫面狀態
// ---------------------------------------------------------------------------

// 欄寬與伸縮模式每次都要重設。
//
// QStandardItemModel::clear() 會讓 QHeaderView 重新初始化各 section，逐 section
// 設過的 resize mode 與寬度會一起回到預設值。少了這一步，Title 欄在第一次重新
// 整理之後就不再伸縮 —— 而且症狀只在「載入過資料之後」才出現，開場看起來是對的。
void AIAnalysisGitLabMR::applyMrHeaderLayout()
{
    QHeaderView *header = m_widgets.mrView->horizontalHeader();

    // 欄位還沒建立就直接走人。
    //
    // setSectionResizeMode() 對不存在的 section 不是「安靜地什麼都不做」——
    // 它內部先 visualIndex() 拿到 -1，再拿那個 -1 去索引 section 陣列，於是
    // 直接 SIGSEGV。那行 Q_ASSERT(visual != -1) 在官方發行的 Qt binary 裡是
    // 編譯掉的（Qt 自己是 release build），所以連個訊息都不會有。
    //
    // 對照組：同一個函式裡的 setColumnWidth() 有做邊界檢查，越界就安靜返回。
    // 兩者行為不一致，所以這個守衛必須留著。
    if (header->count() < MrColumnCount)
        return;

    header->setSectionResizeMode(ColumnIid,     QHeaderView::Fixed);
    header->setSectionResizeMode(ColumnState,   QHeaderView::Fixed);
    header->setSectionResizeMode(ColumnTitle,   QHeaderView::Stretch);
    header->setSectionResizeMode(ColumnAuthor,  QHeaderView::Fixed);
    header->setSectionResizeMode(ColumnCreated, QHeaderView::Fixed);

    m_widgets.mrView->setColumnWidth(ColumnIid,     60);
    m_widgets.mrView->setColumnWidth(ColumnState,   70);
    m_widgets.mrView->setColumnWidth(ColumnAuthor,  110);
    m_widgets.mrView->setColumnWidth(ColumnCreated, 90);
}

// 空白的兩種狀態在畫面上長得一樣，但使用者該做的下一步不同。訊息列以整列
// 合併呈現，且不可選取 —— 否則 hasSelection() 會把提示文字當成一筆 MR。
void AIAnalysisGitLabMR::setMrTableState(MrTableState state,
                                         const QString &message)
{
    m_mrState = state;

    m_mrModel->clear();
    m_mrModel->setColumnCount(MrColumnCount);
    m_widgets.mrView->clearSpans();

    // 先配足長度再依索引指派，欄序完全由 MrColumn 決定。
    QStringList headers;
    for (int c = 0; c < MrColumnCount; ++c)
        headers << QString();
    headers[ColumnIid]     = QString("MR");
    headers[ColumnState]   = QString("Status");
    headers[ColumnTitle]   = QString("Title");
    headers[ColumnAuthor]  = QString("Author");
    headers[ColumnCreated] = QString("Created");
    m_mrModel->setHorizontalHeaderLabels(headers);

    // clear() 之後欄寬與伸縮模式都回到預設值，必須重設。
    applyMrHeaderLayout();

    if (state == MrLoaded)
        return;

    QStandardItem *item = new QStandardItem(message);
    item->setFlags(Qt::NoItemFlags);
    item->setTextAlignment(Qt::AlignCenter);
    m_mrModel->appendRow(item);
    m_widgets.mrView->setSpan(0, 0, 1, MrColumnCount);
}

// 切換 repository、或改動任何一項查詢條件，清單就過期了：畫面上顯示的會是
// 前一組條件的結果，而按下 AI Analysis 時採用的卻是當前的 repository。
void AIAnalysisGitLabMR::invalidateMrTable()
{
    setMrTableState(MrNotFetched, QString(kNotFetchedText));
    updateButtonStates();
}

QString AIAnalysisGitLabMR::selectedRepo() const
{
    const QModelIndexList selected =
            m_widgets.repoView->selectionModel()->selectedIndexes();
    if (selected.isEmpty())
        return QString();
    return m_repoModel->data(selected.first()).toString();
}

QString AIAnalysisGitLabMR::selectedMrIid() const
{
    if (m_mrState != MrLoaded)
        return QString();

    const QModelIndexList selected =
            m_widgets.mrView->selectionModel()->selectedRows(ColumnIid);
    if (selected.isEmpty())
        return QString();

    return m_mrProxy->data(selected.first()).toString();
}

// 兩條取得路徑產出同一種輸入：一個編號。
QString AIAnalysisGitLabMR::effectiveMrIid() const
{
    if (m_widgets.manualMrRadio->isChecked())
        return m_widgets.manualMrEdit->text().trimmed();
    return selectedMrIid();
}

QString AIAnalysisGitLabMR::jiraMode() const
{
    if (m_widgets.jiraNoneRadio->isChecked())
        return QString("none");
    if (m_widgets.jiraManualRadio->isChecked())
        return QString("manual");
    return QString("auto");
}

// ---------------------------------------------------------------------------
// 元件互動
// ---------------------------------------------------------------------------

void AIAnalysisGitLabMR::onRepoSelectionChanged()
{
    invalidateMrTable();
}

void AIAnalysisGitLabMR::onMrSelectionChanged()
{
    updateButtonStates();
}

// 兩種取得方式互斥：選了其中一種，另一種所屬的控件整組停用。
void AIAnalysisGitLabMR::onSourceModeToggled()
{
    const bool manual = m_widgets.manualMrRadio->isChecked();

    m_widgets.manualMrEdit->setEnabled(manual);

    m_widgets.onlyOpenCheck->setEnabled(!manual);
    m_widgets.createdAfterCheck->setEnabled(!manual);
    m_widgets.createdAfterSpin->setEnabled(!manual);
    m_widgets.mrView->setEnabled(!manual);

    updateButtonStates();
}

// 不產生檔案時，存放目錄那一列沒有意義 —— 留著可編輯會讓人以為它還有作用。
void AIAnalysisGitLabMR::onDebugFileToggled()
{
    const bool enabled = m_widgets.debugFileCheck->isChecked();
    m_widgets.saveDirEdit->setEnabled(enabled);
    m_widgets.saveDirBrowseButton->setEnabled(enabled);
    updateButtonStates();
}

void AIAnalysisGitLabMR::onJiraModeToggled()
{
    m_widgets.jiraKeyEdit->setEnabled(m_widgets.jiraManualRadio->isChecked());
    updateButtonStates();
}

void AIAnalysisGitLabMR::onSaveDirBrowseClicked()
{
    const QString dir = QFileDialog::getExistingDirectory(
                Q_NULLPTR, QString("選擇分析檔存放目錄"), resolvedSaveDir());
    if (dir.isEmpty())
        return;
    m_widgets.saveDirEdit->setText(QDir::toNativeSeparators(dir));
}

void AIAnalysisGitLabMR::onManualMrTextChanged(const QString &text)
{
    if (m_sanitizingManualMr)
        return;

    const QString cleaned = extractMergeRequestIid(text);
    if (cleaned != text) {
        m_sanitizingManualMr = true;
        m_widgets.manualMrEdit->setText(cleaned);
        m_sanitizingManualMr = false;
    }

    updateButtonStates();
}

void AIAnalysisGitLabMR::onQueryParameterChanged()
{
    invalidateMrTable();
}

void AIAnalysisGitLabMR::updateButtonStates()
{
    if (!m_widgets.analysisButton)
        return;

    // 未選 repository 就沒有東西可以抓。
    m_widgets.refreshButton->setEnabled(
                !m_widgets.manualMrRadio->isChecked()
                && !selectedRepo().isEmpty());

    // 四個條件全部成立才可以按。停用時刻意不加 tooltip 也不加狀態文字 ——
    // 與 Single Building 的既有作法一致。
    bool ready = !selectedRepo().isEmpty()
            && !effectiveMrIid().isEmpty();

    if (m_widgets.debugFileCheck->isChecked()
            && m_widgets.saveDirEdit->text().trimmed().isEmpty())
        ready = false;

    if (m_widgets.jiraManualRadio->isChecked()
            && m_widgets.jiraKeyEdit->text().trimmed().isEmpty())
        ready = false;

    m_widgets.analysisButton->setEnabled(ready);
}

// ---------------------------------------------------------------------------
// 取得 Merge Request 清單
// ---------------------------------------------------------------------------

void AIAnalysisGitLabMR::onRefreshClicked()
{
    const QString repo = selectedRepo();
    if (repo.isEmpty())
        return;

    QJsonObject params;
    params.insert(QString("repo"), repo);
    params.insert(QString("only_open"), m_widgets.onlyOpenCheck->isChecked());
    params.insert(QString("created_after_enabled"),
                  m_widgets.createdAfterCheck->isChecked());
    params.insert(QString("created_after_days"),
                  m_widgets.createdAfterSpin->value());

    // 憑證與端點必須跟著送 —— 這一支腳本只從環境變數取用它們。
    //
    // runFunctionScript() 的 envVars 是帶預設值的第六個參數，漏了不會有編譯
    // 錯誤：腳本照樣啟動、照樣執行，只是拿到空字串然後回報「未設定環境變數」。
    // 症狀看起來像使用者沒設定，實際上是呼叫端沒送。
    m_shell->runFunctionScript(
        functionName(), QString(kListMergeRequestsScript),
        QString("list_merge_requests"), params,
        [this](const PythonRunner::PythonRunnerResult &result) {
            if (!result.success) {
                // 保留失敗前的舊內容會讓使用者誤以為那是當前條件的結果。
                setMrTableState(MrNotFetched, QString(kNotFetchedText));
                updateButtonStates();
                m_shell->showUI_ErrorMessageBox(
                            QString("取得 Merge Request 清單失敗：\n%1")
                            .arg(failureReason(result)));
                return;
            }

            const QJsonArray items =
                    result.data.value(QString("merge_requests")).toArray();

            if (items.isEmpty()) {
                // 零筆是成功而非失敗 —— 條件太緊是正常結果，不該跳錯誤框。
                setMrTableState(MrEmptyResult, QString(kEmptyResultText));
                updateButtonStates();
                return;
            }

            setMrTableState(MrLoaded, QString());

            for (int i = 0; i < items.size(); ++i) {
                const QJsonObject mr = items.at(i).toObject();

                const QString iid     = QString::number(
                            static_cast<qint64>(mr.value(QString("iid")).toDouble()));
                const QString title   = mr.value(QString("title")).toString();
                const QString author  = mr.value(QString("author")).toString();
                const QString created = mr.value(QString("created_at")).toString();
                const QString state   = mr.value(QString("state")).toString();

                // 依 MrColumn 的索引指派，不靠 append 的先後順序 ——
                // 這樣調整欄序時只要改 enum，這裡不會被漏掉。
                QList<QStandardItem *> row;
                for (int c = 0; c < MrColumnCount; ++c)
                    row << Q_NULLPTR;

                QStandardItem *iidItem = new QStandardItem(iid);
                iidItem->setData(iid.toLongLong(), kSortRole);
                row[ColumnIid] = iidItem;

                QStandardItem *stateItem = new QStandardItem(state);
                stateItem->setData(state, kSortRole);
                row[ColumnState] = stateItem;

                QStandardItem *titleItem = new QStandardItem(title);
                titleItem->setData(title, kSortRole);
                titleItem->setToolTip(title);   // 截斷後仍看得到全文
                row[ColumnTitle] = titleItem;

                QStandardItem *authorItem = new QStandardItem(author);
                authorItem->setData(author, kSortRole);
                row[ColumnAuthor] = authorItem;

                // 顯示絕對日期，排序依完整的時間戳 —— 「3 天前」這種相對
                // 文字若拿去字串比較，10 天前會排在 3 天前之前。
                QStandardItem *createdItem = new QStandardItem(created.left(10));
                createdItem->setData(created, kSortRole);
                createdItem->setToolTip(created);
                row[ColumnCreated] = createdItem;

                for (int c = 0; c < row.size(); ++c)
                    row.at(c)->setEditable(false);

                m_mrModel->appendRow(row);
            }

            updateButtonStates();

            // 腳本在取回筆數達到上限時會這樣標示 —— 「剛好 100 筆」與
            // 「其實有 300 筆」在畫面上完全一樣，不說使用者無從得知。
            if (result.data.value(QString("truncated")).toBool()) {
                m_shell->showUI_WarningMessageBox(
                            QString("結果可能未完整：已達單次取回的上限。\n"
                                    "請縮小查詢條件以取得完整清單。"));
            }
        },
        serviceEnvVars());
}

// ---------------------------------------------------------------------------
// 分析流程
// ---------------------------------------------------------------------------

void AIAnalysisGitLabMR::onAnalysisClicked()
{
    AnalysisContext context;
    context.repo   = selectedRepo();
    context.mrIid  = effectiveMrIid();

    const QJsonObject mode = selectedAiMode();
    context.aiModeName = mode.value(QString("Name")).toString();
    context.aiApiUrl   = mode.value(QString("Api_URL")).toString();
    context.aiApiKey   = mode.value(QString("Api_Key")).toString();
    context.aiModel    = mode.value(QString("Model")).toString();

    context.jiraMode      = jiraMode();
    context.jiraKeyManual = m_widgets.jiraKeyEdit->text().trimmed();
    context.envVars       = serviceEnvVars();

    // 除錯目錄在流程啟動**之前**建立。路徑打錯或沒有寫入權限會在這一刻就
    // 爆出來，而不是等到跑完前三步、付完 AI 的錢，才在第四步發現寫不進去。
    //
    // 時間戳只取一次，五個步驟因此寫進同一個目錄 —— 若每步各自取，跨秒時
    // 會冒出兩個目錄，而且是偶發的。
    if (m_widgets.debugFileCheck->isChecked()) {
        const QString baseDir = resolvedSaveDir();
        const QString stamp =
                QDateTime::currentDateTime().toString("yyyyMMdd_HHmmss");

        // repo 取最後一段：namespace/project 裡的斜線不能出現在目錄名中。
        const QString repoLeaf = context.repo.section(QChar('/'), -1);

        const QString name = QString("gitlab_mr_result_%1_%2_%3")
                .arg(repoLeaf, context.mrIid, stamp);

        // absoluteFilePath() 而不是字串串接：手動串 "\\" 在 Linux 上會組出
        // 一個名字裡帶反斜線的單一檔案，而且它也順手吃掉了 baseDir 結尾有沒有
        // 斜線的問題。
        const QString dir = QDir(baseDir).absoluteFilePath(name);

        // mkpath() 而不是 mkdir()：後者只建一層，存放目錄本身還不存在時會失敗。
        if (!QDir().mkpath(dir)) {
            m_shell->showUI_ErrorMessageBox(
                        QString("無法建立分析檔目錄：\n%1")
                        .arg(QDir::toNativeSeparators(dir)));
            return;
        }

        QTDebug(QString("[%1] 分析檔目錄：%2").arg(functionName(), dir));
        context.debugDir = dir;
    }

    // 決策函式在步驟之間同步執行，裡面不得有任何使用者互動。
    //
    // 它也不含任何業務判斷：失敗就結束，否則依已完成的步數給出下一步。
    // 「第 4 步要不要真的去抓」這種判斷壓在腳本的參數裡，不在這裡 ——
    // 否則 CI 的 shell 得再實作一次同樣的分支。
    PPS2_0DevTool::FlowDecider decide =
            [this, context](const QList<PythonRunner::PythonRunnerResult> &done)
            -> PPS2_0DevTool::FlowStep {
        if (!done.isEmpty() && !done.last().success)
            return PPS2_0DevTool::FlowStep::done();
        if (done.size() >= kFlowStepCount)
            return PPS2_0DevTool::FlowStep::done();
        return buildStep(done.size(), context, done);
    };

    PPS2_0DevTool::FlowCallback finished =
            [this](const PPS2_0DevTool::FlowResult &result) {
        onFlowFinished(result);
    };

    m_shell->runFunctionFlow(functionName(), decide, finished);
}

PPS2_0DevTool::FlowStep AIAnalysisGitLabMR::buildStep(
        int index,
        const AnalysisContext &context,
        const QList<PythonRunner::PythonRunnerResult> &done) const
{
    PPS2_0DevTool::FlowStep step;
    step.envVars = context.envVars;

    QJsonObject params;
    params.insert(QString("repo"),    context.repo);
    params.insert(QString("mr_iid"),  context.mrIid);
    params.insert(QString("debug_dir"), context.debugDir);

    // 勾了除錯才給輸出路徑；沒給的話腳本不寫任何檔案。
    if (!context.debugDir.isEmpty()) {
        params.insert(QString("out_path"),
                      QDir(context.debugDir).absoluteFilePath(
                          QString::fromLatin1(kStepArtifactName[index])));
    }

    // 前面步驟的結果原樣轉送 —— 只挑欄位、改名、轉送，不解讀、不分支。
    const QJsonObject scriptInfo = (done.size() > 1)
            ? done.at(1).data.value(QString("script_info")).toObject()
            : QJsonObject();

    switch (index) {
    case 0:
        step.label      = QString("步驟 1/5：取得 Merge Request 描述");
        step.scriptPath = QString(kDescriptionScript);
        step.action     = QString("mr_description");
        break;

    case 1:
        step.label      = QString("步驟 2/5：取得相關資訊");
        step.scriptPath = QString(kScriptSelectorScript);
        step.action     = QString("script_selector");
        params.insert(QString("description"),
                      done.at(0).data.value(QString("description")).toString());
        // device 的來源尚未定案（見 design.md Open Questions）。參數照樣
        // 宣告並傳空字串，腳本收下但本輪不使用。
        params.insert(QString("device"), QString());
        break;

    case 2:
        step.label      = QString("步驟 3/5：AI 分析");
        step.scriptPath = QString(kSummaryScript);
        step.action     = QString("ai_summary");
        params.insert(QString("description"),
                      done.at(0).data.value(QString("description")).toString());
        params.insert(QString("script_info"), scriptInfo);
        // AI 的三項走 params（不注入環境變數），因此不會出現在命令列上。
        params.insert(QString("ai_mode_name"), context.aiModeName);
        params.insert(QString("ai_api_url"),   context.aiApiUrl);
        params.insert(QString("ai_api_key"),   context.aiApiKey);
        params.insert(QString("ai_model"),     context.aiModel);
        // JIRA 的三個值一併送出，由腳本決定採用哪一個 —— 在這裡挑的話，
        // CI 那一側就得再實作一次同樣的三個分支。
        params.insert(QString("jira_mode"),        context.jiraMode);
        params.insert(QString("jira_key_manual"),  context.jiraKeyManual);
        params.insert(QString("jira_key_detected"),
                      scriptInfo.value(QString("jira_key")).toString());
        break;

    case 3:
        step.label      = QString("步驟 4/5：取得程式碼審閱報告");
        step.scriptPath = QString(kCodeReviewScript);
        step.action     = QString("fetch_code_review");
        // 這一步永遠執行。「要不要真的去抓」由腳本看這個參數決定，Qt 端不跳過
        // 任何步驟 —— 見 design.md 決策十三。來源尚未定案，本輪固定為 false。
        params.insert(QString("fetch_code_review"), false);
        break;

    case 4:
        step.label      = QString("步驟 5/5：合併為 markdown");
        step.scriptPath = QString(kMergeToMdScript);
        step.action     = QString("merge_to_md");
        params.insert(QString("description"),
                      done.at(0).data.value(QString("description")).toString());
        params.insert(QString("script_info"), scriptInfo);
        params.insert(QString("summary"),
                      done.at(2).data.value(QString("summary")).toString());
        params.insert(QString("code_review"),
                      done.at(3).data.value(QString("code_review")).toString());
        break;

    default:
        return PPS2_0DevTool::FlowStep::done();
    }

    step.params = params;
    return step;
}

void AIAnalysisGitLabMR::onFlowFinished(const PPS2_0DevTool::FlowResult &result)
{
    if (!result.success) {
        const int stepNumber = result.failedStepIndex + 1;
        const QString reason = (result.failedStepIndex >= 0
                                && result.failedStepIndex < result.results.size())
                ? failureReason(result.results.at(result.failedStepIndex))
                : QString("未提供失敗原因");

        // 失敗即停：後續步驟沒有被啟動，畫面也沒有任何元素改變。
        m_shell->showUI_ErrorMessageBox(
                    QString("AI 分析在第 %1 步失敗：\n%2")
                    .arg(stepNumber).arg(reason));
        return;
    }

    // 內容取自最後一步的 data，不開任何檔案 —— 未勾選除錯時根本沒有檔案。
    const QString markdown = result.results.isEmpty()
            ? QString()
            : result.results.last().data.value(QString("markdown")).toString();

    m_shell->showResultDialog(QString("AI Analysis"), markdown,
                              result.elapsedMs);
}
