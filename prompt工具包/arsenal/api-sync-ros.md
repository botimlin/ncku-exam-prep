# 軍火庫：Pico 多核同步、計時/stdio/GPIO、micro-ROS rclc、電腦端 rclpy/pyserial/struct
> 用法：一次只貼一張卡（兩條 `---` 之間）進對話，等模型回「收到」再問；函式名、參數順序、數值照卡上抄。
> 來源與驗證：pico-sdk 2.2.0 標頭 grep（2.1.1 這些原型相同）＋ pico2 測試專案 `-Wall -Wextra -Werror` 編譯連結 0 警告；micro-ROS jazzy `libmicroros/include` 標頭＋同專案連結 `libmicroros.a`；pyserial 3.5 inspect＋pty 實跑；struct/array 實跑；rclpy 只從 repo 範本複製（之前在 Jazzy 容器跑過，這次沒實跑）。都沒在板子上跑｜最後更新 2026-11-13

---

【API卡｜SYNC 1/5｜multicore 啟動與 FIFO】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void multicore_launch_core1(void (*entry)(void))`：core1 跑 entry
- `void multicore_reset_core1(void)`：只在 core0 呼叫
- `void multicore_fifo_push_blocking(uint32_t data)`：滿就等
- `uint32_t multicore_fifo_pop_blocking(void)`：空就等
- `bool multicore_fifo_pop_timeout_us(uint64_t timeout_us, uint32_t *out)`：逾時回 false
- `bool multicore_fifo_rvalid(void)`：有資料可讀
- `bool multicore_fifo_wready(void)`：還有空位
- `void multicore_fifo_drain(void)`
FIFO 每方向 32 bit × **4 格**（RP2040 是 8）。launch 也用 FIFO → 傳資料優先用 `queue_t`。
```c
static void core1_entry(void) {          // 型別 void (*)(void)
    while (true) {
        uint32_t v = multicore_fifo_pop_blocking();
        multicore_fifo_push_blocking(v * 2u);
    }
}
    multicore_launch_core1(core1_entry); // 傳函式名，不加 ()
    multicore_fifo_push_blocking(21u);
    uint32_t r;
    if (multicore_fifo_pop_timeout_us(1000, &r)) { /* r == 42 */ }
```
- ✗ `multicore_launch_core1(core1_entry())` → ✓ `(core1_entry)`
- ✗ `pop_timeout_us(&r, 1000)` → ✓ `(1000, &r)`
- core1 stack 預設 0x800（2 KB）→ 大陣列用 static。
前提：`#include "pico/multicore.h"`；CMake `pico_stdlib pico_multicore`
驗證：push 21 → pop 得 42。

---

【API卡｜SYNC 2/5｜queue_t 跨核佇列】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void queue_init(queue_t *q, uint element_size, uint element_count)`：先大小(bytes) 後個數；回 void
- `bool queue_try_add(queue_t *q, const void *data)`：滿 → false
- `bool queue_try_remove(queue_t *q, void *data)`：空 → false
- `bool queue_try_peek(queue_t *q, void *data)`：看、不取走
- `void queue_add_blocking(queue_t *q, const void *data)`：滿就等
- `void queue_remove_blocking(queue_t *q, void *data)`：空就等
- `uint queue_get_level(queue_t *q)`：目前幾個
```c
typedef struct { uint32_t id; int32_t val; } item_t;
static queue_t q;                          // 全域 / static
    queue_init(&q, sizeof(item_t), 8);     // (q, 元素大小 bytes, 元素個數)
    item_t a = { 1, 42 }, b;
    queue_add_blocking(&q, &a);            // 傳指標；內容 memcpy 進去
    if (queue_try_remove(&q, &b)) { }      // 空 → false
    uint n = queue_get_level(&q);          // 目前幾個
```
- ✗ `queue_init(&q, 8, sizeof(item_t))` → ✓ `(&q, sizeof(item_t), 8)`（反了不報錯）
- ✗ `queue_add_blocking(&q, a)` → ✓ `&a`
- ✗ ISR 裡 `_blocking` → ✓ 只用 `queue_try_*`
- `queue_init` 要在 launch core1 前。
前提：`#include "pico/util/queue.h"`；CMake `pico_stdlib`（含 pico_util）
驗證：add 1 筆後 `queue_get_level(&q)` == 1。

