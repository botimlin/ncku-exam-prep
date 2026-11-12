// serial_proto.h — 與電腦端共用的二進位封包格式（little-endian）
//
//  位元組:  0     1     2    3    4..5       6..6+len-1   最後 4 bytes
//          0xAA  0x55  cmd  seq  len(u16LE)  payload      crc32(u32LE)
//  crc32 = 標準 zlib CRC-32，算的範圍是 cmd 到 payload 結尾（不含 AA 55）
//  回覆用同樣格式、同樣 cmd / seq。（與 ../ros2/frame.py 的 encode()/FrameParser 一致）
//  len > FRAME_MAX_PAYLOAD 的封包會被丟掉、不回覆 → 電腦端 CHUNK_BYTES 必須 <= FRAME_MAX_PAYLOAD
#ifndef SERIAL_PROTO_H
#define SERIAL_PROTO_H

#include <stdint.h>
#include <stddef.h>

#define SYNC0 0xAA
#define SYNC1 0x55

// 指令代碼 —— TODO(改這裡) 題目有新指令就在這裡加
#define CMD_ECHO    0x01   // 原樣回傳 payload
#define CMD_SUM_U32 0x02   // payload = u32 陣列 → 回一個 u32 總和
#define CMD_CRC32   0x03   // 回 payload 的 crc32 (u32)

// 最大 payload 長度 —— TODO(改這裡) 題目資料大就加大（RP2350 有 520KB RAM）
#define FRAME_MAX_PAYLOAD 8192

typedef struct {
    uint8_t  cmd;
    uint8_t  seq;
    uint16_t len;
    uint8_t  payload[FRAME_MAX_PAYLOAD] __attribute__((aligned(4))); // 4-byte 對齊，方便當 u32 陣列用
} frame_t;

// 標準 zlib crc32。可以分段算：crc = crc32_update(0, a, n1); crc = crc32_update(crc, b, n2);
uint32_t crc32_update(uint32_t crc, const uint8_t *p, size_t n);

// 每收到一個 byte 就丟進來。回傳：1 = 收到完整且 CRC 正確的封包（內容在 *f）
//                                0 = 還沒收完；-1 = CRC 錯誤或長度太大（封包丟掉）
int proto_feed(uint8_t byte, frame_t *f);

// 狀態機回到「找 AA 55」。收到一半就斷線/對方重開時用（app_serial.c 閒置太久會自動呼叫）
void proto_reset(void);
// 1 = 正在收一個封包的中間（已看到 AA）
int proto_busy(void);

// 送出一個封包（自動加 AA 55、len、crc32）
void proto_send(uint8_t cmd, uint8_t seq, const uint8_t *payload, uint16_t len);

#endif
