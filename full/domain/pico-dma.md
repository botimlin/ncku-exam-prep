# RP2350 DMA 與 pico-sdk `hardware_dma` 完整參考

> 用途：在 RP2350（Raspberry Pi Pico 2）上用 DMA 搬資料、與 PIO/週邊配合、用 DMA 取代 CPU 迴圈以優化效能；並對照考前練習 `section2-3/transfer-engine` 的假想引擎 API。
> 適用版本：RP2350（A2/A3/A4 stepping）；pico-sdk 2.x。API 簽名以 pico-sdk master（= 2.2.0 以後）為準，2.1.x 的差異另行標註。Arm（Cortex-M33）與 RISC-V（Hazard3）核心使用同一套 `hardware_dma` API。
> 來源（實際查閱）：
> - pico-sdk 原始碼 `src/rp2_common/hardware_dma/include/hardware/dma.h`、`src/rp2_common/hardware_dma/dma.c`（master、tag 2.2.0、tag 2.1.1）：https://github.com/raspberrypi/pico-sdk
> - pico-sdk `src/rp2350/hardware_regs/include/hardware/{platform_defs.h, regs/dma.h, regs/dreq.h, regs/intctrl.h, regs/busctrl.h}`、`src/rp2350/hardware_structs/include/hardware/structs/{dma.h, dma_debug.h, busctrl.h, pio.h}`、`src/rp2_common/hardware_pio/include/hardware/pio.h`、`src/rp2_common/hardware_irq/include/hardware/irq.h`
> - RP2350 Datasheet（2026-10-01 版）第 2.1 節 Bus fabric、2.2.3 SRAM、4.4 XIP、12.6 DMA、附錄 D.3/D.4 Errata：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
> - pico-examples `dma/hello_dma`、`dma/control_blocks`、`dma/channel_irq`、`dma/sniff_crc`：https://github.com/raspberrypi/pico-examples/tree/master/dma
> 最後更新：2026-11
>
> 標記：⚠️未驗證 = 沒有在官方來源找到明確敘述，使用前請實測或查證。

---

## 0. 一分鐘總覽（先讀這段）

| 項目 | RP2350 | RP2040（對照） |
|---|---|---|
| DMA 通道數 `NUM_DMA_CHANNELS` | **16** | 12 |
| DMA 系統 IRQ 數 `NUM_DMA_IRQS` | **4**（`DMA_IRQ_0..3`，IRQ 號 10..13） | 2（`DMA_IRQ_0/1`，IRQ 號 11/12） |
| 節拍計時器 `NUM_DMA_TIMERS` | 4 | 4 |
| `TRANS_COUNT` | 低 28 bit = 次數；高 4 bit = `MODE`（0=NORMAL、1=TRIGGER_SELF、0xF=ENDLESS） | 32 bit 全是次數 |
| 位址遞減 / 跳一格遞增 | 有（`INCR_READ_REV` / `INCR_WRITE_REV`） | 無 |
| 安全性 / MPU | 有 `SECCFG_CHx`、DMA MPU（預設所有通道為最高等級 SP，SDK 預設即可用） | 無 |
| 主要 errata | RP2350-E5（abort 與 CHAIN_TO）、RP2350-E8（零長度傳輸的 CHAIN_TO） | RP2040-E12/E13 |

核心心智模型：DMA = 「你描述工作，硬體去搬」。每個通道 4 個暫存器：

```
READ_ADDR    下一個要讀的位址（會自動前進）
WRITE_ADDR   下一個要寫的位址（會自動前進）
TRANS_COUNT  剩幾「筆傳輸」（不是位元組！）；寫入值 = 下次觸發時重新載入的長度
CTRL         資料寬度、是否遞增、DREQ、CHAIN_TO、ring、bswap、IRQ_QUIET、EN、BUSY、錯誤旗標
```

固定節奏（與考前練習 transfer engine 相同）：

```
claim → get_default_config + set_xxx → configure(…, trigger=false/true) → start → busy/wait（或 IRQ）→ 使用結果 → cleanup + unclaim
```

整顆 DMA 每個 clk_sys 週期最多一次讀 + 一次寫（每次最多 32 bit）。多通道同時跑時以 round-robin 平分這個頻寬——**把一份 memcpy 拆給多個通道不會更快**。

---

## 1. 硬體架構（RP2350 datasheet §12.6）

### 1.1 結構

- 兩個 AHB5 manager port：Read manager、Write manager；中間是 address generator 與 read/write address FIFO、transfer data FIFO。
- 讀與寫成對排程（matched pairs）；讀寬度 = 寫寬度（同一個 `DATA_SIZE`）。
- 窄寫入（8/16 bit）會做 byte-lane replication：byte 資料出現在資料匯流排的 4 個 byte lane。寫 SRAM 沒影響（記憶體依 byte strobe 只改該 byte）；但**寫大多數 IO 暫存器時，IO 暫存器會把整個 32 bit 都吃進去**（datasheet §2.1.5）。datasheet 提到 RP2350 可用週邊位址 +0x4000（設 address bit 14）讓無效 byte lane 驅動為 0，例如 8-bit DMA 到 PWM 時。
- DMA **無法存取 SIO**（包括 SIO 的 GPIO 暫存器）。要用 DMA 驅動 GPIO，官方建議：DMA → PIO TX FIFO → PIO 程式輸出到腳位。

### 1.2 三種典型情境

| 情境 | 讀端 | 寫端 | 節拍（TREQ） |
|---|---|---|---|
| 記憶體 → 週邊 | 陣列（遞增） | 週邊 FIFO（不遞增） | 週邊 TX DREQ |
| 週邊 → 記憶體 | 週邊 FIFO（不遞增） | 陣列（遞增） | 週邊 RX DREQ |
| 記憶體 → 記憶體 | 陣列（遞增或不遞增=填值） | 陣列（遞增） | `DREQ_FORCE`（0x3F，全速）或 DMA timer |

### 1.3 觸發（trigger）的方式

通道被觸發後 `CTRL.BUSY=1`，直到 transfer count 歸零（或被 abort）。觸發來源：

1. 寫入通道的 **trigger 暫存器**（每個 alias 群組的最後一格，見下表）。
2. 另一個通道完成，且其 `CHAIN_TO` 指向本通道。
3. 寫 `MULTI_CHAN_TRIGGER`（`dma_start_channel_mask()`），可同時啟動多個通道。
4. RP2350 才有：`TRANS_COUNT.MODE = TRIGGER_SELF` 時完成後自動再觸發自己。

觸發**不會生效**的情況：通道 `EN=0`（若 trigger 暫存器就是 CTRL，則看剛寫入的 EN 值）；通道已 BUSY（觸發被忽略）；寫入值為 0（null trigger）；存取者安全等級低於通道等級。

### 1.4 暫存器別名（alias）表

每個通道 4 個實體暫存器，以 4 種順序各出現一次；每組 +0xC 是 trigger。

| Offset | +0x0 | +0x4 | +0x8 | +0xC（Trigger） | SDK struct 欄位（+0xC） |
|---|---|---|---|---|---|
| 0x00 Alias 0 | READ_ADDR | WRITE_ADDR | TRANS_COUNT | CTRL_TRIG | `ctrl_trig` |
| 0x10 Alias 1 | CTRL | READ_ADDR | WRITE_ADDR | TRANS_COUNT_TRIG | `al1_transfer_count_trig` |
| 0x20 Alias 2 | CTRL | TRANS_COUNT | READ_ADDR | WRITE_ADDR_TRIG | `al2_write_addr_trig` |
| 0x30 Alias 3 | CTRL | WRITE_ADDR | TRANS_COUNT | READ_ADDR_TRIG | `al3_read_addr_trig` |

SDK struct `dma_channel_hw_t` 的欄位依序：`read_addr, write_addr, transfer_count, ctrl_trig, al1_ctrl, al1_read_addr, al1_write_addr, al1_transfer_count_trig, al2_ctrl, al2_transfer_count, al2_read_addr, al2_write_addr_trig, al3_ctrl, al3_write_addr, al3_transfer_count, al3_read_addr_trig`。存取：`dma_hw->ch[ch].xxx`。

用途：
- 只寫 `READ_ADDR_TRIG` 就能重新啟動「固定長度、送往同一週邊」的傳輸（gather）。
- 只寫 `WRITE_ADDR_TRIG` 就能重新啟動「從週邊收到固定長度 buffer」（scatter）。
- 控制區塊（control block）常用的二字組合：`(TRANS_COUNT, READ_ADDR_TRIG)` = Alias 3 的 +0x8/+0xC；`(WRITE_ADDR, TRANS_COUNT_TRIG)` = Alias 1 的 +0x8/+0xC；`(READ_ADDR, WRITE_ADDR_TRIG)` = Alias 2 的 +0x8/+0xC。

### 1.5 `TRANS_COUNT` 語意（重要）

