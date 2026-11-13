# 規格卡：pico/（Pico 2 RP2350 的 pico-sdk 範本）
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：E02（規格卡 PICO）。每張 ≤ 1200 字元。
> 來源：`預製程式碼/說明書/03-pico.md`、`預製程式碼/pico/` 原始碼（行號已用 grep -n / sed -n 核對）｜最後更新 2026-11-13

---

【規格卡｜PICO 1/14｜總覽：檔案、題型、驗證狀態】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
資料夾 `預製程式碼/pico/`（Pico 2 = RP2350，pico-sdk 2.x），下面檔名都相對於它。
| 檔案 | 行數 | 做什麼 / 題型 |
|---|---|---|
| `CMakeLists.txt` | 52 | 一個專案編 5 個 app，stdio 走 USB |
| `serial_proto.h`/`.c` | 47/101 | 封包格式、狀態機、軟體 CRC32 |
| `app_serial.c` | 88 | USB 二進位伺服器：電腦送資料、板子算 |
| `app_multicore.c` | 137 | race 示範+鎖、queue 派工（雙核、pipeline） |
| `app_dma.c` | 141 | DMA copy/fill/sniffer CRC32/比速度 |
| `app_dma_pio.c` | 99 | DMA 依 DREQ 餵 PIO echo |
| `app_pio.c` | 110 | PIO echo、shift_out→bitstream_in 回環 |
| `pio/echo.pio`、`bitstream_in.pio`、`shift_out.pio` | 26/35/34 | PIO 程式 |
| `timing.h` | 69 | 量時間：`PRINT_US`、`cycles_*`、`speedup` |
| `README.md` | 168 | 小抄、13 條陷阱、審查紀錄 |
另有 `pico_sdk_import.cmake`（121 行，SDK 原檔，不用改）。
連接：`serial_proto` ↔ 電腦 `ros2/frame.py`（同封包格式）；`echo.pio` 給 `app_pio`、`app_dma_pio` 共用；`timing.h` 給 4 個印字的 app。
驗證：5 個 app 在電腦上編譯通過（ARM SDK 2.2.0、2.1.1 都 0 warning；RISC-V 用替代工具鏈）；serial 在電腦上模擬測過；**沒有程式在板子上跑過**。
最常改：`app_serial.c:51`（新指令）、`app_multicore.c:80`（core1 計算）、`app_dma.c:27`、`app_dma_pio.c:34`（資料量）。全部 TODO：`grep -n "TODO(改這裡)" *.c *.h pio/*.pio CMakeLists.txt`。
考場第一件事：燒 `app_dma.uf2`，看 sniffer 那行是 PASS。
要看程式：見各列的行號

---

【規格卡｜PICO 2/14｜CMakeLists.txt：target 與編譯指令】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`add_app()`（:19-26）：連 `pico_stdlib`、stdio 走 USB、產生 .uf2/.dis。`PICO_BOARD` 預設 `pico2`（:9-11）。
| target | 行 | 額外 |
|---|---|---|
| `app_serial` | 29-32 | +serial_proto.c、`PICO_STDIO_DEFAULT_CRLF=0`、`pico_multicore` |
| `app_multicore` | 35-36 | `pico_multicore pico_sync` |
| `app_dma` | 39-40 | `hardware_dma` |
| `app_dma_pio` | 43-45 | `hardware_dma hardware_pio`、echo.pio |
| `app_pio` | 48-52 | `hardware_pio`、3 個 .pio |
ARM（預設 `rp2350-arm-s`，最穩）：
```bash
export PICO_SDK_PATH=<含 pico_sdk_init.cmake 的資料夾>
mkdir -p build && cd build
cmake -DPICO_BOARD=pico2 ..
make -j4        # 單一個：make -j4 app_serial
```
RISC-V：另開 `build-rv`，`cmake -DPICO_BOARD=pico2 -DPICO_PLATFORM=rp2350-riscv ..`。SDK 2.2.0 只找 `riscv32-unknown-elf-gcc`/`riscv32-corev-elf-gcc`，找不到→用 ARM。
SDK：`dma_encode_transfer_count` 2.2.0 才有；`app_dma.c:21-24`、`app_dma_pio.c:26-29` 在 <2.2 補一個直接回傳 n 的版本。
沒網路：cmake 會下載 picotool 失敗→加 `-Dpicotool_DIR=<picotool 資料夾>`。
燒錄：按住 BOOTSEL 插 USB→`.uf2` 複製到 `RP2350`；或 `picotool load -x app.uf2 -f`。看輸出：`screen /dev/ttyACM0 115200`。新 app 照 `add_app` 加一段。
要看程式：請操作者貼「cat -n CMakeLists.txt | sed -n 19,52p」

