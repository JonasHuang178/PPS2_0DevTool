# Design

## Context

動機見 `proposal.md` 的 Why。這裡只記下塑造作法的幾項現狀：

- **載入器是純粹的檔案系統解析加 import。** `device/__init__.py` 的公開 API（`known_devices()`、
  `load_hook()`、`normalize_type()`、`device_version()`、`strict_type()`、
  `code_review_source_heading()`）不碰網路、不需要憑證。鉤子的 `extract()` 吃一個 dict。
  **離線驗證不需要新增任何能力**，只需要有人把既有的 API 接起來。
- **回退是逐鉤子的。** `<device>/<type>/` -> `<device>/` -> `default/`（因種類而異的兩支），
  或 `<device>/` -> `default/`（另兩支）。所以「只放要覆寫的那幾支」是既有設計，不是最佳化。
- **每個步驟是一個行程，每個行程處理一筆 MR。** 步驟 3 的 `mr_iid` 是必填且單數，
  `load_hook("summary", ...)` 在那個行程裡只呼叫一次。所以驗證一支鉤子不需要模擬整條流程 ——
  備好一個 `inputs` dict、呼叫一次、看回傳，就是它在真實執行裡會遇到的全部。
- **輸出側的驗證器已經存在，輸入側沒有。** `contract.validate_analysis()` 驗步驟 3 的結構，
  而且是入口腳本自己用的那一支（它的 docstring 記著當初為什麼要驗在產生它的那一步）。
  步驟 5 的 `render()` 沒有對應的驗證：回傳值直接交給 `contract.plain()`，而 `plain()` 吃得下
  任何型別。這個不對稱決定了 D3 要補的是哪一塊。
- **範本的註解是這件事唯一的事實來源**，而且密度很高：五支鉤子的 docstring 把每個 inputs 鍵、
  回傳契約與常見陷阱都寫了，外加 `AUTHORING.md` 與
  `docs/ai-analysis-gitlab-mr/device-authoring.md` 的 device/type 兩節。

## Goals / Non-Goals

**Goals:**

- 把「建一個自己的 device」從「翻三份文件 + 跑一次完整流程才知道對不對」變成一條有驗證的流程。
- 讓最容易犯、且**不會讓任何一步失敗**的那個錯誤（只寫 `mr_type.py` 而 `jira_key.py` 沿用
  default）在寫完的那一刻就看得見。
- **使用者自由實作，但輸出格式不留模糊空間。** 實作怎麼寫是他的事；回傳的形狀不對時，
  失敗要發生在他寫完的那一刻，而不是一份回報成功的壞報告裡。
- 驗證**獨立於 skill 可用** —— 人可以直接跑，CI 也可以。

**Non-Goals:**

- **不產生鉤子的實作，也不建議實作該長什麼樣。** 鷹架是 `_template/` 原樣複製；分析邏輯、
  prompt、版面都由使用者自由發揮（見 D3）。
- 不做互動式 TUI 或產生器 CLI。鷹架那部分是複製檔案，交給 skill 的流程即可。
- 不驗證 prompt 的品質，也不驗證 AI 回得對不對。那需要連線與花費，而且沒有客觀的通過標準。
- 不驗證 `merge_to_md.py` 的版面好不好看。驗證只證明它**載入得到、呼叫得起來、回傳字串**；
  版面要用既有的離線迴路看（拿一份 `03_summary.json` 形狀的假產物單獨重跑步驟 5）。
- 不替使用者決定種類字彙。種類是各條產品線自己的事。

## Decisions

### D1：驗證腳本放 `tools/verify_device.py`，不放 skill 目錄裡

**選它的理由**是三個使用者不只一個：寫 device 的人（想自己再跑一次，不想每次都開 Claude）、
CI（`ci/pps-ai-analysis.gitlab-ci.yml` 已經在那裡，部署前就能擋掉「忘了把目錄一起放出去」）、
以及 skill 本身。放在 `.claude/skills/<名稱>/scripts/` 底下的話，只有第三個拿得到。

**先例**：`tools/make_app_icon.py` 就是這一類東西 —— 開發期用的腳本，放 `tools/`，沒有任何 spec
需求對應它（`app-shell` 規定的是「外殼 SHALL 提供單一組圖示」，不是那支產生器）。

