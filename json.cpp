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

    // 只讀這三個工具層級欄位。其餘一律不碰。
    m_debugMode     = toBool(root.value("Debug_Mode"));
    m_userGuideLink = root.value("User_Guide_Link").toString();
    m_function      = root.value("Function").toObject();   // 整包保留，不解析

    return LoadOk;
}

QJsonObject Config::getFunctionConfig(const QString &functionName) const
{
    return m_function.value(functionName).toObject();
}

bool Config::isFunctionVisible(const QString &functionName) const
{
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
