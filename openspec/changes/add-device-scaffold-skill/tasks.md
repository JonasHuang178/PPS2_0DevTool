# Tasks

## 1. 離線驗證腳本 `tools/verify_device.py`

先做這一組：skill 的流程最後一步要呼叫它，而它可以**獨立對 `default` 驗證**，不必等 skill 存在。

- [ ] 1.1 建立 `tools/verify_device.py` 的骨架：接受 device 名稱參數（省略時讀 `PPS_DEVICE`，
      再省略則 `default`），把 `scripts/` 加進 `sys.path`，只 import `device/__init__.py` 的
      公開 API（見 design D7 與風險一節，不碰底線開頭的內部函式）。驗證：`python3 tools/verify_device.py default`
      能跑完並以結束碼 0 結束。
- [ ] 1.2 實作「device 被發現」與「宣告讀得到」兩項檢查：`known_devices()`、`resolve_name()`、
      `device_version()`、`strict_type()`、`code_review_source_heading()`。`VERSION` 第一碼與
      `ai_analysis_gitlab_mr.SCRIPT_VERSION` 比對**不一致只警告**（design D6）。驗證：對 `default`
      跑出 `VERSION 2.5` 與 `SCRIPT_VERSION 2.10` 的第一碼不一致警告，且結束碼仍為 0。
- [ ] 1.3 實作「四支鉤子各自解析到哪一份」的表：對 `jira_key`、`mr_type`、`summary`、`merge_to_md`
      各呼叫 `load_hook()`，印出回傳的 owner 與（因種類而異的兩支）種類層命中與否。驗證：對
      `default` 跑出四支 owner 皆為 `default`；對一個只放 `merge_to_md.py` 的暫時 device 跑出
      三支落回 `default`、一支是它自己。
- [ ] 1.4 實作「真實標題跑抽取」的並排表：對每個樣本標題組出鉤子收到的 mr dict（`title`、
      `source_branch`、`target_branch`、`description`、`repo`、`mr_iid`），呼叫兩支 `extract()`，
      把 `jira_key` 與 `mr_type` 的結果**並排**列出，`mr_type` 再經 `normalize_type()` 並標示
      對不對得上該 device 的種類目錄（`known_types()`）。驗證：標題 `mod:[PPS-1234][Bug] 修正重試上限`
      對 `default` 跑出 `jira_key=PPS-1234`、`mr_type=Bug -> bug`，且 `bug` 標示為無對應目錄。
- [ ] 1.5 實作「步驟 2 的輸出契約」檢查：兩支 `extract()` 的回傳必須是字串，`None` 要明確指出
      （範本寫明「抽不到就回空字串 —— 不要回 `None`」），`mr_type` 非字串時比照
      `normalize_type()` 的 `DEVICE_HOOK_BAD_RETURN` 報法。驗證：一支回 `None` 的
      `jira_key.extract()` 被指名為違反契約，而回 `""` 的通過。
- [ ] 1.6 實作「步驟 3 的輸出契約」檢查：以**空的 `ai_api_url`** 備好 `inputs`（含 `fetch_jira`、
      `progress`、`debug_write` 三個可呼叫項的無作用替身）呼叫 `analyze()`，把回傳交給
      `wrap_analysis()` 再 `validate_analysis(payload, source=...)`，`source` 帶上 device 與檔名；
      不過就照入口腳本的做法把整份寫成 `bad_analysis.json` 供人檢視。另外檢查 overview 首行是否
      言明未經過 AI（既有需求「未設定 AI 端點時……SHALL 於首行言明未經過 AI」）。驗證：對
      `default` 跑出通過且首行言明的結果（見 `_stub_analysis()`）；對一支回傳 `{}` 的
      `analyze()` 跑出 `AnalysisFormatError` 的訊息並產出 `bad_analysis.json`。
- [ ] 1.7 實作「步驟 5 的輸出契約」檢查：備好 `inputs`（`analysis` 用一份通過驗證的最小結構，
      形狀見 `03_t.json`）呼叫 `render()`，**明確檢查 `isinstance(section, str)`** —— 這是
      `contract.plain()` 會靜默 `str()` 掉的那個缺口。執行期例外比照入口包成指名種類的
      `DEVICE_HOOK_RUNTIME_ERROR`。驗證：一支回傳 dict 的 `render()` 被指名為違反契約；
      對 `default` 跑出通過。
- [ ] 1.8 讓樣本標題可由命令列多次給定，也可由一個每行一個標題的檔案給定，使同一組樣本能重複跑
      並進 CI。沒有給樣本時跳過 1.4 那一節並明說跳過了，不視為通過。驗證：命令列與檔案兩種給法
      對同一組樣本印出相同的表。
- [ ] 1.9 定義結束碼：載入或宣告層面的錯誤（device 不存在、`VERSION` 缺漏、鉤子語法錯誤、
      `STRICT_TYPE` 型別不對）與**輸出格式違反契約**（1.5–1.7）為非 0；版號第一碼不一致、抽取結果
      對不上種類目錄等**判斷留給人**的情況為 0 並印警告。驗證：對一個不存在的 device 名稱跑出非 0；對 `default` 跑出 0。
