// work.c（不要改）
#include "work.h"
#include "pico_sim/pico_sim.h"

#define RECV_US 30
#define PROC_US 30

void receive_packet(uint32_t idx, packet_t *p) {
    uint64_t t0 = time_us_64();
    uint32_t s = idx * 2654435761u + 12345u;
#define NEXT() (s ^= s << 13, s ^= s >> 17, s ^= s << 5, s)
    uint32_t n = 16 + NEXT() % 49;
    p->idx = idx;
    p->len = n * 4;
    for (uint32_t i = 0; i < n; i++) p->payload[i] = NEXT();
    for (uint32_t i = n; i < MAX_WORDS; i++) p->payload[i] = 0;
#undef NEXT
    while (time_us_64() - t0 < RECV_US) tight_loop_contents();
}

static uint32_t crc_table[256];
__attribute__((constructor)) static void crc_init(void) {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
        crc_table[i] = c;
    }
}

uint32_t process_block(const uint32_t *words, uint32_t n_words) {
    uint64_t t0 = time_us_64();
    uint32_t c = 0xFFFFFFFFu;
    for (uint32_t i = 0; i < n_words; i++)
        for (int k = 0; k < 4; k++)
            c = crc_table[(c ^ (words[i] >> (8 * k))) & 0xFF] ^ (c >> 8);
    while (time_us_64() - t0 < PROC_US) tight_loop_contents();
    return c ^ 0xFFFFFFFFu;
}
