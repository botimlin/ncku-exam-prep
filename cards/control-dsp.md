# 貼上卡：嵌入式控制與 DSP（定點數、濾波、PID）
> 用法：一次只複製一張卡（兩條分隔線之間），貼進對話，再在下面寫你的問題。每張 ≤ 1200 字元。
> 來源：full/domain/control-dsp.md、lite/domain/control-dsp.md（詳細版）｜最後更新 2026-11

---

【參考卡｜控制DSP 1/8｜平台選擇與定點格式（RP2350）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2，非 RP2040），兩種核心可選：
- Hazard3（RISC-V）：無 FPU，float 全部軟體模擬 → 用定點數。mul/mulh 各 1 cycle，div 18–19 cycle，有 Zbb min/max/clz。
- Cortex-M33：單精度 FPU，可用 float，不要 double（常數寫 1.0f）；DSP 指令 SMLAD（兩個 16×16 乘加）、SSAT、SMMUL。
- 兩核都沒有 64-bit 除法指令（呼叫軟體 __divdi3，很慢）。
- Hazard3 執行期 float↔定點轉換是軟體浮點，只在初始化做；fix2float/float2fix 只在 Arm 版 pico_float 有。
- 要和 judge 逐位元一致 → 定點 + 固定捨入規則（float 會因 FMA、旗標、平台差末位）。
定點：實際值 = raw / 2^FRAC。寫程式時用「容器型別 + FRAC」描述最不會錯。
| 名稱 | 容器 | FRAC | 範圍 | 用途 |
|---|---|---|---|---|
| Q15 | int16_t | 15 | [−1, 0.999969] | ADC/音訊樣本、係數 |
| Q2.14 | int16_t | 14 | [−2, 2) | biquad 係數 |
| Q31 | int32_t | 31 | [−1, 1) | 高精度係數 |
| Q2.30 | int32_t | 30 | [−2, 2) | biquad 係數（a1 可近 ±2） |
| Q16.16 | int32_t | 16 | [−32768, 32768) | 通用物理量 |
| UQ0.32 | uint32_t | 32 | [0, 1) | 相位累加器，一圈 2^32 |
- Q15 不能表示 +1.0，常數 1.0 寫 32767。
- 角度可用 binary angle（uint16/uint32 全範圍 = 2π），自然繞回。
- 選格式：列出每個變數最大絕對值 → 整數位 = ceil(log2(max)) + 1 符號位 + 1–2 保護位 → 其餘給小數 → 每個乘法/累加算位元增長決定 int32 或 int64 → 只在輸出飽和 → 主機與 double 比對。

---

【參考卡｜控制DSP 2/8｜定點乘法與轉換（C，主機已驗證）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
適用 RP2350 Hazard3 / Cortex-M33 與主機，只用 <stdint.h>。規則：先放大到 64 位元再移位。
```c
#define Q16(x) ((q16_t)((x) * 65536.0 + ((x) >= 0 ? 0.5 : -0.5)))  // 編譯期常數，四捨五入
static inline int16_t sat16(int32_t x) { return x > 32767 ? 32767 : (x < -32768 ? -32768 : (int16_t)x); }
static inline int32_t sat32(int64_t x) { return x > INT32_MAX ? INT32_MAX : (x < INT32_MIN ? INT32_MIN : (int32_t)x); }
static inline int16_t q15_mul(int16_t a, int16_t b) {
    int32_t p = (int32_t)a * b;
    return sat16((p + (1 << 14)) >> 15);     // (-1)×(-1) 飽和成 32767
}
static inline int32_t q16_mul(int32_t a, int32_t b) {
    return (int32_t)(((int64_t)a * b + (1 << 15)) >> 16);
}
static inline int32_t q31_mul(int32_t a, int32_t b) {
    return sat32(((int64_t)a * b + (1LL << 30)) >> 31);
}
static inline q16_t q16_from_int(int32_t i) { return (q16_t)((uint32_t)i << 16); } // 左移負數是 UB
static inline int32_t q16_to_int_round(q16_t a) { return (a + (1 << 15)) >> 16; }
```
（q16_t 為 int32_t。）驗證：q15_mul(-32768,-32768)=32767、q16_mul(1.5,-2.25)=-3.375、q31_mul(0.5,0.5)=0.25。
- 最常見錯誤：`(int64_t)(a * b)` 括號錯，a*b 先以 32 位元溢位（UB）。正確是 `(int64_t)a * b`。