- **單位是「傳輸筆數」**。總位元組 = `TRANS_COUNT × (1/2/4)`（依 `DATA_SIZE`）。
- 讀：目前序列剩餘筆數（即時更新）。寫（非 trigger alias）：設定 **RELOAD 值**，下次觸發時才複製到計數器。同一 RELOAD 值可被重複觸發使用（例如被 chain 時每次跑一樣長）。寫 trigger alias（`al1_transfer_count_trig`）：立即以此值開始。
- RELOAD 值可從 `dma_debug_hw->ch[ch].dbg_tcr` 讀到。
- RP2350：最多 2^28−1 筆（`0x0FFFFFFF`）。高 4 bit `MODE`：

| MODE | 名稱 | 行為 |
|---|---|---|
| 0x0 | NORMAL | 遞減到 0 後停止，觸發 CHAIN_TO、發 IRQ（同 RP2040） |
| 0x1 | TRIGGER_SELF | 同 NORMAL，但完成後立刻再觸發自己（重新載入 count、從目前位址繼續），仍會發 IRQ（若非 IRQ_QUIET）與執行 CHAIN_TO。用途：ring buffer 串流 + 週期性中斷 |
| 0xF | ENDLESS | count 不遞減，永遠跑，不觸發其他通道也不發 IRQ，直到 abort。以 MODE=0xF 且 count=0 觸發會立即停止 |
| 其他 | 保留 | 行為未定義 |

- 陷阱：在 RP2350 上若直接傳一個 ≥ 2^28 的數字，高位會被當成 MODE。SDK 2.2.0+ 建議用 `dma_encode_transfer_count(n)` 包裝（啟用參數檢查時會 assert）。

### 1.6 `CTRL_TRIG` 欄位（RP2350 位元配置）

| Bit | 欄位 | 說明 |
|---|---|---|
| 31 | AHB_ERROR | READ_ERROR \| WRITE_ERROR（唯讀） |
| 30 | READ_ERROR | 讀匯流排錯誤；寫 1 清除 |
| 29 | WRITE_ERROR | 寫匯流排錯誤；寫 1 清除 |
| 26 | BUSY | 序列進行中為 1。清 EN 只會暫停，BUSY 維持 1 |
| 25 | SNIFF_EN | 本通道資料是否給 sniffer（CRC/sum） |
| 24 | BSWAP | 位元組反轉（16-bit 交換兩 byte；32-bit 反轉 4 byte；8-bit 無作用） |
| 23 | IRQ_QUIET | 正常完成不發 IRQ，只在收到 null trigger 時發 |
| 22:17 | TREQ_SEL | 0x00–0x36 DREQ；0x3B–0x3E DMA timer 0–3；0x3F 永久請求（不節流） |
| 16:13 | CHAIN_TO | 完成後觸發的通道；設成自己 = 不 chain。**reset 值為 0**（直接寫暫存器時，通道 1 以上會預設 chain 到通道 0；用 SDK default config 則已設成自己） |
| 12 | RING_SEL | 0 = ring 作用於讀位址；1 = 寫位址 |
| 11:8 | RING_SIZE | 0 = 不繞；n = 只有低 n bit 變化，在 (1<<n) byte 邊界繞回（2–32768 bytes） |
| 7 | INCR_WRITE_REV | RP2350 新增 |
| 6 | INCR_WRITE | 寫位址是否前進 |
| 5 | INCR_READ_REV | RP2350 新增 |
| 4 | INCR_READ | 讀位址是否前進 |
| 3:2 | DATA_SIZE | 0=byte、1=halfword、2=word |
| 1 | HIGH_PRIORITY | DMA 內部排程優先（不改變匯流排優先權） |
| 0 | EN | 通道致能 |

RP2350 位址更新組合：

| INCR | INCR_REV | 每筆位址變化 | SDK `dma_address_update_type_t`（2.2.0+） |
|---|---|---|---|
| 0 | 0 | 不變 | `DMA_ADDRESS_UPDATE_NONE` (0) |
| 1 | 0 | +size | `DMA_ADDRESS_UPDATE_INCREMENT` (1) |
| 0 | 1 | +2×size（跳過交錯的一格） | `DMA_ADDRESS_UPDATE_INCREMENT_BY_TWO` (2，RP2350 only) |
| 1 | 1 | −size（遞減） | `DMA_ADDRESS_UPDATE_DECREMENT` (3，RP2350 only) |

### 1.7 DREQ / 節拍（§12.6.4）

- `TREQ_SEL` 選擇週邊 DREQ、DMA timer、或 `DREQ_FORCE`（0x3F = 全速）。
- RP2350 使用 **credit-based DREQ**：每通道一個 6-bit 飽和計數器，週邊每發一個 dreq 脈衝 +1，DMA 發出一筆傳輸 −1。效果是在途傳輸數不超過週邊 FIFO 的空間/資料量，可達每 clock 一個 word 而不溢位。
- 兩條硬規則（datasheet 明文）：
  1. **DMA 正在服務某個 FIFO 時，CPU 不可同時存取該 FIFO**（會失去同步、資料錯亂/遺失）。
  2. **不可讓多個通道接同一個 DREQ**。
- RP2350 DREQ 編號（`hardware/regs/dreq.h`，RP2040 編號不同，永遠用巨集或 `pio_get_dreq()`）：

| DREQ | 巨集 | DREQ | 巨集 |
|---|---|---|---|
| 0–3 | `DREQ_PIO0_TX0..3` | 4–7 | `DREQ_PIO0_RX0..3` |
| 8–15 | `DREQ_PIO1_TX0..3 / RX0..3` | 16–23 | `DREQ_PIO2_TX0..3 / RX0..3` |
| 24/25 | `DREQ_SPI0_TX/RX` | 26/27 | `DREQ_SPI1_TX/RX` |
| 28/29 | `DREQ_UART0_TX/RX` | 30/31 | `DREQ_UART1_TX/RX` |
| 32–43 | `DREQ_PWM_WRAP0..11` | 44–47 | `DREQ_I2C0_TX/RX, DREQ_I2C1_TX/RX` |
| 48 | `DREQ_ADC` | 49 | `DREQ_XIP_STREAM` |
| 50/51 | `DREQ_XIP_QMITX/QMIRX` | 52 | `DREQ_HSTX` |
| 53 | `DREQ_CORESIGHT` | 54 | `DREQ_SHA256` |
| 59–62 | `DREQ_DMA_TIMER0..3` | 63 | `DREQ_FORCE` |

### 1.8 Pacing timer（§12.6.8.1）

- 4 個分數計時器 `TIMER0..3`，每個 `X`（bit 31:16）/ `Y`（bit 15:0），產生 TREQ 的頻率 = `clk_sys × X / Y`，最多每 clk_sys 一次（X ≤ Y）。
- 例：clk_sys = 150 MHz，X/Y = 1/150 → 1 MHz。Y 最大 65535 → 最低約 clk_sys/65535（150 MHz 時約 2.29 kHz）。

### 1.9 中斷（§12.6.5）

通道在三種情況發出中斷請求：(1) 每次傳輸序列完成（未設 IRQ_QUIET）；(2) 收到 null trigger（設了 IRQ_QUIET）；(3) 讀/寫匯流排錯誤（一定會）。

| 暫存器 | 意義 |
|---|---|
| `INTR` | 原始狀態（不看遮罩），寫 1 清除 |
| `INTE0..3` | 把通道 n 的中斷送往系統 IRQ `DMA_IRQ_0..3` |
| `INTF0..3` | 強制觸發（除錯用） |
| `INTS0..3` | 遮罩後狀態（真正造成 IRQ 的通道）；**寫 1 清除** |

SDK struct：`dma_hw->inte0 / ints0 …` 或 `dma_hw->irq_ctrl[i].inte / .ints`。四條 IRQ 可給不同 NVIC 優先權、分給不同核心、或不同安全域。

### 1.10 Abort（§12.6.8.3 + errata RP2350-E5）

- `CHAN_ABORT` 寫 bitmap → 清計數、強制停止；在途傳輸無法撤回，`BUSY` 會等到它們完成才降為 0。**BUSY 降下前不可重新啟動通道**。RP2350 可輪詢 `CHAN_ABORT` 直到為 0。
- **RP2350-E5**：abort 可能讓 CHAIN_TO 觸發，且通道在 abort 結束前一個 cycle 可能被重新觸發（count=0，下一 cycle 隨即「完成」並觸發 IRQ/CHAIN_TO）。官方程序：
  1. 對要 abort 的通道（以及它 chain 到的通道）**清 EN 並關閉 CHAIN_TO**；
  2. 寫 `CHAN_ABORT`；
  3. 輪詢 `CHAN_ABORT` 直到那些 bit 清為 0。
  - 有 chain 關係時，建議同時 abort 整條鏈。
- SDK 的 `dma_channel_cleanup(ch)` 會：CHAIN_TO 設回自己 + EN=0 → 關掉所有 DMA IRQ 的該通道 enable → `dma_channel_abort()` → 清 `INTR`。**要「停掉並歸還」通道時優先用它。**

