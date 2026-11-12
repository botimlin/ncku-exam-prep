# 嵌入式控制與訊號處理：取樣、定點數、濾波、PID、訊號分析（RP2350 / Hazard3 / Cortex-M33）

- 用途：**備援包**（考前 demo 沒有提到，萬一考題延伸到「感測 → 濾波 → 控制」或「把某個運算核心優化到更快」時使用）。整理機器人 / ROS 2 + 微控制器系統常見的計算核心（kernel）：取樣與固定週期迴圈、定點數（Q format）、各種濾波器、PID 與其他控制律、FFT / Goertzel / RMS / 線上統計，以及在 RP2350 上加速它們的方法（Hazard3 無 FPU、Cortex-M33 有單精度 FPU + DSP 指令、SIO interpolator、ADC + DMA 雙緩衝、雙核分工）。給「考場 LLM」當 context，也給考生自己查。
- 適用版本：RP2350（Pico 2）；pico-sdk 2.x（GitHub master）；Arm CMSIS-DSP（GitHub main）；ROS 2 Jazzy。數學公式為教科書等級標準結果。
- 來源（實際查閱）：
  - RP2350 datasheet §3.1.10 Interpolator、§12.4 ADC、Appendix D 勘誤 RP2350-E1：https://datasheets.raspberrypi.com/rp2350/rp2350-datasheet.pdf
  - pico-sdk 原始碼：`src/rp2_common/hardware_interp/include/hardware/interp.h`、`src/rp2350/hardware_structs/include/hardware/structs/interp.h`、`src/rp2_common/hardware_adc/include/hardware/adc.h`、`src/common/pico_time/include/pico/time.h`、`src/rp2_common/hardware_timer/include/hardware/timer.h`、`src/rp2_common/pico_float/include/pico/float.h`、`src/rp2_common/cmsis/CMakeLists.txt` 與 `cmsis/stub/CMSIS/Core/Include/cmsis_gcc.h`（https://github.com/raspberrypi/pico-sdk）
  - CMSIS-DSP 文件 Biquad DF1：https://arm-software.github.io/CMSIS-DSP/latest/group__BiquadCascadeDF1.html ；Basic Mult：https://arm-software.github.io/CMSIS-DSP/latest/group__BasicMult.html ；原始碼 `Source/BasicMathFunctions/arm_mult_q15.c`、`Source/FilteringFunctions/arm_biquad_cascade_df1_q15.c`（https://github.com/ARM-software/CMSIS-DSP）
  - Audio EQ Cookbook（RBJ biquad 公式，W3C）：https://www.w3.org/TR/audio-eq-cookbook/
  - ROS REP 103（單位與座標慣例）：https://github.com/ros-infrastructure/rep/blob/master/rep-0103.rst
  - SMLAD 語意（QEMU 修正 Q flag 的 commit 說明 + Arm 指令說明）：https://qemu-android.googlesource.com/qemu-android/+/e1d177b922f52569e900e96d611caa09655bdec9
- 驗證方式：第 2、3、5 節標註「已在主機驗證」的程式碼，曾在 x86-64 主機用 `gcc -O2 -fsanitize=undefined` 編譯並與 double 參考比對（數字見各節）；**未在 RP2350 上執行**。interpolator 範例未在硬體上測試。
- 相關檔案：`pico-sdk.md`（時間 API、IRQ、記憶體擺放、除法與浮點表）、`riscv-hazard3.md`（指令週期、Zbb `min/max/clz`）、`pico-dma.md`（ping-pong 雙緩衝）、`multicore-sync.md`（core1、FIFO、queue）、`03-optimize.md`（量測流程）、`ros2.md`。若有 `arm-cortex-m33.md`（M33 指令與 DSP 擴充）、`pico-peripherals.md`（ADC / PWM API）也一併參考。
- 最後更新：2026-11

---

## 0. 一頁總結（先看這裡）

| 情境 | 首選做法 | 為什麼 |
|---|---|---|
| 在 Hazard3（RISC-V）上做任何數學 | **定點數**（int32 + 小數位數 FRAC），乘法用 64-bit 中間值 | Hazard3 **無 FPU**，float 全部軟體模擬；`mul`/`mulh` 各 1 cycle，`div` 18–19 cycle（⚠️未查證，見 datasheet 3.8.7） |
| 在 M33 上 | `float`（單精度硬體）可以用；**不要 double**（常數寫 `1.0f`）；16-bit 資料可用 `SMLAD` 一次做兩個 MAC | M33 有 FPv5 單精度 FPU + DSP 擴充 |
| 需要和 judge 輸出**逐位元相同** | 定點數 + 明確的捨入規則 | float 結果會因 FMA 合併、編譯旗標、平台而差最後幾位 |
| 去雜訊、平滑 | EMA `acc += x - (acc >> k)`（1 減 1 加 1 移位）或 moving average（running sum，O(1)） | 最便宜 |
| 尖峰雜訊（突波） | 3 或 5 點 median | 線性濾波器擋不住 impulse |
| 明確截止頻率 | biquad（2 階 IIR）；定點數用 **DF1 + int64 累加器 + 輸出保留額外小數位** | 低截止頻率時整數回授誤差很大（見 3.3.4 實測） |
| 單一頻率是否存在 | Goertzel，O(N)，每點 1 乘 2 加 | 比整個 FFT 便宜 |
| 很多頻率 | radix-2 FFT，O(N log N)，解析度 fs/N | |
| 控制 | PID：微分取量測值、微分低通、anti-windup、輸出限幅、固定 dt | 見第 4 節 |
| 除以變數 | 先算倒數再乘（reciprocal multiply）；除以常數交給編譯器 | 64-bit 除法是軟體函式，很慢 |
| sin/cos/atan/sqrt | 查表 + 線性內插、CORDIC、整數 sqrt | 不需要浮點 |
| 取樣 | ADC 自由執行 + FIFO + DMA ping-pong；處理放另一核或主迴圈 | CPU 不必逐點輪詢 |

---

## 1. 取樣與時序

### 1.1 取樣定理與混疊

| 名詞 | 定義 / 公式 |
|---|---|
| 取樣頻率 fs | 每秒取樣數；週期 Ts = 1/fs |
| Nyquist 頻率 | fs/2。訊號中**高於 fs/2** 的成分會折疊（alias）到 0…fs/2 |
| 混疊頻率 | 輸入頻率 f 取樣後出現在 \|f − k·fs\| 中最小者（k 為整數） |
| 必要條件 | fs > 2·f_max（嚴格大於）；實務上取 5–10 倍並在 ADC 前加類比低通（anti-aliasing） |
| 例 | fs = 1 kHz，輸入 900 Hz → 看起來是 100 Hz；輸入 1 kHz → 看起來是 DC |

- **數位濾波器無法消除已經混疊的成分**（取樣之後就分不開了），只能在取樣前用類比濾波或提高 fs 後「過取樣 + 數位低通 + 降頻（decimation）」。
- 降頻（例如每 4 點留 1 點）前也必須先數位低通到新的 fs/2 以下，否則一樣混疊。
- 過取樣平均：對不相關的白雜訊，平均 4 個點雜訊標準差減半（約多 1 bit 有效解析度）；ADC 雜訊非白雜訊時效果打折。

### 1.2 RP2350 ADC 的取樣能力（datasheet §12.4、`adc.h`）

| 項目 | 值 |
|---|---|
| 類型 / 解析度 | SAR，12-bit，ENOB 9.2 |
| 最高速率 | 500 kS/s（獨立 48 MHz `clk_adc`，每次轉換 96 cycle） |
| 通道 | QFN-60（RP2350A / Pico 2）：GPIO26–29 為 ch0–3，ch4 = 溫度感測器；QFN-80：GPIO40–47 為 ch0–7，ch8 = 溫度 |
| FIFO | 8 筆；滿了之後新結果被丟棄 |
| 自由執行速率 | `adc_set_clkdiv(div)`：平均每 `(1 + div)` 個 48 MHz cycle 一次；小於 96 會被限制成 96 |
| round robin | `adc_set_round_robin(mask)`：多通道輪流，**每通道速率 = 總速率 / 通道數** |
| 8-bit 模式 | `adc_fifo_setup(..., byte_shift=true)` 右移成 8 bit，可用 byte DMA |

例：要 10 kHz 取樣 → `div = 48e6 / 10e3 − 1 = 4799`。

```c
// API（hardware_adc，CMake 連結 hardware_adc）
void adc_init(void);
void adc_gpio_init(uint gpio);            // 關閉該腳數位功能
void adc_select_input(uint input);        // 0..3（QFN-60），4 = 溫度
uint16_t adc_read(void);                  // 單次轉換（阻塞）
void adc_set_clkdiv(float clkdiv);
void adc_fifo_setup(bool en, bool dreq_en, uint16_t dreq_thresh, bool err_in_fifo, bool byte_shift);
void adc_run(bool run);                   // 開始 / 停止自由執行
uint16_t adc_fifo_get_blocking(void);
void adc_fifo_drain(void);
```

### 1.3 固定週期迴圈：三種寫法

| 寫法 | 週期準確度 | 抖動（jitter） | 備註 |
|---|---|---|---|
| `sleep_ms(10)` 放在迴圈尾 | **差**：週期 = 10 ms + 運算時間，會累積漂移 | 大 | 不要用在控制迴圈 |
| 絕對時間排程 `next = delayed_by_us(next, T); sleep_until(next);` | 好，不累積漂移 | 中（受其他 IRQ 影響） | 主迴圈裡最簡單的正確寫法 |
| `add_repeating_timer_us(-T, cb, ...)`（**負值** = 開始到開始固定週期） | 好 | 小（IRQ context） | callback 要短；不可 `sleep`/`printf` |
| 硬體節拍：ADC 自由執行 / PWM wrap IRQ / DMA timer | 最好（硬體時脈） | 最小 | 取樣點由硬體決定，CPU 只處理資料 |

```c
#include "pico/stdlib.h"
// 寫法 A：絕對時間排程（不漂移）
void control_loop(void) {
    const uint32_t T_US = 1000;                       // 1 kHz
    absolute_time_t next = get_absolute_time();
    for (;;) {
        next = delayed_by_us(next, T_US);
        sample_and_control();                         // 必須 < T_US，否則下一行立即返回並持續落後
        sleep_until(next);                            // 也可 busy_wait_until(next) 降低喚醒延遲
    }
}

// 寫法 B：repeating timer（callback 在 IRQ context，預設 core 0）
static repeating_timer_t tmr;                         // 必須比 timer 活得久：static / 全域
static volatile uint32_t overrun;
static bool on_tick(repeating_timer_t *rt) {
    sample_and_control();
    return true;                                      // true = 繼續
}
// add_repeating_timer_us(-1000, on_tick, NULL, &tmr);   // 負值：固定 1000 µs「開始到開始」
```

- 週期超時（overrun）偵測：在迴圈開頭記 `t0 = time_us_32()`，結尾算 `time_us_32() - t0`，超過預算就計數。
- 控制迴圈裡**先讀感測器、再計算、最後輸出**，並讓讀取點落在固定相位（例如 tick 一開始就讀），抖動才小。
- 運算重的部分（log、printf、通訊）移出 timer callback，用旗標或 queue 交給主迴圈 / 另一核。

### 1.4 時間戳與 dt

```c
// time_us_32() 約 71.6 分鐘溢位；用「無號減法」算差值即可跨越溢位（差值 < 2^32 µs 時正確）
uint32_t now = time_us_32();
uint32_t dt_us = now - last;          // 正確：模 2^32 減法
last = now;
// 錯誤示範：if (now > last) ...      // 溢位那一刻會出錯
// 需要長時間：time_us_64() / absolute_time_diff_us(from, to)（int64_t，to - from）
```