---

【API卡｜SYNC 3/5｜spinlock 與鎖號】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `int spin_lock_claim_unused(bool required)`：回 24–31；false 且沒有 → -1
- `spin_lock_t *spin_lock_init(uint lock_num)`：設為未上鎖，回指標
- `uint32_t spin_lock_blocking(spin_lock_t *lock)`：關本核 IRQ＋拿鎖，回舊 IRQ 狀態
- `void spin_unlock(spin_lock_t *lock, uint32_t saved_irq)`：放鎖＋還原 IRQ
鎖號 `PICO_SPINLOCK_ID_*`：
| 號碼 | 用途 |
|---|---|
| 0–13 | SDK 保留（IRQ=9、TIMER=10、HARDWARE_CLAIM=11、RAND=12、ATOMIC=13） |
| 14–15 | OS1 / OS2 |
| 16–23 | STRIPED_FIRST..LAST（queue/mutex/sem 共用） |
| 24–31 | CLAIM_FREE_FIRST..LAST（`spin_lock_claim_unused`、`critical_section_init` 用） |
```c
    int num = spin_lock_claim_unused(true);    // 24..31；true=沒有就 panic
    lk = spin_lock_init((uint)num);            // 回傳 spin_lock_t *
    uint32_t save = spin_lock_blocking(lk);    // 拿鎖 + 關本核 IRQ
    shared++;
    spin_unlock(lk, save);                     // 一定兩個參數
```
- ✗ `spin_unlock(lk)` → ✓ `spin_unlock(lk, save)`
- ✗ 自己挑號 `spin_lock_init(3)` → ✓ 用 `spin_lock_claim_unused(true)` 的號
- RP2350 預設 `PICO_USE_SW_SPIN_LOCKS`=1（erratum E2）；不要寫 `sio_hw->spinlock[]`。
前提：`#include "hardware/sync.h"`；CMake `pico_stdlib`
驗證：兩核各加 N 次，`shared` == 2N。

---

【API卡｜SYNC 4/5｜critical_section 與 mutex】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void critical_section_init(critical_section_t *crit_sec)`：claim 一個 24–31 的鎖
- `void critical_section_enter_blocking(critical_section_t *crit_sec)`：關本核 IRQ＋鎖
- `void critical_section_exit(critical_section_t *crit_sec)`
- `void critical_section_deinit(critical_section_t *crit_sec)`：還鎖號，之後不能用
- `void mutex_init(mutex_t *mtx)`
- `void mutex_enter_blocking(mutex_t *mtx)`：ISR 不可用
- `bool mutex_try_enter(mutex_t *mtx, uint32_t *owner_out)`：owner_out 可 NULL；ISR 可用
- `void mutex_exit(mutex_t *mtx)`
```c
    critical_section_init(&cs);
    critical_section_enter_blocking(&cs);
    shared++;                                  // 極短
    critical_section_exit(&cs);
    mutex_init(&mtx);
    mutex_enter_blocking(&mtx);
    shared++;                                  // 可較長；不能在 ISR
    mutex_exit(&mtx);
```
- critical_section：跨核＋本核 ISR 都安全，臨界區極短；mutex：持有可較久，只給兩核主程式。
- ✗ 同一核連 `mutex_enter_blocking` 兩次 → deadlock；巢狀用 `recursive_mutex_t`
- ✗ 每個變數都 `critical_section_init` → 只有 8 個號，用完 panic
- 全域 mutex 可寫 `auto_init_mutex(name);` 免 init。
前提：`#include "pico/sync.h"`；CMake `pico_stdlib`
驗證：兩核各加 N 次，`shared` == 2N。

---