### 1.11 匯流排錯誤（§12.6.7）

- 原因：DMA MPU 禁止、位址未對應任何裝置（例如 SIO）、ACCESSCTRL 禁止、APB 逾時（> 65535 cycles，如 ADC 時脈停止時存取）等。
- 反應：該通道停止、設 READ_ERROR/WRITE_ERROR、一定發中斷請求、**不會 CHAIN_TO**；其他通道不受影響。錯誤旗標未清除前通道拒絕重啟。
- 復原：先等 BUSY=0，再對錯誤旗標寫 1 清除（兩個都設了就兩個都清）。`READ_ADDR`/`WRITE_ADDR` 會停在出錯位址附近（略為超過）。

### 1.12 Errata RP2350-E8

- 以 transfer count = 0 觸發的通道，CHAIN_TO **可能不觸發**（⚠️未查證）。對策：不要讓 CHAIN_TO 遇到零長度傳輸；control block 清單中間不要放長度 0 的區塊，改用 dummy 傳輸。（清單結尾的「全 0 null trigger」是另一回事：null trigger 根本不會啟動通道。）

### 1.13 匯流排、頻寬與優先權（§2.1、§2.2.3）

- AHB5 crossbar：6 個 manager（core0 I/D、core1 I/D、DMA R、DMA W），每 cycle 最多 6 筆同時傳輸，32-bit 資料路徑；150 MHz 時理論總頻寬 3.6 GB/s。
- 單一 DMA：每 cycle 1 讀 + 1 寫，32-bit → 150 MHz 時理論上限約 600 MB/s 的搬運量（實際受 bank 衝突、週邊速度影響）。
- SRAM：SRAM0–3（`0x20000000`–`0x2003FFFF`）與 SRAM4–7（`0x20040000`–`0x2007FFFF`）各以位址 bit 3:2 做 word striping；SRAM8（`0x20080000`）、SRAM9（`0x20081000`）各 4 kB，不 striping。不同 bank 的存取可同時進行，同一 bank 同一 cycle 只能服務一個 manager。
- APB 週邊：讀至少 3 cycles、寫至少 4 cycles，比 AHB 慢；UART/SPI/I2C/PWM/ADC 在 APB 上，PIO/USB/DMA 控制暫存器/HSTX FIFO 在 fast AHB 週邊 port 上。
- 匯流排優先權：`busctrl_hw->priority`（`#include "hardware/structs/busctrl.h"`），bit `BUSCTRL_BUS_PRIORITY_DMA_W_BITS`、`BUSCTRL_BUS_PRIORITY_DMA_R_BITS`、`PROC0`、`PROC1`。只在多個 manager 同一 cycle 搶同一 subordinate 時才有作用。
  - **RP2350-E27**：在 FASTPERI 與 APB 仲裁器上這些 bit 接錯（PROC0→DMA 寫、PROC1→core0、DMA_R→core1、DMA_W→DMA 讀）；ROM/SRAM/XIP 仲裁器正確。官方建議另行用 buffer 擺放（例如 SRAM8/9 當處理器私有記憶體、分散到兩個 striped 區域）降低衝突。
- `CTRL.HIGH_PRIORITY`（`channel_config_set_high_priority`）只影響 DMA 內部各通道的排程順序；DMA 未飽和時低優先通道不會掉速。

### 1.14 Cache 與一致性

- RP2350 唯一的 cache 是 **XIP cache**（16 kB、2-way，位於 XIP 子系統內）。datasheet：它只參與 QSPI 記憶體介面的存取，**除非在燒寫 flash，軟體不需考慮 cache 一致性**；每個系統位址只由一個 cache controller 或不經 cache 服務。
- 因此 DMA 讀寫 SRAM **不需要 cache flush/invalidate**。但仍需防止**編譯器**重排或把 buffer 留在暫存器：
  - `dma_channel_wait_for_finish_blocking()` 內含 `__compiler_memory_barrier()`。
  - 自己輪詢 `dma_channel_is_busy()` 或在 IRQ 中設 flag 時，flag 用 `volatile`，並在讀 buffer 前加 `__compiler_memory_barrier()`（或 `__dmb()`，見 `hardware/sync.h`）。
- XIP 位址窗：`0x10……` cached、`0x14……` uncached、`0x18……` cache maintenance、`0x1C……` uncached + untranslated。DMA 從 flash 讀常數表可以，但慢（受 QSPI 速度限制）；大量讀 flash 可用 XIP streaming（`xip_ctrl_hw->stream_addr / stream_ctr` + `DREQ_XIP_STREAM`，datasheet §4.4.3）。若程式碼也在 XIP 上執行，DMA 讀 flash 會跟取指令搶 QSPI。

### 1.15 對齊

- `READ_ADDR`/`WRITE_ADDR` 必須對齊 `DATA_SIZE`（32-bit → 4 的倍數，16-bit → 2 的倍數）。**DMA 不檢查對齊**；未對齊的結果「未定義」（datasheet），不會像考前練習的引擎那樣報錯。
- 起始位址對齊後，整個序列都會保持對齊。
- Ring buffer：buffer 必須對齊到 `1 << size_bits` bytes（例如 `__attribute__((aligned(1024)))`）。

---

## 2. pico-sdk API 參考（`#include "hardware/dma.h"`，CMake 連結 `hardware_dma`）

### 2.1 型別與版本差異

| 項目 | 說明 |
|---|---|
| `dma_channel_config` | 設定物件（內含 `uint32_t ctrl`）。**所有 2.x 版本都可用**，建議寫這個 |
| `dma_channel_config_t` | 2.2.0+ 的新名字；`dma_channel_config` 是它的相容 typedef |
| `enum dma_channel_transfer_size` / `dma_channel_transfer_size_t` | `DMA_SIZE_8 = 0`、`DMA_SIZE_16 = 1`、`DMA_SIZE_32 = 2`（是 log2，**不是位元組數**） |
| `dma_address_update_type_t` | 2.2.0+；RP2350 才有 `INCREMENT_BY_TWO`、`DECREMENT` |
| `dma_channel_set_transfer_count()` | 2.2.0+ 新名字；舊名 `dma_channel_set_trans_count()` 仍保留 |
| `dma_encode_*()` | 2.2.0+；2.1.x 沒有，需自行組 MODE bit |
| 版本判斷 | `#include "pico/version.h"` → `PICO_SDK_VERSION_MAJOR / MINOR / STRING` |

### 2.2 通道 claim

```c
void dma_channel_claim(uint channel);              // 已被 claim 會 panic
void dma_claim_mask(uint32_t channel_mask);
void dma_channel_unclaim(uint channel);
void dma_unclaim_mask(uint32_t channel_mask);
int  dma_claim_unused_channel(bool required);      // required=true：沒有就 panic；false：回傳 -1
bool dma_channel_is_claimed(uint channel);
void dma_channel_cleanup(uint channel);            // 停用 chain/EN、關 IRQ、abort、清 INTR
```

claim 只是軟體層的合作式標記（`dma.c` 中的 bitmap），不會改硬體。

### 2.3 設定物件（`channel_config_*`，全部是 `static inline`）

```c
dma_channel_config dma_channel_get_default_config(uint channel);
dma_channel_config dma_get_channel_config(uint channel);          // 從硬體讀回目前 CTRL
uint32_t channel_config_get_ctrl_value(const dma_channel_config *config);

void channel_config_set_transfer_data_size(dma_channel_config *c, enum dma_channel_transfer_size size);
void channel_config_set_read_increment(dma_channel_config *c, bool incr);
void channel_config_set_write_increment(dma_channel_config *c, bool incr);
void channel_config_set_read_address_update_type(dma_channel_config *c, dma_address_update_type_t t);  // 2.2.0+
void channel_config_set_write_address_update_type(dma_channel_config *c, dma_address_update_type_t t); // 2.2.0+
void channel_config_set_dreq(dma_channel_config *c, uint dreq);
void channel_config_set_chain_to(dma_channel_config *c, uint chain_to);   // 設成自己 = 不 chain
void channel_config_set_ring(dma_channel_config *c, bool write, uint size_bits); // write=true 作用於寫位址；size_bits 0=關
void channel_config_set_bswap(dma_channel_config *c, bool bswap);
void channel_config_set_irq_quiet(dma_channel_config *c, bool irq_quiet);
void channel_config_set_high_priority(dma_channel_config *c, bool high_priority);
void channel_config_set_enable(dma_channel_config *c, bool enable);
void channel_config_set_sniff_enable(dma_channel_config *c, bool sniff_enable);
```

`dma_channel_get_default_config(ch)` 的預設值（必背）：

| 設定 | 預設 |
|---|---|
| Read increment | **true** |
| Write increment | **false** |
| DREQ | `DREQ_FORCE`（全速） |
| Chain to | 自己（= 不 chain） |
| Data size | `DMA_SIZE_32` |
| Ring | 關（write=false, size=0） |
| Byte swap / Quiet IRQ / High priority / Sniff | false |
| Enable | true |