| 問題 | 建議 |
|---|---|
| dt 會變動 | 固定週期就用常數 dt（演算法更簡單、可預先算 `Ki*dt`、`Kd/dt`）；若必須用實測 dt，要對 dt 設上下限，防止第一次呼叫 dt 巨大或為 0 |
| 第一次呼叫 | 初始化 `last`、`y_prev` 為第一個量測值，否則微分項出現大突波 |
| 取樣時間 vs 處理時間 | 時間戳打在「取樣當下」（ADC 完成 / IRQ 進入），不是處理完成時 |
| 多感測器對齊 | 以時間戳內插或取最近者；不要假設到達順序 = 取樣順序 |
| ROS 2 | 訊息 `header.stamp` 應是**量測時間**；控制節點以 timer 固定頻率執行；單位依 REP 103 用 SI（m、s、rad、rad/s、m/s²），座標 x 前 y 左 z 上（右手系）。細節見 `ros2.md` |

---

## 2. 定點數（Fixed-point）

### 2.1 表示法與命名

一個定點數 = 整數 `raw` 搭配固定的小數位數 `FRAC`：**實際值 = raw / 2^FRAC**。

命名在不同文件不一致（Q15 的「15」是小數位；Q16.16 的「16.16」是整數位含符號 + 小數位）。**寫程式時一律用「容器型別 + FRAC」描述最不會錯**。

| 名稱 | 容器 | FRAC | 範圍 | 解析度（1 LSB） | 常見用途 |
|---|---|---|---|---|---|
| Q7 | int8_t | 7 | [−1, 1 − 2^−7] | 7.8e−3 | 少見 |
| **Q15**（CMSIS `q15_t`） | int16_t | 15 | [−1, 0.999969] | 3.05e−5 | 音訊 / ADC 樣本、係數 |
| Q2.14（又稱 Q1.14） | int16_t | 14 | [−2, 2) | 6.1e−5 | biquad 係數（a1 可接近 ±2） |
| **Q31**（CMSIS `q31_t`） | int32_t | 31 | [−1, 1 − 2^−31] | 4.66e−10 | 高精度係數、累加 |
| Q2.30 | int32_t | 30 | [−2, 2) | 9.3e−10 | biquad 係數（本檔 3.3 用） |
| **Q16.16** | int32_t | 16 | [−32768, 32767.99998] | 1.53e−5 | 通用物理量（位置、速度、增益） |
| Q8.24 | int32_t | 24 | [−128, 128) | 6.0e−8 | 小範圍高精度 |
| 無號 UQ0.32 | uint32_t | 32 | [0, 1) | 2.3e−10 | 相位累加器（一圈 = 2^32，自然繞回） |

- 角度可用「binary angle」：`uint16_t` 或 `uint32_t` 的全範圍 = 一圈（2π），加減自然模 2π，不需要 `fmod`。本檔 2.9、2.10 使用此表示法。
- Q15 無法表示 +1.0（最大 32767/32768），常數 1.0 通常寫成 32767 或 `INT16_MAX`。

### 2.2 轉換

```c
#include <stdint.h>
#define FRAC 16
typedef int32_t q16_t;
// 編譯期常數（float 運算由編譯器在編譯時算掉，不會產生執行期浮點碼）
#define Q16(x)     ((q16_t)((x) * 65536.0 + ((x) >= 0 ? 0.5 : -0.5)))   // 四捨五入
#define Q15(x)     ((int16_t)((x) * 32768.0 + ((x) >= 0 ? 0.5 : -0.5)))  // x 必須 < 1.0
// 整數 ↔ Q16
static inline q16_t q16_from_int(int32_t i) { return (q16_t)((uint32_t)i << 16); } // 左移負數是 UB，先轉無號
static inline int32_t q16_to_int_floor(q16_t a) { return a >> 16; }                // 往 −∞
static inline int32_t q16_to_int_round(q16_t a) { return (a + (1 << 15)) >> 16; }  // 四捨五入（.5 往 +∞）
// 改變 FRAC：Q16 → Q8 右移 8（捨棄精度）；Q8 → Q16 左移 8（注意溢位）
```

- 執行期 float ↔ fixed：M33 上 pico_float 提供 `fix2float(int32_t m, int e)`、`float2fix(float f, int e)`（往 −∞）、`float2fix_z`（往 0）等；**這些只在 Arm 最佳化版本存在**（`float.h` 以 `__PICO_FLOAT_ARM_OPTIMIZED` 控制，RISC-V 沒有）。可攜寫法：`(int32_t)(f * 65536.0f)`（往 0 截斷），Hazard3 上這會呼叫軟體浮點，**只在初始化時做**。
- 在 Hazard3 上，`printf("%f")` 也是軟體浮點 + double 提升；除錯輸出改印 raw 整數或 `raw >> FRAC` 與小數部分。

### 2.3 乘法（核心規則：先放大到 64 位元再移位）

兩個 FRAC 為 a、b 的數相乘，乘積 FRAC = a + b，位元寬度相加。要回到原格式就右移。

```c
// 已在主機驗證
static inline int16_t sat16(int32_t x) { return x > 32767 ? 32767 : (x < -32768 ? -32768 : (int16_t)x); }
static inline int32_t sat32(int64_t x) { return x > INT32_MAX ? INT32_MAX : (x < INT32_MIN ? INT32_MIN : (int32_t)x); }

// Q15 × Q15 → Q15：16×16 → 32 位元乘積（Q30），四捨五入後右移 15，飽和
static inline int16_t q15_mul(int16_t a, int16_t b) {
    int32_t p = (int32_t)a * b;              // 一定要先轉 int32（int16 會先被提升成 int，但寫清楚較好）
    return sat16((p + (1 << 14)) >> 15);     // 唯一會溢位的情況：(-1)×(-1) = +1 → 飽和成 32767
}
// Q16.16 × Q16.16 → Q16.16：32×32 → 64 位元
static inline int32_t q16_mul(int32_t a, int32_t b) {
    return (int32_t)(((int64_t)a * b + (1 << 15)) >> 16);    // 結果超出 ±32768 時會截斷錯誤，需要時包 sat32
}
// Q31 × Q31 → Q31
static inline int32_t q31_mul(int32_t a, int32_t b) {
    return sat32(((int64_t)a * b + (1LL << 30)) >> 31);
}
// 混合格式：Q16 值 × Q15 增益 → Q16
static inline int32_t q16_mul_q15(int32_t a, int16_t g) { return (int32_t)(((int64_t)a * g + (1 << 14)) >> 15); }
```

主機驗證結果：`q15_mul(-32768,-32768) = 32767`、`q16_mul(1.5, -2.25) = -3.375`、`q31_mul(0.5, 0.5) = 0.25`。

**最常見錯誤**：`(int64_t)(a * b)` —— 括號錯，`a*b` 先以 32 位元相乘溢位（且是 UB），再轉 64 位元已經太遲。正確是 `(int64_t)a * b`。

各架構指令對應：

| 運算 | Hazard3（RV32IMAC） | Cortex-M33 |
|---|---|---|
| 32×32 → 低 32 | `mul`（1 cycle） | `MUL` |
| 32×32 → 64（有號） | `mul` + `mulh`（各 1 cycle）＋ 64 位元移位的 `srli/slli/or` 數條 | `SMULL`（一條） |
| 64 位元累加 `acc += a*b` | `mul`+`mulh`+`add`+`sltu`+`add`+`add`（約 6 條） | `SMLAL`（一條） |
| 只要高 32 位 `(a*b)>>32` | `mulh`（1 條） | `SMMUL`；`SMMULR` 會四捨五入 |
| 16×16 雙 MAC | 無，逐一 `mul` | `SMLAD`（見 6.3） |
| 飽和到 n 位元 | Zbb `min`+`max`（2 條），或分支 | `SSAT`/`USAT`（一條），CMSIS `__SSAT(x, 16)` |

技巧：Q31 乘法若可接受少 1 bit 精度，`(int32_t)((uint32_t)(((int64_t)a * b) >> 32) << 1)`（先轉無號再左移：負數左移是 UB）在 Hazard3 是 `mulh` + `slli` 兩條，在 M33 是 `SMMUL` + `LSL`。

### 2.4 加減與飽和

```c
// 定點加減直接用整數加減（FRAC 必須相同）；溢位時兩補數會「繞回」= 大正數變大負數，控制系統裡非常危險
static inline int32_t sat_add32(int32_t a, int32_t b) {
    int32_t r;
    if (__builtin_add_overflow(a, b, &r)) return (a < 0) ? INT32_MIN : INT32_MAX;   // GCC / Clang 內建
    return r;
}
static inline int16_t sat_add16(int16_t a, int16_t b) { return sat16((int32_t)a + b); }
// 夾在 [lo, hi]：Hazard3 -O2 通常編成 Zbb max + min 兩條無分支指令
static inline int32_t clamp32(int32_t x, int32_t lo, int32_t hi) { return x < lo ? lo : (x > hi ? hi : x); }
```

- 「中間溢位、最後結果在範圍內」：兩補數模運算保證**最後結果正確**（例如 FIR 的部分和暫時溢位）。但 C 的**有號**溢位是 UB，編譯器可能做出錯誤假設 → 要依賴繞回特性時用 `uint32_t` 做累加，最後再轉回 `int32_t`。
- 需要飽和的地方：濾波器 / PID **輸出**、寫到 16-bit 緩衝區之前、PWM duty。內部累加器用夠寬的型別（int64）而不是到處飽和。

### 2.5 除法與避免除法

| 方法 | 適用 | 成本 |
|---|---|---|
| 除以 2^k：`x >> k` | 無號數、或可接受往 −∞ 捨入的有號數 | 1 cycle |
| 除以編譯期常數：直接寫 `x / 10` | 編譯器自動改成「乘以魔術數 + 移位」 | 數個 cycle（Hazard3 用 `mulhu`） |
| 32-bit 除以變數 | Hazard3 `div` 18–19 cycle；M33 硬體 `SDIV/UDIV` | 中 |
| **64-bit 除法**（例如 `((int64_t)a << 16) / b`） | 兩種核心都**沒有 64-bit 除法指令** → 呼叫 libgcc 軟體函式（Arm `__aeabi_ldivmod`、RISC-V `__divdi3`） | 很慢，熱迴圈避免 |
| 預先算倒數：`inv = ceil(2^32 / d)`，`q = (x * inv) >> 32` | 同一個 d 要除很多次（例如除以 N、除以 dt） | 1 次 `mulhu` |

```c
// 已在主機驗證：當 x * d <= 2^32 時結果與 x / d 完全相同（例如 x、d 都 < 65536）
static inline uint32_t recip_u32(uint32_t d) { return (uint32_t)(((1ull << 32) + d - 1) / d); }  // d >= 2；初始化時算一次
static inline uint32_t div_by_recip(uint32_t x, uint32_t inv) { return (uint32_t)(((uint64_t)x * inv) >> 32); }

// Q16 除法（較慢，有 64-bit 除法）
static inline int32_t q16_div(int32_t a, int32_t b) { return (int32_t)(((int64_t)a * 65536) / b); }  // b != 0
```

- 推導（精確條件）：設 `m = ceil(2^32/d)`、`e = m·d − 2^32 < d`，則 `x·m/2^32 = x/d + x·e/(d·2^32)`；只要 `x·e < 2^32`（`x·d ≤ 2^32` 為充分條件）floor 結果不變。超出範圍需要 33-bit 魔術數或結果修正一步（`if ((q+1)*d <= x) q++`）。
- 有號除以 2^k：C 的 `/` 往 0 捨入，`>>` 往 −∞（GCC 對有號數做算術右移；標準為 implementation-defined）。`-7 / 2 = -3`，`-7 >> 1 = -4`。編譯器為了 `/4` 的語意會多加修正指令；若可接受 floor，直接寫 `>>`。
- 倒數表：除數範圍小（例如 1..256）時可做 `uint32_t inv_tab[257]`。

### 2.6 捨入（rounding）

