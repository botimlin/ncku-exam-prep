// serial_proto.c — 封包收發 + 軟體 crc32
//
// 收封包用「狀態機」：一次吃一個 byte，記住現在在讀封包的哪一段。
//   WAIT_AA → WAIT_55 → HEADER(cmd,seq,len 共 4 bytes) → PAYLOAD(len bytes) → CRC(4 bytes)
// 任何一步出錯就回到 WAIT_AA 重新找開頭（這樣掉 byte 也能自己恢復同步）。
#include "serial_proto.h"
#include <string.h>
#include "pico/stdlib.h"

// ---------------- crc32（查表法，電腦實測比一次算 1 bit 快約 4 倍） ----------------
static uint32_t crc_table[256];
static int crc_table_ready = 0;

__attribute__((constructor)) static void crc32_make_table(void) {   // main() 前在 core0 建好（兩核不會搶著建）
    for (uint32_t i = 0; i < 256; i++) {
        uint32_t c = i;
        for (int k = 0; k < 8; k++)
            c = (c & 1) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);   // 反射多項式
        crc_table[i] = c;
    }
    crc_table_ready = 1;
}

// 驗證：crc32_update(0, "123456789", 9) 應該 == 0xCBF43926。weak：專案裡也加了 algo/crc32.c 時用那一份（結果相同），不會 multiple definition
__attribute__((weak)) uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n) {
    if (!crc_table_ready) crc32_make_table();
    crc ^= 0xFFFFFFFFu;                                // 初值 / 接續
    while (n--) crc = crc_table[(crc ^ *p++) & 0xFF] ^ (crc >> 8);
    return crc ^ 0xFFFFFFFFu;                          // 最後 xor
}

// ---------------- 收封包狀態機 ----------------
enum { ST_WAIT_AA, ST_WAIT_55, ST_HEADER, ST_PAYLOAD, ST_CRC };
static int      st = ST_WAIT_AA;
static uint8_t  hdr[4];        // cmd, seq, len_lo, len_hi
static uint8_t  crcbuf[4];
static uint32_t idx;           // 目前這一段已讀幾個 byte

int proto_feed(uint8_t b, frame_t *f) {
    switch (st) {
    case ST_WAIT_AA:
        if (b == SYNC0) st = ST_WAIT_55;
        return 0;
    case ST_WAIT_55:
        if (b == SYNC1) { st = ST_HEADER; idx = 0; }
        else st = (b == SYNC0) ? ST_WAIT_55 : ST_WAIT_AA;   // AA AA 55 也要能對齊
        return 0;
    case ST_HEADER:
        hdr[idx++] = b;
        if (idx < 4) return 0;
        f->cmd = hdr[0];
        f->seq = hdr[1];
        f->len = (uint16_t)(hdr[2] | (hdr[3] << 8));        // little-endian
        if (f->len > FRAME_MAX_PAYLOAD) { st = ST_WAIT_AA; return -1; }
        idx = 0;
        st = (f->len == 0) ? ST_CRC : ST_PAYLOAD;
        return 0;
    case ST_PAYLOAD:
        f->payload[idx++] = b;
        if (idx == f->len) { idx = 0; st = ST_CRC; }
        return 0;
    case ST_CRC:
        crcbuf[idx++] = b;
        if (idx < 4) return 0;
        st = ST_WAIT_AA;
        {
            uint32_t got = (uint32_t)crcbuf[0] | ((uint32_t)crcbuf[1] << 8) |
                           ((uint32_t)crcbuf[2] << 16) | ((uint32_t)crcbuf[3] << 24);
            uint32_t c = crc32_update(0, hdr, 4);           // cmd..len
            c = crc32_update(c, f->payload, f->len);        // payload
            return (c == got) ? 1 : -1;
        }
    }
    st = ST_WAIT_AA;
    return 0;
}

void proto_reset(void) { st = ST_WAIT_AA; idx = 0; }
int proto_busy(void) { return st != ST_WAIT_AA; }

// ---------------- 送封包 ----------------
// 用 stdio_put_string(..., newline=false, cr_translation=false) 送「原始」bytes：
// 不會被加 \r，也不經過 printf 的格式化，適合二進位資料。（pico_stdio/stdio.c：cr_translation=false
// 時直接呼叫 driver->out_chars）
// USB 輸出行為（pico_stdio_usb/stdio_usb.c）：電腦沒打開序列埠(DTR=0)時資料「直接丟掉」；
// 電腦不讀、TX buffer 滿超過 PICO_STDIO_USB_STDOUT_TIMEOUT_US(預設 0.5 秒)也會丟掉剩下的。
// 所以電腦端要一直讀（frame.py 的 transact() 有在讀），丟掉半包時 FrameParser 會自己重新對齊。
static void put_raw(const uint8_t *p, int n) {
    if (n > 0) stdio_put_string((const char *)p, n, false, false);
}

void proto_send(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint16_t len) {
    uint8_t h[6] = { SYNC0, SYNC1, cmd, seq, (uint8_t)(len & 0xFF), (uint8_t)(len >> 8) };
    uint32_t c = crc32_update(0, &h[2], 4);
    c = crc32_update(c, payload, len);
    uint8_t t[4] = { (uint8_t)c, (uint8_t)(c >> 8), (uint8_t)(c >> 16), (uint8_t)(c >> 24) };
    put_raw(h, 6);
    put_raw(payload, len);
    put_raw(t, 4);
    stdio_flush();             // 立刻送出去，不要等緩衝區滿
}