=> 記憶體到記憶體 memcpy **一定要**再 `channel_config_set_write_increment(&c, true)`。

### 2.4 寫入硬體與啟動

```c
// 注意參數順序：先 write_addr（目的地），再 read_addr（來源）！
void dma_channel_configure(uint channel, const dma_channel_config *config,
                           volatile void *write_addr, const volatile void *read_addr,
                           uint32_t encoded_transfer_count, bool trigger);
// 2.1.x 版最後兩參數為 (uint transfer_count, bool trigger)，用法相同

void dma_channel_set_config(uint channel, const dma_channel_config *config, bool trigger);
void dma_channel_set_read_addr(uint channel, const volatile void *read_addr, bool trigger);
void dma_channel_set_write_addr(uint channel, volatile void *write_addr, bool trigger);
void dma_channel_set_transfer_count(uint channel, uint32_t encoded_transfer_count, bool trigger); // 2.2.0+
void dma_channel_set_trans_count(uint channel, uint32_t trans_count, bool trigger);              // 舊名，仍可用

void dma_channel_transfer_from_buffer_now(uint channel, const volatile void *read_addr, uint32_t encoded_transfer_count);
void dma_channel_transfer_to_buffer_now(uint channel, volatile void *write_addr, uint32_t encoded_transfer_count);

void dma_channel_start(uint channel);            // = dma_start_channel_mask(1u << channel)
void dma_start_channel_mask(uint32_t chan_mask); // 寫 MULTI_CHAN_TRIGGER
```

實作細節（影響行為）：
- `dma_channel_configure` 依序寫 read_addr、write_addr、transfer_count（皆非 trigger alias），最後寫 CTRL：`trigger=false` 寫 `al1_ctrl`（不觸發），`trigger=true` 寫 `ctrl_trig`（觸發）。
- `*_set_*(…, true)` 分別使用 `al3_read_addr_trig`、`al2_write_addr_trig`、`al1_transfer_count_trig`。
- `transfer_from_buffer_now` / `to_buffer_now`：寫位址後寫 `al1_transfer_count_trig` 啟動，適合在 ISR 中快速重啟。

RP2350 transfer count 編碼（2.2.0+）：

```c
uint32_t dma_encode_transfer_count(uint transfer_count);                 // 0 .. 2^28-1，MODE=NORMAL
uint32_t dma_encode_transfer_count_with_self_trigger(uint transfer_count); // MODE=TRIGGER_SELF（RP2040 上 panic）
uint32_t dma_encode_endless_transfer_count(void);                         // 回傳 0xFFFFFFFF（MODE=ENDLESS）（RP2040 上 panic）
```

2.1.x 沒有這些函式時，可手動：`(1u << 28) | n`（TRIGGER_SELF）、`0xFFFFFFFFu`（ENDLESS）。巨集 `DMA_CH0_TRANS_COUNT_MODE_LSB`=28、`DMA_CH0_TRANS_COUNT_MODE_VALUE_TRIGGER_SELF`=1、`..._ENDLESS`=0xF 在 `hardware/regs/dma.h`。

### 2.5 狀態、等待、停止

```c
bool dma_channel_is_busy(uint channel);                    // 讀 CTRL.BUSY
void dma_channel_wait_for_finish_blocking(uint channel);   // 忙等 + __compiler_memory_barrier()
void dma_channel_abort(uint channel);                      // 寫 CHAN_ABORT，輪詢 BUSY 直到 0
```

`dma_channel_abort` 在 RP2350 上**不會**幫你處理 E5（需先清 EN/CHAIN_TO）；`dma_channel_cleanup` 會。RP2040 上 abort 可能產生假的完成中斷（RP2040-E13），SDK 文件建議 abort 前後關/清 IRQ。

### 2.6 中斷 API

```c
// IRQ 0 / 1 專用版本
void dma_channel_set_irq0_enabled(uint channel, bool enabled);
void dma_channel_set_irq1_enabled(uint channel, bool enabled);
void dma_set_irq0_channel_mask_enabled(uint32_t channel_mask, bool enabled);
void dma_set_irq1_channel_mask_enabled(uint32_t channel_mask, bool enabled);
bool dma_channel_get_irq0_status(uint channel);   // 讀 INTS0
bool dma_channel_get_irq1_status(uint channel);
void dma_channel_acknowledge_irq0(uint channel);  // 寫 INTS0 = 1<<ch
void dma_channel_acknowledge_irq1(uint channel);

// 通用版本（irq_index 0..NUM_DMA_IRQS-1；RP2350 為 0..3）——要用 DMA_IRQ_2/3 只能用這組
void dma_irqn_set_channel_enabled(uint irq_index, uint channel, bool enabled);
void dma_irqn_set_channel_mask_enabled(uint irq_index, uint32_t channel_mask, bool enabled);
bool dma_irqn_get_channel_status(uint irq_index, uint channel);
void dma_irqn_acknowledge_channel(uint irq_index, uint channel);
int  dma_get_irq_num(uint irq_index);             // 回傳 DMA_IRQ_<n> 的 IRQ 號
// 巨集：DMA_IRQ_NUM(n) == DMA_IRQ_0 + n
```

系統 IRQ 端（`#include "hardware/irq.h"`）：

```c
typedef void (*irq_handler_t)(void);
void irq_set_exclusive_handler(uint num, irq_handler_t handler);   // 該 IRQ 已有 handler 會出錯
void irq_add_shared_handler(uint num, irq_handler_t handler, uint8_t order_priority); // 常用 PICO_SHARED_IRQ_HANDLER_DEFAULT_ORDER_PRIORITY
void irq_remove_handler(uint num, irq_handler_t handler);
void irq_set_enabled(uint num, bool enabled);
```

注意 IRQ 號：RP2350 `DMA_IRQ_0 = 10`；RP2040 `DMA_IRQ_0 = 11`。**用巨集，別寫數字**。`hardware/irq.h` 註明所有 IRQ API 只作用於「呼叫它的那顆核心」（每核各有一個 NVIC），所以 `irq_set_enabled(DMA_IRQ_n, true)` 要在負責處理該中斷的核心上呼叫；不要在兩顆核心都 enable 同一條 DMA IRQ（兩邊 handler 會互搶）。預設兩核共用同一張 vector table。

### 2.7 DMA timer API

```c
void dma_timer_claim(uint timer);
void dma_timer_unclaim(uint timer);
int  dma_claim_unused_timer(bool required);
bool dma_timer_is_claimed(uint timer);
void dma_timer_set_fraction(uint timer, uint16_t numerator, uint16_t denominator); // 速率 = clk_sys*num/den，num <= den
uint dma_get_timer_dreq(uint timer_num);   // 回傳 DREQ_DMA_TIMER0 + n（給 channel_config_set_dreq）
```

### 2.8 Sniffer（CRC / checksum）API

```c
void dma_sniffer_enable(uint channel, uint mode, bool force_channel_enable);
void dma_sniffer_disable(void);
void dma_sniffer_set_byte_swap_enabled(bool swap);
void dma_sniffer_set_output_invert_enabled(bool invert);
void dma_sniffer_set_output_reverse_enabled(bool reverse);
void dma_sniffer_set_data_accumulator(uint32_t seed_value);
uint32_t dma_sniffer_get_data_accumulator(void);
```

| mode | 巨集（`hardware/regs/dma.h`） | 計算 |
|---|---|---|
| 0x0 | `DMA_SNIFF_CTRL_CALC_VALUE_CRC32` | CRC-32（IEEE 802.3 多項式） |
| 0x1 | `DMA_SNIFF_CTRL_CALC_VALUE_CRC32R` | CRC-32，資料 bit 反轉 |
| 0x2 | `DMA_SNIFF_CTRL_CALC_VALUE_CRC16` | CRC-16-CCITT |
| 0x3 | `DMA_SNIFF_CTRL_CALC_VALUE_CRC16R` | CRC-16-CCITT，資料 bit 反轉 |
| 0xE | `DMA_SNIFF_CTRL_CALC_VALUE_EVEN` | XOR 歸約（1 的總數為奇數時 = 1） |
| 0xF | `DMA_SNIFF_CTRL_CALC_VALUE_SUM` | 32-bit 累加和 |

- 一次只能 sniff 一個通道（`SNIFF_CTRL.DMACH`）；該通道 CTRL 的 `SNIFF_EN` 也要開。
- sniffer 在 channel bswap 的下游：channel bswap 與 sniffer bswap 同時開，對 sniffer 來說效果互相抵消。
- output invert / reverse 只改「讀出時的呈現」，不改計算。
- **陷阱**：`dma_sniffer_enable(ch, mode, true)` 會直接把硬體 CTRL 的 SNIFF_EN 設起來，但之後的 `dma_channel_configure()` 會用 config 整個覆寫 CTRL。所以 config 裡也要 `channel_config_set_sniff_enable(&c, true)`（官方範例就是兩者都做）。