| 方式 | 寫法 | 偏差 |
|---|---|---|
| 截斷（往 −∞） | `x >> n` | 平均偏 −0.5 LSB；長期累加會漂移（例如 EMA 卡住，見 3.2） |
| 往 0（C 除法） | `x / (1 << n)` | 正負不對稱，0 附近有「死區」 |
| 四捨五入（.5 往 +∞） | `(x + (1 << (n-1))) >> n` | 幾乎無偏，只有 .5 偏正；**最常用** |
| 對稱四捨五入 | 正數同上；負數 `-((-x + half) >> n)` | 無正負偏差，多一個分支 |
| 收斂捨入（.5 到偶數） | 較複雜 | 最無偏，DSP 庫才需要 |

CMSIS-DSP 的 `arm_mult_q15` 是**截斷**（`__SSAT((a*b) >> 15, 16)`，無捨入）後飽和；要與 CMSIS 逐位元一致時不要自己加捨入。

### 2.7 溢位分析（決定累加器寬度）

| 運算 | 位元增長 |
|---|---|
| 加 / 減兩個 n-bit | n + 1 |
| N 個 n-bit 相加 | n + ceil(log2 N) |
| n-bit × m-bit | n + m（有號 × 有號：−2^(n−1)·−2^(m−1) 這一個值需要 n+m 位，其他 n+m−1 位） |
| N 個乘積相加（FIR） | n + m + ceil(log2 N)；更緊的界：\|y\| ≤ max\|x\| · Σ\|h_k\|（係數 L1 範數） |

例：16-bit ADC 樣本 × Q15 係數、64 taps：最壞 15+15+6+1 = 37 bits → int32 不夠，用 int64；但若 Σ\|h\| ≤ 1，則 \|y\| ≤ 2^15·2^15 = 2^30 → int32 足夠。

**選擇定點格式的步驟**：

1. 列出每個變數的物理範圍（最大絕對值）與需要的解析度。
2. 整數位 = ceil(log2(max)) + 1（符號）+ 1–2 位保護位（headroom）；剩下的給小數。
3. 每個乘法 / 累加處算位元增長，決定中間值用 int32 還是 int64。
4. 決定每一步的捨入方式與飽和點（通常只在輸出飽和）。
5. 寫主機測試：與 double 版本比對最大誤差（第 8 節）。

### 2.8 Hazard3 與 M33 的取捨

| | Hazard3 | Cortex-M33 |
|---|---|---|
| float 加減乘 | 軟體模擬（慢很多；`pico-sdk.md` 7.7） | 硬體單精度 |
| double | 軟體 | DCP 協處理器加速，但仍比 float 慢 |
| 建議 | Q16.16 / Q15 定點；`mul`/`mulh` 都 1 cycle，定點乘法很便宜 | float 寫法最省事；需要位元一致或 SIMD 時用 Q15 + DSP 指令 |
| 查表 vs 計算 | 查表通常勝出（但要考慮 flash cache miss，表放 RAM） | `sinf` 等仍是軟體函式，熱迴圈中查表通常仍較快 |

### 2.9 查表 + 線性內插（sin / cos / 任意函數）

```c
// 已在主機驗證：256 段表 + 線性內插，對 32767·sin 的最大誤差 3.65 LSB、RMS 1.42 LSB（Q15）
#define SIN_BITS 8
#define SIN_N    (1 << SIN_BITS)
static int16_t sin_tab[SIN_N + 1];          // 多 1 格當保護（tab[N] = tab[0]），省掉 i+1 的繞回判斷
                                            // 不加 const → 放在 RAM（.data），避免 flash cache miss
void sin_tab_init(void) {                   // 可在主機產生後貼成常數表；在 Hazard3 上執行此函式會用到軟體浮點
    for (int i = 0; i <= SIN_N; i++) sin_tab[i] = (int16_t)lroundf(32767.0f * sinf(6.28318531f * i / SIN_N));
}
// a：binary angle，0..65535 = 0..2π
static inline int16_t sin_q15(uint16_t a) {
    uint32_t i = a >> (16 - SIN_BITS);                       // 表索引（高 8 位）
    int32_t  f = a & ((1u << (16 - SIN_BITS)) - 1);          // 小數部分（低 8 位）
    int32_t y0 = sin_tab[i], y1 = sin_tab[i + 1];
    return (int16_t)(y0 + (((y1 - y0) * f) >> (16 - SIN_BITS)));
}
static inline int16_t cos_q15(uint16_t a) { return sin_q15((uint16_t)(a + 16384u)); }   // +90°
```

- 線性內插誤差上界 ≈ h²/8 · max\|f''\|（h = 表間距）。表大小加倍 → 誤差約變 1/4。
- 利用對稱性只存 1/4 週期可省 4 倍記憶體，但多了分支；RP2350 有 520 KB SRAM，通常直接存整週。
- 通用 LUT（非等距或任意函數）：先把輸入正規化成「索引 + 小數」，其餘相同。sqrt、exp、1/x 等都可這樣做；1/x、log 類在 0 附近變化劇烈，要先用 `clz` 正規化（浮點化）再查表。
- RP2350 `interp0` 的 blend 模式可硬體做「兩點之間的 8-bit 小數內插」，見 6.4。

atan2 近似（M33 float 可用）：

```c
// 已在主機驗證：最大誤差 0.0015 rad（約 0.087°）
// 多項式 atan(z) ≈ π/4·z − z(z−1)(0.2447 + 0.0663z)，0 ≤ z ≤ 1；再用象限 / 八分圓還原
float atan2_approx(float y, float x) {
    float ax = fabsf(x), ay = fabsf(y);
    float mx = ax > ay ? ax : ay, mn = ax > ay ? ay : ax;
    if (mx == 0.0f) return 0.0f;
    float z = mn / mx;                                       // 一次除法
    float r = 0.7853981634f * z - z * (z - 1.0f) * (0.2447f + 0.0663f * z);
    if (ay > ax) r = 1.5707963268f - r;
    if (x < 0)   r = 3.1415926536f - r;
    if (y < 0)   r = -r;
    return r;
}
```

### 2.10 CORDIC（只用加減與移位求 sin/cos、atan2、向量長度）

原理：把向量依序旋轉 ±atan(2^−i)，每步只需要 `x ± (y >> i)`；n 步後精度約 n bit。旋轉後長度放大 K⁻¹ ≈ 1.646760，所以起始值先乘 K ≈ 0.6072529。收斂範圍約 ±99.9°（Σ atan(2^−i) ≈ 1.743 rad），所以先做象限化簡。

```c
// 已在主機驗證：24 次迭代，sin/cos 最大誤差 1.3e-7；atan2 最大誤差約 7e-6 rad（輸入約 2^28 量級）
// 角度：uint32_t 一圈 = 2^32；x、y 為 Q30
#define CORDIC_N 24
static int32_t cordic_atan[CORDIC_N];           // atan(2^-i) / 2π · 2^32，初始化時算或貼常數
#define CORDIC_K_Q30 652032874                  // 0.6072529350 · 2^30

void cordic_sincos(uint32_t ang, int32_t *s, int32_t *c) {
    uint32_t q = (ang + (1u << 29)) >> 30;      // 最接近的象限 0..3（4 也會被 &3 變 0）
    int32_t  z = (int32_t)(ang - (q << 30));    // 剩餘角度 [-45°, 45°)
    q &= 3;
    int32_t x = CORDIC_K_Q30, y = 0;
    for (int i = 0; i < CORDIC_N; i++) {
        int32_t xs = x >> i, ys = y >> i;
        if (z >= 0) { x -= ys; y += xs; z -= cordic_atan[i]; }
        else        { x += ys; y -= xs; z += cordic_atan[i]; }
    }
    switch (q) {                                 // 轉回原象限
        case 0: *c =  x; *s =  y; break;
        case 1: *c = -y; *s =  x; break;
        case 2: *c = -x; *s = -y; break;
        default:*c =  y; *s = -x; break;
    }
}

// 向量模式：回傳 atan2(y, x)（一圈 = 2^32），*mag = sqrt(x²+y²)
// 輸入 |x|,|y| 建議 < 2^29（增益約 1.647 再乘 √2 不可溢位），但也不要太小（右移會失去精度，先左移放大）
uint32_t cordic_atan2(int32_t y, int32_t x, uint32_t *mag) {
    uint32_t z = 0;
    if (x < 0) {                                  // 先轉 ±90° 到右半平面
        int32_t t = x;
        if (y >= 0) { x =  y; y = -t; z = 1u << 30; }
        else        { x = -y; y =  t; z = 3u << 30; }
    }
    for (int i = 0; i < CORDIC_N; i++) {
        int32_t xs = x >> i, ys = y >> i;
        if (y > 0) { x += ys; y -= xs; z += (uint32_t)cordic_atan[i]; }
        else       { x -= ys; y += xs; z -= (uint32_t)cordic_atan[i]; }
    }
    if (mag) *mag = (uint32_t)(((int64_t)x * CORDIC_K_Q30) >> 30);
    return z;
}
```

- CORDIC 每次迭代約 6–8 條整數指令；24 次迭代約 150–200 條。若只需要 Q15 精度，16 次迭代即可；**查表 + 內插通常更快**，CORDIC 的優勢是 atan2 與向量長度。

### 2.11 整數平方根與 log2

```c
// 已在主機驗證（0..2e6 全部、以及 0xFFFFFFFF 等邊界）：回傳 floor(sqrt(x))，無乘法無除法，16 次迭代
uint32_t isqrt32(uint32_t x) {
    uint32_t r = 0, bit = 1u << 30;
    while (bit > x) bit >>= 2;
    while (bit) {
        if (x >= r + bit) { x -= r + bit; r = (r >> 1) + bit; }
        else              { r >>= 1; }
        bit >>= 2;
    }
    return r;
}
// 64 位元版：同樣寫法，型別改 uint64_t、bit 起始 1ull << 62
// Q16.16 開根號：sqrt(a/2^16)·2^16 = sqrt(a·2^16) → isqrt64((uint64_t)a << 16)   （主機驗證 sqrt(2) = 1.414200）

// floor(log2(x))，x > 0：Hazard3 Zbb `clz`、M33 `CLZ` 都是一條指令
static inline int ilog2_u32(uint32_t x) { return 31 - __builtin_clz(x); }   // x == 0 時 __builtin_clz 為 UB
```

- 向量長度 `sqrt(x²+y²)`：用 int64 累加平方後 isqrt64；或 CORDIC 向量模式；或「alpha max + beta min」近似 `max + min·3/8`（粗略，誤差數 %）。⚠️ 該近似的誤差界未在此驗證，用前自測。
- 比較距離時**不必開根號**：直接比 `dx²+dy²` 與 `r²`。

---

## 3. 濾波器

### 3.1 Moving average（滑動平均，O(1)）

```c
#define MA_BITS 4
#define MA_N    (1 << MA_BITS)                 // 用 2 的冪：索引用 & 繞回、除法變移位
typedef struct { int16_t buf[MA_N]; int32_t sum; uint32_t i; } ma_t;   // 全部初始化為 0
static inline int16_t ma_step(ma_t *m, int16_t x) {
    m->sum += x - m->buf[m->i];                // 加新的、減最舊的
    m->buf[m->i] = x;
    m->i = (m->i + 1) & (MA_N - 1);
    return (int16_t)(m->sum >> MA_BITS);       // 或 (sum + MA_N/2) >> MA_BITS 四捨五入
}
```

- 每點成本：2 加減 + 1 移位 + 2 記憶體存取，與 N 無關。
- **整數 running sum 永遠精確**；用 float 做 running sum 會因捨入誤差累積而漂移（要定期重算）。
- 頻率響應：sinc 形，第一個零點在 fs/N；對「週期為 N 點的干擾」（例如電源 50/60 Hz）完全抵消。群延遲 (N−1)/2 點。
- 前 N 點（buffer 未滿）輸出偏小；需要時另記有效筆數。