---

【規格卡｜PICO 3/14｜serial_proto.h/.c：封包、狀態機、CRC32】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
封包（小端）：`AA 55 | cmd u8 | seq u8 | len u16 | payload[len] | crc32 u32`，總長 10+len。crc32=zlib CRC-32，範圍 cmd～payload 尾（不含 AA 55）。回覆同 cmd、seq。
`.h`：`SYNC0/1`（14-15）；`CMD_ECHO` 0x01、`CMD_SUM_U32` 0x02、`CMD_CRC32` 0x03（18-20；TODO 在 17）；`FRAME_MAX_PAYLOAD`=8192（23；TODO 在 22；len 是 u16）；`frame_t`（25-30）= cmd、seq、len、`payload[8192]`。
| 函式（.c） | 行號 | 做什麼 |
|---|---|---|
| `crc32_make_table` | 14-22 | `constructor`：`main()` 前在 core0 建好表，兩核同時用也安全 |
| `crc32_update(crc,p,n)` | 25-30 | `weak`：專案另有 `algo/crc32.c` 就用那份（不會 multiple definition）。第一段 crc 給 0，可分段；`"123456789"`→0xCBF43926 |
| `proto_feed(b,f)` | 39-76 | 一次一 byte；1=完整且 CRC 對（在 *f）、0=未完、-1=壞包 |
| `proto_reset`/`proto_busy` | 78/79 | 回 WAIT_AA / 1=收到一半 |
| `proto_send(cmd,seq,p,len)` | 92-101 | 加表頭與 crc；`stdio_put_string(..,false,false)` 送原始 bytes＋`stdio_flush()` |
狀態機：`WAIT_AA`→(AA)→`WAIT_55`→(55)→`HEADER` 收 4 bytes→len>8192 回 -1；len=0 直接 `CRC`；否則 `PAYLOAD` 收 len bytes→`CRC` 收 4 bytes 比對。WAIT_55 收到 AA 留著（`AA AA 55` 能對齊），其他回 WAIT_AA。CRC 後都回 WAIT_AA。
限制：len>8192 整包丟掉不回；電腦端 `CHUNK_BYTES`=4096（須 ≤8192）。
要看程式：請操作者貼「cat -n serial_proto.c | sed -n 33,79p」

---

【規格卡｜PICO 4/14｜app_serial.c：指令分派、加新指令】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
不印任何文字（printf 會混進二進位）；除錯用 LED（:80）。全域 `static frame_t rx`、`reply[8192]`（:19-20）。
| 段落 | 行號 | 內容 |
|---|---|---|
| `handle` ECHO | 26-28 | 原樣 `proto_send`（`handle(f)` 24-57） |
| SUM_U32 | 30-42 | n=len/4（尾巴 1~3 byte 忽略）；`memcpy` 取 u32；和 mod 2^32 回 4 bytes |
| CRC32 | 44-49 | `crc32_update(0,payload,len)`，回 4 bytes |
| default | 54-55 | 不認得的 cmd 不回 |
| `main` | 59-82 | 不等 USB 連線 |
主迴圈 :69-81：`stdio_get_until(buf,512,make_timeout_time_us(1000))`→每 byte `proto_feed`→回 1 就 `handle`、回 -1 就 `n_bad++`（:78）；收到一半且閒置 >100 ms→`proto_reset()`（:73-74）。
TODO：:32 長度檢查；:37 `sum += v` 換計算；:51-52 新指令；:78 回 NACK（CRC 錯時 `rx.seq` 可能錯）。
加新指令（例 0x04 排序）：
1. `serial_proto.h:20` 下加 `#define CMD_SORT_U32 0x04`
2. `app_serial.c:51` 前加 `case CMD_SORT_U32: { …; proto_send(f->cmd, f->seq, 結果, 長度); break; }`，結果陣列用 `static`
3. 電腦端 `ros2/frame.py:17` 加同一個數字
4. 回覆長度 ≤8192
CRLF 關法：CMake :31、`stdio_set_translate_crlf(&stdio_usb,false)`（:61）、送出用 `stdio_put_string(..,false,false)`。
預期（⚠️沒上板；電腦模擬實測）：ECHO `b"hello"`→`b'hello'`；SUM `[1,2,3]`→6；CRC32 `b"123456789"`→0xcbf43926；未知 cmd 沒回覆。
要看程式：請操作者貼「cat -n app_serial.c | sed -n 24,82p」