**代價**：`tools/` 多一支要維護的腳本，而它的行為繫於 `device/__init__.py` 的 API。
緩解見下面的風險一節。

**考慮過**：把驗證寫進 SKILL.md 讓 agent 每次臨場寫 `python -c`。否決 —— 那等於把驗證邏輯
放在一個不會被執行、也不會被 review 的地方，而每次臨場寫出來的檢查都不一樣。

### D2：SKILL.md 只寫流程，內容一律指回 repo 既有檔案

鉤子的介面說明、inputs 每個鍵的意義、陷阱、種類的解析順序 —— 這些**一個字都不抄進 SKILL.md**。
需要時指路：「`extract()` 的契約見 `device/_template/mr_type.py` 的 docstring」。

理由：抄一份就有兩份事實來源，而範本改了 SKILL.md 不會跟著改。漂移之後的那一份比沒有更糟 ——
它看起來權威，而且是 agent 會先讀到的那一份。

這也讓 SKILL.md 短得能整份讀完，而那正是它能被正確執行的前提。

### D3：skill 不碰實作 —— 給輸入、守輸出、中間自由

**鉤子的實作由使用者自己寫。** skill 不產生分析邏輯、不挑重用策略、不預設任何實作形狀。
它守的是兩端：

| 鉤子 | 輸入 | 輸出契約 | 目前誰在驗 |
|---|---|---|---|
| `jira_key.extract(mr)` | `mr` 六個欄位 | 字串；抽不到回空字串，**不要回 `None`** | 沒人 |
| `mr_type.extract(mr)` | 同上 | 字串 | `normalize_type()` 丟 `DeviceError` |
| `summary.analyze(inputs)` | `inputs` 約二十個鍵 | `contract.analysis_body(...)` 的結果 | `validate_analysis()` |
| `parse_code_review.parse(inputs)` | `inputs` 四個鍵 | `contract.code_review_parsed(...)` 的結果 | 入口擋非 dict；`code_review_body()` 收斂不認得的 `review_result` |
| `merge_to_md.render(inputs)` | `inputs` 七個鍵 | **一段 markdown 字串** | 沒人 ← 見下面 |

**`parse_code_review` 是唯一已經被兩段擋住的一支**，而它的來歷說明了為什麼：它比這份計畫
晚出現（`e5c84eb`），而加它的那一輪順手把守衛一起寫了。它守住的兩件事剛好是這一節在講的
兩端 —— 回傳不是 dict 時入口指名是哪一個 device，`review_result` 不在 `REVIEW_RESULTS`
裡時收斂成「判不出來」並記一筆警告（理由寫在 `code_review_body()`：一個拼錯的結論印出去
比不印更糟）。驗證腳本對它要做的不是補驗證，是**把那筆警告提前**到使用者寫完的那一刻，
而不是留在跑完整條流程的 log 裡。

輸入規格**不由 skill 重述**，就是 `_template/` 五支檔案的 docstring（見 D2）。鷹架原樣複製，
使用者填實作區。中間怎麼寫是他的事 —— 要自己打 HTTP、要換一套 prompt 架構、要完全不問 AI，
都可以。

**想重用 `default/` 寫好的零件，明著 import 就行**（`from ai_analysis_gitlab_mr.device.default
import summary as base`，取 `base.parse_reply` 之類）。載入器的 docstring 已經說明這一點。
skill 把它當成**提示**告知，不作為規定 —— 那是使用者的自由。

於是「守住輸出」成為 skill 唯一的強制面，而這件事有三個事實支撐它可以做得徹底：

**其一，步驟 3 的驗證器已經存在，沿用而不重寫。** 入口腳本的路徑是
`wrap_analysis(body)` 蓋上 `schema_version`，再 `validate_analysis(payload, source=where)`，
不過就丟 `AnalysisFormatError` 並把整份寫進除錯目錄的 `bad_analysis.json`。驗證腳本走**同一條
路徑**、`source` 帶上 device 與檔名。它檢查 `schema_version`、`analysis` 是物件、`jira_state`
是 `JIRA_STATES` 之一、`mr_type` 是字串、`coverage` 給了就是物件。`coverage` 與 `mr_type` 由
入口蓋章，鉤子不必填。

