# 主機 ↔ RP2350 通訊（LITE，備援包）
用途：Linux/ROS 2 與 Pico 2 經序列埠互傳、提速。詳見 full/domain/host-mcu-comm.md。來源：pico-sdk 2.x 原始碼（pico_stdio、stdio_usb、tusb_config.h）、TinyUSB cdc_device.h、pySerial 3.5 原始碼、Linux cdc-acm/tty、man termios。最後更新 2026-11

## 連線
| 連線 | Linux | baud |
|---|---|---|
| USB CDC（stdio_usb）| /dev/ttyACM* | 無影響；**1200=重開進BOOTSEL** |
| UART+轉接器（GP0 TX/GP1 RX）| /dev/ttyUSB* 或 ACM | 兩端一致；8N1=10bit/byte→115200≈11.5KB/s |
- USB 1.1 FS 12Mbit/s、bulk 64B；UART FIFO 32B（115200 下 2.8ms 不讀就溢位）。找 port：`ls -l /dev/serial/by-id/`

## Pico 端（事實）
- CMake：`pico_enable_stdio_usb(app 1)`、`pico_enable_stdio_uart(app 0)`（預設 USB=0、UART=1；兩個都開時 USB 被 UART 拖慢）
- `stdio_usb_connected()`=看 DTR；**未連線時輸出直接丟**；主機不讀 500ms 後丟（序號才看得出）
- 預設 CRLF：`printf/putchar/puts/fwrite` 把 `\n`→`\r\n`，毀二進位。解法：`stdio_set_translate_crlf(&stdio_usb,false)`（init 後）或 `stdio_put_string(buf,len,false,false)` 或 `-DPICO_STDIO_DEFAULT_CRLF=0`
- 讀：`stdio_get_until(buf,len,until)` 有≥1byte即回（可能<len），否則 PICO_ERROR_TIMEOUT(-2)；`make_timeout_time_us(0)`=非阻塞；`getchar_timeout_us(us)`
- 2.2.0+ CDC FIFO 只有 64B（2.1.0 為 256），可 `-DCFG_TUD_CDC_TX_BUFSIZE=…` 覆寫⚠️效果需實測
- 不在 IRQ printf（鎖最多卡 1s）；stdio_init_all 在 core0
- TinyUSB：`tud_cdc_write` 回傳實寫數（要迴圈）+`tud_cdc_write_flush`；與 stdio_usb 混用可能競爭⚠️

## Linux 端
- tty 預設 ICANON/ECHO/ICRNL/ONLCR/IXON → 改資料且回送。`stty -F /dev/ttyACM0 raw -echo`（raw 不含 -echo）
- 看資料：`timeout 2 cat /dev/ttyACM0 | xxd | head`；`python3 -m serial.tools.miniterm PORT 115200 --raw`
- C：`cfmakeraw`；VMIN=0,VTIME=0 + `poll`；read/write 可能只做一部分→迴圈
- pySerial：`Serial(p,115200,timeout=0.05)` 自動 raw+DTR；timeout None=阻塞到滿,0=非阻塞,x=等x秒回部分。**`read_until/readline` 逐 byte 慢**→`s.read(max(1,s.in_waiting))` 累積自己切
- 無 pyserial：`fd=os.open(p,os.O_RDWR|os.O_NOCTTY); tty.setraw(fd)`；`select`+`os.read(fd,4096)`
- 一個 port 只能一個讀者（殘留的 cat 會搶 byte）；燒錄後重新列舉→重開 port

## 協定
- frame = COBS(header+payload+CRC16_LE)+0x00；COBS 開銷⌈n/254⌉；壞 frame 在下一個 0x00 重新同步
- COBS：`11 22 00 33`→`03 11 22 02 33 00`；`00`→`01 01 00`
- 標頭(<BBHIH)：ver,type,seq(u16 回繞,遺失=(seq-last-1)&0xFFFF),t_us,len
- CRC-16/CCITT-FALSE poly0x1021 init0xFFFF check("123456789")=0x29B1 = `binascii.crc_hqx(d,0xFFFF)`；CRC-32 0xEDB88320 check=0xCBF43926=`zlib.crc32`；DMA sniffer 可算（pico-dma.md，參數先比對⚠️）
- sync+長度法：驗證失敗只丟 1 byte 再找
- 位元組序明訂 little；C 用 put_u16le 逐 byte 序列化，不 memcpy struct；Hazard3 未對齊存取會例外
- Python `struct`：協定用 `<`；`@BIH`=10 但 C sizeof=12；`array.array('h',payload)` 一次轉
- ACK：串流用 seq 統計遺失；指令用 stop-and-wait+逾時重送+接收端去重

```c
stdio_init_all(); stdio_set_translate_crlf(&stdio_usb,false);
while(!stdio_usb_connected()) sleep_ms(10);
for(;;){ size_t u=0; for(int f=0;f<8;f++) u+=build_frame(tx+u,1,seq++,time_us_32(),pl,32);
  stdio_put_string((const char*)tx,(int)u,false,false); }
```
```python
buf+=s.read(max(1,s.in_waiting))
while (z:=buf.find(0))>=0: enc=bytes(buf[:z]); del buf[:z+1]  # cobs_decode→驗CRC→struct.unpack
```

## 效能
- UART 8N1 上限：115200→11520B/s、921600→92160B/s；USB CDC 實際吞吐必須實測⚠️
- 批次：多 frame 一次 `stdio_put_string`；或「滿 N byte 或超過 T µs」先到者送
- 文字→二進位約省一半以上；Pico 避免 putchar 迴圈；主機避免逐 byte
- 量測：吞吐=bytes/秒+ok/lost/crc 計數；RTT=PING/PONG 帶 perf_counter_ns，報 min/median/p99

## ROS 2
- serial 讀不可在 callback 阻塞：`timeout=0`+`create_timer(0.002,poll)` 讀 in_waiting；或 reader thread→Queue→timer publish
- `msg.data=array.array('h',pl)`（Int16MultiArray）；多 frame 合併成一則發布
- micro-ROS：client(MCU)+agent(主機)；Pico repo 有 jazzy 分支，預編譯庫為 cortex-m0plus，RP2350 ARM 實測可編譯連結（SDK 2.2.0）、板上執行⚠️未驗證、RISC-V 需自行重新編譯（⚠️）；考場不能裝 agent→自訂協定

## 除錯順序
port 對嗎→stdio_usb 有開→等 DTR 連線→CRLF→主機 raw→baud/接線(UART)→read 迴圈累積→位元組序/padding→seq 遺失(主機太慢/兩個讀者)