---

【規格卡｜PICO 5/14｜app_multicore.c：鎖、FIFO、queue pipeline】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 名稱 | 行號 | 內容 |
|---|---|---|
| `N_ADD` | 21 | 200000 每核次數 TODO |
| `counter`/`lock_mode` | 27-28 | volatile；`add_many()`（32-49）依 0=不鎖（錯）、1=spinlock、2=critical_section 加 |
| `job_t`/`result_t` | 52-53 | `{id,data,n}`/`{id,sum}` TODO |
| `core1_main` | 64-85 | 等 FIFO `CMD_RACE`=1/`CMD_WORKER`=2，回 `DONE`=0xD0E；:80 計算 TODO |
| `main` | 87-137 | :92-95 鎖、cs、兩 queue 各 8 格；:96 啟動 core1；:116 `N_JOBS`=16 |
鎖：`spin_lock_init(spin_lock_claim_unused(true))`；`save=spin_lock_blocking(l)`…`spin_unlock(l,save)` 關中斷+忙等，`critical_section_*` 同；`mutex_t` 可久、不能在 IRQ；`queue_t` 內建鎖（推薦）。core1 啟動前 init。
FIFO：`multicore_fifo_push/pop_blocking` 傳 u32，RP2350 每方向深度 4，SDK 也用它→資料改用 queue。
pipeline（:114-134）：core0 填 `data_buf[sent%4]`→`q_job`→core1 算→`q_result`→core0 `queue_try_remove`。`sent-got<4` 才不會蓋到算到一半的 buffer；`data==NULL`=停。
縮小臨界區：鎖裡只留改共用變數那行；先 `local += …`（不鎖），最後鎖一次 `counter += local`。core1 stack 2 KB→大陣列 static。
預期（⚠️沒上板）：`不鎖(錯誤示範) counter=<小於 400000>`；spinlock、critical_section 兩行 `counter=400000 (應為 400000)`；`worker: 16 jobs, total=8503296`。
要看程式：請操作者貼「cat -n app_multicore.c | sed -n 32,85p」

---

【規格卡｜PICO 6/14｜app_dma.c：5 步、channel_config、count】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`dma_xfer(to,from,count,size,rinc,winc)`（:31-45）＝claim→config→start→wait→unclaim，回 0/-1 沒通道/-2 太大：
| 行 | 呼叫與說明 |
|---|---|
| 33-34 | count==0 回 0；>0x0FFFFFFF 回 -2 |
| 35-36 | `dma_claim_unused_channel(false)`：沒有回 -1（true=panic）；:36 TODO 改 CPU 做 |
| 37-38 | `dma_channel_get_default_config(ch)`；`channel_config_set_transfer_data_size(&c,size)`：`DMA_SIZE_8/16/32`=1/2/4 bytes |
| 39-40 | `channel_config_set_read_increment` / `_write_increment(&c,b)` |
| 41 | `dma_channel_configure(ch,&c,寫位址,讀位址,dma_encode_transfer_count(count),true)`：先 dst 後 src；true=立刻開始 |
| 42-43 | `dma_channel_wait_for_finish_blocking(ch)`（等 BUSY=0）→`dma_channel_unclaim(ch)`（一定要還） |
預設：32-bit、讀遞增 true、寫遞增 **false**、`DREQ_FORCE` 全速、chain_to=自己（不串）、sniff/ring/bswap 關。
`dma_copy32`（:46）讀寫都遞增；`dma_fill32`（:47-50）讀不遞增、值放 `static v`。
count=傳輸次數，不是 bytes。RP2350 TRANS_COUNT 低 28 bits=次數、[31:28]=MODE（0 一般、1 自己重啟、F 無限）。2.2.0 `dma_encode_transfer_count` 做 `n & 0x0FFFFFFF`；2.0/2.1 補丁直接回 n→n 須 <2^28。
背景搬（:129-138）：start 後 CPU 先做事（:134 TODO），用 dst 前才 wait。`N_WORDS`=4096（:27 TODO）。
要看程式：請操作者貼「cat -n app_dma.c | sed -n 31,50p」

