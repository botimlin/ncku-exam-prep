// compute.h — 裝置上的計算（不要改 compute.*）
#pragma once
#include <stdint.h>

#define RECORD_SIZE 16

// 對一筆 16 byte 的資料算出 32-bit 結果。約 100 µs（模擬 MCU 算得慢）。
// 結果跟這片板子的「序號」有關，電腦端算不出來，一定要交給板子算。
uint32_t compute_record(const uint8_t rec[RECORD_SIZE]);
