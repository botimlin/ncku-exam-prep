# asm_examples.S — 可以從 C 呼叫的 RV32 組合語言函式（大寫 .S = 會先跑 C 前處理器，可用 #ifdef）
# 呼叫慣例：參數 a0,a1,a2...；回傳值放 a0；t0-t6 隨便用；s0-s11 用了要先存後還；ra = 回傳位址
# 編譯：見 README.md（-march=rv32imac_zba_zbb_zbs -mabi=ilp32）
# 標籤 1: 2: 是「區域數字標籤」，1b = 往回(back)找最近的 1:，1f = 往前(forward)找
    .text

# ---- uint32_t asm_sum_u32(const uint32_t *a, uint32_t n) ：陣列總和 ----
    .globl asm_sum_u32
asm_sum_u32:
    li   t0, 0              # t0 = sum
    beqz a1, 2f             # n == 0 直接結束
1:  lw   t1, 0(a0)          # t1 = *a
    add  t0, t0, t1         # sum += t1
    addi a0, a0, 4          # a++（指標 +4 byte，因為 uint32_t 是 4 byte）
    addi a1, a1, -1         # n--
    bnez a1, 1b             # n != 0 → 繼續
2:  mv   a0, t0             # 回傳值放 a0
    ret

# ---- void asm_memcpy_words(uint32_t *dst, const uint32_t *src, uint32_t n) ----
    .globl asm_memcpy_words
asm_memcpy_words:
    beqz a2, 2f
1:  lw   t0, 0(a1)          # 讀 src
    sw   t0, 0(a0)          # 寫 dst
    addi a0, a0, 4
    addi a1, a1, 4
    addi a2, a2, -1
    bnez a2, 1b
2:  ret

# ---- uint32_t asm_get_field(uint32_t x, uint32_t lo, uint32_t w) = (x >> lo) & ((1<<w)-1)，w<32 ----
    .globl asm_get_field
asm_get_field:
    srl  a0, a0, a1         # x >> lo（srl = 邏輯右移，補 0；sra = 算術右移，補符號位）
    li   t0, 1
    sll  t0, t0, a2         # 1 << w
    addi t0, t0, -1         # mask = (1<<w)-1
    and  a0, a0, t0
    ret

# ---- uint32_t asm_popcount_array_base(const uint32_t *a, uint32_t n) ：只用基本指令 ----
    .globl asm_popcount_array_base
asm_popcount_array_base:
    li   t0, 0              # total
    beqz a1, 9f
1:  lw   t1, 0(a0)
2:  beqz t1, 3f             # 內層迴圈：t1 還有 1 就繼續
    addi t2, t1, -1
    and  t1, t1, t2         # t1 &= t1-1 清掉最低的 1
    addi t0, t0, 1
    j    2b
3:  addi a0, a0, 4
    addi a1, a1, -1
    bnez a1, 1b
9:  mv   a0, t0
    ret

# ---- uint32_t asm_popcount_array_fast(...)：有 Zbb 就用 cpop（一條指令數 1） ----
    .globl asm_popcount_array_fast
asm_popcount_array_fast:
#ifdef __riscv_zbb
    li   t0, 0
    beqz a1, 9f
1:  lw   t1, 0(a0)
    cpop t1, t1             # t1 = popcount(t1)（Hazard3 有 Zbb）
    add  t0, t0, t1
    addi a0, a0, 4
    addi a1, a1, -1
    bnez a1, 1b
9:  mv   a0, t0
    ret
#else
    j    asm_popcount_array_base   # 沒有 Zbb：直接跳去基本版（尾呼叫，ra 不變）
#endif

# ---- int32_t asm_bnn_dot(const uint32_t *w, const uint32_t *x, uint32_t n) ----
# 二值神經網路（BNN）：位元 1 代表 +1、0 代表 -1，n 個 word = 32n 個權重
# dot = (相同的個數) - (不同的個數) = 2*popcount(XNOR(w,x)) - 32n
    .globl asm_bnn_dot
asm_bnn_dot:
    li   t0, 0              # t0 = 相同位元總數
    slli t3, a2, 5          # t3 = 32n（等一下要用）
    beqz a2, 9f
1:  lw   t1, 0(a0)
    lw   t2, 0(a1)
#ifdef __riscv_zbb
    xnor t1, t1, t2         # Zbb：一條 xnor
    cpop t1, t1
    add  t0, t0, t1
#else
    xor  t1, t1, t2
    not  t1, t1             # xnor = not(xor)
2:  beqz t1, 3f
    addi t4, t1, -1
    and  t1, t1, t4
    addi t0, t0, 1
    j    2b
3:
#endif
    addi a0, a0, 4
    addi a1, a1, 4
    addi a2, a2, -1
    bnez a2, 1b
9:  slli t0, t0, 1          # 2 * matches
    sub  a0, t0, t3         # - 32n
    ret

# ---- void asm_apply(uint32_t (*f)(uint32_t), uint32_t *a, uint32_t n) ：a[i] = f(a[i]) ----
# 示範「會呼叫別的函式」的寫法：要存 ra 和 s 暫存器，堆疊 16 byte 對齊
    .globl asm_apply
asm_apply:
    addi sp, sp, -16        # 開 16 byte 堆疊（sp 必須保持 16 的倍數）
    sw   ra, 12(sp)         # 呼叫 f 會蓋掉 ra，先存
    sw   s0, 8(sp)          # s0..s2 是 callee-saved：我用了就要負責還原
    sw   s1, 4(sp)
    sw   s2, 0(sp)
    mv   s0, a0             # s0 = f（存在 s 暫存器，呼叫 f 後不會被改）
    mv   s1, a1             # s1 = a
    mv   s2, a2             # s2 = n
    beqz s2, 2f
1:  lw   a0, 0(s1)          # 參數 = a[i]
    jalr ra, 0(s0)          # 呼叫 f（等同 jalr s0）
    sw   a0, 0(s1)          # a[i] = 回傳值
    addi s1, s1, 4
    addi s2, s2, -1
    bnez s2, 1b
2:  lw   s2, 0(sp)          # 還原（順序無所謂，位置要對）
    lw   s1, 4(sp)
    lw   s0, 8(sp)
    lw   ra, 12(sp)
    addi sp, sp, 16
    ret