---

【規格卡｜PICO 7/14｜app_dma.c：sniffer CRC32、預期輸出】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
`dma_crc32(p,nbytes)`（:65-87）＝zlib `crc32`：
1. nbytes==0 回 0（:66）
2. `dma_claim_unused_channel(true)`（:67，會 panic）；寫到 `static volatile uint8_t sink`
3. `DMA_SIZE_8`、讀遞增、寫不遞增（:70-72）
4. 先設 sniffer：`dma_sniffer_set_data_accumulator(0xFFFFFFFF)`（:73）→`dma_sniffer_set_output_reverse_enabled(true)`（:74）→`dma_sniffer_enable(ch,DMA_SNIFF_CTRL_CALC_VALUE_CRC32R,false)`（:76，不會清 OUT_REV）→`channel_config_set_sniff_enable(&c,true)`（:77，一定要）
5. `dma_channel_configure(ch,&c,&sink,p,dma_encode_transfer_count(nbytes),true)`+wait（:79-80）
6. `dma_sniffer_get_data_accumulator() ^ 0xFFFFFFFF`（:81）→`dma_sniffer_disable()`（:84，全晶片一組）→unclaim
不要分段續算（寫回初值是否受 OUT_REV 影響未知）。對照組 `cpu_crc32`（:90-94）。
FAIL 看值：`649c2fd3`=少反轉→:74 改 false；`340bc6d9`=多 XOR→拿掉 :81 的 `^`；其他→查 :77、順序。
預期輸出（⚠️沒上板；zlib 等價靠暫存器說明推得）：
```
copy 4096 words: loop=<t>us memcpy=<t>us dma=<t>us  正確=OK
fill: dst[0]=deadbeef dst[last]=deadbeef
crc32("123456789") dma=cbf43926 (<n> cycles) cpu=cbf43926 期望=CBF43926 PASS
crc32 16384 bytes: cpu=<t>us dma=<t>us (x<倍數>) 相同=OK
overlap: work=332833500, dma 搬完了 正確=OK
```
要看程式：請操作者貼「cat -n app_dma.c | sed -n 65,87p」

---

【規格卡｜PICO 8/14｜app_dma_pio.c：DMA + PIO（DREQ）】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 行 | 內容 |
|---|---|
| 34 | `N`=4096 個 u32（TODO，<2^28） |
| 44-49 | pio0 載入 echo（<0→印「PIO 指令空間不夠」停）、`pio_claim_unused_sm(pio,true)`、`echo_program_init` |
| 52-58 | 兩個 `dma_claim_unused_channel(false)`；任一失敗：先 unclaim 要到的，印「DMA 通道不夠」停 |
| 60-66 | ch_tx：32-bit、讀遞增、寫**不**遞增、`channel_config_set_dreq(&ctx,pio_get_dreq(pio,sm,true))`；configure 寫 `&pio->txf[sm]`、讀 src、最後參數 **false** |
| 68-73 | ch_rx：32-bit、讀**不**遞增、寫遞增、`pio_get_dreq(pio,sm,false)`；configure 寫 dst、讀 `&pio->rxf[sm]`、false |
| 77 | `dma_start_channel_mask((1u<<ch_tx) \| (1u<<ch_rx))` 同時開 |
| 78-80 | TODO CPU 做事；先 wait ch_rx 再 wait ch_tx |
| 88 | 對照組：CPU put/get |
| 94-97 | unclaim、停 SM、`pio_remove_program_and_unclaim_sm` |
DREQ：TX=FIFO 沒滿才寫；RX=有資料才讀。用 `pio_get_dreq()`（PIO0 TX0..3=0..3、RX0..3=4..7），不寫數字。沒設（DREQ_FORCE）→溢位、讀到空的。
只開 TX→RX 滿→SM 卡 push→TX 滿→ch_tx 永遠 BUSY，所以兩個一起開。
echo 用 TX 和 RX→不能 `fifo_join`（各 4 格）。DMA_SIZE_32 配 echo 門檻 32；改 8-bit 要連 .pio 門檻一起改（⚠️未驗證，建議維持 32-bit）。
預期（⚠️沒上板）：`DMA+PIO 4096 words: <t> us, 結果 OK`、`CPU put/get 4096 words: <t> us (DMA 快 x<倍數>) 結果 OK`
要看程式：請操作者貼「cat -n app_dma_pio.c | sed -n 60,80p」

