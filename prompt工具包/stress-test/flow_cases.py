"""flow_cases.py — flow.py 用的假考題（題目原文 + 題目 repo 的檔案 + 操作者拿得到的資料）。

題型照 ../../預製程式碼/預測考題.md 信心最高的幾類；內容是假想的，不是真考題。
relevant：模型要了這些（卡片編號 / 系列 / 資料代號 / 題目段 / 程式）算「要得合理」。
"""
import re

DEFAULT_DATA = {
    "K3": """stages: [build, judge]
build:
  stage: build
  image: registry.exam.local/pico-build:2.2.0
  script:
    - cmake -S . -B build -DPICO_BOARD=pico2 && cmake --build build -j8
judge:
  stage: judge
  rules:
    - if: '$CI_COMMIT_MESSAGE =~ /^Q[1-3]:/'
  script:
    - python3 /judge/run.py --question "${CI_COMMIT_MESSAGE%%:*}" --uf2 build/*.uf2""",
    "K6": """Ubuntu 24.04；cmake 3.28；arm-none-eabi-gcc 13.2.1；PICO_SDK_PATH=/opt/pico-sdk（2.2.0）
/dev/ttyACM0""",
    "S3": """## main...origin/main
 M src/main.c
c0ffee1 (HEAD -> main, tag: start, origin/main) initial""",
    "K5": "（grep TODO/FIXME 沒有結果）",
}


def is_relevant(case, note):
    kind, _, val = note.partition(":")
    if kind in ("seg",):
        return True
    if kind in ("code", "code-by-name", "nofile"):
        return any(f in val for f in case["expect_files"]) or kind.startswith("code")
    for p in case["relevant"]:
        if val.startswith(p):
            return True
    return False


