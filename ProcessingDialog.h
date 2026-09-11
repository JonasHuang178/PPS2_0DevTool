#ifndef PROCESSINGDIALOG_H
#define PROCESSINGDIALOG_H

#include <QProgressDialog>

// 執行期間的處理中對話框。
//
// 對話框由整條流程共用：流程啟動時建立、流程結束時銷毀，步驟之間只換文字，
// 不關閉也不重建。每步重建會讓視窗真的消失再出現（Windows 上是 ShowWindow
// 層級的閃爍與焦點重奪），並在步驟交界處留下沒有互斥遮罩的空窗。
//
// 文字分兩層，各自有自己的來源：
//   標題列    步驟名稱，由功能提供（只有一步的流程就是功能名稱）
//   標籤      階段文字，由腳本經 stderr 回報
// 用標題列承載第二層而不是把兩行塞進標籤 —— QProgressDialog 會隨標籤內容
// 重算大小，多行字串在步驟切換時會讓視窗尺寸跳動，換掉一種閃爍又換來另一種。
//
// 與預設的 QProgressDialog 有三處刻意的差異：
//
// 1. 取消鈕是唯一的取消途徑 —— Escape 與視窗關閉都被攔掉。
//    誤觸 Escape 會砍掉整條流程，而因為取消時不呼叫 callback，畫面什麼都
//    不會發生，使用者只會覺得「按了沒反應」。
//
//    Escape 必須在 event() 攔，不能只靠 keyPressEvent()。QProgressDialog
//    在 QEvent::ShortcutOverride 階段就把 Escape 消化掉了，keyPressEvent()
//    根本不會被呼叫 —— 原本寫在那裡的守衛看起來對，實際上從未生效，對話框
//    照樣被隱藏並發出 canceled()。以原生 QProgressDialog 子類別寫同樣的守衛
//    可重現，所以這是 QProgressDialog 的行為，不是這裡寫錯。
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
    explicit ProcessingDialog(const QString &stepLabel, QWidget *parent = Q_NULLPTR);

    // 切換到新的步驟：步驟名稱寫進標題列，階段文字重設回初始文字。
    // 不重設的話，新步驟在回報第一則 stage 之前，畫面上留著的會是上一步
    // 最後回報的階段文字 —— 使用者看到的是一段已經結束的工作。
    void setStep(const QString &stepLabel);

    // 更新腳本回報的階段文字。
    void setStage(const QString &stage);

signals:
    // 使用者按下取消鈕。
    void cancelRequested();

protected:
    // Escape 的主要攔截點。keyPressEvent() 對 Escape 是攔不到的（見上）。
    bool event(QEvent *event) Q_DECL_OVERRIDE;

    void keyPressEvent(QKeyEvent *event) Q_DECL_OVERRIDE;
    void closeEvent(QCloseEvent *event) Q_DECL_OVERRIDE;

private slots:
    void onCanceled();

private:
    bool m_cancelling;
};

#endif // PROCESSINGDIALOG_H
