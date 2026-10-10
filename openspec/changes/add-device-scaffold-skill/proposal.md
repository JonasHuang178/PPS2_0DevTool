# Proposal

## Why

新增一個 device 的成本不在寫邏輯，而在**知道有哪些鉤子、各自收什麼、必須回什麼**。既有需求
「device 實作的範本」的理由已經把那一半寫明了：

> 這些名稱沒有別的地方會提示。要使用時得翻文件或讀載入器的原始碼，而那是一個每次都要付、
> 且容易讓人直接放棄的成本。

範本解決了「有哪些」。沒解決的是另一半 —— **「我填完了，它真的被載到了嗎」**。

目前要回答那一句，唯一的途徑是按下 `AI Analysis` 跑完整條流程：要 GitLab 憑證、要 AI 端點、
要等上幾分鐘、要花一次 AI 的錢。而最容易犯的那個錯誤，代價還不只這些 —— 文件已經警告過它：

> ⚠️ **標題格式與 default 不同的話，這兩支通常要一起寫。** 只寫 `mr_type.py` 的話，
> `jira_key.py` 會沿用 default 的規則（標題第一個方括號），於是安靜地抽到錯的東西。

那個錯誤**不會讓任何一步失敗**。它的症狀是報告末尾印出 `JIRA: Alpha (invalid)` ——
要跑完、要讀到報告末尾、而且要知道那一行本來該長什麼樣，才看得出來。一個只想改報告版面的人
很可能根本不會注意到自己順手複製的 `mr_type.py` 已經把 JIRA 抽歪了。

同一類的失敗還有第二個，而它連報告都不會提醒你。入口腳本把步驟 5 的 `render()` 回傳交給
`contract.plain()`，而 `plain()` 會**靜默** `str()` 非字串 —— 實測 `plain({'overview': 'x'})`
回的是 `"{'overview': 'x'}"`。所以一支回傳 dict 的 `render()` 會讓那段字面印進報告，而**五個
步驟全部回報成功**。目前沒有任何機制抓得到它。

這件事不需要連線也能回答：device 的載入器是純粹的檔案系統解析加 import，`extract()` 吃的是
一個 dict。缺的不是能力，是**有人把它接起來**。

## What Changes

- **新增一個 Claude Code skill 協助使用者開發自己的 device**：問清楚標題格式與要覆寫哪幾支
  鉤子，從 `_template/` 複製出**只有那幾支**的目錄，指出每一支的輸入規格在哪，然後實跑驗證。
- **實作由使用者自己寫，skill 不碰。** 不產生分析邏輯、不挑重用策略、不建議實作該長什麼樣。
  契約只有兩端：**輸入**照 `_template/` 的 docstring 給，**輸出格式**必須遵守 —— 中間自由發揮。
  要自己打 HTTP、要換一套 prompt 架構、要完全不問 AI 都可以。
- **新增 `tools/verify_device.py`**：一支離線驗證 device 的腳本。不連 GitLab、不呼叫 AI、不需要
  任何憑證。它回答五個問題：
  - 這個 device 被發現了嗎（`known_devices()`）
  - `VERSION` 讀得到嗎，第一碼對得上通用層的 `SCRIPT_VERSION` 嗎
  - 五支鉤子**各自實際解析到哪一份**（印出回退路徑，證明「我以為我覆寫了」是真的）
  - 拿**真實的 MR 標題**跑 `jira_key.extract()` 與 `mr_type.extract()`，兩支並排列出結果
  - **回傳的形狀合不合契約** —— 沿用入口腳本自己那一支 `validate_analysis()` 驗步驟 3 的結構，
    明確檢查步驟 5 回的是不是字串（補上 `plain()` 吃掉的那個缺口），並把步驟 4 的
    `review_result` 不在 `REVIEW_RESULTS` 內這件事**提前**回報（入口已經會記警告，但那要
    跑完整條流程才看得到）
- 第四項正是上面第一個陷阱的解法：兩支並排，抽歪了一眼就看得出來，而且是在寫完的那一刻、
  不是在讀報告末尾的時候。第五項是第二個陷阱的解法。
