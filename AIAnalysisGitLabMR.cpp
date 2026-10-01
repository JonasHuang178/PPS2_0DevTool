#include "AIAnalysisGitLabMR.h"

#include "debug.h"

#include <QCheckBox>
#include <QColor>
#include <QComboBox>
#include <QDateTime>
#include <QDesktopServices>
#include <QDir>
#include <QFile>
#include <QFileDialog>
#include <QFont>
#include <QHeaderView>
#include <QItemSelectionModel>
#include <QJsonArray>
#include <QLabel>
#include <QLineEdit>
#include <QListView>
#include <QMap>
#include <QPushButton>
#include <QRadioButton>
#include <QSpinBox>
#include <QStandardItem>
#include <QStandardItemModel>
#include <QStringList>
#include <QApplication>
#include <QPainter>
#include <QStyle>
#include <QTableView>
#include <QTemporaryDir>
#include <QToolButton>
#include <QUrl>
#include <QWidget>

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
const char *kMrInfoScript =
        "scripts/ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_info.py";
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
    "02_mr_info.json",
    "03_summary.json",
    // 結構而非排好版的 markdown：報告要印出附件的日期、作者與連結，而那三個值只有
    // 步驟 4 拿得到，步驟 5 收到的只是這個路徑。渲染在步驟 5，與 03_summary.json 同理。
    "04_code_review.json",
    "05_report.md"
};

// 共用服務的設定鍵。注入為環境變數時一律取鍵名的全大寫形式 ——
// 機械化的對應規則，不另外維護一張對照表。
const char *kServiceKey[] = {
    // device 不是憑證，但走同一條注入路徑：腳本只從環境變數讀，Qt 與 CI 對它來說
    // 長得一模一樣。鍵名全大寫即為變數名，所以這裡是 PPS_Device -> PPS_DEVICE。
    "PPS_Device",
    // code review 附件的檔名前綴，同上那條注入路徑。沒有預設值 —— 沒設定時步驟 4
    // 直接失敗並點名這個鍵，因為給了預設值會讓漏設的人靜默用到一個他沒選的前綴。
    "PPS_Scripts_CodeReview_File_StartsWith",
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

// 標題欄項目上存放該筆的 GitLab 網址。
//
// 網址**取自取得清單那一步的回傳資料**，不由這裡組合 —— 它早就在回傳裡
// （見那支腳本的 _row()），只是先前沒有被接起來。自己組的話就多一份對
// GitLab 網址形狀的假設，而那份假設沒有任何東西會驗證它。
const int kWebUrlRole = Qt::UserRole + 2;

// 候選作者項目上存放**未經加工的作者名稱**。顯示文字是「名稱 (筆數)」，
// 拿顯示文字去比對表格裡的作者永遠對不上。
const int kAuthorNameRole = Qt::UserRole + 1;

// 標題欄的連結色。與選取時的前景色（#042C53）刻意不同，否則選中那一列就
// 看不出標題是可點的 —— 而要讓它在選取時真的留著，光靠 ForegroundRole 不夠，
// 見 LinkColumnDelegate。
const char *const kLinkColor = "#0B57D0";

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

// 把工作目錄下的某個產物當成參數送出 —— 檔案不存在就整個鍵不放。
//
// 合併那一步的契約是「路徑給了就必須存在」：指名一個不存在的檔案代表上一步
// 沒寫成功，該當成錯誤停下來。而「這一段本來就沒有內容」（例如未要求程式碼
// 審閱）要表達成**沒給**，不是給一個指向空氣的路徑。兩者的差別全靠這裡。
// 設定檔的關鍵字清單填進輸入框：以 ", " 串接。
//
// 設定檔用 JSON array（與 Repo_List、AI_Mode_List 同一個慣例），輸入框是逗號
// 分隔的一行 —— 中間只有這一個轉換，而且是**單向**的：使用者改過的內容不寫回
// 任何地方，重新啟動就回到設定檔的值。
QString joinKeywords(const QJsonArray &items)
{
    QStringList out;
    for (int i = 0; i < items.size(); ++i) {
        const QString one = items.at(i).toString().trimmed();
        if (!one.isEmpty())
            out.append(one);
    }
    return out.join(QString(", "));
}

// 設定檔裡的數值，數字與字串兩種寫法都收。
//
// 這個設定檔的慣例是用字串裝值（`"Debug_Mode": "false"`），但數字本來就會被寫成數字，
// 兩種都有人寫。只認其中一種的結果是「我明明填了，它當作沒填」—— 而那在畫面上看不出來。
//
// 原樣轉成字串交給腳本，由腳本去驗與正規化：驗一次就好，而腳本那一側是命令列與 CI
// 也會經過的路徑。
QString configNumber(const QJsonObject &object, const QString &key)
{
    const QJsonValue value = object.value(key);
    if (value.isDouble())
        return QString::number(value.toDouble());
    return value.toString().trimmed();
}

void insertArtifactPath(QJsonObject &params,
                        const QString &key,
                        const QDir &workDir,
                        const char *artifactName)
{
    const QString path =
            workDir.absoluteFilePath(QString::fromLatin1(artifactName));
    if (QFile::exists(path))
        params.insert(key, path);
}

} // namespace