**其二，`analyze()` 可以完全離線驗證**，而且依據是一條既有的需求（「分析流程的對外契約與 AI
端點缺失時的行為」）：

> 未設定 AI 端點時，AI 分析那一步 SHALL 產出替代內容而非失敗，且該內容 SHALL 於首行言明
> 未經過 AI。

所以驗證腳本用**空的 `ai_api_url`** 呼叫使用者的 `analyze()`：不連線、不花錢，而且順便驗出
使用者有沒有遵守那條「首行要言明未經過 AI」—— **一支自由寫出來的 `analyze()` 極容易漏掉它**，
而漏掉的後果正是那條需求的理由所警告的：「一份看起來正常、實際上沒問過 AI 的報告，比一個錯誤
訊息糟得多」。`default` 的做法見 `_stub_analysis()`。

**其三，`render()` 有一個目前沒有任何機制抓得到的漏洞 —— 這是這道防線最硬的理由。**
入口腳本把 `render()` 的回傳交給 `contract.plain()`，而 `plain()` 會**靜默** `str()` 非字串。
已實測：

```
plain({'overview': 'x'})  ->  "{'overview': 'x'}"
plain(['a', 'b'])         ->  "['a', 'b']"
```

一支回傳 dict 的 `render()` 會讓報告裡印出那段字面，而**五個步驟全部回報成功**。沒有任何一步
失敗，沒有任何訊息，而症狀要有人去讀那份報告才看得見。驗證腳本因此明確檢查
`isinstance(section, str)`，補上這個缺口。

`render()` 的執行期例外，入口是包成 `DEVICE_HOOK_RUNTIME_ERROR` 並在訊息裡**指名種類**（改壞的
往往是某個種類專屬的那一份）—— 驗證比照，否則使用者得自己猜是哪一層的那一支。

### D4：只產生使用者真的要覆寫的那幾支鉤子

訪談問出要覆寫哪幾支，只複製那幾支加上必要的 `__init__.py`。

但有一條**例外要主動提**：使用者說只要 `mr_type.py` 時，如果他的標題格式與 default 不同
（JIRA key 不在第一個方括號），skill 要指出 `jira_key.py` 多半也得寫，並說明症狀。這是
proposal 裡那個陷阱，而訪談是唯一能在它發生前攔住它的時機。

skill **不替他決定** —— 格式真的相同時只寫一支是對的。它只確保那個決定是知情的。

### D5：種類目錄不產生 `__init__.py`

種類目錄是 namespace package，載入器的 docstring 明寫「不需要 `__init__.py`。放一個目錄進去，
字面上就是新增一個種類」。產生一個等於加入一個不需要的檔案，而下一個讀的人會以為它是必要的。

空的種類目錄是合法且有用的（搭配 `STRICT_TYPE` 宣告「這些種類我認得但不需要客製」），所以
skill 允許只建目錄不放鉤子。

### D6：版號第一碼比對是警告，不是失敗

`VERSION` 的第一碼該與通用層的 `SCRIPT_VERSION` 一致。驗證從 `ai_analysis_gitlab_mr.SCRIPT_VERSION`
**讀出來比對**，不寫死數字。

但不一致**只警告**，因為範本明寫「不一致不會讓執行失敗……忘了就是忘了，由開發者自負」。
驗證不該比它所驗證的契約更嚴格。

實際情況也站在這一邊：現在 `SCRIPT_VERSION = "2.11"` 而 `default` 的 `VERSION = "2.6"` ——
**連 default 都已經不一致了**。把它做成失敗會讓驗證第一次跑就對著 default 報錯，而使用者會
學到的唯一一件事是「這個檢查要忽略」。

### D7：驗證的五項檢查，與各自擋住的失敗

