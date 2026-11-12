# Pico 2 (RP2350) 除錯：沒有除錯器也能查

> **實際跑過**：§1 的 LED 範本在 `pico-build` 容器編譯通過（0 warning）；`picotool info`；`.dis`/`.map`/`nm`/`addr2line`；
> pyserial（主機有 3.5 版）透過假的序列埠 (pty) 收發資料。
> **沒跑過**（這裡沒有板子、也沒有 Debug Probe）：燒錄、序列埠監看程式接真的板子、openocd/gdb。這些指令是對照
> 官方文件《Getting started with Raspberry Pi Pico-series》附錄 A 和 picotool 的 `help` 輸出寫的。

## 1. 它到底有沒有在跑？先用 LED

`PICO_DEFAULT_LED_PIN` 在 pico2 = **GP25**（`boards/pico2.h`）。範本（`pico_stdlib` 就夠了）：
```c
#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/uart.h"
#define LED PICO_DEFAULT_LED_PIN

static void blink_code(int n) {          // 閃 n 下、停 1 秒，永遠重複 = 錯誤代碼 n
    for (;;) {
        for (int i = 0; i < n; i++) { gpio_put(LED, 1); sleep_ms(150); gpio_put(LED, 0); sleep_ms(150); }
        sleep_ms(1000);
    }
}
static void dbg_uart(const char *s) { uart_puts(uart0, s); }   // 只寫 GP0，不影響 USB 上的資料

int main(void) {
    stdio_init_all();
    gpio_init(LED); gpio_set_dir(LED, GPIO_OUT);
    gpio_put(LED, 1);                    // ① 一上電就恆亮 = 有跑到 main
    dbg_uart("boot\r\n");
    int ok = 1;                          // TODO(改這裡)：你的初始化檢查
    if (!ok) blink_code(3);              // ② 閃 3 下 = 初始化失敗
    uint32_t loops = 0;
    for (;;) {
        gpio_put(LED, (loops++ / 50) & 1);   // ③ 每 0.5 秒換一次 = 主迴圈正常
        sleep_ms(10);
    }
}
```
| LED 看到 | 意思 |
|---|---|
| 完全不亮 | 沒燒進去 / 燒錯檔/ 卡在 `stdio_init_all()` 之前 |
| 恆亮不閃 | 有跑到 main，但卡在主迴圈之前（等 USB、等資料、panic） |
| 慢閃 | 主迴圈正常 → 問題在通訊或計算 |
| 閃 N 下 | 你自己定義的錯誤代碼 |

## 2. 燒錄、看資訊、重開

| 動作 | 指令 / 方法 |
|---|---|
| 最可靠的燒錄 | 按住 **BOOTSEL** 插 USB → 出現隨身碟 `RP2350` → `cp build/app.uf2 /media/$USER/RP2350/`（自動重開） |
| 用 picotool 燒 | `picotool load -x build/app.uf2 -f`（`-x` 燒完就執行；`-f` 讓**正在跑而且有開 USB stdio** 的板子自己重開進 BOOTSEL） |
| 重開 | `picotool reboot`（回到程式）、`picotool reboot -u`（進 BOOTSEL）；兩個都可以加 `-f` |
| 看檔案裡是什麼 | `picotool info -a build/app.uf2`（**不用板子**，實測） |
| 看板子裡是什麼 | `picotool info -a`（板子要在 BOOTSEL，或加 `-f`） |