// ---------------------------------------------------------------------------
// LinkColumnDelegate
// ---------------------------------------------------------------------------

LinkColumnDelegate::LinkColumnDelegate(QObject *parent)
    : QStyledItemDelegate(parent)
{
}

void LinkColumnDelegate::initStyleOption(QStyleOptionViewItem *option,
                                         const QModelIndex &index) const
{
    QStyledItemDelegate::initStyleOption(option, index);

    // ForegroundRole 已經被基底類別套進 QPalette::Text，但選取時畫的是
    // HighlightedText —— 把同一個顏色也放進去，paint() 才取得到它。
    //
    // 讀的是**項目自己的** ForegroundRole，而不是寫死 kLinkColor：這個委派因此
    // 不必知道那個顏色是什麼，換色只要改填資料的那一邊。
    const QVariant colour = index.data(Qt::ForegroundRole);
    if (colour.canConvert<QColor>())
        option->palette.setColor(QPalette::HighlightedText,
                                 colour.value<QColor>());
}

void LinkColumnDelegate::paint(QPainter *painter,
                               const QStyleOptionViewItem &option,
                               const QModelIndex &index) const
{
    QStyleOptionViewItem opt = option;
    initStyleOption(&opt, index);

    QStyle *style = opt.widget ? opt.widget->style() : QApplication::style();

    // 文字區域要在清掉文字**之前**算，免得日後某個樣式把它算得與內容有關。
    const QRect textRect =
            style->subElementRect(QStyle::SE_ItemViewItemText, &opt, opt.widget);
    const QString text = opt.text;

    // 讓樣式畫背景、選取高亮與焦點框，但**不要讓它畫文字** —— 外殼的樣式表規則
    // 會在這一步把選取時的文字色寫死，而那正是要覆寫的東西。文字自己畫是唯一能
    // 蓋過它的方式（試過只改 palette，沒有用）。
    opt.text.clear();
    style->drawControl(QStyle::CE_ItemViewItem, &opt, painter, opt.widget);

    if (text.isEmpty())
        return;

    const bool selected = (opt.state & QStyle::State_Selected) != 0;
    const QColor colour = opt.palette.color(opt.state & QStyle::State_Enabled
                                            ? QPalette::Normal : QPalette::Disabled,
                                            selected ? QPalette::HighlightedText
                                                     : QPalette::Text);

    // 截斷與對齊沿用 option 上的值，不自己訂 —— 那兩個由檢視與項目決定，寫死在這裡
    // 就會與其餘四欄不一致，而症狀是「只有標題欄的省略號出現得比較早」。
    painter->save();
    painter->setFont(opt.font);
    painter->setPen(colour);
    painter->drawText(textRect,
                      int(opt.displayAlignment),
                      opt.fontMetrics.elidedText(text, opt.textElideMode,
                                                 textRect.width()));
    painter->restore();
}

// ---------------------------------------------------------------------------
// MrFilterProxyModel
// ---------------------------------------------------------------------------

MrFilterProxyModel::MrFilterProxyModel(int authorColumn, int titleColumn,
                                       QObject *parent)
    : QSortFilterProxyModel(parent)
    , m_authorColumn(authorColumn)
    , m_titleColumn(titleColumn)
{
}

void MrFilterProxyModel::setAuthors(const QSet<QString> &authors)
{
    m_authors = authors;
    invalidateFilter();
}

void MrFilterProxyModel::setSkipRules(const QStringList &startsWith,
                                      const QStringList &endsWith,
                                      const QStringList &contains)
{
    m_startsWith = startsWith;
    m_endsWith   = endsWith;
    m_contains   = contains;
    invalidateFilter();
}

bool MrFilterProxyModel::authorAccepts(const QString &author) const
{
    // 空集合代表不過濾 —— 一個都沒勾等同顯示全部。
    return m_authors.isEmpty() || m_authors.contains(author);
}

