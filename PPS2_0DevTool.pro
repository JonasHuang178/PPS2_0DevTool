QT       += core gui widgets

TARGET   = PPS2_0DevTool
TEMPLATE = app

CONFIG  += c++11

# Qt5 + qmake。Windows 端使用 Qt Creator + MinGW；
# macOS 僅用於確認編得過（開發輔助，非支援平台），因此所有 Windows 專屬
# API 一律以 #ifdef Q_OS_WIN 隔離。

SOURCES += \
    main.cpp \
    pps2_0devtool.cpp \
    json.cpp \
    debug.cpp \
    common.cpp \
    PythonRunner.cpp \
    ProcessingDialog.cpp

HEADERS += \
    pps2_0devtool.h \
    json.h \
    debug.h \
    common.h \
    result_code.h \
    version.h \
    PythonRunner.h \
    ProcessingDialog.h

FORMS += \
    pps2_0devtool.ui

RESOURCES += \
    resources.qrc

# Windows 執行檔本身的圖示（檔案總管、捷徑、開始功能表、釘選的工作列按鈕）。
# 這是連結期由 windres 寫進 PE 資源區段的，執行中的程式無法改變自己在磁碟上
# 的圖示資源 —— 換圖一律要重新建置。
# qmake 在非 Windows 平台忽略 RC_ICONS，因此不需要條件式包裝，macOS 端照樣
# 編得過。
RC_ICONS = resources/icons/PPS2_0DevTool.ico

# 一旦設定 RC_ICONS，qmake 產生的資源檔會一併帶入 VERSIONINFO 區塊。不設定
# 的話版本會是 qmake 的預設值，與 version.h 的 v2.0.0 對不上 —— 使用者在檔案
# 內容頁看到的版本會和 About 對話框顯示的不同。
# 註：VERSION 只在函式庫專案影響輸出檔名；本專案 TEMPLATE = app，TARGET 不受
# 影響。
VERSION                  = 2.0.0
QMAKE_TARGET_PRODUCT     = PPS 2.0 DevTool
QMAKE_TARGET_DESCRIPTION = PPS 2.0 DevTool

# 把設定檔與腳本一併放到執行檔目錄旁，讓相對腳本路徑可以解析。
# （開發期間的便利措施；正式部署由安裝程式負責。）
