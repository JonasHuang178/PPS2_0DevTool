# device 擴充腳本的範本

複製整個目錄、改成你的 device 名稱，再把不需要的擴充腳本刪掉（刪掉的那幾支會回退到
`default`）：

```
cp -r device/_template device/<你的名稱>
```

寫法見
[`docs/ai-analysis-gitlab-mr/device-authoring.md`](../../../../docs/ai-analysis-gitlab-mr/device-authoring.md)；
種類目錄的範本在 [`_type_template/`](_type_template/)。

**通用層改了之後這份範本必須立刻跟上。** 既有 device 要不要跟是它負責人的判斷，但範本的
讀者是還不存在的 device —— 沒有人能替它判斷。範本落後一代，從那天起每一個新 device 都從
舊骨架長出來，而且不會有任何徵兆。

## 版本記錄

`TEMPLATE_VERSION`（`__init__.py`）—— 這一份記的是**範本自己**改過幾次，與任何 device
的版號無關。版號規則見
[`docs/contributing.md`](../../../../docs/contributing.md) 的「版號」一節。

| 版號 | 日期 | 說明 |
|---|---|---|
| `v2.0.0` | 2026-11-03 | 首次發版 |