`picotool info -a app_serial.uf2` 實測（可以確認燒的是不是對的程式、對的晶片）：
```
File app_serial.uf2 family ID 'rp2350-arm-s':
 name:                app_serial
 features:            USB stdin / stdout        ← 有開 USB stdio
 target chip:         RP2350
 image type:          ARM Secure                ← ARM 版（RISC-V 版會寫 RISC-V）
 pico_board:          pico2
 build attributes:    Release
```
- picotool 在哪：`which picotool`；SDK 自己編的那一份在 `build/_deps/picotool/picotool`。
- ⚠ 實測：pico-build 裡 SDK 編的 picotool **沒有 USB 功能**（印出 `compiled without USB support`），`load`、`reboot` 會變成 `Unknown command`。這時候就用 BOOTSEL 拖檔案的方法。
- 有 USB 版 picotool 但沒插板子時印：`No accessible RP-series devices in BOOTSEL mode were found.`（實測）。
- 容器裡看不到板子 → 容器要用 `--privileged -v /dev/bus/usb:/dev/bus/usb`（picotool）或 `--device /dev/ttyACM0`（序列埠）啟動。

## 3. 序列埠監看

```bash
ls /dev/ttyACM* /dev/serial/by-id/         # 板子插上後出現 ttyACM0；by-id 的名字含 "Pico"，比較不會認錯
python3 -m serial.tools.list_ports          # pyserial 列出所有序列埠
sudo dmesg -w                               # 一邊插拔一邊看 (可能要 sudo)：會看到 cdc_acm ... ttyACM0
```

| 工具 | 開啟 | 離開 | 有沒有（這台實測） |
|---|---|---|---|
| pyserial miniterm | `python3 -m serial.tools.miniterm /dev/ttyACM0 115200` | **Ctrl-]**（選單 Ctrl-T） | ✅ 主機有；容器裡沒有 |
| screen | `screen /dev/ttyACM0 115200` | **Ctrl-a 再按 k**，然後按 y | ❌ 沒裝 |
| picocom | `picocom -b 115200 /dev/ttyACM0` | **Ctrl-a 再按 Ctrl-x** | ❌ 沒裝 |
| minicom（官方文件用這個） | `minicom -D /dev/ttyACM0 -b 115200` | Ctrl-a 再按 x | ❌ 沒裝 |
| cat | `stty -F /dev/ttyACM0 raw -echo; cat /dev/ttyACM0` | Ctrl-C | ✅ 一定有 |
| 看二進位 | `cat /dev/ttyACM0 \| xxd` | Ctrl-C | ✅ |

- USB CDC 的 baud rate 其實沒有作用（隨便設都一樣快），**但不要設 1200**：SDK 預設 `PICO_STDIO_USB_RESET_MAGIC_BAUD_RATE=1200`，用 1200 打開序列埠會讓板子**重開進 BOOTSEL**（stdio_usb.h 原始碼確認）。
- **同一時間只能有一個程式打開序列埠**。監看程式開著的時候，你的 bridge / `micro_ros_agent` 會讀不到資料或出現 `device busy`。→ 先關掉監看程式。
- `Permission denied: '/dev/ttyACM0'`：使用者不在 `dialout` 群組（這台實測不在）。不能改系統 → 用 `sudo`，或在 `--device` 啟動的容器裡用 root 執行。
- 拔插或重新燒錄後，`ttyACM0` 可能變成 `ttyACM1`（舊的還被某個程式開著）。如果還接了 Debug Probe，它**也會佔用一個 ttyACM**。

## 4. 除錯訊息不要弄壞二進位協定

題目常用 USB 序列埠傳二進位封包，這時候 `printf` 的文字會混進封包裡 → 電腦端解析失敗。替代方法：

| 方法 | 做法 |
|---|---|
| UART 當除錯口 | `pico_enable_stdio_uart(x 1)` 後，GP0=TX、GP1=RX、115200。只想讓除錯訊息走 UART：用 `uart_puts(uart0, "...")`，不要用 printf |
| LED | §1 |
| 協定裡加除錯指令 | 例如 cmd `0x7F` = 回傳內部計數器、錯誤碼（電腦端送一個封包問就好） |
| 先用文字模式 | 先讓計算正確（用 printf），再換成二進位協定 |
| 存在陣列裡 | 把中間值記到全域陣列，最後一次用協定送回去 |

