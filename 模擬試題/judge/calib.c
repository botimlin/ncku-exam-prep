// judge 用：同樣的收資料 + 計算，在一顆核心上依序做完要多久（當作效能的基準）。
#include "pico_sim/pico_sim.h"
#include "work.h"

int main(void) {
    stdio_init_all();
    static packet_t p;
    uint32_t x = 0;
    uint64_t t0 = time_us_64();
    for (uint32_t i = 0; i < N_PACKETS; i++) {
        receive_packet(i, &p);
        x ^= process_block(p.payload, p.len / 4);
    }
    printf("SERIAL ms=%.1f xor=0x%08x\n", (double)(time_us_64() - t0) / 1000.0, (unsigned)x);
    return 0;
}
