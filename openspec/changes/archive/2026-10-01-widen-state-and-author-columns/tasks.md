# Tasks

## 1. Qt

- [x] 1.1 以表格實際的字型量出四種狀態與常見名字所需的寬度，含儲存格內距
      （向樣式問 `PM_FocusFrameHMargin`，不自己猜）
- [x] 1.2 Status 70 → 85，Author 110 → 150
- [x] 1.3 Author 加上提示文字（完整名稱）

## 2. 核對

- [x] 2.1 全新建置零警告零錯誤
- [x] 2.2 離屏截圖確認 `opened` 完整顯示、`Jonas Huang` 完整顯示
- [x] 2.3 以一個刻意過長的名字（`Christopher Nolan`）確認仍會截斷 —— 那是預期行為，
      全名由提示文字補
- [x] 2.4 確認排序、對齊與標題欄的連結色未受影響（同一次執行一併確認）

## 3. 文件

- [x] 3.1 `README.md` 補上欄寬的取捨與 Author 的提示文字

## 4. 待實機驗證

- [ ] 4.1 在 Windows 實機確認兩欄在該平台的字型下也不截斷（寬度是在 Linux 的字型下量的）
- [ ] 4.2 確認滑過被截斷的作者欄會跳出完整名稱

## 5. 併入主規格

- [x] 5.1 把 delta 併入 `openspec/specs/ai-analysis-gitlab-mr/spec.md`
