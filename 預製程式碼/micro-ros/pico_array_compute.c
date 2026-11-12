// pico_array_compute.c — 收 Int32MultiArray → compute() → 發 Int32MultiArray
// ⚠ 未經編譯驗證（not compile-verified）；API 已對過 jazzy libmicroros/include 標頭檔。
//   考場請先 build + 用 ros2 topic pub 測一次。
// Topic（有 namespace）：訂閱 /<BOARD_NS>/input，發佈 /<BOARD_NS>/output
// 協定（跟 host_driver.py 約好）：data[0] = job_id（區塊編號），data[1..] = 資料
//   回傳也是 data[0] = job_id，host 才能「照順序合併」多塊板子的結果。
// 簡化：只等一次 agent（沒有重連）。要重連請抄 pico_pingpong.c 的狀態機。
#include <string.h>
#include <rcl/rcl.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>
#include <rmw_microros/rmw_microros.h>
#include <std_msgs/msg/int32_multi_array.h>
#include "pico/stdlib.h"
#include "pico_uart_transports.h"

#define BOARD_NS "pico0"   // TODO(改這裡) 每塊板子不同：pico0 / pico1 / pico2 ...（燒錄前改！）
#define LED_PIN 25
// ---- 最大長度（重要！數字來自 libmicroros/include 的 config.h，見 README §4）----
// 預編函式庫：custom transport MTU = 512 B、RMW_UXRCE_STREAM_HISTORY = 4
//   reliable（_default）  ：一則 ≤ 512×4 − 12 ≈ 2036 B → 扣掉 ~16 B 訊息 overhead ≈ 505 個 int32
//   best_effort           ：一則 ≤ 512 − 12 = 500 B → ≈ 121 個 int32
// 兩種超過的情況（行為不同！）：
//   (a) 超過傳輸上限 → 板子收不到（callback 不會被叫）；板子發太大 → rcl_publish 回傳錯誤
//   (b) 沒超過傳輸上限、但元素數 > MAX_LEN（capacity）→ callback「會被叫」但 data.size = 0
//       （rosidl_typesupport_microxrcedds 的反序列化行為）→ 下面 sub_cb 會直接忽略
#define MAX_LEN 400        // TODO(改這裡) 含 data[0] 的 job_id；保守取 ≤ 450

// 初始化失敗 → LED 快閃（不能 printf，只能看 LED）
static void error_loop(void) {
    while (true) { gpio_put(LED_PIN, 1); sleep_ms(100); gpio_put(LED_PIN, 0); sleep_ms(100); }
}
#define RCCHECK(fn) { rcl_ret_t rc_ = (fn); if (rc_ != RCL_RET_OK) error_loop(); }
#define RCSOFTCHECK(fn) { rcl_ret_t rc_ = (fn); (void)rc_; }

rclc_support_t support;
rcl_node_t node;
rcl_allocator_t allocator;
rclc_executor_t executor;
rcl_publisher_t pub;
rcl_subscription_t sub;
std_msgs__msg__Int32MultiArray msg_in, msg_out;
static int32_t in_buf[MAX_LEN], out_buf[MAX_LEN];   // 靜態 buffer（主 stack 只有 2 KB，不能放 stack）

// TODO(改這裡) 你的運算：輸入 in[0..n-1]，輸出寫到 out，回傳輸出長度（≤ cap）
static size_t compute(const int32_t *in, size_t n, int32_t *out, size_t cap) {
    // 範例：插入排序（題目可能是 sort / CRC32 / SHA / NN 推論…）
    if (n > cap) n = cap;
    for (size_t i = 0; i < n; i++) {
        int32_t v = in[i]; size_t j = i;
        while (j > 0 && out[j - 1] > v) { out[j] = out[j - 1]; j--; }
        out[j] = v;
    }
    return n;
}

