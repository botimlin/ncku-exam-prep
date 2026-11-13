// main.c — 2-3：雙核心「收資料 / 計算」管線（規格在 README.md）
//
// core0：收封包（receive_packet），放進共用的環狀緩衝區 ring。
// core1：從 ring 取出封包，用 DMA 把 payload 搬到 work_buf，再算 process_block，累計結果。
// 全部做完後 core1 用 FIFO 通知 core0，core0 印出結果。
//
// 這份程式是學長留下來的，「應該」可以動。實際上一跑就 panic，修好之後結果也不對，而且很慢。
// 你可以改這個檔案的任何地方；不要改 work.c / work.h / pico_sim/。

#include "pico_sim/pico_sim.h"
#include "work.h"

#define RING_SIZE 8

typedef struct {
    packet_t slot[RING_SIZE];
    volatile uint32_t head;    // core0 下一個要寫的位置
    volatile uint32_t tail;    // core1 下一個要讀的位置
    volatile uint32_t count;   // ring 裡有幾個封包
} ring_t;

// ring 和 work_buf 放在同一個 struct 裡，work_guard 用來偵測 work_buf 被寫爆（不要拿掉）。
static struct {
    ring_t   ring;
    uint32_t work_buf[MAX_WORDS];
    uint32_t work_guard[4 * MAX_WORDS];
} sh;

#define GUARD 0xDEADBEEFu

static spin_lock_t *ring_lock;

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
        uint32_t save = spin_lock_blocking(ring_lock);
        if (sh.ring.count == 0) {
            spin_unlock(ring_lock, save);
            continue;
        }
        packet_t *p = &sh.ring.slot[sh.ring.tail];

        // 用 DMA 把 payload 搬到 work_buf
        int ch = dma_claim_unused_channel(true);
        dma_channel_config c = dma_channel_get_default_config(ch);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
        dma_channel_configure(ch, &c, sh.work_buf, p->payload, p->len, true);
        dma_channel_wait_for_finish_blocking(ch);
        check_guard();

        uint32_t crc = process_block(sh.work_buf, p->len / 4);
        stats.xor_acc ^= crc;
        stats.bytes += p->len;
        stats.packets++;

        sh.ring.tail = (sh.ring.tail + 1) % RING_SIZE;
        sh.ring.count--;
        n++;
        spin_unlock(ring_lock, save);
    }
    multicore_fifo_push_blocking(n);
}

int main(void) {
    stdio_init_all();
    for (int i = 0; i < 4 * MAX_WORDS; i++) sh.work_guard[i] = GUARD;
    ring_lock = spin_lock_init((uint)spin_lock_claim_unused(true));

    multicore_launch_core1(core1_main);

    uint64_t t0 = time_us_64();
    for (uint32_t i = 0; i < N_PACKETS; i++) {
        packet_t pkt;
        receive_packet(i, &pkt);

        while (sh.ring.count == RING_SIZE) tight_loop_contents();   // ring 滿了就等
        sh.ring.slot[sh.ring.head] = pkt;
        sh.ring.head = (sh.ring.head + 1) % RING_SIZE;
        sh.ring.count++;
    }
    uint32_t done = multicore_fifo_pop_blocking();
    uint64_t t1 = time_us_64();

    printf("RESULT packets=%u bytes=%llu xor=0x%08x\n", (unsigned)done,
           (unsigned long long)stats.bytes, (unsigned)stats.xor_acc);
    printf("TIME ms=%.1f\n", (double)(t1 - t0) / 1000.0);
    return 0;
}
