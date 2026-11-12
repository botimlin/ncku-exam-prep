# 除錯（精簡版）

## 流程
重現 → 縮小 → 列 2–4 個假設 → 每個設計能區分的實驗 → 只改確認的原因 → 回歸測試
止損：卡 20 分問模型或換方法；卡 40 分回到上個能用的 commit 改做別的。

## 回報格式（/除錯）
```
做了什麼 / 預期 / 實際：
完整錯誤（編譯錯誤貼第一個 error）：
相關程式碼：
最近改了什麼 / 已試過：
環境（容器或板子、ARM/RISC-V、編譯指令）：
```

## 症狀 → 原因
| 症狀 | 常見原因 / 處理 |
|---|---|
| 一堆編譯錯誤 | 只修第一個 |
| implicit declaration | 少 include；`grep -rn 名稱 $PICO_SDK_PATH/src --include=*.h` |
| expected ';' | 錯在前一行 |
| undefined reference | CMake 沒連 `hardware_xxx` / `pico_xxx`；少 `-pthread`、`-lm` |
| multiple definition | header 變數要 extern |
| RAM overflowed | buffer 太大，常數改 const |
| 崩潰（Linux） | `-g -O0 -fsanitize=address,undefined`；gdb → run → bt |
| 卡住 | `*_blocking` 等不到資料（FIFO 空、DMA 沒啟動）、死結（鎖順序）、輪詢變數沒 volatile/atomic、中斷沒清旗標、unsigned 遞減迴圈、ROS 沒 spin |
| 結果錯 | 差一、**DMA count 是筆數非 bytes**、有號無號、整數提升、`a & b == c` 優先序、位移 ≥ 寬度 UB、endianness / shift 方向、沒等 DMA 完成就讀、debug 輸出混入 stdout |
| 時好時壞 | 資料競爭（`-fsanitize=thread`）、未初始化（`-Wall -Wextra`）、中斷 / 雙核共用沒保護 |
| 板子沒輸出 | `stdio_init_all()`、CMake `pico_enable_stdio_usb/uart`、開頭 `sleep_ms(2000)`、確認燒的是新版、LED 確認有在跑 |
| ros2 找不到 | `source /opt/ros/jazzy/setup.bash`；自己的套件 `source install/setup.bash` |
| 改了沒效果 | 沒重編、跑到舊執行檔、CMake 快取（刪 build/）|

## ROS 2 沒資料
`node list` → `topic list`（名稱完全一致？）→ `node info` → `topic info -v`（型別、pub/sub 數、QoS）→ `topic echo` → `topic hz` → `topic pub --once` 單獨測（沒 subscriber 會等待，加 `-w 0`）

## 工具
- gdb：`break f` `run` `next` `step` `print x` `print *p@10` `bt` `watch x` `info threads`
- `#define DBG(f,...) fprintf(stderr,"[%s:%d] " f "\n",__FILE__,__LINE__,##__VA_ARGS__)`，提交前移除
- 重複執行：`for i in $(seq 50); do ./prog; done | sort | uniq -c`
- git：`stash` / `stash pop`、`checkout -- f`、`diff <好commit> -- f`、`bisect`
