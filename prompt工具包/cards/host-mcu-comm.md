# 貼上卡：主機 ↔ RP2350 序列通訊
> 用法（照 `../../考場SOP.md`）：模型寫【要卡】編號時，到 `../編號卡/` Ctrl-F 那個編號複製這張卡，包在 `<<<資料 開始>>>`…`<<<資料 結束>>>` 裡、最後一行寫「繼續」再貼。本檔編號：L09（參考卡 主機↔MCU）。每張 ≤ 1200 字元。
> 來源：full/domain/host-mcu-comm.md、lite/domain/host-mcu-comm.md（詳細版）｜最後更新 2026-11

---

【參考卡｜主機↔MCU 1/8｜除錯清單：症狀 → 修正】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：RP2350（Pico 2），非 RP2040；pico-sdk 2.x；Linux 主機。
建議順序：port 對嗎 → stdio_usb 有開 → 等 DTR 連線 → CRLF → 主機 raw → baud/接線（UART）→ read 迴圈累積 → 位元組序/padding → seq 遺失。
- 完全收不到：開錯 port（ttyACM0 可能是 Debug Probe、板子是 ttyACM1）→ `ls -l /dev/serial/by-id/`。
- 完全收不到：沒寫 `pico_enable_stdio_usb(app 1)`（預設 USB stdio 關、UART 開）；沒在 core 0 呼叫 `stdio_init_all()`。
- 開機訊息不見：主機開 port（DTR）前的輸出被丟 → `while (!stdio_usb_connected()) sleep_ms(10);`。
- 燒錄 / 重開後一直沒資料：重新列舉，舊 fd 失效 → 程式要重開 port。
- 板子變成 USB 隨身碟：主機把 baud 設成 1200 → 進 BOOTSEL。不要用 1200。
- 二進位多出 0x0D、CRC 常錯：Pico 端 CRLF 轉換沒關（printf / fwrite 會轉）。
- 收到 0x0D 變 0x0A、資料被回送、要等換行：主機 tty 不是 raw → `stty -F /dev/ttyACM0 raw -echo`。
- 亂碼（UART）：兩端 baud 不一致、TX/RX 沒交叉、沒共地。
- 要 100 byte 只拿到 37：read 本來就可能回傳較少 → 迴圈累積給 parser。
- 不定期少資料、seq 跳號：主機讀太慢（裝置 500 ms 逾時丟棄），或兩個程式同時讀同一 port（殘留的 cat）。
- 輸出只有 ~11 KB/s：USB 與 UART stdio 同時開，被 UART 拖慢 → `pico_enable_stdio_uart(app 0)`。
- 印到一半卡 ~1 s：在 IRQ 中 printf。
- ROS 2 node 其他 callback 不跑：serial read 在 callback 中阻塞。
- 數值怪（大小顛倒、差 256 倍）：位元組序 / struct padding 不一致 → 協定一律 `<`。
- RISC-V 例外、ARM 正常：`(uint32_t *)` 指向未對齊位址 → 用 memcpy。
看原始位元組：`timeout 2 cat /dev/ttyACM0 | xxd | head -20`。

---

【參考卡｜主機↔MCU 2/8｜Pico 端 stdio 設定與 CRLF】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：RP2350（Pico 2），非 RP2040；pico-sdk 2.x 原始碼確認。
CMake：
```cmake
pico_enable_stdio_usb(app 1)    # USB CDC → /dev/ttyACM*
pico_enable_stdio_uart(app 0)   # 關掉 UART stdio
```
- 預設 USB stdio = 0、UART stdio = 1。兩個都開時輸出送到所有 driver，USB 會被 115200 的 UART 拖到 ~11.5 KB/s。
- `stdio_usb_connected()` 看 DTR；未連線時輸出直接丟；主機不讀時 TX FIFO 滿超過 500 ms 就丟（只有序號看得出）。
- 2.2.0 起 CDC FIFO 只有 64 B（2.1.0 是 256），可用 `CFG_TUD_CDC_TX_BUFSIZE` 覆寫（效果 ⚠️未驗證）。
- 不要在 IRQ 中 printf（鎖最多等 1 s）；`stdio_init_all()` 在 core 0 呼叫。
CRLF：預設輸出把 `\n`（0x0A）變 `\r\n`，毀二進位。printf / putchar / puts / fwrite 都會轉。關法擇一：
```c
stdio_set_translate_crlf(&stdio_usb, false); // stdio_init_all 之後；#include "pico/stdio_usb.h"
stdio_put_string((const char *)buf, (int)len, false, false); // raw 寫
// 或 CMake：target_compile_definitions(app PRIVATE PICO_STDIO_DEFAULT_CRLF=0)
```
- 若編譯時 `PICO_STDIO_ENABLE_CRLF_SUPPORT=0`，呼叫 `stdio_set_translate_crlf` 會 panic。
讀取：
- `stdio_get_until(buf, len, until)`：有 ≥1 byte 就回傳數量（可能 < len），否則 `PICO_ERROR_TIMEOUT`（-2）。`make_timeout_time_us(0)` = 非阻塞。
- `getchar_timeout_us(us)`：回 0–255 或 PICO_ERROR_TIMEOUT。`getchar` 永遠阻塞。

