#ifndef JSON_H
#define JSON_H

#include <QJsonObject>
#include <QString>

// 工具層級設定的讀取。
//
// 硬性規則：新增一個功能不得修改這個檔案，新增一個共用服務的鍵也不得修改
// 這個檔案。只有在新增一整個工具層級區塊時才需要改它。
//
// 外殼只認得四個工具層級欄位（Debug_Mode / User_Guide_Link / Service /
// Function）。Service 與 Function 兩個物件都整包保留、不做任何解析 ——
// 功能透過 getFunctionConfig() 取得「Service 併上自己區塊」的結果，同名鍵
// 以自己的區塊為準。舊版把每個功能的每個欄位寫死在這裡解析，結果程式讀的
// 鍵與設定檔實際的鍵長期不一致而沒人發現。
//
// Service 存放跨功能共用的服務端點與憑證（GitLab、JIRA、AI…）。抄在每個
// 功能區塊裡的話，使用者換憑證時漏改一處，那個功能就會在執行期以舊憑證
// 失敗，而失敗的症狀（例如 401）會把人引向「憑證過期」這個錯誤方向。

class Config
{
public:
    enum LoadStatus {
        LoadOk,
        LoadFileNotFound,
        LoadParseError,
        LoadRootMissing
    };

    Config();

    // 載入設定檔。失敗時 errorMessage 會填入可直接顯示給使用者的說明。
    LoadStatus load(const QString &filePath, QString *errorMessage);

    bool    debugMode() const     { return m_debugMode; }
    QString userGuideLink() const { return m_userGuideLink; }

    // 取得指定功能的設定：Service 併上該功能在 Function 底下的區塊，
    // 同名鍵以功能區塊為準（讓個別功能能指向與共用設定不同的伺服器）。
    //
    // 合併只發生在這裡，外殼其餘部分（含請求信封的組裝）因此不需要知道
    // Service 的存在 —— startFlowStep() 照常呼叫這個函式即可。
    //
    // 名稱不存在時回傳空物件（不是只回傳 Service），不視為錯誤 —— 缺漏的
    // 必填設定由腳本層的必填檢查負責回報，那裡能精確指出缺的是哪一個鍵。
    QJsonObject getFunctionConfig(const QString &functionName) const;

    // 該功能的 tab 是否應該顯示。
    // 只有 "Visible" 為字串 "true" 才顯示；區塊或鍵不存在時回傳 false
    // 並記一筆警告。
    //
    // 這裡刻意讀 Function 底下的**原始**區塊，不是 getFunctionConfig() 的
    // 合併結果：否則 Service 裡一個誤放的 Visible 會讓所有「未設定 Visible」
    // 的功能從「預設隱藏並記警告」變成全部顯示，而預設隱藏正是為了讓漏設定
    // 的功能不要靜默出現在畫面上。
    bool isFunctionVisible(const QString &functionName) const;

private:
    bool        m_debugMode;
    QString     m_userGuideLink;
    QJsonObject m_service;    // 整包保留，不解析
    QJsonObject m_function;   // 整包保留，不解析
};

#endif // JSON_H