### 3.2 指數移動平均 EMA / 一階 IIR 低通

公式：`y[n] = y[n−1] + α (x[n] − y[n−1])`，0 < α ≤ 1。

| 關係 | 公式 |
|---|---|
| α 與時間常數 τ | α = 1 − e^(−Ts/τ) ≈ Ts/(τ + Ts) |
| α 與截止頻率（α 小時） | fc ≈ α·fs / (2π) |
| α = 2^−k | 時間常數約 2^k 個樣本；不需要乘法 |

```c
// 已在主機驗證：常數輸入 1000 → 收斂到 1000；-1000 → -1000
// 狀態 acc 帶 k 位額外小數（acc = y·2^k），避免截斷造成的穩態誤差
typedef struct { int32_t acc; } ema_t;               // 初始化：acc = 第一筆樣本 << k（用乘法避免負數左移 UB）
static inline int32_t ema_step(ema_t *f, int32_t x, int k) {
    f->acc += x - (f->acc >> k);
    return f->acc >> k;
}
// 錯誤示範（常見）：y += (x - y) >> k;
//   主機實測 k=4：從 0 往 1000 收斂卡在 985（差 < 16 時 (x-y)>>4 = 0），往負方向卻能到 -1000 → 不對稱偏差
```

- 溢位：`acc` 需要 輸入位寬 + k 位，16-bit 輸入、k ≤ 15 放 int32 安全。
- 任意 α（非 2 的冪）：`acc += ((int64_t)(x_q - y_q) * alpha_q15) >> 15` 一類寫法，但同樣要保留額外小數位。
- 高通：`hp = x − lp`（一階高通 = 原訊號減一階低通）。

### 3.3 Biquad（二階 IIR）

#### 3.3.1 係數（RBJ Audio EQ Cookbook）

```
w0 = 2π·f0/fs     alpha = sin(w0) / (2Q)     （Butterworth：Q = 1/√2 ≈ 0.7071）
低通 LPF：b0 = (1 − cos w0)/2   b1 = 1 − cos w0      b2 = (1 − cos w0)/2
高通 HPF：b0 = (1 + cos w0)/2   b1 = −(1 + cos w0)   b2 = (1 + cos w0)/2
兩者    ：a0 = 1 + alpha        a1 = −2 cos w0       a2 = 1 − alpha
全部除以 a0 正規化，差分方程：
y[n] = b0 x[n] + b1 x[n−1] + b2 x[n−2] − a1 y[n−1] − a2 y[n−2]
```

- 係數**在主機或初始化時用 double 算好**，再轉成定點常數。例：fs = 1 kHz、f0 = 10 Hz、Q = 0.7071 → b0 = 0.000944691、a1 = −1.911196288、a2 = 0.914975054。可見 a1 接近 −2 → 係數格式至少要能表示 ±2（Q2.14 / Q2.30），b0 很小 → 小數位要多。
- **符號慣例陷阱**：CMSIS-DSP 的 biquad 用 `y = b0x + b1x1 + b2x2 + a1y1 + a2y2`（**回授項是加號**），所以用 RBJ / MATLAB 算出的 a1、a2 **要取負號**再交給 CMSIS。
- 高階濾波器拆成多個 biquad 串接（cascade），不要直接實作 4 階以上的直接型（係數量化後容易不穩定）。

#### 3.3.2 結構

| 結構 | 狀態數 | 適合 | 定點注意 |
|---|---|---|---|
| Direct Form I（DF1） | 4（x1 x2 y1 y2） | **定點首選** | 只有一個累加器；中間值溢位只要最後結果在範圍內就不影響（模運算，用寬累加器） |
| Direct Form II | 2 | 少用 | 內部節點增益很大，定點易溢位 |
| **Transposed DF2（DF2T）** | 2 | **浮點首選**（M33 float） | 狀態值範圍大，定點不推薦 |

```c
// 浮點 DF2T（M33）
typedef struct { float b0, b1, b2, a1, a2, s1, s2; } bq_f_t;   // a1/a2 為 RBJ 正規化後的值（未取負）
static inline float bq_df2t(bq_f_t *f, float x) {
    float y = f->b0 * x + f->s1;
    f->s1 = f->b1 * x - f->a1 * y + f->s2;
    f->s2 = f->b2 * x - f->a2 * y;
    return y;
}
```

每點：5 乘 4 加。

#### 3.3.3 定點 DF1（Hazard3 / 需要位元一致）

```c
// 已在主機驗證（見 3.3.4）：係數 Q2.30、樣本 int16、輸出狀態帶 16 位額外小數（Q16），累加器 int64
typedef struct {
    int32_t b0, b1, b2, a1, a2;      // Q30，a1/a2 用 RBJ 正規化後的值（未取負）
    int32_t x1, x2;                  // 過去輸入（int16 樣本）
    int32_t y1, y2;                  // 過去輸出，Q16（= 樣本值 · 65536），需 |y| < 32768
} bq_q30_t;

static inline int16_t bq_q30_step(bq_q30_t *f, int16_t x) {
    int64_t acc = ((int64_t)f->b0 * x + (int64_t)f->b1 * f->x1 + (int64_t)f->b2 * f->x2) * 65536   // → Q46
                - (int64_t)f->a1 * f->y1 - (int64_t)f->a2 * f->y2;                                  // Q30·Q16 = Q46
    int32_t y = (int32_t)((acc + (1 << 29)) >> 30);          // Q46 → Q16，四捨五入
    f->x2 = f->x1; f->x1 = x;
    f->y2 = f->y1; f->y1 = y;
    return sat16((y + (1 << 15)) >> 16);                      // Q16 → int16，飽和
}
// 係數轉換（主機或初始化）：b0_q30 = lround(b0 * (1 << 30)) …
```

溢位檢查：|a1|<2 → |a1_q30| < 2^31，|y1| < 2^31 → 乘積 < 2^62；a2 項 < 2^61；b 項很小 → 總和 < 2^63，int64 不會溢位。⚠️ 此估計針對低通（b 很小）；高通 / 帶阻的 b 係數接近 ±1、±2，b 項 ×65536 後可達約 2^63 → 要重新估算，或先把輸入縮小 1–2 bit。

#### 3.3.4 實測：輸出量化對低截止頻率 biquad 的影響

主機測試（fs = 1 kHz、f0 = 10 Hz 低通，輸入 20000 的步階後接 5 Hz、振幅 10000 正弦，5000 點，對照 double 實作）：

| 實作 | 最大誤差（LSB） |
|---|---|
| Q30 係數、y 狀態只存整數（int16 精度） | **111.6**（RMS 76） |
| 同上 + 誤差回授（error feedback：保存 `acc` 被捨棄的低位，下次加回） | 5.0 |
| y 狀態保留 16 位額外小數（3.3.3 的寫法） | **0.5** |
| float DF2T | 0.52 |

結論：**極點越靠近 1（f0/fs 越小），回授路徑的量化誤差被放大越多**。定點 biquad 的回授狀態要保留額外小數位，或使用誤差回授；或提高 f0/fs（先降頻再濾）。

#### 3.3.5 CMSIS-DSP 對照（M33；pico-sdk **沒有內附 CMSIS-DSP**，只有 CMSIS-Core stub）

| 函式 | 係數陣列（每段） | 累加器 |
|---|---|---|
| `arm_biquad_cascade_df1_q15` | 6 個：`{b0, 0, b1, b2, a1, a2}`（中間的 0 是為了 SIMD 對齊）| 64-bit（34.30），最後移位 + 飽和到 Q15 |
| `arm_biquad_cascade_df1_fast_q15` | 同上 | 32-bit（2.30），只有 1 個保護位，輸入須縮到 [−0.25, 0.25) |
| `arm_biquad_cascade_df1_q31` | 5 個：`{b0, b1, b2, a1, a2}` | 64-bit |
| `arm_biquad_cascade_df1_f32` | 5 個 | float |

- `postShift`：等於把係數放大 2^postShift，讓係數可以超出 [−1, 1)（例如 a1 ≈ −1.9 時用 postShift = 1，係數除以 2 存）。
- 記得 a1、a2 **取負號**（見 3.3.1）。

### 3.4 FIR（有限脈衝響應）

`y[n] = Σ_{k=0}^{N−1} h[k] · x[n−k]`，每點 N 次 MAC。

```c
// 已在主機驗證（脈衝輸入回傳 h[0..N-1]、步階輸入收斂到 Σh）
// 「雙倍長度緩衝」：每個樣本寫兩次，讓視窗永遠連續 → 內迴圈沒有取模 / 分支
#define FN 32
static int16_t fbuf[2 * FN];
static uint32_t fpos = 0;
int32_t fir_step(const int16_t *h, int16_t x) {          // h：Q15，回傳 Q15·樣本（呼叫端再 >>15 + 飽和）
    fpos = (fpos == 0) ? FN - 1 : fpos - 1;              // 往回寫：最新樣本在 fbuf[fpos]
    fbuf[fpos] = fbuf[fpos + FN] = x;
    int32_t acc = 0;                                     // 依 2.7 確認 int32 足夠，否則用 int64
    for (int k = 0; k < FN; k++) acc += (int32_t)h[k] * fbuf[fpos + k];   // fbuf[fpos+k] = x[n-k]
    return acc;
}
```

| 優化 | 做法 | 效果 |
|---|---|---|
| 對稱係數（線性相位 FIR 皆對稱，h[k] = h[N−1−k]） | `acc += h[k] * (x[n−k] + x[n−N+1+k])`，k < N/2（奇數 N 加中間項） | 乘法減半 |
| 區塊處理 | 一次處理 B 個輸出，係數載入一次重複使用 | 減少 load |
| 迴圈展開 + 多累加器 | `#pragma GCC unroll 4`，2–4 個獨立累加器 | 減少迴圈開銷與相依（`riscv-hazard3.md` 9.1） |
| M33 SMLAD | 兩個 int16 打包成一個 32-bit 字，一條指令做 2 個 MAC | 約 2 倍（見 6.3） |
| 降頻 FIR（decimation by M） | 只計算要保留的輸出 | 減 M 倍 |
| 長濾波器（數百 taps） | FFT 區塊卷積（overlap-add） | O(log N)/點，但實作複雜 |
| 簡單低通 | 改用 moving average 或 EMA | 成本與 N 無關 |

環形緩衝的另一種寫法：`buf[(pos + k) & (N − 1)]`（N 為 2 的冪），每次 MAC 多一個 `and`。

### 3.5 Median（中值）濾波：去突波

```c
// 已在主機驗證：med3(1,5,3)=3、med3(9,2,4)=4、med3(3,3,1)=3
static inline int32_t med3(int32_t a, int32_t b, int32_t c) {   // 無分支：Zbb min/max 或 M33 條件執行
    int32_t lo = a < b ? a : b, hi = a < b ? b : a;
    int32_t m  = hi < c ? hi : c;
    return lo > m ? lo : m;
}
// 5 點：把視窗複製到暫存陣列做插入排序，取 [2]；小視窗插入排序最快、最不容易寫錯
int32_t med5(const int32_t w[5]) {
    int32_t t[5];
    for (int i = 0; i < 5; i++) {
        int32_t v = w[i]; int j = i;
        while (j > 0 && t[j - 1] > v) { t[j] = t[j - 1]; j--; }
        t[j] = v;
    }
    return t[2];
}
```

- 中值濾波保留邊緣（步階）、去除寬度 < (N+1)/2 的突波；不是線性濾波器，不能用頻率響應描述。
- 常見組合：median（去突波）→ EMA（去高頻雜訊）。
- 大視窗（> 15）才需要雙堆積或計數直方圖（8-bit 資料可用 256 格直方圖）。

### 3.6 互補濾波（IMU 姿態融合）

