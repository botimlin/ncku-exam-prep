# 貼上卡：實作（照規格寫 / 改程式：位元欄位、封包、PIO、DMA、雙核、RISC-V、ROS 2）
> 用法：一次只複製一張卡（兩條分隔線之間），把 `{{...}}` 換成你的內容送出。每張 ≤ 1200 字元，每張都能在新對話直接用。卡上寫「先貼 xx.md」的，同一個對話先貼那張參考卡，模型回「收到」再貼提示卡（小模型沒有硬體知識，參考卡就是它的知識）。
> 寫法：第一行 `Task (EN)` 是英文任務句；資料放在 `<<<資料 開始>>>` 和 `<<<資料 結束>>>` 之間；輸出格式放在資料後面。能用程式算的（bit 欄位、struct 大小、機器碼拆欄位）都交給程式，模型只抄結果、查表。標題後的 `→` 是下一張。
> 流程：實作 1、2（位元 / 封包）、3 → 4（PIO）、5（DMA）、6（雙核）、7、8（RISC-V）、9（ROS 2）→ 編譯測試 → `09-template-adapt.md` 範本 7（檢查）。
> 機器碼拆欄位（實作 8 用，已和 GNU as 2.42 對過）：`python3 -c "x=0xX;f=lambda h,l:x>>l&(1<<h-l+1)-1;s=lambda v,n:v-(v>>n-1<<n);print('op',hex(f(6,0)),'rd',f(11,7),'f3',f(14,12),'rs1',f(19,15),'rs2',f(24,20),'f7',hex(f(31,25)));print('I',s(f(31,20),12),'S',s(f(31,25)<<5|f(11,7),12),'B',s(f(31,31)<<12|f(7,7)<<11|f(30,25)<<5|f(11,8)<<1,13),'J',s(f(31,31)<<20|f(19,12)<<12|f(20,20)<<11|f(30,21)<<1,21),'U',hex(f(31,12)))"`
> 範本：`../預製程式碼/bits-riscv/`（bitops.h、packet_fields.c、bitstream.c）、`pico/`（app_dma.c、app_pio.c、pio/*.pio、app_multicore.c）、`ros2/node_template.py`。
> 來源：上列範本原始碼、pioasm 2.2.0（`.pio.h` 指令清單格式、delay 上限）、GNU as 2.42 rv32i（機器碼對照）、`cards/pio.md`、`pico-dma.md`、`multicore-sync.md`、`riscv-hazard3.md`、`ros2.md`｜最後更新 2026-11

---

【提示卡｜實作 1/9｜規格位元表 → C 欄位程式】
Task (EN): Copy every field of the bit table into the output table, show the width and mask arithmetic, then write C with bitops.h GET_FIELD / SET_FIELD / sign_extend and a round-trip self-check. Answer in Traditional Chinese.
任務：把規格的位元表寫成程式。範本 `bits-riscv/bitops.h`：GET_FIELD(x,hi,lo)、SET_FIELD(x,hi,lo,v)、sign_extend(v,寬度)。
<<<資料 開始>>>
[位元表原文]
{{貼}}
[資料來源] {{uint32_t 暫存器 / uint8_t 陣列（大端或小端）}}
[規格的範例值]（沒有寫「無」）{{…}}
<<<資料 結束>>>
規則：
1. 每個欄位一列，名稱、hi、lo 照抄規格。寬度寫「hi − lo + 1 = 答案」，mask 寫「(1u << 寬度) − 1 = 0x…」。
2. 規格寫 signed、二補數、有號、可為負的欄位才是有號；取出後一定包 sign_extend(值, 寬度)。
3. 不要自己寫 >> 和 &，全部用 GET_FIELD / SET_FIELD。
4. 自我檢查：每個欄位 SET_FIELD 放一個值，GET_FIELD 取回要相等；有號欄位用負數測；有範例值就也測範例。
填法：「組 32-bit」只寫「直接用」、「load_be32(p)」或「load_le32(p)」（大端用 be，在 packet_fields.c）；「有號欄位」只寫欄位名或「無」。
只輸出（欄位名照抄）：
| 欄位 | hi | lo | 寬度 | mask | 有號 |
組 32-bit：
有號欄位：
程式（≤ 12 行）：
自我檢查（≤ 4 行）：
驗證：gcc -Wall -I bits-riscv t.c -o t && ./t，印出 PASS
範例（只示範格式，內容不要照抄）：
| speed | 13 | 4 | 13 − 4 + 1 = 10 | (1u << 10) − 1 = 0x3FF | 否 |

---

【提示卡｜實作 2/9｜封包 / 位元流規格 → 解析程式】
Task (EN): Fill the offset table from the byte-level spec (offset = previous offset + previous size, show it), pick the endianness and ONE parse method, then write the parser. Answer in Traditional Chinese.
任務：依封包規格算出每個欄位的位置，寫解析程式。
<<<資料 開始>>>
[封包規格原文]（欄位順序、大小、大小端）
{{貼}}
[語言] {{Python / C}}
<<<資料 結束>>>
解析方式：A struct（欄位都是整 byte，Python）　B read_msb（欄位不是整 byte，高位先；bitstream.c）　C read_lsb（欄位不是整 byte，低位先；bitstream.c）　D load_be16 / load_be32 / load_le32（整 byte，C；packet_fields.c）
規則：
1. 每個欄位一列，順序照規格；offset 寫「上一列 offset + 上一列大小 = 答案」，第一列是 0（B、C 用 bit 當單位）。
2. 長度可變的欄位（payload[len]）後面的 offset 寫成「數字 + len」。
3. struct 字元：B/b = u8/i8、H/h = u16/i16、I/i = u32/i32、Q = u64；有號用小寫。格式字串第一個字一定是 `>` 或 `<`（不寫會自動補 padding），只包含 payload 前的固定欄位。
4. C 不要把 byte 指標強轉成 uint32_t *（不對齊會 trap），用 D 的函式。
填法：「大小端」只寫「大端 >」或「小端 <」。
只輸出：
大小端：
解析方式（照抄選項的字母和文字）：
| 欄位 | offset | 大小 | 有號 | struct 字元 |
固定部分總長：
格式字串：
程式（≤ 10 行）：
驗證：python3 -c "import struct;print(struct.calcsize('格式字串'))" 要等於固定部分總長

---

【提示卡｜實作 3/9｜PIO 程式逐行解讀 + C 端要的設定】→ 實作 4
Task (EN): Using ONLY the pio.md reference cards pasted earlier, explain every PIO instruction in the first table, then fill the 6-row C-config table. Answer in Traditional Chinese.
任務：逐行解讀 PIO 程式，推出 C 端要怎麼設定。先貼 `pio.md` 的 PIO 2/8、3/8，模型回「收到」再貼這張。
<<<資料 開始>>>
[指令清單]（建置後 `sed -n '/instructions\[\]/,/};/p' build/名稱.pio.h`；沒建置就貼 .pio 原文）
{{貼}}
[C 端 init]（沒有寫「無」）
{{貼}}
[規格要求]（速率、位元順序、腳位；沒有寫「無」）{{…}}
<<<資料 結束>>>
規則：
1. 每條指令一列（.wrap_target、.wrap、label 不算），行號用清單的 0、1、2…；意思只根據參考卡。
2. 每條 cycle = 1 + delay；jmp x-- 迴圈跑 X 初值 + 1 次。
3. 有 pull 指令 → autopull 關；只有 out 沒有 pull → autopull 開。push / autopush 同理。
只輸出：
| 行 | 指令 | 做什麼 | 動到（X/Y/ISR/OSR/pins/FIFO） | side / delay |
| 設定 | 要的值 | 依據（哪一行） |
| 1 autopull（開/關、門檻） | | |
| 2 out shift（右移 = LSB 先 / 左移） | | |
| 3 autopush（開/關、門檻） | | |
| 4 in shift（右移又沒收滿 32 bit → C 端讀值要 >> (32 − bit 數)） | | |
| 5 腳位（out / set / in / sideset 的 base、count） | | |
| 6 每圈或每 bit 幾 cycle（列算式）、clkdiv | | |
C 端和上表不同的地方（沒有寫「無」）：

---

【提示卡｜實作 4/9｜PIO 程式最小修改 + C init】→ 範本 7
Task (EN): Using the pio.md reference cards pasted earlier, output a minimal patch to the .pio and the matching C init, then fill the 7-row checklist. Answer in Traditional Chinese.
任務：照規格最小修改 PIO 程式，C 端 init 一起改。先貼 `pio.md` 的 PIO 1/8、3/8，模型回「收到」再貼這張。
<<<資料 開始>>>
[要改成什麼] {{例如 一次送 2 bit、CPU 每次 put 1 個 byte、baud 改 9600}}
[.pio 原文，帶行號]（`cat -n x.pio`）
{{貼}}
[C 端 init，帶行號]
{{貼}}
<<<資料 結束>>>
規則：
1. .pio 和 C 各最多改 4 行；程式名、label、腳位常數照原樣。只改速度 → 只改 clkdiv 或 baud，.pio 不動。
2. delay 上限看 .side_set（pio.md 3/8 的表）；不夠就改 clkdiv 或加 nop，不要寫超過上限的 [n]。
3. 左移 + 門檻 < 32：資料要放在 word 高位（put(v << (32 − 門檻))）；右移放低位。
只輸出：
檔名:行號
修改前：
修改後：
（每處一組，最多 4 組）
| 檢查 | 結果 OK / 有問題 | 依據 |
| 1 指令數 ≤ 32（同一個 PIO 的程式加總） | | |
| 2 非 opt side_set 每行都有 side；delay ≤ 上限 | | |
| 3 .wrap_target / .wrap 還包住迴圈 | | |
| 4 out/in 每次 bit 數 × 次數 = autopull/autopush 門檻 | | |
| 5 shift 方向和資料放的位置一致 | | |
| 6 新用到的腳有 set_*_pins、pio_gpio_init、pindirs | | |
| 7 用到 v1 指令 → 有 .pio_version 1 | | |
驗證：建置沒有 pioasm 錯誤，再跑 app 的測試

---

【提示卡｜實作 5/9｜DMA 設定：需求表 → pico-sdk 呼叫】→ 範本 7
Task (EN): Using the pico-dma.md cards pasted earlier, fill the 9-row table (spec value, current code, OK/NG), then output the full call sequence. Answer in Traditional Chinese.
任務：依規格填 DMA 設定表，寫出（或修正）完整呼叫順序。先貼 `pico-dma.md` DMA 1/8、2/8（PIO 再加 4/8），模型回「收到」。範本：`pico/app_dma.c` 的 dma_xfer()。
<<<資料 開始>>>
[規格] {{例如 把 uint8_t in[2048] 複製到 out，用 32-bit 傳輸}}
[現在的程式，帶行號]（從頭寫就寫「無」）
{{貼}}
<<<資料 結束>>>
規則：
1. 筆數 = 總 bytes ÷ 每筆 bytes（8/16/32-bit = 1/2/4），寫出算式；count 包 dma_encode_transfer_count(筆數)。
2. write_increment 預設 false：寫到陣列設 true，寫到 FIFO / 暫存器設 false。
3. 程式沒寫的項目，「現在程式」填「沒寫（預設 …）」再判斷。
只輸出：
| 項目 | 規格要的 | 現在程式 | OK/NG |
| 1 read_addr（configure 第 4 參數） | | | |
| 2 write_addr（第 3 參數） | | | |
| 3 每筆大小 DMA_SIZE_8/16/32 | | | |
| 4 筆數（算式） | | | |
| 5 read_increment（預設 true） | | | |
| 6 write_increment（預設 false） | | | |
| 7 DREQ（記憶體↔記憶體 DREQ_FORCE；PIO 用 pio_get_dreq） | | | |
| 8 chain_to（不串接就不設） | | | |
| 9 結束：wait_for_finish → unclaim | | | |
程式（照順序，≤ 10 行）：

---

【提示卡｜實作 6/9｜雙核分工：共享變數表 → 保護方式】→ 範本 7
Task (EN): Using the multicore-sync.md cards pasted earlier, list every variable both cores touch, pick ONE protection A–F for each, then output a minimal patch. Locks go only around the shared read/write lines. Answer in Traditional Chinese.
任務：找出兩核都會碰的變數，選保護方式，給最小修改。先貼 `multicore-sync.md` 多核同步 4/8、5/8，模型回「收到」。範本：`pico/app_multicore.c`（job_t / result_t + queue_t）。
<<<資料 開始>>>
[規格：core0、core1 各做什麼] {{…}}
[程式，帶行號]（兩核會跑到的函式與全域變數）
{{貼}}
<<<資料 結束>>>
保護方式：A 不共享（各核區域變數，最後合併一次）　B queue_t（傳一筆筆資料或工作）　C multicore_fifo（只傳 32-bit 通知或索引）　D spin lock / critical_section（鎖內只放那幾行）　E atomic（單一 32-bit 計數）　F 不用保護（launch 前寫好，之後只讀）
規則：
1. 計算、迴圈、printf、sleep 一律放鎖外；鎖內只有讀寫共享變數的那幾行。
2. 最多改 8 行；名稱與 TODO(改這裡) 照原樣。
只輸出：
| 變數 | 誰寫 | 誰讀 | 保護（照抄選項） |
鎖內的行（沒有鎖寫「無」）：
檔名:行號
修改前：
修改後：
驗證：跑 2 次結果相同，且等於單核版

---

【提示卡｜實作 7/9｜RISC-V 組語逐行解讀】→ 看到機器碼用實作 8
Task (EN): Using the riscv-hazard3.md cards pasted earlier, explain each assembly line in the table, then give the equivalent C and the suspicious points. Answer in Traditional Chinese.
任務：逐行解讀 RV32 組語，寫出等價的 C。先貼 `riscv-hazard3.md` RISC-V 1/8、2/8，模型回「收到」。
<<<資料 開始>>>
[組語，帶行號]（`cat -n f.S`，或 .dis 的一段）
{{貼}}
[參數意思]（a0、a1… 是什麼；沒有寫「無」）{{…}}
<<<資料 結束>>>
規則：
1. 每條指令一列（label、. 開頭的 directive 不算）；pseudo 照參考卡展開（bnez a1,L = bne a1,x0,L）。
2. 「運算」用 C 寫，暫存器名照原樣；lw/sw 的位址寫「基底 + offset」。
3. 有號 / 無號要分清楚：blt/bge 有號、bltu/bgeu 無號；srai 補符號位、srli 補 0；lb 有號、lbu 無號。
只輸出：
| 行 | 指令 | 運算（C 寫法） | 結果寫到 |
等價的 C（≤ 6 行）：
迴圈跑幾次（沒有迴圈寫「無」）：
可疑處（有號/無號、offset、沒存 ra 或 s 暫存器；沒有寫「無」）：
範例（只示範格式，內容不要照抄）：
| 7 | srli t2, t2, 1 | t2 = (uint32_t)t2 >> 1 | t2 |
| 8 | bltu t2, t3, 4b | if ((uint32_t)t2 < (uint32_t)t3) goto 4 | 跳到 label 4 |

---

【提示卡｜實作 8/9｜RISC-V 機器碼 → 組語（程式拆欄位）】
Task (EN): The fields were computed by a script. Copy them, pick the format from the opcode table, name the instruction, write the assembly. Do not split bits yourself. Answer in Traditional Chinese.
任務：機器碼翻回組語。欄位由程式算，你只抄、查表。
取得：本檔開頭「機器碼拆欄位」那行 python3 指令（X 換成機器碼），印出 2 行。
<<<資料 開始>>>
[機器碼] {{0x…}}
[程式印出的 2 行]
{{貼}}
<<<資料 結束>>>
opcode 表（數字 = funct3）：0x33 R：add 0 sll 1 slt 2 sltu 3 xor 4 srl 5 or 6 and 7（f7=0x20：sub、sra）｜0x13 I：addi 0 slli 1 slti 2 sltiu 3 xori 4 srli 5 ori 6 andi 7（f7=0x20：srai）｜0x03 I：lb 0 lh 1 lw 2 lbu 4 lhu 5｜0x23 S：sb 0 sh 1 sw 2｜0x63 B：beq 0 bne 1 blt 4 bge 5 bltu 6 bgeu 7｜0x6f J：jal｜0x67 I：jalr｜0x37 U：lui｜0x17 U：auipc
規則：imm 只抄第 2 行裡和「格式」同字母的那個數（格式 S 就抄 S 後面的數；R 沒有 imm）；slli/srli/srai 的位移量 = rs2 欄位。
只輸出：
opcode：
格式：
funct3 / funct7：
rd / rs1 / rs2：
imm：
組語（暫存器寫 xN）：
驗證：echo ".insn 0xX" | riscv64-unknown-elf-as -march=rv32i -o t.o - && riscv64-unknown-elf-objdump -dM no-aliases,numeric t.o（分支、jal 印的是目標位址，從 0 算：ffffffec = −20）

---

【提示卡｜實作 9/9｜從規格改 ROS 2 node（node_template.py）】→ 範本 7
Task (EN): Fill the interface table from the spec, then output minimal edits to node_template.py. The subscription QoS must match the other side's publisher. Answer in Traditional Chinese.
任務：照規格改 `ros2/node_template.py`。先貼 `ros2.md` 的 ROS 2 3/8（QoS），模型回「收到」。
<<<資料 開始>>>
[規格原文]（node 名、topic、型別、QoS、參數、運算）
{{貼}}
[node_template.py 相關行，帶行號]（`cat -n ros2/node_template.py | sed -n 14,63p`）
{{貼}}
<<<資料 結束>>>
規則：
1. 型別 std_msgs/msg/X → `from std_msgs.msg import X`；create_publisher、create_subscription、callback 裡建立的訊息各自換成對的型別。
2. 對方 publisher 是 BEST_EFFORT（sensor_data）→ 我的 subscription 也 BEST_EFFORT；pub、sub 不同 QoS 就多一個 QoSProfile 給 sub。規格沒寫用 RELIABLE。
3. 參數預設值的型別照規格（0.5 不能寫成 0 或 1）。
只輸出：
| topic | 方向 pub/sub | 型別 | QoS |
node 名稱：
參數（名稱 = 預設值）：
檔名:行號
修改前：
修改後：
（每處一組，最多 10 行）
驗證：ros2 topic info -v 對方的 topic 看兩端 QoS，再 ros2 topic pub --once 測一筆