bool MrFilterProxyModel::titleAccepts(const QString &title) const
{
    // 比對一律區分大小寫，且所有字元都是字面文字 —— 不支援萬用字元或正規
    // 表示法。本工具另一個功能的過濾已明文如此，兩個輸入框對同一個字元的
    // 解讀不該相反。
    for (int i = 0; i < m_startsWith.size(); ++i) {
        if (title.startsWith(m_startsWith.at(i), Qt::CaseSensitive))
            return false;
    }
    for (int i = 0; i < m_endsWith.size(); ++i) {
        if (title.endsWith(m_endsWith.at(i), Qt::CaseSensitive))
            return false;
    }
    for (int i = 0; i < m_contains.size(); ++i) {
        if (title.contains(m_contains.at(i), Qt::CaseSensitive))
            return false;
    }
    return true;
}

bool MrFilterProxyModel::filterAcceptsRow(int sourceRow,
                                          const QModelIndex &sourceParent) const
{
    QAbstractItemModel *model = sourceModel();
    if (!model)
        return true;

    const QString author =
            model->index(sourceRow, m_authorColumn, sourceParent).data().toString();
    const QString title =
            model->index(sourceRow, m_titleColumn, sourceParent).data().toString();

    // 兩個條件為 AND，順序與統計的算法一致（先作者，再標題）。
    //
    // 表格顯示提示文字（尚未取得／沒有符合條件）時只有一列，而那一列的作者
    // 與標題都是空字串：候選作者在那些狀態下已被清空（集合為空 -> 不過濾），
    // 而空標題不可能被任何非空關鍵字命中，所以提示列不會被藏起來。
    return authorAccepts(author) && titleAccepts(title);
}

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
    , m_authorModel(new QStandardItemModel(this))
    , m_mrProxy(new MrFilterProxyModel(ColumnAuthor, ColumnTitle, this))
    , m_mrState(MrNotFetched)
    , m_truncated(false)
    , m_rebuildingAuthors(false)
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

    // 標題欄專用的委派，只為了一件事：選取那一列時連結色不要消失（見該類別）。
    m_widgets.mrView->setItemDelegateForColumn(ColumnTitle,
                                               new LinkColumnDelegate(this));

    // 指標移入標題欄時改變游標形狀。
    //
    // entered() 需要滑鼠追蹤，而 QAbstractScrollArea 的事件來自 viewport —— 只在
    // view 上設定，訊號不會發出，而那個失敗沒有任何徵兆。
    m_widgets.mrView->setMouseTracking(true);
    m_widgets.mrView->viewport()->setMouseTracking(true);

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

    // --- Filter 群組 ---
    m_widgets.authorView->setModel(m_authorModel);
    m_widgets.authorView->setEditTriggers(QAbstractItemView::NoEditTriggers);
    m_widgets.authorView->setSelectionMode(QAbstractItemView::NoSelection);
    m_widgets.authorView->setUniformItemSizes(true);

    // 預設收合：過濾不是每次都要調的東西，而視窗是固定尺寸，展開那一百多像素
    // 就是表格的四到五列。
    m_widgets.filterToggleButton->setArrowType(Qt::RightArrow);
    m_widgets.filterToggleButton->setChecked(false);
    m_widgets.filterContentWidget->setVisible(false);

    // 排除關鍵字的預設值來自設定檔。使用者在執行期間的修改不寫回任何地方 ——
    // 重新啟動就回到這裡填進去的值。
    m_widgets.skipStartsWithEdit->setText(
                joinKeywords(cfg.value(QString("Skip_Title_StartsWith_List")).toArray()));
    m_widgets.skipEndsWithEdit->setText(
                joinKeywords(cfg.value(QString("Skip_Title_EndsWith_List")).toArray()));
    m_widgets.skipContainsEdit->setText(
                joinKeywords(cfg.value(QString("Skip_Title_Contains_List")).toArray()));

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

    connect(m_widgets.filterToggleButton, SIGNAL(toggled(bool)),
            this, SLOT(onFilterToggled(bool)));
    connect(m_widgets.filterClearButton, SIGNAL(clicked()),
            this, SLOT(onClearFilterClicked()));
    connect(m_authorModel, SIGNAL(itemChanged(QStandardItem*)),
            this, SLOT(onAuthorItemChanged(QStandardItem*)));

    // 排除關鍵字以**輸入結束**才套用，不逐字元套用 —— 否則表格會在輸入
    // 「skip」的過程中隨 s、sk、ski 連續重算。來源路徑那個輸入框用的是同一個
    // 慣例（見外殼的 onSourcePathEdited）。
    connect(m_widgets.skipStartsWithEdit, SIGNAL(editingFinished()),
            this, SLOT(onSkipRulesEdited()));
    connect(m_widgets.skipEndsWithEdit, SIGNAL(editingFinished()),
            this, SLOT(onSkipRulesEdited()));
    connect(m_widgets.skipContainsEdit, SIGNAL(editingFinished()),
            this, SLOT(onSkipRulesEdited()));

    connect(m_widgets.mrView, SIGNAL(doubleClicked(QModelIndex)),
            this, SLOT(onMrDoubleClicked(QModelIndex)));
    connect(m_widgets.mrView, SIGNAL(entered(QModelIndex)),
            this, SLOT(onMrEntered(QModelIndex)));
    connect(m_widgets.mrView, SIGNAL(viewportEntered()),
            this, SLOT(onMrViewportEntered()));
    connect(m_widgets.repoView, SIGNAL(doubleClicked(QModelIndex)),
            this, SLOT(onRepoDoubleClicked(QModelIndex)));

    // --- 初始狀態 ---
    setMrTableState(MrNotFetched, QString(kNotFetchedText));
    applyFilters();
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

    // Status 容得下最寬的那個狀態。GitLab 的狀態只有 opened / closed / merged /
    // locked 四種，最寬的是 merged；原本的 70 會把它與 opened 都截成 `open…`。
    // 多留一些是給別的字型與 DPI 的餘裕 —— 這幾個值是在這個容器的字型下量出來的，
    // Windows 上的字型不同。
    m_widgets.mrView->setColumnWidth(ColumnState,   85);

    // Author 容得下「名 姓」這種常見長度（`Jonas Huang` 量到 114，原本的 110 差一點點，
    // 於是每一列都是 `Jonas Hua…`）。
    //
    // **不追求容得下所有名字** —— 再長的名字一定存在，而這一欄每多一像素，會伸縮的
    // 標題欄就少一像素。截斷的那幾筆由提示文字補上（見填資料的那一段）。
    m_widgets.mrView->setColumnWidth(ColumnAuthor,  150);
    // Created 比它顯示的字串寬一截，是因為那一欄現在固定帶著排序指示器的箭頭
    // （見底下的預設排序）。維持 90 的話 `2026-09-30` 會被截成 `2026-0…`。
    m_widgets.mrView->setColumnWidth(ColumnCreated, 115);

    // 預設排序：建立日期由新到舊。
    //
    // 與欄寬同一個理由寫在這裡 —— clear() 之後連排序指示器也回到預設（第 0 欄遞增），
    // 所以每次重建都要重設。而這裡正是「每次重建」唯一會經過的地方。
    //
    // 在資料塞進來**之前**設定是對的：proxy 開著 dynamicSortFilter，之後插入的列會
    // 自動落到正確的位置。
    //
    // 排序依的是 kSortRole 放的完整時間戳（畫面上只顯示到日），所以同一天的多筆也排得開。
    // 使用者之後可以自己點欄位改排序，那個選擇會留到下一次重新整理為止 —— 重新整理是
    // 一批新資料，回到預設才是可預期的。
    m_widgets.mrView->sortByColumn(ColumnCreated, Qt::DescendingOrder);
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

    if (state != MrLoaded) {
        // 候選作者是從那一批資料推導出來的。資料沒了，候選也不該留著 ——
        // 而且留著一個非空的作者集合會讓底下那一列提示文字被過濾掉。
        clearAuthorCandidates();
        m_truncated = false;
    }

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

    // 顯示過濾器的設定**不重設** —— 它們不是查詢條件，使用者填的排除關鍵字不該
    // 因為換了一個 repository 就消失。候選作者則由 setMrTableState 清掉。
    applyFilters();
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
// 顯示過濾
// ---------------------------------------------------------------------------