陀螺儀（gyro）短時間準但會漂移；加速度計（accel）長時間平均準但雜訊大、受運動加速度干擾。互補濾波 = 對 gyro 積分做高通 + 對 accel 角度做低通。

```c
// angle、gyro_rate 單位：rad、rad/s（REP 103）；dt 秒
// a = tau / (tau + dt)，tau = 交越時間常數（常見 0.1–1 s）
float comp_filter(float angle, float gyro_rate, float accel_angle, float dt, float a) {
    return a * (angle + gyro_rate * dt) + (1.0f - a) * accel_angle;
}
// accel_angle（roll）= atan2f(ay, az)；pitch = atan2f(-ax, sqrtf(ay*ay + az*az))   ← 依感測器軸向確認
```

- 定點版：角度用 binary angle（int32 一圈 2^32）或 Q16 rad；a 用 Q15；atan2 用 CORDIC（2.10）。
- 角度跨 ±π 時要先把 `accel_angle − angle` 包回 [−π, π) 再融合（binary angle 的差值自動處理）。
- 3 軸完整姿態：Mahony / Madgwick（四元數）屬於更進階內容，此處不展開。

### 3.7 一維 Kalman 濾波（常數模型）

```c
typedef struct { float x, P, Q, R; } kf1_t;      // x 估計、P 估計變異、Q 過程雜訊、R 量測雜訊
float kf1_step(kf1_t *k, float z) {
    k->P += k->Q;                               // 預測（模型：x 不變）
    float K = k->P / (k->P + k->R);             // Kalman gain
    k->x += K * (z - k->x);                     // 更新
    k->P *= (1.0f - K);
    return k->x;
}
```

- Q、R 固定時，P 與 K 會收斂成常數 → **穩態就是 EMA**，α = K∞。資源有限時直接離線算出 K∞，用 3.2 的 EMA 實作（無除法）。
- 調整：R 大（量測不可信）→ 更平滑、更慢；Q 大（模型不可信）→ 跟得更快。
- 加入速度狀態（等速模型）需要 2×2 矩陣，運算量仍小，但已超出本備援包範圍。

### 3.8 濾波器選擇表

| 需求 | 選擇 | 每點成本 |
|---|---|---|
| 簡單平滑、低記憶體 | EMA（α = 2^−k） | 2 加減 + 2 移位 |
| 平滑且能抵消固定週期干擾 | moving average | 2 加減 + 1 移位 + 2 存取 |
| 突波 | median 3/5 | 3–10 比較 |
| 精確截止頻率、陡峭度 | biquad（cascade） | 5 乘 4 加 / 段 |
| 線性相位（波形不失真） | 對稱 FIR | N/2 乘 |
| 兩種感測器互補 | 互補濾波 | 數個乘加 |
| 已知雜訊統計 | Kalman（穩態 = EMA） | 1 除法（非穩態） |

---

## 4. 控制

### 4.1 離散 PID（位置式）

連續形式 u = Kp·e + Ki∫e dt + Kd·de/dt，以固定 dt 離散化（後向差分）：

```
e[n] = r[n] − y[n]
I[n] = I[n−1] + Ki·dt·e[n]               （積分項儲存「已乘 Ki」的值 → 線上改 Ki 不會跳動）
D[n] = −Kd·(y[n] − y[n−1]) / dt          （微分取量測值：setpoint 跳動時不會產生 derivative kick）
u[n] = sat(Kp·e[n] + I[n] + D[n])
```

```c
// 名稱避開 POSIX 的 pid_t
typedef struct {
    float kp, ki_dt, kd_div_dt;      // 預先算好 ki*dt、kd/dt：迴圈內沒有除法
    float d_alpha;                   // 微分低通 EMA 係數，0 < d_alpha ≤ 1（1 = 不濾波）
    float out_min, out_max;
    float i, d, y_prev;
    int   first;
} pid_ctrl_t;

float pid_step(pid_ctrl_t *p, float r, float y) {
    if (p->first) { p->y_prev = y; p->first = 0; }       // 避免第一次微分突波
    float e = r - y;
    float d_raw = -p->kd_div_dt * (y - p->y_prev);       // 微分取量測值
    p->d += p->d_alpha * (d_raw - p->d);                 // 微分低通（雜訊會被微分放大）
    p->y_prev = y;

    float i_new = p->i + p->ki_dt * e;
    float u = p->kp * e + i_new + p->d;
    // anti-windup（條件積分 / clamping）：輸出飽和且誤差會讓它更飽和時，不更新積分
    if (u > p->out_max)      { u = p->out_max; if (e < 0) p->i = i_new; }
    else if (u < p->out_min) { u = p->out_min; if (e > 0) p->i = i_new; }
    else                     { p->i = i_new; }
    return u;
}
```

| 元件 | 為什麼需要 | 做法 |
|---|---|---|
| 輸出飽和 | 致動器有上下限（PWM 0–100%） | `clamp(u, min, max)` |
| **anti-windup** | 飽和期間積分持續累積 → 解除飽和後大幅超調 | (a) 條件積分（上面）；(b) 積分項本身夾在 [out_min, out_max]；(c) back-calculation：`i += ki_dt*e + (dt/Tt)*(u_sat − u_unsat)`，追蹤時間常數 Tt 常取 Ti 或 √(Ti·Td) 量級 |
| 微分取量測值 | setpoint 階躍時 de/dt 無限大（derivative kick） | 用 −dy/dt |
| 微分濾波 | 量測雜訊被 1/dt 放大 | 一階低通（EMA），常見時間常數 Td/N，N ≈ 5–20 |
| setpoint 斜率限制 | 避免目標突變 | 4.4 rate limiter |
| bumpless transfer | 手動 ↔ 自動切換時輸出不跳 | 切換時令 `i = u_current − kp*e − d` |

### 4.2 增量式（速度式）PID

```
Δu[n] = Kp(e[n] − e[n−1]) + Ki·dt·e[n] + (Kd/dt)(e[n] − 2e[n−1] + e[n−2])
u[n]  = sat(u[n−1] + Δu[n])
```

- 輸出直接被飽和限制，**天然 anti-windup**；適合步進馬達、閥門等「增量」型致動器。
- 缺點：Ki = 0 時，輸出 = P/PD 項 + 一個由初值與歷次飽和決定的任意偏移（沒有積分項把輸出「錨定」到誤差），飽和後這個偏移會漂移 → 增量式通常一定要有 I 項。

### 4.3 整數 PID（Hazard3）

```c
// 增益 Q16.16（例如 Kp=2.5 → 163840），量測 / 設定值為整數工程單位（例如編碼器 count、ADC 碼）
// 輸出為整數（例如 PWM level），內部積分用 int64 保留小數
typedef struct {
    int32_t kp_q16, ki_dt_q16, kd_dt_q16;       // ki*dt、kd/dt 先在主機算好
    int32_t out_min, out_max;
    int64_t i_q16;                              // 積分（Q16，輸出單位）
    int32_t y_prev;
} pid_i_t;

int32_t pid_i_step(pid_i_t *p, int32_t r, int32_t y) {
    int32_t e  = r - y;
    int64_t pt = (int64_t)p->kp_q16 * e;                        // Q16
    int64_t dt = -(int64_t)p->kd_dt_q16 * (y - p->y_prev);      // Q16
    p->y_prev = y;
    int64_t i_new = p->i_q16 + (int64_t)p->ki_dt_q16 * e;
    // 積分夾在輸出範圍（Q16）內：最簡單的 anti-windup
    int64_t imax = (int64_t)p->out_max * 65536, imin = (int64_t)p->out_min * 65536;
    if (i_new > imax) i_new = imax; else if (i_new < imin) i_new = imin;
    p->i_q16 = i_new;
    int64_t u = (pt + i_new + dt + 32768) >> 16;                // 四捨五入回整數
    if (u > p->out_max) u = p->out_max; else if (u < p->out_min) u = p->out_min;
    return (int32_t)u;
}
```

- Ki·dt 很小時 Q16 解析度可能不足（ki_dt_q16 量化成 0 或誤差很大）→ 積分改用更多小數位（例如 Q24），或積分累加原始 e，最後再乘 Ki。
- 64 位元運算在 RV32 上是多條指令，但仍遠快於軟體浮點。

### 4.4 Bang-bang、遲滯、前饋、斜率限制

```c
// 遲滯（hysteresis）開關：避免在設定點附近高速抖動（chattering）
bool on = false;
void thermostat(int32_t y, int32_t sp, int32_t h) {
    if (y < sp - h)      on = true;
    else if (y > sp + h) on = false;           // 介於兩者之間：維持原狀態
}

// 斜率限制（rate limiter）：每個週期最多變化 max_step
static inline int32_t rate_limit(int32_t cur, int32_t target, int32_t max_step) {
    int32_t d = target - cur;
    if (d > max_step) d = max_step; else if (d < -max_step) d = -max_step;
    return cur + d;
}

// 前饋（feedforward）+ 回授：已知模型時，前饋提供大部分輸出，PID 只修正誤差
// 例：馬達速度 → u = kff * speed_ref + friction_sign + pid_step(...)
```

- 遲滯寬度 h 要大於量測雜訊峰對峰值。
- 前饋不影響穩定性（不在迴路內），但模型錯誤會讓 PID 承擔剩餘誤差。

### 4.5 調參（tuning）

Ziegler–Nichols 閉迴路法：先只用 P，增大 Kp 直到持續等幅振盪，記下臨界增益 Ku 與振盪週期 Tu。

| 控制器 | Kp | Ti | Td |
|---|---|---|---|
| P | 0.5 Ku | — | — |
| PI | 0.45 Ku | Tu / 1.2 | — |
| PID | 0.6 Ku | Tu / 2 | Tu / 8 |

換算：Ki = Kp/Ti，Kd = Kp·Td。ZN 結果通常超調偏大（約 25% 量級），作為起點再手動調低。

手動調參順序（經驗法則）：

1. Ki = Kd = 0，加大 Kp 到反應夠快但開始輕微超調。
2. 加 Kd 抑制超調 / 振盪（同時要有微分濾波）。
3. 加 Ki 消除穩態誤差；出現緩慢振盪就減少 Ki。
4. 檢查飽和時的行為（anti-windup）、雜訊下的輸出抖動。

### 4.6 控制迴圈時序要求

| 項目 | 建議（經驗法則） |
|---|---|
| 取樣頻率 vs 閉迴路頻寬 | fs 約為閉迴路頻寬的 10–30 倍；太慢 → 相位延遲大、不穩；太快 → 微分雜訊大、整數解析度不足（Ki·dt 太小） |
| 計算延遲 | 「讀感測器 → 輸出」的延遲越短越好且要**固定**；延遲 = 額外相位落後 |
| jitter | 週期抖動相當於時變 dt；用硬體 timer / alarm 觸發，避免在控制迴路中 `printf` |
| 多速率 | 內迴路（電流 / 速度）快、外迴路（位置）慢，外迴路頻率通常比內迴路低 5–10 倍 |
| 量測 | 用 `time_us_32()` 或 cycle counter 量每次控制計算的最壞時間（`pico-sdk.md` 第 10 節），最壞值 < 週期的一半為宜 |

---

## 5. 訊號分析

### 5.1 FFT 基本

| 項目 | 值 |
|---|---|
| 直接 DFT | N² 次複數乘法 |
| radix-2 FFT（N = 2^m） | (N/2)·log2 N 個 butterfly，每個 1 次複數乘（4 實數乘 + 2 加）+ 2 次複數加 |
| 頻率解析度（bin 寬） | Δf = fs / N；bin k 的頻率 = k·fs/N |
| 實數輸入 | 只有 k = 0..N/2 有意義（其餘共軛對稱）；可用「N/2 點複數 FFT + 後處理」計算 |
| 觀測時間 | T = N/fs；要分辨 1 Hz 差異需要至少約 1 s 的資料 |
| 洩漏（leakage） | 訊號頻率不在 bin 中心時能量擴散 → 先乘視窗（Hann：w[n] = 0.5 − 0.5 cos(2πn/(N−1))） |
| 定點 FFT | 每一級可能增長 1 bit → 每級右移 1（block floating point）避免溢位 |