【API卡｜SYNC 5/5｜semaphore、關中斷、__dmb】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void sem_init(semaphore_t *sem, int16_t initial_permits, int16_t max_permits)`：初始可用數、上限
- `void sem_acquire_blocking(semaphore_t *sem)`：等到 >0 再 −1
- `bool sem_acquire_timeout_ms(semaphore_t *sem, uint32_t timeout_ms)`
- `bool sem_release(semaphore_t *sem)`：+1；已到上限回 false；ISR 可呼叫
- `uint32_t save_and_disable_interrupts(void)`：只關本核，回舊狀態
- `void restore_interrupts(uint32_t status)`
- `void __dmb(void)`：記憶體屏障
```c
    sem_init(&sem, 0, 1);                      // (sem, 初始, 最大)
    bool ok = sem_release(&sem);               // 另一核 / ISR 通知；已滿回 false
    sem_acquire_blocking(&sem);                // 等到 permits > 0
    uint32_t s = save_and_disable_interrupts();// 只擋本核
    shared++;
    restore_interrupts(s);
    __dmb();                                   // 記憶體屏障
```
- ✗ `sem_wait` / `sem_post`（POSIX）→ ✓ `sem_acquire_blocking` / `sem_release`
- ✗ `sem_init(&sem, 1)` → ✓ 三個參數
- ✗ 用關中斷擋另一核 → 擋不住；跨核用 spinlock / critical_section
前提：`#include "pico/sync.h"`、`"hardware/sync.h"`；CMake `pico_stdlib`
驗證：core1 `sem_release` 後 core0 的 `sem_acquire_blocking` 返回。

---

【API卡｜PICO-IO 1/4｜計時 API】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `uint32_t time_us_32(void)`：開機後 µs；約 71.6 分（1h11m35s）繞回
- `uint64_t time_us_64(void)`：不會繞回
- `absolute_time_t get_absolute_time(void)`：2.x 預設就是 `uint64_t` µs
- `int64_t absolute_time_diff_us(absolute_time_t from, absolute_time_t to)`：= to − from
- `absolute_time_t make_timeout_time_ms(uint32_t ms)`：現在 + ms
- `bool time_reached(absolute_time_t t)`：到了 → true
- `void sleep_ms(uint32_t ms)`、`void sleep_us(uint64_t us)`：低功耗等；不可在 IRQ
- `void busy_wait_us(uint64_t delay_us)`、`void busy_wait_ms(uint32_t delay_ms)`：純忙等
```c
    absolute_time_t start = get_absolute_time();
    sleep_ms(10);                              // 可讓出 CPU（低功耗等）
    int64_t us = absolute_time_diff_us(start, get_absolute_time()); // to - from
    absolute_time_t dl = make_timeout_time_ms(500);
    while (!time_reached(dl)) { tight_loop_contents(); }
```
- ✗ `absolute_time_diff_us(end, start)` → 負數；✓ `(start, end)`
- ✗ IRQ handler 裡 `sleep_ms` → ✓ `busy_wait_us`
前提：`#include "pico/stdlib.h"`；CMake `pico_stdlib`
驗證：`sleep_ms(10)` 前後 diff ≈ 10000。

---

【API卡｜PICO-IO 2/4｜stdio 收發與錯誤碼】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `int getchar_timeout_us(uint32_t timeout_us)`：回 0–255 或 `PICO_ERROR_TIMEOUT`；0 = 不等
- `bool stdio_usb_connected(void)`：主機已開 port（DTR）
- `int stdio_put_string(const char *s, int len, bool newline, bool cr_translation)`：len=-1 → strlen；回 len
- `int putchar_raw(int c)`：1 byte，不轉 CRLF
- `void stdio_flush(void)`
錯誤碼：`PICO_OK`=0、`PICO_ERROR_GENERIC`=-1、`PICO_ERROR_TIMEOUT`=**-2**、`PICO_ERROR_NO_DATA`=-3。
```c
    while (!stdio_usb_connected()) sleep_ms(50);   // 等主機開 port（DTR）
    int c = getchar_timeout_us(0);                 // 0 = 不等
    if (c != PICO_ERROR_TIMEOUT) {                 // PICO_ERROR_TIMEOUT = -2
        uint8_t b = (uint8_t)c;                    // 0..255
        (void)b;
    }
    static const char pkt[] = { 0x01, 0x0A, 0x00 };
    stdio_put_string(pkt, 3, false, false);        // (s, len, newline, cr_translation)
    stdio_flush();
```
- ✗ `c == EOF` / `c == -1` 當沒資料 → ✓ `c == PICO_ERROR_TIMEOUT`
- ✗ printf 送二進位（0x0A 變 0D 0A）→ ✓ `stdio_put_string(buf, n, false, false)`
前提：`#include "pico/stdlib.h"`、`"pico/stdio_usb.h"`；CMake `pico_stdlib`＋`pico_enable_stdio_usb(app 1)`
驗證：電腦收到 `01 0a 00`（沒有 0d）。

