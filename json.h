#ifndef JSON_H
#define JSON_H

#include <QJsonObject>
#include <QString>

// 工具層級設定的讀取。
//
// 硬性規則：新增一個功能不得修改這個檔案。
// 外殼只認得三個工具層級欄位（Debug_Mode / User_Guide_Link / Function），
// Function 物件整包保留、不做任何解析，功能自己透過 getFunctionConfig()
// 取自己的區塊。舊版把每個功能的每個欄位寫死在這裡解析，結果程式讀的鍵
// 與設定檔實際的鍵長期不一致而沒人發現。

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

    // 取得指定功能的完整設定區塊。
    // 名稱不存在時回傳空物件，不視為錯誤 —— 缺漏的必填設定由腳本層的
    // 必填檢查負責回報，那裡能精確指出缺的是哪一個鍵。
    QJsonObject getFunctionConfig(const QString &functionName) const;

    // 該功能的 tab 是否應該顯示。
    // 只有 "Visible" 為字串 "true" 才顯示；區塊或鍵不存在時回傳 false
    // 並記一筆警告。
    bool isFunctionVisible(const QString &functionName) const;

private:
    bool        m_debugMode;
    QString     m_userGuideLink;
    QJsonObject m_function;   // 整包保留，不解析
};

#endif // JSON_H