CASES = [
    {
        "id": "serial_batch",
        "main_files": ["host/send.py", "pico/main.c"],
        # 解法：二進位（struct / pack / fread / getchar 讀 4 byte）＋ 一次送很多筆（不要每筆等 ok）
        "solution_checks": [r"struct\.pack|pack_u32|to_bytes|tobytes|array\(|二進位|binary", r"批次|batch|一次送|整批|chunk|CHUNK|分塊"],
        "expect_area": ["E01", "E02"],
        "expect_files": ["send.py", "main.c", "serial_bridge.py", "app_serial.c", "frame.py", "serial_proto"],
        "relevant": ["E01", "E02-01", "E02-03", "E02-04", "F01-00", "F01-01", "C07", "C08", "L09", "A07-03", "A07-04",
                     "A05-02", "Q07", "K2", "K3", "K4", "R1", "S1", "S4", "T6", "T7", "M01"],
        "segments": [
            """第 1 題（30 分）：主機透過 USB 序列埠（/dev/ttyACM0）把 N 個 32 位元無號整數送到 Pico 2，Pico 2 回傳它們的總和（mod 2^32）。
現有程式：host/send.py 每次送一個數字的十進位文字加換行，等 Pico 回 "ok" 再送下一個；最後送 "END"，Pico 回總和。
pico/main.c 用 scanf 逐行讀數字。N = 200000 時要跑 1 分鐘以上。""",
            """要求：
1. 結果必須正確（judge 會比對總和）。
2. 評分依完成時間：10 秒內滿分，超過 30 秒只有正確分 10 分。
3. 可以修改 host/send.py 與 pico/main.c，不可修改 judge/ 資料夾與 CMakeLists.txt 的 target 名稱 q1。
4. 提交：commit message 以 "Q1:" 開頭。""",
        ],
        "files": {
            "host/send.py": """import serial, sys, random
N = int(sys.argv[1]) if len(sys.argv) > 1 else 200000
nums = [random.getrandbits(32) for _ in range(N)]
ser = serial.Serial("/dev/ttyACM0", 115200, timeout=5)
for x in nums:
    ser.write(f"{x}\\n".encode())
    assert ser.readline().strip() == b"ok"
ser.write(b"END\\n")
got = int(ser.readline())
print("pico:", got, "expect:", sum(nums) & 0xFFFFFFFF)
""",
            "pico/main.c": """#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"

int main(void) {
    stdio_init_all();
    uint32_t sum = 0;
    char line[32];
    while (true) {
        if (scanf("%31s", line) != 1) continue;
        if (strcmp(line, "END") == 0) {
            printf("%lu\\n", (unsigned long)sum);
            sum = 0;
            continue;
        }
        sum += (uint32_t)strtoul(line, NULL, 10);
        printf("ok\\n");
    }
}
""",
        },
        "data": {
            "K2": "./CMakeLists.txt\n./host/send.py\n./pico/main.c\n./judge/run.py\n./README.md\n./.gitlab-ci.yml",
            "S1": "N=200000：總時間 71.4 s（每個數字來回約 0.36 ms）",
            "S4": "10 秒內滿分，超過 30 秒只有正確分 10 分（題目第 2 段）",
            "B2": "cmake_minimum_required(VERSION 3.13)\ninclude(pico_sdk_import.cmake)\nproject(q1 C CXX ASM)\npico_sdk_init()\nadd_executable(q1 pico/main.c)\ntarget_link_libraries(q1 pico_stdlib)\npico_enable_stdio_usb(q1 1)\npico_enable_stdio_uart(q1 0)\npico_add_extra_outputs(q1)",
        },
    },
    {
        "id": "dma_copy",
        "main_files": ["pico/copy.c"],
        "solution_checks": [r"write_increment\(\s*&c\s*,\s*true", r"dst\s*,\s*src\s*,\s*N\s*,|count\s*[=＝]\s*N\b|N\s*（筆數）|改成\s*`?N`?", r"dma_channel_unclaim|unclaim"],
        "expect_area": ["E02"],
        "expect_files": ["copy.c", "app_dma.c"],
        "relevant": ["E02-01", "E02-06", "E02-07", "E02-13", "A01", "C01", "L02", "Q09-05", "Q08", "F01-07", "M01",
                     "K2", "K3", "P1", "R1", "B1"],
        "segments": [
            """第 2-3 題（20 分）：pico/copy.c 要把 src 陣列（4096 個 uint32_t）複製到 dst，再印出 dst 的總和。
目前同時有 CPU 迴圈版和一個寫壞的 DMA 版。DMA 版印出的總和不對，而且呼叫第二次之後就 panic（"No DMA channels are available"）。
請修好 DMA 版，讓總和和 CPU 版相同，並且可以重複呼叫 100 次。judge 會讀序列埠上的 "sum=" 那一行。""",
        ],
        "files": {
            "pico/copy.c": """#include <stdio.h>
#include "pico/stdlib.h"
#include "hardware/dma.h"

#define N 4096
static uint32_t src[N], dst[N];

static void copy_cpu(void) { for (int i = 0; i < N; i++) dst[i] = src[i]; }

static void copy_dma(void) {
    int ch = dma_claim_unused_channel(true);
    dma_channel_config c = dma_channel_get_default_config(ch);
    channel_config_set_transfer_data_size(&c, DMA_SIZE_32);
    channel_config_set_read_increment(&c, true);
    channel_config_set_write_increment(&c, false);
    dma_channel_configure(ch, &c, dst, src, N * 4, true);
    dma_channel_wait_for_finish_blocking(ch);
}

int main(void) {
    stdio_init_all();
    for (int i = 0; i < N; i++) src[i] = i * 3 + 1;
    for (int k = 0; k < 100; k++) {
        copy_dma();
        uint32_t s = 0;
        for (int i = 0; i < N; i++) s += dst[i];
        printf("sum=%lu\\n", (unsigned long)s);
    }
    while (1) tight_loop_contents();
}
""",
        },
        "data": {
            "K2": "./CMakeLists.txt\n./pico/copy.c\n./README.md\n./.gitlab-ci.yml",
            "P1": "sum=12288\n\n*** PANIC ***\n\nNo DMA channels are available",
            "R1": "預期 sum=25163776（CPU 版）；實際第一次 sum=12288，第二次之後 panic: No DMA channels are available",
        },
    },
    {
        "id": "ros2_topic",
        "main_files": ["ros2_ws/src/q21/q21/consumer.py", "ros2_ws/src/q21/q21/producer.py"],   # 題目提到的檔都貼
        "solution_checks": [r"[\"']/numbers[\"']", r"BEST_EFFORT|qos_profile_sensor_data|best_effort"],
        "expect_area": ["E01"],
        "expect_files": ["consumer.py", "producer.py", "node_template.py"],
        "relevant": ["E01-01", "E01-07", "E01-08", "E01-10", "L08", "Q04-06", "A07-01", "A07-02", "C10", "Q09-09", "M01",
                     "T1", "T2", "T3", "T4", "T5", "K2", "K3", "K4"],
        "segments": [
            """第 2-1 題（20 分）：ros2_ws/src/q21/q21/producer.py 每 0.1 秒在 /numbers 發布一個 std_msgs/Int32（1, 2, 3, ...）。
consumer.py 應該訂閱它，每收到一個就在 /total 發布目前的累計總和（std_msgs/Int64）。
現在 consumer 啟動後 /total 完全沒有輸出。請找出原因並修好；不可修改 producer.py。
環境：ROS 2 Jazzy，用 `ros2 run q21 producer` 和 `ros2 run q21 consumer` 啟動。""",
        ],
        "files": {
            "ros2_ws/src/q21/q21/producer.py": """import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32

class Producer(Node):
    def __init__(self):
        super().__init__("producer")
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self.pub = self.create_publisher(Int32, "/numbers", qos)
        self.n = 0
        self.create_timer(0.1, self.tick)

    def tick(self):
        self.n += 1
        self.pub.publish(Int32(data=self.n))

def main():
    rclpy.init(); rclpy.spin(Producer())
""",
            "ros2_ws/src/q21/q21/consumer.py": """import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32, Int64

class Consumer(Node):
    def __init__(self):
        super().__init__("consumer")
        self.total = 0
        self.sub = self.create_subscription(Int32, "/number", self.cb, 10)
        self.pub = self.create_publisher(Int64, "/total", 10)

    def cb(self, msg):
        self.total += msg.data
        self.pub.publish(Int64(data=self.total))

def main():
    rclpy.init(); rclpy.spin(Consumer())
""",
        },
        "data": {
            "K2": "./ros2_ws/src/q21/package.xml\n./ros2_ws/src/q21/setup.py\n./ros2_ws/src/q21/q21/producer.py\n./ros2_ws/src/q21/q21/consumer.py\n./README.md\n./.gitlab-ci.yml",
            "T1": "/consumer\n/producer",
            "T3": "（ros2 topic info -v /numbers）\nType: std_msgs/msg/Int32\nPublisher count: 1\n  Node name: producer\n  QoS profile:\n    Reliability: BEST_EFFORT\n    Durability: VOLATILE\nSubscription count: 0",
            "T2": "/consumer\n  Subscribers:\n    /number: std_msgs/msg/Int32\n  Publishers:\n    /total: std_msgs/msg/Int64",
        },
        "commands": {"ros2 topic list": "/number\n/numbers\n/parameter_events\n/rosout\n/total"},
    },
    {
        "id": "bits_fields",
        "main_files": ["src/decode.c"],
        "solution_checks": [r"buf\[3\]\s*<<\s*24|buf\[0\]\s*\|\s*\(?\s*\(?uint32_t\)?\s*buf\[1\]\s*<<\s*8|memcpy|le32|little", r"0x800|sign_extend|<<\s*20\s*\)\s*>>\s*20|int16_t\)\s*\(?\s*\(?w\s*<<|-\s*0x1000|- 4096|\(int32_t\)\s*\(w\s*<<\s*20\)"],
        "expect_area": ["E05"],
        "expect_files": ["decode.c", "packet_fields.c", "bitops.h"],
        "relevant": ["E05", "C12-05", "C12-06", "Q09-01", "Q09-02", "L06-08", "M01", "K2", "K3", "R1", "B1"],
        "segments": [
            """第 2-2 題（20 分）：一個 32 位元的感測器封包標頭（little-endian 存放）欄位如下（bit 31 是最高位）：
| 欄位 | 位元 | 說明 |
| ver | 31..29 | 版本 |
| type | 28..24 | 類型 |
| len | 23..12 | payload 長度（byte） |
| temp | 11..0 | 溫度，12 位元有號數（二補數），單位 0.1°C |
請完成 src/decode.c 的 decode_header()，把 4 個 byte 的 buf 解成 struct hdr。judge 會用 1000 組隨機資料比對。""",
        ],
        "files": {
            "src/decode.c": """#include <stdint.h>
#include "decode.h"

/* buf[0..3]：little-endian 的 32 位元標頭 */
void decode_header(const uint8_t *buf, struct hdr *h) {
    uint32_t w = buf[0] << 24 | buf[1] << 16 | buf[2] << 8 | buf[3];
    h->ver  = w >> 29;
    h->type = (w >> 24) & 0x1F;
    h->len  = (w >> 12) & 0xFFF;
    h->temp = w & 0xFFF;          /* TODO: 有號數 */
}
""",
            "src/decode.h": "#include <stdint.h>\nstruct hdr { uint8_t ver, type; uint16_t len; int16_t temp; };\nvoid decode_header(const uint8_t *buf, struct hdr *h);",
        },
        "data": {
            "K2": "./src/decode.c\n./src/decode.h\n./test/test_decode.c\n./Makefile\n./.gitlab-ci.yml",
            "R1": "輸入 buf = 38 ff 05 5a\n預期 ver=2 type=26 len=95 temp=-200（-20.0°C）\n實際 ver=1 type=24 len=4080 temp=1370",
        },
    },
    {
        "id": "multicore_race",
        "main_files": ["pico/counter.c"],
        # 正確修法一定要有同步（鎖或 atomic）；只加 volatile 不算
        "solution_checks": [r"spin_lock_blocking|critical_section_enter_blocking|mutex_enter_blocking|__atomic|atomic_fetch_add"],
        "expect_area": ["E02"],
        "expect_files": ["counter.c", "app_multicore.c"],
        "relevant": ["E02-01", "E02-05", "A04", "C05", "L05", "Q09-06", "F01-04", "F01-05", "Q08", "M01",
                     "K2", "K3", "P1", "R1", "S1"],
        "segments": [
            """第 2-3 題（20 分）：pico/counter.c 讓 core0 與 core1 各處理 50000 筆資料，每筆呼叫 work(i)（約 20 µs），
再把結果加到共用的 total。目前 total 每次跑都不一樣（應該是 5000050000）。
請修好，讓 total 每次都正確；評分另外看總時間，越短越好（單核約 2 秒）。""",
        ],
        "files": {
            "pico/counter.c": """#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"

#define N 50000
static volatile uint64_t total = 0;

static uint32_t work(uint32_t i) { busy_wait_us(20); return i; }

static void run(uint32_t start) {
    for (uint32_t i = start; i < start + N; i++) {
        total += work(i);
    }
}

static void core1_main(void) { run(N + 1); multicore_fifo_push_blocking(1); }

int main(void) {
    stdio_init_all();
    uint64_t t0 = time_us_64();
    multicore_launch_core1(core1_main);
    run(1);
    multicore_fifo_pop_blocking();
    printf("total=%llu time=%llu us\\n", total, time_us_64() - t0);
    while (1) tight_loop_contents();
}
""",
        },
        "data": {
            "K2": "./CMakeLists.txt\n./pico/counter.c\n./README.md\n./.gitlab-ci.yml",
            "P1": "total=4999481023 time=1003512 us",
            "R1": "預期 total=5000050000；實際 4999481023、4999877310、4998990142（每次不同）",
            "S1": "total 錯的版本 time=1003512 us（約 1.0 s）",
        },
    },
]
CASE_BY_ID = {c["id"]: c for c in CASES}
