// pico_dualcore_micro_ros.c — 雙核心：core0 跑 micro-ROS，core1 幫忙算一半
// ✅ 編譯、連結通過（pico-sdk 2.2.0、PICO_BOARD=pico2、官方 jazzy libmicroros.a、arm-none-eabi-gcc 13.2）；沒燒錄、沒在板子上跑過。
//   CMake 要多連 pico_multicore（見 CMakeLists.txt）。
// 規則：所有 rcl/rclc/rmw 呼叫「只能在 core0」！core1 只做純運算，不碰 micro-ROS、不 printf。
//   （libmicroros 編譯時 RCUTILS_NO_THREAD_SUPPORT=ON、沒開 UCLIENT_PROFILE_MULTITHREAD → 非執行緒安全）
// 流程：core0 收到陣列 → 切兩半 → 後半丟給 core1（queue）→ core0 自己算前半
//       → 等 core1 回報完成（queue）→ 合併 → publish
// 協定同 pico_array_compute.c：data[0] = job_id，data[1..] = 資料
// pico-sdk 注意事項（已對 pico-sdk 2.2.0 原始碼）：
//   - pico/util/queue.h 是 SDK 官方的跨核心安全佇列（內部用 spinlock，含記憶體屏障）→ OK
//   - core1 stack 預設 PICO_CORE1_STACK_SIZE = 0x800（2 KB）→ core1 裡不要開大陣列
//   - 只有「寫 flash」才需要 multicore_lockout / flash_safe_execute；本程式不寫 flash
//   - USB（TinyUSB）中斷在 core0 跑；core1 長時間運算不影響 USB
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <rmw_microros/rmw_microros.h>
#include <std_msgs/msg/int32_multi_array.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "pico/util/queue.h"
#include "pico_uart_transports.h"

#define BOARD_NS "pico0"   // TODO(改這裡) 每塊板子不同
#define MAX_LEN 400        // TODO(改這裡) 上限見 pico_array_compute.c 的說明
#define LED_PIN 25

static void error_loop(void) {   // 初始化失敗 → LED 快閃
    while (true) { gpio_put(LED_PIN, 1); sleep_ms(100); gpio_put(LED_PIN, 0); sleep_ms(100); }
}
#define RCCHECK(fn) { rcl_ret_t rc_ = (fn); if (rc_ != RCL_RET_OK) error_loop(); }
#define RCSOFTCHECK(fn) { rcl_ret_t rc_ = (fn); (void)rc_; }

typedef struct { uint32_t lo, hi; } task_t;   // 給 core1 的工作：處理 [lo, hi)
queue_t q_task;   // core0 → core1
queue_t q_done;   // core1 → core0（內容是做完的 hi，當「完成」訊號）

static int32_t in_buf[MAX_LEN], out_buf[MAX_LEN];   // 兩顆核心共用（SRAM 共享）
rclc_support_t support; rcl_node_t node; rcl_allocator_t allocator;
rclc_executor_t executor; rcl_publisher_t pub; rcl_subscription_t sub;
std_msgs__msg__Int32MultiArray msg_in, msg_out;

// TODO(改這裡) 純運算：處理 in[lo..hi) 寫到 out[lo..hi)。兩核心都會呼叫，不能用全域暫存變數！
static void compute_range(const int32_t *in, int32_t *out, uint32_t lo, uint32_t hi) {
    for (uint32_t i = lo; i < hi; i++) out[i] = in[i] * in[i];   // 範例：平方（逐元素，好切）
}
// 若題目是「排序」：兩核各排一半 → core0 最後 merge 兩段（要多一個暫存陣列）
// 若題目是「加總 / CRC」：各算部分結果 → 用 q_done 傳回部分結果再合併

static void core1_main(void) {
    task_t t;
    while (true) {
        queue_remove_blocking(&q_task, &t);          // 等工作（沒有就睡著等）
        compute_range(in_buf, out_buf, t.lo, t.hi);
        queue_add_blocking(&q_done, &t.hi);          // 回報完成
    }
}

void sub_cb(const void *msgin) {
    const std_msgs__msg__Int32MultiArray *m = (const std_msgs__msg__Int32MultiArray *)msgin;
    if (m->data.size < 1) return;                    // 空的或太長（> MAX_LEN 時 size 會是 0）
    uint32_t n = m->data.size - 1;                   // 去掉 job_id 後的資料個數
    uint32_t mid = 1 + n / 2;
    // msg_in.data.data 就是 in_buf，所以直接用索引；資料在 [1, 1+n)（index 0 是 job_id）
    // executor 在這個 callback 裡等 core1 做完才會收下一則 → in_buf 不會被中途覆寫
    task_t t = { .lo = mid, .hi = 1 + n };
    queue_add_blocking(&q_task, &t);                 // 後半 [mid, 1+n) 給 core1
    compute_range(in_buf, out_buf, 1, mid);          // 前半 [1, mid) core0 自己算
    uint32_t done;
    queue_remove_blocking(&q_done, &done);           // 等 core1 做完
    out_buf[0] = m->data.data[0];                    // job_id 原樣帶回
    msg_out.data.size = n + 1;                       // size ≤ capacity（MAX_LEN）
    RCSOFTCHECK(rcl_publish(&pub, &msg_out, NULL));
}

int main(void) {
    rmw_uros_set_custom_transport(true, NULL,
        pico_serial_transport_open, pico_serial_transport_close,
        pico_serial_transport_write, pico_serial_transport_read);
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    // queue_init(佇列, 每個元素大小, 元素個數)
    queue_init(&q_task, sizeof(task_t), 4);
    queue_init(&q_done, sizeof(uint32_t), 4);
    multicore_launch_core1(core1_main);              // 啟動 core1（queue 要先 init 好）

    // 手動配置 sequence（in_buf 給收、out_buf 給發）
    msg_in.data.data = in_buf;   msg_in.data.capacity = MAX_LEN;  msg_in.data.size = 0;
    msg_out.data.data = out_buf; msg_out.data.capacity = MAX_LEN; msg_out.data.size = 0;
    msg_in.layout.dim.data = NULL;  msg_in.layout.dim.capacity = 0;  msg_in.layout.dim.size = 0;
    msg_out.layout.dim.data = NULL; msg_out.layout.dim.capacity = 0; msg_out.layout.dim.size = 0;
    msg_in.layout.data_offset = 0;  msg_out.layout.data_offset = 0;

    while (rmw_uros_ping_agent(1000, 1) != RMW_RET_OK) { tight_loop_contents(); }

    allocator = rcl_get_default_allocator();
    RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
    RCCHECK(rclc_node_init_default(&node, "dual_node", BOARD_NS, &support));
    const rosidl_message_type_support_t *ts =
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray);
    RCCHECK(rclc_subscription_init_default(&sub, &node, ts, "input"));    // /pico0/input
    RCCHECK(rclc_publisher_init_default(&pub, &node, ts, "output"));      // /pico0/output
    executor = rclc_executor_get_zero_initialized_executor();
    RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));
    RCCHECK(rclc_executor_add_subscription(&executor, &sub, &msg_in, &sub_cb, ON_NEW_DATA));

    gpio_put(LED_PIN, 1);
    while (true) rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));
    return 0;
}
// 什麼時候雙核心才有用？運算時間 >> 傳輸時間時。若瓶頸在 USB 傳輸，先優化傳輸（README）。