---

【參考卡｜控制DSP 3/8｜捨入、除法、溢位與數值陷阱】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
情境：RP2350（Hazard3 / M33）或主機上的定點 C 程式。
捨入：CMSIS-DSP arm_mult_q15 是截斷再飽和（要一致就別加捨入）。`x >> n` 往 −∞（平均偏 −0.5 LSB，長期累加漂移）；C 的 `/` 往 0；最常用四捨五入 `(x + (1 << (n-1))) >> n`。`-7 / 2 = -3`，`-7 >> 1 = -4`。
除法：
- 除以 2^k 用移位；除以編譯期常數直接寫，編譯器轉乘法。
- 同一個變數 d 要除很多次 → 倒數乘法（主機已驗證，x·d ≤ 2^32 時與 x/d 完全相同）：
```c
static inline uint32_t recip_u32(uint32_t d) { return (uint32_t)(((1ull << 32) + d - 1) / d); }  // d >= 2，初始化算一次
static inline uint32_t div_by_recip(uint32_t x, uint32_t inv) { return (uint32_t)(((uint64_t)x * inv) >> 32); }
```
位元增長：加兩個 n-bit → n+1；N 項和 → +ceil(log2 N)；n×m → n+m；FIR 更緊界 |y| ≤ max|x|·Σ|h|。
陷阱：
- 有號溢位、負數左移是 UB → int64、無號累加、乘法 `x * (1 << n)`。
- 溢位繞回：最大正數 + 1 = 最大負數（馬達反轉）→ 輸出處飽和；內部累加器用夠寬型別。
- `char` 在 Arm 與 RISC-V 預設無號、x86 有號；`long` 在 RP2350 32 位、x86-64 Linux 64 位 → 用 int8_t、int32_t。
- float 只有 24 位尾數：16777216.0f + 1.0f == 16777216.0f；時間用整數 µs。
- 隱性 double：`x * 0.5`、`sin()`、`printf("%f")` → 常數加 f、`-Wdouble-promotion`。
- Hazard3 div 除以 0 不 trap（回傳 −1），C 為 UB → 先檢查。
- 抓隱性浮點/64 位除法：objdump 找 __mulsf3、__adddf3、__divdi3。

---

【參考卡｜控制DSP 4/8｜便宜濾波器：EMA、移動平均、中值（C，主機已驗證）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
EMA / 一階低通：`y[n] = y[n−1] + α(x[n] − y[n−1])`。α = 2^−k 時時間常數約 2^k 樣本，不需乘法；α ≈ Ts/(τ+Ts)；fc ≈ α·fs/(2π)。
```c
// 狀態 acc 帶 k 位額外小數（acc = y·2^k），避免截斷造成穩態誤差
typedef struct { int32_t acc; } ema_t;   // 初始化：acc = 第一筆樣本 * (1 << k)
static inline int32_t ema_step(ema_t *f, int32_t x, int k) {
    f->acc += x - (f->acc >> k);
    return f->acc >> k;
}
```
- 錯誤寫法：`y += (x - y) >> k;` 實測 k=4 從 0 往 1000 收斂卡在 985，往負方向卻到 -1000（不對稱偏差）。
- 16-bit 輸入、k ≤ 15 時 acc 用 int32 安全。高通 = x − 低通。
移動平均（N = 2^k，O(1)，整數永遠精確）：
```c
#define MA_BITS 4
#define MA_N (1 << MA_BITS)
typedef struct { int16_t buf[MA_N]; int32_t sum; uint32_t i; } ma_t;   // 全部初始化為 0
// ma_step(ma_t *m, int16_t x) 本體：
m->sum += x - m->buf[m->i];
m->buf[m->i] = x;
m->i = (m->i + 1) & (MA_N - 1);
return (int16_t)(m->sum >> MA_BITS);
```
- 第一個零點在 fs/N，可完全抵消週期 N 點的干擾；前 N 點輸出偏小。
中值（去突波，保留步階）：
```c
static inline int32_t med3(int32_t a, int32_t b, int32_t c) {
    int32_t lo = a < b ? a : b, hi = a < b ? b : a;
    int32_t m  = hi < c ? hi : c;
    return lo > m ? lo : m;
}
```
常見組合：median 去突波 → EMA 去高頻。濾波狀態用第一筆樣本初始化。

