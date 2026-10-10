# 不開 Qt 跑這個功能

> 這個功能的四支腳本都能直接在命令列執行。Qt 那一側只是替使用者填信封、
> 按下執行。
>
> **CI 就是命令列，只是由 pipeline 按下執行。** 指令是同一組，所以這兩件事在這裡
> 是同一份文件。
>
> 信封的三種投遞方式、`--dump-config`、`--help` 這些**不限於這個功能**的用法，
> 見 [`scripts/AUTHORING.md`](../../scripts/AUTHORING.md) 第 3.6 與第 10 章。
> 功能本身的畫面與行為見 [README.md](README.md)。

## 四支腳本的介面

四支都**不需要憑證、不需要 `config`**。要給的只有 `source_path` 與（寫入那一支的）
`params`。

| 腳本 | `action` | 要給什麼 | 做什麼 |
|---|---|---|---|
| `single_building_list_source.py` | `list_source` | `source_path` | 列出該層的 `.cpp`（不遞迴） |
| `single_building_list_target.py` | `list_target` | — | 讀出暫存設定檔的內容 |
| `single_building_modify_setting.py` | `modify_setting` | `params.files`（絕對路徑清單） | 寫入暫存設定檔 |
| `single_building_recovery_setting.py` | `recovery_setting` | — | 清空暫存設定檔並回讀 |

`source_path` 是**目錄**，不是檔案。只有 `list_source` 會用到它；另外三支讀寫的是
暫存設定檔，與來源路徑無關。

暫存設定檔的位置由 `scripts/single_building/__init__.py` 的 `SETTING_FILE_NAME`
決定一次（目前 `PPS2_0DevTool_single_building.txt`，放在作業系統的暫存目錄），
三支讀寫它的腳本共用那一個宣告。

## 跑一次

```bash
cd scripts

# 1) 列出來源目錄裡的 .cpp
echo '{"action":"list_source","source_path":"/path/to/src","config":{},"params":{}}' \
  | python3 single_building/single_building_list_source.py --request-stdin
```

```json
{"result": "PASS", "message": "找到 2 個 .cpp 檔案",
 "detail": "來源路徑：/path/to/src",
 "data": {"files": [{"name": "a10.cpp", "path": "/path/to/src/a10.cpp"},
                    {"name": "a2.cpp",  "path": "/path/to/src/a2.cpp"}]}}
```

```bash
# 2) 把挑好的絕對路徑寫進暫存設定檔
echo '{"action":"modify_setting","source_path":"","config":{},
       "params":{"files":["/path/to/src/a2.cpp"]}}' \
  | python3 single_building/single_building_modify_setting.py --request-stdin
```

```json
{"result": "PASS", "message": "已保存 1 筆設定",
 "detail": "設定檔：/tmp/PPS2_0DevTool_single_building.txt",
 "data": {"count": 1}}
```

```bash
# 3) 讀回來確認
echo '{"action":"list_target","source_path":"","config":{},"params":{}}' \
  | python3 single_building/single_building_list_target.py --request-stdin

# 4) 清空
echo '{"action":"recovery_setting","source_path":"","config":{},"params":{}}' \
  | python3 single_building/single_building_recovery_setting.py --request-stdin
```

`list_source` 的 `data.files` 的 `path` 可以直接當 `modify_setting` 的
`params.files` 用 —— 那正是 Qt 那一側在做的事，它不改這些值。

## 不必記上面那些

`--dump-config` 會印出該腳本的信封模板，連每個鍵的說明一起：

```bash
python3 single_building/single_building_modify_setting.py --dump-config
```

```json
{
  "_template_version": "2.0.0",
  "action": "modify_setting",
  "source_path": "",
  "config": {},
  "params": { "files": [] },
  "_help": {
    "config": {},
    "params": { "files": "要保存的絕對路徑清單，一個字串一筆" }
  }
}
```

填完存成檔案，用 `--request` 餵進去即可。模板由參數宣告導出，不是另外手寫的一份，
所以它不會與 `--help` 或實際接受的鍵不一致。

## 排序由 Qt 做，不是腳本

`list_source` 回的是 `os.listdir()` 給的次序 —— 腳本裡沒有任何 `sorted()`，
所以那個次序**不保證**，會隨檔案系統而異。上面的範例輸出剛好是 `a10.cpp` 在前。

畫面上看到的自然排序（`a2.cpp` 在 `a10.cpp` 之前）在 Qt 的代理模型裡，不在腳本裡。
命令列使用者要同樣的次序得自己排。

這是刻意的：排序是呈現，而腳本不負責呈現。
