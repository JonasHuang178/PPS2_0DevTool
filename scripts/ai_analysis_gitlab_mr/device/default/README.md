# default device

未指定 `PPS_DEVICE` 時使用的通用實作，同時是**所有 device 的後備** —— 別的 device 沒有
提供的擴充腳本會逐支回退到這裡。所以五支擴充腳本必須都存在，而且要能獨力跑完整條流程。

## 版本記錄

`DEVICE_VERSION`（`__init__.py`）。版號規則見
[`docs/contributing.md`](../../../../docs/contributing.md) 的「版號」一節。

| 版號 | 日期 | 說明 |
|---|---|---|
| `v2.0.0` | 2026-11-03 | 首次發版 |