**USB 連線時機**：`stdio_init_all()` 不會等電腦開序列埠，開頭的 printf 會**直接被丟掉**。
```cmake
target_compile_definitions(x PRIVATE PICO_STDIO_USB_CONNECT_WAIT_TIMEOUT_MS=3000)  # 開機最多等 3 秒 (預設 0；-1 = 一直等)
```
或在程式裡：`while (!stdio_usb_connected()) sleep_ms(10);`（⚠ 沒接電腦就會一直卡在這裡）。

**panic / assert 的行為**（看 SDK 原始碼確認）：
- `panic("fmt", ...)`：印出 `*** PANIC ***` 和訊息 → `_exit` → 無限迴圈執行 `__breakpoint()`。沒接除錯器時就是**停住**；USB 可能來不及把訊息送出去。
- `assert(x)`：**Release（SDK 預設）有 `-DNDEBUG` → assert 整個消失**。Debug 版（`-DCMAKE_BUILD_TYPE=Debug`，實測 `-Og -g`）才有作用。
- `hard_assert(x)`：Release 也會檢查，失敗時呼叫 `panic("Hard assert")`。
- `PICO_ENTER_USB_BOOT_ON_EXIT=1`：`_exit`（包含 panic）時直接進 BOOTSEL，方便馬上重新燒錄。
- HardFault（例如存取 NULL、沒對齊的存取）：預設的處理函式就是停住。症狀跟 panic 一樣：LED 不動、序列埠沒反應或消失。

## 5. 讀 build 產生的 `.dis`、`.map`、`.elf`

`pico_add_extra_outputs` 會產生 `build/app.dis`（反組譯 + 原始碼）和 `build/app.elf.map`（記憶體配置）。
工具在容器裡：`arm-none-eabi-{size,nm,objdump,addr2line}`。

```bash
grep -n '<main>:' build/app_serial.dis                # 找函式
grep -A12 '^[0-9a-f]* <main>:' build/app_serial.dis   # 看它的組合語言
arm-none-eabi-size build/app_serial.elf               # 總大小
arm-none-eabi-nm -S --size-sort build/app_serial.elf | tail   # 最大的幾個符號
arm-none-eabi-addr2line -f -e build/app_serial.elf 0x10000284 # 位址 → 函式和行號
```
實測輸出（app_serial）：
```
   text	   data	    bss	    dec	    hex	filename
  27164	      0	  23792	  50956	   c70c	app_serial.elf       ← text = flash 裡的程式；bss = RAM 裡初始為 0 的變數
10000274 00000160 T main                                       ← 位址 0x10000274，大小 0x160 = 352 bytes
20002258 00002000 b reply                                      ← 0x2000... = RAM 裡的 8 KB 陣列
200003a8 00000510 t dcd_rp2040_irq                             ← 函式在 0x2000... = 放在 RAM 執行 (比較快)
main
/w/pico/app_serial.c:62                                       ← addr2line 的結果
```
| 位址開頭 | 在哪裡 | 說明 |
|---|---|---|
| `0x10000000` | FLASH（4 MB，`xr`） | 程式碼、const 資料 |
| `0x20000000` | RAM（512 KB） | 變數、stack、heap；`__not_in_flash_func(f)` 的函式也在這 |
| `0x20080000` / `0x20081000` | SCRATCH_X / SCRATCH_Y（各 4 KB） | core1 / core0 的 stack |

`.map` 檔開頭的 `Memory Configuration` 就是上面這張表；搜尋函式名稱可以看到它是從哪個 `.o` 來的：
```
 .text.proto_feed
                0x10000480      0x1c0 CMakeFiles/app_serial.dir/serial_proto.c.o
```
用途：確認某個函式是不是真的在 RAM（`time_critical`）、找出把 RAM 吃光的大陣列、確認最佳化後函式還在不在（被 inline 掉就找不到了）。
HardFault 時如果你有拿到 PC 的值（例如用除錯器看到），用 `addr2line` 換成行號。