- 什麼時候值得：需要很多頻率成分（頻譜、找主頻率）時。只要少數幾個頻率 → Goertzel；只要「主頻率」且訊號乾淨 → 零交越計數更便宜。
- CMSIS-DSP 有 `arm_rfft_fast_f32` 等，但 pico-sdk 不內附；考場若不能安裝套件，就自寫 radix-2（約 40 行）或用 Goertzel。

### 5.2 Goertzel（單一頻率的能量）

```c
// 已在主機驗證：N=256、fs=1000、50 Hz 正弦 → bin 13（12.8 取整）功率 14339（bin 中心時理論值 N²/4·A² = 16384）
// k = round(N * f_target / fs)；coeff = 2 cos(2πk/N)（初始化時算）
float goertzel_power(const float *x, int n, float coeff) {
    float s1 = 0, s2 = 0;
    for (int i = 0; i < n; i++) {
        float s = x[i] + coeff * s1 - s2;     // 每點 1 乘 2 加
        s2 = s1; s1 = s;
    }
    return s1 * s1 + s2 * s2 - coeff * s1 * s2;   // = |X[k]|²
}
```

- 成本 O(N)/頻率；粗略判斷：要算的頻率數 M 小於約 log2 N 時，Goertzel 比整個 FFT 便宜。
- 可以「串流」：每來一個樣本更新一次，N 點後讀結果並清零，不需要存整個區塊。
- 定點版：狀態 s 隨 N 線性增長（共振），要用 int32/int64 並估計最大值（約 N·A / (2 sin(2πk/N)) 量級 ⚠️未驗證此界，實作前用主機測最大值）；coeff 用 Q14（範圍 ±2）。
- 應用：DTMF 偵測、檢查特定振動頻率。

### 5.3 零交越（zero-crossing）與頻率估計

```c
// 帶遲滯，避免雜訊在 0 附近產生多次交越；回傳是否偵測到「負→正」交越
typedef struct { int state; } zc_t;            // state: 0 = 低, 1 = 高
static inline int zc_step(zc_t *z, int32_t x, int32_t h) {
    if (!z->state && x > h)  { z->state = 1; return 1; }
    if ( z->state && x < -h) { z->state = 0; }
    return 0;
}
// 頻率 = 正向交越次數 / 經過時間。精度：交越時間可線性內插 t = t0 + dt · y0 / (y0 − y1)
```

- 先去 DC（減去平均或高通），否則交越點偏移。
- 只適合單一主頻率、雜訊不大的訊號。

### 5.4 峰值偵測

```c
// 串流峰值偵測：前一點比兩側大、超過門檻、且距離上一個峰至少 min_gap 點
typedef struct { int32_t p2, p1; uint32_t n, last_peak; } pk_t;
int pk_step(pk_t *s, int32_t x, int32_t thresh, uint32_t min_gap, uint32_t *peak_idx) {
    int found = 0;
    if (s->n >= 2 && s->p1 > s->p2 && s->p1 >= x && s->p1 > thresh &&
        (s->n - 1) - s->last_peak >= min_gap) {
        s->last_peak = s->n - 1; *peak_idx = s->last_peak; found = 1;   // 峰在前一點
    }
    s->p2 = s->p1; s->p1 = x; s->n++;
    return found;
}
```

- 先平滑（EMA / moving average）再找峰，否則雜訊造成大量假峰。
- 平頂（連續相等）時，上面的 `p1 > p2 && p1 >= x` 只回報平頂的**第一點**；依題目定義調整。`last_peak` 初值 0 會擋掉開頭 min_gap 點內的峰，需要時另設旗標。
- 次樣本精度：拋物線內插 `δ = 0.5·(y[−1] − y[+1]) / (y[−1] − 2y[0] + y[+1])`。

### 5.5 RMS、平均、變異數

```c
// RMS（整數）：平方和用 int64，最後 isqrt
uint32_t rms_i16(const int16_t *x, uint32_t n) {
    int64_t ss = 0;
    for (uint32_t i = 0; i < n; i++) ss += (int32_t)x[i] * x[i];
    return isqrt64((uint64_t)(ss / n));        // 64 位元除法只做一次；n 為 2 的冪時改 >>
}
// AC RMS：先減平均。σ² = E[x²] − (E[x])²；整數運算時精確（沒有浮點抵消問題），只要不溢位
```

Welford 線上演算法（float 時避免「大數相減」的災難性抵消）：

```c
typedef struct { uint32_t n; float mean, m2; } welford_t;
void welford_add(welford_t *w, float x) {
    w->n++;
    float d = x - w->mean;
    w->mean += d / (float)w->n;
    w->m2 += d * (x - w->mean);                // 用「更新後」的 mean
}
// 母體變異數 = m2 / n；樣本變異數 = m2 / (n − 1)
```

- float 的 `Σx² − (Σx)²/n`：資料平均很大、變異很小時（例如 ADC 讀數 3000 ± 2）兩個大數相減，有效位數全部消失 → 用 Welford，或先減掉一個近似平均（例如第一個樣本）再累加。
- 整數資料：`int64` 的 Σx 與 Σx² 是精確的，沒有這個問題；注意 n·Σx² 可能溢位 int64（16-bit 資料在 n < 2^31 時 Σx² < 2^61 安全，但 n·Σx² 不一定）。

---

## 6. 效能：在 RP2350 上把 kernel 做快

### 6.1 每點運算量速查

| Kernel | 乘法 | 加減 | 其他 | 備註 |
|---|---|---|---|---|
| EMA（α=2^−k） | 0 | 2 | 2 移位 | |
| Moving average | 0 | 2 | 1 移位、2 存取、1 and | |
| Median 3 | 0 | 0 | 3 比較（min/max） | |
| Biquad DF1 | 5 | 4 | 2 移位、狀態搬移 | 定點用 64-bit：Hazard3 每個 MAC 約 6 條 |
| FIR N taps | N（對稱 N/2） | N | 2N load | M33 SMLAD → N/2 條 MAC |
| PID | 3–4 | 5 | 2 比較（飽和） | 無除法（預算 ki·dt、kd/dt） |
| Goertzel | 1 | 2 | | 每頻率 |
| FFT N 點 | 2 log2 N（實數乘，每點平均） | 3 log2 N | 位元反轉 | |
| sin 查表內插 | 1 | 2 | 2 load、移位 | |
| CORDIC n 次 | 0 | 3n | 2n 移位、n 分支 | |
| isqrt32 | 0 | ~32 | 16 迴圈 | |

### 6.2 Hazard3（RISC-V）專屬技巧

- **不要讓 float 混進熱迴圈**：檢查方法 —— 反組譯找 `__addsf3`、`__mulsf3`、`__divsf3`、`__aeabi_*`、`__adddf3` 等呼叫（64 位除法：RISC-V `__divdi3`、Arm `__aeabi_ldivmod`）；或連結 map 檔看是否拉進 soft-float 函式。加 `-Wdouble-promotion -Wfloat-conversion` 找隱性轉換。
- `mul`、`mulh` 都 1 cycle → 定點乘法便宜；`div` 18–19 cycle → 迴圈內用倒數乘法（2.5）。
- Zbb：`min/max/minu/maxu`（飽和、clamp、median 無分支）、`clz`（正規化、log2）、`sext.h`（int16 符號擴展）、`rev8`（位元組序）。寫普通 C 的三元運算子，`-O2` 通常就會用上；用 `objdump -d` 確認。
- 分支預測只有單一 BTB entry（`riscv-hazard3.md` 5.3）→ 資料相依的分支（例如 median、飽和判斷）改成 min/max 無分支版本。
- load-use 停頓 1 cycle → 內迴圈先載入下一筆再算這一筆（軟體 pipelining）、展開 + 多累加器。
- 64-bit 累加在 RV32 約需 4 條指令（`add`、`sltu`、`add`、`add`）；若能證明 int32 足夠（2.7），用 int32 累加可快很多。

### 6.3 Cortex-M33 專屬技巧

- 使用 `float` 而非 `double`；常數加 `f`；用 `sinf/sqrtf/fabsf`；注意 `printf("%f")` 會提升成 double。
- 除以常數改乘倒數（`x * (1.0f/3.0f)` 由編譯器算常數）；`-ffast-math` 會讓編譯器自動做這種替換，但可能改變結果（不保證位元一致）。
- DSP 擴充（SIMD on 32-bit 暫存器）：

| 指令 | 語意 |
|---|---|
| `SMLAD Rd, Rn, Rm, Ra` | Rd = Ra + Rn[15:0]·Rm[15:0] + Rn[31:16]·Rm[31:16]（兩個有號 16×16 乘加到 32 位元）；加法溢位**不飽和**、會繞回並設定 Q flag |
| `SMLALD` | 同上但累加到 64 位元（RdHi:RdLo）—— CMSIS biquad q15 用這個 |
| `SMUAD` | 兩個 16×16 乘積相加（無累加） |
| `QADD16 / QSUB16` | 兩組 16-bit 飽和加減 |
| `SSAT / USAT` | 飽和到指定位元數 |
| `SMMUL / SMMULR` | 32×32 取高 32 位（R = 四捨五入） |
| `PKHBT / PKHTB` | 打包兩個半字 |

```c
// pico-sdk 內含 CMSIS-Core stub（CMake：target_link_libraries(app cmsis_core)；#include "RP2350.h"）
// 其 cmsis_gcc.h 在 __ARM_FEATURE_DSP 時把 __SMLAD 定義成 ACLE 的 __smlad（<arm_acle.h>）
#include <arm_acle.h>
// 兩兩打包的 Q15 FIR 內積：h、x 都 4-byte 對齊、n 為偶數
int32_t dot_q15_smlad(const int16_t *h, const int16_t *x, int n) {
    const int32_t *h2 = (const int32_t *)h, *x2 = (const int32_t *)x;   // 嚴格來說違反 strict aliasing；
    int32_t acc = 0;                                                    // 穩妥做法：memcpy 取 32-bit 或 -fno-strict-aliasing
    for (int i = 0; i < n / 2; i++) acc = __smlad(h2[i], x2[i], acc);
    return acc;                                                         // 注意 32-bit 累加溢位（2.7）
}
// 64 位元累加版：__smlald(a, b, (int64_t)acc)
```

- 雙倍長度環形緩衝（3.4）讓 x 視窗連續，但起點 `fpos` 可能是奇數 → 32-bit 讀取不對齊。M33 允許非對齊的一般 `LDR`（效能較差），但 `LDRD/LDM` 不行；簡單起見維持兩份緩衝或以 2 個樣本為單位推進。⚠️ 確切非對齊行為請查 `arm-cortex-m33.md` 或 Armv8-M 手冊。
- CMSIS-DSP 不在 pico-sdk 內；若考場環境有提供原始碼才能用。自己寫 + `__smlad` 通常足夠。

### 6.4 RP2350 硬體插值器（SIO interpolator，`hardware_interp`）

每個核心各有 2 個（`interp0`、`interp1`），位在 SIO（Arm 與 RISC-V 都可用）。暫存器讀寫 1 cycle，結果下一個 cycle 可讀。**每核各自一組**：core0 設定的 interp0 與 core1 的 interp0 是不同硬體。

資料路徑（每個 lane）：

