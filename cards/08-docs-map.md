# 貼上卡：官方文件導航
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/08-docs-map.md、lite/08-docs-map.md（詳細版）｜最後更新 2026-11
> 這份主要給自己看（查網址、節號）；第 7 張是給模型的貼上範本。

---

【參考卡｜官方文件導航 1/7｜DMA 與 PIO 在 RP2350 datasheet 的節號】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
文件：RP2350 datasheet Release 8（2026-10-01），晶片 RP2350（Pico 2），非 RP2040。
網址：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
頁碼是頁面右下角印的頁碼，PDF 檢視器約 +1。Ctrl+F 用「節號. 節名」。
DMA（第 12.6 節，16 通道）：
- 12.6.2 Configuring channels（p.1011）
- 12.6.2.2.1 Count modes：ENDLESS、TRIGGER_SELF（p.1012）
- 12.6.2.3 Control/Status：DATA_SIZE、RING_SIZE、RING_SEL、CHAIN_TO（p.1013）
- 12.6.3.1 Aliases and triggers，Table 1253（p.1013）
- 12.6.3.2 Chaining（p.1014）
- 12.6.4.1 System DREQ table，Table 1254（p.1015）
- 12.6.5 Interrupts（p.1017）
- 12.6.8.2 CRC calculation（sniffer）、12.6.8.3 Channel abort（p.1021）
- 12.6.9.2 DMA control blocks（p.1023）
- 12.6.10 List of Registers（p.1025）
PIO（第 11 章，3 個 PIO）：
- 11.2 Programmer's model（p.793）
- 11.3 pioasm（p.799）
- 11.4 Instruction Set，11.4.1 Summary（p.802）
- 11.5.1 Side-set、11.5.3 FIFO joining、11.5.4 Autopush and Autopull、11.5.5 Clock Dividers（p.814–821）
- 11.6 Examples（p.826）
- 11.7 List of registers（p.847）

---

【參考卡｜官方文件導航 2/7｜RP2350 datasheet 其他常用節號】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
文件：RP2350 datasheet Release 8（2026-10-01），晶片 RP2350（Pico 2），非 RP2040。頁碼為頁面印的頁碼。
- 2.1.3 Atomic register access：+0x1000 XOR、+0x2000 SET、+0x3000 CLR（p.23）
- 2.1.5 Narrow IO register writes（p.24）
- 2.2 Address map，Table 8（p.27）
- 3.1.4 Hardware spinlocks（p.37）
- 3.1.5 Inter-processor FIFOs (Mailboxes)（p.38）
- 3.1.6 Doorbells（p.39）
- 3.1.7 Integer divider：RP2350 沒有 RP2040 的記憶體映射除法器
- 3.1.10 Interpolator（p.40）
- 3.2 Interrupts，Table 95 IRQ 號碼（p.80）
- 3.7.4.9 Cortex-M33 Execution timing（p.127）
- 3.8.1 Hazard3 Instruction set reference（p.227）
- 3.8.6.1 Xh3irq 中斷控制器（p.265）
- 3.8.7 Hazard3 Instruction cycle counts（p.272）
- 3.8.9 Hazard3 CSR（mcycle、mcountinhibit）（p.279）
- 4.4.1 XIP cache（p.315）
- 5.3 Launching code on Processor Core 1（p.345）
- 8.1 Clocks、8.6 PLL（p.467、527）
- 9.4 Function select，Table 677（p.540）；9.6 Pads（p.543）
- 12.1 UART、12.2 I2C、12.3 SPI、12.4 ADC、12.5 PWM（p.871、892、943、963、973）
- 12.8 System timers、12.9 Watchdog（p.1094、1105）
- Appendix D Errata（p.1351）

---

【參考卡｜官方文件導航 3/7｜RP2350 勘誤（Appendix D）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
來源：RP2350 datasheet Release 8，Appendix D Errata。晶片 RP2350，非 RP2040。在 PDF 用 Ctrl+F 搜 RP2350-E5 這種編號。
- E1（§D.9.1，A2/A3/A4）：Interpolator 的 OVERF 位元失效。對策：自己檢查 ACCUM0/ACCUM1 的 MSB，或事先算邊界。
- E2（§D.9.2，A2/A3/A4）：SIO SPINLOCK 寫入會鏡像到 +0x80。對策：用處理器原子指令；SDK 在 RP2350 預設用軟體鎖；可安全使用的硬體 spinlock：5、6、7、10、11、18–31。
- E5（§D.4.1，A2/A3/A4）：CHAIN_TO 與 ABORT 作用中的通道交互有問題。對策：abort 前先清掉被 abort 的通道和它 chain 到的通道的 CH0_CTRL_TRIG.EN。
- E8（§D.4.2，A2/A3/A4）：零長度傳輸時 CHAIN_TO 可能不觸發。對策：不要把 CHAIN_TO 和零長度傳輸一起用，用 dummy 傳輸取代。
- E9（§D.5.1，只有 A2）：Bank 0 GPIO 開啟輸入時內建 pull-down 拉不下來。對策：先關 GPIO0.IE，讀之前才暫時打開；或外接 ≤ 8.2 kΩ 下拉。
- E27（§D.3.1，A2/A3/A4）：APB 與 FASTPERI 的 bus priority 套到錯的 manager。無完整修正。
- E30（§D.2.13）：reboot() 的 delay_ms 為 0 時不重開機；傳 1。SDK 2.3.0 起自動處理。

---

