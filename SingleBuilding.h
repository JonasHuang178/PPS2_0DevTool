#ifndef SINGLEBUILDING_H
#define SINGLEBUILDING_H

#include "PythonRunner.h"

#include <QList>
#include <QObject>
#include <QSortFilterProxyModel>
#include <QString>
#include <QStringList>

QT_BEGIN_NAMESPACE
class QLineEdit;
class QListView;
class QPushButton;
class QStandardItemModel;
QT_END_NAMESPACE

class PPS2_0DevTool;

// 功能要用到的元件。由外殼在 UI_SetupSignal() 填好後交過來。
//
// 不直接傳整包 Ui::PPS2_0DevTool：功能之間互相獨立是本工具的基本原則，
// 讓一個功能看得到所有其他功能的元件是不必要的耦合。
struct SingleBuildingWidgets
{
    QLineEdit   *filterEdit;
    QPushButton *filterClearButton;
    QListView   *sourceView;
    QListView   *targetView;
    QPushButton *addButton;
    QPushButton *removeButton;
    QPushButton *targetClearButton;
    QPushButton *recoveryButton;
    QPushButton *modifyButton;

    SingleBuildingWidgets()
        : filterEdit(Q_NULLPTR)
        , filterClearButton(Q_NULLPTR)
        , sourceView(Q_NULLPTR)
        , targetView(Q_NULLPTR)
        , addButton(Q_NULLPTR)
        , removeButton(Q_NULLPTR)
        , targetClearButton(Q_NULLPTR)
        , recoveryButton(Q_NULLPTR)
        , modifyButton(Q_NULLPTR) {}
};

// 兩個清單共用的排序／過濾代理。
//
// 用代理層而不是逐項 setHidden()：逐項隱藏時「被藏起來但仍處於選取」的項目
// 會在送出時混進去，而那正是規格要求避免的行為。
//
// 排序與過濾的大小寫規則刻意不同，兩者是不同的關切：
//   過濾  區分大小寫 —— 使用者主動輸入，要不要區分由他自己掌握
//   排序  不分大小寫 —— 被動看到的結果；ASCII 序會把所有大寫排在所有小寫
//                       之前，使用者只會覺得清單根本沒排序
//
// 排序為自然排序：名稱中的數字段落依數值比較，a2.cpp 排在 a10.cpp 之前。
//
// 自己寫比較函式而不是用 QCollator::setNumericMode()：Qt 在沒有 ICU 的建置上
// 會走後備實作，那條路徑**靜默忽略** numericMode —— numericMode() 照樣回報
// true，compare() 卻是逐字元比較。規格要求的行為不能取決於目標平台的 Qt
// 是怎麼編的。
class NaturalSortFilterProxyModel : public QSortFilterProxyModel
{
    Q_OBJECT

public:
    explicit NaturalSortFilterProxyModel(QObject *parent = Q_NULLPTR);

    void setSourceModel(QAbstractItemModel *sourceModel) Q_DECL_OVERRIDE;

protected:
    bool lessThan(const QModelIndex &left,
                  const QModelIndex &right) const Q_DECL_OVERRIDE;
};

// Single Building 功能。
//
// Qt 端只負責讓使用者選擇：掃描目錄、讀寫暫存設定檔全部在 Python。
class SingleBuilding : public QObject
{
    Q_OBJECT

public:
    // 功能名稱。同時是 tab 標題與設定檔 Function 底下的鍵名。
    static QString functionName();

    explicit SingleBuilding(PPS2_0DevTool *shell, QObject *parent = Q_NULLPTR);

    // 接上元件並建立訊號連接。外殼在 UI_SetupSignal() 呼叫一次。
    void attachWidgets(const SingleBuildingWidgets &widgets);

    // 進入功能（切換到本分頁，或啟動時本分頁即為當前分頁）。
    void enterFunction();

public slots:
    void onSourcePathChanged(const QString &sourceFilePath,
                             const QString &functionName);

private slots:
    void onFilterTextChanged(const QString &text);
    void onFilterClearClicked();
    void onAddClicked();
    void onRemoveClicked();
    void onSourceDoubleClicked(const QModelIndex &index);
    void onTargetDoubleClicked(const QModelIndex &index);
    void onTargetClearClicked();
    void onModifySettingClicked();
    void onRecoverySettingClicked();
    void updateButtonStates();

private:
    // 清單中的一筆。顯示 name，保存 path ——
    // 完整路徑前綴完全相同又很長，顯示出來只會撐爆清單寬度。
    struct FileEntry
    {
        QString name;
        QString path;
    };

    // --- 腳本 ---
    void runListSource(bool thenListTarget);
    void runListTarget();
    void runRecoverySetting(bool thenListSource);
    void reportPendingErrors();
    static QList<FileEntry> parseFiles(const QJsonObject &data);

    // --- 清單操作 ---
    void setSourceEntries(const QList<FileEntry> &entries);
    void setTargetEntries(const QList<FileEntry> &entries);
    void addEntriesToTarget(const QList<FileEntry> &entries);
    QList<FileEntry> selectedEntries(QListView *view) const;
    QStringList targetPaths() const;
    bool targetContainsName(const QString &name) const;

    PPS2_0DevTool         *m_shell;
    SingleBuildingWidgets  m_widgets;

    QStandardItemModel          *m_sourceModel;
    QStandardItemModel          *m_targetModel;
    NaturalSortFilterProxyModel *m_sourceProxy;
    NaturalSortFilterProxyModel *m_targetProxy;

    // 一次進入功能會接續跑兩支腳本。兩者的失敗原因先累積起來，最後合併成
    // 一個訊息框 —— 連跳兩個訊息框只是讓使用者多按一次確定。
    QString m_pendingSourceError;
    QString m_pendingTargetError;
};

#endif // SINGLEBUILDING_H