| 檢查 | 用到的 API | 擋住的失敗 |
|---|---|---|
| device 被發現 | `known_devices()` / `resolve_name()` | 目錄名不是合法識別字（`ssd-gen4`）、放錯層、底線開頭 |
| 宣告讀得到 | `device_version()`、`strict_type()`、`code_review_source_heading()` | 漏了必填的 `VERSION`；`STRICT_TYPE = "false"`（字串在 Python 裡是真值）|
| 五支鉤子各自解析到哪 | `HOOK_NAMES` 逐支 `load_hook()`，取回傳的第二個值 | 「我以為我覆寫了」—— 檔名打錯、放錯目錄，於是安靜落回 `default` |
| 真實標題跑抽取 | 兩支 `extract()` + `normalize_type()` | **D4 那個陷阱**：兩支並排列出，抽歪了一眼看得出來；種類正規化後對不對得上目錄 |
| **輸出格式** | `wrap_analysis()` + `validate_analysis()`；`code_review_body()`；`isinstance(section, str)` | **D3 那三件**：`analyze()` 回傳的結構不合契約、沒在首行言明未經過 AI、`render()` 回傳非字串而被 `plain()` 靜默轉成字面。外加 `parse()` 的 `review_result` 不在 `REVIEW_RESULTS` 內 —— 那一筆入口已經會記警告，這裡只是讓它早幾天被看到 |

後三項是這支腳本存在的理由 —— 它們擋的都是**不會讓任何一步失敗**的失敗。前兩項是便利，
第三到第五項是目前只能靠讀報告（或根本讀不出來）才發現的那幾類。

**鉤子名單一律讀 `HOOK_NAMES`（或 `UNTYPED_HOOKS` + `TYPED_HOOKS`），不在驗證腳本裡抄一份。**
這份計畫自己就是證據：它寫的時候只有四支，第五支 `parse_code_review` 在那之後才加進來。抄一份
的症狀不是報錯，是驗證腳本安靜地少驗一支 —— 而那正是這整支腳本要消滅的那一類失敗。

輸入的標題樣本由使用者提供（訪談時就會問到）。code review 的樣本報告同理，覆寫那一支時才需要。
腳本接受命令列參數或一個小檔案，讓同一組樣本可以重複跑、也可以進 CI。

## Risks / Trade-offs

- **驗證腳本與載入器的 API 耦合** → 只用 `device/__init__.py` 的 `__all__` 列出的公開名稱，
  不碰底線開頭的內部函式（`_import`、`_hook_file`）。那份 `__all__` 就是這個模組宣告的對外契約。

- **自由實作意味著 skill 擔保不了正確性，只擔保形狀。** 一支通過五項檢查的 `analyze()` 仍然
  可以問錯的問題、切錯的 diff → 驗證的輸出照實說自己驗了什麼、沒驗什麼（見 Non-Goals），
  不印「通過」。把形狀的保證講成品質的保證，比不驗更糟。

- **使用者若明著 import `default/` 的零件，就綁上了那些名稱**（`parse_reply`、`ROLE_PROMPT`
  之類）。default 改名就壞 → 壞法是 import 時的 `AttributeError`／`ImportError`，指名檔案與
  屬性，而載入器本來就把這類失敗轉成說得出位置的 `DeviceError`。這是可接受的壞法，也是使用者
  自己選的耦合；驗證的第三項檢查會在那時失敗。

- **驗證只能證明「對這幾個樣本是對的」。** 使用者給三個標題，就只驗了三個 → 腳本照實把樣本
  與結果並排印出，不印「通過」。訪談時要求樣本涵蓋至少一個反例（沒有種類、或格式不照約定的
  標題），因為那是回退路徑唯一會被走到的時候。

- **skill 產出的程式碼仍然是人要維護的。** 鷹架省掉的是查文件與接驗證的成本，不是理解成本 →
  產出保留範本的關鍵註解（尤其回傳契約與那個陷阱的警告），不產生「乾淨但沒有來由」的程式碼。

- **`tools/` 多一支腳本**，而 `tools/` 目前沒有任何測試 → 驗證腳本的正確性由它對 `default`
  的輸出來擔保：對一個已知的 device 跑出已知的結果。這也順便讓它在 CI 裡有一個不需要新增
  fixture 的煙霧測試。

## Open Questions

- skill 的名稱（`new-device` 或別的）與觸發描述的字句，待實作時定。這不影響作法與任務拆解。