---

【API卡｜PICO-IO 3/4｜GPIO 與板載 LED】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `void gpio_init(uint gpio)`：設 SIO 功能、輸入、輸出值 0
- `void gpio_set_dir(uint gpio, bool out)`：`GPIO_OUT`=1、`GPIO_IN`=0
- `void gpio_put(uint gpio, bool value)`
- `bool gpio_get(uint gpio)`
- `void gpio_pull_up(uint gpio)`
`PICO_DEFAULT_LED_PIN` = **25**（pico、pico2）；`pico2_w` 沒定義（LED 在無線晶片上）。
```c
    gpio_init(PICO_DEFAULT_LED_PIN);               // pico2 = 25
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);  // GPIO_OUT=1, GPIO_IN=0
    gpio_put(PICO_DEFAULT_LED_PIN, 1);             // 1 亮 / 0 暗
    gpio_init(IN_PIN);
    gpio_set_dir(IN_PIN, GPIO_IN);
    gpio_pull_up(IN_PIN);
    bool level = gpio_get(IN_PIN);
```
要換：`IN_PIN` = 你的輸入腳號（例 15）。
- ✗ 沒 `gpio_init` 就 `gpio_put` → 腳不動；✓ init → set_dir → put
- ✗ `gpio_set_dir(pin, 0)` 想當輸出 → 0 是輸入；✓ `GPIO_OUT`
前提：`#include "pico/stdlib.h"`（含 hardware/gpio.h）；CMake `pico_stdlib`
驗證：板載 LED 亮。

---

【API卡｜PICO-IO 4/4｜標頭 → CMake 函式庫名】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
pico-sdk 2.2.0、pico2 實測：只連 `pico_stdlib pico_multicore` 就能編譯連結本檔 SYNC、PICO-IO 全部函式。
| 標頭 | CMake |
|---|---|
| `pico/stdlib.h`、`pico/time.h`、`hardware/timer.h`、`hardware/gpio.h` | `pico_stdlib` |
| `pico/util/queue.h` | `pico_stdlib`（含 `pico_util`） |
| `pico/sync.h`、`hardware/sync.h` | `pico_stdlib`（含 `pico_sync`、`hardware_sync`） |
| `pico/multicore.h` | `pico_multicore`（要另外加） |
| `pico/stdio_usb.h` | `pico_enable_stdio_usb(app 1)` |
| `rcl/…`、`rclc/…`、`rmw_microros/…`、`std_msgs/…` | `microros` |
```cmake
target_link_libraries(app pico_stdlib pico_multicore microros)
target_include_directories(app PUBLIC libmicroros/include)
pico_enable_stdio_usb(app 1)
pico_enable_stdio_uart(app 0)
```
- micro-ROS 另要 `link_directories(libmicroros)`（放在 `add_executable` 前）。
- ✗ 寫 `hardware_multicore` / `pico_queue` → 不存在；✓ `pico_multicore`，queue 在 `pico_stdlib`
- ✗ 漏 `pico_multicore` → `pico/multicore.h: No such file`
前提：`pico_sdk_init()` 之後寫
驗證：`make` 0 錯誤，產生 `app.uf2`。

---

