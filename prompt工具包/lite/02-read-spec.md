# 讀題與文件（精簡版）

## 原則
先廣後深｜先找評分方式｜分清事實與推測｜寫下理解｜datasheet 只讀相關段落（Overview → 方塊圖 → 操作流程 → 暫存器表 → 限制 → 範例）

## 1. 盤點（5–10 分）
```bash
find . -type f -not -path './.git/*' | head -100
find . -name CMakeLists.txt -o -name Makefile -o -name package.xml
cat .gitlab-ci.yml            # 實際評分流程
git log --oneline | head
grep -rn "TODO\|FIXME\|HINT" --include='*.[chS]' --include='*.py' --include='*.pio' .
```
要找：題目說明、評分腳本 / CI、建置設定、進入點、TODO 位置、「請勿修改」區、範例輸入輸出。

## 2. 題目理解卡
```
目標（一句話）：
輸入 / 輸出（格式精確到空白換行）：
評分：正確性判定 / 效能指標與單位 / 給分方式 / 提交限制
限制：時間、記憶體、硬體、不能改的檔案與介面
可動的地方：
baseline：
疑點：
```
沒寫的填「未說明」，不要猜。

## 3. 架構圖要回答
元件（node / 執行緒 / 核心 / DMA ch / PIO SM / ISR）｜連接（topic / FIFO / 共享記憶體 / DMA / 中斷）｜資料流（格式、量、頻率）｜觸發方式（輪詢 / 中斷 / timer）｜共享資源與保護｜最慢的段｜有限資源（DMA ch、PIO 32 條指令、FIFO 深度、SRAM、核心）
```
[來源] --(格式,頻率)--> [A] --(機制)--> [B] --> [輸出]
```

## 4. 精讀段落
一次貼一小節；先問「跟題目有關嗎」；數值保留原文；PDF 用搜尋找暫存器名、"must"、"note"、"errata"。

## 5. 走讀程式
main → 主迴圈 → 標出初始化 / 處理 / 輸出 / 同步點 → 深入熱點。
```bash
grep -rn "dma_\|pio_\|multicore_\|spin_lock\|mutex" --include='*.c' .
grep -rn "create_subscription\|create_publisher\|create_timer" .
```

## 6. 動手前
先跑 baseline（編譯、執行、可以的話提交一次），確認工具鏈可用並記下基準分數。

## 常見錯誤
沒看評分腳本｜輸出格式差一個空白｜單位搞錯（bytes vs 筆數、ms vs us）｜改到不能改的｜沒跑 baseline｜從頭細讀整章｜沒查證模型說的 API
