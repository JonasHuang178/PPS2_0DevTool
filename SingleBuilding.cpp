#include "SingleBuilding.h"

#include "debug.h"
#include "pps2_0devtool.h"

#include <QItemSelectionModel>
#include <QJsonArray>
#include <QJsonObject>
#include <QLineEdit>
#include <QListView>
#include <QMessageBox>
#include <QModelIndex>
#include <QPushButton>
#include <QStandardItem>
#include <QStandardItemModel>

#include <algorithm>

namespace {

// 清單項目上存放絕對路徑的角色。顯示的是檔名，寫進設定檔的是這個。
const int kPathRole = Qt::UserRole + 1;

const char *kListSourceScript     = "scripts/single_building_list_source.py";
const char *kListTargetScript     = "scripts/single_building_list_target.py";
const char *kModifySettingScript  = "scripts/single_building_modify_setting.py";
const char *kRecoverySettingScript = "scripts/single_building_recovery_setting.py";

// 自然排序的比較：數字段落依數值比較，其餘字元不分大小寫。
//
// 回傳 <0 / 0 / >0，語意同 strcmp。
int naturalCompare(const QString &a, const QString &b)
{
    int i = 0;
    int j = 0;

    while (i < a.size() && j < b.size()) {
        const QChar ca = a.at(i);
        const QChar cb = b.at(j);

        if (ca.isDigit() && cb.isDigit()) {
            // 跳過前導零之後先比位數，位數相同再逐位比 —— 直接把整段轉成
            // 整數會在遇到超長編號時溢位。
            int si = i;
            while (si < a.size() && a.at(si) == QLatin1Char('0')) ++si;
            int sj = j;
            while (sj < b.size() && b.at(sj) == QLatin1Char('0')) ++sj;

            int ei = si;
            while (ei < a.size() && a.at(ei).isDigit()) ++ei;
            int ej = sj;
            while (ej < b.size() && b.at(ej).isDigit()) ++ej;

            const int lengthA = ei - si;
            const int lengthB = ej - sj;
            if (lengthA != lengthB)
                return lengthA < lengthB ? -1 : 1;

            for (int k = 0; k < lengthA; ++k) {
                const QChar da = a.at(si + k);
                const QChar db = b.at(sj + k);
                if (da != db)
                    return da < db ? -1 : 1;
            }

            i = ei;
            j = ej;
            continue;
        }

        const QChar fa = ca.toCaseFolded();
        const QChar fb = cb.toCaseFolded();
        if (fa != fb)
            return fa < fb ? -1 : 1;

        ++i;
        ++j;
    }

    if (i < a.size())
        return 1;
    if (j < b.size())
        return -1;

    // 只差在大小寫（或前導零）時給一個穩定的次序，否則同一批資料兩次載入
    // 可能排出不同結果。
    return QString::compare(a, b, Qt::CaseSensitive);
}

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

} // namespace

// ---------------------------------------------------------------------------
// NaturalSortFilterProxyModel
// ---------------------------------------------------------------------------

NaturalSortFilterProxyModel::NaturalSortFilterProxyModel(QObject *parent)
    : QSortFilterProxyModel(parent)
{
    // 過濾與排序的大小寫規則各自獨立，見標頭檔的說明。
    setFilterCaseSensitivity(Qt::CaseSensitive);
    setDynamicSortFilter(true);
}

void NaturalSortFilterProxyModel::setSourceModel(QAbstractItemModel *sourceModel)
{
    QSortFilterProxyModel::setSourceModel(sourceModel);

    // sort() 一定要等來源模型接上之後才呼叫。在建構子裡呼叫時還沒有模型，
    // 那一次是空操作，sortColumn() 會留在 -1 —— 清單於是完全沒有排序，
    // 而且 setDynamicSortFilter(true) 也救不回來（它只重新套用既有的排序欄）。
    sort(0);
}

bool NaturalSortFilterProxyModel::lessThan(const QModelIndex &left,
                                           const QModelIndex &right) const
{
    return naturalCompare(sourceModel()->data(left).toString(),
                          sourceModel()->data(right).toString()) < 0;
}