void AIAnalysisGitLabMR::onFilterToggled(bool expanded)
{
    m_widgets.filterToggleButton->setArrowType(expanded ? Qt::DownArrow
                                                        : Qt::RightArrow);
    m_widgets.filterContentWidget->setVisible(expanded);
}

void AIAnalysisGitLabMR::onAuthorItemChanged(QStandardItem *item)
{
    Q_UNUSED(item);

    // 重建候選時 setCheckState() 也會發這個訊號，而那不是使用者的勾選。
    if (m_rebuildingAuthors)
        return;

    applyFilters();
}

void AIAnalysisGitLabMR::onSkipRulesEdited()
{
    applyFilters();
}

void AIAnalysisGitLabMR::onClearFilterClicked()
{
    m_rebuildingAuthors = true;
    for (int row = 0; row < m_authorModel->rowCount(); ++row) {
        if (QStandardItem *item = m_authorModel->item(row))
            item->setCheckState(Qt::Unchecked);
    }
    m_rebuildingAuthors = false;

    // clear() 不會發出 editingFinished（那個訊號只在使用者結束輸入時發出），
    // 所以底下要自己套用一次。
    m_widgets.skipStartsWithEdit->clear();
    m_widgets.skipEndsWithEdit->clear();
    m_widgets.skipContainsEdit->clear();

    applyFilters();
}