---

【參考卡｜控制DSP 5/8｜Biquad 二階 IIR（RBJ 係數 + 定點 DF1）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
係數（RBJ Audio EQ Cookbook，在主機或初始化用 double 算）：
w0 = 2π·f0/fs，alpha = sin(w0)/(2Q)（Butterworth Q = 0.7071）
LPF：b0 = (1−cos w0)/2，b1 = 1−cos w0，b2 = (1−cos w0)/2
HPF：b0 = (1+cos w0)/2，b1 = −(1+cos w0)，b2 = (1+cos w0)/2
共同：a0 = 1+alpha，a1 = −2cos w0，a2 = 1−alpha；全部除以 a0。
y[n] = b0x[n] + b1x[n−1] + b2x[n−2] − a1y[n−1] − a2y[n−2]
例：fs=1kHz、f0=10Hz → b0=0.000944691、a1=−1.911196288、a2=0.914975054（a1 近 −2 → 係數格式要能表示 ±2）。
定點 DF1（bq_q30_step 本體；係數 b0..a2 為 Q2.30、a1/a2 用 RBJ 正規化值未取負；x1,x2 為 int16 樣本；y1,y2 為 Q16 且 |y| < 32768；累加器 int64）：
```c
int64_t acc = ((int64_t)f->b0 * x + (int64_t)f->b1 * f->x1 + (int64_t)f->b2 * f->x2) * 65536
            - (int64_t)f->a1 * f->y1 - (int64_t)f->a2 * f->y2;   // Q46
int32_t y = (int32_t)((acc + (1 << 29)) >> 30);                    // Q46 → Q16
f->x2 = f->x1; f->x1 = x;
f->y2 = f->y1; f->y1 = y;
return sat16((y + (1 << 15)) >> 16);
```
- 實測（f0/fs=0.01）：y 狀態只存整數誤差 111.6 LSB；保留 16 位額外小數 0.5 LSB。極點越靠近 1 越要保留。
- ⚠️ int64 不溢位的估計只針對低通；高通 b 係數接近 ±1、±2 要重新估算或先縮小輸入。
- 浮點（M33）用 Transposed DF2；定點用 DF1。4 階以上拆成多個 biquad 串接。
- CMSIS-DSP biquad 回授項是加號 → RBJ 的 a1、a2 要取負號再給。pico-sdk 沒內附 CMSIS-DSP。

---

【參考卡｜控制DSP 6/8｜離散 PID 程式碼（float，M33 或主機）】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
I[n] = I[n−1] + Ki·dt·e（積分存已乘 Ki 的值，線上改 Ki 不跳）；D = −Kd·(y[n]−y[n−1])/dt（微分取量測值，避免 setpoint 跳動的 derivative kick）；u = sat(Kp·e + I + D)。
```c
typedef struct {
    float kp, ki_dt, kd_div_dt;      // 預先算好 ki*dt、kd/dt
    float d_alpha;                   // 微分低通係數，0 < d_alpha ≤ 1（1 = 不濾波）
    float out_min, out_max;
    float i, d, y_prev;
    int   first;
} pid_ctrl_t;
float pid_step(pid_ctrl_t *p, float r, float y) {
    if (p->first) { p->y_prev = y; p->first = 0; }
    float e = r - y;
    float d_raw = -p->kd_div_dt * (y - p->y_prev);
    p->d += p->d_alpha * (d_raw - p->d);
    p->y_prev = y;
    float i_new = p->i + p->ki_dt * e;
    float u = p->kp * e + i_new + p->d;
    // anti-windup（條件積分）：飽和且誤差會讓它更飽和時不更新積分
    if (u > p->out_max)      { u = p->out_max; if (e < 0) p->i = i_new; }
    else if (u < p->out_min) { u = p->out_min; if (e > 0) p->i = i_new; }
    else                     { p->i = i_new; }
    return u;
}
```
- 名稱避開 POSIX 的 pid_t。第一次呼叫令 y_prev = y，避免微分突波。
- Hazard3（無 FPU）改整數版：增益 Q16.16、積分 int64；Ki·dt 太小量化成 0 時積分用更多小數位（如 Q24）。

