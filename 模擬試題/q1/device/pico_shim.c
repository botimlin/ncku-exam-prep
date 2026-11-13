// pico_shim.c（不要改）
#define _GNU_SOURCE
#include "pico_shim.h"
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>
#include <unistd.h>

#define BYTE_US   1
#define FLUSH_US  1000

static uint8_t  inbuf[4096];
static int      in_pos, in_len;
static uint8_t  outbuf[8192];
static int      out_len;

static uint64_t now_us(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000ull + (uint64_t)ts.tv_nsec / 1000;
}
static uint64_t t_boot;
uint64_t time_us_64(void) { return now_us() - t_boot; }
void busy_wait_us(uint64_t us) { uint64_t end = now_us() + us; while (now_us() < end) { } }

void stdio_init_all(void) { t_boot = now_us(); }

void stdio_flush(void) {
    if (!out_len) return;
    busy_wait_us(FLUSH_US + (uint64_t)out_len * BYTE_US);
    int off = 0;
    while (off < out_len) {
        ssize_t w = write(1, outbuf + off, (size_t)(out_len - off));
        if (w < 0) { if (errno == EINTR || errno == EAGAIN) continue; _exit(0); }
        off += (int)w;
    }
    out_len = 0;
}

void putchar_raw(int c) {
    if (out_len == (int)sizeof outbuf) stdio_flush();
    outbuf[out_len++] = (uint8_t)c;
}

int getchar_timeout_us(uint32_t timeout_us) {
    stdio_flush();                                   // 輸出還沒送出去就要等輸入 → 先送
    if (in_pos == in_len) {
        struct pollfd p = { .fd = 0, .events = POLLIN };
        int ms = (int)((timeout_us + 999) / 1000);
        int r = poll(&p, 1, ms);
        if (r == 0) return PICO_ERROR_TIMEOUT;
        if (r < 0) return PICO_ERROR_TIMEOUT;
        if (p.revents & (POLLHUP | POLLERR) && !(p.revents & POLLIN)) _exit(0);
        ssize_t n = read(0, inbuf, sizeof inbuf);
        if (n <= 0) _exit(0);                        // 電腦那端關掉了
        in_pos = 0; in_len = (int)n;
    }
    busy_wait_us(BYTE_US);
    return inbuf[in_pos++];
}
