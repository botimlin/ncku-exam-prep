# 00 索引：什麼情況用哪份

> ⚠️ 舊版入口。考場流程改看 [`../../考場SOP.md`](../../考場SOP.md)；這裡的內容已經併進 `cards/` 與 SOP，留著當紙本備查。

> 用途：工具包入口。考試時先看這份決定要開哪個檔案。
> 兩個版本：`full/`（超詳細，給強模型或自己讀）、`lite/`（精簡，小 context 模型用）。
> lite 檔名對應：`lite/00-starter.md` = full 的 01；`lite/05-submit-and-time.md` = full 的 05 + 06；02、03、04、07 同編號。lite 沒有 01、06。下表的節號指 `full/` 版。
> 最後更新：2026-11

---

## 官方已公布的考場模型條件（2026-11-10 常見問題信）

- 部署在消費級硬體上的小模型，不公開名稱；網頁聊天介面，**不能上傳檔案**；對話長度與單次貼上長度有限制。
- 小模型對 RP2350 / pico-sdk / ROS 2 Jazzy 的細節多半不清楚。**硬體事實要靠你貼給它**：查官方文件（`08-docs-map.md`）或貼 `cards/` 的參考卡。
- 可上網、可登入個人帳號與雲端筆記；**禁止**其他 LLM、AI agent、Copilot、搜尋引擎 AI 摘要、Gmail / LINE / Discord。可帶紙本筆記與書（列印 `print/`）。

## 開考後第一件事

1. 開新對話 → 貼 `cards/00-starter.md` 的卡 1（最短，建議考場用）；模型貼得下才用 `lite/00-starter.md` 或 `01-context.md`。
2. 看題目 → `/理解` → 填題目理解卡（`02-read-spec.md`）。
3. 盤點檔案、跑 baseline、確認能編譯能提交。
4. 開始依 `03-optimize.md` 的流程做。

---

## 依情境找檔案

| 我現在… | 開這份 |
|---|---|
| 剛開新對話 | `01-context.md` / `lite/00-starter.md` |
| 拿到題目、不知道從哪開始 | `02-read-spec.md` |
| 要讀 datasheet 某段 | `02-read-spec.md` 第 4 節 |
| 要讀懂一段程式碼 | `02-read-spec.md` 第 5 節 |
| 要讓程式變快 | `03-optimize.md` |
| 不知道瓶頸在哪 | `03-optimize.md` 第 2、3 節 |
| 編譯 / 連結錯誤 | `04-debug.md` 第 2.1、2.2 節 |
| 程式卡住 / 崩潰 / 結果錯 | `04-debug.md` 第 2 節 |
| 準備提交 | `05-submit-check.md` |
| 不確定時間怎麼分配 | `06-time-plan.md` |
| 碰到工具包沒涵蓋的技術 | `07-unknown-tech.md` |
| 要查 datasheet / pico-sdk / ROS 2 官方文件 | `08-docs-map.md`（章節號、網址、不用 AI 摘要的搜尋法）|
| 要貼一段正確資料給模型 | `cards/<主題>.md`（每張 ≤ 1200 字元，一次貼一張）|
| 開考前 30 分鐘（repo 地圖、CI、理解卡、選範本、時間表） | `cards/10-exam-day-flow.md` |
| CMake / pico-sdk / colcon 建置錯誤、要改 CMakeLists | `cards/05-cmake-build.md`（完整手冊 `../預製程式碼/tools/cmake.md`）|
| gdb、sanitizer、程式卡住、板子沒反應、序列埠 bytes 不對、ROS 2 節點互相看不到 | `cards/06-tools-debug.md`（完整手冊 `../預製程式碼/tools/debug-*.md`）|
| 要讓模型改我的預製範本（不從頭寫） | `cards/09-template-adapt.md` |
| 模型變笨、忘記規則 | `/摘要` → 開新對話 → 貼開場 + 狀態卡 |

## 依技術找檔案（`domain/`）

| 技術 | 檔案 | 內容 |
|---|---|---|
| ROS 2 | `domain/ros2.md` | CLI 排查、rclpy/rclcpp、QoS、executor、效能 |
| RP2350 / pico-sdk 基礎 | `domain/pico-sdk.md` | 架構、記憶體、CMake 建置、計時量測、GPIO、中斷 |
| DMA | `domain/pico-dma.md` | 設定流程、API、chaining、DREQ、與 PIO 搭配 |
| PIO | `domain/pio.md` | 9 條指令、FIFO、side-set、初始化、範例 |
| RISC-V / 位元運算 | `domain/riscv-hazard3.md` | RV32 指令、Hazard3 擴充、inline asm、位元技巧 |
| 多執行緒 / 雙核 | `domain/multicore-sync.md` | 臨界區、鎖、原子操作、pico multicore、FIFO |
| Linux / git / GitLab | `domain/git-env.md` | shell、git 救援、CI pipeline、Docker、建置工具 |

### 備援包（練習包沒提到，但可能出現）

| 技術 | 檔案 | 內容 |
|---|---|---|
| RP2350 周邊 | `domain/pico-peripherals.md` | UART、SPI、I2C、PWM、ADC、timer/alarm、GPIO IRQ、中斷 |
| ARM Cortex-M33 | `domain/arm-cortex-m33.md` | 板子跑 ARM 核心時，取代 RISC-V 包：Thumb-2、FPU/DSP、DWT 計時 |
| 主機↔板子通訊 | `domain/host-mcu-comm.md` | USB CDC / UART、封包格式、CRC、pyserial、ROS 2 橋接、吞吐量計算 |
| 控制與訊號處理 | `domain/control-dsp.md` | 定點數、濾波器、PID、FFT、取樣、interpolator |
| C / Linux 效能 | `domain/c-linux-perf.md` | perf/gprof、cache、struct 佈局、向量化、編譯旗標、I/O 加速 |
| Python / rclpy 效能 | `domain/python-perf.md` | cProfile、CPython 成本模型、GIL、numpy、rclpy callback 成本 |
| 演算法與資料結構 | `domain/algorithms-ds.md` | ring buffer、hash、prefix sum、排序選擇、CRC、慢寫法→替代寫法 |
| 平行與分散式 | `domain/parallel-distributed.md` | Amdahl/Gustafson、分解模式、OpenMP、MPI、管線、ROS 2 分散式 |
| FreeRTOS SMP | `domain/freertos.md` | 板子跑 RTOS 時：task、queue、notification、雙核親和性 |

## 貼給模型的建議組合

| 模型能力 | 貼什麼 |
|---|---|
| **考場預設（小模型、貼上有限）** | `cards/00-starter.md` 卡 1 → 每個問題貼一張相關的 `cards/` 卡或一小段官方文件 + 問題 |
| 貼得下約 4000 字元 | `lite/00-starter.md` + 需要時貼一份 `lite/` 檔案 |
| 強、context 大（考場不太可能） | `full/01-context.md` + 需要時貼對應的 `full/` 檔案 |
| 很弱或不能用 | 自己照 `full/` 的流程與檢查清單做，查 `08-docs-map.md` 與紙本 |

一次不要貼太多。**每次只貼跟目前問題相關的那一張卡或那一段文件。** 卡片分兩種：【提示卡】是要填空後送出的提問模板，【參考卡】是讓模型以正確事實為準的資料。
