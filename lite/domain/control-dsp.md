# 嵌入式控制與 DSP 速查（RP2350）

> 用途：備援包；取樣/定點/濾波/PID/訊號分析與加速
> 適用：RP2350、pico-sdk 2.x、CMSIS-DSP
> 來源：rp2350-datasheet.pdf §3.1.10 §12.4、pico-sdk（hardware_interp/interp.h、adc.h、pico_time）、arm-software.github.io/CMSIS-DSP、w3.org/TR/audio-eq-cookbook
> 最後更新 2026-11（詳見 full/domain/control-dsp.md）

## 平台
- Hazard3 **無 FPU**→用定點；`mul/mulh` 1 cycle、`div` 18–19（⚠️未查證，datasheet 3.8.7）；Zbb `min/max/clz`
- M33：單精度 FPU（別用 double，常數 `1.0f`）；DSP：`SMLAD`（兩個 16×16 乘加，溢位繞回設 Q flag）、`SSAT`、`SMMUL`；`<arm_acle.h>` `__smlad(a,b,acc)`
- 兩核都無 64-bit 除法指令（軟體：Arm `__aeabi_ldivmod`、RISC-V `__divdi3`，慢）
- 要和 judge 逐位元一致→定點+固定捨入（float 有 FMA/平台差）

## 取樣
- fs>2f_max；高於 fs/2 會混疊，取樣後無法濾除
- ADC 12-bit，500 kS/s，48 MHz/96 cycle；`adc_set_clkdiv(d)`：每 (1+d) cycle（10 kHz→4799）；FIFO 8；round robin 速率均分
- 固定週期：`next=delayed_by_us(next,T); sleep_until(next);` 或 `add_repeating_timer_us(-T,...)`（負=固定週期）；勿 `sleep_ms` 迴圈
- dt：`uint32_t d = now - last;`（無號減法跨溢位）；時間戳打在取樣當下
- ADC API：`adc_init; adc_gpio_init(26); adc_select_input(0); adc_fifo_setup(en,dreq_en,thresh,err,byte_shift); adc_run(true)`

## 定點
- 值=raw/2^FRAC；Q15 int16 [−1,1)；Q31；Q16.16 int32 ±32768；biquad 係數需 ±2（Q2.30）
- 乘：`(int32_t)(((int64_t)a*b + (1<<15)) >> 16)`；**不是** `(int64_t)(a*b)`
- Q15×Q15：`sat16((a*b + (1<<14)) >> 15)`；−1×−1 要飽和
- 捨入：`>>` 往 −∞、`/` 往 0；加半 LSB 再移
- 除變數→倒數：`m=ceil(2^32/d)`, `q=(x*m)>>32`（x·d≤2^32 精確）
- 位元增長：乘 n+m；N 項和 +log2N；|y|≤max|x|·Σ|h|
- 有號溢位、負數左移=UB→int64/無號/乘法
- sin：256 段表+線性內插（Q15 誤差≤3.7 LSB）；binary angle（uint16/uint32 一圈）
- CORDIC 24 次：sin/cos 誤差~1e-7；atan2、長度
- isqrt：bit-by-bit 16 迴圈；Q16 sqrt=`isqrt64((uint64_t)a<<16)`；log2=31−clz
- `fix2float/float2fix` 只在 Arm 版 pico_float；Hazard3 執行期 float 轉換只在初始化做

## 濾波
- MA：`sum+=x-buf[i]; buf[i]=x; i=(i+1)&(N-1); y=sum>>k`
- EMA：`acc+=x-(acc>>k); y=acc>>k`（τ≈2^k 樣本）；`y+=(x-y)>>k` 會卡在目標下方
- Biquad（RBJ）：w0=2πf0/fs, α=sin w0/(2Q)；LPF b0=b2=(1−cos)/2, b1=1−cos, a0=1+α, a1=−2cos, a2=1−α，全除 a0；`y=b0x+b1x1+b2x2−a1y1−a2y2`
- 定點用 DF1+int64；**y 狀態留額外小數位**（f0/fs=0.01 實測：整數 y 誤差 111 LSB→0.5）；float 用 DF2T
- CMSIS biquad：a1,a2 **取負**；q15 係數 `{b0,0,b1,b2,a1,a2}`+postShift
- FIR 雙倍緩衝 `buf[p]=buf[p+N]=x` 免取模；對稱係數乘法減半
- median3：min/max 無分支；突波先 median 再 EMA
- 互補：`θ=a(θ+ω·dt)+(1−a)θ_acc`，a=τ/(τ+dt)
- Kalman 1D：P+=Q; K=P/(P+R); x+=K(z−x); P*=(1−K)；穩態=EMA

## PID
- 預算 `ki*dt`、`kd/dt`；積分存已乘 Ki 值
- D 取量測 `−Kd·Δy/dt`+低通；首呼叫 y_prev=y
- anti-windup：飽和且 e 同向時不積分／積分夾範圍／back-calc
- 增量式 Δu 天然 anti-windup
- 骨架：`e=r-y; d+=a*(-kd_dt*(y-yp)-d); yp=y; in=i+ki_dt*e; u=kp*e+in+d;` 飽和→夾 u，僅在 e 使 u 回到範圍時 `i=in`
- ZN（Ku,Tu）：PID Kp=.6Ku Ti=Tu/2 Td=Tu/8；PI .45Ku Tu/1.2
- 遲滯開關防抖；rate limit；前饋
- fs≈閉迴路頻寬 10–30×（經驗）；延遲固定

## 分析
- FFT：(N/2)log2N butterfly；bin=fs/N；Hann 防洩漏
- Goertzel：`s=x+c·s1−s2`, c=2cos(2πk/N)；P=s1²+s2²−c·s1·s2
- 零交越加遲滯、先去 DC；峰值：先平滑+門檻+最小間距
- RMS：int64 Σx² + isqrt；float 變異用 Welford

## interp（每核 2 個，SIO）
- lane=mask(**rotate right**(ACCUM,SHIFT))(+sign)；RES0/1=BASE+lane（ADD_RAW 用原值）；FULL=BASE2+lane0+lane1；POP 寫回累加器；右旋 s 時 MASK_MSB≤31−s
- blend 只 interp0（8-bit α）；clamp 只 interp1 lane0
- API：`interp_default_config`、`interp_config_set_{shift,mask,signed,add_raw,cross_input,cross_result,blend,clamp}`、`interp_set_config`、`interp0->accum/base/peek/pop/add_raw[]`；ISR 用 `interp_save/restore`；link `hardware_interp`
- NCO 查表：add_raw+shift23+mask1..8，base0=step, base2=tab，`*(int16_t*)interp0->pop[2]`
- E1：OVERF 不可靠

## 陷阱
- Arm/RISC-V `char` 無號、x86 有號；`long` 32 vs 64
- float 2^24+1 失精度；時間用整數 µs
- 濾波狀態用第一筆初始化
- 抓隱性浮點/64 位除法：objdump 找 RV `__mulsf3/__adddf3/__divdi3`、Arm `__aeabi_dadd/__aeabi_ldivmod`；`-Wdouble-promotion`
- 測試：主機 double 參考比對 max/RMS 誤差（LSB），脈衝/步階/正弦/邊界；`-fsanitize=undefined`
- ADC+DMA ping-pong（DREQ_ADC, 16-bit, chain）→core1 處理；表放 RAM
