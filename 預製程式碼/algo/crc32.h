/* crc32.h — CRC 家族（zlib 相容 CRC-32 / CRC-32C / CRC-16 / 任意參數 CRC）
 *
 * 用法（增量 API，跟 zlib 一樣：第一次傳 0，之後把上次結果傳回去）：
 *     crc32_init();                              // 開機呼叫一次（建表）
 *     uint32_t c = crc32_update(0, buf1, n1);    // 第一段
 *     c = crc32_update(c, buf2, n2);             // 接著算第二段
 *     // c == crc32_update(0, buf1+buf2 串起來, n1+n2)
 *
 * 驗證：crc32_update(0, "123456789", 9) == 0xCBF43926
 * 純 C11，不用 malloc，MCU 可直接編譯。表格放 RAM（共 4KB+1KB+512B）。
 */
#ifndef CRC32_H
#define CRC32_H
#include <stdint.h>
#include <stddef.h>

void     crc32_init(void);  /* 建所有查表；不呼叫也行，update 會自動呼叫 */

/* ---- CRC-32（zlib / PNG / Ethernet）三種實作，結果完全相同 ---- */
uint32_t crc32_bitwise(uint32_t crc, const uint8_t *p, size_t n); /* 最慢，最好懂 */
uint32_t crc32_table  (uint32_t crc, const uint8_t *p, size_t n); /* 每 byte 查一次表 */
uint32_t crc32_slice4 (uint32_t crc, const uint8_t *p, size_t n); /* 每 4 byte 查 4 表，最快 */
uint32_t crc32_update (uint32_t crc, const uint8_t *p, size_t n); /* = 最快的那個 */

/* ---- 其他常見 CRC（查表版）---- */
uint32_t crc32c_update(uint32_t crc, const uint8_t *p, size_t n); /* CRC-32C (Castagnoli) */
uint16_t crc16_ccitt_false(uint16_t crc, const uint8_t *p, size_t n);
/* crc16_ccitt_false：第一次傳 0xFFFF（init），沒有 xorout，可增量 */

/* ---- 任意參數的通用 CRC（bit-by-bit，慢但萬用）----
 * 題目給你一個「CRC 規格」時，把參數填進來就能算，用來當標準答案對照。 */
typedef struct {
    uint8_t  width;   /* 1..32 位元（CRC-5、CRC-7 也可以）*/
    uint32_t poly;    /* 一般（非反轉）寫法，例如 CRC-32 = 0x04C11DB7 */
    uint32_t init;    /* 初始值 */
    uint8_t  refin;   /* 1 = 每個輸入 byte 先位元反轉（LSB 先處理）*/
    uint8_t  refout;  /* 1 = 最後結果整個位元反轉 */
    uint32_t xorout;  /* 最後 XOR 的值 */
} crc_param_t;
uint32_t crc_generic(const crc_param_t *c, const uint8_t *p, size_t n);

/* 常見 CRC 參數表（check = 對 "123456789" 的結果，用來驗證你填對了）
 * 名稱              width poly        init        refin refout xorout      check
 * CRC-32 (zlib)     32  0x04C11DB7  0xFFFFFFFF  1     1      0xFFFFFFFF  0xCBF43926
 * CRC-32/BZIP2      32  0x04C11DB7  0xFFFFFFFF  0     0      0xFFFFFFFF  0xFC891918
 * CRC-32/MPEG-2     32  0x04C11DB7  0xFFFFFFFF  0     0      0x00000000  0x0376E6E7
 * CRC-32C           32  0x1EDC6F41  0xFFFFFFFF  1     1      0xFFFFFFFF  0xE3069283
 * CRC-16/CCITT-FALSE16  0x1021      0xFFFF      0     0      0x0000      0x29B1
 * CRC-16/XMODEM     16  0x1021      0x0000      0     0      0x0000      0x31C3
 * CRC-16/KERMIT     16  0x1021      0x0000      1     1      0x0000      0x2189
 * CRC-16/MODBUS     16  0x8005      0xFFFF      1     1      0x0000      0x4B37
 * CRC-16/ARC        16  0x8005      0x0000      1     1      0x0000      0xBB3D
 * CRC-8 (SMBus)      8  0x07        0x00        0     0      0x00        0xF4
 *
 * refin=refout=1 的 CRC 可用「右移 + 反轉多項式」快速寫法（本檔 crc32_* 就是）：
 *   反轉多項式：0x04C11DB7 -> 0xEDB88320，0x1EDC6F41 -> 0x82F63B78，0x8005 -> 0xA001
 * refin=refout=0 的 CRC 用「左移 + 原多項式」（本檔 crc16_ccitt_false 就是）。
 */
#endif
