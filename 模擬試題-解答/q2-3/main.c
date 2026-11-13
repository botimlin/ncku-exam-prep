// 解答：main.c（和題目版本的差別都標了「修正」）
#include "pico_sim/pico_sim.h"
#include "work.h"

#define RING_SIZE 8

typedef struct {
    packet_t slot[RING_SIZE];
    volatile uint32_t head;
    volatile uint32_t tail;
    volatile uint32_t count;
} ring_t;

static struct {
    ring_t   ring;
    uint32_t work_buf[MAX_WORDS];
    uint32_t work_guard[4 * MAX_WORDS];
} sh;

#define GUARD 0xDEADBEEFu

static spin_lock_t *ring_lock;
static int dma_ch;                       // 修正 1：通道只在開機時 claim 一次（原本每個封包 claim、從不 unclaim）
static dma_channel_config dma_cfg;

static struct {
    uint32_t packets;
    uint64_t bytes;
    uint32_t xor_acc;
} stats;

static void check_guard(void) {
    for (int i = 0; i < 4 * MAX_WORDS; i++)
        if (sh.work_guard[i] != GUARD) panic("work_buf 後面的記憶體被寫壞了（第 %d 個 word）", i);
}

static void core1_main(void) {
    uint32_t n = 0;
    while (n < N_PACKETS) {
        // 修正 5：只在鎖裡做「取出 + 搬走」，算 CRC 移到鎖外面。
        // 等資料時：拿鎖、看 count、沒資料就放鎖再試（不要拿著鎖空等，也不要不拿鎖就讀 count）。
        uint32_t save;
        for (;;) {
            save = spin_lock_blocking(ring_lock);
            if (sh.ring.count > 0) break;                   // 有資料：拿著鎖往下走
            spin_unlock(ring_lock, save);
            tight_loop_contents();
        }
        packet_t *p = &sh.ring.slot[sh.ring.tail];
        uint32_t len = p->len;
        // 修正 2：transfer_count 是「筆數」：DMA_SIZE_32 時 = len / 4（原本填 byte 數 → 搬 4 倍）
        // 修正 3：寫位址要遞增（預設不遞增 → 每筆都寫到 work_buf[0]）—— 設定在 main() 裡
        dma_channel_configure(dma_ch, &dma_cfg, sh.work_buf, p->payload, len / 4, true);
        dma_channel_wait_for_finish_blocking(dma_ch);
        sh.ring.tail = (sh.ring.tail + 1) % RING_SIZE;
        sh.ring.count--;
        spin_unlock(ring_lock, save);

        check_guard();
        uint32_t crc = process_block(sh.work_buf, len / 4);   // work_buf 只有 core1 用，不必鎖
        stats.xor_acc ^= crc;                                 // stats 只有 core1 寫，core0 等 FIFO 之後才讀
        stats.bytes += len;
        stats.packets++;
        n++;
    }
    multicore_fifo_push_blocking(n);
}

int main(void) {
    stdio_init_all();
    for (int i = 0; i < 4 * MAX_WORDS; i++) sh.work_guard[i] = GUARD;
    ring_lock = spin_lock_init((uint)spin_lock_claim_unused(true));

    dma_ch = dma_claim_unused_channel(true);
    dma_cfg = dma_channel_get_default_config((uint)dma_ch);
    channel_config_set_transfer_data_size(&dma_cfg, DMA_SIZE_32);
    channel_config_set_read_increment(&dma_cfg, true);
    channel_config_set_write_increment(&dma_cfg, true);     // 修正 3

    multicore_launch_core1(core1_main);

    uint64_t t0 = time_us_64();
    for (uint32_t i = 0; i < N_PACKETS; i++) {
        // ring 滿了就等。count 一定要在鎖裡讀：這樣 core1 放鎖之前對這格做的事（DMA 讀走 payload），
        // core0 拿到鎖之後一定看得到，才不會在 core1 還沒搬走之前就把這格蓋掉。
        for (;;) {
            uint32_t save = spin_lock_blocking(ring_lock);
            int full = (sh.ring.count == RING_SIZE);
            spin_unlock(ring_lock, save);
            if (!full) break;
            tight_loop_contents();
        }
        // 小優化：直接收進 ring 的空格，少一次 264 byte 的 struct 複製。
        // 這格在 count++ 之前 core1 不會碰，所以收資料（30 µs）不用拿鎖。
        receive_packet(i, &sh.ring.slot[sh.ring.head]);

        uint32_t save = spin_lock_blocking(ring_lock);      // 修正 4：count++ 原本沒有鎖 → lost update
        sh.ring.head = (sh.ring.head + 1) % RING_SIZE;
        sh.ring.count++;
        spin_unlock(ring_lock, save);
    }
    uint32_t done = multicore_fifo_pop_blocking();
    uint64_t t1 = time_us_64();

    printf("RESULT packets=%u bytes=%llu xor=0x%08x\n", (unsigned)done,
           (unsigned long long)stats.bytes, (unsigned)stats.xor_acc);
    printf("TIME ms=%.1f\n", (double)(t1 - t0) / 1000.0);
    dma_channel_unclaim((uint)dma_ch);
    return 0;
}