- 步驟 3 的驗證**不必連線也不必花錢**，依據是一條既有的需求：未設定 AI 端點時那一步 SHALL 產出
  替代內容而非失敗，且該內容 SHALL 於首行言明未經過 AI。驗證腳本用空的端點呼叫使用者的
  `analyze()`，順便驗出他有沒有遵守那條「首行要言明」—— 一支自由寫出來的 `analyze()` 極容易
  漏掉它，而漏掉的後果就是那條需求的理由所警告的那種報告。
- skill **只產生使用者真的要覆寫的那幾支鉤子**。逐鉤子回退是既有設計，整組複製會讓那份複本
  跟著 `default` 漂移。
- `tools/verify_device.py` 是**獨立可用的**，不是 skill 的私有零件：人可以直接跑，CI 也可以
  （`ci/pps-ai-analysis.gitlab-ci.yml` 已經在那裡）。

不做：

- **不改任何執行期行為。** 載入器、解析順序、五個步驟、報告版面、`default` 的五支鉤子全部不動。
  新 device 照既有規則被發現與載入，與手寫出來的沒有任何差別。
- **不替使用者寫鉤子的實作。** 鷹架是 `_template/` 原樣複製，實作區留給他。skill 擔保的是形狀，
  不是品質 —— 一支通過全部檢查的 `analyze()` 仍然可以問錯的問題，而驗證的輸出會照實說自己驗了
  什麼、沒驗什麼，不印「通過」。
- **不改 `_template/`，也不把它的內容抄進 skill。** 範本的註解是這件事唯一的事實來源；skill
  只寫流程，內容一律指回 `_template/`、`AUTHORING.md` 與
  `docs/ai-analysis-gitlab-mr/device-authoring.md`。抄一份就是製造第二份會
  漂移的事實來源，而漂移的那一份會比沒有更糟。
- **不碰 Qt 端。** 指定 device 的途徑（設定檔 `PPS_Device` -> 環境變數 `PPS_DEVICE`）已經存在。
- **不自動產生種類目錄的完整實作。** 種類是各條產品線自己的字彙，skill 問出有哪些、建出目錄與
  要覆寫的鉤子即可。

## Capabilities

### New Capabilities

（無）

### Modified Capabilities

（無 —— 本變更設 `skip_specs: true`）

本變更不改任何可觀察的產品行為，所以沒有 spec 該改。這與這個 repo 既有的界線一致：**spec 描述
產品的行為，開發工具不在其中**。`tools/make_app_icon.py`、`.claude/` 底下的既有 skill、
`AUTHORING.md` 都沒有任何對應的需求，而應用程式圖示那條需求（`app-shell`）規定的是「外殼 SHALL
提供單一組圖示」，不是那支產生器。

唯一一條規定開發者設施的需求是「device 實作的範本」，而它在 spec 裡**有運行期的理由**：範本住在
`scripts/ai_analysis_gitlab_mr/device/` 底下，與被部署的腳本放在一起，所以載入器的發現規則必須
把它排除 —— 那條需求的最後一句正是「範本與其中的種類範本 MUST NOT 被視為可用的 device 或種類」。
skill 與 `tools/` 底下的驗證腳本沒有這層耦合：執行期沒有任何東西讀它們。

## Impact

**新增**

- `.claude/skills/<名稱>/SKILL.md` —— 訪談、鷹架、驗證的流程
- `tools/verify_device.py` —— 離線驗證，可獨立執行

**唯讀依賴**（不修改，但 skill 與驗證腳本的行為繫於它們）

- `scripts/ai_analysis_gitlab_mr/device/__init__.py` —— `known_devices()`、`load_hook()`、
  `normalize_type()`、`device_version()` 是驗證腳本的全部依據
- `scripts/ai_analysis_gitlab_mr/device/_template/` —— 鷹架的來源
- `scripts/ai_analysis_gitlab_mr/device/default/` —— `summary.py` 的零件來源，與回退的終點
- `scripts/ai_analysis_gitlab_mr/__init__.py` —— `SCRIPT_VERSION`，版號第一碼的比對對象

**不改**

- 任何 `scripts/` 底下的執行期程式碼、任何 `.cpp`/`.h`/`.ui`、任何 `openspec/specs/`
