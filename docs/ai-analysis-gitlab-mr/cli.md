# 不開 Qt 跑這個功能

> 這個功能的六支腳本都能直接在命令列執行。Qt 那一側只是替使用者填信封、
> 按順序按下執行。
>
> **CI 就是命令列，只是由 pipeline 按下執行。** 指令是同一組，所以這兩件事在這裡
> 是同一份文件。
>
> 信封的三種投遞方式、`--dump-config`、`--help` 這些**不限於這個功能**的用法，
> 見 [`scripts/AUTHORING.md`](../../scripts/AUTHORING.md) 第 3.6 與第 10 章。
> 功能本身的畫面與行為見 [README.md](README.md)。

## 六支腳本的介面

六支都**不需要 `config`**。憑證一律走環境變數（見下一節），其餘要給的都在 `params`。

| 腳本 | `action` | 要給什麼 | 做什麼 |
|---|---|---|---|
| `..._list_merge_requests.py` | `list_merge_requests` | `repo`、`only_open`、`created_after_enabled`、`created_after_days` | 取 Merge Request 清單（不屬於五步流程，是給人挑的） |
| `..._description.py` | `mr_description` | `repo`、`mr_iid` | **1/5** 取 MR 描述，已扣掉上一輪貼進去的 AI 分析 |
| `..._info.py` | `mr_info` | `repo`、`mr_iid`、`jira_mode`、`jira_key_manual` | **2/5** 抽出 JIRA key 與 MR 種類 |
| `..._summary.py` | `ai_summary` | 見下面的「步驟 3 的參數」 | **3/5** AI 分析。唯一要錢、唯一要等分鐘級的一步 |
| `..._code_review.py` | `fetch_code_review` | `repo`、`mr_iid`、`jira_key`、`jira_state` | **4/5** 自 JIRA 附件取程式碼審閱報告 |
| `..._merge_to_md.py` | `merge_to_md` | 三個檔案路徑 + `repo`、`mr_iid`、`ai_mode` | **5/5** 合併為 markdown 報告 |

六支都另外收兩個共通的 `params`：

| `params` | 意思 |
|---|---|
| `out_path` | 產物寫到哪裡。**不給就不落檔**，結果只出現在 stdout 的回應信封裡 |
| `debug_dir` | 除錯檔寫到哪裡。不給就不寫 |

**步驟 3 的參數**比較多，因為 AI 的設定不走環境變數：

| `params` | 意思 |
|---|---|
| `description_path` 或 `description` | 步驟 1 的產物。手上是檔案就用前者，是字串就用後者 |
| `jira_key`、`mr_type` | 步驟 2 的產物 |
| `jira_mode` | `auto` 從標題第一個方括號抽 / `manual` 用 `jira_key_manual` / `none` 不用 |
| `ai_mode_name`、`ai_api_url`、`ai_api_key`、`ai_model` | 要問哪一個 AI |
| `ai_timeout`、`ai_retries`、`ai_reask`、`ai_recheck` | 四個等待設定。不給就用腳本自己的預設（120 / 3 / 1 / 0） |

## 憑證走環境變數

```bash
export GITLAB_SERVER_URL=https://gitlab.example.com
export GITLAB_ACCESS_TOKEN=...
export JIRA_SERVER_URL=https://jira.example.com
export JIRA_ACCESS_TOKEN=...
export PPS_SCRIPTS_CODEREVIEW_FILE_STARTSWITH=CodeReview_   # 步驟 4 需要，無預設值
export PPS_DEVICE=default                                   # 省略即 default
```

**AI 的四項不在這裡** —— 它們走 `params`，所以會落在步驟 3 的請求檔裡。那份檔案
用完要刪（見下面「幾個不明顯的地方」）。

不需要設 `PYTHONPATH`：每支入口腳本自己把 `scripts/` 插進 `sys.path`
（理由見[最外層 README](../../README.md) 的「最高原則」末段）。

## 跑一次

五步照順序跑，每一步的產物是下一步的輸入。`W` 是工作目錄。

```bash
cd scripts
W=/tmp/pps-work && mkdir -p "$W"
REPO=group/project
IID=42
```

```bash
# 1/5 取 MR 描述 -> 01_description.md
echo '{"action":"mr_description","config":{},"params":{
  "repo":"'$REPO'","mr_iid":"'$IID'","out_path":"'$W'/01_description.md"}}' \
  | python3 ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_description.py --request-stdin
```

```bash
# 2/5 抽出 JIRA key 與種類 -> 02_mr_info.json
echo '{"action":"mr_info","config":{},"params":{
  "repo":"'$REPO'","mr_iid":"'$IID'","jira_mode":"auto","jira_key_manual":"",
  "out_path":"'$W'/02_mr_info.json"}}' \
  | python3 ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_info.py --request-stdin

JIRA_KEY=$(python3 -c "import json;print(json.load(open('$W/02_mr_info.json'))['jira_key'])")
MR_TYPE=$(python3 -c "import json;print(json.load(open('$W/02_mr_info.json'))['mr_type'])")
```

