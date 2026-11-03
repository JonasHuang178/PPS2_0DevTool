#!/usr/bin/env python3
"""default device —— 未指定 PPS_DEVICE 時使用的通用實作。

也是所有 device 的後備：某個 device 沒有提供的擴充腳本會落到這裡（逐支回退），因種類
而異的那兩支也是 —— 種類只在自己的 device 之內解析，找不到就落到這裡。所以這五支必須
都存在，而且要能獨力跑完整條流程。
"""

# 這個 device 的版本，會印在報告末尾的出處資訊裡。**必填。**
#
# 版號 vA.B.C：前兩碼指出這個 device 照的是哪一代通用層，第三碼是它自己動過的次數。
# 完整規則見 docs/contributing.md 的「版號」一節 —— 那裡是唯一的來源，這裡只放值。
#
# default 也適用這條規則，沒有例外。
DEVICE_VERSION = "v2.0.0"

# 這裡**刻意不宣告** STRICT_TYPE 與 CODE_REVIEW_SOURCE_HEADING。
#
# 兩者都是選填，未宣告就落到預設值 —— 而 default 的職責正是「沒有特別需求時用這一份」，
# 所以它的行為應該就是預設行為。在這裡重複宣告一次預設值，日後改預設值時就有兩個地方
# 要改，而漏掉其中一個不會有任何徵兆。
#
# 可宣告的項目及其預設值見 `device/_template/__init__.py` 的註解。
