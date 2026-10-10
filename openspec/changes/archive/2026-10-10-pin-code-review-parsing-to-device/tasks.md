# Tasks

## 1. 載入器

- [x] 1.1 `device/__init__.py` 的分組註解改寫：三支的兩個理由分開寫，並寫明
      `parse_code_review` 看得到種類但**刻意**不用（design D1、D2）。
      驗證：`UNTYPED_HOOKS` 仍是三支、`TYPED_HOOKS` 仍是兩支、`HOOK_NAMES` 仍是五支。

## 2. 入口腳本與呼叫端

- [x] 2.1 `..._code_review.py` 的 `_parse_with_hook()` docstring 加一句：這一支雖然
      跑在步驟 4、種類已經解出來了，但不依種類解析，並指向載入器的分組說明。
- [x] 2.2 `AIAnalysisGitLabMR.cpp` 步驟 4 加一句註解：**不轉送種類**，以及為什麼。
      驗證：`qmake && make` 零警告。

## 3. 規格

- [x] 3.1 live spec：「鉤子 SHALL 分為兩類」那一段改寫 —— 分類不變，但兩個理由分開
      寫，並把 `parse_code_review` 那一條升級成 SHALL NOT 依種類解析。
- [x] 3.2 新增一條 MUST NOT：那一步的鉤子 MUST NOT 收到種類（design D4）。
- [x] 3.3 補兩個 scenario：種類目錄中的解析鉤子不被載入、那一步不收種類。
- [x] 3.4 `openspec validate --all` 全綠。

## 4. 文件

- [x] 4.1 `device-authoring.md`：鉤子表的「因種類而異」欄維持「否」，底下那段改寫成
      「它看得到種類但刻意不用，因為報告格式是 device 的屬性」。
- [x] 4.2 `device-authoring.html`：掛點圖配色與圖下說明同步；Q&A 新增一題
      「想換掉審閱報告的解析規則該怎麼改」。
- [x] 4.3 `_type_template/README.md` 維持「只有兩支會因種類而異」，並補一句說明
      `parse_code_review` 為什麼不在裡面。

## 5. 確認

- [x] 5.1 步驟 4 的 `--dump-config` 不含 `mr_type`。
- [x] 5.2 `qmake && make` 零警告、全 py `compileall` 過、文件零死連結。
