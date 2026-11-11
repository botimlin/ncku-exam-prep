# 08 官方文件導航圖（精簡）
> 版本：RP2350 datasheet Release 8（2026-10-01，80d627281ed5）；pico-sdk 2.3.1；ROS 2 Jazzy。詳見 full/08-docs-map.md｜最後更新 2026-11
> 頁碼 = 頁面右下角印的頁碼；PDF 檢視器頁框約 +1。用「節號. 節名」Ctrl+F，例 `12.6.4.1. System`。

## RP2350 datasheet
https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
| 主題 | 節 | p. |
|---|---|---|
| 原子別名 +0x1000 XOR/+0x2000 SET/+0x3000 CLR | 2.1.3 | 23 |
| 窄寫入 8/16-bit | 2.1.5 | 24 |
| 位址總表 Table 8 | 2.2 | 27 |
| SIO spinlock / FIFO / doorbell | 3.1.4 / 3.1.5 / 3.1.6 | 37–39 |
| Interpolator | 3.1.10 | 40 |
| IRQ 號碼 Table 95 | 3.2 | 80 |
| M33 指令週期 | 3.7.4.9 | 127 |
| Hazard3 擴充 / Xh3irq / 週期 / CSR | 3.8.1 / 3.8.6.1 / 3.8.7 / 3.8.9 | 227 / 265 / 272 / 279 |
| XIP cache | 4.4.1 | 315 |
| 核心 1 啟動 | 5.3 | 345 |
| 時脈 / PLL | 8.1 / 8.6 | 467 / 527 |
| GPIO 功能表 Table 677 / Pads | 9.4 / 9.6 | 540 / 543 |
| PIO 程式模型 / 指令集 | 11.2 / 11.4 | 793 / 802 |
| Side-set / FIFO join / Autopull / CLKDIV | 11.5.1 / 11.5.3 / 11.5.4 / 11.5.5 | 814–821 |
| PIO 範例 / 暫存器 | 11.6 / 11.7 | 826 / 847 |
| UART / I2C / SPI / ADC / PWM | 12.1 / 12.2 / 12.3 / 12.4 / 12.5 | 871 / 892 / 943 / 963 / 973 |
| DMA 設定 / Count modes | 12.6.2 / 12.6.2.2.1 | 1011 / 1012 |
| DMA CTRL（RING_SIZE、CHAIN_TO） | 12.6.2.3 | 1013 |
| DMA 觸發 / chaining | 12.6.3 / 12.6.3.2 | 1013 / 1014 |
| DREQ 表 Table 1254 | 12.6.4.1 | 1015 |
| DMA IRQ / sniffer CRC / abort | 12.6.5 / 12.6.8.2 / 12.6.8.3 | 1017 / 1021 / 1021 |
| DMA 暫存器 | 12.6.10 | 1025 |
| Timer / Watchdog | 12.8 / 12.9 | 1094 / 1105 |
| 勘誤 Appendix D | D | 1351 |

勘誤：E1 interp OVERF §D.9.1｜E2 spinlock 鏡像 +0x80 §D.9.2｜E5 CHAIN_TO+ABORT §D.4.1｜E8 零長度 CHAIN_TO §D.4.2｜E9 GPIO pull-down（A2）§D.5.1｜E27 bus priority §D.3.1｜E30 reboot(0) §D.2.13。Ctrl+F `RP2350-E5`。

## 其他 PDF（datasheets.raspberrypi.com/pico/…）
- pico-2-datasheet.pdf（§3.1 pinout）
- getting-started-with-pico.pdf（Appendix C 命令列建置）
- raspberry-pi-pico-c-sdk.pdf（2.8 多核、3.3 pioasm、7 CMake 設定、8 CMake 函式）

## pico-sdk API（瀏覽器可開，curl 會被擋）
https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_dma
同頁換錨點：`group_hardware_pio` `group_sm_config` `group_hardware_gpio` `group_hardware_irq` `group_hardware_sync` `group_hardware_interp` `group_hardware_timer`
high_level.html：`group_pico_multicore` `group_pico_sync` `group_pico_time` `group_queue`
runtime.html：`group_pico_stdio`

## 標頭檔（最好貼）
前綴 https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/
- `rp2_common/hardware_dma/include/hardware/dma.h`（pio、gpio、irq、sync 同格式）
- `rp2_common/pico_multicore/include/pico/multicore.h`
- `common/pico_time/include/pico/time.h`、`common/pico_util/include/pico/util/queue.h`
- `rp2350/hardware_regs/include/hardware/regs/dreq.h`、`intctrl.h`、`platform_defs.h`（上一層）
GitHub：`t` 找檔、`y` 永久連結、Raw 按鈕。不要按 Copilot 與 `.`。
範例：github.com/raspberrypi/pico-examples（dma/ pio/ multicore/ interp/ timer/ adc/dma_capture）

## ROS 2 Jazzy（https://docs.ros.org/en/jazzy/ 開頭）
- `Concepts/Intermediate/About-Quality-of-Service-Settings.html`
- `Concepts/Intermediate/About-Executors.html`
- `Concepts/Intermediate/About-Domain-ID.html`
- `Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics/Understanding-ROS2-Topics.html`
- `Tutorials/Beginner-Client-Libraries/Colcon-Tutorial.html`
- `How-To-Guides/Using-callback-groups.html`
- `p/rclpy/`、`p/rclcpp/`
QoS 預設值：https://raw.githubusercontent.com/ros2/rmw/jazzy/rmw/include/rmw/qos_profiles.h

## 搜尋（不可用 AI 摘要）
- Google：`https://www.google.com/search?q=關鍵字&udm=14`（Web 篩選，無 AI 摘要）
- DuckDuckGo：https://noai.duckduckgo.com/
- 不用 Bing（有 Copilot）。不點任何 AI 框。不開 Gmail。

## 貼上範本（每次 ≤1200 字元）
以下摘自 RP2350 datasheet §X.Y（官方文件）。晶片是 RP2350，非 RP2040；與你記憶不同時以此為準。
＜原文開始＞
<原文>
＜原文結束＞
問題：……
