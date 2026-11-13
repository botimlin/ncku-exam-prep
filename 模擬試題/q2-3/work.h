// work.h — 2-3 的「收資料」與「計算」（不要改 work.h / work.c）
#pragma once
#include <stdint.h>

#define N_PACKETS  3000
#define MAX_WORDS  64

typedef struct {
    uint32_t idx;                  // 第幾個封包（0..N_PACKETS-1）
    uint32_t len;                  // payload 的長度，單位是 BYTE（一定是 4 的倍數，64..256）
    uint32_t payload[MAX_WORDS];
} packet_t;

// 模擬從 USB 收到第 idx 個封包：約 30 µs。
void receive_packet(uint32_t idx, packet_t *p);

// 模擬計算：回傳 words[0..n_words-1]（以 little-endian byte 看）的 CRC-32（zlib 相容），約 30 µs。
uint32_t process_block(const uint32_t *words, uint32_t n_words);
