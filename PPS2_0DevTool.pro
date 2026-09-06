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

# 把設定檔與腳本一併放到執行檔目錄旁，讓相對腳本路徑可以解析。
# （開發期間的便利措施；正式部署由安裝程式負責。）
