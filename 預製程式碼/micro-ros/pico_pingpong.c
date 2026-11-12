// pico_pingpong.c — micro-ROS Ping-Pong（Pico / Pico 2 + pico-sdk）
// ✅ 編譯、連結通過（pico-sdk 2.2.0、PICO_BOARD=pico2、官方 jazzy libmicroros.a、arm-none-eabi-gcc 13.2）；沒燒錄、沒在板子上跑過。考場請先 build。
// 功能：timer 每 2 秒發 /microROS/ping；收到別人的 ping 就回 /microROS/pong；
//       收到自己 ping 的 pong 就計數。含 agent 斷線重連狀態機（同官方 reconnection_example）。
// 需搭配：pico_uart_transport.c + pico_uart_transports.h（官方 repo 內）
// 測試（電腦端）：
//   ros2 topic echo /microROS/ping
//   ros2 topic pub --once /microROS/ping std_msgs/msg/Header "{frame_id: 'host'}"
//   ros2 topic echo /microROS/pong
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <rcl/rcl.h>
#include <rcl/error_handling.h>
#include <rclc/rclc.h>
#include <rclc/executor.h>               // rclc.h 沒有 include executor.h，要自己加
#include <rmw_microros/rmw_microros.h>
#include <std_msgs/msg/header.h>
#include "pico/stdlib.h"
#include "pico_uart_transports.h"

#define LED_PIN 25            // TODO(改這裡) Pico / Pico 2 板載 LED = GP25（Pico W / 2 W 不是！）
#define STR_CAP 50            // frame_id buffer 大小（含結尾 '\0' → 最多 49 字元）
#define PING_PERIOD_MS 2000   // TODO(改這裡) ping 週期

// RCCHECK / RCSOFTCHECK 要自己寫（rclc.h 沒定義）。RCCHECK：出錯回傳 false → 狀態機去重連
#define RCCHECK(fn) { rcl_ret_t rc_ = (fn); if (rc_ != RCL_RET_OK) { return false; } }
// RCSOFTCHECK：忽略錯誤（rcl_* 有 warn_unused_result，用變數接住消除警告）
#define RCSOFTCHECK(fn) { rcl_ret_t rc_ = (fn); (void)rc_; }
// 每隔 MS 毫秒才執行一次 X（= 官方 EXECUTE_EVERY_N_MS，官方用 uxr_millis()）
#define EVERY_N_MS(MS, X) do { static int64_t t_ = -1; int64_t now_ = to_ms_since_boot(get_absolute_time()); \
    if (t_ == -1) t_ = now_; if (now_ - t_ > (MS)) { X; t_ = now_; } } while (0)

// ---- 全域物件（不要放 stack：Pico 主 stack 預設只有 2 KB，PICO_STACK_SIZE=0x800）----
rclc_support_t support;
rcl_node_t node;
rcl_allocator_t allocator;
rclc_executor_t executor;
rcl_timer_t timer;
rcl_publisher_t ping_pub, pong_pub;
rcl_subscription_t ping_sub, pong_sub;

// Header 內有字串 frame_id（rosidl_runtime_c__String：data/size/capacity）
// micro-ROS 收訊息時是「反序列化進你給的記憶體」，不會幫你 malloc → 必須先給 .data/.capacity
std_msgs__msg__Header out_ping, in_ping, in_pong;
char out_buf[STR_CAP], in_ping_buf[STR_CAP], in_pong_buf[STR_CAP];
int device_id, pong_count;

enum { WAITING_AGENT, AGENT_AVAILABLE, AGENT_CONNECTED, AGENT_DISCONNECTED } state;

// 簽名必須是 rcl_timer_callback_t：void (*)(rcl_timer_t *, int64_t)
void ping_timer_cb(rcl_timer_t *t, int64_t last_call_time) {
    (void)last_call_time;
    if (t == NULL) return;
    // frame_id = "亂數_裝置ID"，用來辨識是誰發的
    snprintf(out_ping.frame_id.data, STR_CAP, "%d_%d", rand(), device_id);
    out_ping.frame_id.size = strlen(out_ping.frame_id.data);   // size 要自己設（不含 '\0'）
    int64_t ms = rmw_uros_epoch_millis();   // 有 sync_session 成功才是真實時間
    out_ping.stamp.sec = (int32_t)(ms / 1000);
    out_ping.stamp.nanosec = (uint32_t)((ms % 1000) * 1000000);
    pong_count = 0;
    RCSOFTCHECK(rcl_publish(&ping_pub, &out_ping, NULL));
}

// 字串太長（> capacity）時，typesupport 會把 size 設 0、資料跳過，callback 照樣被叫
// → 先檢查 size，避免拿到舊的 buffer 內容誤判
void ping_sub_cb(const void *msgin) {           // 收到 ping
    const std_msgs__msg__Header *m = (const std_msgs__msg__Header *)msgin;
    if (m->frame_id.size == 0) return;
    if (strcmp(out_ping.frame_id.data, m->frame_id.data) != 0)  // 不回自己的 ping
        RCSOFTCHECK(rcl_publish(&pong_pub, m, NULL));           // 原封不動回 pong
}

void pong_sub_cb(const void *msgin) {           // 收到 pong
    const std_msgs__msg__Header *m = (const std_msgs__msg__Header *)msgin;
    if (m->frame_id.size == 0) return;
    if (strcmp(out_ping.frame_id.data, m->frame_id.data) == 0) pong_count++;
}

