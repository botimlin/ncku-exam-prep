# 在電腦上除錯 C / Python（gcc、sanitizer、gdb、strace、pdb）

> 全部在這台 Ubuntu 24.04 上實際跑過（gcc 13.3、gdb 15.1、strace、Python 3.12）。
> 症狀→原因的大表在 [`../../prompt工具包/cards/04-debug.md`](../../prompt工具包/cards/04-debug.md)，這份講「工具怎麼用」。
> 這台主機**沒有** `ltrace`、`valgrind`、`py-spy`；**有** `perf`。考場先 `which gdb strace` 確認。

## 1. 編譯參數：除錯版 vs 正式版

| 參數 | 作用 | 什麼時候用 |
|---|---|---|
| `-g -O0` | 有行號、變數不會被最佳化掉 | 用 gdb 時（`-O2` 會看到 `k=<optimized out>`，實測） |
| `-Wall -Wextra` | 開常見警告 | **永遠開**，警告常常就是 bug |
| `-Werror=parentheses` | 只把某一種警告變成錯誤 | 不想全部 `-Werror` 時 |
| `-fsanitize=address,undefined -fno-omit-frame-pointer` | 抓越界、use-after-free、溢位、移位錯 | 結果怪、偶爾當掉 |
| `-fsanitize=undefined -fno-sanitize-recover=all` | UB 一發生就停，exit code 變 1 | 想讓測試直接失敗 |
| `-fsanitize=thread -O1 -pthread` | 抓 data race（**不能**和 address 一起用） | 多執行緒結果每次不一樣 |

實測 `-Wall -Wextra` 抓到的：
```
w.c:5:9: warning: suggest parentheses around assignment used as truth value [-Wparentheses]     ← if (n = 5)
w.c:6:40: warning: comparison of integer expressions of different signedness: 'int' and 'unsigned int' [-Wsign-compare]
```
⚠ sanitizer 版本會慢 2–5 倍，**只拿來找 bug，交出去的版本要拿掉**。在 CMake 裡：
`target_compile_options(app PRIVATE -fsanitize=address,undefined)` 加上 `target_link_options(app PRIVATE -fsanitize=address,undefined)`。

## 2. Sanitizer 輸出怎麼讀：找「第一個在你程式裡的 frame」

### 2a. 陣列越界（`for (i = 0; i <= n; i++)`）
沒開 sanitizer：印出 `sum=28`、exit code 0 —— **看起來是對的，bug 被藏起來了**。開 ASan 後：
```
==1598859==ERROR: AddressSanitizer: heap-buffer-overflow on address 0x503000000060 ...
READ of size 4 at 0x503000000060 thread T0
    #0 0x61cb15e473d3 in sum oob.c:6            ← 第一個是你的程式：oob.c 第 6 行讀越界
    #1 0x61cb15e47601 in main oob.c:13          ← 誰呼叫的
    #2 ... in __libc_start_call_main             ← libc 的，不用看
0x503000000060 is located 0 bytes after 32-byte region   ← 剛好超過 32 bytes (8 個 int) 的結尾 = 差一 (off-by-one)
allocated by thread T0 here:
    #1 ... in main oob.c:11                     ← 這塊記憶體是在第 11 行 malloc 的
```
讀法：**錯誤種類**（heap-buffer-overflow / stack-buffer-overflow / heap-use-after-free）→ **READ 或 WRITE、幾 bytes** →
**#0 的檔名:行號** → `located N bytes after` 判斷超出多少。下面的 Shadow bytes 不用看。

### 2b. use-after-free
```
ERROR: AddressSanitizer: heap-use-after-free ...
    #0 ... in main uaf.c:8        ← 在這裡使用
freed by thread T0 here:
    #1 ... in main uaf.c:7        ← 在這裡 free 的
previously allocated by thread T0 here:
    #1 ... in main uaf.c:5
```

### 2c. UB（整數溢位、移位超過寬度）
沒開：印出 `-2147483648 1`，不會有任何警告。開 `-fsanitize=undefined`：
```
ub.c:5:9: runtime error: signed integer overflow: 2147483647 + 1 cannot be represented in type 'int'
ub.c:8:20: runtime error: shift exponent 32 is too large for 32-bit type 'unsigned int'
```
→ 封包解析、CRC、bit 運算的題目特別常見：改用 `uint32_t`，或寫成 `(uint64_t)` 再移位。

### 2d. data race（兩個 thread 同時 `counter++`）
沒開：`counter=144230`、`counter=181755`（期望 200000，每次都不一樣）。開 TSan：
```
WARNING: ThreadSanitizer: data race (pid=1598952)
  Read of size 8 at 0x55ffc6052018 by thread T2:
    #0 work race.c:4
  Previous write of size 8 at 0x55ffc6052018 by thread T1:
    #0 work race.c:4
  Location is global 'counter' of size 8         ← 哪一個變數
SUMMARY: ThreadSanitizer: data race race.c:4 in work
```
→ 修法：`pthread_mutex`、`atomic_fetch_add`，或每個 thread 算自己的區域總和，最後再加起來（最快）。

