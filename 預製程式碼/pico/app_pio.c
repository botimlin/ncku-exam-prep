// app_pio.c — PIO 模板：echo 測試 + 位元流「送出 → 接收」自我回環測試
//
// PIO 是什麼：晶片裡的「小型可程式狀態機」，每個 cycle 執行一條指令，專門做精準的位元 I/O。
//   RP2350 有 3 個 PIO 區塊 (pio0/pio1/pio2)，每塊 4 個 SM（state machine）、32 條指令空間。
// 固定流程：
//   1 pio_add_program 把程式載入指令記憶體（回傳 offset）
//   2 pio_claim_unused_sm 要一個 SM
//   3 xxx_program_init（寫在 .pio 檔最下面的 c-sdk 區塊）設定腳位 / shift / clkdiv 並啟動
//   4 pio_sm_put_blocking 送資料進 TX FIFO；pio_sm_get_blocking 從 RX FIFO 拿資料
// .pio 檔會在 build 時由 pioasm 轉成 echo.pio.h 等標頭檔（CMake 的 pico_generate_pio_header）
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/pio.h"
#include "hardware/clocks.h"    // clock_get_hz()
#include "echo.pio.h"
#include "bitstream_in.pio.h"
#include "shift_out.pio.h"
#include "timing.h"

#define DATA_PIN 2          // TODO(改這裡) 資料腳
#define CLK_PIN  3          // TODO(改這裡) 時脈腳（bitstream_in 規定 CLK = DATA + 1）

// 載入程式 + 要一個 SM；失敗回 false
static bool load(PIO pio, const pio_program_t *prog, uint *sm, uint *offset) {
    int o = pio_add_program(pio, prog);                  // 失敗回負數（指令空間不夠等），不能直接轉 uint
    if (o < 0) return false;
    *offset = (uint)o;
    int s = pio_claim_unused_sm(pio, false);             // false = 沒空的回 -1
    if (s < 0) { pio_remove_program(pio, prog, *offset); return false; }   // 失敗也要把程式拿掉
    *sm = (uint)s;
    return true;
}

static void test_echo(void) {
    PIO pio = pio0;
    uint sm, off;
    if (!load(pio, &echo_program, &sm, &off)) { printf("echo: 載入失敗\n"); return; }
    echo_program_init(pio, sm, off);

    uint32_t test[] = { 0x12345678, 0xFFFFFFFF, 0x00000001, 0xA5A5A5A5 };  // TODO(改這裡)
    for (int i = 0; i < 4; i++) {
        pio_sm_put_blocking(pio, sm, test[i]);           // 送進 TX FIFO
        uint32_t r = pio_sm_get_blocking(pio, sm);       // 從 RX FIFO 拿回來
        printf("echo: 送 %08lx 收 %08lx\n", (unsigned long)test[i], (unsigned long)r);
    }

    // 速度測試：連續塞 N 個字（每次 put 後立刻 get，FIFO 不會塞滿）
    const int N = 10000;
    uint64_t t0 = time_us_64();
    uint32_t x = 0;
    for (int i = 0; i < N; i++) { pio_sm_put_blocking(pio, sm, (uint32_t)i); x ^= pio_sm_get_blocking(pio, sm); }
    printf("echo %d 字: %llu us (xor=%08lx)\n", N, (unsigned long long)(time_us_64() - t0), (unsigned long)x);

    pio_sm_set_enabled(pio, sm, false);
    pio_remove_program_and_unclaim_sm(&echo_program, pio, sm, off);   // 歸還（不然下次會不夠用）
}

static void test_loopback(void) {
    PIO pio = pio1;                       // 送和收放同一個 PIO 區塊（共用腳位設定比較單純）
    uint sm_rx, off_rx, sm_tx, off_tx;
    if (!load(pio, &bitstream_in_program, &sm_rx, &off_rx)) { printf("loopback: 載入失敗\n"); return; }
    if (!load(pio, &shift_out_program, &sm_tx, &off_tx)) {           // 第二個失敗：把第一個還回去
        pio_remove_program_and_unclaim_sm(&bitstream_in_program, pio, sm_rx, off_rx);
        printf("loopback: 載入失敗\n"); return;
    }

    bitstream_in_program_init(pio, sm_rx, off_rx, DATA_PIN);          // 先開接收端
    shift_out_program_init(pio, sm_tx, off_tx, DATA_PIN, CLK_PIN, 10.0f);  // TODO(改這裡) clkdiv

    uint32_t msg[] = { 0xDEADBEEF, 0x0F0F0F0F, 0x80000001, 0x12345678 };
    int ok = 0;
    for (int i = 0; i < 4; i++) {
        pio_sm_put_blocking(pio, sm_tx, msg[i]);
        uint32_t r = 0;                                  // 等最多 100ms，沒接好/沒時脈才不會永遠卡住
        absolute_time_t until = make_timeout_time_ms(100);
        while (pio_sm_is_rx_fifo_empty(pio, sm_rx) && !time_reached(until)) tight_loop_contents();
        if (!pio_sm_is_rx_fifo_empty(pio, sm_rx)) r = pio_sm_get(pio, sm_rx);
        printf("loopback: 送 %08lx 收 %08lx %s\n", (unsigned long)msg[i], (unsigned long)r,
               r == msg[i] ? "OK" : "錯");
        ok += (r == msg[i]);
    }
    printf("loopback: %d/4 正確\n", ok);

    pio_sm_set_enabled(pio, sm_tx, false);                           // 用完歸還（跟 test_echo 一樣）
    pio_sm_set_enabled(pio, sm_rx, false);
    pio_remove_program_and_unclaim_sm(&shift_out_program, pio, sm_tx, off_tx);
    pio_remove_program_and_unclaim_sm(&bitstream_in_program, pio, sm_rx, off_rx);
}

int main(void) {
    stdio_init_all();
    while (!stdio_usb_connected()) sleep_ms(50);
    sleep_ms(200);
    printf("clk_sys = %lu Hz\n", (unsigned long)clock_get_hz(clk_sys));   // PIO 速度的基準

    test_echo();
    test_loopback();

    while (true) tight_loop_contents();
}

// 小抄：常用 PIO 指令
//   out <dst>, n   從 OSR 拿 n bits（dst: pins, x, y, null, pindirs）
//   in  <src>, n   n bits 塞進 ISR（src: pins, x, y, null）
//   push / pull    ISR→RX FIFO / TX FIFO→OSR（可用 autopush/autopull 自動做）
//   mov dst, src   可加 ~（NOT）或 ::（位元反轉）
//   jmp x-- label  x 不為 0 就減 1 並跳（計數迴圈）
//   wait 0/1 pin n 等某支腳變成 0/1（n 相對 in_base；wait 0/1 gpio n 是絕對編號）
//   [n]            指令後多等 n cycles；side x 同時設 side-set 腳