QStringList AIAnalysisGitLabMR::parseSkipKeywords(const QString &text)
{
    QStringList out;
    const QStringList parts = text.split(QChar(','));
    for (int i = 0; i < parts.size(); ++i) {
        const QString one = parts.at(i).trimmed();

        // 空的關鍵字一律丟掉。空字串是**所有**標題的子字串，留著的話一個多餘的
        // 逗號就會讓整張表格一筆不剩 —— 而畫面上看不出成因。使用者打字打到
        // 「skip,」那一瞬間正是這個情況。
        if (!one.isEmpty())
            out.append(one);
    }
    return out;
}

QSet<QString> AIAnalysisGitLabMR::checkedAuthors() const
{
    QSet<QString> picked;
    for (int row = 0; row < m_authorModel->rowCount(); ++row) {
        QStandardItem *item = m_authorModel->item(row);
        if (item && item->checkState() == Qt::Checked)
            picked.insert(item->data(kAuthorNameRole).toString());
    }
    return picked;
}

void AIAnalysisGitLabMR::clearAuthorCandidates()
{
    m_rebuildingAuthors = true;
    m_authorModel->clear();
    m_rebuildingAuthors = false;

    // 清掉候選時必須同時把作者條件也清掉。留著一個非空的集合，表格那一列提示
    // 文字（作者欄是空字串）會被判定為不符而整列消失，畫面上只剩一片空白。
    m_mrProxy->setAuthors(QSet<QString>());
}

void AIAnalysisGitLabMR::rebuildAuthorCandidates()
{
    clearAuthorCandidates();

    // 自**來源模型**推導，不從過濾後的結果推導 —— 從結果推導的話，一勾選某位
    // 作者，其餘作者的候選就跟著消失，使用者再也回不去。
    //
    // QMap 依鍵排序，所以候選的次序就是作者名稱的次序：穩定且可預期，同一批
    // 資料兩次載入不會排出不同結果。
    QMap<QString, int> counts;
    for (int row = 0; row < m_mrModel->rowCount(); ++row) {
        const QString author =
                m_mrModel->index(row, ColumnAuthor).data().toString();
        counts[author] += 1;
    }

    m_rebuildingAuthors = true;
    for (QMap<QString, int>::const_iterator it = counts.constBegin();
         it != counts.constEnd(); ++it) {
        // 作者為空字串時仍然建立候選（GitLab 對已刪除的使用者可能給不出名字）。
        // 略過的話那幾筆永遠無法被挑出來，而那是一個看不見的洞。
        const QString label = it.key().isEmpty()
                ? QString("(未標明) (%1)").arg(it.value())
                : QString("%1 (%2)").arg(it.key()).arg(it.value());

        QStandardItem *item = new QStandardItem(label);
        item->setData(it.key(), kAuthorNameRole);   // 比對用的是原值，不是顯示文字
        item->setCheckable(true);
        item->setCheckState(Qt::Unchecked);
        item->setEditable(false);
        m_authorModel->appendRow(item);
    }
    m_rebuildingAuthors = false;
}

void AIAnalysisGitLabMR::applyFilters()
{
    // attachWidgets() 之前不會有元件。
    if (!m_widgets.skipContainsEdit)
        return;

    m_mrProxy->setSkipRules(
                parseSkipKeywords(m_widgets.skipStartsWithEdit->text()),
                parseSkipKeywords(m_widgets.skipEndsWithEdit->text()),
                parseSkipKeywords(m_widgets.skipContainsEdit->text()));
    m_mrProxy->setAuthors(checkedAuthors());

    // 過濾會把列藏起來。保留選取的話，使用者可能在看不見那一筆的情況下按下
    // AI Analysis，而整條流程會對著一筆他看不到的 Merge Request 跑完、回報成功。
    //
    // 選取一空，「指定了 MR」就不成立，AI Analysis 自動停用 —— 不需要另外偵測
    // 「選取的那一筆被藏起來了」。
    m_widgets.mrView->clearSelection();

    updateFilterStatus();
    updateButtonStates();
}

void AIAnalysisGitLabMR::updateFilterStatus()
{
    if (!m_widgets.filterStatusLabel)
        return;

    if (m_mrState != MrLoaded) {
        m_widgets.filterStatusLabel->clear();
        return;
    }

    const int total = m_mrModel->rowCount();

    // 兩個過濾器分別篩掉幾筆：先作者、再標題，兩者不重複計，因此
    // total = 顯示 + author + skip 必然成立。
    //
    // 不在 filterAcceptsRow() 裡累加計數器 —— 那一支由 Qt 依需要呼叫，次數與
    // 順序都不保證，累加出來的數字會看起來合理但其實不對。改成拿同一份判定
    // 規則走一遍來源模型。
    int authorRejected = 0;
    int skipRejected = 0;
    for (int row = 0; row < total; ++row) {
        const QString author =
                m_mrModel->index(row, ColumnAuthor).data().toString();
        if (!m_mrProxy->authorAccepts(author)) {
            ++authorRejected;
            continue;
        }
        const QString title =
                m_mrModel->index(row, ColumnTitle).data().toString();
        if (!m_mrProxy->titleAccepts(title))
            ++skipRejected;
    }

    QString text = QString("共 %1 筆，顯示 %2（Author %3、Skip %4）")
            .arg(total)
            .arg(total - authorRejected - skipRejected)
            .arg(authorRejected)
            .arg(skipRejected);

    if (m_truncated) {
        text += QString(" · 已達上限，名單可能不完整");
    }

    m_widgets.filterStatusLabel->setText(text);
}

