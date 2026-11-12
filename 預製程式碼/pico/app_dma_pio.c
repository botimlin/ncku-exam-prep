// app_dma_pio.c — DREQ 節奏的 DMA：記憶體 → PIO TX FIFO → (echo 程式) → PIO RX FIFO → 記憶體
//
// DREQ（Data REQuest）是什麼：
//   預設 DMA 用 DREQ_FORCE = 全速一直搬。但 PIO 的 FIFO 只有 4~8 格，
//   全速塞會溢位/讀到空的。設 channel_config_set_dreq(&c, pio_get_dreq(pio, sm, is_tx))
//   之後，DMA 會「FIFO 有空位才寫 / 有資料才讀」，自動跟上周邊的速度。
//
// 兩個通道：
//   ch_tx：src[] (讀遞增) → &pio->txf[sm] (寫不動)，DREQ = TX
//   ch_rx：&pio->rxf[sm] (讀不動) → dst[] (寫遞增)，DREQ = RX
// CPU 在這期間完全空閒（可以去做別的事），這就是「搬運交給 DMA、計算交給 PIO/CPU」。
//
// 正確性重點（regs/dreq.h、hardware/pio.h、echo.pio）：
//   - DREQ 編號用 pio_get_dreq() 算，不要自己寫數字（PIO0 TX0..3 = 0..3、RX0..3 = 4..7）
//   - TX DREQ = TX FIFO 沒滿；RX DREQ = RX FIFO 有資料
//   - 兩個通道「都要」啟動：只開 TX → RX FIFO 滿 → SM 卡在 push → OSR 不再 pull → TX FIFO 滿
//     → ch_tx 永遠 BUSY（卡死）。所以用 mask 一起開。
//   - echo 同時用 TX 跟 RX，所以「不能」fifo_join（echo_program_init 沒 join = 各 4 格）
//   - DMA_SIZE_32 對應 echo.pio 的 autopull 門檻 32 + `in x, 32` + push；改 8-bit 傳輸時
//     .pio 的門檻也要跟著改（窄寫入在匯流排上的 byte lane 行為請查 datasheet，不確定就維持 32-bit）
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/dma.h"
#include "hardware/pio.h"
#include "echo.pio.h"
#include "timing.h"

#define N 4096                                   // TODO(改這裡) 要搬幾個 u32
static uint32_t src[N], dst[N];

int main(void) {
    stdio_init_all();
    while (!stdio_usb_connected()) sleep_ms(50);
    sleep_ms(200);
    for (int i = 0; i < N; i++) src[i] = (uint32_t)i * 0x9E3779B9u;

    // ---- PIO：載入 echo ----
    PIO pio = pio0;
    int off_i = pio_add_program(pio, &echo_program);       // 失敗回傳負數（SDK pio.h）
    if (off_i < 0) { printf("PIO 指令空間不夠\n"); while (1) tight_loop_contents(); }
    uint off = (uint)off_i;
    uint sm = (uint)pio_claim_unused_sm(pio, true);
    echo_program_init(pio, sm, off);

    // ---- DMA：要兩個通道 ----
    int ch_tx = dma_claim_unused_channel(false);
    int ch_rx = dma_claim_unused_channel(false);
    if (ch_tx < 0 || ch_rx < 0) { printf("DMA 通道不夠\n"); while (1) tight_loop_contents(); }

    dma_channel_config ctx = dma_channel_get_default_config((uint)ch_tx);
    channel_config_set_transfer_data_size(&ctx, DMA_SIZE_32);
    channel_config_set_read_increment(&ctx, true);           // 讀 src[] 往後走
    channel_config_set_write_increment(&ctx, false);         // 一直寫同一個 FIFO 位址
    channel_config_set_dreq(&ctx, pio_get_dreq(pio, sm, true));   // true = TX
    // chain_to 預設 = 自己（不串接）；count 用 dma_encode_transfer_count（RP2350 高 4 bits 是 MODE）
    dma_channel_configure((uint)ch_tx, &ctx, &pio->txf[sm], src, dma_encode_transfer_count(N), false);  // false = 先不開始

    dma_channel_config crx = dma_channel_get_default_config((uint)ch_rx);
    channel_config_set_transfer_data_size(&crx, DMA_SIZE_32);
    channel_config_set_read_increment(&crx, false);          // 一直讀同一個 FIFO 位址
    channel_config_set_write_increment(&crx, true);          // 寫 dst[] 往後走
    channel_config_set_dreq(&crx, pio_get_dreq(pio, sm, false));  // false = RX
    dma_channel_configure((uint)ch_rx, &crx, dst, &pio->rxf[sm], dma_encode_transfer_count(N), false);

    // ---- 同時啟動兩個通道（用 mask 一次開，比一個一個開更同步）----
    uint64_t t0 = time_us_64();
    dma_start_channel_mask((1u << ch_tx) | (1u << ch_rx));
    // TODO(改這裡) CPU 在這裡可以做別的事
    dma_channel_wait_for_finish_blocking((uint)ch_rx);       // 「收」完成 = 資料全部回來了
    dma_channel_wait_for_finish_blocking((uint)ch_tx);       // 保險：送的那個也確認 BUSY=0 再 unclaim
    uint64_t t_dma = time_us_64() - t0;

    printf("DMA+PIO %d words: %llu us, 結果 %s\n", N, (unsigned long long)t_dma,
           memcmp(src, dst, sizeof src) == 0 ? "OK" : "FAIL");
    // 對照組：CPU 自己 put/get（見 app_pio.c 的速度測試）
    memset(dst, 0, sizeof dst);
    t0 = time_us_64();
    for (int i = 0; i < N; i++) { pio_sm_put_blocking(pio, sm, src[i]); dst[i] = pio_sm_get_blocking(pio, sm); }
    uint64_t t_cpu = time_us_64() - t0;
    printf("CPU put/get %d words: %llu us (DMA 快 x%.1f) 結果 %s\n", N, (unsigned long long)t_cpu,
           (double)speedup(t_cpu, t_dma), memcmp(src, dst, sizeof src) == 0 ? "OK" : "FAIL");

    // ---- 收拾 ----
    dma_channel_unclaim((uint)ch_tx);
    dma_channel_unclaim((uint)ch_rx);
    pio_sm_set_enabled(pio, sm, false);
    pio_remove_program_and_unclaim_sm(&echo_program, pio, sm, off);
    while (true) tight_loop_contents();
}
