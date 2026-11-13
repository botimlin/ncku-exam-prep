// 解答：device_main.c — 「Pico 韌體」：從 USB 序列埠收 frame、計算、回傳結果
//
// frame 格式和指令見 q1/README.md §2。這是可以改的檔案。

#include <string.h>
#include "pico_shim.h"
#include "compute.h"

#define SOF0 0xA5
#define SOF1 0x5A

#define CMD_PING        0x01
#define CMD_CALC_ONE    0x10
#define CMD_CALC_BATCH  0x11
#define RSP_FLAG        0x80      // 回應的 cmd = 請求的 cmd | 0x80
#define RSP_ERROR       0xEE

#define ERR_BAD_CRC     1
#define ERR_BAD_LEN     2
#define ERR_UNKNOWN_CMD 3

#define MAX_PAYLOAD     1024

static uint32_t crc_table[256];

static void crc32_init(void) {
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
        crc_table[i] = c;
    }
}

static uint32_t crc32_update(uint32_t c, const uint8_t *p, int n) {
    c ^= 0xFFFFFFFFu;
    for (int i = 0; i < n; i++) c = crc_table[(c ^ p[i]) & 0xFF] ^ (c >> 8);
    return c ^ 0xFFFFFFFFu;
}

// ---- 送出一個 frame ------------------------------------------------------
static uint8_t txbuf[6 + MAX_PAYLOAD + 4];

static void send_frame(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint16_t len) {
    txbuf[0] = SOF0; txbuf[1] = SOF1;
    txbuf[2] = cmd;  txbuf[3] = seq;
    txbuf[4] = (uint8_t)len; txbuf[5] = (uint8_t)(len >> 8);
    if (len) memcpy(txbuf + 6, payload, len);
    uint32_t crc = crc32_update(0, txbuf + 2, 4 + len);
    for (int i = 0; i < 4; i++) txbuf[6 + len + i] = (uint8_t)(crc >> (8 * i));
    for (int i = 0; i < 6 + len + 4; i++) putchar_raw(txbuf[i]);
    stdio_flush();
}

static void send_error(uint8_t seq, uint8_t cmd, uint8_t code) {
    uint8_t p[2] = { cmd, code };
    send_frame(RSP_ERROR, seq, p, 2);
}

// ---- 處理一個收到的 frame -------------------------------------------------
static uint8_t outbuf[MAX_PAYLOAD];

static void handle(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint16_t len) {
    switch (cmd) {
    case CMD_PING:
        send_frame(CMD_PING | RSP_FLAG, seq, payload, len);
        break;
    case CMD_CALC_ONE: {
        if (len != RECORD_SIZE) { send_error(seq, cmd, ERR_BAD_LEN); break; }
        uint32_t r = compute_record(payload);
        for (int i = 0; i < 4; i++) outbuf[i] = (uint8_t)(r >> (8 * i));
        send_frame(CMD_CALC_ONE | RSP_FLAG, seq, outbuf, 4);
        break;
    }
    case CMD_CALC_BATCH:
    {   // 解答：新增 batch 指令
        if (len == 0 || len % RECORD_SIZE != 0) { send_error(seq, cmd, ERR_BAD_LEN); break; }
        int k = len / RECORD_SIZE;                 // len ≤ 1024 → k ≤ 64 → 回應 ≤ 256 byte
        for (int j = 0; j < k; j++) {
            uint32_t r = compute_record(payload + RECORD_SIZE * j);
            for (int i = 0; i < 4; i++) outbuf[4 * j + i] = (uint8_t)(r >> (8 * i));
        }
        send_frame(CMD_CALC_BATCH | RSP_FLAG, seq, outbuf, (uint16_t)(4 * k));
        break;
    }
    default:
        send_error(seq, cmd, ERR_UNKNOWN_CMD);
        break;
    }
}

// ---- 主迴圈：一個 byte 一個 byte 解析 frame ------------------------------
int main(void) {
    stdio_init_all();
    crc32_init();

    static uint8_t frame[4 + MAX_PAYLOAD + 4];   // cmd seq len_lo len_hi payload crc
    enum { WAIT_SOF0, WAIT_SOF1, READ_HDR, READ_BODY } st = WAIT_SOF0;
    int pos = 0;
    uint16_t len = 0;   // 解答 bug：原本是 uint8_t，len ≥ 256 會被截斷（編譯器的 -Wtype-limits 警告就在講這個）

    for (;;) {
        int c = getchar_timeout_us(100000);
        if (c == PICO_ERROR_TIMEOUT) { st = WAIT_SOF0; continue; }
        uint8_t b = (uint8_t)c;
        switch (st) {
        case WAIT_SOF0:
            if (b == SOF0) st = WAIT_SOF1;
            break;
        case WAIT_SOF1:
            st = (b == SOF1) ? READ_HDR : (b == SOF0 ? WAIT_SOF1 : WAIT_SOF0);
            pos = 0;
            break;
        case READ_HDR:
            frame[pos++] = b;
            if (pos == 4) {
                len = frame[2] | (frame[3] << 8);
                if (len > MAX_PAYLOAD) { send_error(frame[1], frame[0], ERR_BAD_LEN); st = WAIT_SOF0; break; }
                st = READ_BODY;
            }
            break;
        case READ_BODY:
            frame[pos++] = b;
            if (pos == 4 + len + 4) {
                uint32_t got = 0;
                for (int i = 0; i < 4; i++) got |= (uint32_t)frame[4 + len + i] << (8 * i);
                if (got != crc32_update(0, frame, 4 + len)) send_error(frame[1], frame[0], ERR_BAD_CRC);
                else handle(frame[0], frame[1], frame + 4, len);
                st = WAIT_SOF0;
            }
            break;
        }
    }
}