## 3. gdb 速成（用 `crash.c`：鏈結串列走太遠 → NULL）

```bash
gcc -g -O0 crash.c -o crash
./crash 5 7          # Segmentation fault (core dumped), exit code 139
gdb -q -batch -ex "run 5 7" -ex bt ./crash      # ★ 一行就知道當在哪
```
實際輸出：
```
Program received signal SIGSEGV, Segmentation fault.
0x000055555555522d in nth (h=0x0, k=7) at crash.c:17
17	        h = h->next;            /* crashes when k >= length */
#0  0x000055555555522d in nth (h=0x0, k=7) at crash.c:17     ← h=0x0：NULL 指標
#1  0x00005555555552f4 in main (argc=3, argv=...) at crash.c:26
```
- gdb 一開始問 `Enable debuginfod for this session? (y or [n])` → 直接按 Enter（選 n）。不想被問：`export DEBUGINFOD_URLS=`。
- 程式要讀 stdin：`gdb ./prog` 之後 `run < input.txt`。

### 互動指令（`gdb ./crash` 進去之後打）

| 指令 | 作用 | 實測輸出範例 |
|---|---|---|
| `run 5 7` / `r` | 帶參數執行 | |
| `bt` | 呼叫堆疊（當掉時第一個打的指令） | `#0 nth (h=0x0, k=7) at crash.c:17` |
| `frame 1` / `f 1` | 切到第 1 層（main），看它的變數 | `#1 ... in main ... crash.c:26` |
| `info locals` / `info args` | 所有區域變數 / 參數 | `n = 5  k = 7  arr = {0, 1, 4, ...}` |
| `p arr` | 印整個陣列 | `{0, 1, 4, 9, 16, 25, 36, 49, 64, 81}` |
| `p arr[2]@4` | 從 arr[2] 開始印 4 個 | `{4, 9, 16, 25}` |
| `p buf[0]@len` | 印指標指向的 len 個元素（malloc 來的陣列要這樣印） | |
| `p/x n` | 用 16 進位印 | `0x5` |
| `p *h` / `p h->next->val` | 印結構 / 跟著指標走 | `{val = 40, next = 0x555555559300}` / `30` |
| `list` / `l` | 印目前位置附近的原始碼 | |
| `break crash.c:9` / `b nth` | 在某一行 / 某函式停下 | |
| `break crash.c:9 if i == 3` | 有條件的中斷點 | 停的時候 `p i` → `3` |
| `tbreak nth` | 只停一次的中斷點 | `Temporary breakpoint 2, nth (...)` |
| `watch s` | 變數**被改**的時候停 | `Old value = 1  New value = 3` |
| `display i` | 每走一步都自動印 i | `1: i = 0` |
| `next` / `n` | 下一行（不進入函式） | |
| `step` / `s` | 下一行（會進入函式） | |
| `finish` | 跑完目前的函式，印出回傳值 | `Value returned is $4 = 20` |
| `continue` / `c` | 繼續跑到下一個中斷點 | |
| `info breakpoints` / `delete` | 列出 / 刪除全部中斷點 | |
| `info threads` / `thread 2` / `thread apply all bt` | 多執行緒 | 見 §4 |
| `quit` / `q` | 離開 | |

一次跑完一串（不用互動，適合貼給 LLM 看）：
```bash
gdb -q -batch -ex "break crash.c:9 if i == 3" -ex "run 5 2" -ex "p i" -ex "p *x" \
    -ex "delete" -ex "tbreak nth" -ex "continue" -ex "info args" -ex finish ./crash
```

### core dump
- 這台：`ulimit -c` 預設 0，`core_pattern` 是 apport。`ulimit -c unlimited` 之後當掉，core 存在
  `/var/lib/apport/coredump/core.<很長的路徑>.<pid>...`，用 `gdb ./crash /var/lib/apport/coredump/core.xxx` 再 `bt`（實測成功）。
- **在 Docker 容器裡**（實測）：core 被送到主機的 apport，容器裡**找不到 core 檔**。→ 考場不要依賴 core，直接用 `gdb -batch -ex run -ex bt`。

## 4. 程式卡住（hang / deadlock）

**方法 A（考場一定能用）**：在 gdb 裡執行 → 卡住時按 **Ctrl-C** → `thread apply all bt`。
（非互動版：`( sleep 2; pkill -INT -x hang ) & gdb -q -batch -ex run -ex "thread apply all bt" ./hang`）

兩把鎖順序相反的實測結果：
```
Thread 3 ... "hang":
#3  ___pthread_mutex_lock (mutex=0x555555558040 <A>)     ← thread 3 在等鎖 A
#4  0x000055555555526f in t2 (p=0x0) at hang.c:6
Thread 2 ... "hang":
#3  ___pthread_mutex_lock (mutex=0x555555558080 <B>)     ← thread 2 在等鎖 B
#4  0x0000555555555221 in t1 (p=0x0) at hang.c:5
Thread 1 ... in main () at hang.c:11                     ← main 在 pthread_join
```
→ 每個 thread 都往下找**第一個你寫的函式**（t1、t2），就知道誰在等誰 → 改成兩邊用相同的上鎖順序。