---

【規格卡｜PICO 9/14｜pio/echo.pio、bitstream_in.pio：逐條指令】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
移位：OUT 左移（shift_right=false）從 bit31 拿=MSB 先，右移從 bit0。IN 左移新 bit 進 bit0，右移從 bit31 進。SDK 預設右移；範本都設左移。
**echo.pio**（0x6020、0x4020、0x8020）
| 行 | 指令 | 做什麼 / 何時停 |
|---|---|---|
| 9 | `out x, 32` | OSR→X；autopull；TX FIFO 空時停 |
| 10-12 | TODO | 可插 `mov x, ~x`（反相）、`mov x, ::x`（反轉） |
| 13 | `in x, 32` | X→ISR |
| 14 | `push` | ISR→RX FIFO（RX 滿時停） |
wrap 範圍 :8～:15；每字 ≥3 cycle。
init（:19-25）：`sm_config_set_out_shift(&c,false,true,32)`（左移、autopull、32）；`sm_config_set_in_shift(&c,false,false,32)`（autopush **關**，否則 push 兩次）；不碰 GPIO。
**bitstream_in.pio**（0x2021、0x20a1、0x4001）
| 行 | 指令 | 做什麼 |
|---|---|---|
| 8 | `wait 0 pin 1` | 等 CLK=0（pin 1=in_base+1） |
| 9 | `wait 1 pin 1` | 等 CLK 上升沿 |
| 10 | `in pins, 1` | DATA 1 bit 進 ISR；autopush 32 |
init（:19-34）：`sm_config_set_in_pins(&c,data_pin)`；`sm_config_set_in_shift(&c,false,true,32)`（左移、autopush→最先收到的 bit 在 bit31）；`sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_RX)`（RX 8 格）；clkdiv 1；`pio_gpio_init` DATA、DATA+1；**不設 pindirs**。CLK 必須=DATA+1，否則改 `wait 1 gpio N`。每 bit ≥3 cycle→送端 clkdiv ≥2。
要看程式：請操作者貼「cat -n pio/bitstream_in.pio | sed -n 6,34p」

---

【規格卡｜PICO 10/14｜pio/shift_out.pio：逐條指令】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
32-bit 一位一位送到 DATA，side-set 在 CLK 產生時脈（簡單 SPI 輸出）。pioasm：0x6101、0xb142。
| 行 | 指令 | 做什麼 / 何時停 |
|---|---|---|
| 9 | `.side_set 1` | 每條 1 bit side（CLK）；非 opt→每條都要寫 `side`；delay 最大 15 |
| 10 | `.wrap_target` | |
| 11 | `out pins, 1 side 0 [1]` | OSR 1 bit→DATA、CLK=0，共 2 cycle；TX 空時停在這（CLK 維持 0，⚠️推定） |
| 12 | `nop side 1 [1]` | CLK=1，共 2 cycle（收端在上升沿取樣） |
| 13 | `.wrap` | 回 :11 |
每 bit 4 cycle：位元速率 = clk_sys/clkdiv/4（150 MHz/10/4 = 3.75 Mbit/s）。
init `shift_out_program_init(pio,sm,offset,data_pin,clk_pin,clkdiv)`（:18-33）依序：
1. `sm_config_set_out_pins(&c,data_pin,1)`
2. `sm_config_set_sideset_pins(&c,clk_pin)`
3. `sm_config_set_out_shift(&c,false,true,32)`：左移=MSB 先、autopull、門檻 32
4. `sm_config_set_fifo_join(&c,PIO_FIFO_JOIN_TX)`：TX 8 格
5. `sm_config_set_clkdiv(&c,clkdiv)`（:25 TODO）
6. `pio_sm_set_pins_with_mask(pio,sm,0,mask)` 先設 0；`pio_sm_set_pindirs_with_mask(pio,sm,mask,mask)` 設輸出（兩腳不必相鄰）
7. `pio_gpio_init` ×2（也解除 RP2350 pad 隔離）→`pio_sm_init`→`pio_sm_set_enabled`
改 8-bit、MSB 先：:23 門檻改 8，put `(uint32_t)byte << 24`；LSB 先：改右移 true，直接 put `byte`。
要看程式：請操作者貼「cat -n pio/shift_out.pio | sed -n 8,33p」