bool create_entities(void) {
    allocator = rcl_get_default_allocator();
    RCCHECK(rclc_support_init(&support, 0, NULL, &allocator));
    // TODO(改這裡) 多塊板子時 node 名稱/namespace 要不同，例如 "pico0"
    RCCHECK(rclc_node_init_default(&node, "pingpong_node", "", &support));
    const rosidl_message_type_support_t *ts = ROSIDL_GET_MSG_TYPE_SUPPORT(std_msgs, msg, Header);
    // QoS 照官方 freertos_apps ping_pong：ping reliable 發，其餘 best_effort（BE 訂閱可收 reliable 發佈）
    RCCHECK(rclc_publisher_init_default(&ping_pub, &node, ts, "/microROS/ping"));
    RCCHECK(rclc_publisher_init_best_effort(&pong_pub, &node, ts, "/microROS/pong"));
    RCCHECK(rclc_subscription_init_best_effort(&ping_sub, &node, ts, "/microROS/ping"));
    RCCHECK(rclc_subscription_init_best_effort(&pong_sub, &node, ts, "/microROS/pong"));
    // jazzy：rclc_timer_init_default 已 deprecated（官方 pico 範例還在用，只是警告）→ 用 ..._default2
    RCCHECK(rclc_timer_init_default2(&timer, &support, RCL_MS_TO_NS(PING_PERIOD_MS),
                                     ping_timer_cb, true));
    // handle 數 = timer 數 + subscription 數（這裡 1 + 2 = 3）。數錯 → add 會失敗！
    executor = rclc_executor_get_zero_initialized_executor();
    RCCHECK(rclc_executor_init(&executor, &support.context, 3, &allocator));
    RCCHECK(rclc_executor_add_timer(&executor, &timer));
    RCCHECK(rclc_executor_add_subscription(&executor, &ping_sub, &in_ping, &ping_sub_cb, ON_NEW_DATA));
    RCCHECK(rclc_executor_add_subscription(&executor, &pong_sub, &in_pong, &pong_sub_cb, ON_NEW_DATA));
    (void)rmw_uros_sync_session(1000);   // 跟 agent 對時（可選，失敗也沒關係）
    return true;
}

void destroy_entities(void) {
    // agent 已經不在了 → 把 destroy 的等待時間設 0，避免卡很久（同官方 reconnection 範例）
    rmw_context_t *rmw_ctx = rcl_context_get_rmw_context(&support.context);
    (void)rmw_uros_set_context_entity_destroy_session_timeout(rmw_ctx, 0);
    RCSOFTCHECK(rcl_publisher_fini(&ping_pub, &node));
    RCSOFTCHECK(rcl_publisher_fini(&pong_pub, &node));
    RCSOFTCHECK(rcl_subscription_fini(&ping_sub, &node));
    RCSOFTCHECK(rcl_subscription_fini(&pong_sub, &node));
    RCSOFTCHECK(rcl_timer_fini(&timer));
    RCSOFTCHECK(rclc_executor_fini(&executor));
    RCSOFTCHECK(rcl_node_fini(&node));
    RCSOFTCHECK(rclc_support_fini(&support));
}

int main(void) {
    // 1) 告訴 micro-ROS 用 USB 序列埠傳輸（函式在 pico_uart_transport.c；open 裡會呼叫 stdio_init_all）
    rmw_uros_set_custom_transport(true, NULL,
        pico_serial_transport_open, pico_serial_transport_close,
        pico_serial_transport_write, pico_serial_transport_read);
    gpio_init(LED_PIN);
    gpio_set_dir(LED_PIN, GPIO_OUT);

    // 2) 字串 buffer 綁到訊息上（只做一次，重連也不用重做）
    out_ping.frame_id.data = out_buf;    out_ping.frame_id.capacity = STR_CAP; out_ping.frame_id.size = 0;
    in_ping.frame_id.data = in_ping_buf; in_ping.frame_id.capacity = STR_CAP;  in_ping.frame_id.size = 0;
    in_pong.frame_id.data = in_pong_buf; in_pong.frame_id.capacity = STR_CAP;  in_pong.frame_id.size = 0;
    device_id = (int)(time_us_64() & 0x7fff);   // 簡單當 ID 用（開機時間 → 每塊板子不太一樣）
    srand(device_id);

    // 3) 重連狀態機：等 agent → 建立 → 連線中 spin → 斷線就拆掉重來
    // 注意：USB 序列埠被 agent 佔用，printf 的字你看不到，還會混進封包串流 → 不要 printf。
    state = WAITING_AGENT;
    while (true) {
        switch (state) {
        case WAITING_AGENT:
            EVERY_N_MS(500, state = (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) ? AGENT_AVAILABLE : WAITING_AGENT);
            break;
        case AGENT_AVAILABLE:
            state = create_entities() ? AGENT_CONNECTED : WAITING_AGENT;
            if (state == WAITING_AGENT) destroy_entities();
            break;
        case AGENT_CONNECTED:
            EVERY_N_MS(200, state = (rmw_uros_ping_agent(100, 1) == RMW_RET_OK) ? AGENT_CONNECTED : AGENT_DISCONNECTED);
            if (state == AGENT_CONNECTED) rclc_executor_spin_some(&executor, RCL_MS_TO_NS(10));
            break;
        case AGENT_DISCONNECTED:
            destroy_entities();
            state = WAITING_AGENT;
            break;
        }
        gpio_put(LED_PIN, state == AGENT_CONNECTED);   // LED 亮 = 已連上 agent
    }
    return 0;
}
