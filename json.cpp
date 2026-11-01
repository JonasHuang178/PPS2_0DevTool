#include "json.h"

#include "debug.h"
#include "version.h"

#include <QFile>
#include <QJsonDocument>
#include <QJsonParseError>
#include <QJsonValue>

namespace {

// 設定檔中的布林一律以字串 "true" / "false" 表示。
bool toBool(const QJsonValue &value)
{
    return value.toString().compare(QString("true"), Qt::CaseInsensitive) == 0;
}

} // namespace

Config::Config()
    : m_debugMode(false)
{
}

Config::LoadStatus Config::load(const QString &filePath, QString *errorMessage)
{
    QFile file(filePath);
    if (!file.exists()) {
        if (errorMessage)
            *errorMessage = QString("找不到設定檔：\n%1").arg(filePath);
        return LoadFileNotFound;
    }

    if (!file.open(QIODevice::ReadOnly)) {
        if (errorMessage)
            *errorMessage = QString("無法讀取設定檔：\n%1\n\n%2")
                    .arg(filePath, file.errorString());
        return LoadFileNotFound;
    }

    const QByteArray raw = file.readAll();
    file.close();

    QJsonParseError parseError;
    const QJsonDocument doc = QJsonDocument::fromJson(raw, &parseError);
    if (parseError.error != QJsonParseError::NoError || !doc.isObject()) {
        if (errorMessage) {
            *errorMessage = QString("設定檔不是合法的 JSON：\n%1\n\n%2（位置 %3）")
                    .arg(filePath,
                         parseError.errorString(),
                         QString::number(parseError.offset));
        }
        return LoadParseError;
    }

    const QJsonObject root = doc.object().value(CONFIG_ROOT_KEY).toObject();
    if (root.isEmpty()) {
        if (errorMessage)
            *errorMessage = QString("設定檔缺少根鍵 \"%1\"：\n%2")
                    .arg(CONFIG_ROOT_KEY, filePath);
        return LoadRootMissing;
    }

    // 只讀這四個工具層級欄位。其餘一律不碰。
    m_debugMode     = toBool(root.value("Debug_Mode"));
    m_userGuideLink = root.value("User_Guide_Link").toString();
    m_service       = root.value("Service").toObject();    // 整包保留，不解析
    m_function      = root.value("Function").toObject();   // 整包保留，不解析

    // Service 缺席是合法的：不使用任何共用服務的部署不需要寫這一段。
    // toObject() 對不存在的鍵回傳空物件，所以這裡不需要額外處理。

    return LoadOk;
}

QJsonObject Config::getFunctionConfig(const QString &functionName) const
{
    // 功能不存在時回傳空物件，而不是只回傳 Service —— 「這個功能沒有設定」
    // 與「這個功能只有共用設定」是兩件事，後者會讓漏寫的功能區塊看起來像是
    // 寫了一半。
    if (!m_function.contains(functionName))
        return QJsonObject();

    const QJsonObject section = m_function.value(functionName).toObject();

    // Service 先鋪底，功能區塊後蓋上去 —— 同名鍵因此以功能區塊為準。
    QJsonObject merged = m_service;
    for (QJsonObject::const_iterator it = section.constBegin();
         it != section.constEnd(); ++it) {
        merged.insert(it.key(), it.value());
    }
    return merged;
}

bool Config::isFunctionVisible(const QString &functionName) const
{
    // 這裡讀的是 Function 底下的原始區塊，不是 getFunctionConfig() 的合併
    // 結果 —— 見標頭檔的說明。
    if (!m_function.contains(functionName)) {
        QTWarn(QString("Function/%1 未在設定檔中定義，預設隱藏").arg(functionName));
        return false;
    }

    const QJsonObject section = m_function.value(functionName).toObject();
    if (!section.contains("Visible")) {
        QTWarn(QString("Function/%1 未設定 Visible，預設隱藏").arg(functionName));
        return false;
    }

    return section.value("Visible").toString() == QString("true");
}