---

【規格卡｜PICO 11/14｜app_pio.c：載入、echo 測試、回環】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
固定流程：`pio_add_program`（回 offset）→`pio_claim_unused_sm`→`xxx_program_init`（.pio 檔的 c-sdk 區塊）→`pio_sm_put_blocking`/`pio_sm_get_blocking`→用完 `pio_sm_set_enabled(false)`+`pio_remove_program_and_unclaim_sm`。RP2350：3 個 PIO、每個 4 SM、32 條指令。
| 名稱 | 行號 | 內容 |
|---|---|---|
| `DATA_PIN`/`CLK_PIN` | 21-22 | 2/3（CLK=DATA+1，TODO） |
| `load()` | 25-33 | `pio_add_program`<0 回 false；`pio_claim_unused_sm(pio,false)` 失敗先 `pio_remove_program` |
| `test_echo()` | 35-57 | pio0；4 個值 put/get（:41 TODO）；10000 字量時間；:55-56 歸還 |
| `test_loopback()` | 59-89 | pio1；第二個 load 失敗先還第一個（:63-66）；先開 bitstream_in 再開 shift_out（clkdiv 10，:69 TODO）；每字等 RX 最多 100 ms（:76-78）；:85-88 歸還兩個 |
| `main` | 91-101 | 等 USB、印 clk_sys、跑兩個測試 |
左移+MSB 先→收到的字=送出的字；同一顆晶片讀得到自己的腳，不用接線。
預期（⚠️沒上板，推算）：
```
clk_sys = 150000000 Hz
echo: 送 12345678 收 12345678      （共 4 行）
echo 10000 字: <t> us (xor=00000000)
loopback: 送 deadbeef 收 deadbeef OK   （共 4 行）
loopback: 4/4 正確
```
收到 `00000000 錯`=100 ms 內沒資料（腳位錯、CLK≠DATA+1、沒 `pio_gpio_init`）。`載入失敗`=指令空間或 SM 不夠→換 PIO 區塊或先 remove。
要看程式：請操作者貼「cat -n app_pio.c | sed -n 59,89p」

---

【規格卡｜PICO 12/14｜timing.h：ARM vs RISC-V 計時】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
header-only，`#include "timing.h"`。平台用 `#if defined(__riscv)`（:22）選。
| 名稱 | 行號 | 做什麼 |
|---|---|---|
| `PRINT_US(label,t0)` | 29-30 | 印 `[時間] %-20s %8llu us`（`time_us_64()-t0`） |
| `cycles_init()` | 33-44 | 啟動 cycle 計數器，用前呼叫一次 |
| `cycles_now()` | 47-53 | 目前值（兩平台方向不同，不要自己減） |
| `cycles_since(c0)` | 56-62 | 經過幾個 cycle |
| `speedup(slow,fast)` | 65-67 | slow/fast；fast=0 回 0 |
| 項目 | ARM Cortex-M33 | RISC-V Hazard3 |
|---|---|---|
| 計數器 | SysTick，24-bit 往下數 | `mcycle` CSR 低 32 bits，往上數 |
| init | :39-42 `csr=0`→`rvr=0xFFFFFF`→`cvr=0`→`csr=0x5`（ENABLE+CLKSOURCE） | :37 `riscv_clear_csr(0x320,1)` 清 mcountinhibit bit0 |
| 為何要 init | RVR 重置值 UNKNOWN | mcountinhibit 重置 0x5，CY 暫停 |
| 差值 | `(c0-now) & 0x00FFFFFF`（:60） | `now-c0`（:58） |
| 最長 | 2^24−1 ≈16.7M cycles ≈0.11 s @150 MHz，超過**默默繞回** | 2^32 ≈28.6 s |
CSR 寫數字 0x320：SDK 巨集會把參數直接貼進 `csrci`。SDK 不用 SysTick；自己用 SysTick 中斷時 `cycles_init` 會改掉設定。
量法：>0.1 s 用 `time_us_64()`（64-bit、1 µs）；短的用 cycles；先暖身一次；重複 N 次取平均；結果要用到（印出或存 volatile），否則可能被最佳化掉。
要看程式：請操作者貼「cat -n timing.h | sed -n 22,67p」