【API卡｜UROS 1/6｜support、node 初始化】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
micro-ROS jazzy，全部回傳 `rcl_ret_t`：`RCL_RET_OK`=0、`RCL_RET_ERROR`=1、`RCL_RET_TIMEOUT`=2。
- `rcl_allocator_t rcl_get_default_allocator()`
- `rclc_support_init(rclc_support_t *support, int argc, char const * const *argv, rcl_allocator_t *allocator)`
- `rclc_node_init_default(rcl_node_t *node, const char *name, const char *namespace_, rclc_support_t *support)`
```c
#define RCCHECK(fn) { rcl_ret_t rc_ = (fn); if (rc_ != RCL_RET_OK) error_loop(); }
rclc_support_t support;
rcl_node_t node;
rcl_allocator_t allocator;
    allocator = rcl_get_default_allocator();
    RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
    RCCHECK(rclc_node_init_default(&node, "compute_node", "pico0", &support));
```
要換：`"compute_node"` = node 名；`"pico0"` = namespace（每塊板子不同；不要給 `""`）。
- `RCCHECK` 要自己 `#define`（rclc.h 沒有）；`error_loop()` 自己寫（LED 快閃）；物件放全域。
- ✗ `rclc_support_init(&support, &allocator)` → ✓ 四個參數 `(&support, 0, NULL, &allocator)`
- ✗ `rclc_node_init_default(&node, "n", &support)` → ✓ namespace 在 support 前面
前提：`#include <rcl/rcl.h>`、`<rclc/rclc.h>`
驗證：`ros2 node list` 看到 `/pico0/compute_node`。

---

【API卡｜UROS 2/6｜publisher、subscription、type support】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rclc_publisher_init_default(rcl_publisher_t *publisher, const rcl_node_t *node, const rosidl_message_type_support_t *type_support, const char *topic_name)`
- `rclc_publisher_init_best_effort(…同上四個…)`
- `rclc_subscription_init_default(rcl_subscription_t *subscription, rcl_node_t *node, const rosidl_message_type_support_t *type_support, const char *topic_name)`
- `rclc_subscription_init_best_effort(…同上四個…)`
- `ROSIDL_GET_MSG_TYPE_SUPPORT(套件, msg, 型別)`：三個參數
```c
    const rosidl_message_type_support_t *ts =
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray);
    RCCHECK(rclc_publisher_init_default(&pub, &node, ts, "output"));
    RCCHECK(rclc_subscription_init_default(&sub, &node, ts, "input"));
```
- `_default` = RELIABLE；`_best_effort` = BEST_EFFORT；電腦端 QoS 要配（RELIABLE 訂閱收不到 BEST_EFFORT 發佈）。
- namespace `pico0` + `"input"` → `/pico0/input`；`"/input"` 開頭有 `/` 就不加 namespace。
- ✗ `ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, Int32MultiArray)` → ✓ `(std_msgs, msg, Int32MultiArray)`
前提：`#include <std_msgs/msg/int32_multi_array.h>`（型別 `Int32MultiArray` → 檔名 `int32_multi_array.h`）
驗證：`ros2 topic info -v /pico0/input` 看 QoS。

---

【API卡｜UROS 3/6｜timer 與 executor】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rclc_timer_init_default2(rcl_timer_t *timer, rclc_support_t *support, const uint64_t timeout_ns, const rcl_timer_callback_t callback, bool autostart)`
- `rclc_executor_init(rclc_executor_t *executor, rcl_context_t *context, const size_t number_of_handles, const rcl_allocator_t *allocator)`
- `rclc_executor_add_timer(rclc_executor_t *executor, rcl_timer_t *timer)`
- `rclc_executor_spin_some(rclc_executor_t *executor, const uint64_t timeout_ns)`
- `RCL_MS_TO_NS(ms)` = ms × 1000000LL
```c
    RCCHECK(rclc_timer_init_default2(&timer, &support, RCL_MS_TO_NS(100), timer_cb, true));
    executor = rclc_executor_get_zero_initialized_executor();
    RCCHECK(rclc_executor_init(&executor, &support.context, 3, &allocator)); // 1 timer + 2 sub
    RCCHECK(rclc_executor_add_timer(&executor, &timer));
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));
```
- handles 數 = timer 數 + sub 數；不夠 → add 回錯誤。
- spin_some 沒資料回 `RCL_RET_TIMEOUT`（正常，不要當錯誤）。
- ✗ `rclc_timer_init_default(...)`（4 參數）→ deprecated warning；✓ `_default2(..., true)`
- ✗ `rclc_executor_init(&executor, &support, …)` → ✓ `&support.context`
前提：`#include <rclc/executor.h>`（rclc.h 不含）
驗證：`ros2 topic hz` ≈ 10 Hz。