void sub_cb(const void *msgin) {
    // msgin 就是 &msg_in（executor 把資料反序列化進你給的 msg_in / in_buf）
    const std_msgs__msg__Int32MultiArray *m = (const std_msgs__msg__Int32MultiArray *)msgin;
    if (m->data.size < 1) return;                       // 至少要有 job_id（太長也會變 0）
    int32_t job_id = m->data.data[0];
    size_t n = m->data.size - 1;
    size_t out_n = compute(&m->data.data[1], n, &out_buf[1], MAX_LEN - 1);
    // capacity 檢查：size 絕對不能 > capacity，不然序列化會越界
    if (out_n + 1 > msg_out.data.capacity) out_n = msg_out.data.capacity - 1;
    out_buf[0] = job_id;
    msg_out.data.size = out_n + 1;
    // reliable 發佈會「等 agent ACK」才回來（rmw_publish.c：uxr_run_session_until_confirm_delivery）
    RCSOFTCHECK(rcl_publish(&pub, &msg_out, NULL));
}

// 手動配置 sequence 記憶體：.data 指向 buffer、.capacity = 大小、.size = 目前用量
// 欄位名稱（int32_multi_array__struct.h）：layout.dim(.data/.size/.capacity)、layout.data_offset、
//   data(.data/.size/.capacity)，data 型別 = rosidl_runtime_c__int32__Sequence
static void alloc_msgs(void) {
    msg_in.data.data = in_buf;   msg_in.data.capacity = MAX_LEN;  msg_in.data.size = 0;
    msg_out.data.data = out_buf; msg_out.data.capacity = MAX_LEN; msg_out.data.size = 0;
    // layout.dim 是「巢狀型別」的 sequence：收到 dim 個數 > capacity 時反序列化直接失敗 → 整則丟掉
    // 這裡給 0 容量 → host 端「不要填 layout.dim」，否則收不到
    msg_in.layout.dim.data = NULL;  msg_in.layout.dim.capacity = 0;  msg_in.layout.dim.size = 0;
    msg_out.layout.dim.data = NULL; msg_out.layout.dim.capacity = 0; msg_out.layout.dim.size = 0;
    msg_in.layout.data_offset = 0;  msg_out.layout.data_offset = 0;
    // 另一種寫法（自動配置，用 malloc；含字串/巢狀）：
    //   #include <micro_ros_utilities/type_utilities.h>
    //   micro_ros_utilities_memory_conf_t conf = micro_ros_utilities_memory_conf_default;
    //   conf.max_basic_type_sequence_capacity = MAX_LEN;  // int32 sequence
    //   conf.max_ros2_type_sequence_capacity = 1;         // layout.dim
    //   conf.max_string_capacity = 16;                    // dim.label
    //   micro_ros_utilities_create_message_memory(
    //       ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray), &msg_in, conf);
}

int main(void) {
    rmw_uros_set_custom_transport(true, NULL,
        pico_serial_transport_open, pico_serial_transport_close,
        pico_serial_transport_write, pico_serial_transport_read);
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);
    alloc_msgs();

    // 等 agent：每次最多等 1 秒，一直試到連上為止（所以先開板子或先開 agent 都可以）
    while (rmw_uros_ping_agent(1000, 1) != RMW_RET_OK) { tight_loop_contents(); }

    allocator = rcl_get_default_allocator();
    RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
    RCCHECK(rclc_node_init_default(&node, "compute_node", BOARD_NS, &support)); // namespace = BOARD_NS
    const rosidl_message_type_support_t *ts =
        ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Int32MultiArray);
    // 相對名稱 "input" + namespace "pico0" → /pico0/input（rcl 會自動補開頭的 "/"）
    // 大訊息用 reliable（_default）；小又要快可改 _best_effort（host 端 QoS 也要配合）
    RCCHECK(rclc_subscription_init_default(&sub, &node, ts, "input"));
    RCCHECK(rclc_publisher_init_default(&pub, &node, ts, "output"));

    executor = rclc_executor_get_zero_initialized_executor();
    RCCHECK(rclc_executor_init(&executor, &support.context, 1, &allocator));  // 1 個 subscription
    RCCHECK(rclc_executor_add_subscription(&executor, &sub, &msg_in, &sub_cb, ON_NEW_DATA));

    gpio_put(LED_PIN, 1);                                   // LED 恆亮 = 全部建立成功
    while (true) {
        rclc_executor_spin_some(&executor, RCL_MS_TO_NS(1));   // timeout 小 → 反應快
    }
    return 0;
}