// ---------------------------------------------------------------------------
// 開啟外部頁面
// ---------------------------------------------------------------------------

void AIAnalysisGitLabMR::onMrDoubleClicked(const QModelIndex &index)
{
    // 只有標題欄會開啟頁面，而標題欄也是唯一帶著連結外觀的那一欄。
    if (!index.isValid() || m_mrState != MrLoaded || index.column() != ColumnTitle)
        return;

    // index 是 proxy 的索引，data() 會穿過 proxy 取到來源的角色值。
    const QString url = index.data(kWebUrlRole).toString();
    if (url.isEmpty()) {
        QTWarn(QString("[%1] 該筆 Merge Request 的回傳資料沒有網址，不開啟")
               .arg(functionName()));
        return;
    }

    QDesktopServices::openUrl(QUrl(url));
}

void AIAnalysisGitLabMR::onMrEntered(const QModelIndex &index)
{
    const bool overLink = index.isValid() && m_mrState == MrLoaded
            && index.column() == ColumnTitle;
    m_widgets.mrView->viewport()->setCursor(
                overLink ? Qt::PointingHandCursor : Qt::ArrowCursor);
}

void AIAnalysisGitLabMR::onMrViewportEntered()
{
    // 指標在 viewport 內但不在任何一列上（例如表格底下的空白）。
    m_widgets.mrView->viewport()->setCursor(Qt::ArrowCursor);
}