---

【參考卡｜主機↔MCU 3/8｜Linux 端：raw tty、pySerial、標準庫】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：Linux 主機，Pico 2（RP2350）USB CDC = /dev/ttyACM*；UART 轉接器 = /dev/ttyUSB* 或 ACM。
- USB CDC 的 baud 不影響速度（但 1200 = 板子重開進 BOOTSEL，不要用）；UART 兩端 baud 必須一致。
- tty 預設 ICANON / ECHO / ICRNL / ONLCR / IXON → 改資料且回送給裝置。一定要 raw：`stty -F /dev/ttyACM0 raw -echo`（raw 不含 -echo）；檢查 `stty -F /dev/ttyACM0 -a`。
- 看資料：`timeout 3 cat /dev/ttyACM0 | xxd | head`。
- 一個 port 只能一個讀者；燒錄後重新列舉 → 重開 port。關 port 放掉 DTR → Pico 輸出被丟。
pySerial 3.5（自動設 raw、拉 DTR）：
```python
import serial
s = serial.Serial('/dev/ttyACM0', 115200, timeout=0.05)
buf += s.read(max(1, s.in_waiting))  # 有多少拿多少，累積到 bytearray 再切 frame
```
- timeout=None 阻塞到讀滿；0 非阻塞；x 秒回傳已收到的部分（可能空）。
- `read_until` / `readline` 內部逐 byte 讀，高速下很慢。
- 開啟後 `s.reset_input_buffer()` 丟殘留。
沒有 pyserial（標準庫）：
```python
import os, termios, tty, select
fd = os.open('/dev/ttyACM0', os.O_RDWR | os.O_NOCTTY)
tty.setraw(fd)
termios.tcflush(fd, termios.TCIFLUSH)
r, _, _ = select.select([fd], [], [], 0.05)  # 最多等 50 ms
data = os.read(fd, 4096) if r else b''       # 可能 < 4096
os.write(fd, b'\x01\x02\x00')                # 回傳實際寫入數，要迴圈
```
C：`cfmakeraw`；VMIN=0、VTIME=0 + `poll`；read / write 要迴圈。

---

【參考卡｜主機↔MCU 4/8｜協定框架：COBS 與標頭】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
適用：Pico 2（RP2350）↔ Linux 的二進位串流。
建議 frame = COBS( header + payload + CRC16_LE ) + 0x00。
COBS 規則：把資料切成「最多 254 個非零 byte + 一個 0」的組；每組前放一碼 = 該組非零 byte 數 + 1，刪掉那個 0；碼 0xFF = 254 個非零、後面沒有隱含的 0。最後補 0x00 當分隔。開銷 ⌈n/254⌉ B + 1。壞 frame 在下一個 0x00 重新同步。
範例：
- `00` → `01 01 00`
- `00 00` → `01 01 01 00`
- `11 22 00 33` → `03 11 22 02 33 00`
- `11 22 33 44` → `05 11 22 33 44 00`
- `11 00 00 00` → `02 11 01 01 01 00`
標頭（10 B，little-endian，Python `struct.Struct('<BBHIH')`）：
- 0 u8 ver：協定版本，不認得就丟
- 1 u8 type：1=SAMPLE、2=PING、3=PONG、4=CMD
- 2 u16 seq：16-bit 回繞；遺失數 = `(seq - last - 1) & 0xFFFF`；每種 type 各自計數
- 4 u32 t_us：裝置 `time_us_32()`（約 71.6 分鐘回繞），主機可算實際取樣率與 jitter
- 8 u16 len：payload 長度，與實際長度比對
- 10+len u16：CRC-16，涵蓋 offset 0..10+len-1
其他框架：SLIP（END=0xC0，0xC0→DB DC、0xDB→DB DD，最壞 2 倍）；sync+長度（`AA 55 len payload crc`，驗證失敗只丟 1 byte 再找 sync，必須有 CRC，max_len 越小越好）；固定長度不建議（錯一個 byte 之後全錯位）。
文字 vs 二進位：除錯用文字（printf + 主機 split）；效能用二進位（16 個 int16 約 46 B vs 文字 32–112 B）。兩者不要混在同一條串流。
ACK：感測串流只用 seq 統計遺失；指令用 stop-and-wait + 逾時重送（逾時 > RTT p99）+ 接收端依 seq 去重。USB CDC 線路錯誤極少，真正會丟的是緩衝溢位 / 逾時丟棄 / 重新列舉。

