#include "ProcessingDialog.h"

#include <QCloseEvent>
#include <QEvent>
#include <QFontMetrics>
#include <QKeyEvent>
#include <QPushButton>

namespace {

// 腳本回報 stage 前的初始文字。切換步驟時也用它把上一步的殘留文字蓋掉。
const char *const kInitialStageText = "Processing...";

// 對話框的固定尺寸。
//
// 寬度取 460 是為了讓常見的中文階段文字一行放得下；高度只需容納一行標籤、一條
// 跑馬燈與取消鈕，130 留了餘裕。兩個值都只在這個檔案出現，要調整改這裡即可。
const int kDialogWidth  = 460;
const int kDialogHeight = 130;

// 標籤可用寬度 = 對話框寬度扣掉左右內距。QProgressDialog 的內距沒有公開的取得
// 方式，這是估的：估寬了文字會提早被截斷，估窄了會貼到邊。
const int kLabelPadding = 60;

} // namespace

ProcessingDialog::ProcessingDialog(const QString &stepLabel, QWidget *parent)
    : QProgressDialog(parent)
    , m_cancelling(false)
{
    setWindowTitle(stepLabel.isEmpty() ? QString("Processing") : stepLabel);
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
                   | Qt::CustomizeWindowHint
                   | Qt::MSWindowsFixedSizeDialogHint);

    // 固定尺寸：使用者不能以滑鼠改變大小。
    //
    // 兩件事一起做才完整 ——
    //   setFixedSize()                 鎖住尺寸，順便擋掉「標籤文字一變、視窗就
    //                                  跟著縮放」那種執行過程中的跳動
    //   MSWindowsFixedSizeDialogHint   Windows 上換成固定尺寸對話框的細邊框，
    //                                  視窗邊緣不再是可拖曳的縮放區
    //
    // 順序有關係：setWindowFlags() 會重建原生視窗，尺寸要在它之後才鎖得住。
    setFixedSize(kDialogWidth, kDialogHeight);

    applyLabelText(QString(kInitialStageText));

    connect(this, SIGNAL(canceled()), this, SLOT(onCanceled()));
}

void ProcessingDialog::setStep(const QString &stepLabel)
{
    if (m_cancelling)
        return;   // 取消中不再被流程的步驟切換覆蓋

    setWindowTitle(stepLabel.isEmpty() ? QString("Processing") : stepLabel);
    applyLabelText(QString(kInitialStageText));
}

void ProcessingDialog::setStage(const QString &stage)
{
    if (m_cancelling)
        return;   // 取消中不再被腳本的進度覆蓋

    if (!stage.isEmpty())
        applyLabelText(stage);
}

void ProcessingDialog::onCanceled()
{
    if (m_cancelling)
        return;

    m_cancelling = true;

    // QProgressDialog::cancel() 會把對話框藏起來，但行程還要幾秒才會真的
    // 結束。這段期間主視窗必須維持鎖定，所以把它再顯示回來。
    applyLabelText(QString("取消中…"));
    setCancelButtonText(QString("Cancel"));
    if (QPushButton *button = findChild<QPushButton *>())
        button->setEnabled(false);

    show();

    emit cancelRequested();
}

void ProcessingDialog::applyLabelText(const QString &text)
{
    // 尺寸固定之後，視窗不會再為了長文字變寬，所以放不下的部分要自己處理。
    // 與 MR 表格的標題欄同一種作法：截斷成「…」，完整內容放進 tooltip。交給
    // QLabel 硬裁的話，斷點取決於像素寬度，中文可能剛好斷在半個字上。
    const int available = kDialogWidth - kLabelPadding;
    const QString shown = fontMetrics().elidedText(text, Qt::ElideRight, available);

    setLabelText(shown);
    setToolTip(shown == text ? QString() : text);
}

bool ProcessingDialog::event(QEvent *event)
{
    // Escape 不算取消，而且必須在這裡攔。
    //
    // QProgressDialog 在 ShortcutOverride 階段就處理掉 Escape，之後直接把
    // 對話框藏起來並發出 canceled() —— keyPressEvent() 從頭到尾不會被呼叫。
    // 只在 keyPressEvent() 裡擋的話，守衛看起來存在，實際上完全沒作用。
    //
    // 兩個事件型別都要吞：ShortcutOverride 決定這個按鍵走不走捷徑路徑，
    // KeyPress 則是它之後（在別的 Qt 版本或平台上）可能改走的一般路徑。
    if (event->type() == QEvent::ShortcutOverride
            || event->type() == QEvent::KeyPress) {
        if (static_cast<QKeyEvent *>(event)->key() == Qt::Key_Escape) {
            event->accept();
            return true;
        }
    }
    return QProgressDialog::event(event);
}

void ProcessingDialog::keyPressEvent(QKeyEvent *event)
{
    // Escape 在 event() 就被吞掉了，正常情況下走不到這裡。守衛留著是因為
    // 這條路徑在不同 Qt 版本／平台上不保證一致，而多留一道的成本是零。
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