### 2.9 PIO 相關（`#include "hardware/pio.h"`）

```c
uint pio_get_dreq(PIO pio, uint sm, bool is_tx);   // is_tx=true → TX DREQ
// FIFO 位址（hardware/structs/pio.h）：pio->txf[sm]（io_wo_32）、pio->rxf[sm]（io_ro_32）
```

### 2.10 除錯輔助

```c
void print_dma_ctrl(dma_channel_hw_t *channel);      // 只在未定義 NDEBUG 時存在；印 CTRL 各欄位
dma_hw->ch[ch].read_addr / write_addr / transfer_count / ctrl_trig   // 即時值
dma_debug_hw->ch[ch].dbg_tcr      // TRANS_COUNT 的 reload 值（#include "hardware/structs/dma_debug.h"；hardware/structs/dma.h 已含入）
dma_debug_hw->ch[ch].dbg_ctdreq   // DREQ 計數器；寫任意值會清除並重新握手
dma_hw->intr                       // 原始中斷狀態
dma_hw->n_channels                 // 硬體通道數（應為 16）
dma_hw->fifo_levels                // 內部 FIFO 水位（除錯）
```

---

## 3. 對照：考前練習 transfer engine → 真正的 pico-sdk

考前練習 `section2-3/transfer-engine/engine.h` 刻意模仿 DMA。下表把它的每個概念對應到實機 API：

| 練習引擎 | pico-sdk / RP2350 | 差異與陷阱 |
|---|---|---|
| `ENGINE_CHANNELS 4` | `NUM_DMA_CHANNELS`（RP2350 = 16，RP2040 = 12） | 通道仍是有限資源，用完要還 |
| `int engine_claim(void)`，全滿回 -1 | `int dma_claim_unused_channel(bool required)`；`required=false` 全滿回 -1，`true` 直接 panic | — |
| `engine_job_t` | `dma_channel_config`（CTRL）+ 讀位址 + 寫位址 + 筆數 | 真實 API 把「位址/筆數」與「設定」分開 |
| `.src` | `read_addr`（`dma_channel_configure` 第 4 個參數） | **參數順序是 (dst, src)**，跟 `memcpy(dst, src, n)` 一樣先目的地 |
| `.dst` | `write_addr`（第 3 個參數） | 同上 |
| `.count`（筆數，不是 bytes） | `TRANS_COUNT`（第 5 個參數），同樣是筆數 | 一樣的頭號錯誤：填 bytes 會搬 2 或 4 倍量並蓋掉後面記憶體。RP2350 高 4 bit 是 MODE |
| `.size = XFER_8/16/32`（值 = 1/2/4 bytes） | `channel_config_set_transfer_data_size(&c, DMA_SIZE_8/16/32)`（值 = **0/1/2**） | 不能把 bytes 數直接傳進去：`DMA_SIZE_32` 是 2 不是 4 |
| `.src_increment` | `channel_config_set_read_increment(&c, bool)` | **預設 true** |
| `.dst_increment` | `channel_config_set_write_increment(&c, bool)` | **預設 false**（memcpy 忘了設 = 全寫到同一格） |
| `engine_configure(ch, &job)` | `dma_channel_configure(ch, &c, dst, src, count, false)` | 引擎在 BUSY 時拒絕；硬體不擋，BUSY 時改暫存器會改到進行中的傳輸 |
| `engine_start(ch)` | `dma_channel_start(ch)`；或 configure 最後一參數 `true`；或 `dma_start_channel_mask(mask)` | 通道 BUSY 時觸發被**靜默忽略** |
| `engine_busy(ch)` | `dma_channel_is_busy(ch)` | — |
| `engine_wait(ch)` | `dma_channel_wait_for_finish_blocking(ch)`，或 IRQ | wait 內含 compiler barrier |
| `engine_release(ch)` | `dma_channel_cleanup(ch); dma_channel_unclaim(ch);` | 引擎在 BUSY 時拒絕；硬體上 unclaim 不會停通道，要先 cleanup/abort |
| 引擎驗證 size ∈ {1,2,4} | `channel_config_set_transfer_data_size` 內有 `assert` | — |
| 引擎驗證 count != 0 | 硬體允許 0：立即完成、不搬資料；配 CHAIN_TO 有 errata E8（⚠️未查證） | — |
| 引擎驗證位址對齊，不對齊就停 | **硬體不檢查**，結果未定義 | 自己保證 `__attribute__((aligned(4)))` |
| 複製 vs 填值只差 `src_increment` | 一樣：填值 = `read_increment=false` 指向一個 pattern 變數 | pattern 變數必須在 DMA 期間保持有效（別用即將離開 scope 的區域變數） |
| 引擎是一條 pthread，仍佔 CPU | 真硬體只吃匯流排頻寬，CPU 完全空出 | 但會與 CPU 搶同一個 SRAM bank / 週邊 |

最直接的「翻譯」範例：

```c
// 練習版
engine_job_t copy = { .src = src, .dst = dst, .count = N, .size = XFER_32,
                      .src_increment = true, .dst_increment = true };
int ch = engine_claim();
engine_configure(ch, &copy);
engine_start(ch);
engine_wait(ch);
engine_release(ch);

// pico-sdk 版
int ch = dma_claim_unused_channel(true);
dma_channel_config c = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
channel_config_set_read_increment(&c, true);
channel_config_set_write_increment(&c, true);
dma_channel_configure(ch, &c, dst, src, N /* 筆數 */, false);
dma_channel_start(ch);
dma_channel_wait_for_finish_blocking(ch);
dma_channel_cleanup(ch);
dma_channel_unclaim(ch);
```

---

## 4. 範例程式（自行撰寫的短範例；未在本機編譯，使用前請在考場環境編譯驗證）

共同標頭：

```c
#include <string.h>
#include "pico/stdlib.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/pio.h"
// CMakeLists.txt: target_link_libraries(app pico_stdlib hardware_dma hardware_pio)
```

### 4.1 memcpy 取代（32-bit，含頭尾處理）

```c
// 把 n bytes 從 src 複製到 dst。DMA 只處理 4-byte 對齊的中段；不對齊時退回 memcpy。
static int g_copy_ch = -1;

void dma_memcpy(void *dst, const void *src, size_t n) {
    if (g_copy_ch < 0) g_copy_ch = dma_claim_unused_channel(true);
    uintptr_t d = (uintptr_t)dst, s = (uintptr_t)src;
    if (n < 64 || ((d ^ s) & 3)) {            // 太短或兩邊對齊相位不同：CPU 較划算（門檻請實測）
        memcpy(dst, src, n);
        return;
    }
    size_t head = (4 - (d & 3)) & 3;          // 先用 CPU 補到 4-byte 對齊
    memcpy(dst, src, head);
    d += head; s += head; n -= head;
    size_t words = n / 4, tail = n % 4;

    dma_channel_config c = dma_channel_get_default_config(g_copy_ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, true);   // 預設是 false！
    dma_channel_configure(g_copy_ch, &c, (void *)d, (const void *)s, words, true);
    dma_channel_wait_for_finish_blocking(g_copy_ch);

    memcpy((void *)(d + words * 4), (const void *)(s + words * 4), tail);
}
```

要「真的」賺到時間：啟動後不要立刻 wait，先讓 CPU 做其他不碰 `dst` 的工作，最後才 wait（見 §6）。

### 4.2 memset 式填值

```c
static uint32_t fill_pattern;   // 必須在 DMA 期間有效：用 static/全域，不要用即將返回的區域變數

void dma_fill32(uint32_t *dst, uint32_t value, size_t words, int ch) {
    fill_pattern = value;
    dma_channel_config c = dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);   // 一直讀同一格 → 填值
    channel_config_set_write_increment(&c, true);
    dma_channel_configure(ch, &c, dst, &fill_pattern, words, true);
    dma_channel_wait_for_finish_blocking(ch);
}
// byte 填值：DMA_SIZE_8 + uint8_t pattern；寫 SRAM 時只改目標 byte。
```

### 4.3 記憶體 → PIO TX FIFO（由 PIO 節流）

```c
void dma_to_pio(PIO pio, uint sm, const uint32_t *buf, size_t words, int ch) {
    dma_channel_config c = dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);              // FIFO 位址固定
    channel_config_set_dreq(&c, pio_get_dreq(pio, sm, true));   // TX DREQ
    dma_channel_configure(ch, &c, &pio->txf[sm], buf, words, true);
}
```

### 4.4 PIO RX FIFO → 記憶體

```c
void dma_from_pio(PIO pio, uint sm, uint32_t *buf, size_t words, int ch) {
    dma_channel_config c = dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);               // FIFO 位址固定
    channel_config_set_write_increment(&c, true);
    channel_config_set_dreq(&c, pio_get_dreq(pio, sm, false));  // RX DREQ
    dma_channel_configure(ch, &c, buf, &pio->rxf[sm], words, true);
}
```