---

【規格卡｜PICO 13/14｜程式陷阱：看到這種寫法就照右邊改】
以下是正確的參考資料（pico-sdk 2.2.0）。和你的記憶不同時，以這張為準。函式名照抄，不要自己換。
| 程式長這樣 | 問題 | 改成 |
|---|---|---|
| 陣列複製卻 `set_write_increment(&c, false)` 或沒設 | 只寫到 dst[0] | `channel_config_set_write_increment(&c, true);` |
| configure 的 count 是 `N * 4`、`sizeof(arr)` | count 是筆數，不是 bytes | 填元素個數 `N` 或 `count_of(arr)` |
| `dma_claim_unused_channel(...)` 後面沒有 unclaim | 通道用完 → panic | wait 那行後面加 `dma_channel_unclaim(ch);`（沒有 dma_release_channel） |
| `dma_channel_configure(ch, &c, src, dst, …)` | 參數順序反了 | 先寫入位址 dst，再讀取 src |
| 兩核都 `total += …`，沒有鎖 | race，每次結果不同 | 迴圈裡加到區域變數 `uint64_t local`，迴圈後鎖一次加進 total |
| 鎖包住耗時的計算 | 另一核一直等 | 計算移到鎖外，鎖只包 `total += local;` |
| 用鎖 | — | 全域 `static spin_lock_t *lk;`，main 開頭 `lk = spin_lock_init(spin_lock_claim_unused(true));`，加總 `uint32_t s = spin_lock_blocking(lk); total += local; spin_unlock(lk, s);` |
| `scanf` / `printf` 逐筆收送數字 | 文字＋一筆一來回太慢 | 二進位批次：Pico `getchar_timeout_us` 每 4 byte 組一個 u32；電腦 `struct.pack("<%dI" % n, *nums)` 一次送 |
| 二進位回覆混了 `printf` | 電腦解不出 | 回覆用 `putchar_raw` 逐 byte 送 |
| PIO 開 autopush 又手動 `push` | 每字收兩次 | `sm_config_set_in_shift` 第 3 參數 false |
編譯錯誤看 L19-06；看不懂就【要卡】。

---

【規格卡｜PICO 14/14｜建置、通訊錯誤與驗證】
以下是正確的參考資料（預製程式碼 2026-11-13 版）。和你的記憶不同時，以這張為準。
| 症狀 | 原因 | 修法 |
|---|---|---|
| `SDK location was not specified` | 沒設 `PICO_SDK_PATH` | export 後刪 build 重跑 |
| `riscv32-unknown-elf-gcc … not found` | 沒 RISC-V 工具鏈 | 改 ARM |
| `echo.pio.h: No such file` | 少 `pico_generate_pio_header` | 加上 |
| `dma_encode_transfer_count` undeclared | SDK<2.2 | 抄 app_dma.c:21-24 |
| 電腦端 transact 逾時 | cmd 沒 case、len>8192、port 錯 | 對 cmd 數字、切小包 |
| 回覆多 `0d`、解不出 | CRLF 沒關、用 printf | 查 `app_serial.c:61`、CMake :31 |
| copy 只有 dst[0] 對 | 寫遞增預設 false | `channel_config_set_write_increment(&c,true)` |
| 搬 2/4 倍 | count 填 bytes | count=bytes÷每次大小 |
| DMA 不結束 | count≥2^28 變 MODE；DMA+PIO 只開一個通道 | n<2^28；mask 同時開 |
| claim panic/-1 | 沒 unclaim | 每個 claim 配 unclaim |
| PIO 每字收兩次 | autopush 開又手動 push | in_shift 第 3 參數 false |
| PIO 位元順序錯 | 兩端移位方向不同 | 左移=MSB 先 |
驗證（⚠️沒上板，成功的樣子）：
- `app_dma`：`crc32("123456789") dma=cbf43926 … PASS`，其他 `正確=OK`
- `app_multicore`：`spinlock … counter=400000`、`total=8503296`（不鎖也 400000→再跑、加大 N_ADD）
- `app_pio`：`loopback: 4/4 正確`；`app_dma_pio`：兩行都 `結果 OK`
- `app_serial`：`unpack_u32(transact(ser,CMD_CRC32,b"123456789"))[0] == 0xcbf43926`
要看程式：見各列的行號
