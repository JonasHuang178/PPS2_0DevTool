#ifndef COMMON_H
#define COMMON_H

#include <QString>
#include <QtGlobal>

// 把毫秒格式化為 "01h 23m 45s"。
QString formatElapsedTime(qint64 milliseconds);

#endif // COMMON_H