## 6. 有 Debug Probe（CMSIS-DAP）的話【⚠ 沒有實測：這裡沒有 probe】

接線：probe 的 SC → SWCLK、SD → SWDIO、GND → GND（板子底端的 3 pin DEBUG 接頭）；UART 線接 GP0/GP1。
官方文件的指令（RP2350 用 `target/rp2350.cfg`；RISC-V 核心用 `target/rp2350-riscv.cfg`，這個名稱是推測，請先 `ls` 確認）：
```bash
# 直接燒錄（不用按 BOOTSEL）
openocd -f interface/cmsis-dap.cfg -f target/rp2350.cfg -c "adapter speed 5000" \
        -c "program build/app.elf verify reset exit"
# 開 GDB server（第 1 個終端機，保持開著）
openocd -f interface/cmsis-dap.cfg -f target/rp2350.cfg -c "adapter speed 5000"
# 第 2 個終端機
gdb-multiarch build/app.elf          # 或 arm-none-eabi-gdb；主機內建的 gdb 只有 x86（實測：會把 ARM 程式碼反組譯成 x86）
(gdb) target extended-remote :3333   # 官方文件寫 target remote localhost:3333，兩個都可以
(gdb) monitor reset init
(gdb) load
(gdb) break main
(gdb) continue
(gdb) bt / p 變數 / info registers   # 跟 debug-host.md 一樣
```
- 要用 Debug build（`-DCMAKE_BUILD_TYPE=Debug`），不然很多變數會是 `<optimized out>`。
- 官方文件寫 `sudo openocd`（沒裝 udev rules 時要 sudo）。
- 這台主機和 pico-build 都**沒有** openocd、gdb-multiarch、arm-none-eabi-gdb。考場先 `which openocd gdb-multiarch arm-none-eabi-gdb`。
- 卡死、連不上（程式把時脈關掉了）：官方的 `target/rp2350-rescue.cfg` 可以把晶片重設成可以連線的狀態。

## 7. 板子的症狀 → 原因

| 症狀 | 先檢查 | 常見原因 |
|---|---|---|
| 沒有 `/dev/ttyACM*` | `dmesg`、LED、`lsusb` | 沒開 `pico_enable_stdio_usb`；程式在 USB 初始化前就當了；USB 線只能充電；板子還在 BOOTSEL（出現的是隨身碟） |
| 有 ttyACM 但沒有輸出 | 換個監看程式、重新打開 | 開頭的 printf 在電腦開序列埠前就送了（§4 WAIT_TIMEOUT）；`printf` 沒有 `\n` 還在緩衝；被別的程式搶走了 |
| 輸出亂碼 / 二進位資料被改 | 用 `xxd` 看原始 bytes | `0x0a` 被改成 `0d 0a` → `PICO_STDIO_DEFAULT_CRLF=0`；printf 混進封包；UART 的 baud 不一致 |
| 跑一下就停 / 卡住 | LED 還有沒有在閃 | panic / HardFault；stack 爆了（大陣列放在區域變數 → 改成 `static`）；`getchar()` 在等資料；死結 |
| 第一次正常，第二次就壞 | 拔插後重測 | 全域變數 / 狀態機沒有重設；接收緩衝區有上一次剩下的資料（電腦端先 `reset_input_buffer()`）；DMA channel 沒有釋放 |
| 偶爾資料錯 | 收發的長度、校驗 | USB 一次只收到一部分（要用迴圈收滿 N bytes）；雙核心 race（用 `pico_sync`）；沒有 `__dmb()` |
| 很慢 | 量時間 | 每個 byte 一次 `getchar`/`putchar`（改成整塊讀寫）；USB 封包太小；`printf` 太多 |
| 燒進去完全沒反應 | `picotool info -a x.uf2` | 燒錯平台（`rp2350-riscv` vs `arm-s`）；`PICO_BOARD` 不是 pico2；拖進去的是舊的 uf2 |
