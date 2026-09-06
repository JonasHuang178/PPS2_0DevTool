#include "ProcessingDialog.h"

#include <QCloseEvent>
#include <QKeyEvent>
#include <QPushButton>

ProcessingDialog::ProcessingDialog(const QString &functionName, QWidget *parent)
    : QProgressDialog(parent)
    , m_cancelling(false)
{
    setWindowTitle(functionName.isEmpty() ? QString("Processing") : functionName);
    setLabelText(QString("Processing..."));   // 腳本回報 stage 前的初始文字
    setCancelButtonText(QString("Cancel"));

    // 跑馬燈：range 為 (0, 0) 才會是不確定進度。
    // 絕對不要呼叫 setValue() —— 一呼叫就會切回百分比模式。
    setRange(0, 0);

    // 立即顯示、立即鎖定主視窗。
    setMinimumDuration(0);
    setWindowModality(Qt::ApplicationModal);

    setAutoClose(false);
    setAutoReset(false);

    // 移除標題列的關閉鈕：讓它消失，比留著但沒有反應好 ——
    // 後者會讓使用者以為程式當掉了。
    setWindowFlags((windowFlags() & ~Qt::WindowCloseButtonHint)
                   | Qt::CustomizeWindowHint);

    connect(this, SIGNAL(canceled()), this, SLOT(onCanceled()));
}

void ProcessingDialog::setStage(const QString &stage)
{
    if (m_cancelling)
        return;   // 取消中不再被腳本的進度覆蓋

    if (!stage.isEmpty())
        setLabelText(stage);
}

void ProcessingDialog::onCanceled()
{
    if (m_cancelling)
        return;

    m_cancelling = true;

    // QProgressDialog::cancel() 會把對話框藏起來，但行程還要幾秒才會真的
    // 結束。這段期間主視窗必須維持鎖定，所以把它再顯示回來。
    setLabelText(QString("取消中…"));
    setCancelButtonText(QString("Cancel"));
    if (QPushButton *button = findChild<QPushButton *>())
        button->setEnabled(false);

    show();

    emit cancelRequested();
}

void ProcessingDialog::keyPressEvent(QKeyEvent *event)
{
    // Escape 不算取消。
    if (event->key() == Qt::Key_Escape) {
        event->ignore();
        return;
    }
    QProgressDialog::keyPressEvent(event);
}

void ProcessingDialog::closeEvent(QCloseEvent *event)
{
    // 視窗關閉不算取消。
    event->ignore();
}