// ---------------------------------------------------------------------------
// SingleBuilding
// ---------------------------------------------------------------------------

QString SingleBuilding::functionName()
{
    return QString("Single Building");
}

SingleBuilding::SingleBuilding(PPS2_0DevTool *shell, QObject *parent)
    : QObject(parent)
    , m_shell(shell)
    , m_sourceModel(new QStandardItemModel(this))
    , m_targetModel(new QStandardItemModel(this))
    , m_sourceProxy(new NaturalSortFilterProxyModel(this))
    , m_targetProxy(new NaturalSortFilterProxyModel(this))
{
    m_sourceProxy->setSourceModel(m_sourceModel);
    m_targetProxy->setSourceModel(m_targetModel);
}

void SingleBuilding::attachWidgets(const SingleBuildingWidgets &widgets)
{
    m_widgets = widgets;

    m_widgets.sourceView->setModel(m_sourceProxy);
    m_widgets.targetView->setModel(m_targetProxy);

    QListView *views[] = { m_widgets.sourceView, m_widgets.targetView };
    for (int i = 0; i < 2; ++i) {
        views[i]->setSelectionMode(QAbstractItemView::ExtendedSelection);
        views[i]->setEditTriggers(QAbstractItemView::NoEditTriggers);
        views[i]->setUniformItemSizes(true);
    }

    connect(m_widgets.filterEdit, SIGNAL(textChanged(QString)),
            this, SLOT(onFilterTextChanged(QString)));
    connect(m_widgets.filterClearButton, SIGNAL(clicked()),
            this, SLOT(onFilterClearClicked()));
    connect(m_widgets.addButton, SIGNAL(clicked()),
            this, SLOT(onAddClicked()));
    connect(m_widgets.removeButton, SIGNAL(clicked()),
            this, SLOT(onRemoveClicked()));
    connect(m_widgets.targetClearButton, SIGNAL(clicked()),
            this, SLOT(onTargetClearClicked()));
    connect(m_widgets.modifyButton, SIGNAL(clicked()),
            this, SLOT(onModifySettingClicked()));
    connect(m_widgets.recoveryButton, SIGNAL(clicked()),
            this, SLOT(onRecoverySettingClicked()));

    connect(m_widgets.sourceView, SIGNAL(doubleClicked(QModelIndex)),
            this, SLOT(onSourceDoubleClicked(QModelIndex)));
    connect(m_widgets.targetView, SIGNAL(doubleClicked(QModelIndex)),
            this, SLOT(onTargetDoubleClicked(QModelIndex)));

    // selectionModel() 要等 setModel() 之後才存在。
    connect(m_widgets.sourceView->selectionModel(),
            SIGNAL(selectionChanged(QItemSelection,QItemSelection)),
            this, SLOT(updateButtonStates()));
    connect(m_widgets.targetView->selectionModel(),
            SIGNAL(selectionChanged(QItemSelection,QItemSelection)),
            this, SLOT(updateButtonStates()));
    connect(m_targetModel, SIGNAL(rowsInserted(QModelIndex,int,int)),
            this, SLOT(updateButtonStates()));
    connect(m_targetModel, SIGNAL(rowsRemoved(QModelIndex,int,int)),
            this, SLOT(updateButtonStates()));
    connect(m_targetModel, SIGNAL(modelReset()),
            this, SLOT(updateButtonStates()));

    updateButtonStates();
}

// ---------------------------------------------------------------------------
// 進入功能與來源路徑
// ---------------------------------------------------------------------------

void SingleBuilding::enterFunction()
{
    m_pendingSourceError.clear();
    m_pendingTargetError.clear();

    if (m_shell->getUI_sourcePathLineEditText().isEmpty()) {
        // 應用程式啟動時來源路徑尚未由使用者指定。把它當成失敗的話，使用者
        // 每次啟動都會看到一個無從避免的錯誤訊息框。
        QTDebug(QString("[%1] 來源路徑為空，略過取得來源清單")
                .arg(functionName()));
        setSourceEntries(QList<FileEntry>());
        runListTarget();
        return;
    }

    runListSource(true);
}

