#ifndef PROCESSINGDIALOG_H
#define PROCESSINGDIALOG_H

#include <QProgressDialog>

// 執行期間的處理中對話框。
//
// 與預設的 QProgressDialog 有三處刻意的差異：
//
// 1. 取消鈕是唯一的取消途徑 —— Escape 與視窗關閉都被攔掉。
//    誤觸 Escape 會砍掉一次長時間的呼叫，而因為取消時不呼叫 callback，
//    畫面什麼都不會發生，使用者只會覺得「按了沒反應」。
//
// 2. setMinimumDuration(0)。預設是 4 秒 —— 在對話框實際顯示之前沒有
//    互斥遮罩，主視窗仍可操作，直接違反「執行期間主視窗鎖定」。
//
// 3. 按下取消後對話框不關閉，改顯示「取消中…」直到行程真的結束。
//    否則主視窗會在行程還在終止的那幾秒內被解除鎖定。

class ProcessingDialog : public QProgressDialog
{
    Q_OBJECT

public:
    explicit ProcessingDialog(const QString &functionName, QWidget *parent = Q_NULLPTR);

    // 更新腳本回報的階段文字。
    void setStage(const QString &stage);

signals:
    // 使用者按下取消鈕。
    void cancelRequested();

protected:
    void keyPressEvent(QKeyEvent *event) Q_DECL_OVERRIDE;
    void closeEvent(QCloseEvent *event) Q_DECL_OVERRIDE;

private slots:
    void onCanceled();

private:
    bool m_cancelling;
};

#endif // PROCESSINGDIALOG_H
