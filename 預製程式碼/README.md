# 成大上機考 預製程式碼（總索引）

> 先讀 [`預測考題.md`](預測考題.md)：裡面有硬體推測、歷屆對照、猜題清單。
> 每份程式碼都有繁中註解，要改的地方都標了 `TODO(改這裡)`。

## 考場用法（3 步）
1. **讀完題目和出題 repo 的 README**，判斷題目像下表的哪一種。
2. 打開對應的檔案，**先看檔頭註解和 `TODO(改這裡)`**，照題目的規格改。
3. 一定要先交一個**能動的版本**（有完成次序分），再回來優化。

## 題型 → 檔案

| 題目在問… | 打開 |
|---|---|
| ROS 2 node 寫不出來或資料沒在傳 | `ros2/node_template.py`、`ros2/README.md`（CLI 除錯清單） |
| 電腦用 USB 序列埠傳資料給 Pico | `ros2/frame.py` + `ros2/serial_bridge.py` ↔ `pico/serial_proto.c` + `pico/app_serial.c`（**兩邊封包格式一致**） |
| 電腦和 Pico 用 micro-ROS 溝通 | `micro-ros/`（先看 README 的排查表） |
| 傳太慢 | `ros2/serial_bridge.py` 的批次模式（實測快約 350 倍）、`ros2/bench.py` |
| 拆給多片板子平行算 | `ros2/multi_device.py`、`micro-ros/host_driver.py`、`algo/sort.c`（merge） |
| 依規格打包或拆解位元欄位 | `bits-riscv/bitops.h`、`bits-riscv/packet_fields.c` |
| 從位元流讀欄位 | `bits-riscv/bitstream.c` |
| RISC-V 指令編碼、解碼、模擬器 | `bits-riscv/rv32_encode_decode.c` |
| 寫 RISC-V 組語 | `bits-riscv/asm_examples.S`、`bits-riscv/rv32_asm_cheatsheet.md` |
| PIO 程式 | `pico/pio/*.pio`、`pico/app_pio.c` |
| 雙核心 race condition、鎖、queue | `pico/app_multicore.c`（Pico）、`linux-perf/parallel_template.c`（電腦） |
| 一個收資料、一個計算的 pipeline | `pico/app_multicore.c`、`linux-perf/pipeline_template.c`、`micro-ros/pico_dualcore_micro_ros.c` |
| DMA 複製、填值、通道管理 | `pico/app_dma.c` |
| DMA 硬體算 CRC32（sniffer） | `pico/app_dma.c`（開機自我測試會印 PASS 或 FAIL） |
| DMA 搭配 PIO（DREQ） | `pico/app_dma_pio.c` |
| CRC（各種規格） | `algo/crc32.c`（`crc_generic` 可以直接填規格參數） |
| SHA-0、SHA-1、SHA-256 | `algo/sha1_sha0.c`、`algo/sha256.c` |
| 排序、合併 | `algo/sort.c`（radix 比 qsort 快約 9 倍） |
| 二值神經網路（eBNN） | `algo/bnn.c` |
| 其他校驗碼（Adler、Fletcher、XOR） | `algo/checksum_misc.c` |
| 量時間 | `pico/timing.h`、`linux-perf/bench.h` |
| 優化清單、perf 用法 | `linux-perf/README.md` |
| CMake 怎麼改、CMake 錯誤怎麼修 | `tools/cmake.md`（22 個真實錯誤的對照表） |
| gdb、sanitizer、strace、Python 除錯 | `tools/debug-host.md` |
| 板子沒反應、序列埠監看、看 .dis/.map | `tools/debug-pico.md` |
| ROS 2 進階除錯（doctor、log、rosbag、跨容器） | `tools/debug-ros2.md` |
| 不能裝擴充套件的 VS Code、vim/nano 求生 | `tools/vscode.md` |
| 考場工具 SOP（10 步） | `tools/README.md` |

## 驗證狀態（要誠實知道哪些沒試過）

| 資料夾 | 驗證程度 |
|---|---|
| `ros2/` | ✅ 在 ROS 2 Jazzy 容器裡搭配模擬 Pico（`fake_pico.py`）實際跑過 |
| `algo/`、`linux-perf/` | ✅ 電腦上的測試全部通過（含標準測試向量）；ARM 和 RISC-V 都能編譯 |
| `bits-riscv/` | ✅ 電腦上測試通過；RISC-V 版在 qemu 模擬器上跑過 |
| `tools/` | ✅ CMake、gdb、sanitizer、ROS 2 指令都實際跑過；燒錄、實體序列埠、Debug Probe 只對照官方文件（標「沒有實測」） |
| `pico/` | ✅ ARM 編譯通過（0 錯誤、0 警告；SDK 2.2.0 和 2.1.1 都試過），**已逐行對照 SDK 2.2.0 原始碼和 datasheet 暫存器說明審查**，修了 11 個問題（見 `pico/README.md` 的設計審查紀錄）。⚠️ 沒在實體板子上跑過 |
| `micro-ros/` | ✅ 3 支 Pico 端程式都**編譯、連結通過**（pico-sdk 2.2.0、pico2、官方 jazzy `libmicroros.a`），也已逐行對照官方 jazzy 標頭檔審查，修了 8 個問題。⚠️ 沒在板子上跑過、沒接 agent 測過。官方的 lib 還沒正式支援 Pico 2（能連結，但執行沒有保證），連結失敗時的處理方式寫在 `micro-ros/README.md` §6 |

## 考前要做
- 把整個 `預製程式碼/` 放到考場打得開的地方：**私人** GitHub repo，或 Google Drive。不要公開，以免別的考生拿去用。
- 考場的模型一次能貼的程式碼有限，**一次只貼一個檔案的一小段**。
