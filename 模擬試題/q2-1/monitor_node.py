#!/usr/bin/env python3
"""monitor_node.py — 評分用的監看程式（不要改這個檔案）

訂閱 /sensor/filtered（QoS：reliable、depth 10），收到 COUNT 筆就把結果寫進 monitor.log 然後結束。
monitor.log 每行：seq avg 收到的時間（秒）
    python3 monitor_node.py [--count 40] [--timeout 30] [--log monitor.log]
"""
import argparse
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32MultiArray


class Monitor(Node):
    def __init__(self):
        super().__init__("monitor")
        self.rows = []
        self.sub = self.create_subscription(Int32MultiArray, "/sensor/filtered", self.on_msg, 10)

    def on_msg(self, msg):
        if len(msg.data) >= 2:
            self.rows.append((int(msg.data[0]), int(msg.data[1]), time.monotonic()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--timeout", type=float, default=30.0)
    ap.add_argument("--log", default="monitor.log")
    a = ap.parse_args()
    rclpy.init()
    node = Monitor()
    t_end = time.monotonic() + a.timeout
    try:
        while rclpy.ok() and len(node.rows) < a.count and time.monotonic() < t_end:
            rclpy.spin_once(node, timeout_sec=0.1)
    except KeyboardInterrupt:
        pass
    with open(a.log, "w") as f:
        for seq, avg, t in node.rows:
            f.write(f"{seq} {avg} {t:.4f}\n")
    print(f"monitor：收到 {len(node.rows)} 筆，寫入 {a.log}")
    node.destroy_node()
    rclpy.try_shutdown()


if __name__ == "__main__":
    main()
