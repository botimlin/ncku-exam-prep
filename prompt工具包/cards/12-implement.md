# 貼上卡：實作（照規格寫 / 改程式：位元欄位、封包、PIO、DMA、雙核、RISC-V、ROS 2）
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容送出。每張 ≤ 1200 字元，每張都能在新對話直接用。卡上寫「先貼 xx.md」的，同一個對話先貼那張參考卡，模型回「收到」再貼提示卡（小模型沒有硬體知識，參考卡就是它的知識）。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。能用程式算的（bit 欄位、struct 大小、機器碼解碼）都交給程式，模型只抄結果、照樣板填。判斷規則直接寫在表格的列裡（壓力測試：規則放在列裡比放在「規則」段落準）。標題後的 `→` 是下一張。
> 流程：實作 1、2（位元 / 封包）、3 → 4（PIO）、5（DMA）、6（雙核）、7、8（RISC-V）、9（ROS 2）→ 編譯測試 → `09-template-adapt.md` 範本 7（檢查）。
> 機器碼解碼（實作 8 用，印 2 行：欄位、格式 + 指令名 + imm；已和 GNU as 2.42 對過 RV32I/M，Zba/Zbb 等擴充印「?」）：`python3 -c "x=0xX;f=lambda h,l:x>>l&(1<<h-l+1)-1;s=lambda v,n:v-(v>>n-1<<n);o,a,r,b=f(6,0),f(14,12),f(24,20),f(31,25);F={51:'R',19:'I',3:'I',103:'I',35:'S',99:'B',111:'J',55:'U',23:'U'}.get(o,'?');T={51:'add sll slt sltu xor srl or and',19:'addi slli slti sltiu xori srli ori andi',3:'lb lh lw ? lbu lhu',35:'sb sh sw',99:'beq bne ? ? blt bge bltu bgeu',103:'jalr'};N=(T.get(o,'?').split()+['?']*8)[a*(o!=103)];N={111:'jal',55:'lui',23:'auipc'}.get(o,N);k=o==19 and a in(1,5);N=(N if b==0 else{'add':'sub','srl':'sra'}.get(N,'?')if b==32 else'mul mulh mulhsu mulhu div divu rem remu'.split()[a]if b==1 else'?')if o==51 else('srai'if b==32 and a==5 else N if b==0 else'?')if k else N;m={'I':r if k else s(f(31,20),12),'S':s(b<<5|f(11,7),12),'B':s(f(31,31)<<12|f(7,7)<<11|f(30,25)<<5|f(11,8)<<1,13),'J':s(f(31,31)<<20|f(19,12)<<12|f(20,20)<<11|f(30,21)<<1,21),'U':hex(f(31,12)),'R':'無'}.get(F,'?');print('op',hex(o),'rd',f(11,7),'f3',a,'rs1',f(19,15),'rs2',r,'f7',hex(b));print('格式',F,'指令',N,'imm',m)"`
> PIO 檢查（實作 3、4 用；讀 pioasm 產生的 .pio.h，印每行 cycle、迴圈每圈 cycle、autopull / autopush、in 讀值要移幾位、clkdiv；已和 pioasm 2.2.0 輸出對過；wait 的等待時間不算）：`python3 -c "import re,sys;A=sys.argv[1:];t=open(A[0]).read();L=[(int(i),' '.join(s.split())) for i,s in re.findall(r'//\s*(\d+): ([^\n]+)',t)];D=lambda s:int((re.findall(r'\[(\d+)\]',s)or[0])[0]);O=[s.split()[0] for i,s in L];h=lambda o:o in O;N=lambda s:int(s.split(',')[1].split()[0]);[print('行',i,s,'→ cycle 1+%d=%d'%(D(s),1+D(s))+'（+ 等待）'*O[i].startswith('wait')) for i,s in L];J=[(int(s.split(',')[1].split()[0]),i,s.split()[1].rstrip(',')) for i,s in L if s.startswith('jmp') and ',' in s and int(s.split(',')[1].split()[0])<=i];a,b,r=J[0] if J else(L[0][0],L[-1][0],'');S=[1+D(s) for i,s in L if a<=i<=b];K=[int(s.split(',')[1].split()[0])+1 for i,s in L if i<a and s.startswith('set '+r[:1]+',')] if r[1:]=='--' else[];k=K[-1] if K else 1;print('迴圈：行 %d–%d'%(a,b)+(' 跑 %d 次'%k if J else '（沒有 jmp 迴圈，算 wrap 一圈）')+'，每圈 cycle = '+' + '.join(map(str,S))+' = %d'%sum(S));print('autopull：'+('關（有 pull）' if h('pull') else '開（有 out 沒 pull），門檻 = CPU 每次 put 的 bit 數（put 整個 word = 32）' if h('out') else '關（沒有 out）'));print('autopush：'+('關（有 push）' if h('push') else '開（有 in 沒 push）' if h('in') else '關（沒有 in）'));n=sum(N(s)*(k if a<=i<=b and J else 1) for i,s in L if s.startswith('in '));h('push') and print('每次 push 收 %d bit → in 右移時讀值 >> %d；左移時讀值 & 0x%X'%(n,32-n,(1<<n)-1));len(A)>2 and print('clkdiv = %g ÷ (%g × %d) = %.2f'%(float(A[1]),float(A[2]),sum(S),float(A[1])/float(A[2])/sum(S)))" build/名稱.pio.h 150e6 速率`（150e6 = clk_sys；速率 = 每圈的速率：UART 填 baud、每圈送 1 byte 填 byte 速率）
> 範本：`../預製程式碼/bits-riscv/`（bitops.h、packet_fields.c、bitstream.c）、`pico/`（app_dma.c、app_pio.c、pio/*.pio、app_multicore.c）、`ros2/node_template.py`。
> 來源：上列範本原始碼、pioasm 2.2.0（`.pio.h` 指令清單格式、delay 上限）、GNU as 2.42 rv32im（機器碼對照）、pico-sdk 2.2.0 `hardware/dma.h`、`cards/pio.md`、`pico-dma.md`、`multicore-sync.md`、`riscv-hazard3.md`、`ros2.md`｜最後更新 2026-11

---

【提示卡｜實作 1/9｜規格位元表 → C 欄位程式】
Task (EN): Copy every field of the bit table into the output table, show the width and mask arithmetic, then fill the C templates with bitops.h GET_FIELD / SET_FIELD / sign_extend. Answer in Traditional Chinese.
任務：把規格的位元表寫成程式。`#include "bitops.h"`（`bits-riscv/`），不要自己 #define。
<<<資料 開始>>>
[位元表原文]
{{貼}}
[資料來源] {{uint32_t 暫存器 / uint8_t 陣列（大端或小端）}}
[規格的範例值]（沒有寫「無」）{{…}}
<<<資料 結束>>>
規則：
1. 每個欄位一列，名稱、hi、lo 照抄規格（hi 是比較大的數）。寬度寫「hi − lo + 1 = 答案」，mask 寫「(1u << 寬度) − 1 = 0x…」。
2. 規格寫 signed、二補數、有號、可為負的欄位才是有號。
3. 程式每個欄位一行，照樣板（x = 組好的 32-bit）：無號 `uint32_t 名 = GET_FIELD(x, hi, lo);`　有號 `int32_t 名 = sign_extend(GET_FIELD(x, hi, lo), 寬度);`　寫入 `y = SET_FIELD(y, hi, lo, 值);`（結果一定要接回 y）
4. 自我檢查每個欄位一行：`GET_FIELD(SET_FIELD(0u, hi, lo, 值), hi, lo) == 值`；有號欄位用 `sign_extend(GET_FIELD(SET_FIELD(0u, hi, lo, (uint32_t)-3), hi, lo), 寬度) == -3`；有範例值也比對。
填法：「組 32-bit」只寫「直接用」、「load_be32(p)」或「load_le32(p)」（大端用 be，從 packet_fields.c 複製）；「有號欄位」只寫欄位名或「無」。
只輸出（欄位名照抄）：
| 欄位 | hi | lo | 寬度 | mask | 有號 |
組 32-bit：
有號欄位：
程式（≤ 12 行）：
自我檢查（≤ 6 行，最後 puts(ok ? "PASS" : "FAIL")）：
範例（只示範格式，內容不要照抄）：
| speed | 13 | 4 | 13 − 4 + 1 = 10 | (1u << 10) − 1 = 0x3FF | 否 |

---

【提示卡｜實作 2/9｜封包 / 位元流規格 → 解析程式】
Task (EN): Fill the offset table from the spec (offset = previous offset + previous size, show it), pick the endianness and ONE parse method, then fill that method's code template. Answer in Traditional Chinese.
任務：依封包規格算出每個欄位的位置，寫解析程式。
<<<資料 開始>>>
[封包規格原文]（欄位順序、大小、大小端）
{{貼}}
[語言] {{Python / C}}
<<<資料 結束>>>
解析方式：A struct（欄位都是整 byte，Python）　B read_msb（有欄位不是整 byte，高位先、MSB-first、bit7 先；bitstream.c）　C read_lsb（有欄位不是整 byte，低位先、LSB-first、bit0 先；bitstream.c）　D load_be16 / load_be32 / load_le32（整 byte，C；packet_fields.c；2 byte 小端沒有函式 → (uint16_t)(p[o] | p[o+1] << 8)）
規則：
1. 每個欄位一列，順序照規格；offset 寫「上一列 offset + 上一列大小 = 答案」，第一列 0（B、C 用 bit）；payload[len] 之後寫「數字 + len」。
2. struct 字元只能填：1 byte B（有號 b）、2 byte H（h）、4 byte I（i）、8 byte Q（q）；解析方式選 B、C、D 時填「不用」。
3. 格式字串 = `>` 或 `<`，後面接 struct 字元欄由上往下抄（payload 前停）。
程式樣板：A `a, b, … = struct.unpack_from('格式字串', buf, 0)`｜B、C `BitStream s = { buf, 0 };` 每個欄位一行 `uint32_t 名 = read_msb(&s, 大小);`｜D `uint32_t 名 = load_be32(p + offset);`（不要把指標強轉成 uint32_t *）
填法：「大小端」只寫「大端 >」或「小端 <」。
只輸出：
大小端：
解析方式（照抄選項的字母和文字）：
| 欄位 | offset | 大小 | 有號 | struct 字元 |
固定部分總長（payload 前最後一列的 offset + 大小，寫算式）：
格式字串（解析方式 B、C、D 寫「不用」）：
程式（≤ 10 行）：

---

【提示卡｜實作 3/9｜PIO 程式逐行解讀 + C 端要的設定】→ 實作 4
Task (EN): A script already computed the cycles, autopull/autopush, the read shift and clkdiv. Copy its lines into the tables, take the shift direction from the spec, then compare each row with the C init. Answer in Traditional Chinese.
任務：逐行解讀 PIO 程式，推出 C 端設定。（前面已貼 `pio.md` PIO 2/8、3/8）
取得：建置後跑本檔開頭「PIO 檢查」那行 python3（換成你的 .pio.h、clk_sys、速率）。
<<<資料 開始>>>
[程式印出的幾行]
{{貼}}
[C 端 init，帶行號]（沒有寫「無」）
{{貼}}
[規格要求]（速率、位元順序、腳位；沒有寫「無」）{{…}}
<<<資料 結束>>>
規則：程式印的數字直接抄，不要自己重算；「C 端現在」照抄那一行和行號。
只輸出：
| 行 | 指令 | 做什麼（根據參考卡） | cycle（抄程式） |
| 設定（照列裡的方法填） | 要的值 | C 端現在（沒給寫「沒寫」） | OK/NG |
| 1 autopull：抄程式「autopull：」那行 | | | |
| 2 out shift：規格 LSB 先→右移；MSB 先→左移；沒 out→不用 | | | |
| 3 autopush：抄程式「autopush：」那行 | | | |
| 4 in shift：LSB 先→右移，抄「右移時讀值」；MSB 先→左移；沒 in→不用 | | | |
| 5 腳位：out base、count；sideset base；in base（寫 GP 號） | | | |
| 6 cycle：抄程式「每圈 cycle」和「clkdiv」 | | | |
C 端要改的地方（每個 NG 列一行：第幾行 → 改成什麼；沒有寫「無」）：

---

【提示卡｜實作 4/9｜PIO 程式最小修改 + C init】→ 範本 7
Task (EN): Using the pio.md cards pasted earlier, pick the change type(s), write the numbers of the places that type lists, output one patch per number only, then fill the checklist. Answer in Traditional Chinese.
任務：照規格最小修改 PIO 程式，C 端一起改。（前面已貼 `pio.md` PIO 1/8、3/8）
<<<資料 開始>>>
[要改成什麼] {{例如 一次送 2 bit、CPU 每次 put 1 個 byte、baud 改 9600}}
[.pio 原文，帶行號]（第一行寫檔名；`cat -n x.pio`）
{{貼}}
[C 端 init，帶行號]（第一行寫檔名；呼叫 put 的那行也貼）
{{貼}}
<<<資料 結束>>>
類型（可多選，→ 後面是要改的地方）：
A 只改速度 → ① baud 或 clkdiv 那 1 行（.pio 不動）
B CPU 每次 put 的 bit 數變了 → ② set_out_shift 門檻改成那個數；③ 左移時呼叫端 put(v) 改成 put((uint32_t)v << 數字)，數字 = 32 − 門檻
C 每次送幾 bit / 用幾支腳變了 → ④ .pio 的 `out pins, n`；⑤ set_out_pins 的 count；⑥ mask 加 `| (1u << (data_pin + 1))`；⑦ pio_gpio_init(pio, data_pin) 保留，後面加 `pio_gpio_init(pio, data_pin + 1);`
D 時序變了 → ⑧ 改 [n] 或加 nop；[n] ≤ 上限（3/8 的表）
規則：只改選到的編號；修改後 = 原本那行，只換數字或在後面加東西。
只輸出：
類型（照抄字母和文字）：
要改的編號：
（每個編號一組 3 行，檔名照資料第一行）
檔名:行號
修改前：
修改後：
| 檢查 | OK / 有問題 | 依據 |
| 1 非 opt side_set 每行有 side；delay ≤ 上限 | | |
| 2 out 每次 bit 數 × 次數 = 門檻 | | |
| 3 shift 方向和資料放的位置一致 | | |
| 4 新用到的腳有 set_*_pins、pio_gpio_init、pindirs | | |

---

【提示卡｜實作 5/9｜DMA 設定：需求表 → pico-sdk 呼叫】→ 範本 7
Task (EN): Using the pico-dma.md cards pasted earlier, fill the table, then the code template. Answer in Traditional Chinese.
任務：依規格填 DMA 設定表，再填程式樣板（前面已貼 DMA 2/8，PIO 另加 4/8）。
<<<資料 開始>>>
[規格] {{…}}
[現在的程式，帶行號]（沒有寫「無」）
{{貼}}
<<<資料 結束>>>
填法：「現在程式」照抄那一行；沒寫就填「沒寫（預設 …）」。
只輸出：
| 項目 | 規格要的 | 現在程式 | OK/NG |
| 1 read_addr（從哪讀） | | | |
| 2 write_addr（寫到哪） | | | |
| 3 每筆大小 DMA_SIZE_8/16/32 | | | |
| 4 筆數 = 總 bytes ÷ 每筆 bytes（算式 = 數字；只寫 sizeof(陣列) 沒除以每筆大小 → NG） | | | |
| 5 read_increment：讀陣列 true、讀 FIFO false | | | |
| 6 write_increment：寫陣列 true、寫 FIFO false | | | |
| 7 DREQ：記憶體↔記憶體 DREQ_FORCE；送進 PIO 用 pio_get_dreq(pio, sm, true) | | | |
| 8 有 wait_for_finish_blocking | | | |
| 9 有 dma_channel_unclaim | | | |
程式（<n> 換成第 n 列「規格要的」的數字）：
int ch = dma_claim_unused_channel(true);
dma_channel_config c = dma_channel_get_default_config(ch);
channel_config_set_transfer_data_size(&c, <3>);
channel_config_set_read_increment(&c, <5>);
channel_config_set_write_increment(&c, <6>);
channel_config_set_dreq(&c, <7>);
dma_channel_configure(ch, &c, <2>, <1>, dma_encode_transfer_count(<4>), true);
dma_channel_wait_for_finish_blocking(ch);
dma_channel_unclaim(ch);

---

【提示卡｜實作 6/9｜雙核分工：共享變數表 → 保護方式】→ 範本 7
Task (EN): Using the multicore-sync.md cards pasted earlier, list every global variable, pick ONE protection A–F for each (first rule that matches, top to bottom), then output a minimal patch; for B fill the B template. Answer in Traditional Chinese.
任務：找出兩核都會碰的變數，選保護方式，給最小修改。（前面已貼 `multicore-sync.md` 多核同步 4/8、5/8）範本：`pico/app_multicore.c`。
<<<資料 開始>>>
[規格：core0、core1 各做什麼] {{…}}
[程式，帶行號]（第一行寫檔名；兩核會跑到的函式與全域變數）
{{貼}}
<<<資料 結束>>>
保護方式（由 A 往下，第一個符合的就選）：
A 不用保護：launch 前寫好，之後兩核只讀
B 區域變數：在 for 迴圈裡累加的共享變數 → 迴圈內加到 local，迴圈結束後上鎖加一次 g += local
C atomic：兩核都會 +1 的單一 32-bit 計數
D queue_t：一核寫、另一核讀的資料（編號、結果、工作）
E multicore_fifo：只傳 1 個 32-bit 通知
F spin lock：其他兩核都會寫的資料（鎖內只放讀寫那幾行）
規則：每個 static 全域變數一列；計算、printf、sleep 放鎖外；名稱照原樣。
只輸出：
| 變數 | 誰寫 | 誰讀 | 保護（照抄字母和文字） |
鎖內的行（選 B 寫 g += local 那一行；F 寫鎖裡的行；沒有鎖寫「無」）：
檔名:第一行-最後一行
修改前：（選 B：從 lock 那行抄到 unlock 那行）
修改後：（選 B：照下面樣板，g、v、lk 換成程式裡的名稱）
    uint32_t local = 0;
    for (原本的迴圈頭) {
        原本的計算;
        local += v;      // 原本是 g += v;
    }
    uint32_t save = spin_lock_blocking(lk);
    g += local;
    spin_unlock(lk, save);
驗證：跑 2 次結果相同，且等於單核版

---

【提示卡｜實作 7/9｜RISC-V 組語逐行解讀】→ 看到機器碼用實作 8
Task (EN): Using the riscv-hazard3.md cards pasted earlier, explain each line, write each forward branch's condition reversed, find the loop, then write the equivalent C using the reversed conditions. Answer in Traditional Chinese.
任務：逐行解讀 RV32 組語，寫出等價的 C。（前面已貼 `riscv-hazard3.md` RISC-V 1/8、2/8）
<<<資料 開始>>>
[組語，帶行號]（`cat -n f.S`，或 .dis 的一段）
{{貼}}
[參數意思]（a0、a1… 是什麼；沒有寫「無」）{{…}}
<<<資料 結束>>>
規則：
1. 每條指令一列（label、. 開頭的 directive 不算）；pseudo 照參考卡展開（bnez a1,L = bne a1,x0,L）；表格裡暫存器名照原樣。
2. blt/bge 有號、bltu/bgeu 無號；srai 補符號位、srli 補 0；lb 有號、lbu 無號。
3. 反過來：>= 變 <、< 變 >=、== 變 !=、!= 變 ==，左右兩邊不換位置（bge a5, a4 → a5 < a4）。
只輸出：
| 行 | 指令 | 運算（C 寫法） | 結果寫到 |
被跳過的行（每個往後跳的分支一行，label 後面是 f：第幾行的分支、跳過第幾～幾行、if (條件反過來)；沒有寫「無」）：
迴圈跑幾次（往前跳、label 後面是 b 的分支 = 迴圈；次數 = 每圈減 1 的暫存器的初值，寫參數名；沒有寫「無」）：
等價的 C（≤ 6 行；被跳過的行放進 if (反過來的條件)，暫存器換成參數名）：
可疑處（參數是有號 int 卻用 bltu、bgeu、srli、lbu → 可疑；第幾行、為什麼、改成什麼；沒有寫「無」）：
範例（只示範格式，內容不要照抄）：
| 8 | bltu t2, t3, 4b | if ((uint32_t)t2 < (uint32_t)t3) goto 4 | 跳到 label 4 |
被跳過的行：第 5 行 bge a5, a4, 6f 跳過第 6 行 → if (a5 < a4)

---

【提示卡｜實作 8/9｜RISC-V 機器碼 → 組語（程式解碼）】
Task (EN): A script already decoded the format, mnemonic and immediate. Copy them, then write the assembly using the operand order for that format. Do not decode bits yourself. Answer in Traditional Chinese.
任務：機器碼翻回組語。格式、指令名、imm 都由程式算，你只抄，再照格式排運算元。
取得：本檔開頭「機器碼解碼」那行 python3 指令（X 換成機器碼），印出 2 行。
<<<資料 開始>>>
[機器碼] {{0x…}}
[程式印出的 2 行]
{{貼}}
<<<資料 結束>>>
運算元順序（xN 的 N = 第 1 行 rd、rs1、rs2 後面的數）：
R：指令 x[rd], x[rs1], x[rs2]
I：指令 x[rd], x[rs1], imm　（lb lh lw lbu lhu jalr：指令 x[rd], imm(x[rs1])）
S：指令 x[rs2], imm(x[rs1])
B：指令 x[rs1], x[rs2], imm
J：jal x[rd], imm　U：指令 x[rd], imm
規則：格式、指令、imm 只抄第 2 行，不要自己改；指令印「?」就寫「?」，改用下面驗證那行看。
只輸出：
格式：
指令：
rd / rs1 / rs2：
imm：
組語：
範例（只示範格式，內容不要照抄）：
格式：I
指令：lw
rd / rs1 / rs2：x5 / x10 / 不用
imm：-4
組語：lw x5, -4(x10)
驗證：echo ".insn 0xX" | riscv64-unknown-elf-as -march=rv32im -o t.o - && riscv64-unknown-elf-objdump -dM no-aliases,numeric t.o（分支、jal 印的是目標位址，從 0 算：ffffffec = −20）

---

【提示卡｜實作 9/9｜從規格改 ROS 2 node（node_template.py）】→ 範本 7
Task (EN): Fill the interface table, then fill the edit table for node_template.py (new code, or 不改). Subscription QoS must match the publisher. Answer in Traditional Chinese.
任務：照規格改 `ros2/node_template.py`。（前面已貼 `ros2.md` ROS 2 3/8 QoS）
<<<資料 開始>>>
[規格原文]（node 名、topic、型別、QoS、參數、運算）
{{貼}}
<<<資料 結束>>>
規則：
1. 型別 std_msgs/msg/X → import X；pub、sub、out = X() 各用自己的型別。
2. 對方 publisher 是 BEST_EFFORT（sensor_data）→ sub 用 qos_profile_sensor_data（17 行 import）；其他照原本 QOS。
3. 參數名照規格，預設值型別照規格（0.5 不能寫成 0 或 1）。
只輸出：
| topic | 方向 pub/sub | 型別 | QoS |
node 名稱：
| 行 | 原本 | 改成（不用改寫「不改」） |
| 17 | from rclpy.qos import …, ReliabilityPolicy | |
| 18 | from std_msgs.msg import Int32 | |
| 33 | super().__init__("processor") | |
| 36 | declare_parameter("in_topic", "/number") | |
| 37 | declare_parameter("out_topic", "/double") | |
| 38 | declare_parameter("factor", 2) | |
| 42 | get_parameter("factor") | |
| 45 | create_publisher(Int32, out_topic, QOS) | |
| 46 | create_subscription(Int32, in_topic, self.on_msg, QOS) | |
| 59 | out = Int32() | |
| 60 | out.data = msg.data * self.factor | |
驗證：ros2 topic info -v 看兩端 QoS，再 ros2 topic pub --once 測一筆