- [ ] 1.10 在 `scripts/AUTHORING.md` 與 `README.md` 的 device 一節各加一段指向這支腳本的說明
      （怎麼跑、它回答哪五個問題、以及它**不**回答什麼 —— 尤其「驗形狀不等於驗品質」）。只加指路與用法，不重述鉤子介面。
      驗證：照文件寫的指令原樣複製到終端機能跑出預期輸出。

## 2. skill 本體

- [ ] 2.1 建立 `.claude/skills/<名稱>/SKILL.md` 的 frontmatter：name、description 要能在
      「建一個自己的 device」「客製 MR 分析邏輯」「`PPS_DEVICE`」這類說法下被觸發，
      `allowed-tools` 限制到實際需要的範圍。驗證：在本 repo 的 session 裡列出可用 skill 能看到它，
      且描述裡出現 device 與 AI Analysis GitLab MR 的字樣。
- [ ] 2.2 寫訪談那一節：device 名稱（檢查識別字形狀、與 `known_devices()` 不衝突）、2~3 個真實
      MR 標題樣本（要求至少一個反例，見 design 風險一節）、要覆寫哪幾支鉤子、是否分種類與有哪些、
      `STRICT_TYPE`、code review 總表節名是否與預設不同。驗證：照 SKILL.md 走一遍，上述每一項
      都有被問到且答案被記下來。
- [ ] 2.3 寫鷹架那一節：從 `_template/` 複製出**只有使用者要覆寫的那幾支**加上 `__init__.py`，
      種類目錄**不產生** `__init__.py`（design D5），並允許只建空的種類目錄。內容一律指回
      `_template/`、`AUTHORING.md`、`README.md`，不抄其介面說明（design D2）。驗證：對「只要
      `merge_to_md.py`、兩個種類」這組答案，產出的目錄樹恰好是 `__init__.py`、`merge_to_md.py`
      與兩個子目錄，且沒有多餘檔案。
- [ ] 2.4 寫「輸入在哪、輸出要守什麼」那一節（design D3）：鷹架是 `_template/` **原樣複製**，
      實作區留空給使用者；skill 指出每一支的輸入規格就在該檔的 docstring，並把四支的輸出契約
      列成一張表（`extract()` 回字串、`analyze()` 回 `contract.analysis_body(...)`、`render()`
      回 markdown 字串）。**不產生實作、不建議實作該長什麼樣。** 另以一句提示告知「想重用
      `default/` 的零件就明著 import」，標明那是使用者的自由而非規定。驗證：產出的四支鉤子
      實作區為空（或僅保留範本原有的佔位），且 `load_hook()` 四支都載入得到。
- [ ] 2.5 寫 D4 那個例外的提示：使用者只要 `mr_type.py` 而標題格式與 default 不同時，指出
      `jira_key.py` 多半也得寫、說明症狀（報告末尾的 `JIRA: Alpha (invalid)`）、但**不替他決定**。
      驗證：以「標題 JIRA key 在第二個方括號、只要 mr_type」這組答案走一遍，提示出現且使用者
      維持原決定時流程照樣完成。
- [ ] 2.6 寫最後的驗證那一節：呼叫 `tools/verify_device.py`，帶上訪談時收集的標題樣本，把輸出
      原樣交給使用者並解讀警告。使用者填完實作後**再跑一次**，因為 1.5–1.7 的輸出契約檢查
      只有在實作存在時才有意義。驗證：流程走完後終端機上出現 1.3 與 1.4 兩張表；實作填完後
      再跑一次會多出 1.5–1.7 的三段結果。

## 3. 端到端確認

- [ ] 3.1 照 skill 走一遍建出一個暫時的 device（標題格式刻意與 default 不同），確認它可被
      `PPS_DEVICE` 指定、四支鉤子解析如預期。驗證：`python3 tools/verify_device.py <名稱>`
      結束碼 0，且鉤子表顯示的 owner 與訪談時的選擇一致。
- [ ] 3.2 在那個暫時的 device 上**故意只寫 `mr_type.py`**，確認 1.4 的並排表讓「`jira_key`
      沿用 default 抽到錯的東西」看得出來。驗證：表上同一個標題的 `jira_key` 欄位是 default
      規則抽出的錯值，且該列有標示它來自 `default`。
- [ ] 3.3 在那個暫時的 device 上**故意讓 `render()` 回傳 dict**，確認 1.7 抓得到。驗證：驗證
      腳本以非 0 結束並指名該檔違反輸出契約；而對照之下，不經驗證直接跑步驟 5 會產出一份把
      `{'overview': ...}` 字面印進報告、且回報成功的結果 —— 兩者並列即為這項檢查的理由。
- [ ] 3.4 移除暫時的 device，確認 `known_devices()` 回到變更前的內容，`git status` 沒有殘留。
      驗證：`python3 tools/verify_device.py default` 仍為 0，且工作區只剩本變更要交付的檔案。