考前練習的 `echo` PIO 程式（`out x,32 / in x,32 / push`，autopull）若要用 DMA 測：開兩個通道，一個 4.3 送、一個 4.4 收；**先啟動 RX 通道再啟動 TX 通道**，或用 `dma_start_channel_mask((1u<<rx)|(1u<<tx))` 同時啟動。DMA 跑時 CPU 不可 `pio_sm_get/put` 同一個 FIFO。

### 4.5 完成中斷（IRQ）

```c
static int ch;
static volatile bool done;

static void dma_irq0_handler(void) {
    if (dma_channel_get_irq0_status(ch)) {
        dma_channel_acknowledge_irq0(ch);   // 一定要清，否則 handler 會一直重入
        done = true;
    }
}

void setup(void) {
    ch = dma_claim_unused_channel(true);
    /* … 建立 config c … */
    dma_channel_configure(ch, &c, dst, src, N, false);
    dma_channel_set_irq0_enabled(ch, true);                 // INTE0
    irq_set_exclusive_handler(DMA_IRQ_0, dma_irq0_handler); // 或 irq_add_shared_handler(...)
    irq_set_enabled(DMA_IRQ_0, true);
    dma_channel_start(ch);
}

// 主迴圈：
// while (!done) { /* 做別的事 */ }
// __compiler_memory_barrier();   // 之後才讀 dst
```

在 ISR 內「重新設定並立刻再啟動」：`dma_channel_set_read_addr(ch, next_buf, true);`（只寫 READ_ADDR_TRIG，count 用 reload 值）。這正是 pico-examples `channel_irq` 的做法。

RP2350 用第 3、4 條 DMA IRQ：

```c
dma_irqn_set_channel_enabled(2, ch, true);
irq_set_exclusive_handler(dma_get_irq_num(2), handler);   // = DMA_IRQ_2
irq_set_enabled(dma_get_irq_num(2), true);
// handler 內：if (dma_irqn_get_channel_status(2, ch)) dma_irqn_acknowledge_channel(2, ch);
```

### 4.6 Ping-pong（雙緩衝，兩通道互相 chain）

```c
#define N 1024
static uint32_t buf[2][N];
static int ch_a, ch_b;
static volatile int ready = -1;        // 哪個 buffer 剛填好

static void pingpong_isr(void) {
    if (dma_channel_get_irq0_status(ch_a)) {
        dma_channel_acknowledge_irq0(ch_a);
        dma_channel_set_write_addr(ch_a, buf[0], false);   // 重設位址，不觸發（等 ch_b chain 過來）
        ready = 0;
    }
    if (dma_channel_get_irq0_status(ch_b)) {
        dma_channel_acknowledge_irq0(ch_b);
        dma_channel_set_write_addr(ch_b, buf[1], false);
        ready = 1;
    }
}

void pingpong_start(PIO pio, uint sm) {
    ch_a = dma_claim_unused_channel(true);     // 兩個都先 claim，才能互相設定 chain_to
    ch_b = dma_claim_unused_channel(true);
    int chs[2] = { ch_a, ch_b };
    for (int i = 0; i < 2; i++) {
        dma_channel_config c = dma_channel_get_default_config(chs[i]);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
        channel_config_set_read_increment(&c, false);
        channel_config_set_write_increment(&c, true);
        channel_config_set_dreq(&c, pio_get_dreq(pio, sm, false));
        channel_config_set_chain_to(&c, chs[i ^ 1]);           // A→B、B→A
        dma_channel_configure(chs[i], &c, buf[i], &pio->rxf[sm], N, false);
    }
    dma_set_irq0_channel_mask_enabled((1u << ch_a) | (1u << ch_b), true);
    irq_set_exclusive_handler(DMA_IRQ_0, pingpong_isr);
    irq_set_enabled(DMA_IRQ_0, true);
    dma_channel_start(ch_a);
}
// 主迴圈：看到 ready==k 就處理 buf[k]；必須在另一個 buffer 填滿前處理完，否則資料被覆蓋。
```

重點：chain 讓「下一段」在硬體層無縫接上（設定與執行 pipeline 化），CPU 只需在對方運作時重設已完成那個通道的位址。
（此處兩通道接同一 DREQ，但任一時刻只有一個在跑；這是常見 ping-pong 寫法，與 §1.7「不可讓多個通道接同一個 DREQ」是否衝突 datasheet 未明說 ⚠️未驗證，資料偶爾錯時可改用單通道 ring + TRIGGER_SELF（§4.7）。）

### 4.7 RP2350：單通道 ring buffer + 週期中斷（TRIGGER_SELF）

```c
#define RING_BITS 10                                    // 1 << 10 = 1024 bytes = 256 words
static uint32_t ring[256] __attribute__((aligned(1 << RING_BITS)));   // 必須對齊到 ring 大小

void ring_start(PIO pio, uint sm, int ch) {
    dma_channel_config c = dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, false);
    channel_config_set_write_increment(&c, true);
    channel_config_set_ring(&c, true, RING_BITS);       // write=true：寫位址在 1024 bytes 內繞
    channel_config_set_dreq(&c, pio_get_dreq(pio, sm, false));
    dma_channel_set_irq0_enabled(ch, true);
    // 每 128 筆（半個 ring）完成一次 → IRQ → 自動重新觸發，位址繼續在 ring 內前進
    dma_channel_configure(ch, &c, ring, &pio->rxf[sm],
                          dma_encode_transfer_count_with_self_trigger(128), true); // SDK 2.2.0+
    // SDK 2.1.x：改傳 (1u << 28) | 128
}
// ISR：ack 後處理「剛寫完的那一半」。RP2040 沒有此 mode，需改用兩通道 ping-pong 或 control-block 重新觸發。
```

若完全不需要中斷、只要永遠循環（例如持續把波形表送到 PIO）：count 用 `dma_encode_endless_transfer_count()` 搭配讀端 ring；要停止只能 abort（並遵守 E5 程序）。

### 4.8 Scatter-gather：控制通道 + 資料通道（control blocks）

依 pico-examples `control_blocks` 的結構：控制通道把一筆 `{len, read_addr}` 寫進資料通道 Alias 3 的 `(TRANS_COUNT, READ_ADDR_TRIG)`，寫入 READ_ADDR_TRIG 即啟動資料通道；資料通道完成後 chain 回控制通道載入下一筆；最後一筆 `{0, NULL}` 是 null trigger，資料通道（設了 IRQ_QUIET）因而發 IRQ 表示整串結束。

```c
typedef struct { uint32_t len; const void *read_addr; } cb_t;   // 順序必須對應 al3_transfer_count, al3_read_addr_trig

static const cb_t blocks[] = {
    { 64, part0 }, { 16, part1 }, { 128, part2 },
    { 0, NULL },                       // null trigger：結束（不要在中間放 len=0，見 errata E8）
};

void gather_start(uint32_t *dst, int ctrl_ch, int data_ch) {
    dma_channel_config c = dma_channel_get_default_config(ctrl_ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, true);
    channel_config_set_ring(&c, true, 3);               // 寫位址在 8 bytes（2 個暫存器）內繞回
    dma_channel_configure(ctrl_ch, &c, &dma_hw->ch[data_ch].al3_transfer_count,
                          &blocks[0], 2, false);        // 每次觸發搬 2 words = 1 個 control block

    c = dma_channel_get_default_config(data_ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, true);       // 寫位址不重設 → 各段接續寫成連續 dst（gather）
    channel_config_set_chain_to(&c, ctrl_ch);
    channel_config_set_irq_quiet(&c, true);             // 只在 null trigger 時發 IRQ
    dma_channel_configure(data_ch, &c, dst, NULL, 0, false);

    dma_channel_start(ctrl_ch);
    // 等待整串結束（無中斷版）：
    while (!(dma_hw->intr & (1u << data_ch))) tight_loop_contents();
    dma_hw->intr = 1u << data_ch;        // 清除（INTR / INTS 寫 1 清除）
}
// 若目的地是週邊 FIFO：write_increment=false + 設 DREQ（官方範例送到 UART）。
// 注意：上例 len 的單位是「32-bit 筆數」。
```

### 4.9 DMA timer 節拍（定速輸出，例如每 1 µs 一筆）

```c
int t = dma_claim_unused_timer(true);
dma_timer_set_fraction(t, 1, 150);                 // clk_sys=150 MHz 時 → 1 MHz（clk_sys 不同要重算）
channel_config_set_dreq(&c, dma_get_timer_dreq(t));
// … configure/start …；用完 dma_timer_unclaim(t);
```

### 4.10 用 sniffer 算 CRC32（不需要複製時寫到 dummy）

