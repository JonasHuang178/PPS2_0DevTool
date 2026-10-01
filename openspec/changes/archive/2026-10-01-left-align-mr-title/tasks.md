# Tasks

## 1. Qt

- [x] 1.1 建列迴圈裡的對齊改成條件式：標題欄 `AlignLeft | AlignVCenter`，其餘 `AlignCenter`
- [x] 1.2 確認標題欄仍垂直置中（單用 `AlignLeft` 會讓文字貼著儲存格頂端，與其餘四欄差半行）

## 2. 核對

- [x] 2.1 全新建置零警告
- [x] 2.2 離屏啟動跑滿不崩
- [x] 2.3 以 Qt 實測：照正式碼那一段設過之後，標題欄讀回 `AlignLeft | AlignVCenter`、
      其餘四欄讀回 `AlignCenter`、表頭仍是置中

## 3. 文件

- [x] 3.1 `README.md` 的對齊說明改掉

## 4. 待實機驗證

- [ ] 4.1 取回一批真實的 Merge Request，目視確認標題靠左、其餘四欄置中，且四欄與表頭對齊
- [ ] 4.2 確認標題過長時截斷與靠左同時成立，提示文字仍是完整標題

## 5. 併入主規格

- [x] 5.1 把 delta 併入 `openspec/specs/ai-analysis-gitlab-mr/spec.md`