void SingleBuilding::onSourcePathChanged(const QString &sourceFilePath,
                                         const QString &functionName_)
{
    // 來源路徑是各功能私有的，但 Qt 的訊號會送達所有已連接的 slot。
    // 少了這個比對，使用者為了別的分頁調整路徑就會清掉本功能的設定。
    if (functionName_ != functionName())
        return;

    // 重新開始：設定保存的是絕對路徑，換了來源目錄之後原有的設定不再指向
    // 使用者當下在看的檔案。清空的動作與 Recovery Setting 完全相同，直接
    // 重用同一支腳本 —— 但不經過確認框，那只掛在按鈕上。
    QTDebug(QString("[%1] 來源路徑變更為 %2，清空設定並重新載入")
            .arg(functionName(), sourceFilePath));

    m_pendingSourceError.clear();
    m_pendingTargetError.clear();
    runRecoverySetting(true);
}

// ---------------------------------------------------------------------------
// 腳本
// ---------------------------------------------------------------------------

void SingleBuilding::runListSource(bool thenListTarget)
{
    const bool started = m_shell->runFunctionScript(
        functionName(), QString(kListSourceScript), QString("list_source"),
        QJsonObject(),
        [this, thenListTarget](const PythonRunner::PythonRunnerResult &result) {
            if (result.success) {
                setSourceEntries(parseFiles(result.data));
            } else {
                // 保留失敗前的舊內容會讓使用者誤以為那是當前來源的內容。
                setSourceEntries(QList<FileEntry>());
                m_pendingSourceError = failureReason(result);
            }

            if (thenListTarget)
                runListTarget();
            else
                reportPendingErrors();
        });

    if (!started) {
        // 啟動失敗時外殼已經跳過錯誤訊息框（或是忙碌，那是程式缺陷不是
        // 使用者操作錯誤），這裡再加一個訊息只是讓使用者多按一次確定。
        setSourceEntries(QList<FileEntry>());
        if (thenListTarget)
            runListTarget();
        else
            reportPendingErrors();
    }
}

void SingleBuilding::runListTarget()
{
    const bool started = m_shell->runFunctionScript(
        functionName(), QString(kListTargetScript), QString("list_target"),
        QJsonObject(),
        [this](const PythonRunner::PythonRunnerResult &result) {
            if (result.success) {
                setTargetEntries(parseFiles(result.data));
            } else {
                setTargetEntries(QList<FileEntry>());
                m_pendingTargetError = failureReason(result);
            }
            reportPendingErrors();
        });

    if (!started) {
        setTargetEntries(QList<FileEntry>());
        reportPendingErrors();
    }
}

void SingleBuilding::runRecoverySetting(bool thenListSource)
{
    const bool started = m_shell->runFunctionScript(
        functionName(), QString(kRecoverySettingScript),
        QString("recovery_setting"), QJsonObject(),
        [this, thenListSource](const PythonRunner::PythonRunnerResult &result) {
            if (result.success) {
                // 腳本清空後自己回讀，回傳的內容必為空 —— 不需要再串一支
                // 讀取設定的腳本。
                setTargetEntries(parseFiles(result.data));
            } else {
                setTargetEntries(QList<FileEntry>());
                m_pendingTargetError = failureReason(result);
            }

            if (!thenListSource) {
                reportPendingErrors();
                return;
            }

            if (m_shell->getUI_sourcePathLineEditText().isEmpty()) {
                setSourceEntries(QList<FileEntry>());
                reportPendingErrors();
            } else {
                runListSource(false);
            }
        });

    if (!started) {
        setTargetEntries(QList<FileEntry>());
        reportPendingErrors();
    }
}