```c
static uint8_t dummy;
uint32_t dma_crc32_check(const uint8_t *data, size_t len, int ch) {
    dma_channel_config c = dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_8);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);       // 全寫到同一個 dummy byte
    channel_config_set_sniff_enable(&c, true);           // config 也要開（configure 會覆寫 CTRL）
    dma_sniffer_set_data_accumulator(0xFFFFFFFFu);
    dma_sniffer_set_output_reverse_enabled(true);
    dma_sniffer_enable(ch, DMA_SNIFF_CTRL_CALC_VALUE_CRC32R, true);
    dma_channel_configure(ch, &c, &dummy, data, len, true);
    dma_channel_wait_for_finish_blocking(ch);
    return dma_sniffer_get_data_accumulator();
}
// 官方範例：資料尾端附上軟體算出的 CRC32（反射式、多項式 0xEDB88320）後整段 sniff，結果為 0 代表正確。
// 要得到與 zlib crc32() 完全相同的值需要的 invert/reverse 組合：⚠️未驗證，請與軟體 CRC 比對後再用。
```

`DMA_SNIFF_CTRL_CALC_VALUE_SUM` 可用來做 32-bit 累加和；8/16-bit 傳輸時被加進去的是哪個值（是否含 byte-lane replication）⚠️未驗證，請先用 32-bit 傳輸並與軟體結果比對。

### 4.11 安全停止（RP2350，含 E5 對策）

```c
void dma_stop_chain(uint32_t mask) {          // mask = 鏈上所有通道
    for (uint i = 0; i < NUM_DMA_CHANNELS; i++) {
        if (mask & (1u << i)) {
            // CHAIN_TO 指回自己 + EN=0（寫 al1_ctrl 不會觸發）
            hw_write_masked(&dma_hw->ch[i].al1_ctrl,
                            (i << DMA_CH0_CTRL_TRIG_CHAIN_TO_LSB),
                            DMA_CH0_CTRL_TRIG_CHAIN_TO_BITS | DMA_CH0_CTRL_TRIG_EN_BITS);
        }
    }
    dma_hw->abort = mask;
    while (dma_hw->abort & mask) tight_loop_contents();
    dma_hw->intr = mask;                      // 清掉 abort 期間可能出現的中斷
}
// 單一通道：直接 dma_channel_cleanup(ch) 即可（SDK 已做相同步驟）。
```

### 4.12 量測：CPU 迴圈 vs DMA

```c
#include "pico/time.h"
uint64_t t0 = time_us_64();
for (int r = 0; r < 100; r++) memcpy(dst, src, sizeof src);
uint64_t cpu_us = time_us_64() - t0;

t0 = time_us_64();
for (int r = 0; r < 100; r++) {
    dma_channel_configure(ch, &c, dst, src, count_of(src), true);   // count_of = 陣列元素數（此處 uint32_t 陣列 = 筆數）
    dma_channel_wait_for_finish_blocking(ch);
}
uint64_t dma_us = time_us_64() - t0;
// 重複多次取平均；用 1 µs 解析度量太短的事件不準，必要時加大資料量或重複次數。
// 若想用 cycle 級精度：Arm 可用 DWT CYCCNT、RISC-V 可用 mcycle ⚠️未驗證於本文件，請查 datasheet 對應章節。
```

---

## 5. 常見陷阱（依發生頻率排序）

1. **count 填成 bytes**：`TRANS_COUNT` 是筆數。`DMA_SIZE_32` 時 bytes/4，`DMA_SIZE_16` 時 bytes/2。用 `count_of(array)`（元素數）而不是 `sizeof(array)`（bytes）。—— 考前練習 `make mistake` 演示的就是這件事。
2. **`dma_channel_configure` 參數順序**：`(ch, &cfg, write_addr/dst, read_addr/src, count, trigger)`。目的地在前。
3. **忘了 `write_increment=true`**：default config 是 read 遞增、write 不遞增（給「記憶體→週邊」用的）。memcpy 結果會變成 dst[0] = src 最後一筆，其餘不變。
4. **把 bytes 數當 `DMA_SIZE_*` 傳**：`DMA_SIZE_8/16/32` = 0/1/2。
5. **位址未對齊**：硬體不檢查、結果未定義。32-bit 要 4-byte 對齊；`uint8_t` 陣列不保證對齊。
6. **DMA buffer 生命週期**：DMA 寫入/讀出區域變數，函式返回後 stack 被重用 → 資料錯亂。用 `static` / 全域，或確定 wait 完才返回。fill 用的 pattern 變數同理。
7. **編譯器重排 / 快取在暫存器**：自己輪詢 busy 或 ISR 設 flag 時，flag 要 `volatile`，讀 buffer 前加 `__compiler_memory_barrier()`。（RP2350 SRAM 沒有 CPU data cache，不需要 cache 維護。）
8. **通道 BUSY 時重新觸發被靜默忽略**：連續兩次 configure+trigger 而中間沒 wait，第二次可能完全沒發生。BUSY 時改 READ/WRITE_ADDR 會改到進行中的傳輸。
9. **IRQ 沒 acknowledge**：handler 不斷重入，主程式卡死。`dma_channel_acknowledge_irq0(ch)` 或 `dma_hw->ints0 = 1u << ch`。
10. **`irq_set_exclusive_handler` 衝突**：同一 IRQ 已有 handler（例如其他函式庫）會出錯 → 改用 `irq_add_shared_handler` 或用另一條 `DMA_IRQ_n`。
11. **CPU 與 DMA 同時碰同一個週邊 FIFO**、**兩個通道接同一 DREQ**：datasheet 明文禁止。
12. **8/16-bit DMA 寫入 IO 暫存器**：資料被複製到整個 32 bit（byte-lane replication），可能改到其他欄位。
13. **DMA 寫 GPIO（SIO）**：DMA 無法存取 SIO → 匯流排錯誤。改用 PIO。
14. **`CHAIN_TO` 預設值**：直接寫 CTRL 暫存器（不用 SDK default config）時，CHAIN_TO reset 值為 0，通道 1 以上會 chain 到通道 0。SDK default config 已設成自己。
15. **Abort chain 的通道會自己重啟**（RP2350-E5）：先清 EN 與 CHAIN_TO 再 abort；或用 `dma_channel_cleanup`。
16. **零長度 + CHAIN_TO**（RP2350-E8 ⚠️未查證）：chain 可能不發生。
17. **Ring buffer 未對齊**：`channel_config_set_ring` 只保留低 n bit 變化，buffer 沒對齊 `1<<n` 就會繞到錯的區域。注意 ring 只能套用在讀或寫其中一邊。
18. **RP2350 count ≥ 2^28** 會被解讀成 MODE。用 `dma_encode_transfer_count()`（2.2.0+）。
19. **把 RP2040 程式直接搬過來**：IRQ 號、DREQ 編號、通道數都不同；用巨集與 `NUM_DMA_*`，不要寫死數字。
20. **`dma_sniffer_enable(..., true)` 後又 `dma_channel_configure`**：CTRL 被 config 覆寫，SNIFF_EN 消失 → 結果沒變。config 裡也要 `channel_config_set_sniff_enable(&c, true)`。
21. **`print_dma_ctrl` 編譯不過**：只有未定義 `NDEBUG`（Debug build）才存在。
22. **`unclaim` 不等於停止**：unclaim 只改軟體標記，正在跑的通道會繼續跑。先 `dma_channel_cleanup`。

---

## 6. DMA 什麼時候「不會」比較快

| 情況 | 原因 | 對策 |
|---|---|---|
| 很短的傳輸（數十 bytes 等級，門檻 ⚠️需實測） | 設定 4 個暫存器 + 啟動 + 輪詢的固定成本，可能大於 CPU 直接 `memcpy` | 小量用 CPU；或把多段小傳輸用 control block 一次交給 DMA |
| 啟動後立刻 `wait` | CPU 沒做別的事，只剩「DMA 搬得比 CPU 快多少」的差距 | 啟動後讓 CPU 先算別的（不碰目標 buffer），最後才 wait；或雙緩衝讓運算與搬運重疊 |
| 用 `DMA_SIZE_8` 搬大量資料 | 每筆只搬 1 byte，頻寬只用到 1/4 | 對齊後用 `DMA_SIZE_32`，頭尾零碎 bytes 另外處理 |
| 多通道分割同一份 memcpy | 整顆 DMA 每 cycle 只有 1 讀 + 1 寫，通道間 round-robin 平分 | 一個通道即可；多通道是為了「多件獨立工作」不是加速單件 |
| CPU 與 DMA 搶同一 SRAM bank | 同一 bank 每 cycle 只服務一個 manager | 把 CPU 熱資料與 DMA buffer 分在不同 striped 區域（SRAM0–3 vs SRAM4–7），或用 SRAM8/9 給 CPU 私用；必要時調 `busctrl_hw->priority`（注意 E27） |
| 讀 flash（XIP）/ APB 週邊 | 受 QSPI 或 APB 速度限制 | 常用資料先搬到 SRAM；flash 大量讀可考慮 XIP streaming |
| 受週邊 DREQ 節流 | 速度由週邊決定（如 UART 鮑率、PIO 時脈分頻） | DMA 的好處在於「CPU 空出來」，不是傳得更快；想更快要調週邊/PIO 本身 |
| 資料需要逐筆運算（不只是搬） | DMA 只能搬、bswap、算 CRC/sum/parity | 運算仍需 CPU（或 PIO）；DMA 負責把資料餵進/拿出 |