void AIAnalysisGitLabMR::onRepoDoubleClicked(const QModelIndex &index)
{
    if (!index.isValid())
        return;

    const QString repo = m_repoModel->data(index).toString();
    if (repo.isEmpty())
        return;

    QString server =
            config().value(QString("Gitlab_Server_URL")).toString().trimmed();

    // 組不出網址就不要開一個壞掉的網址 —— 瀏覽器只會說「找不到伺服器」，而那句
    // 話指不出真正要修的地方是執行檔旁那份設定檔。
    if (server.isEmpty()) {
        m_shell->showUI_ErrorMessageBox(
                    QString("未設定 GitLab 伺服器位址，無法開啟專案頁面。\n\n"
                            "請在設定檔的 Service.Gitlab_Server_URL 填入位址。"));
        return;
    }

    while (server.endsWith(QChar('/')))
        server.chop(1);

    QDesktopServices::openUrl(QUrl(QString("%1/%2").arg(server, repo)));
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
                applyFilters();
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
                applyFilters();
                return;
            }

            setMrTableState(MrLoaded, QString());

            // 連結外觀的字型取自 view，不是預設建構的 QFont —— 後者的字族與
            // 大小可能與表格其餘欄位不同，那一欄會連字體都變了。
            QFont linkFont = m_widgets.mrView->font();
            linkFont.setUnderline(true);
            const QColor linkColor(QString::fromLatin1(kLinkColor));

            for (int i = 0; i < items.size(); ++i) {
                const QJsonObject mr = items.at(i).toObject();

                const QString iid     = QString::number(
                            static_cast<qint64>(mr.value(QString("iid")).toDouble()));
                const QString title   = mr.value(QString("title")).toString();
                const QString author  = mr.value(QString("author")).toString();
                const QString created = mr.value(QString("created_at")).toString();
                const QString state   = mr.value(QString("state")).toString();
                const QString webUrl  = mr.value(QString("web_url")).toString();

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
                titleItem->setData(webUrl, kWebUrlRole);

                // 標題欄是唯一可點的那一欄，所以也是唯一帶著連結外觀的。外觀把
                // 範圍講清楚之後，「為什麼雙擊作者欄沒反應」就不需要被解釋。
                titleItem->setData(linkColor, Qt::ForegroundRole);
                titleItem->setData(linkFont, Qt::FontRole);

                // 外觀像連結卻要**連按兩下**，是使用者無從猜到的落差，所以在
                // tooltip 裡講出來。單擊必須留給選取 —— 那是按下 AI Analysis 的
                // 前提，單擊即開會讓「只想選一筆」變成不可能。
                titleItem->setToolTip(
                            QString("%1\n（連按兩下開啟 GitLab 頁面）").arg(title));
                row[ColumnTitle] = titleItem;

                QStandardItem *authorItem = new QStandardItem(author);
                authorItem->setData(author, kSortRole);
                // 欄寬容得下常見的名字，但不可能容得下全部。截斷的那幾筆靠這個提示
                // 文字才看得到全名 —— 否則「這一欄放不下」就等於「這個資訊看不到」。
                authorItem->setToolTip(author);
                row[ColumnAuthor] = authorItem;

                // 顯示絕對日期，排序依完整的時間戳 —— 「3 天前」這種相對
                // 文字若拿去字串比較，10 天前會排在 3 天前之前。
                QStandardItem *createdItem = new QStandardItem(created.left(10));
                createdItem->setData(created, kSortRole);
                createdItem->setToolTip(created);
                row[ColumnCreated] = createdItem;

                // 對齊只在這裡設一次，規則寫成一個條件式而不是逐欄分開設 ——
                // 逐欄設的話，之後加一欄就會漏掉，而漏掉的症狀是那一欄靠左、
                // 其餘置中，看起來像是沒對齊，不像是少寫了一行。新增的欄位
                // 因此自動取得置中，那是四個短欄位的共同需求。
                //
                // 標題欄例外，靠左。它是唯一的長文字欄：置中的話每一列的起點
                // 隨標題長短而異，一整排讀下來是跳的；而這一欄正是使用者用來
                // 掃視、挑出想分析的那一筆的。過長時從右側截斷，靠左才讓每一列
                // 都從同一個位置開始。
                //
                // 表頭不必設：QHeaderView 的水平表頭預設就是置中。
                for (int c = 0; c < row.size(); ++c) {
                    row.at(c)->setEditable(false);
                    row.at(c)->setTextAlignment(
                                c == ColumnTitle
                                ? (Qt::AlignLeft | Qt::AlignVCenter)
                                : Qt::AlignCenter);
                }

                m_mrModel->appendRow(row);
            }

            // 腳本在取回筆數達到上限時會這樣標示 —— 「剛好 100 筆」與
            // 「其實有 300 筆」在畫面上完全一樣，不說使用者無從得知。
            //
            // 改以狀態行持續顯示，不再跳一次性的訊息框：達到上限意味著某些作者
            // 根本不會出現在候選清單中，而使用者正是在按掉那個框**之後**才開始
            // 在候選裡找人 —— 最需要那個提示的時刻，它剛好不在。
            m_truncated = result.data.value(QString("truncated")).toBool();

            // 候選作者自**來源模型**推導，所以必須在填完列之後。
            rebuildAuthorCandidates();
            applyFilters();
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

    // 三個等待相關的設定。沒設定時留空字串，腳本據此採用自己的預設 —— Qt 不複製一份
    // 預設值，否則同一個數字會有兩個來源，而它們可以不一致；而且命令列與 CI 那條路徑
    // 根本不經過 Qt。
    //
    // 三個一起決定最壞情況的等待時間，所以要把等待封頂就得三個一起調（見 README）。
    context.aiTimeout  = configNumber(mode, QString("Timeout_Seconds"));
    context.aiRetries  = configNumber(mode, QString("Retry_Count"));
    context.aiReask    = configNumber(mode, QString("Reask_Count"));

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
        context.workDir  = dir;
    } else {
        // 沒勾除錯也要有地方放中間產物 —— 第 5 步的輸入是檔案路徑，不是內容。
        // 用暫存目錄，流程結束時連同 context 一起被刪，使用者的磁碟上不留東西。
        QSharedPointer<QTemporaryDir> temp(new QTemporaryDir);
        if (!temp->isValid()) {
            m_shell->showUI_ErrorMessageBox(
                        QString("無法建立暫存目錄：\n%1")
                        .arg(temp->errorString()));
            return;
        }

        // 預設會在解構時一併移除目錄；寫明只是讓這件事在讀 code 時看得見。
        temp->setAutoRemove(true);

        context.tempDir = temp;
        context.workDir = temp->path();
        QTDebug(QString("[%1] 暫存工作目錄：%2")
                .arg(functionName(), context.workDir));
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

    // 每一步都落檔。工作目錄一定有值（勾除錯就是使用者指定的目錄，否則是
    // 暫存目錄），因此不再有「這一步沒有輸出檔」的情況 —— 第 5 步要靠這些
    // 檔案才合併得出報告。
    const QDir workDir(context.workDir);
    params.insert(QString("out_path"),
                  workDir.absoluteFilePath(
                      QString::fromLatin1(kStepArtifactName[index])));

    switch (index) {
    case 0:
        step.label      = QString("步驟 1/5：取得 Merge Request 描述");
        step.scriptPath = QString(kDescriptionScript);
        step.action     = QString("mr_description");
        break;

    case 1:
        step.label      = QString("步驟 2/5：取得相關資訊");
        step.scriptPath = QString(kMrInfoScript);
        step.action     = QString("mr_info");
        // 這一步自己連 GitLab 取 MR —— 抽 JIRA key 的規則讀的是標題，而步驟 1
        // 的產物只有描述本文，手動輸入編號時畫面上也沒有標題。
        //
        // 模式與手動輸入的值一併送出，由腳本決定採用哪一個；在這裡挑的話，CI
        // 那一側就得再實作一次同樣的三個分支。
        params.insert(QString("jira_mode"),       context.jiraMode);
        params.insert(QString("jira_key_manual"), context.jiraKeyManual);
        break;

    case 2:
        step.label      = QString("步驟 3/5：AI 分析");
        step.scriptPath = QString(kSummaryScript);
        step.action     = QString("ai_summary");
        params.insert(QString("description"),
                      done.at(0).data.value(QString("description")).toString());
        // 上一步解出來的 key。有效性由該 device 的鉤子判定，不在這裡也不在上一步。
        params.insert(QString("jira_key"),
                      done.at(1).data.value(QString("jira_key")).toString());
        // 上一步解出來的種類。它決定該 device 的哪一份 summary 鉤子被載入，但
        // 「誰被載入」仍由腳本端決定 —— Qt 只是原樣轉送，不認得任何種類。
        //
        // 步驟 5 不需要這一行：種類會被步驟 3 寫進分析結果，而步驟 5 本來就要讀
        // 那份檔案。轉送兩次就有兩個來源，而它們可以不一致。
        params.insert(QString("mr_type"),
                      done.at(1).data.value(QString("mr_type")).toString());
        // 模式唯讀轉送，讓鉤子能分辨 key 是抽出來的還是使用者手填的。
        params.insert(QString("jira_mode"), context.jiraMode);
        // AI 的四項走 params（不注入環境變數），因此不會出現在命令列上。
        params.insert(QString("ai_mode_name"), context.aiModeName);
        params.insert(QString("ai_api_url"),   context.aiApiUrl);
        params.insert(QString("ai_api_key"),   context.aiApiKey);
        params.insert(QString("ai_model"),     context.aiModel);
        params.insert(QString("ai_timeout"),   context.aiTimeout);
        params.insert(QString("ai_retries"),   context.aiRetries);
        params.insert(QString("ai_reask"),     context.aiReask);
        break;

    case 3:
        step.label      = QString("步驟 4/5：取得程式碼審閱報告");
        step.scriptPath = QString(kCodeReviewScript);
        step.action     = QString("fetch_code_review");
        // 這一步永遠執行，Qt 端不跳過任何步驟 —— 見 design.md 決策十三。
        //
        // 「要不要真的去抓」由 key 與它的狀態決定，**不另設布林開關** —— 那樣會出現
        // 「開關為真但沒有 key」這種自相矛盾的狀態。
        //
        // key 來自步驟 2，狀態來自步驟 3：有效性是該 device 的政策、由它的鉤子在
        // 步驟 3 判定，所以那個結論住在分析結構裡。這一步只是原樣轉送，Qt 不重判 ——
        // 重判就會有第二份規則，而兩份必然漂移。
        params.insert(QString("jira_key"),
                      done.at(1).data.value(QString("jira_key")).toString());
        params.insert(QString("jira_state"),
                      done.at(2).data.value(QString("analysis")).toObject()
                              .value(QString("jira_state")).toString());
        break;

    case 4:
        step.label      = QString("步驟 5/5：合併為 markdown");
        step.scriptPath = QString(kMergeToMdScript);
        step.action     = QString("merge_to_md");
        // 這一步收的是**檔案路徑**，不是內容。路徑給了就必須存在，所以只有
        // 真的寫出來的那幾份才送過去 —— 例如未要求程式碼審閱時第 4 步不落檔，
        // 那一段就整段略過。
        insertArtifactPath(params, QString("ori_md_file_path"),
                           workDir, kStepArtifactName[0]);
        insertArtifactPath(params, QString("mr_summary_json_file_path"),
                           workDir, kStepArtifactName[2]);
        insertArtifactPath(params, QString("code_review_json_file_path"),
                           workDir, kStepArtifactName[3]);
        // 報告末尾的出處資訊要印出使用者選的 AI 模式。這一步本身不做 AI 分析，
        // 所以它只是被轉送過來、原樣印出，與 repo / mr_iid 同一類。
        params.insert(QString("ai_mode"), context.aiModeName);
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