---

【API卡｜UROS 4/6｜subscription callback 與 rcl_publish】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rclc_executor_add_subscription(rclc_executor_t *executor, rcl_subscription_t *subscription, void *msg, rclc_subscription_callback_t callback, rclc_executor_handle_invocation_t invocation)`
- invocation：`ON_NEW_DATA`=0（有新資料才叫）、`ALWAYS`=1
- `rcl_publish(const rcl_publisher_t *publisher, const void *ros_message, rmw_publisher_allocation_t *allocation)`
- subscription callback：`void (*)(const void *)`；timer callback：`void (*)(rcl_timer_t *, int64_t)`
```c
void sub_cb(const void *msgin) {                       // rclc_subscription_callback_t
    const std_msgs__msg__Int32MultiArray *m = (const std_msgs__msg__Int32MultiArray *)msgin;
    if (m->data.size == 0) return;                     // 太長(>capacity)也會是 0
    RCSOFTCHECK(rcl_publish(&pub, &msg_out, NULL));    // 第 3 參數 NULL
}
    RCCHECK(rclc_executor_add_subscription(&executor, &sub, &msg_in, &sub_cb, ON_NEW_DATA));
```
- `msg` = 收件用的全域訊息變數；`RCSOFTCHECK` = 忽略錯誤的自訂巨集。
- ✗ `rcl_publish(&pub, &msg)` → ✓ `(&pub, &msg, NULL)`；回傳值不接有 warn_unused_result warning
- ✗ callback 寫 `void cb(void *m)` → incompatible pointer warning；✓ `const void *`
前提：`#include <rclc/executor.h>`、`<std_msgs/msg/int32_multi_array.h>`
驗證：pub 到 `/pico0/input` → `/pico0/output` 有回覆。

---

【API卡｜UROS 5/6｜custom transport 與 ping agent】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
- `rmw_ret_t rmw_uros_set_custom_transport(bool framing, void *args, open_custom_func open_cb, close_custom_func close_cb, write_custom_func write_cb, read_custom_func read_cb)`：順序 open、close、write、read
- `rmw_ret_t rmw_uros_ping_agent(const int timeout_ms, const uint8_t attempts)`：agent 在 → `RMW_RET_OK`(0)，不在 → `RMW_RET_ERROR`(1)
官方 `pico_uart_transports.h` 提供四個函式：`pico_serial_transport_open` / `_close` / `_write` / `_read`（直接傳名字，不用自己寫）。
```c
    rmw_uros_set_custom_transport(true, NULL,
        pico_serial_transport_open, pico_serial_transport_close,
        pico_serial_transport_write, pico_serial_transport_read);
    while (rmw_uros_ping_agent(1000, 1) != RMW_RET_OK) { tight_loop_contents(); }
```
- framing = `true`（序列埠要 framing）。open 裡會呼叫 `stdio_init_all()`。
- 順序：set_custom_transport → ping 到 OK → `rclc_support_init`。
- USB 被 agent 佔用 → 不要 printf（會混進封包）。
前提：`#include <rmw_microros/rmw_microros.h>`、`"pico_uart_transports.h"`；`add_executable` 要加 `pico_uart_transport.c`
驗證：agent 顯示 session established。

---