---

【參考卡｜主機↔MCU 5/8｜CRC、位元組序、struct】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
適用：Pico 2（RP2350，ARM 與 RISC-V 皆 little-endian）↔ Linux（也是 little-endian）。
CRC-16/CCITT-FALSE：poly 0x1021、init 0xFFFF、不反射、xorout 0；check("123456789") = 0x29B1。
```c
uint16_t crc16_ccitt(const uint8_t *p, size_t n) {
  uint16_t crc = 0xFFFF;
  while (n--) {
    crc ^= (uint16_t)(*p++) << 8;
    for (int i = 0; i < 8; i++)
      crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  }
  return crc;
}
```
- Python：`binascii.crc_hqx(data, 0xFFFF)`（init 0 則是 CRC-16/XMODEM）。
- CRC-32（zlib）：反射 poly 0xEDB88320、init / xorout 0xFFFFFFFF；check = 0xCBF43926 = `zlib.crc32(data)`。
- 兩端參數必須完全一致，先用 "123456789" 互驗。RP2350 DMA sniffer 可算 CRC，但與軟體版一致所需的 seed / invert / reverse 組合 ⚠️未驗證，先比對 check 值。
位元組序：
- 協定明訂 little-endian；C 端逐 byte 序列化（`p[0] = (uint8_t)v; p[1] = (uint8_t)(v >> 8);`），不 memcpy struct。
- `struct { uint8_t a; uint32_t b; uint16_t c; }` 的 sizeof = 12；packed = 7。Hazard3 對未對齊 load/store 產生例外。
Python struct：
- `<` little、不對齊（協定用這個）；`@`（預設）有對齊但結尾不補：`struct.calcsize('@BIH')` = 10，與 C 的 12 不同；`'<BIH'` = 7。
- `array.array('h', payload)` 一次把 bytes 變 int16 陣列（本機序 = little）。

---

【參考卡｜主機↔MCU 6/8｜吞吐量、延遲與優化】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：RP2350（Pico 2），非 RP2040；pico-sdk 2.x；Linux 主機。
上限計算：
- UART 8N1 = 10 bit/byte：115200 → 11,520 B/s（32 B RX FIFO 2.78 ms 填滿）；921600 → 92,160 B/s。
- USB CDC：USB 1.1 Full Speed 12 Mbit/s、bulk 封包 64 B、每 1 ms 一個 frame；理論約 1.2 MB/s ⚠️未驗證；實際受 tud_task 頻率、FIFO（2.2.0+ 64 B）、flush 影響，必須實測。baud 設定不影響 CDC 速度。
延遲來源：tud_task 週期（≤ 1 ms）、批次等待、主機 read timeout、ROS 2 timer 週期。
取捨：累積滿一塊再送 → 吞吐高延遲高；每筆立刻送 → 延遲低吞吐低。折衷：「滿 N byte 或超過 T µs」先到者送：
```c
if (used >= 1024 || (used && time_us_32() - t_first >= 2000)) {
    stdio_put_string((const char *)txbuf, (int)used, false, false);
    used = 0;
}
```
優化清單（大→小）：
1. 先量：吞吐 bytes/s、frames/s 加 ok / lost / crc 計數；RTT 用 PING/PONG，報 min / median / p99。
2. 關掉不需要的 stdio driver（UART 與 USB 同開會被拖慢）。
3. 文字 → 二進位，Pico 省掉 printf 格式化。
4. 批次寫出：多個 frame 一次 `stdio_put_string`；主機一次 `read(in_waiting)`。
5. 避免逐 byte API：Pico 不用 putchar 迴圈；主機不用 read_until / readline / read(1)。
6. 增大 CDC FIFO（`CFG_TUD_CDC_TX_BUFSIZE`）⚠️效果請實測。
7. 主機：`struct.Struct` 預編譯、`array.array('h', payload)`、多 frame 併一則 ROS 訊息。
8. 延遲優先：減小批次、reader thread + 小 timeout。
9. UART：提高 baud（兩端同改），接收用 IRQ / DMA。
每次優化後重量，確認 crc / cobs / lost 沒增加（快但錯 = 0 分）。

