// app_serial.c — 電腦 ⇄ Pico 二進位封包伺服器（USB 序列埠）
//
// 題型：「電腦送資料給板子算（排序 / CRC / SHA / 加總…），板子回結果」
// 流程：讀 USB → proto_feed() 組封包 → handle() 依 cmd 計算 → proto_send() 回覆
//
// ⚠ 重要：這個程式「不要用 printf」！printf 的文字會混進二進位資料，電腦端會解析錯。
//    要除錯就改用 LED（gpio_put）或另外開 UART。
//
// 為什麼用 stdio_get_until() 讀：
//   - 一次可以讀「很多 byte」（getchar 一次只讀 1 個，比較慢）
//   - 有 timeout，不會卡死；SDK 內建，不用自己碰 TinyUSB
//   - 輸入方向 SDK 本來就不會轉換 \r\n（stdio_get_until 直接呼叫 driver->in_chars）；輸出方向用 stdio_put_string(.., false, false)
//     再加上 CMake 的 PICO_STDIO_DEFAULT_CRLF=0 與下面的 stdio_set_translate_crlf()，三重保險。
#include <string.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "serial_proto.h"

static frame_t rx;                    // 收到的封包（很大，放全域不要放 stack）
static uint8_t reply[FRAME_MAX_PAYLOAD];
static uint32_t n_ok = 0, n_bad = 0;  // 統計（可以用 LED 顯示）

// ---------------- 各指令的處理 ----------------
static void handle(const frame_t *f) {
    switch (f->cmd) {
    case CMD_ECHO:                                     // 原樣回傳
        proto_send(f->cmd, f->seq, f->payload, f->len);
        break;

    case CMD_SUM_U32: {                                // u32 陣列加總
        // len 不是 4 的倍數：多出來的 1~3 byte 忽略（跟 frame.py 的 unpack_u32 / fake_pico.py 一樣）
        uint32_t n = f->len / 4;                       // TODO(改這裡) 題目若要回錯誤就在這判斷
        uint32_t sum = 0;                              // uint32_t 相加自動 mod 2^32（= 電腦端 & 0xFFFFFFFF）
        for (uint32_t i = 0; i < n; i++) {
            uint32_t v;
            memcpy(&v, f->payload + 4 * i, 4);         // 用 memcpy 取 u32（合法、編譯器會變成一條 ldr）
            sum += v;                                  // TODO(改這裡) 換成題目要的計算
        }
        memcpy(reply, &sum, 4);                        // ARM / RISC-V 都是 little-endian
        proto_send(f->cmd, f->seq, reply, 4);
        break;
    }

    case CMD_CRC32: {                                  // payload 的 crc32
        uint32_t c = crc32_update(0, f->payload, f->len);  // 也可以改用 DMA sniffer（見 app_dma.c）
        memcpy(reply, &c, 4);
        proto_send(f->cmd, f->seq, reply, 4);
        break;
    }

    // TODO(改這裡) 新指令加在這裡，例如：
    // case 0x04: my_sort(...); proto_send(f->cmd, f->seq, 結果, 長度); break;

    default:
        break;                                         // 不認得的指令：不回（或回錯誤碼，看題目）
    }
}

int main(void) {
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb, false);       // 關掉 \n→\r\n（二進位必須）
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);

    // 不用等 stdio_usb_connected()：電腦會先開 port 才送封包；pyserial 開 port 預設 DTR=1 = connected。
    // ⚠ 電腦端不要把 baudrate 設成 1200！SDK 預設會因此重開進 BOOTSEL（PICO_STDIO_USB_RESET_MAGIC_BAUD_RATE）
    static uint8_t buf[512];                           // 一次最多讀 512 bytes（USB Full Speed 實際每次 <= 64）
    absolute_time_t last_rx = get_absolute_time();
    while (true) {
        // 等到「現在+1000us」這個時間點；有資料立刻回傳讀到幾個 byte，沒資料回 PICO_ERROR_TIMEOUT (-2)
        int n = stdio_get_until((char *)buf, sizeof buf, make_timeout_time_us(1000));
        if (n > 0) last_rx = get_absolute_time();
        else if (proto_busy() && absolute_time_diff_us(last_rx, get_absolute_time()) > 100000)
            proto_reset();                             // 收到一半停了 100ms（電腦端重開/垃圾）→ 重新找 AA 55
        for (int i = 0; i < n; i++) {
            int r = proto_feed(buf[i], &rx);
            if (r == 1) { n_ok++; handle(&rx); }
            else if (r < 0) n_bad++;                    // CRC 錯：丟掉（TODO(改這裡) 題目要求回 NACK 就在這回）
        }
        gpio_put(PICO_DEFAULT_LED_PIN, (n_ok >> 4) & 1);   // 收越多封包 LED 閃越快
    }
}

// ---------------- 加速想法（考試時視情況套用） ----------------
// 1) 雙核心：core0 只負責收封包，把 frame 丟進 queue_t，core1 計算 → 見 app_multicore.c
//    （注意 rx 只有一份！要用多個 buffer 輪流，否則 core1 算到一半會被 core0 覆蓋）
// 2) CRC 用 DMA sniffer 算（硬體算、CPU 空出來）→ 見 app_dma.c 的 dma_crc32()
// 3) 傳輸量才是瓶頸時：多板分工、二進位而不是文字、一次送大封包減少來回
