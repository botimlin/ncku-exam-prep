#!/usr/bin/env python3
# host_driver.py — 電腦端 rclpy 節點：把大陣列切塊，分給 N 塊 Pico 算，收回後照順序合併並計時
# 搭配板子程式：pico_array_compute.c / pico_dualcore_micro_ros.c
# 協定：Int32MultiArray，data[0] = job_id（第幾塊），data[1:] = 資料；回傳格式一樣。
#
# 為什麼每塊板子要不同 namespace？
#   每塊板子的 node 都訂閱相對名稱 "input"。namespace 設 pico0 → 實際 topic 是 /pico0/input，
#   設 pico1 → /pico1/input。這樣 host 才能「指定」資料送給哪一塊。
#   如果大家都用同一個 /input，每塊板子都會收到全部資料（重複算，沒有加速）。
#
# 執行：source /opt/ros/jazzy/setup.bash && python3 host_driver.py
# （每塊板子都要有自己的 agent 在跑，見 agent_cheatsheet.md）
import time
import heapq
import collections
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from std_msgs.msg import Int32MultiArray

N_BOARDS = 2          # TODO(改這裡) 板子數量（namespace 必須是 pico0 .. pico{N-1}）
CHUNK = 300           # TODO(改這裡) 每塊資料個數；+1(job_id) 要 ≤ 板子的 MAX_LEN（預設 400）
                      # 且 reliable 傳輸上限 ≈ 505 個 int32（MTU 512 × history 4，見 README §4）
MERGE = "sorted"      # TODO(改這裡) "concat"：依 job_id 接起來；"sorted"：各塊已排序 → k-way merge
# 範例對應：pico_array_compute.c（排序）→ "sorted"；pico_dualcore_micro_ros.c（平方）→ "concat"
# 預設 "sorted" = 配 CMakeLists.txt 預設的 APP_SRC（pico_array_compute.c）。換板子程式時兩邊一起改，否則 correct=False
TIMEOUT_S = 10.0
RESEND_S = 1.0        # TODO(改這裡) 一塊送出後幾秒沒回就重送（回覆遺失時不用等到 TIMEOUT_S）


def make_data():
    # TODO(改這裡) 題目給的輸入（例如讀檔）
    import random
    random.seed(0)
    return [random.randint(-1000, 1000) for _ in range(3000)]


def host_compute(data):
    # TODO(改這裡) 用來對答案的「電腦端正確版本」
    return [x * x for x in data] if MERGE == "concat" else sorted(data)


class Driver(Node):
    def __init__(self):
        super().__init__('host_driver')
        # 要跟板子端 QoS 一致：板子用 rclc_*_init_default → RELIABLE（rmw_qos_profile_default）
        # 板子若改 _best_effort：這裡也要改 BEST_EFFORT（reliable 訂閱收不到 best_effort 發佈）
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        self.pubs, self.results, self.busy = [], {}, [False] * N_BOARDS
        self.job_of = [None] * N_BOARDS   # 每塊板子手上那一塊：(job_id, 送出時間)
        for i in range(N_BOARDS):
            self.pubs.append(self.create_publisher(Int32MultiArray, f'/pico{i}/input', qos))
            # lambda 預設參數 b=i：記住是哪塊板子回的（常見 bug：直接用 i 會全部變最後一個）
            self.create_subscription(Int32MultiArray, f'/pico{i}/output',
                                     lambda msg, b=i: self.on_result(b, msg), qos)

    def on_result(self, board, msg):
        if len(msg.data) < 1:
            return
        job_id = msg.data[0]               # msg.data 是 array('i')，可直接索引/切片
        self.results[job_id] = list(msg.data[1:])
        if self.job_of[board] and self.job_of[board][0] == job_id:   # 回的是手上那一塊才算空出來
            self.busy[board], self.job_of[board] = False, None       # （重送後才到的舊回覆不算）

    def send(self, board, job_id, chunk):
        msg = Int32MultiArray()           # 不要填 layout.dim！板子端 dim capacity = 0
        msg.data = [job_id] + chunk       # 給 list 即可，rclpy 會轉成 array('i')
        self.pubs[board].publish(msg)
        self.busy[board] = True
        self.job_of[board] = (job_id, time.perf_counter())

    def wait_boards(self):
        # 等每塊板子的 subscriber 和 publisher 都出現（agent 連上 + 板子建立好 node）
        # 只等 input 不夠：output 還沒配對好時板子回的第一則會掉（volatile QoS 不補發）
        def ready(i):
            return (self.pubs[i].get_subscription_count() > 0 and
                    self.count_publishers(f'/pico{i}/output') > 0)
        while rclpy.ok() and not all(ready(i) for i in range(N_BOARDS)):
            self.get_logger().info('等板子上線中…（ros2 topic list 看看）')
            rclpy.spin_once(self, timeout_sec=0.5)

    def run(self, data):
        chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)]
        todo = collections.deque(range(len(chunks)))   # 還沒送出（或要重送）的 job_id
        t0 = time.perf_counter()
        deadline = t0 + TIMEOUT_S
        # 流量控制：每塊板子一次只給一塊（等它回完再給下一塊），避免板子 buffer 爆掉掉資料
        while len(self.results) < len(chunks) and time.perf_counter() < deadline:
            now = time.perf_counter()
            for b in range(N_BOARDS):
                if self.busy[b] and now - self.job_of[b][1] > RESEND_S:   # 回覆遺失 → 收回來重送
                    job = self.job_of[b][0]
                    self.get_logger().warning(f'pico{b} 第 {job} 塊 {RESEND_S}s 沒回，重送')
                    self.busy[b], self.job_of[b] = False, None
                    if job not in self.results:
                        todo.appendleft(job)
                while todo and todo[0] in self.results:   # 已經有結果的不用再送
                    todo.popleft()
                if not self.busy[b] and todo:
                    job = todo.popleft()
                    self.send(b, job, chunks[job])
            rclpy.spin_once(self, timeout_sec=0.001)
        dt = time.perf_counter() - t0
        if len(self.results) < len(chunks):
            self.get_logger().error(f'逾時！只收到 {len(self.results)}/{len(chunks)} 塊')
        # 依 job_id 排序後合併（各板子回來的順序不一定！）
        parts = [self.results[k] for k in sorted(self.results)]
        if MERGE == "sorted":
            out = list(heapq.merge(*parts))
        else:
            out = [x for p in parts for x in p]
        return out, dt


def main():
    rclpy.init()
    node = Driver()
    node.wait_boards()
    data = make_data()
    out, dt = node.run(data)
    ok = (out == host_compute(data))
    print(f'boards={N_BOARDS} n={len(data)} chunk={CHUNK} time={dt*1000:.1f} ms '
          f'throughput={len(data)*4/dt/1024:.1f} KiB/s correct={ok}')
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