**方法 B：`gdb -p PID` 接上已經在跑的程式** —— 這台實測**失敗**：
```
Could not attach to process. ... check the setting of /proc/sys/kernel/yama/ptrace_scope
```
因為 `ptrace_scope=1`（只能 debug 自己的子程序）。不能改系統設定 → 用方法 A。容器裡要 `docker run --cap-add=SYS_PTRACE` 才可能成功。

## 5. strace：看程式跟作業系統說了什麼

```bash
strace -e trace=openat ./cfg              # 開不了哪個檔？
strace -f -e trace=openat,read,write ./prog    # -f 包含子程序/thread
strace -f -o trace.txt ./prog             # 存檔，輸出不會跟程式的輸出混在一起
strace -c ./prog                          # 每一種系統呼叫的次數和時間統計
```
實測：程式只印 `load failed`，strace 一下就知道是什麼：
```
openat(AT_FDCWD, "config/params.txt", O_RDONLY) = -1 ENOENT (No such file or directory)
```
→ **相對路徑**是從「你在哪裡執行」開始算，不是從執行檔的位置。評分系統的工作目錄可能不一樣。

卡住時看最後一行（實測）：`read(0,` 後面沒有結果 = **在等 stdin**（忘了 `< input.txt`、或在等序列埠/socket）。
`strace -p PID` 和 `gdb -p` 一樣會被 ptrace_scope 擋住。

`time ./prog`：`real` = 實際經過的時間；`user`+`sys` > `real` = 有用到多核心；`real` 遠大於 `user` = 在等 I/O 或 sleep。

## 6. Python

**讀 traceback：從最下面往上看。** 最後一行是錯誤種類，往上第一個**你的檔案**就是出事的地方：
```
  File ".../bug.py", line 11, in main
    print(parse(f))
  File ".../bug.py", line 6, in parse
    return struct.unpack("<%dI" % (n // 4), payload)
struct.error: unpack requires a buffer of 4 bytes      ← n=6 不是 4 的倍數
```

| 工具 | 指令 | 用途 |
|---|---|---|
| pdb 從頭開始 | `python3 -m pdb bug.py` → `b parse`、`c`、`n`、`s`、`p n, len(frame)`、`where`、`q` | 一步一步跑 |
| 當掉時自動停（post-mortem） | `python3 -m pdb -c continue bug.py` | 出現 `Uncaught exception. Entering post mortem debugging` 後 `p n, len(frame)` → `(6, 8)` |
| 程式裡設中斷點 | 在要停的那一行寫 `breakpoint()` | 不用改指令 |
| 卡住 | 直接按 Ctrl-C → `KeyboardInterrupt` 的 traceback 就是卡住的位置 | |
| 卡住（不能 Ctrl-C） | 程式開頭加 `import faulthandler, signal; faulthandler.register(signal.SIGUSR1)`，然後 `kill -USR1 PID` | 實測印出 `File ..., line 4 in wait_ack` |
| C 擴充模組 segfault | `python3 -X faulthandler prog.py` | 實測印出 `Fatal Python error: Segmentation fault` 和 Python 的呼叫堆疊 |
| py-spy | **沒有安裝**，考場也不能裝 → 用上面兩種 | |

## 7. printf 除錯的紀律

1. **除錯訊息一律印到 stderr**。評分只比對 stdout，多一行就錯。
2. **輸出被吃掉的陷阱**（實測）：stdout 接到 pipe 或檔案時是**整塊緩衝**的，程式當掉時，緩衝區裡還沒寫出去的東西**全部消失**：
   ```
   ./lost | cat        → 只看到 "DBG step 1 (stderr)"，stdout 的 "step 1 ok" 不見了
   ```
   評分系統一定是用 pipe 接輸出。→ C 用 `fprintf(stderr, ...)` 或 `fflush(stdout)`；Python 用 `print(..., flush=True)` 或 `print(..., file=sys.stderr)`。
3. **二分法**：在程式中間印一行 → 有印到 = bug 在後半段 → 再印在後半段的中間 → 大約 5 次就能找到出錯的那一行。
4. 印**數值**不要只印「到這裡了」：`fprintf(stderr, "i=%d n=%d s=%d\n", i, n, s);`
5. 可以整個關掉的 DEBUG 巨集（實測：沒加 `-DDEBUG` 時完全沒有輸出、也沒有警告）：
```c
#ifdef DEBUG
#define DBG(...) fprintf(stderr, "[%s:%d] ", __FILE__, __LINE__), fprintf(stderr, __VA_ARGS__)
#else
#define DBG(...) ((void)0)
#endif
DBG("x=%d\n", x);          // gcc -DDEBUG ... 時才會印：[dbg.c:9] x=42
```
CMake：`cmake -B build -DCMAKE_C_FLAGS=-DDEBUG`（實測有加到編譯指令裡）。交出去之前再 `rm -rf build` 重建一次，確認沒有帶 -DDEBUG。