---

【參考卡｜控制DSP 7/8｜PID：anti-windup、增量式、調參、時序】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
anti-windup（飽和期間積分持續累積 → 解除後大超調）三種做法：
(a) 條件積分：輸出飽和且 e 會讓它更飽和時不積分。
(b) 積分項本身夾在 [out_min, out_max]。
(c) back-calculation：`i += ki_dt*e + (dt/Tt)*(u_sat − u_unsat)`，Tt 常取 Ti 或 √(Ti·Td) 量級。
其他元件：微分一階低通（時間常數 Td/N，N ≈ 5–20）；setpoint 斜率限制；bumpless transfer 切換時令 `i = u_current − kp*e − d`。
增量式：Δu = Kp(e−e1) + Ki·dt·e + (Kd/dt)(e − 2e1 + e2)，u = sat(u_prev + Δu)。天然 anti-windup；但 Ki = 0 時輸出偏移會漂移，通常一定要有 I 項。
Ziegler–Nichols（只用 P 加到等幅振盪，得 Ku、Tu）：
| 控制器 | Kp | Ti | Td |
|---|---|---|---|
| P | 0.5Ku | — | — |
| PI | 0.45Ku | Tu/1.2 | — |
| PID | 0.6Ku | Tu/2 | Tu/8 |
Ki = Kp/Ti，Kd = Kp·Td；ZN 超調偏大（約 25%），當起點。手調：先 Kp → 加 Kd 抑制超調 → 加 Ki 消穩態誤差。
時序（經驗）：fs 約閉迴路頻寬 10–30 倍；讀感測器 → 輸出延遲要短且固定；外迴路比內迴路慢 5–10 倍；控制計算最壞時間 < 週期一半。
振盪時查：Kp/Kd 太大、延遲大、dt 與實際週期不符、微分沒濾波、單位錯（deg/rad）。

---

【參考卡｜控制DSP 8/8｜固定週期迴圈、dt、主機測試 kernel】
以下是正確的參考資料，若與你的記憶不同，以這張為準。
平台：RP2350（Pico 2），pico-sdk 2.x。
```c
const uint32_t T_US = 1000;                  // 1 kHz
absolute_time_t next = get_absolute_time();
for (;;) {
    next = delayed_by_us(next, T_US);
    sample_and_control();                    // 必須 < T_US
    sleep_until(next);
}
// 或 add_repeating_timer_us(-1000, on_tick, NULL, &tmr);  負值 = 開始到開始固定週期
// tmr 要 static；callback 在 IRQ context，要短，不可 sleep/printf
```
- 不要 `sleep_ms(10)` 放迴圈尾：週期 = 10 ms + 運算時間，會漂移。
- dt：`uint32_t dt_us = now - last;`（無號減法跨 time_us_32 的 71.6 分鐘溢位）；不要 `if (now > last)`。
- 固定週期就用常數 dt，預算 Ki*dt、Kd/dt；用實測 dt 要設上下限。
- 時間戳打在取樣當下；先讀感測器 → 計算 → 輸出。
- overrun 偵測：迴圈開頭記 `t0 = time_us_32()`，結尾比較預算。
主機測試定點 kernel：只依賴 <stdint.h>，與 double 參考版一起編譯：
`gcc -O2 -Wall -Wextra -fsanitize=undefined,address test_kernel.c kernel.c -lm`
- 測試訊號：全 0（輸出須全 0）、脈衝、步階（看是否卡在目標下方）、通帶/截止/阻帶正弦（截止處約 0.707）、最大最小交替（溢位飽和）、隨機、INT16_MIN/MAX/0/−1。
- 指標：最大絕對誤差與 RMS 誤差（LSB）；位元一致用 diff/cmp。