【API卡｜UROS 6/6｜Int32MultiArray 的 sequence 欄位】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
`std_msgs__msg__Int32MultiArray`（`int32_multi_array__struct.h`）：
- `.data`：`rosidl_runtime_c__int32__Sequence` = `{ int32_t *data; size_t size; size_t capacity; }`；size = 有效個數，capacity = buffer 元素數
- `.layout`：`.dim`（同樣 data/size/capacity）、`.data_offset`
```c
#define MAX_LEN 400
std_msgs__msg__Int32MultiArray msg_in, msg_out;
static int32_t in_buf[MAX_LEN], out_buf[MAX_LEN];
    msg_in.data.data = in_buf;   msg_in.data.capacity = MAX_LEN;  msg_in.data.size = 0;
    msg_out.data.data = out_buf; msg_out.data.capacity = MAX_LEN; msg_out.data.size = 0;
    msg_in.layout.dim.data = NULL;  msg_in.layout.dim.capacity = 0;  msg_in.layout.dim.size = 0;
    msg_out.layout.dim.data = NULL; msg_out.layout.dim.capacity = 0; msg_out.layout.dim.size = 0;
    msg_in.layout.data_offset = 0;  msg_out.layout.data_offset = 0;
    msg_out.data.size = n;                             // size ≤ capacity
```
要換：`MAX_LEN` = 最大元素數；`n` = 要發的個數。
- micro-ROS 不 malloc：沒設 `.data/.capacity` → 收不到。
- 收到 > capacity 個 → callback 照叫但 `size`=0。
- ✗ 發佈 `size > capacity` → 越界；✓ 先夾到 capacity
- ✗ `capacity = sizeof(in_buf)` → ✓ `MAX_LEN`（元素數）
- dim capacity = 0 → 電腦端不要填 `layout.dim`。
前提：`#include <std_msgs/msg/int32_multi_array.h>`
驗證：pub `{data: [1,2,3]}` → callback 裡 `size` == 3。

---

【API卡｜HOST-PY 1/4｜rclpy：publisher、subscription、timer、參數】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
來源：repo 範本 `node_template.py`、`serial_bridge.py`、`host_driver.py` 原樣複製（之前在 Jazzy 跑過，這次沒實跑）。
- `self.create_publisher(msg_type, topic, qos)`
- `self.create_subscription(msg_type, topic, callback, qos)`
- `self.create_timer(period_sec, callback)`：秒（float）
- `self.declare_parameter(name, default)`；`self.get_parameter(name).value`
```python
        self.declare_parameter("in_topic", "/number")    # TODO(改這裡) 輸入 topic
        in_topic = self.get_parameter("in_topic").value
        self.pub = self.create_publisher(Int32, out_topic, QOS)
        self.sub = self.create_subscription(Int32, in_topic, self.on_msg, QOS)
            self.timer = self.create_timer(period, self.on_timer)
```
- qos 也可直接寫 `10`；多個 sub 共用 callback：`lambda msg, b=i: self.on_result(b, msg)`（host_driver.py）。
- ✗ `create_subscription(Int32, cb, topic)` → ✓ `(Int32, topic, cb, qos)`
- ✗ `create_timer(100, cb)` 想要 100 ms → ✓ `create_timer(0.1, cb)`
- ✗ `get_parameter(name)` 直接當值 → ✓ `.value`
前提：`import rclpy`、`from rclpy.node import Node`、`from std_msgs.msg import Int32`
驗證：`ros2 topic pub --once /number std_msgs/msg/Int32 "{data: 21}"` → `/double` 得 42。

---

【API卡｜HOST-PY 2/4｜rclpy：QoS 與 init / spin / shutdown】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
來源：repo 範本原樣複製（這次沒實跑）。
```python
from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
QOS = QoSProfile(
    depth=10,
    history=HistoryPolicy.KEEP_LAST,
    reliability=ReliabilityPolicy.RELIABLE,   # TODO(改這裡) 收不到感測器資料時改 BEST_EFFORT
    durability=DurabilityPolicy.VOLATILE,     # TRANSIENT_LOCAL = 晚加入的訂閱者也拿得到最後一筆
)
def main():
    rclpy.init()
    node = Processor()
    try:
        rclpy.spin(node)          # 一直等 callback；沒有 spin 的話 callback 永遠不會被呼叫!
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
```
- 自己控迴圈：`rclpy.spin_once(self, timeout_sec=0.001)`；條件 `rclpy.ok()`；結尾 `rclpy.shutdown()`（host_driver.py）。
- `ReliabilityPolicy.BEST_EFFORT`、`DurabilityPolicy.TRANSIENT_LOCAL`：範本只在註解出現 ⚠️未驗證
- `from rclpy.qos import qos_profile_sensor_data`（BEST_EFFORT、depth 5）⚠️未驗證
- ✗ `QoSProfile(10)` → ✓ `QoSProfile(depth=10)`（關鍵字）
- ✗ 沒 `rclpy.spin` → callback 永遠不跑
前提：`from rclpy.executors import ExternalShutdownException`
驗證：Ctrl+C 結束沒有 traceback。