```
lane 值 = sign_extend?( mask( rotate_right(ACCUMx 或 交叉輸入, SHIFT), MASK_LSB..MASK_MSB ) )
RESULT0 = BASE0 + (ADD_RAW ? ACCUM0 : lane0 值)
RESULT1 = BASE1 + (ADD_RAW ? ACCUM1 : lane1 值)
RESULT2（FULL）= BASE2 + lane0 值 + lane1 值              （ADD_RAW 不影響 FULL）
PEEKx：讀結果，不改狀態
POPx ：讀結果，同時把 RESULT0→ACCUM0、RESULT1→ACCUM1（CROSS_RESULT 時交叉寫回）
寫 ACCUMx_ADD（struct 的 add_raw[x]）：ACCUMx += 寫入值；讀 add_raw[x]：回傳 lane x 的 shift+mask 值（不加 BASE）
寫 BASE_1AND0（base01）：低 16 位 → BASE0、高 16 位 → BASE1（依 SIGNED 符號擴展）
```

- **RP2350 的 SHIFT 是「右旋轉（rotate）」而非右移**（RP2040 是右移）。好處：右旋 (32−k) 再遮罩 = 左移 k，可產生「索引 × 元素大小」。代價：低位會轉到高位，**必須用 MASK 把轉上來的位元遮掉**（右旋 s 位時 MASK_MSB ≤ 31−s 才等同右移）。勘誤 RP2350-E1：因為 rotate，OVERF 旗標會誤判，不要依賴 OVERF。

| 模式 | 只在 | 行為 |
|---|---|---|
| Blend | `interp0` lane 0 設 BLEND | PEEK1 = BASE0 + α·(BASE1 − BASE0)，α = lane1 shift+mask 值的低 8 位 / 256（α 最大 255/256，所以到不了 BASE1）；PEEK0 回傳 α；PEEK2 = BASE2 + lane0 值（不加 lane1）。lane1 SIGNED 決定 BASE0/1 視為有號或無號 |
| Clamp | `interp1` lane 0 設 CLAMP | PEEK0 = clamp(lane0 值, BASE0, BASE1)，不做加法；比較的有號與否由 lane0 SIGNED 決定 |

API（`#include "hardware/interp.h"`，CMake 連結 `hardware_interp`）：

| 函式 | 說明 |
|---|---|
| `interp_config interp_default_config(void)` | 全部關閉、mask 0..31（直通） |
| `interp_config_set_shift(&c, shift)` | 0..31（RP2350 為右旋） |
| `interp_config_set_mask(&c, lsb, msb)` | 保留 lsb..msb（含） |
| `interp_config_set_signed(&c, b)` | 從 mask MSB 符號擴展 |
| `interp_config_set_cross_input(&c, b)` | 改用另一 lane 的累加器當輸入 |
| `interp_config_set_cross_result(&c, b)` | POP 時把另一 lane 的結果寫回本累加器 |
| `interp_config_set_add_raw(&c, b)` | lane 結果用未 shift/mask 的累加器值 |
| `interp_config_set_blend(&c, b)` | 只能用在 interp0 lane 0 |
| `interp_config_set_clamp(&c, b)` | 只能用在 interp1 lane 0 |
| `interp_config_set_force_bits(&c, bits)` | 結果 bit 29:28 OR 上 0..3（產生指標用） |
| `interp_set_config(interp, lane, &c)` | 寫入 CTRL_LANEx |
| `interp_set_base / interp_get_base(interp, idx[, v])`、`interp_set_base_both(interp, v)` | BASE0/1/2、BASE_1AND0 |
| `interp_set_accumulator / interp_get_accumulator(interp, lane[, v])` | |
| `interp_add_accumulator(interp, lane, v)` | 寫 ACCUMx_ADD |
| `interp_peek_lane_result / interp_pop_lane_result(interp, lane)` | lane 0/1 |
| `interp_peek_full_result / interp_pop_full_result(interp)` | RESULT2 |
| `interp_get_raw(interp, lane)` | 讀 add_raw：shift+mask 值 |
| `interp_save(interp, &s)` / `interp_restore(interp, &s)`（`interp_hw_save_t`） | **ISR 與主程式共用 interpolator 時，ISR 進出要存 / 還原** |
| `interp_claim_lane(interp, lane)` / `interp_unclaim_lane` | 宣告佔用（避免多個模組衝突） |
| 直接存取：`interp0->accum[i]`、`->base[i]`、`->peek[i]`、`->pop[i]`、`->add_raw[i]`、`->base01`、`->ctrl[i]` | 最快 |

範例 A：Q16.16 控制量 → 整數並夾在 [0, TOP]（一次寫 + 一次讀完成「右移 + 符號擴展 + 飽和」）

```c
// ⚠️ 未在硬體上測試；寫法依 datasheet §3.1.10.3 clamp 範例（shift 2 / mask 0..29 / signed）推廣
interp_config c = interp_default_config();
interp_config_set_shift(&c, 16);          // 右旋 16
interp_config_set_mask(&c, 0, 15);        // 31-16 = 15：遮掉轉上來的小數位
interp_config_set_signed(&c, true);       // 從 bit 15 符號擴展（整數部分須在 int16 範圍）
interp_config_set_clamp(&c, true);
interp_set_config(interp1, 0, &c);
interp1->base[0] = 0;                     // 下限
interp1->base[1] = TOP;                   // 上限
// 迴圈內：
interp1->accum[0] = (uint32_t)u_q16;
uint32_t level = interp1->peek[0];        // = clamp(u_q16 >> 16, 0, TOP)
```

在 Hazard3 上同樣的事是 `srai` + `max` + `min` 三條指令，interpolator 只省 1 條；**單獨做飽和不值得**，值得的是把「shift + mask + 加 base + 累加器前進」合在一次 POP 的情況（範例 B）。

範例 B：相位累加器 + 查表位址（NCO / DDS，正弦波產生）

```c
// ⚠️ 未在硬體上測試；結構同 datasheet §3.1.10.5 texture mapping（ADD_RAW + POP2）
// phase：uint32 一圈 = 2^32；表 256 筆 int16 → 位址 = tab + (phase >> 24) * 2
interp_config c0 = interp_default_config();
interp_config_set_add_raw(&c0, true);     // RESULT0 = BASE0(step) + ACCUM0 → POP 時相位前進
interp_config_set_shift(&c0, 23);         // 右旋 23：bit 24..31 移到 bit 1..8
interp_config_set_mask(&c0, 1, 8);        // = (phase >> 24) << 1（int16 位元組偏移）
interp_set_config(interp0, 0, &c0);
interp_config c1 = interp_default_config();
interp_set_config(interp0, 1, &c1);       // lane1：accum1 = base1 = 0 → 對 FULL 貢獻 0
interp0->accum[0] = phase0;  interp0->base[0] = step;   // step = f_out / fs · 2^32
interp0->accum[1] = 0;       interp0->base[1] = 0;
interp0->base[2]  = (uintptr_t)sin_tab;
for (int i = 0; i < n; i++)
    out[i] = *(const int16_t *)interp0->pop[2];        // 一次 load 得到位址並前進相位
```

範例 C：兩點線性內插（blend）—— datasheet §3.1.10.4 示範用 ACCUM0 保存「整數 + 12 位小數」位置，lane0（BLEND）產生 int16 陣列的位元組偏移，lane1（CROSS_INPUT + SIGNED）取小數的高 8 位當 α；每步讀 PEEK2 得到樣本對位址，把兩個樣本寫進 BASE0/BASE1，讀 PEEK1 得到內插值，再寫 `add_raw[0] = step` 前進。α 只有 8 bit，精度約 1/256。SDK 的音訊升頻就是用這招。

### 6.5 ADC + DMA 雙緩衝與雙核分工

```c
// 結構同 pico-dma.md 4.6（兩通道互相 chain 的 ping-pong），改成從 ADC FIFO 讀 16-bit
#include "hardware/adc.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#define NS 256
static uint16_t abuf[2][NS];
static int ach[2];
static volatile int a_ready = -1;

static void adc_dma_isr(void) {
    for (int k = 0; k < 2; k++) {
        if (dma_channel_get_irq0_status(ach[k])) {
            dma_channel_acknowledge_irq0(ach[k]);
            dma_channel_set_write_addr(ach[k], abuf[k], false);   // 重設位址，等對方 chain 回來
            a_ready = k;
        }
    }
}

void adc_stream_start(uint32_t fs_hz) {
    adc_init();
    adc_gpio_init(26);
    adc_select_input(0);
    adc_fifo_setup(true, true, 1, false, false);   // 啟用 FIFO、DREQ、門檻 1、不放錯誤位、不右移
    adc_set_clkdiv(48000000.0f / fs_hz - 1.0f);    // 例：10 kHz → 4799
    ach[0] = dma_claim_unused_channel(true);
    ach[1] = dma_claim_unused_channel(true);
    for (int k = 0; k < 2; k++) {
        dma_channel_config c = dma_channel_get_default_config(ach[k]);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
        channel_config_set_read_increment(&c, false);
        channel_config_set_write_increment(&c, true);
        channel_config_set_dreq(&c, DREQ_ADC);
        channel_config_set_chain_to(&c, ach[k ^ 1]);
        dma_channel_configure(ach[k], &c, abuf[k], &adc_hw->fifo, NS, false);
    }
    dma_set_irq0_channel_mask_enabled((1u << ach[0]) | (1u << ach[1]), true);
    irq_set_exclusive_handler(DMA_IRQ_0, adc_dma_isr);
    irq_set_enabled(DMA_IRQ_0, true);
    dma_channel_start(ach[0]);
    adc_run(true);
}
// 處理端：看到 a_ready == k 就處理 abuf[k]（必須在 NS/fs 時間內處理完，否則被覆蓋）
```

- 時間預算：每個 buffer 有 NS/fs 秒（256 點 @ 10 kHz = 25.6 ms）處理。處理時間 / 預算 = CPU 使用率；用 `time_us_32()` 量。
- 區塊處理（block processing）比逐點處理快：函式呼叫、狀態載入 / 存回的開銷分攤到整個區塊；狀態放區域變數（暫存器）、迴圈結束再寫回 struct。
- 雙核分工（`multicore-sync.md`）：
  - core1：收資料 + 濾波（DMA IRQ 設在 core1：在 core1 上呼叫 `irq_set_exclusive_handler` / `irq_set_enabled`，IRQ 會在呼叫的那個核心啟用）。
  - core0：控制律、通訊（USB / UART / ROS 2 橋接）。
  - 交換：小資料用 `multicore_fifo_push_blocking` / `pop`；結構資料用 `pico/util/queue.h` 或 SPSC ring buffer。共享變數要考慮撕裂讀取（64-bit 或 struct 用鎖或序號）。
  - interpolator 是每核獨立的，各核各自設定。
- 查表 / 熱函式放 RAM（`pico-sdk.md` 8.2：`__not_in_flash_func`、`__not_in_flash("grp")`），避免 flash cache miss 造成時間不固定。

### 6.6 通用優化順序（kernel 層級）

1. **先量測**（`03-optimize.md`）：確認瓶頸真的在這個 kernel。
2. 演算法：O(N) running sum 取代 O(N·W) 重算；Goertzel 取代 FFT；EMA 取代長 FIR；不開根號直接比平方。
3. 數值格式：Hazard3 → 定點；M33 → float（非 double）或 Q15 SIMD。
4. 去除除法、`%`、函式呼叫（`static inline`）、浮點轉換。
5. 記憶體：表與緩衝放 SRAM、連續存取、2 的冪大小。
6. 迴圈：展開、多累加器、把不變量移出迴圈、`restrict` 指標。
7. 硬體：DMA 搬資料、interpolator 算位址、第二核心、PIO 做精準時序 IO。
8. 每一步**與參考輸出比對**（第 8 節），確定沒有改變結果。

---

## 7. 數值陷阱總表