【參考卡｜官方文件導航 4/7｜pico-sdk 標頭檔與 API 網址】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
pico-sdk 最新版 2.3.1（master 分支內容相同）。晶片 RP2350（Pico 2）。
標頭檔（最好的貼上來源，有函式簽名與註解）：
前綴 https://raw.githubusercontent.com/raspberrypi/pico-sdk/2.3.1/src/
- rp2_common/hardware_dma/include/hardware/dma.h
- rp2_common/hardware_pio/include/hardware/pio.h
- rp2_common/hardware_gpio/include/hardware/gpio.h
- rp2_common/hardware_irq/include/hardware/irq.h
- rp2_common/hardware_sync/include/hardware/sync.h
- rp2_common/pico_multicore/include/pico/multicore.h
- common/pico_time/include/pico/time.h
- common/pico_util/include/pico/util/queue.h
- rp2350/hardware_regs/include/hardware/regs/dreq.h（DREQ 號碼）
- rp2350/hardware_regs/include/hardware/platform_defs.h（NUM_DMA_CHANNELS 等）
路徑一定要是 rp2350，不是 rp2040。
線上 API（瀏覽器開，程式抓會被擋）：
https://www.raspberrypi.com/documentation/pico-sdk/hardware.html#group_hardware_dma
同頁錨點：group_channel_config、group_hardware_pio、group_sm_config、group_pio_instructions、group_hardware_irq
high_level.html#group_pico_multicore、#group_pico_time、#group_queue
範例：https://github.com/raspberrypi/pico-examples（dma/、pio/、multicore/）
GitHub：按 t 找檔名、y 永久連結、Raw 看純文字。不要按 Copilot 和「.」。

---

【參考卡｜官方文件導航 5/7｜ROS 2 Jazzy 文件網址】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
版本：ROS 2 Jazzy Jalisco。GitHub 分支一律 jazzy。
前綴 https://docs.ros.org/en/jazzy/
- Concepts/Intermediate/About-Quality-of-Service-Settings.html（QoS）
- Concepts/Intermediate/About-Executors.html
- Concepts/Intermediate/About-Domain-ID.html
- Tutorials/Beginner-CLI-Tools/Understanding-ROS2-Topics/Understanding-ROS2-Topics.html（ros2 topic echo / hz / info）
- Tutorials/Beginner-Client-Libraries/Colcon-Tutorial.html
- Tutorials/Beginner-Client-Libraries/Writing-A-Simple-Py-Publisher-And-Subscriber.html
- How-To-Guides/Using-callback-groups.html
- Tutorials/Demos/Intra-Process-Communication.html
- Tutorials/Intermediate/Launch/Launch-Main.html（launch）
- p/rclpy/api/qos.html、p/rclpy/api/execution_and_callbacks.html
- search.html（站內搜尋）、p/rclcpp/generated/index.html
原始碼（raw）：
- QoS 預設值：https://raw.githubusercontent.com/ros2/rmw/jazzy/rmw/include/rmw/qos_profiles.h
- rclpy executor：https://raw.githubusercontent.com/ros2/rclpy/jazzy/rclpy/rclpy/executors.py
- ros2 topic hz：https://raw.githubusercontent.com/ros2/ros2cli/jazzy/ros2topic/ros2topic/verb/hz.py
REP 2001（ROS 2 variants）：https://www.ros.org/reps/rep-2001.html

---

【參考卡｜官方文件導航 6/7｜沒有 AI 摘要的搜尋方法】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
考場禁止：其他 LLM、AI agent、Copilot、搜尋引擎的 AI 摘要、Gmail / LINE / Discord。
順序：書籤 → 站內搜尋 → GitHub 找檔 → 一般搜尋。
- Google 網址加 udm=14（Web 篩選，不顯示 AI 摘要）：
  https://www.google.com/search?q=rp2350+DREQ&udm=14
  Google 沒保證 udm=14 永久有效；若還是看到 AI 摘要，不要點、不要看，往下捲。不要點「AI 模式」。
- DuckDuckGo：用 https://noai.duckduckgo.com/ ，或 Search Settings → AI Features → Search Assist 選 Never。不要點 Duck.ai。
- Bing 會顯示 Copilot 回答：不要用。
- GitHub：搜尋框輸入 repo:raspberrypi/pico-sdk 關鍵字（可能要登入，允許登入）。不要按 Copilot、不要按「.」開 github.dev。
- site: 查詢（都加 &udm=14）：
  site:datasheets.raspberrypi.com rp2350
  site:github.com/raspberrypi/pico-sdk sm_config_set_out_shift
  site:docs.ros.org/en/jazzy executor
  site:man7.org clock_gettime

---

【參考卡｜官方文件導航 7/7｜貼原文給模型的範本】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
規則：
- 一次只貼一段原文，約 1200 字元以內。
- 一定附出處：文件名 + 節號 + 節名，或檔案路徑 + 函式名。
- PDF 複製的表格會被打散：只留需要的幾列，改寫成「欄位 = 值」一行一個；刪掉頁首頁尾與頁碼。
- 標頭檔：從函式上方的註解開頭，選到宣告結尾，只貼一個函式。
- 問題寫在原文後面，一次只問一件事。
範本 A（datasheet）：
以下摘自 RP2350 datasheet §12.6.4.1 System DREQ table（官方文件，Release 8，2026-10-01）。晶片是 RP2350（Raspberry Pi Pico 2），不是 RP2040。若與你的記憶不同，以這段為準。表格是從 PDF 複製，排版可能被打散。
＜原文開始＞
（貼原文）
＜原文結束＞
問題：（一句話）
範本 B（標頭檔）：
以下摘自 pico-sdk 2.3.1 原始碼 src/rp2_common/hardware_pio/include/hardware/pio.h（官方標頭檔，含註解）。
＜原文開始＞
（貼函式註解與宣告）
＜原文結束＞
問題：（一句話，指定回答格式，例如「只列參數與一行說明」）
