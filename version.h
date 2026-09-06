#ifndef VERSION_H
#define VERSION_H

// 工具身分與檔名常數。
// 這裡刻意使用巨集而非常數物件：BUILD_DATE 需要字面字串串接。

#define TOOL_NAME        "PPS 2.0 DevTool"
#define TOOL_VERSION     "v2.0.0"

#define CONFIG_FILE_NAME "PPS2_0DevTool.json"
#define CONFIG_ROOT_KEY  "PPS2_0DevTool"

#define SCRIPTS_DIR_NAME "scripts"

#define BUILD_DATE       __DATE__ " " __TIME__

#endif // VERSION_H
