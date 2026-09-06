#ifndef RESULT_CODE_H
#define RESULT_CODE_H

// Qt 端的框架層級錯誤碼，分三類：設定、行程、回應。
//
// 各功能需要自己的錯誤碼時，請在自己的標頭定義，不要加進這裡。
// 注意：這與 Python 回傳的 error.code 是兩套獨立的詞彙表，刻意不共用 ——
// 否則每新增一個腳本錯誤都要改 C++。

enum ResultCode {
    RC_OK = 0,

    // --- 設定類 ---
    RC_CONFIG_FILE_NOT_FOUND = 100,  // 設定檔不存在或無法讀取
    RC_CONFIG_PARSE_FAILED   = 101,  // 設定檔不是合法 JSON
    RC_CONFIG_ROOT_MISSING   = 102,  // 缺少根鍵
    RC_CONFIG_KEY_MISSING    = 103,  // 缺少必要的鍵

    // --- 行程類 ---
    RC_PROCESS_BUSY            = 200,  // 已有腳本在執行
    RC_PROCESS_SCRIPT_NOT_FOUND = 201, // 腳本檔案不存在
    RC_PROCESS_FAILED_TO_START = 202,  // 執行指令無法啟動
    RC_PROCESS_CRASHED         = 203,  // 行程異常終止
    RC_PROCESS_CANCELLED       = 204,  // 使用者取消

    // --- 回應類 ---
    RC_RESPONSE_NO_JSON        = 300,  // 標準輸出沒有可解析的 JSON
    RC_RESPONSE_NOT_OBJECT     = 301,  // 標準輸出的 JSON 不是物件
    RC_RESPONSE_RESULT_MISSING = 302   // 缺少 result 欄位
};

#endif // RESULT_CODE_H