void SingleBuilding::reportPendingErrors()
{
    QStringList parts;
    if (!m_pendingSourceError.isEmpty())
        parts << QString("取得來源清單失敗：\n%1").arg(m_pendingSourceError);
    if (!m_pendingTargetError.isEmpty())
        parts << QString("讀取設定失敗：\n%1").arg(m_pendingTargetError);

    m_pendingSourceError.clear();
    m_pendingTargetError.clear();

    if (parts.isEmpty())
        return;

    // 一次進入功能會跑兩支腳本，兩支都失敗時連跳兩個訊息框只是讓使用者
    // 多按一次確定。
    m_shell->showUI_ErrorMessageBox(parts.join(QString("\n\n")));
}

QList<SingleBuilding::FileEntry> SingleBuilding::parseFiles(
        const QJsonObject &data)
{
    QList<FileEntry> entries;

    const QJsonArray files = data.value(QString("files")).toArray();
    for (int i = 0; i < files.size(); ++i) {
        const QJsonObject item = files.at(i).toObject();

        FileEntry entry;
        entry.name = item.value(QString("name")).toString();
        entry.path = item.value(QString("path")).toString();
        if (entry.name.isEmpty())
            continue;

        entries.append(entry);
    }
    return entries;
}

// ---------------------------------------------------------------------------
// 動作按鈕
// ---------------------------------------------------------------------------

void SingleBuilding::onModifySettingClicked()
{
    QJsonArray paths;
    const QStringList list = targetPaths();
    for (int i = 0; i < list.size(); ++i)
        paths.append(list.at(i));

    QJsonObject params;
    params.insert(QString("files"), paths);

    m_shell->runFunctionScript(
        functionName(), QString(kModifySettingScript),
        QString("modify_setting"), params,
        [this](const PythonRunner::PythonRunnerResult &result) {
            if (!result.success) {
                m_shell->showUI_ErrorMessageBox(
                            QString("寫入設定失敗：\n%1")
                            .arg(failureReason(result)));
                return;
            }
            // 不重讀設定檔：畫面上的結果清單已經就是剛剛寫進去的內容，
            // 重讀只是多彈一次處理中對話框。
            m_shell->showUI_InfoMessageBox(result.message);
        });
}

void SingleBuilding::onRecoverySettingClicked()
{
    // 清空之後暫存設定檔的原有內容無法復原，因此先確認。
    const QMessageBox::StandardButton answer = QMessageBox::question(
                Q_NULLPTR, functionName(),
                QString("這會清空已保存的設定，且無法復原。\n\n確定要繼續嗎？"),
                QMessageBox::Yes | QMessageBox::No, QMessageBox::No);
    if (answer != QMessageBox::Yes)
        return;

    m_pendingSourceError.clear();
    m_pendingTargetError.clear();
    runRecoverySetting(false);
}

// ---------------------------------------------------------------------------
// 清單操作
// ---------------------------------------------------------------------------

void SingleBuilding::onFilterTextChanged(const QString &text)
{
    // setFilterFixedString() 而不是 setFilterRegularExpression()：使用者輸入
    // 的 * 與 ? 要當成一般字元參與比對，不是萬用字元。
    m_sourceProxy->setFilterFixedString(text);

    // 過濾會把項目藏起來。保留選取的話，使用者按下加入時會送出畫面上看不到
    // 的項目 —— 清空選取讓所見即所得。
    m_widgets.sourceView->clearSelection();
    updateButtonStates();
}

void SingleBuilding::onFilterClearClicked()
{
    // 只清過濾文字，來源清單的內容不動。
    m_widgets.filterEdit->clear();
}

void SingleBuilding::onAddClicked()
{
    addEntriesToTarget(selectedEntries(m_widgets.sourceView));
}

void SingleBuilding::onSourceDoubleClicked(const QModelIndex &index)
{
    if (!index.isValid())
        return;

    const QModelIndex source = m_sourceProxy->mapToSource(index);
    FileEntry entry;
    entry.name = m_sourceModel->data(source).toString();
    entry.path = m_sourceModel->data(source, kPathRole).toString();

    addEntriesToTarget(QList<FileEntry>() << entry);
}