---

【參考卡｜主機↔MCU 7/8｜ROS 2 橋接 node】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：ROS 2 Jazzy rclpy + pySerial，Pico 2（RP2350）。parser.feed(bytes) 回傳 (type, seq, t_us, payload) 清單。
serial 讀取不可在 callback 中阻塞（會卡住其他 callback）。
方案 A：timer 非阻塞輪詢：
```python
self.ser = serial.Serial(port, 115200, timeout=0)    # read 立即返回
self.pub = self.create_publisher(Int16MultiArray, 'pico/samples', 10)
self.timer = self.create_timer(0.002, self.poll)

def poll(self):
    n = self.ser.in_waiting
    if n == 0:
        return
    for typ, seq, t_us, pl in self.parser.feed(self.ser.read(n)):
        if typ == 1:
            msg = Int16MultiArray()
            msg.data = array.array('h', pl)   # int16[] 底層就是 array('h')
            self.pub.publish(msg)
```
方案 B：reader thread（延遲較低）：`timeout=0.05`，迴圈 `ser.read(max(1, ser.in_waiting))` 後 feed。從非 executor 執行緒 publish ⚠️未驗證執行緒安全；保守做法：thread 只放進 `queue.Queue`，timer 取出 publish。
- 每秒上千個 frame 時 ROS 2 發布成本變瓶頸 → 多 frame 合併成一則訊息。
- host→MCU：subscription callback 內 build_frame 後 `ser.write(...)`。
micro-ROS：官方 Pico repo 的預編譯庫是 cortex-m0plus（RP2040）；RP2350 ARM 實測可編譯連結（SDK 2.2.0），板上執行 ⚠️未驗證；RISC-V 不能用。考場不能裝 agent → 自訂協定 + rclpy 橋接。

---

【參考卡｜主機↔MCU 8/8｜最小收發範例】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
環境：RP2350（Pico 2），非 RP2040；pico-sdk 2.x。⚠️ Pico 端未在真板子上編譯過，先驗證。
Pico 端（批次送 8 個 frame，一次寫出）：
```c
stdio_init_all();
stdio_set_translate_crlf(&stdio_usb, false); // 二進位資料：關掉 \n -> \r\n
while (!stdio_usb_connected()) sleep_ms(10); // 等主機開 port（DTR 拉高）
for (;;) {
  size_t used = 0;
  for (int f = 0; f < 8; f++)
    used += build_frame(txbuf + used, 1, seq++, time_us_32(), pl, 32);
  stdio_put_string((const char *)txbuf, (int)used, false, false);
}
```
（build_frame = 寫 10 B 標頭 + payload + CRC16_LE，再 COBS 編碼並補 0x00。）
Pico 端非阻塞讀：`int k = stdio_get_until(in, sizeof in, make_timeout_time_us(0));`，逐 byte 累積到 0x00 為一個 frame（k<0 時不處理）。
主機端解析迴圈：
```python
buf += s.read(max(1, s.in_waiting))
while (z := buf.find(0)) >= 0:
    enc = bytes(buf[:z]); del buf[:z + 1]
    if not enc: continue                 # 連續 0x00
    # cobs_decode(enc) → 驗 CRC16（binascii.crc_hqx(body, 0xFFFF)）
    # → struct.Struct('<BBHIH').unpack_from(body, 0) → 檢查 ver 與 len
    # → lost += (seq - last_seq[typ] - 1) & 0xFFFF
```
- buf 超過最大 frame 長度仍無 0x00 就清掉。開頭 1–2 個壞 frame 正常。
- 先用文字 `printf("alive %u\n", n++)` 確認連線再切二進位；loopback echo 程式可分離主機與 Pico 問題。
