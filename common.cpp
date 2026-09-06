#include "common.h"

QString formatElapsedTime(qint64 milliseconds)
{
    if (milliseconds < 0)
        milliseconds = 0;

    const qint64 totalSeconds = milliseconds / 1000;
    const qint64 hours   = totalSeconds / 3600;
    const qint64 minutes = (totalSeconds % 3600) / 60;
    const qint64 seconds = totalSeconds % 60;

    return QString("%1h %2m %3s")
            .arg(hours,   2, 10, QChar('0'))
            .arg(minutes, 2, 10, QChar('0'))
            .arg(seconds, 2, 10, QChar('0'));
}