---

## 7. 除錯檢查清單

1. 通道號是否有效？`ch >= 0`（`dma_claim_unused_channel(false)` 可能回 -1），且 `< NUM_DMA_CHANNELS`。
2. 讀回 config：`print_dma_ctrl(&dma_hw->ch[ch])`（Debug build），或手動解 `dma_hw->ch[ch].ctrl_trig`：
   - `EN`=1？`BUSY`？`DATA_SIZE` 對嗎？`INCR_READ/INCR_WRITE` 對嗎？`TREQ_SEL` 是預期 DREQ 嗎？`CHAIN_TO` 是自己還是預期通道？
   - `READ_ERROR`/`WRITE_ERROR` 有沒有被設？有 → 檢查位址（SIO？未映射？被 ACCESSCTRL 擋？），等 BUSY=0 後寫 1 清除。
3. `dma_hw->ch[ch].transfer_count`：卡在非 0 且 BUSY=1 → 通常是 DREQ 沒來（週邊/PIO SM 沒啟動、方向 TX/RX 選錯、PIO 號或 SM 號錯）。
4. `dma_debug_hw->ch[ch].dbg_tcr`：reload 值是不是你以為的筆數？（抓「填成 bytes」的 bug）
5. `dma_hw->ch[ch].read_addr / write_addr`：停在哪裡？與起點相減 / 筆寬 = 實際完成筆數。
6. 結果「只有第一格對」→ write increment 忘了開。「整個 buffer 都是同一值」→ read increment 誤關。「多寫了 2/4 倍、蓋掉後面變數」→ count 用了 bytes。
7. 中斷沒進來：`INTE`（`dma_channel_set_irqN_enabled`）、`irq_set_enabled(DMA_IRQ_N, true)`、handler 有安裝、handler 用的 IRQ 號與 enable 的一致？有沒有 `IRQ_QUIET`？`dma_hw->intr` 有沒有對應 bit？
8. 中斷進來後卡死：handler 沒 ack。
9. 第二次傳輸沒發生：觸發時通道仍 BUSY；或 CHAIN_TO 遇到零長度（E8 ⚠️未查證）；或 EN=0。
10. abort 後通道又自己跑起來：E5 → 先清 EN/CHAIN_TO。
11. 資料偶爾錯：CPU 同時存取 DMA 正服務的 FIFO？兩通道同一 DREQ？DMA buffer 是區域變數？讀 buffer 前少了 barrier？
12. Ring 位置怪：buffer 是否對齊 `1 << size_bits`？`write` 參數選對邊了嗎？
13. 用 sniffer 結果不變：config 中 `sniff_enable` 沒開、`dma_sniffer_enable` 的 channel 參數錯、種子值沒設。
14. 版本相關編譯錯誤：`dma_channel_config_t`、`dma_encode_*`、`dma_channel_set_transfer_count`、`*_address_update_type` 都是 2.2.0+；舊 SDK 改用 `dma_channel_config`、`dma_channel_set_trans_count`、手動 MODE bit。

---

## 8. 優化檢查清單

1. **先量測**：用 `time_us_64()` 包住原本 CPU 迴圈與 DMA 版本，重複多次取平均；確認瓶頸真的在搬資料。
2. **重疊**：DMA 啟動後 CPU 做其他工作；只在真正需要結果時 `wait`。能用 IRQ 就不要忙等。
3. **加寬**：對齊後用 `DMA_SIZE_32`；`__attribute__((aligned(4)))` 宣告 buffer。
4. **雙緩衝 / ping-pong**：串流資料（PIO/ADC/SPI）用兩通道 chain 或 RP2350 `TRIGGER_SELF` + ring，CPU 處理一半時 DMA 填另一半。
5. **減少中斷次數**：多段傳輸用 control block 鏈 + `IRQ_QUIET`，只在整串結束時中斷一次。
6. **減少 ISR 成本**：在 ISR 中只寫一個 trigger alias 重啟（`dma_channel_set_read_addr(ch, p, true)` 或 `dma_channel_transfer_from_buffer_now`），讓 count 用 reload 值。
7. **重用設定**：config 只算一次；同一 channel 重複執行時只更新位址並觸發，不要每次重 claim。
8. **小量資料留給 CPU**：設定成本 > 搬運時間時直接 `memcpy`/迴圈。
9. **避開匯流排衝突**：CPU 工作資料與 DMA buffer 放不同 SRAM bank/區域；熱迴圈程式碼與 DMA 都不要同時壓在 flash（XIP）上。
10. **讓硬體做額外工作**：位元組序轉換用 `bswap`；CRC/checksum/parity 用 sniffer；反向複製或交錯資料抽取用 RP2350 的 `DECREMENT` / `INCREMENT_BY_TWO`（2.2.0+ API）。
11. **定速輸出不用 CPU 計時**：用 DMA timer（`dma_timer_set_fraction` + `dma_get_timer_dreq`）或週邊 DREQ 節流。
12. **優先權**：時間敏感的通道用 `channel_config_set_high_priority`（DMA 內部）；匯流排層級用 `busctrl_hw->priority`（注意 E27 在週邊仲裁器上接錯）；中斷層級可把時間敏感通道路由到另一條 `DMA_IRQ_n` 並給較高 NVIC 優先權。

---

## 9. 向模型提問的範本

> 使用方式：把 `{{...}}` 換成實際內容，連同本文件一起貼給模型。

**範本 1：把 CPU 迴圈改成 DMA**

```
以下是 RP2350 上用 pico-sdk {{SDK 版本，例如 2.2.0}} 的程式片段，目前用 CPU 迴圈做 {{複製/填值/送到 PIO}}：
{{貼上程式碼}}
資料型別是 {{uint8_t/uint16_t/uint32_t}}，筆數 {{N}}，來源位址 {{是否對齊}}，目的地 {{記憶體/PIO pio{{0|1|2}} SM {{n}} 的 TX FIFO}}。
請改寫成 DMA 版本：列出每一個 channel_config_set_* 的值與理由，dma_channel_configure 的 (write_addr, read_addr, count) 各填什麼（count 用筆數），
並說明 CPU 在 DMA 期間可以做什麼，以及怎麼量測前後時間差。
```

**範本 2：DMA 沒有動 / 結果錯誤**

```
RP2350 DMA 通道 {{ch}} 沒有照預期運作。現象：{{例如 transfer_count 卡在 37、只有第一個元素正確、IRQ 沒進來}}。
設定程式碼：{{貼上}}
我讀到的暫存器值：ctrl_trig=0x{{...}}，transfer_count={{...}}，read_addr=0x{{...}}，write_addr=0x{{...}}，dbg_tcr={{...}}，intr=0x{{...}}。
請逐欄位解碼 ctrl_trig（依 RP2350 位元配置：BUSY=bit26、TREQ_SEL=bit22:17、CHAIN_TO=bit16:13、DATA_SIZE=bit3:2…），
對照本文件第 7 節的除錯清單，指出最可能的原因並給出修正後的程式碼。
```

**範本 3：串流 / 雙緩衝設計**

```
我需要從 {{PIO/ADC/SPI}} 連續接收資料，速率約 {{每秒筆數}}，每筆 {{位元數}} bit，每收滿 {{N}} 筆要用 CPU 處理一次（處理約需 {{時間}}）。
平台 RP2350、pico-sdk {{版本}}。請比較 (a) 兩通道 CHAIN_TO ping-pong 與 (b) 單通道 ring + TRIGGER_SELF 兩種做法，
給出完整設定（buffer 對齊、ring size_bits、count、DREQ、IRQ 安裝與 acknowledge），並分析處理時間是否來得及、來不及會發生什麼。
```

**範本 4：效能判斷**

```
這段程式的瓶頸是 {{描述}}，資料量 {{bytes}}，在 RP2350 clk_sys={{MHz}} 下目前耗時 {{µs}}。
請估算用 DMA（{{DMA_SIZE_8/16/32}}）的理論時間與固定設定成本，判斷改用 DMA 是否值得；
考慮 SRAM bank 衝突（SRAM0-3/4-7 striping、SRAM8/9）、APB/XIP 速度與 DMA 每 cycle 1 讀 1 寫的上限。
若不值得，請提出替代優化（例如加寬存取、重疊運算、改資料擺放）。數字若是估計請明確標示。
```

**範本 5：閱讀文件後對照 API**

```
考題文件描述了一個 {{模組/引擎名稱}}，其 API 為：{{貼上 API 與說明}}。
請把它逐一對照到 pico-sdk hardware_dma 的函式（參考本文件第 3 節的對照表），
指出語意差異（count 單位、size 編碼、預設遞增、對齊檢查、busy 時的行為、釋放資源），
並寫出等價的 pico-sdk 程式碼。
```