---

【API卡｜HOST-PY 3/4｜pyserial】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
pyserial 3.5（inspect＋pty 實跑）：
- `serial.Serial(port=None, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=None, ...)`：timeout 單位秒；None = 永遠等
- `ser.read(size=1)` → bytes；逾時回 `b''`（不丟例外）
- `ser.write(data)` → int（寫了幾 byte）
- `ser.in_waiting`：屬性，不加 `()`
- `ser.reset_input_buffer()`：清掉沒讀的舊資料
- `ser.close()`
- `serial.SerialException`：開不了 / 拔線；是 `OSError` 子類
- `serial.tools.list_ports.comports()`：每項有 `.device`、`.description`
```python
ser = serial.Serial(name, 115200, timeout=0.05)   # port, baudrate, timeout=秒
print("read timeout ->", repr(ser.read(4)))         # 沒資料 → b''
print("read(ser.in_waiting or 1) ->", ser.read(ser.in_waiting or 1))
print("write ->", ser.write(b"\x0a\x0d"))           # 回傳寫了幾 byte
ser.reset_input_buffer()
for p in serial.tools.list_ports.comports():
    print(p.device, p.description)
```
要換：`name` = `/dev/ttyACM0` 等。
- ✗ `ser.in_waiting()` → ✓ `ser.in_waiting`
- ✗ `ser.write("abc")`（str）→ ✓ `b"abc"`
- ✗ `timeout=None` → 沒資料就卡死；✓ `timeout=0.05` 自己迴圈
- USB CDC 不看 baudrate。
前提：`import serial`、`import serial.tools.list_ports`
驗證：沒資料時 `read` 回 `b''`。

---

【API卡｜HOST-PY 4/4｜struct 格式字元與 array】
以下是驗證過的參考（照抄，不要憑記憶改名稱、參數順序、數值）。
Python 3.13 實跑：
| 字元 | 意思 | bytes |
|---|---|---|
| `<` / `>` | 小端 / 大端，無對齊（Pico 是小端） | – |
| `B` / `H` / `I` | uint8 / uint16 / uint32 | 1 / 2 / 4 |
| `i` / `f` | int32 / float32 | 4 / 4 |
不寫 `<` = 本機對齊：`calcsize("BI")`=8、`calcsize("<BI")`=5。
```python
print(struct.pack("<I", 1).hex(), struct.pack(">I", 1).hex())
print(struct.pack("<BBH", 0x10, 7, 300).hex())
(v,) = struct.unpack("<I", b"\x2a\x00\x00\x00"); print(v)
print(struct.unpack_from("<H", b"\xaa\x55\x03\x00", 2))
n = 3; print(struct.pack(f"<{n}I", 1, 2, 3).hex())
a = array.array("i", [1, -1, 300])
print(a.itemsize, a.tobytes().hex(), sys.byteorder)
```
輸出：`01000000 00000001`、`10072c01`、`42`、`(3,)`、`010000000200000003000000`、`4 01000000ffffffff2c010000 little`
- `unpack` 永遠回 tuple → ✓ `(v,) = ...`
- ✗ `pack("<B", 256)`、`pack("<I", -1)` → `struct.error`；負數用 `i`
- ✗ `unpack("<I", 2 bytes)` → `struct.error: unpack requires a buffer of 4 bytes`
- `array('i').tobytes()` 用本機序（x86/ARM 都 little）= 小端 int32。
前提：`import struct, array, sys`
驗證：輸出跟上面一樣。
