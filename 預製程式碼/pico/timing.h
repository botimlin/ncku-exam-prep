// timing.h — 量時間的小工具（直接 #include "timing.h" 就能用）
//
// 兩種量法：
//   1) 微秒：time_us_64()  —— 任何長度都能量，精度 1 us
//   2) CPU cycle：cycles_now() —— 很短的程式碼用（例如一個迴圈 < 0.1 秒）
//      ARM (Cortex-M33)：用 SysTick（24-bit 往下數，CLKSOURCE=1 處理器時脈 = clk_sys）
//                        最多 2^24-1 ≈ 16.7M cycles ≈ 0.11 秒 @150MHz，超過會「默默繞回」算錯
//      RISC-V (Hazard3)：用 mcycle CSR（讀低 32 bits 往上數，≈ 28 秒 @150MHz 才繞回）
//   出處：hardware/regs/m33.h（SYST_CSR/RVR/CVR 說明）、hardware/regs/rvcsr.h（MCOUNTINHIBIT）
//   ⚠ SDK 本身不用 SysTick（計時用 TIMER），但若你自己用 SysTick 中斷，這裡會改掉它的設定
//
// 用法：
//   uint64_t t0 = time_us_64();  ...要量的程式...  PRINT_US("CPU 迴圈", t0);
//   cycles_init(); uint32_t c0 = cycles_now(); ... ; printf("%lu cycles\n", cycles_since(c0));
#ifndef TIMING_H
#define TIMING_H

#include <stdio.h>
#include <stdint.h>
#include "pico/stdlib.h"     // time_us_64()

#if defined(__riscv)
#include "hardware/riscv.h"
#else
#include "hardware/structs/systick.h"
#endif

// 印出「從 t0 到現在」花了幾微秒
#define PRINT_US(label, t0) \
    printf("[時間] %-20s %8llu us\n", (label), (unsigned long long)(time_us_64() - (t0)))

// 啟動 cycle 計數器（程式開頭呼叫一次）
static inline void cycles_init(void) {
#if defined(__riscv)
    // mcountinhibit (CSR 0x320) 重置值 = 0x5（CY=bit0、IR=bit2 都「暫停」以省電，rvcsr.h），
    // 清掉 bit0 (CY) mcycle 才會數。CSR 用數字寫：riscv_clear_csr 會把名字直接貼進組合語言
    riscv_clear_csr(0x320, 1);
#else
    systick_hw->csr = 0;                   // 先關
    systick_hw->rvr = M33_SYST_RVR_BITS;   // 重載值 0xFFFFFF（重置值是 UNKNOWN，一定要設）→ 週期 2^24
    systick_hw->cvr = 0;                   // 寫任何值 = 清 0（也清 COUNTFLAG）
    systick_hw->csr = M33_SYST_CSR_ENABLE_BITS | M33_SYST_CSR_CLKSOURCE_BITS;  // =0x5：啟用 + 處理器時脈；不開中斷
#endif
}

// 讀目前 cycle 值（注意：兩平台方向不同，請用 cycles_since 算差）
static inline uint32_t cycles_now(void) {
#if defined(__riscv)
    return riscv_read_csr(mcycle);
#else
    return systick_hw->cvr;
#endif
}

// 從 c0 到現在過了幾個 cycle
static inline uint32_t cycles_since(uint32_t c0) {
#if defined(__riscv)
    return cycles_now() - c0;                       // 往上數
#else
    return (c0 - cycles_now()) & 0x00FFFFFF;        // 往下數、週期 2^24 → 差值取低 24 bits（經過時間必須 < 2^24 cycles）
#endif
}

// 加速倍數，例如 speedup(cpu_us, dma_us)
static inline float speedup(uint64_t slow_us, uint64_t fast_us) {
    return fast_us ? (float)slow_us / (float)fast_us : 0.0f;
}

#endif
