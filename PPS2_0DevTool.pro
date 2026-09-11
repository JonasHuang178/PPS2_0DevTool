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
    ProcessingDialog.cpp \
    SingleBuilding.cpp

HEADERS += \
    pps2_0devtool.h \
    json.h \
    debug.h \
    common.h \
    result_code.h \
    version.h \
    PythonRunner.h \
    ProcessingDialog.h \
    SingleBuilding.h

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
#
# main.cpp 以 QCoreApplication::applicationDirPath() 找設定檔，PythonRunner 以
# 同一個基準解析 scripts/ 底下的相對腳本路徑 —— 兩者都必須在執行檔「旁邊」。
# Qt Creator 預設是 shadow build，那個目錄不是專案目錄，所以這段複製不是可有
# 可無的便利措施，少了它程式會在啟動時就因為找不到設定檔而結束。

# DESTDIR 明確寫出來，底下的複製規則才有可靠的目的地可用。這裡指定的位置與
# qmake 原本的預設輸出相同，執行檔不會換地方：Windows 因 debug_and_release 而
# 多一層 debug/ 或 release/，其餘平台就是建置目錄本身。
win32 {
    CONFIG(debug, debug|release) {
        DESTDIR = $$OUT_PWD/debug
    } else {
        DESTDIR = $$OUT_PWD/release
    }
} else {
    DESTDIR = $$OUT_PWD
}

# 複製掛在 PRE_TARGETDEPS，不是 QMAKE_POST_LINK。POST_LINK 只在執行檔真的重新
# 連結時才跑，而「只改了 scripts/ 底下的 .py」不會觸發重新連結 —— 那正是最需要
# 重新複製的時候，卻會變成唯一不複製的時候，症狀是改了腳本卻毫無反應。這個目標
# 沒有對應的實體檔案，make 因此每次建置都會執行它。
#
# 代價是每次建置都會連帶重新連結一次執行檔（PRE_TARGETDEPS 永遠比目標新）。
# 這是刻意換來的：另一種寫法是讓相依性列出 scripts/ 底下的實際檔案，那樣就不必
# 每次重連，但相依清單在 qmake 執行時就固定了 —— 之後「新增」一支腳本不會出現
# 在清單裡，要重跑 qmake 才會被複製。用幾秒的連結時間換掉一個不會報錯、只會讓
# 新腳本安靜地不生效的坑，划算。
deploy_runtime.target = deploy_runtime_files

win32 {
    # cmd 的 copy 不接受結尾的反斜線（"dst\" 會讓引號失效），所以目的地寫成完整
    # 檔名而不是目錄。xcopy 的 /e 連空目錄一併帶上（gitlab_utils 這類只放說明的
    # 分組日後若真的變空也不會漏），/i 把目的地當成目錄而不是檔案，/y 覆蓋時不
    # 詢問，/q 不逐檔列印。
    deploy_runtime.commands = \
        if not exist $$shell_quote($$shell_path($$DESTDIR)) mkdir $$shell_quote($$shell_path($$DESTDIR)) $$escape_expand(\\n\\t) \
        copy /y $$shell_quote($$shell_path($$PWD/PPS2_0DevTool.json)) $$shell_quote($$shell_path($$DESTDIR/PPS2_0DevTool.json)) $$escape_expand(\\n\\t) \
        xcopy /e /i /y /q $$shell_quote($$shell_path($$PWD/scripts)) $$shell_quote($$shell_path($$DESTDIR/scripts))
} else {
    # cp -R 的老問題：目的地已存在時複製的是目錄本身，會變成 dst/scripts/scripts。
    # 來源結尾加上 /. 複製的是內容而不是目錄，重跑才會是覆蓋而不是往下疊一層。
    deploy_runtime.commands = \
        mkdir -p $$shell_quote($$DESTDIR/scripts) $$escape_expand(\\n\\t) \
        cp -f $$shell_quote($$PWD/PPS2_0DevTool.json) $$shell_quote($$DESTDIR/PPS2_0DevTool.json) $$escape_expand(\\n\\t) \
        cp -f -R $$shell_quote($$PWD/scripts/.) $$shell_quote($$DESTDIR/scripts/)
}

QMAKE_EXTRA_TARGETS += deploy_runtime
PRE_TARGETDEPS      += deploy_runtime_files

# 注意：複製是單向的，只會覆蓋與新增，不會刪除。在 scripts/ 底下改名或刪檔之後，
# 執行檔旁邊會留著舊的那一份。那不影響執行（Qt 端是以固定路徑指定腳本），但要
# 確認「舊檔真的沒被用到」時，把執行檔旁的 scripts/ 整個刪掉再建一次最乾脆。
