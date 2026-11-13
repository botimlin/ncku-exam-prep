// compute.c（不要改）
#include "compute.h"
#include "pico_shim.h"
#include <stdlib.h>

#define COMPUTE_US 100

static uint32_t table[256];
static uint32_t board_serial;

__attribute__((constructor)) static void compute_init(void) {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
        table[i] = c;
    }
    const char *s = getenv("DEVICE_SEED");           // 【模擬】板子序號
    board_serial = s ? (uint32_t)strtoul(s, NULL, 0) : 0x13572468u;
}

static uint32_t crc_update(uint32_t c, const uint8_t *p, int n) {
    for (int i = 0; i < n; i++) c = table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
    return c;
}

uint32_t compute_record(const uint8_t rec[RECORD_SIZE]) {
    uint64_t t0 = time_us_64();
    uint8_t s[4] = { (uint8_t)board_serial, (uint8_t)(board_serial >> 8),
                     (uint8_t)(board_serial >> 16), (uint8_t)(board_serial >> 24) };
    uint32_t c = crc_update(0xFFFFFFFFu, s, 4);
    c = crc_update(c, rec, RECORD_SIZE) ^ 0xFFFFFFFFu;
    while (time_us_64() - t0 < COMPUTE_US) { }
    return c;
}
