// pico_shim.h — 讓「Pico 韌體」在電腦上跑的替身（不要改 pico_shim.* 和 compute.*）
//
// 函式名稱照 pico-sdk（pico/stdlib.h、pico/stdio.h）。在真的 Pico 2 上，這些來自 stdio_usb。
// 【模擬】USB 序列埠的成本：
//   - 每收 1 byte 約 1 µs
//   - 每次把輸出送回電腦（stdio_flush，或輸出還沒送就開始等輸入時自動送）：約 1000 µs + 每 byte 1 µs
//     → 一來一回（一次 request / response）的固定成本約 1 ms，跟真的 USB full-speed 差不多。
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define PICO_ERROR_TIMEOUT (-1)

void     stdio_init_all(void);
int      getchar_timeout_us(uint32_t timeout_us);   // 回傳 0..255，逾時回傳 PICO_ERROR_TIMEOUT
void     putchar_raw(int c);                        // 不做 \n → \r\n 轉換
void     stdio_flush(void);
uint64_t time_us_64(void);
void     busy_wait_us(uint64_t us);
