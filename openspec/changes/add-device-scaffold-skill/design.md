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
  `load_hook("summary", ...)` 在那個行程裡只呼叫一次。這一點決定了下面 D3 的結論。
- **範本的註解是這件事唯一的事實來源**，而且密度很高：四支鉤子的 docstring 把每個 inputs 鍵、
  回傳契約與常見陷阱都寫了，外加 `AUTHORING.md` 與 `README.md` 的 device/type 兩節。

## Goals / Non-Goals

**Goals:**

- 把「建一個自己的 device」從「翻三份文件 + 跑一次完整流程才知道對不對」變成一條有驗證的流程。
- 讓最容易犯、且**不會讓任何一步失敗**的那個錯誤（只寫 `mr_type.py` 而 `jira_key.py` 沿用
  default）在寫完的那一刻就看得見。
- 驗證**獨立於 skill 可用** —— 人可以直接跑，CI 也可以。

**Non-Goals:**

- 不做互動式 TUI 或產生器 CLI。鷹架那部分是複製檔案加改字串，交給 skill 的流程即可。
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

### D3：`summary.py` 的客製分兩條路，依使用者的意圖決定

**修正一件事**：先前討論時我說「包一層覆寫 `build_prompt` 是無效的」。那句話只對一半 ——
在**自己的模組**裡定義 `build_prompt` 然後 `analyze = base.analyze`，確實無效（`base.analyze`
在它自己的模組命名空間裡解析 `build_prompt`）。但**指派到 base 模組上**是有效的，而那正是
`_type_template/summary.py` 的 docstring 已經推薦的寫法：

```python
from ai_analysis_gitlab_mr.device.default import summary as base

def analyze(inputs):
    base.ROLE_PROMPT = MY_ROLE_PROMPT     # 只在這個行程內有效
    return base.analyze(inputs)
```

已實測：`base.ROLE_PROMPT` 與 `base.build_prompt` 兩種指派都生效（`build_prompt` 在呼叫時
才從模組字典解析那兩個常數）。

而「只在這個行程內有效」在這裡**不是勉強的免責，是真的安全**：每個步驟是一個行程、每個行程
一筆 MR、`load_hook("summary")` 只呼叫一次，所以那個行程裡不存在第二個會讀到 `base` 的
使用者。沒有別人會看到被改掉的常數。

所以 skill 依意圖產生兩種：

| 使用者要的 | 產出 | 大小 |
|---|---|---|
| 只改 prompt（最常見） | 照 `_type_template` 推薦的寫法，指派 prompt 常數後轉呼 `base.analyze` | 約 3 行加 prompt 字串 |
| 要改解析或輸出結構 | 自己的 `analyze()`，明著 import 重用 `base.parse_reply` 等零件 | 約 40 行 |

**第一種是預設**，因為它是最常見的需求，而且它是 repo 自己的範本推薦的寫法 —— skill 不該
發明第二套慣例。第二種保留給真的要改 `OUTPUT_SPEC` 與 `parse_reply` 對應關係的人；那兩個是
「同一件事的兩面」（`parse_reply` 的 docstring 自己這麼說），改一個就得改另一個，包不住。

**整支複製 533 行的 `default/summary.py`** 不作為預設。範本說它「最省事」是對的，但那份複本
會跟著 default 漂移，而 skill 的產出會被複製很多次 —— 預設值的影響是乘上次數的。要的人
仍然可以複製，skill 不阻止。

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

實際情況也站在這一邊：現在 `SCRIPT_VERSION = "2.10"` 而 `default` 的 `VERSION = "2.5"` ——
**連 default 都已經不一致了**。把它做成失敗會讓驗證第一次跑就對著 default 報錯，而使用者會
學到的唯一一件事是「這個檢查要忽略」。

### D7：驗證的四項檢查，與各自擋住的失敗

| 檢查 | 用到的 API | 擋住的失敗 |
|---|---|---|
| device 被發現 | `known_devices()` / `resolve_name()` | 目錄名不是合法識別字（`ssd-gen4`）、放錯層、底線開頭 |
| 宣告讀得到 | `device_version()`、`strict_type()`、`code_review_source_heading()` | 漏了必填的 `VERSION`；`STRICT_TYPE = "false"`（字串在 Python 裡是真值）|
| 四支鉤子各自解析到哪 | `load_hook()` 回傳的第二個值 | 「我以為我覆寫了」—— 檔名打錯、放錯目錄，於是安靜落回 default |
| 真實標題跑抽取 | 鉤子的 `extract()` + `normalize_type()` | **D4 那個陷阱**：兩支並排列出，抽歪了一眼看得出來；種類正規化後對不對得上目錄 |

第三與第四項是這支腳本存在的理由 —— 它們是目前**只能靠讀報告末尾**才發現的那兩類錯誤。

輸入的標題樣本由使用者提供（訪談時就會問到）。腳本接受命令列參數或一個小檔案，讓同一組樣本
可以重複跑、也可以進 CI。

## Risks / Trade-offs

- **驗證腳本與載入器的 API 耦合** → 只用 `device/__init__.py` 的 `__all__` 列出的公開名稱，
  不碰底線開頭的內部函式（`_import`、`_hook_file`）。那份 `__all__` 就是這個模組宣告的對外契約。

- **D3 第一種寫法依賴 `default/summary.py` 的常數名**（`ROLE_PROMPT`、`PROMPT_TEMPLATE`）。
  default 改名就壞 → 壞法是 `AttributeError`，發生在 import 時、指名檔案與屬性，不是安靜地
  用錯 prompt。這是可接受的壞法；而驗證的第三項檢查也會在那時失敗。

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