```bash
# 3/5 AI 分析 -> 03_summary.json
cat > "$W/req3.json" <<EOF
{"action":"ai_summary","config":{},"params":{
  "repo":"$REPO","mr_iid":"$IID",
  "description_path":"$W/01_description.md",
  "jira_key":"$JIRA_KEY","jira_mode":"auto","mr_type":"$MR_TYPE",
  "ai_mode_name":"Open AI","ai_api_url":"$AI_API_URL",
  "ai_api_key":"$AI_API_KEY","ai_model":"gpt-4o",
  "out_path":"$W/03_summary.json"}}
EOF
python3 ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py --request "$W/req3.json"
rm -f "$W/req3.json"          # 裡面有 AI 金鑰

JIRA_STATE=$(python3 -c "import json;print(json.load(open('$W/03_summary.json'))['analysis']['jira_state'])")
```

```bash
# 4/5 程式碼審閱報告 -> 04_code_review.json（可能不產生）
rm -f "$W/04_code_review.json"
echo '{"action":"fetch_code_review","config":{},"params":{
  "repo":"'$REPO'","mr_iid":"'$IID'",
  "jira_key":"'$JIRA_KEY'","jira_state":"'$JIRA_STATE'",
  "out_path":"'$W'/04_code_review.json"}}' \
  | python3 ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_code_review.py --request-stdin
```

```bash
# 5/5 合併為 markdown -> 05_report.md
CR=""
[ -f "$W/04_code_review.json" ] && \
  CR="\"code_review_json_file_path\": \"$W/04_code_review.json\","

cat > "$W/req5.json" <<EOF
{"action":"merge_to_md","config":{},"params":{
  "ori_md_file_path":"$W/01_description.md",
  "mr_summary_json_file_path":"$W/03_summary.json",
  $CR
  "repo":"$REPO","mr_iid":"$IID","ai_mode":"Open AI",
  "out_path":"$W/05_report.md"}}
EOF
python3 ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_merge_to_md.py --request "$W/req5.json"

cat "$W/05_report.md"
```

步驟 1 與 2 的順序可以互換，其餘不行 —— 3 吃 1 與 2 的產物，4 吃 2 與 3 的，
5 吃 1、3、4 的。

## 不必記上面那些

`--dump-config` 會印出該腳本的信封模板，連每個鍵的說明一起：

```bash
python3 ai_analysis_gitlab_mr/ai_analysis_gitlab_mr_summary.py --dump-config
```

填完存成檔案，用 `--request` 餵進去即可。模板由參數宣告導出，不是另外手寫的一份，
所以它不會與 `--help` 或實際接受的鍵不一致。

## 在 CI 上

可照抄的範例：

```
ci/pps-ai-analysis.gitlab-ci.yml
```

那是**給使用者的樣板，不是本專案自己的 pipeline**。複製到你的 repo 根目錄改名
`.gitlab-ci.yml` 即可。一個 stage、一個 job、五步照順序跑；GitLab 的 `script` 是一份
shell 腳本，前一行失敗就不會執行下一行，所以「失敗即停並指出第幾步」與 Qt 那側一致，
而且不必額外寫任何判斷。

| | Qt 工具 | CI |
|---|---|---|
| 投遞 | 信封走 stdin | 每一步寫一份 `req<N>.json`，`--request` 餵進去 |
| 設定來源 | 設定檔的 `Service` 區塊，由 Qt 注入成環境變數 | CI/CD Variables，runner 自行設定 |
| 編排 | `runFunctionFlow()` | `script:` 的行序 |
| 進度與診斷 | Debug console | job log（stderr 與 stdout 都進去） |
| 產物 | 工作目錄（勾除錯時留時間戳目錄） | `artifacts.paths` |

腳本端對兩個呼叫端**長得一模一樣**：憑證只從環境變數讀、產物只由 `out_path` 決定、
log 全走 stderr。所以沒有「CI 專用的腳本路徑」要維護。

要先設成 CI/CD Variables（**Masked + Protected**）的四個：

```
GITLAB_ACCESS_TOKEN   JIRA_ACCESS_TOKEN   AI_API_URL   AI_API_KEY
```

## 幾個不明顯的地方

- **AI 金鑰會落在 `req3.json` 裡**（AI 四項走 `params`，不走環境變數），所以範例在步驟 3
  之後立刻刪它，並在 `after_script` 再刪一次 —— `after_script` 連失敗的 job 也會跑，
  而 `artifacts` 收的是整個 `pps-work/`
- **步驟 4 永遠執行**，「要不要真的去抓附件」由它自己依 `jira_key` 與 `jira_state` 決定。
  在 CI 再判一次就有了第二份規則，而兩份規則會漂移
- **步驟 5 收的是檔案路徑，不是內容。** 路徑給了就必須存在，所以步驟 4 沒落檔時
  `code_review_json_file_path` **整個鍵不放**（不是放空字串）
- **`jira_state` 來自步驟 3，不是步驟 2** —— 步驟 2 抽出 key，步驟 3 才判定它有效與否
- **`-v` 打開 DEBUG 等級**。job log 有大小上限（預設 4 MB），`-v` 加上一支大 MR 有可能
  撞到，而被截掉的是尾端 —— 也就是結果信封所在的位置