void SingleBuilding::onRemoveClicked()
{
    const QModelIndexList selected =
            m_widgets.targetView->selectionModel()->selectedIndexes();

    QList<int> rows;
    for (int i = 0; i < selected.size(); ++i)
        rows.append(m_targetProxy->mapToSource(selected.at(i)).row());

    // 由後往前刪，否則前面的列被移除後，後面記下來的列號就全部失效了。
    std::sort(rows.begin(), rows.end());
    for (int i = rows.size() - 1; i >= 0; --i)
        m_targetModel->removeRow(rows.at(i));
}

void SingleBuilding::onTargetDoubleClicked(const QModelIndex &index)
{
    if (!index.isValid())
        return;

    m_targetModel->removeRow(m_targetProxy->mapToSource(index).row());
}

void SingleBuilding::onTargetClearClicked()
{
    // 只清畫面，不碰暫存設定檔 —— 使用者沒按 Modify Setting 就沒有寫入。
    m_targetModel->removeRows(0, m_targetModel->rowCount());
}

void SingleBuilding::updateButtonStates()
{
    if (!m_widgets.addButton)
        return;

    m_widgets.addButton->setEnabled(
                m_widgets.sourceView->selectionModel()->hasSelection());
    m_widgets.removeButton->setEnabled(
                m_widgets.targetView->selectionModel()->hasSelection());
    m_widgets.filterClearButton->setEnabled(
                !m_widgets.filterEdit->text().isEmpty());
    m_widgets.targetClearButton->setEnabled(m_targetModel->rowCount() > 0);
}

// ---------------------------------------------------------------------------
// 模型
// ---------------------------------------------------------------------------

void SingleBuilding::setSourceEntries(const QList<FileEntry> &entries)
{
    m_sourceModel->clear();
    for (int i = 0; i < entries.size(); ++i) {
        QStandardItem *item = new QStandardItem(entries.at(i).name);
        item->setData(entries.at(i).path, kPathRole);
        m_sourceModel->appendRow(item);
    }
    updateButtonStates();
}

void SingleBuilding::setTargetEntries(const QList<FileEntry> &entries)
{
    m_targetModel->clear();
    for (int i = 0; i < entries.size(); ++i) {
        QStandardItem *item = new QStandardItem(entries.at(i).name);
        item->setData(entries.at(i).path, kPathRole);
        m_targetModel->appendRow(item);
    }
    updateButtonStates();
}

void SingleBuilding::addEntriesToTarget(const QList<FileEntry> &entries)
{
    for (int i = 0; i < entries.size(); ++i) {
        // 已存在的靜默略過：多選時為每一筆重複跳一個訊息框只會擋住操作。
        if (targetContainsName(entries.at(i).name))
            continue;

        QStandardItem *item = new QStandardItem(entries.at(i).name);
        item->setData(entries.at(i).path, kPathRole);
        m_targetModel->appendRow(item);
    }
    updateButtonStates();
}

QList<SingleBuilding::FileEntry> SingleBuilding::selectedEntries(
        QListView *view) const
{
    QSortFilterProxyModel *proxy =
            qobject_cast<QSortFilterProxyModel *>(view->model());
    QStandardItemModel *model =
            qobject_cast<QStandardItemModel *>(proxy->sourceModel());

    QList<FileEntry> entries;
    const QModelIndexList selected = view->selectionModel()->selectedIndexes();
    for (int i = 0; i < selected.size(); ++i) {
        const QModelIndex source = proxy->mapToSource(selected.at(i));

        FileEntry entry;
        entry.name = model->data(source).toString();
        entry.path = model->data(source, kPathRole).toString();
        entries.append(entry);
    }
    return entries;
}

QStringList SingleBuilding::targetPaths() const
{
    QStringList paths;
    for (int row = 0; row < m_targetModel->rowCount(); ++row)
        paths.append(m_targetModel->item(row)->data(kPathRole).toString());
    return paths;
}

bool SingleBuilding::targetContainsName(const QString &name) const
{
    for (int row = 0; row < m_targetModel->rowCount(); ++row) {
        if (m_targetModel->item(row)->text() == name)
            return true;
    }
    return false;
}