| 陷阱 | 症狀 | 對策 |
|---|---|---|
| `(int64_t)(a*b)` 括號錯 | 大數相乘結果錯 | `(int64_t)a * b` |
| 有號溢位是 UB | `-O2` 下行為怪異、迴圈被優化掉 | 用 int64、`__builtin_*_overflow`、無號累加 |
| 左移負數是 UB | UBSan 報 `left shift of negative value` | 用乘法 `x * (1 << n)` 或先轉無號 |
| 有號右移 | 往 −∞ 捨入（GCC 為算術移位；標準為 implementation-defined） | 需要往 0 捨入時用 `/` |
| 捨入偏差 | 長時間累加後漂移；EMA 停在目標下方 | 加 0.5 LSB 再移位；保留額外小數位 |
| 符號擴展 | int16 讀成 uint16、`uint8_t` 差值變大正數 | 計算前轉成正確有號型別；Hazard3 `sext.h` |
| `char` 有無號 | x86 預設有號，**Arm 與 RISC-V 預設無號** → 主機測試和板子結果不同 | 一律用 `int8_t` / `uint8_t` |
| `long` 寬度 | x86-64 Linux 為 64 位，RP2350 為 32 位 | 用 `<stdint.h>` 型別 |
| 飽和 vs 繞回 | 兩補數溢位：最大正數 + 1 = 最大負數，馬達反轉 | 在輸出處飽和 |
| Q15 −1 × −1 | 結果 +1 無法表示 | 飽和到 32767 |
| float 精度 | float 只有 24 位尾數：16777216.0f + 1.0f == 16777216.0f；時間戳用 float 秒數會失去 µs 精度 | 時間用整數 µs；累加器用 int 或 double（M33）|
| 災難性抵消 | 平均大、變異小時 Σx² − (Σx)²/n 為負或亂數 | Welford；先減近似平均；整數運算 |
| 比較浮點相等 | `0.1f + 0.2f == 0.3f` 不保證成立 | `fabsf(a − b) <= eps · max(1, \|a\|, \|b\|)` |
| 隱性 double | `x * 0.5`、`sin()`、`printf("%f")` | 常數加 `f`、`sinf`、`-Wdouble-promotion` |
| FMA 合併 | M33 上 `a*b+c` 可能被合併成一條 VFMA，結果與主機不同 | `-ffp-contract=off` 取得較一致的結果；或改用定點 |
| 位元一致性 | judge 比對精確輸出 | 定點 + 固定捨入；或照題目給的參考實作逐步複製（含運算順序） |
| 除以 0 | Hazard3 `div` 不 trap（回傳 −1），C 層級為 UB | 除法前檢查；dt 設下限 |
| 濾波器初始狀態 | 開機前幾百點輸出偏離（從 0 爬升） | 以第一筆樣本初始化狀態 |
| 積分飽和 | 解除飽和後大幅超調 | anti-windup（4.1） |
| 時間溢位 | `time_us_32` 71.6 分鐘回繞 | 無號減法算差值 |

---

## 8. 測試 kernel：主機參考比對

在 Linux / 容器內，把 kernel 原始碼（只依賴 `<stdint.h>`、不含 pico 標頭）和 double 參考實作一起編譯，用已知訊號比對。

```c
// test_kernel.c —— gcc -O2 -Wall -Wextra -fsanitize=undefined,address test_kernel.c kernel.c -lm && ./a.out
#include <stdio.h>
#include <math.h>
#include <stdint.h>
#include "kernel.h"          // 待測的定點實作，例如 bq_q30_step、ema_step

typedef struct { double max_abs, sum_sq; long n; } err_t;
static void err_add(err_t *e, double got, double ref) {
    double d = fabs(got - ref);
    if (d > e->max_abs) e->max_abs = d;
    e->sum_sq += d * d; e->n++;
}
int main(void) {
    err_t e = {0};
    for (int i = 0; i < 10000; i++) {
        int16_t x = (i == 0) ? 10000 : 0;                    // 1) 脈衝 → 看脈衝響應
        // int16_t x = (i >= 100) ? 10000 : 0;               // 2) 步階 → 看穩態值、超調、上升時間
        // int16_t x = (int16_t)lround(10000*sin(2*M_PI*50*i/1000.0));  // 3) 正弦 → 看增益 / 相位
        double ref = reference_double(x);                    // 同演算法的 double 版
        double got = kernel_fixed(x);
        err_add(&e, got, ref);
    }
    printf("max abs err = %.3f LSB, RMS err = %.3f LSB\n", e.max_abs, sqrt(e.sum_sq / e.n));
    return e.max_abs > 2.0;                                  // 門檻依需求訂；非 0 結束碼方便腳本判斷
}
```

| 測試訊號 | 檢查什麼 |
|---|---|
| 全 0 | 輸出必須全 0（偏移、初始化錯誤） |
| 脈衝 | 脈衝響應 = FIR 係數 / IIR 衰減是否穩定 |
| 步階 | 穩態值（DC 增益）、是否卡在目標下方（捨入偏差）、超調 |
| 正弦（通帶 / 截止 / 阻帶各一） | 增益是否符合設計（截止頻率處約 −3 dB = 0.707） |
| 最大振幅 / 最小振幅交替 | 溢位、飽和是否正確 |
| 隨機 | 與參考的最大誤差、RMS 誤差 |
| 邊界值 | INT16_MIN、INT16_MAX、0、−1 |

- 指標：最大絕對誤差（LSB）、RMS 誤差、SNR = 10·log10(Σref² / Σ(got−ref)²)。
- 位元一致比對：把輸出寫成文字檔，`diff` 或 `cmp`；或計算雜湊（例如 32-bit FNV）比較。
- 加 `-fsanitize=undefined` 抓有號溢位、負數左移；`-Wconversion` 抓隱性截斷。
- 主機與目標差異：`char` 有無號、`long` 寬度、float FMA；kernel 只用 `int32_t/int64_t` 等固定寬度型別才能保證兩邊相同。
- 在板子上：用同一組輸入陣列（編進程式）跑一次，經 USB / UART 印出結果與雜湊，和主機比對。

---

## 9. 除錯檢查清單

1. 輸出全 0 或常數？→ 係數轉定點時是否全變 0（FRAC 太少）；移位方向；初始化。
2. 輸出爆掉 / 正負亂跳？→ 溢位（乘法括號、累加器寬度）；IIR 係數符號（CMSIS 要取負）；量化後極點跑出單位圓。
3. 輸出停在目標附近一點點？→ 截斷偏差（EMA 寫法、`>>` 沒加捨入）。
4. 結果和主機不同？→ `char` 有無號、`long` 寬度、float FMA、未初始化變數、UB。
5. 控制迴路振盪？→ Kp/Kd 太大、迴圈延遲太大、dt 與實際週期不符、微分沒濾波、量測單位錯（deg vs rad、count vs m）。
6. 解除飽和後大超調？→ anti-windup。
7. 設定點改變時輸出突跳？→ 微分改取量測值；setpoint 斜率限制。
8. 頻率估計錯？→ 混疊（fs 不夠、沒做抗混疊）、bin 計算（k·fs/N）、窗函數。
9. 偶發錯誤？→ ISR 與主程式共用變數撕裂；DMA buffer 在處理時被覆蓋（處理太慢）；interpolator 在 ISR 中被改而未 save/restore。
10. 時間不固定？→ flash cache miss（熱碼 / 表放 RAM）、IRQ 干擾、`printf` 在迴圈中。
11. Hazard3 特別慢？→ 反組譯找 soft-float / `__divdi3` 呼叫（Arm 版 64 位除法是 `__aeabi_ldivmod`）。

## 10. 優化檢查清單

- [ ] 量到 kernel 的實際 cycle / µs（多次取中位數或最小值），並記錄 baseline。
- [ ] 熱迴圈內沒有 float（Hazard3）/ double（M33）/ 64-bit 除法 / `%` / `printf`。
- [ ] 除數是 2 的冪或編譯期常數，否則已改為倒數乘法。
- [ ] 緩衝大小為 2 的冪，索引用 `&`；或使用雙倍長度緩衝消除繞回。
- [ ] 累加器寬度經過分析（int32 夠就不用 int64）。
- [ ] 分支改無號 / min-max（Hazard3 單 entry BTB）。
- [ ] 熱函式 `static inline` 或 `__not_in_flash_func`；查表放 RAM。
- [ ] 區塊處理，狀態放區域變數。
- [ ] 迴圈展開 + 多累加器（注意浮點加法順序改變會改變結果）。
- [ ] M33：16-bit 資料用 `__smlad`；飽和用 `__ssat`。
- [ ] 資料搬運交給 DMA；取樣交給 ADC 自由執行 / 硬體 timer；重運算移到 core1。
- [ ] 每次修改後與參考輸出比對，結果相同（或誤差在規格內）。

---

## 11. 向模型提問的範本

### 11.1 浮點演算法轉定點

```
我在 RP2350 的 {{Hazard3 RISC-V / Cortex-M33}} 上，要把下面的浮點演算法改成定點數：
{{貼上 C 程式碼}}
各變數的物理範圍：{{例如 x: ±4096（ADC 碼）、gain: 0..8、輸出: 0..1000}}
精度需求：{{例如 誤差 < 1 LSB / 與參考輸出逐位元相同}}
請：(1) 為每個變數選 Q 格式（容器型別 + 小數位數）並說明理由；(2) 標出每個乘法 / 累加的位元增長與是否需要 int64；
(3) 指定每處的捨入與飽和；(4) 給出完整 C 程式（只用 stdint 型別，不用 float）；
(5) 附一個主機上的測試程式，與 double 版本比較最大誤差與 RMS 誤差。
```

### 11.2 設計與實作濾波器

```
取樣頻率 {{fs}} Hz，訊號 {{描述，例如 IMU 加速度，含 {{f_noise}} Hz 振動雜訊與偶發突波}}。
需求：{{例如 保留 0–{{f_pass}} Hz、延遲 < {{N}} ms、每點運算 < {{cycles}} cycles}}，平台 {{Hazard3 / M33}}。
請比較 EMA、moving average、median、biquad、FIR 哪一個（或組合）最合適，給出係數計算（用 double 在主機算）、
定點或 float 實作、每點運算量，並說明低截止頻率時的量化問題要怎麼處理。
```

### 11.3 PID 控制器檢查

```
這是我的 PID 控制程式（控制 {{對象，例如 直流馬達轉速}}，迴圈頻率 {{Hz}}，輸出範圍 {{min..max}}）：
{{貼上程式碼}}
觀察到的問題：{{例如 設定點改變時輸出突跳 / 飽和後大超調 / 穩態抖動}}。
請逐項檢查：dt 是否正確且固定、微分是否取量測值並有濾波、anti-windup、輸出飽和、整數溢位與捨入、
第一次呼叫的初始化，指出具體行號與修正後的程式碼。
```

### 11.4 kernel 效能優化

```
以下 kernel 在 RP2350 {{Hazard3 / M33}}、clk_sys {{150 MHz}} 上每個樣本花 {{X}} cycles，目標 {{Y}} cycles：
{{貼上程式碼}}
反組譯片段：{{貼上 objdump 熱迴圈}}
限制：輸出必須與原版 {{逐位元相同 / 誤差 < Z}}。
請依「演算法 → 數值格式 → 去除除法與浮點 → 記憶體擺放 → 迴圈展開 → 硬體（DMA / interpolator / SMLAD / 第二核心）」的順序列出可行改法，
估計每項的收益，先給最有把握的一項的完整程式碼，並說明如何驗證結果沒變。
```

### 11.5 用 RP2350 interpolator 加速

```
我的熱迴圈做的是：{{例如 phase += step; idx = phase >> 24; y = tab[idx];}}，跑在 core {{0/1}}，{{有 / 沒有}} ISR 也用 interpolator。
請根據 RP2350 datasheet §3.1.10（注意 RP2350 的 SHIFT 是右旋轉，必須用 MASK 遮掉轉上來的位元）與 pico-sdk hardware_interp API，
設計 lane 0 / lane 1 的 shift、mask、signed、add_raw、cross 設定與 BASE0/1/2 的值，寫出設定與迴圈程式碼，
並逐步推導一個具體輸入的結果以證明正確；如果 interpolator 不會比純 C 快，請直接說明。
```
